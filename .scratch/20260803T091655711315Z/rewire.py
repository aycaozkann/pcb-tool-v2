"""rewire — label ile "uçan" bağlanmış şematiği PIN'DEN PIN'E kabloya çevirir.

Girdi şematiğin mevcut netlist'i **referanstır**: tüm label'lar ve eski teller
silinir, her net `sch_route` ile pinden pine ortogonal olarak yeniden çizilir,
sonra netlist tekrar alınıp **birebir aynı** olduğu kanıtlanır. Değiştiyse
dosya `.bak`'tan geri alınır.

    python3 rewire.py board.kicad_sch              # dry-run raporu
    python3 rewire.py board.kicad_sch --write      # .bak + yaz + netlist kanıtı
    python3 rewire.py board.kicad_sch --write --keep-names   # net başına 1 isim etiketi
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sch_route import Router, commit_stubs, junction_points, route_net  # noqa: E402
from sch_wire import (assert_kicad_closed, netlist_nets, num,  # noqa: E402
                      q, snap)
from wireify import _sym_placements  # noqa: E402
from sch_wire import load_lib_symbols, _block  # noqa: E402

BLOCK_RE = re.compile(r'^\t\((global_label|hierarchical_label|label|wire|junction|'
                      r'bus|bus_entry|no_connect) ', re.M)


def _u(path: str, tag: str) -> str:
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"rewire/{os.path.basename(path)}/{tag}"))


def _place_power(path, text, net, lib_id, pins, router, stub=2.54,
                 flag_pin: str | None = None):
    """Her pin'e bir güç sembolü (power:GND vb.) yerleştirir + pin'e tel çeker.

    Sembolün pin ankrajı, bizim pin çıkışımıza TAM oturmalı; rotasyon bunun için
    seçilir (sembolün dış yönü, bizim pin'in dış yönünün tersi olmalı).
    """
    from sch_wire import GRID, SchBuilder, _xform
    import math as _m
    proj = re.search(r'\(project "([^"]+)"', text)
    sheet = re.search(r'\(path "/([0-9a-fA-F-]+)"', text)
    sb = SchBuilder(project=proj.group(1) if proj else "project")
    if sheet:
        sb._sheet_uuid = sheet.group(1)
    src = load_lib_symbols("/usr/share/kicad/symbols/power.kicad_sym")
    sym = src[lib_id.split(":")[-1]]
    sb.embed(sym, lib_id)
    p0 = sym.pins[0]

    if flag_pin:
        sb.embed(src["PWR_FLAG"], "power:PWR_FLAG")

    syms, polys, errs, flag_pts = [], [], [], []
    for k, pr in enumerate(pins):
        is_flag = flag_pin == f"{pr.ref}-{pr.pin.number}"
        target = pr.out(stub * 2 if is_flag else stub)
        chosen = None
        for rot in (0, 90, 180, 270):
            ox, oy = _xform(_m.cos(_m.radians(p0.angle + 180)),
                            _m.sin(_m.radians(p0.angle + 180)), rot, "")
            if abs(ox + pr.dx) < 1e-6 and abs(oy + pr.dy) < 1e-6:
                chosen = rot
                break
        rot = 0 if chosen is None else chosen
        dx, dy = _xform(p0.x, p0.y, rot, "")
        ref = f"#PWR{len(syms) + 1:03d}_{net}"
        pl = sb.place(ref, lib_id, target[0] - dx, target[1] - dy, rot=rot,
                      value=net, hide_ref=True)
        got = pl.pin(p0.number).xy
        if got != target:
            errs.append(f"{net}: {pr.ref}-{pr.pin.number} güç sembolü ankrajı "
                        f"{got} != {target}")
            continue
        seg = [pr.xy, target]
        polys.append(seg)
        router.commit(seg, net)
        syms.append(sb._symbols[-1])

        if is_flag:
            # Kart-dışı besleme noktası: ray başına EN FAZLA BİR PWR_FLAG.
            # GND telinin ortasına dik bir sap + junction ile bağlanır.
            mid = (round(pr.x + pr.dx * stub, 2), round(pr.y + pr.dy * stub, 2))
            px, py = -pr.dy, pr.dx
            ftgt = (round(mid[0] + px * stub, 2), round(mid[1] + py * stub, 2))
            frot = 0
            for rot in (0, 90, 180, 270):
                ox, oy = _xform(_m.cos(_m.radians(p0.angle + 180)),
                                _m.sin(_m.radians(p0.angle + 180)), rot, "")
                if abs(ox + px) < 1e-6 and abs(oy + py) < 1e-6:
                    frot = rot
                    break
            fdx, fdy = _xform(p0.x, p0.y, frot, "")
            fpl = sb.place(f"#FLG001_{net}", "power:PWR_FLAG",
                           ftgt[0] - fdx, ftgt[1] - fdy, rot=frot,
                           value="PWR_FLAG", hide_ref=True)
            fseg = [mid, fpl.pin(p0.number).xy]
            polys.append(fseg)
            router.commit(fseg, net)
            syms.append(sb._symbols[-1])
            flag_pts.append(mid)
    return syms, polys, errs, dict(sb._embedded)


def rewire(path: str, write: bool = False, keep_names: bool = True,
           force: bool = False, nets_override: dict[str, list[str]] | None = None,
           power_nets: dict[str, str] | None = None,
           flag_pins: dict[str, str] | None = None,
           no_connect: list[str] | None = None) -> dict:
    """nets_override: {net: ['J1-A6', 'U1-1', ...]} — verilirse HEDEF netlist budur
    (mevcut bağlantı korunmaz, yenisi kurulur ve doğrulama buna göre yapılır).
    power_nets: {net: 'power:GND'} — bu net'ler tel yerine güç sembolü ile bağlanır.
    """
    power_nets = power_nets or {}
    flag_pins = flag_pins or {}
    no_connect = no_connect or []
    text = open(path, encoding="utf-8").read()
    libs = load_lib_symbols(path)
    placements = _sym_placements(text, libs)

    anchors = {}
    for pl in placements:
        for pin in pl.sym.pins:
            if pin.unit in (0, pl.unit):
                pr = pl.pin(pin.number)
                anchors[f"{pl.ref}-{pin.number}"] = pr

    before = netlist_nets(path)
    if nets_override:
        nets = {n: sorted(m) for n, m in nets_override.items() if len(m) > 1}
        target = {n: set(m) for n, m in nets.items()}
    else:
        nets = {n: sorted(m) for n, m in before.items()
                if not n.startswith("unconnected-") and len(m) > 1}
        target = None

    router = Router()
    net_of = {m: n for n, ms in nets.items() for m in ms}
    router.block_symbols(placements, keep={pr.xy for pr in anchors.values()})
    router.block_pins({pr.xy: pr for pr in anchors.values()}, net_of)

    # 1) pin listelerini hazırla
    prepared, missing = {}, []
    for net in nets:
        pins, seen_xy = [], set()
        for m in nets[net]:
            pr = anchors.get(m)
            if pr is None:
                missing.append(f"{net}: {m} ankraj yok")
                continue
            # Üst üste bindirilmiş (stacked) pinler aynı ankrajı paylaşır ve zaten
            # bağlıdır (ör. USB-C sembolünde 4 adet GND) -> tek temsilci al.
            if pr.xy not in seen_xy:
                seen_xy.add(pr.xy)
                pins.append(pr)
        if len(pins) >= 2:
            prepared[net] = pins

    # 2) Güç net'leri: uzun tel yerine her pin'e güç sembolü (spagetti önler)
    pwr_syms, pwr_libs, pwr_polys = [], {}, {}
    for net, lib_id in power_nets.items():
        if net not in prepared:
            continue
        pins = prepared.pop(net)
        syms, polys, errs2, libtxt = _place_power(
            path, text, net, lib_id, pins, router, flag_pin=flag_pins.get(net))
        pwr_syms += syms
        pwr_libs.update(libtxt)
        pwr_polys[net] = polys
        missing += errs2

    # 3) TÜM pin çıkışlarını önce rezerve et (yabancı net'in ucuna basmayı önler)
    polys_by_net = commit_stubs(router, prepared)

    # 3) büyük net'ler önce (yer darken sıkışmasınlar)
    errors = []
    for net in sorted(prepared, key=lambda n: -len(prepared[n])):
        polys, errs = route_net(router, net, prepared[net], pre_stubbed=True)
        polys_by_net[net] += polys
        errors += errs

    report = {
        "nets": len(nets),
        "routed_nets": len(polys_by_net),
        "wire_segments": sum(len(p) - 1 for ps in polys_by_net.values() for p in ps),
        "unroutable": len(errors),
        "missing_anchors": len(missing),
        "errors": errors[:10] + missing[:10],
    }
    if not write:
        return report

    assert_kicad_closed(path, force=force)

    # 1) eski bağlantı öğelerini sil (label / wire / junction / no_connect)
    out, i = [], 0
    for m in BLOCK_RE.finditer(text):
        if m.start() < i:
            continue
        blk = _block(text, m.start())
        out.append(text[i:m.start()])
        i = m.start() + len(blk) + 1        # bloğu ve ardındaki \n'i at
    out.append(text[i:])
    new = "".join(out)

    # yeni güç sembollerinin lib tanımlarını (lib_symbols ...) bloğuna ekle
    if pwr_libs:
        m = re.search(r"^\t\(lib_symbols\n", new, re.M)
        blk = _block(new, m.start())
        insert = "\n".join(pwr_libs.values()) + "\n"
        cut = m.start() + len(blk) - 1          # kapanış parantezinden önce
        while new[cut - 1] in "\n\t":
            cut -= 1
        new = new[:cut] + "\n" + insert.rstrip("\n") + new[cut:]

    # 2) yeni telleri + junction'ları ekle
    body = list(pwr_syms)
    all_polys = {**polys_by_net, **pwr_polys}
    for net, polys in all_polys.items():
        for pi, pts in enumerate(polys):
            for si, (a, b) in enumerate(zip(pts, pts[1:])):
                body.append(
                    "\t(wire\n"
                    f"\t\t(pts (xy {num(a[0])} {num(a[1])}) (xy {num(b[0])} {num(b[1])}))\n"
                    "\t\t(stroke (width 0) (type default))\n"
                    f"\t\t(uuid {q(_u(path, f'{net}/{pi}/{si}'))})\n\t)")
    for p in junction_points(all_polys):
        body.append("\t(junction\n"
                    f"\t\t(at {num(p[0])} {num(p[1])}) (diameter 0) (color 0 0 0 0)\n"
                    f"\t\t(uuid {q(_u(path, f'j/{p[0]},{p[1]}'))})\n\t)")
    for m in no_connect:                # bilinçli kullanılmayan pinler
        pr = anchors.get(m)
        if pr is None:
            missing.append(f"no_connect: {m} ankraj yok")
            continue
        body.append(f"\t(no_connect (at {num(pr.x)} {num(pr.y)}) "
                    f"(uuid {q(_u(path, 'nc/' + m))}))")

    if keep_names:                      # net başına 1 isim etiketi (tel ÜZERİNDE)
        # Etiketler net'ler arasında KAYDIRILIR: 2.54 mm aralıklı iki paralel
        # telin isimleri aynı x'te üst üste binerse hangi ismin hangi tele ait
        # olduğu okunamaz (D+/D- ters okundu sanılır).
        for ni, (net, polys) in enumerate(sorted(polys_by_net.items())):
            segs = [(a, b) for pts in polys for a, b in zip(pts, pts[1:])]
            a, b = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
            frac = 0.25 + 0.15 * (ni % 4)
            lp = (snap(a[0] + (b[0] - a[0]) * frac), snap(a[1] + (b[1] - a[1]) * frac))
            lo, hi = min(a[0], b[0]), max(a[0], b[0])
            loy, hiy = min(a[1], b[1]), max(a[1], b[1])
            if not (lo <= lp[0] <= hi and loy <= lp[1] <= hiy):
                lp = a                              # kısa segment: uca düş
            body.append(f"\t(label {q(net)}\n"
                        f"\t\t(at {num(lp[0])} {num(lp[1])} 0)\n"
                        "\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n"
                        f"\t\t(uuid {q(_u(path, f'n/{net}'))})\n\t)")

    tail = new.rstrip()
    assert tail.endswith(")")
    new = tail[:-1].rstrip("\n") + "\n" + "\n".join(body) + "\n)\n"

    shutil.copyfile(path, path + ".bak")
    open(path, "w", encoding="utf-8").write(new)

    after = netlist_nets(path)
    norm = lambda d: {k.lstrip("/"): {m for m in v if not m.startswith("#")}
                      for k, v in d.items()}
    a = norm(after)
    if target is not None:            # hedef net tablosuna göre doğrula
        b = {k: {m for m in v if not m.startswith("#")} for k, v in target.items()}
        a = {k: v for k, v in a.items() if not k.startswith("unconnected-")}
    else:                             # mevcut bağlantı korunmalı
        b = norm(before)
    changed = sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))
    report["netlist_identical"] = not changed
    report["netlist_diff"] = changed[:10]
    if changed:
        shutil.copyfile(path + ".bak", path)
        report["rolled_back"] = True
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sch")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--keep-names", action="store_true", default=True)
    ap.add_argument("--no-names", dest="keep_names", action="store_false")
    ap.add_argument("--force", action="store_true",
                    help="KiCad-açık kontrolünü atla — SADECE scratch kopyada")
    ap.add_argument("--nets", help="hedef netlist JSON: {nets:{...}, power_nets:{...}}")
    a = ap.parse_args()
    nets_override = power_nets = flag_pins = no_connect = None
    if a.nets:
        import json
        cfg = json.load(open(a.nets, encoding="utf-8"))
        nets_override = cfg["nets"]
        power_nets = cfg.get("power_nets")
        flag_pins = cfg.get("flag_pins")
        no_connect = cfg.get("no_connect")
    rep = rewire(a.sch, write=a.write, keep_names=a.keep_names, force=a.force,
                 nets_override=nets_override, power_nets=power_nets,
                 flag_pins=flag_pins, no_connect=no_connect)
    for k, v in rep.items():
        print(f"{k}: {v}")
    return 0 if (not a.write or rep.get("netlist_identical")) else 1


if __name__ == "__main__":
    sys.exit(main())
