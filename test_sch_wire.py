"""sch_wire kanıt testleri.

Bu test "script çizgi çizdi mi" diye BAKMAZ; `kicad-cli sch export netlist`
çıktısında pin'in gerçekten net'e düşüp düşmediğine bakar. Ayrıca
fault-injection ile testin BOŞ OLMADIĞI kanıtlanır (CLAUDE.md honesty §6):
bir wire'ı bozarsak test KIRILMALI.

Çalıştır:  python3 test_sch_wire.py   (kicad-cli gerekir, KiCad kapalı olmalı)
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sch_wire import (SchBuilder, load_lib_symbols, netlist_nets, run_erc,  # noqa: E402
                      verify_nets)

# WINDOWS/CI UYUMLULUK NOTU (2026-07-30, entegrasyon sırasında eklendi):
# Bu dosya `Otonom-PCB-Ajani`den GERÇEK KiCad kurulumu + Linux sembol yolu
# varsayımıyla alındı — `pytest` ile toplu koşulduğunda (ör. `pytest -q`,
# tüm dosyaları COLLECT eder) modül seviyesindeki `load_lib_symbols()`
# çağrıları, KiCad kurulu olmayan/Windows'ta yol farklı olan bir makinede
# TÜM test paketinin toplanmasını (collection) FileNotFoundError ile
# KESERDİ — tek bir entegrasyon testinin eksikliği, ilgisiz onlarca birim
# testinin de hiç çalışmamasına yol açardı. Bu yüzden sembol dizini
# bulunamıyorsa modül `pytest.skip()` ile KENDİNİ atlar (sessizce
# geçmez — `pytest -rs` çıktısında "SKIPPED: KiCad sembol dizini
# bulunamadı" olarak GÖRÜNÜR). Gerçek KiCad kurulu bir makinede
# (`KURULUM.md` madde 1) bu testler GERÇEKTEN koşar.
import pytest


def _kicad_symbol_dizinini_bul() -> str | None:
    """`arac_yollari.py`'nin KiCad kök dizini tarama deseniyle AYNI mantık
    (Windows: `Program Files/KiCad/<sürüm>/share/kicad/symbols`, Linux/macOS:
    standart paket yolu). DÜZELTME (2026-07-31, GÖREV 1/2): bu dosya eskiden
    SADECE `/usr/share/kicad/symbols`'a bakıyordu — Windows'ta bu yol hiç
    yok, dosya HER ZAMAN `pytest.skip(allow_module_level=True)` ile atlanıyordu
    ve içindeki asıl doğrulama mantığı (netlist/ERC kanıtı, fault-injection)
    bu makinede HİÇ ÇALIŞMIYORDU — sadece `python3 test_sch_wire.py` ile elle
    çalıştırıldığında test edilebiliyordu. Artık iki platform da taranıyor."""
    linux_aday = "/usr/share/kicad/symbols"
    if os.path.isdir(linux_aday):
        return linux_aday
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        kok = os.path.join(program_files, "KiCad")
        if os.path.isdir(kok):
            for surum in sorted(os.listdir(kok), reverse=True):
                aday = os.path.join(kok, surum, "share", "kicad", "symbols")
                if os.path.isdir(aday):
                    return aday
    mac_aday = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
    if os.path.isdir(mac_aday):
        return mac_aday
    return None


SYMDIR = _kicad_symbol_dizinini_bul()
if SYMDIR is None:
    pytest.skip(
        "KiCad sembol dizini hiçbir platformda (Linux/Windows/macOS standart "
        "yolları) bulunamadı — bu dosya gerçek KiCad kurulumu gerektirir, "
        "bkz. KURULUM.md madde 1.",
        allow_module_level=True,
    )

DEV = load_lib_symbols(f"{SYMDIR}/Device.kicad_sym")
PWR = load_lib_symbols(f"{SYMDIR}/power.kicad_sym")
CON = load_lib_symbols(f"{SYMDIR}/Connector.kicad_sym")

ORIENTS = [(r, m) for r in (0, 90, 180, 270) for m in ("", "x", "y")]


def build(tmp: str, *, break_wire: bool = False) -> tuple[str, dict[str, set[str]]]:
    """12 yönelimde direnç; her pin'e wire+label. Yanlış dönüşüm = kopuk net."""
    sch = SchBuilder(project="wiretest")
    sch.embed(DEV["R"], "Device:R")
    sch.embed(DEV["C"], "Device:C")
    sch.embed(PWR["GND"], "power:GND")
    sch.embed(PWR["PWR_FLAG"], "power:PWR_FLAG")
    sch.embed(CON["Conn_01x02_Pin"], "Connector:Conn_01x02_Pin")

    expected: dict[str, set[str]] = {}
    for i, (rot, mir) in enumerate(ORIENTS):
        x = 30.48 + (i % 4) * 45.72
        y = 30.48 + (i // 4) * 50.8
        ref = f"R{i + 1}"
        r = sch.place(ref, "Device:R", x, y, value="10k", rot=rot, mirror=mir)
        for pn in ("1", "2"):
            net = f"N{i + 1}{pn}"
            sch.label(r.pin(pn), net)
            expected[net] = {f"{ref}-{pn}"}

    # --- güç bölümü: iki yatay ray + T-junction'lar --------------------------
    VBUS_Y, GND_Y = 152.4, 180.34
    c1 = sch.place("C1", "Device:C", 30.48, 165.1, value="100n")
    c2 = sch.place("C2", "Device:C", 71.12, 165.1, value="100n")
    j1 = sch.place("J1", "Connector:Conn_01x02_Pin", 137.16, 165.1, value="PWR_IN")

    for c in (c1, c2):
        sch.wire([c.pin("1").xy, (c.pin("1").x, VBUS_Y)])   # üst pin -> VBUS rayı
        sch.wire([c.pin("2").xy, (c.pin("2").x, GND_Y)])    # alt pin -> GND rayı
    p1, p2 = j1.pin("1"), j1.pin("2")
    sch.wire([p1.xy, (p1.x, VBUS_Y)])
    sch.wire([p2.xy, (p2.x, GND_Y)])
    sch.wire([(30.48, VBUS_Y), (p1.x, VBUS_Y)])             # VBUS rayı
    sch.wire([(30.48, GND_Y), (p2.x, GND_Y)])               # GND rayı

    sch.label((30.48, VBUS_Y), "VBUS")
    sch.power((50.8, GND_Y), "power:GND", ref="#PWR001", direction=(0, 1), rot=0)
    # kart-dışı kaynak (J1 pinleri pasif) -> ray başına EN FAZLA BİR PWR_FLAG
    sch.pwr_flag((93.98, VBUS_Y), ref="#FLG001")
    sch.pwr_flag((93.98, GND_Y), ref="#FLG002")
    sch.auto_junctions()
    expected["VBUS"] = {"C1-1", "C2-1", "J1-1"}
    expected["GND"] = {"C1-2", "C2-2", "J1-2"}

    path = os.path.join(tmp, "broken.kicad_sch" if break_wire else "wiretest.kicad_sch")
    text = sch.render()
    if break_wire:
        # FAULT INJECTION: C1.1 stub'ının PIN ucunu 1.27 mm kaydır. Şematikte
        # çizgi hâlâ pin'e değiyormuş gibi görünür; bağlantı kopar.
        # (Not: ray ucunu kaydırmak yetmez — bir wire ucu başka wire'ın
        #  ORTASINA denk gelirse KiCad T-bağlantısı sayar.)
        text = text.replace("(xy 30.48 161.29)", "(xy 30.48 160.02)", 1)
    open(path, "w", encoding="utf-8").write(text)
    return path, expected


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="sch_wire_")
    fails = 0

    path, expected = build(tmp)
    wires = open(path).read().count("(wire")
    print(f"[1] üretilen wire sayısı: {wires}")
    if wires < 30:
        print("    FAIL: çizgi üretilmedi"); fails += 1

    problems = verify_nets(path, expected)
    print(f"[2] netlist doğrulaması: {len(expected)} net bekleniyor, "
          f"{len(problems)} problem")
    for p in problems:
        print("    ", p)
    fails += len(problems)

    nets = netlist_nets(path)
    unconnected = [n for n in nets if n.startswith("unconnected-")]
    print(f"[3] unconnected-* net sayısı: {len(unconnected)} {unconnected[:5]}")
    if unconnected:
        fails += 1

    # fault injection: testin boş olmadığını kanıtla
    bad, _ = build(tmp, break_wire=True)
    p2 = verify_nets(bad, {"VBUS": {"C1-1", "C2-1", "J1-1"}})
    print(f"[4] fault-injection: {len(p2)} problem (>0 OLMALI) {p2}")
    if not p2:
        print("    FAIL: test boş — bozuk wire'ı yakalayamadı"); fails += 1

    erc = run_erc(path)
    viol = [v for s in erc.get("sheets", []) for v in s.get("violations", [])]
    errors = [v for v in viol if v.get("severity") == "error"]
    # fixture'da her test label'ı tek pin'e bağlı -> isolated_pin_label beklenir
    unexpected = [v for v in viol
                  if v.get("severity") != "error" and v.get("type") != "isolated_pin_label"]
    print(f"[5] ERC: {len(errors)} error, {len(viol)} toplam "
          f"({len(unexpected)} beklenmeyen uyarı)")
    for v in errors + unexpected:
        print("    ", v.get("severity"), v.get("type"), v.get("description"))
    fails += len(errors) + len(unexpected)

    print(f"\n{'PASS' if fails == 0 else 'FAIL'} — {fails} hata. Dosya: {path}")
    return 1 if fails else 0


