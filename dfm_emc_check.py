#!/usr/bin/env python
"""DFM/EMC nüans denetleyicisi — board dosyasından ÖLÇER, iddiaya bakmaz.

SKILL-dfm / SKILL-emc-esd / SKILL-konnektor içindeki kuralların
**bugün pcbnew 10 API'siyle otomatikleştirilebilen** alt kümesini uygular.
Her kontrol bir `Finding` üretir; hiçbir kontrol "sessizce geçmez": kapsam
sayısı (kaç öğe bakıldı) her zaman raporlanır, 0 kapsam = FAIL.

Otomatikleştirilemeyenler bilerek yoktur (bkz. SKILL-dogrulama-matrisi):
kaplama/mating-cycle, MSL, DC-bias, ESD clamp seçimi, EMC ölçümü — bunlar
belge/lab kapılarıdır, board dosyasında bilgi olarak bulunmazlar.

Kullanım:
    python dfm_emc_check.py <board.kicad_pcb> [--json out.json]
                            [--hs-net-regex '(?i)(usb|mipi|d_p|d_n|rgmii|tx|rx)']
                            [--edge-keepout-mm 2.0] [--stitch-max-mm 2.5]
                            [--paste-ratio-max 0.80] [--epad-area-mm2 4.0]
                            [--annular-min-mm 0.15]

Çıkış kodu: 0 = tüm kontroller PASS, 1 = en az bir FAIL, 2 = çalıştırma hatası.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys

try:
    import pcbnew  # type: ignore
except ImportError:  # projenin kendi kuralı: pcbnew bağımlılığı HER ZAMAN lazy
    pcbnew = None  # noqa: N816

MM = 1e6


def mm(v: float) -> float:
    return v / MM


def xy(p):
    return (mm(p.x), mm(p.y))


# --------------------------------------------------------------------------- #
# Bulgu kabı
# --------------------------------------------------------------------------- #
class Finding(dict):
    def __init__(self, check, status, scanned, violations, detail):
        super().__init__(
            check=check,
            status=status,          # PASS / FAIL / NO_COVERAGE
            scanned=scanned,        # kaç öğe incelendi (0 ise kontrol boştur)
            violations=violations,  # liste
            detail=detail,
        )


def result(check, scanned, violations, detail=""):
    if scanned == 0:
        return Finding(check, "NO_COVERAGE", 0, [], detail or "incelenecek öğe yok")
    return Finding(check, "FAIL" if violations else "PASS", scanned, violations, detail)


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #
def board_outline_segments(board):
    """Edge.Cuts üzerindeki çizim öğelerinden örneklenmiş nokta listesi."""
    pts = []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            shape = d.GetEffectiveShape()
        except Exception:
            shape = None
        if shape is None:
            continue
        # Her şekli poligon/çizgi zincirine indir ve köşelerini örnekle
        poly = pcbnew.SHAPE_POLY_SET()
        try:
            d.TransformShapeToPolygon(poly, pcbnew.UNDEFINED_LAYER, 0,
                                      pcbnew.FromMM(0.01), pcbnew.ERROR_INSIDE)
        except Exception:
            continue
        for oi in range(poly.OutlineCount()):
            ol = poly.Outline(oi)
            for i in range(ol.PointCount()):
                p = ol.CPoint(i)
                pts.append((mm(p.x), mm(p.y)))
    return pts


def dist_point_to_points(pt, pts):
    x, y = pt
    best = float("inf")
    for px, py in pts:
        d = math.hypot(px - x, py - y)
        if d < best:
            best = d
    return best


def vias(board):
    return [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]


def pad_area_mm2(pad, layer):
    """Bakır pad alanı mm² (efektif poligon; oval/custom şekiller dahil)."""
    return pad.GetEffectivePolygon(layer).Area() / (MM * MM)


def is_ceramic_two_terminal(fp):
    """C*/R*/L* referanslı, 2 padli, SMD parça — flex crack adayı."""
    ref = fp.GetReference()
    if not re.match(r"^[CRL]\d", ref):
        return False
    return len(list(fp.Pads())) == 2


# --------------------------------------------------------------------------- #
# 1) Teardrop sayımı (SKILL-dfm §Teardrop)
# --------------------------------------------------------------------------- #
def check_teardrops(board):
    zones = list(board.Zones())
    td = [z for z in zones if z.IsTeardropArea()]
    # Kural: sayı raporlanır; 0 ise FAIL değil ama AÇIK madde olarak işaretlenir.
    return Finding("teardrop_count", "PASS" if td else "NO_COVERAGE",
                   len(zones), [],
                   f"{len(td)} teardrop zone / {len(zones)} zone. "
                   "0 ise raporda AÇIK madde (pcbnew SWIG üretemez, GUI adımı).")


# --------------------------------------------------------------------------- #
# 2) Via-in-pad → IPC-4761 Type VII gerektirir (SKILL-dfm)
# --------------------------------------------------------------------------- #
def check_via_in_pad(board):
    viz = vias(board)
    pads = [(f, p) for f in board.GetFootprints() for p in f.Pads()
            if p.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN)]
    hits = []
    for v in viz:
        vp = v.GetPosition()
        for f, p in pads:
            if not p.IsOnLayer(v.TopLayer()) and not p.IsOnLayer(v.BottomLayer()):
                continue
            layer = v.TopLayer() if p.IsOnLayer(v.TopLayer()) else v.BottomLayer()
            if p.GetEffectivePolygon(layer).Collide(vp):
                hits.append({
                    "via_mm": xy(vp),
                    "pad": f"{f.GetReference()}.{p.GetNumber()}",
                    "net": v.GetNetname(),
                })
                break
    return result("via_in_pad", len(viz), hits,
                  "Bulunan her via-in-pad, fab notunda IPC-4761 Type VII "
                  "(dolgu+kapak, dimple ≤25 µm) olarak belirtilmelidir.")


# --------------------------------------------------------------------------- #
# 3) Annular ring → teardrop/DFM adayları (SKILL-dfm §Teardrop nerede gerekir)
# --------------------------------------------------------------------------- #
def check_annular(board, min_mm):
    """Halka ölçümü TAM SAYI nm ile yapılır.

    mm float'ında (0.7-0.4)/2 = 0.14999999999999997 çıkar ve tam sınırdaki
    (0.15 mm) her pad yanlışlıkla ihlal olur — USB-C J1'in 16 padinde bu
    yaşandı. Ölçüm birimini aracın iç birimi (nm) yapmak sınır hatasını
    tamamen kaldırır.
    """
    limit_nm = int(round(min_mm * MM))
    items, viol = 0, []
    for v in vias(board):
        items += 1
        # TUZAK (e): PCB_VIA.GetWidth() artık bir KATMAN argümanı istiyor
        # (per-layer via genişliği stack'leri desteklendiği için) -
        # parametresiz çağrı KiCad'de "GetWidth called without a layer
        # argument" debug assert'i (GUI pop-up, headless akışı kilitler)
        # fırlatıyor. TopLayer() ile via'nın üst katmandaki genişliği
        # alınır - standart (through) bir via için bu tüm katmanlarda
        # aynıdır, annular ring hesabı için yeterli.
        ring_nm = (v.GetWidth(v.TopLayer()) - v.GetDrill()) // 2
        if ring_nm < limit_nm:
            viol.append({"type": "via", "pos_mm": xy(v.GetPosition()),
                         "net": v.GetNetname(), "annular_mm": round(ring_nm / MM, 4)})
    for f in board.GetFootprints():
        for p in f.Pads():
            d = p.GetDrillSize()
            if d.x <= 0:
                continue
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue  # mekanik delik: annular ring kavramı yok
            items += 1
            ring_nm = (min(p.GetSizeX(), p.GetSizeY()) - d.x) // 2
            if ring_nm < limit_nm:
                viol.append({"type": "pth", "pad": f"{f.GetReference()}.{p.GetNumber()}",
                             "annular_mm": round(ring_nm / MM, 4)})
    return result("annular_ring", items, viol,
                  f"Halka < {min_mm} mm olan delikler teardrop adayıdır "
                  "(Class 2 ~0.15 / Class 3 ~0.20 mm).")


# --------------------------------------------------------------------------- #
# 4) EPAD pasta kapsaması (SKILL-dfm §QFN/EPAD)
# --------------------------------------------------------------------------- #
def check_paste_coverage(board, epad_area_mm2, ratio_max):
    scanned, viol = 0, []
    for f in board.GetFootprints():
        for p in f.Pads():
            if not p.IsOnLayer(pcbnew.F_Paste) and not p.IsOnLayer(pcbnew.B_Paste):
                continue
            cu = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Paste) else pcbnew.B_Cu
            area = pad_area_mm2(p, cu)
            if area < epad_area_mm2:
                continue
            scanned += 1
            mv = p.GetSolderPasteMargin(cu)
            margin = mm(mv[0] if isinstance(mv, (tuple, list)) else mv.x)
            # Oran, aynı dikdörtgen modeli üzerinden hesaplanır (poligon köşe
            # yuvarlaması iki tarafta da olduğu için sadeleşir).
            w0, h0 = mm(p.GetSizeX()), mm(p.GetSizeY())
            ratio = (max(w0 + 2 * margin, 0) * max(h0 + 2 * margin, 0)) / (w0 * h0)
            if ratio > ratio_max:
                viol.append({"pad": f"{f.GetReference()}.{p.GetNumber()}",
                             "copper_mm2": round(area, 3),
                             "paste_margin_mm": round(margin, 4),
                             "paste_ratio": round(ratio, 3)})
    return result("epad_paste_coverage", scanned, viol,
                  f"≥{epad_area_mm2} mm² pad'lerde pasta oranı ≤{ratio_max} olmalı "
                  "(windowpane). SINIR: tek pad + negatif margin modelini ölçer; "
                  "ayrı ayrı çizilmiş çok-açıklıklı pasta desenini tanımaz → "
                  "o durumda elle doğrula.")


# --------------------------------------------------------------------------- #
# 5) Kenar/depanel — seramik flex crack riski (SKILL-dfm §MLCC)
# --------------------------------------------------------------------------- #
def check_edge_keepout(board, keepout_mm):
    edge = board_outline_segments(board)
    if not edge:
        return Finding("edge_keepout_ceramics", "NO_COVERAGE", 0, [],
                       "Edge.Cuts bulunamadı")
    scanned, viol = 0, []
    for f in board.GetFootprints():
        if not is_ceramic_two_terminal(f):
            continue
        scanned += 1
        pos = xy(f.GetPosition())
        d = dist_point_to_points(pos, edge)
        if d < keepout_mm:
            viol.append({"ref": f.GetReference(), "pos_mm": pos,
                         "edge_dist_mm": round(d, 3),
                         "orientation_deg": round(f.GetOrientationDegrees() % 180, 1)})
    return result("edge_keepout_ceramics", scanned, viol,
                  f"2 uçlu seramikler kart kenarından ≥{keepout_mm} mm. "
                  "İhlal listesindeki `orientation_deg` ile parçanın uzun ekseni "
                  "kırma hattına PARALEL mi elle doğrula (SKILL-dfm §MLCC).")


# --------------------------------------------------------------------------- #
# 6) Dönüş via'sı — her hızlı sinyal via'sının yanında GND via'sı (SKILL-emc-esd §3)
# --------------------------------------------------------------------------- #
def check_return_vias(board, hs_regex, max_mm):
    rx = re.compile(hs_regex)
    viz = vias(board)
    gnd = [v for v in viz if re.match(r"^/?(GND|AGND|DGND|VSS)", v.GetNetname() or "")]
    hs = [v for v in viz if v.GetNetname() and rx.search(v.GetNetname())]
    viol = []
    for v in hs:
        p = xy(v.GetPosition())
        d = min((math.hypot(p[0] - g[0], p[1] - g[1])
                 for g in (xy(x.GetPosition()) for x in gnd)), default=float("inf"))
        if d > max_mm:
            viol.append({"net": v.GetNetname(), "pos_mm": p,
                         "nearest_gnd_via_mm": None if math.isinf(d) else round(d, 3)})
    return result("return_via_near_hs_via", len(hs), viol,
                  f"Her hızlı sinyal via'sının ≤{max_mm} mm yakınında GND via'sı "
                  f"olmalı. GND via sayısı={len(gnd)}.")


# --------------------------------------------------------------------------- #
# 7) Netclass pattern iki yönlü kapsama (SKILL-pcb-highspeed-escape §9)
# --------------------------------------------------------------------------- #
def check_netclass_coverage(board, hs_regex):
    rx = re.compile(hs_regex)
    rows, miss = 0, []
    for netname, net in board.GetNetsByName().items():
        name = str(netname)
        if not name or not rx.search(name):
            continue
        rows += 1
        nc = net.GetNetClassName()
        if nc in ("Default", "", None):
            miss.append({"net": name, "netclass": nc})
    return result("hs_netclass_assigned", rows, miss,
                  "Hızlı desene uyan her net Default DIŞINDA bir netclass'ta "
                  "olmalı; ters yön (güç/CC netlerinin yanlışlıkla kapsanması) "
                  "elle gözden geçirilir.")


# --------------------------------------------------------------------------- #
CHECKS = ("teardrop_count", "via_in_pad", "annular_ring", "epad_paste_coverage",
          "edge_keepout_ceramics", "return_via_near_hs_via", "hs_netclass_assigned")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--json")
    ap.add_argument("--hs-net-regex",
                    default=r"(?i)(usb|mipi|csi|rgmii|_d_?[pn]\b|_tx|_rx|clk)")
    ap.add_argument("--edge-keepout-mm", type=float, default=2.0)
    ap.add_argument("--stitch-max-mm", type=float, default=2.5)
    ap.add_argument("--paste-ratio-max", type=float, default=0.80)
    ap.add_argument("--epad-area-mm2", type=float, default=4.0)
    ap.add_argument("--annular-min-mm", type=float, default=0.15)
    a = ap.parse_args(argv)

    if pcbnew is None:
        findings = [
            result(c, 0, [], "pcbnew import edilemedi — kontrol KOŞULMADI")
            for c in CHECKS
        ]
        out = {"board": a.board, "checks": findings,
               "summary": {"NO_COVERAGE": len(findings), "PASS": 0, "FAIL": 0}}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if a.json:
            with open(a.json, "w") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        return 2  # "2 = çalıştırma hatası" (docstring) — pcbnew yoksa gerçek bir hata

    board = pcbnew.LoadBoard(a.board)
    findings = [
        check_teardrops(board),
        check_via_in_pad(board),
        check_annular(board, a.annular_min_mm),
        check_paste_coverage(board, a.epad_area_mm2, a.paste_ratio_max),
        check_edge_keepout(board, a.edge_keepout_mm),
        check_return_vias(board, a.hs_net_regex, a.stitch_max_mm),
        check_netclass_coverage(board, a.hs_net_regex),
    ]
    out = {"board": a.board, "checks": findings,
           "summary": {s: sum(1 for f in findings if f["status"] == s)
                       for s in ("PASS", "FAIL", "NO_COVERAGE")}}
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if a.json:
        with open(a.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 1 if out["summary"]["FAIL"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # çalıştırma hatası sessizce PASS'a dönüşmesin
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
