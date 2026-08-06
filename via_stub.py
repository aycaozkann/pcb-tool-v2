#!/usr/bin/env python
"""Yüksek hızlı via stub rezonansı denetleyicisi — board dosyasından ÖLÇER.

Her hızlı-sinyal via'sında, via konumuna gerçekten değen aynı-net izlerin
katmanlarını bulur. Kullanılan en üst/en alt katmanın via bareli dışında
kalan iki parçasından uzunu rezonans açısından baskın açık stub sayılır:

    f_res = c / (4 * L_stub * sqrt(Dk_eff))

Kabul kapısı ``f_res > bw_margin * kanal_bant_genişliği`` biçimindedir.
KiCad 10 Python bağlaması stackup öğelerini okunabilir olarak açmadığı için
katman z-derinlikleri board S-expression'ındaki açık ``(setup (stackup ...))``
verisinden alınır. Bu veri yok/eksikse kalınlık uydurulmaz: NO_COVERAGE.

Bilinen sınırlar (sessiz güven üretmemek için):
- Blind/buried via sınırı TopLayer/BottomLayer ile eşlenir; karmaşık HDI
  yapılarında üretici build-up sırası ve lazer-via yapısı ayrıca doğrulanır.
- Back-drill/residual-stub bilgisi standart board nesnesinde güvenilir biçimde
  bulunmadığından modellenmez; back-drill varsa sonuç fab çizimiyle düzeltilir.
- Dk frekansa bağlı ve via çevresindeki gerçek etkin Dk, laminat Dk'sından
  farklıdır. Stackup Dk'sı kullanılan model ilk-tarama içindir; sign-off 3D EM'dir.
- Bir stub birden çok dielektrikten geçerse Dk uzunluk-ağırlıklı ortalanır.
- Bağlantı katmanı yalnız via merkezine değen track/arc uçlarından çıkarılır;
  yalnız zone/pad üzerinden bağlı bir katman görünmez ve via kapsam dışı kalır.
- İki tarafta stub varsa fiziksel olarak ayrı açık uçlardır; toplamları değil,
  daha uzun olanı (en düşük rezonansı veren taraf) değerlendirilir.
- ``--data-rate-gbps`` dönüşümü açık NRZ Nyquist modelidir:
  ``f_knee = data_rate / 2``. Gerçek yükselme süresi/bant genişliği biliniyorsa
  ``--channel-bw-ghz`` verilmelidir.

Kullanım:
    python via_stub.py <board.kicad_pcb> [--json out.json]
                       [--channel-bw-ghz 5.0 | --data-rate-gbps 10.0]
                       [--bw-margin 2.0] [--dk 4.0]
                       [--hs-net-regex '(?i)(usb|mipi|csi|rgmii|...)']

Çıkış kodu: 0 = FAIL yok, 1 = en az bir FAIL, 2 = çalıştırma hatası.
NO_COVERAGE, kardeş araç sözleşmesi gereği exit-code 0 olabilir; çağıran özet
sayacını da kontrol etmelidir.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MM = 1e6
C_MPS = 299_792_458.0


def mm(v: float) -> float:
    return v / MM


def xy(p):
    return (round(mm(p.x), 4), round(mm(p.y), 4))


class Finding(dict):
    def __init__(self, check, status, scanned, violations, detail):
        super().__init__(check=check, status=status, scanned=scanned,
                         violations=violations, detail=detail)


def result(check, scanned, violations, detail=""):
    if scanned == 0:
        return Finding(check, "NO_COVERAGE", 0, [],
                       detail or "incelenecek öğe yok")
    return Finding(check, "FAIL" if violations else "PASS", scanned,
                   violations, detail)


@dataclass
class StackItem:
    name: str
    kind: str
    thickness_mm: float
    dk: float | None
    z0_mm: float = 0.0
    z1_mm: float = 0.0


@dataclass
class Stackup:
    items: list[StackItem]
    copper_z_mm: dict[str, float]


def balanced_form(text: str, start: int) -> str | None:
    """`start` konumundaki parantezli S-expression formunu döndürür."""
    depth = 0
    quoted = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def direct_layer_forms(stack_form: str) -> list[str]:
    """Stackup'ın yalnız doğrudan çocuk `(layer ...)` formlarını çıkarır."""
    forms, depth, quoted, escaped, i = [], 0, False, False, 0
    while i < len(stack_form):
        ch = stack_form[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            i += 1
            continue
        if ch == '"':
            quoted = True
            i += 1
            continue
        if ch == "(":
            depth += 1
            if depth == 2 and stack_form.startswith("(layer ", i):
                form = balanced_form(stack_form, i)
                if form is None:
                    raise ValueError("stackup layer formu kapanmıyor")
                forms.append(form)
                i += len(form)
                depth -= 1
                continue
        elif ch == ")":
            depth -= 1
        i += 1
    return forms


def prop(form: str, name: str) -> str | None:
    m = re.search(rf"\({re.escape(name)}\s+(?:\"([^\"]+)\"|([^\s\)]+))\)", form)
    return (m.group(1) or m.group(2)) if m else None


def parse_stackup(path: str) -> tuple[Stackup | None, str]:
    """Açık KiCad stackup'tan bakır merkez z'lerini ve dielektrikleri çıkarır."""
    text = Path(path).read_text(encoding="utf-8")
    setup_at = text.find("(setup")
    if setup_at < 0:
        return None, "(setup ...) bulunamadı"
    setup = balanced_form(text, setup_at)
    if setup is None:
        return None, "(setup ...) formu kapanmıyor"
    stack_at = setup.find("(stackup")
    if stack_at < 0:
        return None, "açık (setup (stackup ...)) kalınlık verisi yok"
    stack = balanced_form(setup, stack_at)
    if stack is None:
        return None, "stackup formu kapanmıyor"

    parsed = []
    for form in direct_layer_forms(stack):
        nm = re.match(r'\(layer\s+"([^"]+)"', form)
        kind = prop(form, "type")
        thick = prop(form, "thickness")
        if not nm or not kind:
            continue
        if kind != "copper" and kind not in ("core", "prepreg"):
            continue
        if thick is None:
            return None, f"{nm.group(1)} kalınlığı stackup'ta yok"
        dk_s = prop(form, "epsilon_r")
        parsed.append(StackItem(nm.group(1), kind, float(thick),
                                float(dk_s) if dk_s is not None else None))

    copper_indices = [i for i, item in enumerate(parsed) if item.kind == "copper"]
    if len(copper_indices) < 2:
        return None, "stackup'ta en az iki açık bakır katman yok"
    parsed = parsed[copper_indices[0]:copper_indices[-1] + 1]
    z = 0.0
    copper_z = {}
    for item in parsed:
        item.z0_mm = z
        item.z1_mm = z + item.thickness_mm
        if item.kind == "copper":
            copper_z[item.name] = (item.z0_mm + item.z1_mm) / 2.0
        z = item.z1_mm
    return Stackup(parsed, copper_z), "stackup"


def path_dk(stackup: Stackup, z0: float, z1: float,
            user_dk: float | None) -> tuple[float | None, str]:
    if user_dk is not None:
        return user_dk, "kullanıcı verdi (--dk)"
    lo, hi = sorted((z0, z1))
    weighted = length = 0.0
    for item in stackup.items:
        if item.kind == "copper":
            continue
        overlap = max(0.0, min(hi, item.z1_mm) - max(lo, item.z0_mm))
        if overlap <= 0:
            continue
        if item.dk is None:
            return None, f"stackup: {item.name} epsilon_r eksik"
        weighted += overlap * item.dk
        length += overlap
    if length <= 0:
        return None, "stackup: stub yolunda dielektrik bulunamadı"
    return weighted / length, "stackup epsilon_r (uzunluk-ağırlıklı)"


def track_touches(track, pos) -> bool:
    try:
        points = (track.GetStart(), track.GetEnd())
    except Exception:
        return False
    return any(p.x == pos.x and p.y == pos.y for p in points)


def canonical_layer_name(layer_id: int) -> str:
    """Özel kullanıcı adı (örn. GND1) yerine stackup'taki In1.Cu adını ver.

    `import pcbnew` BİLEREK burada, fonksiyon içinde (2026-08-03, Madde 5):
    eskiden modül seviyesindeydi, yani `import via_stub` (örn. bir testte
    veya orkestrasyon kodunda) pcbnew kurulu olmayan HER ortamda anında
    `ModuleNotFoundError` ile çökerdi — dosyanın geri kalanı hiç
    çalıştırılamadan. `pcbnew_koprusu.py`'nin lazy-import deseniyle AYNI
    disiplin: modül HER ZAMAN import edilebilir, pcbnew'e ihtiyaç YALNIZCA
    gerçekten çağrıldığında ortaya çıkar (ve `main()`'de fail-closed
    NO_COVERAGE olarak yakalanır, ham `ModuleNotFoundError` sızmaz)."""
    import pcbnew

    return str(pcbnew.LayerName(layer_id))


def check_via_stubs(board, stackup: Stackup | None, stack_error: str,
                    hs_regex: str, channel_bw_ghz: float | None,
                    bw_source: str, margin: float, user_dk: float | None):
    rx = re.compile(hs_regex)
    hs_vias = [t for t in board.GetTracks()
               if t.GetClass() == "PCB_VIA" and rx.search(t.GetNetname() or "")]
    if channel_bw_ghz is None:
        return Finding("via_stub_resonance", "NO_COVERAGE", 0, [],
                       "--channel-bw-ghz veya --data-rate-gbps verilmedi")
    if stackup is None:
        return Finding("via_stub_resonance", "NO_COVERAGE", 0, [],
                       f"stackup kapsamı yok: {stack_error}; "
                       f"yüksek-hızlı via adayı={len(hs_vias)}")
    if not hs_vias:
        return result("via_stub_resonance", 0, [],
                      "hs-net-regex ile eşleşen via yok; aday=0")

    tracks_by_net = {}
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA":
            continue
        tracks_by_net.setdefault(track.GetNetCode(), []).append(track)

    scanned, violations, skipped = 0, [], []
    target_ghz = margin * channel_bw_ghz
    for via in hs_vias:
        pos = via.GetPosition()
        layer_names = sorted({canonical_layer_name(t.GetLayer())
                              for t in tracks_by_net.get(via.GetNetCode(), [])
                              if track_touches(t, pos)},
                             key=lambda n: stackup.copper_z_mm.get(n, math.inf))
        known = [n for n in layer_names if n in stackup.copper_z_mm]
        if len(known) < 2:
            skipped.append({"net": via.GetNetname(), "pos_mm": xy(pos),
                            "reason": "via merkezine değen en az iki bilinen track katmanı yok",
                            "touching_layers": layer_names})
            continue
        top_name = canonical_layer_name(via.TopLayer())
        bottom_name = canonical_layer_name(via.BottomLayer())
        if top_name not in stackup.copper_z_mm or bottom_name not in stackup.copper_z_mm:
            skipped.append({"net": via.GetNetname(), "pos_mm": xy(pos),
                            "reason": "via span katmanı stackup z-haritasında yok",
                            "via_layers": [top_name, bottom_name]})
            continue
        via_lo, via_hi = sorted((stackup.copper_z_mm[top_name],
                                 stackup.copper_z_mm[bottom_name]))
        used_lo = min(stackup.copper_z_mm[n] for n in known)
        used_hi = max(stackup.copper_z_mm[n] for n in known)
        if used_lo < via_lo - 1e-9 or used_hi > via_hi + 1e-9:
            skipped.append({"net": via.GetNetname(), "pos_mm": xy(pos),
                            "reason": "track katmanı via spanı dışında",
                            "touching_layers": known})
            continue

        top_stub = max(0.0, used_lo - via_lo)
        bottom_stub = max(0.0, via_hi - used_hi)
        if bottom_stub >= top_stub:
            stub, stub_z0, stub_z1, side = bottom_stub, used_hi, via_hi, "alt"
        else:
            stub, stub_z0, stub_z1, side = top_stub, via_lo, used_lo, "üst"
        scanned += 1
        if stub <= 1e-12:
            dk, dk_source, fres = None, "stub yok", math.inf
        else:
            dk, dk_source = path_dk(stackup, stub_z0, stub_z1, user_dk)
            if dk is None:
                scanned -= 1
                skipped.append({"net": via.GetNetname(), "pos_mm": xy(pos),
                                "reason": dk_source, "stub_mm": round(stub, 4)})
                continue
            fres = C_MPS / (4.0 * (stub / 1000.0) * math.sqrt(dk)) / 1e9
        if fres <= target_ghz:
            violations.append({
                "via_mm": xy(pos), "net": via.GetNetname(),
                "stub_mm": round(stub, 4), "stub_side": side,
                "top_stub_mm": round(top_stub, 4),
                "bottom_stub_mm": round(bottom_stub, 4),
                "f_res_ghz": round(fres, 4),
                "channel_bw_ghz": channel_bw_ghz,
                "target_f_res_ghz": round(target_ghz, 4),
                "dk": round(dk, 4), "dk_source": dk_source,
                "used_layers": known,
            })

    detail = (f"HS via adayı={len(hs_vias)}, ölçülebilen={scanned}, "
              f"kapsam dışı={len(skipped)}; BW={channel_bw_ghz:g} GHz "
              f"({bw_source}), marj={margin:g}, hedef f_res>{target_ghz:g} GHz. "
              "scanned sayısını her koşuda izle.")
    finding = result("via_stub_resonance", scanned, violations, detail)
    if skipped:
        finding["coverage_gaps"] = skipped
    return finding


def positive(name: str, value: float | None) -> None:
    if value is not None and value <= 0:
        raise ValueError(f"{name} sıfırdan büyük olmalı")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--json")
    bw = ap.add_mutually_exclusive_group()
    bw.add_argument("--channel-bw-ghz", type=float)
    bw.add_argument("--data-rate-gbps", type=float)
    ap.add_argument("--bw-margin", type=float, default=2.0)
    ap.add_argument("--dk", type=float)
    ap.add_argument("--hs-net-regex",
                    default=r"(?i)(usb|mipi|csi|rgmii|_d_?[pn]\b|_tx|_rx|clk)")
    a = ap.parse_args(argv)

    for name, value in (("--channel-bw-ghz", a.channel_bw_ghz),
                        ("--data-rate-gbps", a.data_rate_gbps),
                        ("--bw-margin", a.bw_margin), ("--dk", a.dk)):
        positive(name, value)
    if a.channel_bw_ghz is not None:
        channel_bw, bw_source = a.channel_bw_ghz, "kullanıcı verdi"
    elif a.data_rate_gbps is not None:
        channel_bw = a.data_rate_gbps / 2.0
        bw_source = "--data-rate-gbps'ten f_knee=data_rate/2 (NRZ Nyquist modeli)"
    else:
        channel_bw, bw_source = None, "verilmedi"

    try:
        import pcbnew
    except ImportError as exc:
        # Madde 5 (2026-08-03): pcbnew kurulu değilse sessiz crash yerine
        # NO_COVERAGE ile fail-closed rapor — dosyanın kendi "kardeş araç
        # sözleşmesi" (NO_COVERAGE exit-code 0 olabilir, çağıran özet
        # sayacına bakmalı) burada da uygulanır.
        findings = [Finding("via_stub_resonance", "NO_COVERAGE", 0, [],
                            f"pcbnew modülü bulunamadı ({exc}) — bu kontrol KiCad'in "
                            "gömülü Python'unda çalıştırılmalı; sessizce PASS/çökme "
                            "yerine NO_COVERAGE raporlandı.")]
        out = {
            "board": a.board, "channel_bw_ghz": channel_bw, "bandwidth_source": bw_source,
            "bw_margin": a.bw_margin, "dk_override": a.dk, "checks": findings,
            "summary": {s: sum(1 for f in findings if f["status"] == s)
                        for s in ("PASS", "FAIL", "NO_COVERAGE")},
        }
        text = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)
        if a.json:
            Path(a.json).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0

    board = pcbnew.LoadBoard(a.board)
    stackup, stack_status = parse_stackup(a.board)
    findings = [check_via_stubs(board, stackup, stack_status, a.hs_net_regex,
                                channel_bw, bw_source, a.bw_margin, a.dk)]
    out = {
        "board": a.board,
        "channel_bw_ghz": channel_bw,
        "bandwidth_source": bw_source,
        "bw_margin": a.bw_margin,
        "dk_override": a.dk,
        "checks": findings,
        "summary": {s: sum(1 for f in findings if f["status"] == s)
                    for s in ("PASS", "FAIL", "NO_COVERAGE")},
    }
    text = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)
    if a.json:
        Path(a.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if out["summary"]["FAIL"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # çalıştırma hatası sessizce PASS'a dönüşmesin
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