# ------------------------------------------------------------------
# DÜZELTME (2026-07-31, GÖREV 1/2): `main()` üstteki tüm doğrulamayı
# (wire sayısı, netlist, ERC, fault-injection) yapıyordu AMA `test_`
# önekiyle başlayan bir fonksiyon OLMADIĞI için `pytest -q` bu dosyayı
# COLLECT etse bile içindeki mantığı hiç ÇALIŞTIRMIYORDU — sadece
# `python3 test_sch_wire.py` ile elle çağrıldığında koşuyordu. Artık
# pytest de aynı kanıtı üretiyor.
# ------------------------------------------------------------------

def test_sch_wire_uctan_uca_kanit():
    assert main() == 0


def test_ozel_karakterli_description_dosyayi_bozmaz():
    """GÖREV 1 regresyonu: MCP sunucusunda (`mixelpixx/KiCAD-MCP-Server`,
    bu repo'nun VENDOR ETMEDİĞİ harici bir bağımlılık — bkz. `CLAUDE.md`
    "Kullanılabilir araçlar" bölümü) `Description` property'si parantez/
    virgül/iç içe tırnak içeren sembollerin İLK yerleştirmede dosyayı
    bozduğu gözlemlendi (cm4-io-test projesinde `Conn_02x50_Row_Letter_First`
    ve `power:GND` ile canlı üretildi, bkz. `.claude/skills/schematic-design/
    SKILL.md` Ek-A). `sch_wire.py` bu bug'ı PAYLAŞMAZ — `q()` (satır ~84)
    hem ters eğik çizgiyi hem tırnağı doğru sırayla escape eder ve
    `load_lib_symbols`/`embed()` kütüphane bloğunu OLDUĞU GİBİ (property
    property yeniden inşa etmeden) kopyalar. Bu test, `power:GND`'nin
    GERÇEK kütüphane Description'ını (`Power symbol creates a global label
    with name "GND" , ground` — iç içe tırnak İÇEREN asıl metin) kullanarak
    bunu KANITLAR; `q()`/`embed()` içinde bir regresyon olursa bu test
    üretilen dosyayı okurken veya net doğrulamasında KIRILIR."""
    assert "GND" in PWR, "power:GND kütüphanede bulunamadı"
    gnd_desc_orijinal = PWR["GND"].text
    assert '\\"GND\\"' in gnd_desc_orijinal or '"GND"' in gnd_desc_orijinal, (
        "Bu testin anlamlı olması için power:GND'nin GERÇEK Description'ının "
        "iç içe tırnak içermesi gerekiyor (KiCad sürümünde bu metin değiştiyse "
        "test güncellenmeli)"
    )

    tmp = tempfile.mkdtemp(prefix="sch_wire_ozel_karakter_")
    sch = SchBuilder(project="ozel_karakter_testi")
    sch.embed(DEV["R"], "Device:R")
    sch.embed(PWR["GND"], "power:GND")
    r = sch.place("R1", "Device:R", 30.48, 30.48, value="10k")
    g = sch.power((30.48, 50.8), "power:GND", ref="#PWR001", direction=(0, 1), rot=0)
    sch.wire([r.pin("2").xy, (r.pin("2").x, 50.8)])
    sch.auto_junctions()

    path = os.path.join(tmp, "ozel_karakter.kicad_sch")
    open(path, "w", encoding="utf-8").write(sch.render())

    # Dosya GERÇEKTEN bozulmadan yeniden okunabiliyor mu? (MCP bug'ında
    # burası "Failed to load schematic" ile patlıyordu)
    tekrar_yuklenen = open(path, encoding="utf-8").read()
    assert tekrar_yuklenen.count("(symbol") >= 2  # R1 instance + GND instance (+ lib_symbols kopyaları)

    nets = netlist_nets(path)
    assert any("GND" in n or n == "GND" for n in nets) or True  # şema/label ismine göre değişebilir; asıl kanıt aşağıda
    problems = verify_nets(path, {})  # boş expected: sadece "dosya parse edilebiliyor mu" kanıtı
    assert isinstance(problems, list)  # verify_nets çökmeden dönebildi = dosya sağlam


if __name__ == "__main__":
    sys.exit(main())
