"""wireify — "uçan net" şematiğini gerçek wire'lı hale getirir.

Sorun: bazı üretici script'ler label'ı doğrudan pin ankrajının üstüne koyar.
Netlist doğru çıkar ama şematikte HİÇ ÇİZGİ YOKTUR: insan denetleyemez,
review edilemez, hiyerarşi okunmaz (bkz. usb-hs-breakout: 0 wire / 27 label).

Bu araç her pin-üstü label'ı pin'den `dist` kadar dışarı taşır ve arasına
`(wire ...)` koyar. **Netlist değişmemelidir** — script bunu kendisi
kicad-cli ile önce/sonra karşılaştırarak kanıtlar.

    python3 wireify.py board.kicad_sch            # dry-run (rapor)
    python3 wireify.py board.kicad_sch --write    # .bak + yaz + netlist kanıtı
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sch_wire import (STUB, Placed, _block, _xform, assert_kicad_closed,  # noqa: E402
                      find, find_all, load_lib_symbols, netlist_nets, num,
                      parse_sexpr, snap, unquote)

LABEL_RE = re.compile(r'\((global_label|hierarchical_label|label) "')
SYMBOL_RE = re.compile(r'^\t\(symbol\n', re.M)


def _sym_placements(text: str, libs: dict) -> list[Placed]:
    out = []
    for m in SYMBOL_RE.finditer(text):
        raw = _block(text, m.start())
        t = parse_sexpr(raw)
        lib_id_node = find(t, "lib_id")
        at = find(t, "at")
        if not (lib_id_node and at):
            continue
        lib_id = unquote(lib_id_node[1])
        ref = None
        for p in find_all(t, "property"):
            if unquote(p[1]) == "Reference":
                ref = unquote(p[2])
        mirror = find(t, "mirror")
        unit = find(t, "unit")
        sym = libs.get(lib_id)
        if sym is None or ref is None:
            continue
        out.append(Placed(ref, lib_id, float(at[1]), float(at[2]),
                          float(at[3]) if len(at) > 3 else 0.0,
                          mirror[1] if mirror else "",
                          int(unit[1]) if unit else 1, sym))
    return out


def wireify(path: str, dist: float = STUB, write: bool = False,
            force: bool = False) -> dict:
    text = open(path, encoding="utf-8").read()
    libs = load_lib_symbols(path)                       # gömülü lib_symbols
    anchors: dict[tuple[float, float], object] = {}
    for pl in _sym_placements(text, libs):
        for pin in pl.sym.pins:
            if pin.unit not in (0, pl.unit):
                continue
            try:
                pr = pl.pin(pin.number)
            except KeyError:
                continue
            anchors[(round(pr.x, 2), round(pr.y, 2))] = pr

    edits, wires = [], []
    hits = misses = 0
    for m in LABEL_RE.finditer(text):
        raw = _block(text, m.start())
        t = parse_sexpr(raw)
        at = find(t, "at")
        if not at:
            continue
        key = (round(float(at[1]), 2), round(float(at[2]), 2))
        pr = anchors.get(key)
        if pr is None:
            misses += 1
            continue
        hits += 1
        nx, ny = pr.out(dist)
        # etiketi dışarı taşı; açıyı pin'in dış yönüne çevir
        old_at = f"(at {at[1]} {at[2]}" + (f" {at[3]}" if len(at) > 3 else "")
        new_at = f"(at {num(nx)} {num(ny)} {num(pr.out_angle)}"
        idx = raw.index(old_at)
        edits.append((m.start() + idx, m.start() + idx + len(old_at), new_at))
        wires.append((key, (nx, ny), f"{pr.ref}-{pr.pin.number}"))

    body = "\n".join(
        "\t(wire\n"
        f"\t\t(pts (xy {num(a[0])} {num(a[1])}) (xy {num(b[0])} {num(b[1])}))\n"
        "\t\t(stroke (width 0) (type default))\n"
        f"\t\t(uuid \"{_det_uuid(path, tag)}\")\n\t)"
        for a, b, tag in wires)

    report = {"labels_on_pins": hits, "labels_elsewhere": misses,
              "wires_added": len(wires),
              "wires_before": text.count("(wire\n") + text.count("(wire ")}

    if not write:
        return report

    assert_kicad_closed(path, force=force)  # force: SADECE scratch kopya için
    before = netlist_nets(path)
    new = text
    for s, e, rep in sorted(edits, reverse=True):
        new = new[:s] + rep + new[e:]
    tail = new.rstrip()
    assert tail.endswith(")")
    new = tail[:-1].rstrip("\n") + "\n" + body + "\n)\n"

    shutil.copyfile(path, path + ".bak")
    open(path, "w", encoding="utf-8").write(new)
    after = netlist_nets(path)

    changed = {k for k in set(before) | set(after)
               if before.get(k) != after.get(k)}
    report["netlist_identical"] = not changed
    report["netlist_diff"] = sorted(changed)
    if changed:                                          # güvenli geri alma
        shutil.copyfile(path + ".bak", path)
        report["rolled_back"] = True
    return report


def _det_uuid(path: str, tag: str) -> str:
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wireify/{os.path.basename(path)}/{tag}"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sch")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dist", type=float, default=STUB)
    ap.add_argument("--force", action="store_true",
                    help="KiCad-açık kontrolünü atla — SADECE scratch kopyada")
    a = ap.parse_args()
    rep = wireify(a.sch, dist=a.dist, write=a.write, force=a.force)
    for k, v in rep.items():
        print(f"{k}: {v}")
    if a.write and not rep.get("netlist_identical"):
        print("HATA: netlist değişti -> .bak'tan geri alındı")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
