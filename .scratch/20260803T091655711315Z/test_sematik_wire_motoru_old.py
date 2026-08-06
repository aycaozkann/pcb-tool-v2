"""
sematik_wire_motoru_old.py için test suite (DEPRECATED modül — sch_wire.py birincil, bu dosya yalnızca regresyon referansı için tutuluyor).

NOT (proje disipliniyle uyumlu dürüstlük notu): Bu testler yalnızca
KiCad/kicad-cli GEREKTİRMEYEN kısmı kapsar (S-Expr üretimi, geometri
dönüşümleri, render çıktısı). `netlist_nets`, `dogrula_netler`,
`erc_calistir` gerçek `kicad-cli` gerektirir ve bu ortamda test
EDİLEMEDİ — bunlar `KURULUM.md` madde 1'deki gerçek KiCad 10 kurulumuyla,
Claude Code üzerinden ayrıca doğrulanmalıdır (tıpkı `test_kicad_koprusu.py`
başındaki notta olduğu gibi).
"""

import math
import subprocess

import pytest

from sematik_wire_motoru_old import (
    KutuphaneSembolu,
    Pin,
    SematikUretici,
    kicad_kapali_mi_dogrula,
    ortogonal_rota,
    snap,
    sayi,
    _calisan_kicad_surecleri,
    _donusum,
)


def _basit_sembol(isim: str = "R") -> KutuphaneSembolu:
    """Gerçek bir .kicad_sym dosyası okumadan, elle 2 pinli bir sembol kurar
    (Device:R'nin basitleştirilmiş hâli — pin 1 üstte, pin 2 altta)."""
    pinler = [
        Pin(numara="1", isim="~", x=0.0, y=3.81, aci=270.0, uzunluk=1.27, etype="passive", unit=1),
        Pin(numara="2", isim="~", x=0.0, y=-3.81, aci=90.0, uzunluk=1.27, etype="passive", unit=1),
    ]
    metin = (
        f'(symbol "{isim}"\n'
        '  (symbol "R_0_1"\n'
        '    (rectangle (start -1.016 2.54) (end 1.016 -2.54))\n'
        '  )\n'
        '  (symbol "R_1_1"\n'
        '    (pin passive line (at 0 3.81 270) (length 1.27)\n'
        '      (name "~" (effects (font (size 1.27 1.27))))\n'
        '      (number "1" (effects (font (size 1.27 1.27))))\n'
        '    )\n'
        '    (pin passive line (at 0 -3.81 90) (length 1.27)\n'
        '      (name "~" (effects (font (size 1.27 1.27))))\n'
        '      (number "2" (effects (font (size 1.27 1.27))))\n'
        '    )\n'
        '  )\n'
        ')'
    )
    return KutuphaneSembolu(isim=isim, pinler=pinler, metin=metin)


def test_sayi_kayan_nokta_artigini_temizler():
    assert sayi(195.57999999999998) == "195.58"


def test_snap_grid_e_yuvarlar():
    assert snap(1.30, grid=1.27) == 1.27


def test_donusum_0_derece_degisiklik_yapmaz():
    x, y = _donusum(1.0, 2.0, 0, "")
    assert (x, y) == (1.0, -2.0)  # sadece Y AŞAĞI çevrilir


def test_donusum_90_derece_dogru_doner():
    x, y = _donusum(1.0, 0.0, 90, "")
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(-1.0, abs=1e-9)


def test_ortogonal_rota_yatay_veya_dikeyse_dogrudan_baglar():
    assert ortogonal_rota((0, 0), (5, 0)) == [(0, 0), (5, 0)]


def test_ortogonal_rota_capraz_asla_uretmez():
    rota = ortogonal_rota((0, 0), (5, 5))
    assert len(rota) == 3
    for (x1, y1), (x2, y2) in zip(rota, rota[1:]):
        assert x1 == x2 or y1 == y2  # her segment yatay YA DA dikey


def test_pin_ankraji_0_derece_dogru_konumda():
    sch = SematikUretici(proje="test")
    r = _basit_sembol()
    sch.gom(r, "Device:R")
    # 99.06 = 78 * 1.27 -> grid'e zaten oturuyor, snap() bir şey değiştirmiyor
    yer = sch.yerlestir("R1", "Device:R", 99.06, 99.06, deger="10k")
    pin1 = yer.pin("1")
    # pin1 lib'te (0, 3.81) -> Y AŞAĞI çevrilince (99.06, 99.06-3.81)
    assert pin1.x == pytest.approx(99.06)
    assert pin1.y == pytest.approx(95.25)


def test_wire_ve_render_ciktisinda_gercek_wire_var():
    sch = SematikUretici(proje="test")
    r = _basit_sembol()
    sch.gom(r, "Device:R")
    r1 = sch.yerlestir("R1", "Device:R", 30.0, 30.0, deger="10k")
    r2 = sch.yerlestir("R2", "Device:R", 60.0, 30.0, deger="10k")
    sch.pin_pin_baglantisi(r1.pin("2"), r2.pin("1"))
    metin = sch.render()
    assert metin.count("(wire") >= 1
    assert '"Device:R"' in metin  # gömülü kütüphane sembolü render'a girmiş
    assert "(kicad_sch" in metin and metin.strip().endswith(")")


def test_guc_sembolu_pwr_referanslari_otomatik_artar():
    sch = SematikUretici(proje="test")
    gnd_sembol = KutuphaneSembolu(
        isim="GND",
        pinler=[Pin(numara="1", isim="GND", x=0.0, y=0.0, aci=90.0, uzunluk=0.0,
                    etype="power_in", unit=1)],
        metin='(symbol "GND" (symbol "GND_0_1" (pin power_in line (at 0 0 90) '
              '(length 0) (name "GND") (number "1"))))',
    )
    sch.gom(gnd_sembol, "power:GND")
    p1 = sch.guc_sembolu((50.0, 50.0), "power:GND", ref="#PWR001")
    p2 = sch.guc_sembolu((60.0, 50.0), "power:GND")  # ref verilmedi -> otomatik
    assert p1.ref == "#PWR001"
    assert p2.ref == "#PWR002"


def test_etiket_pin_ustune_stub_ekler():
    sch = SematikUretici(proje="test")
    r = _basit_sembol()
    sch.gom(r, "Device:R")
    r1 = sch.yerlestir("R1", "Device:R", 30.0, 30.0)
    sch.etiket(r1.pin("1"), "VBUS")
    metin = sch.render()
    assert '(label "VBUS"' in metin
    assert metin.count("(wire") == 1  # etiket için stub wire eklendi


# ------------------------------------------------------------------
# kicad_kapali_mi_dogrula / _calisan_kicad_surecleri — platform güvenliği
#
# REGRESYON: önceki sürüm koşulsuz `pgrep` çağırıyordu; Windows'ta pgrep
# yok, bu yüzden `yaz()` HER çağrıda yakalanmamış FileNotFoundError ile
# çöküyordu (dış incelemenin P0 bulgusu). Bu makinede GERÇEKTEN Windows'ta
# koşturulup doğrulandı (aşağıdaki ilk test monkeypatch içermez).
# ------------------------------------------------------------------

def test_calisan_kicad_surecleri_gercek_platformda_cokmez():
    """Monkeypatch YOK — bu makinenin gerçek platformunda (Windows dahil)
    fonksiyon hiçbir istisna fırlatmadan bir liste döndürmeli."""
    sonuc = _calisan_kicad_surecleri()
    assert isinstance(sonuc, list)


def test_kicad_kapali_mi_dogrula_gercek_platformda_calisir(tmp_path):
    """Gerçek ortamda (KiCad açık değilken) hiç hata fırlatılmamalı —
    önceki sürüm Windows'ta burada FileNotFoundError ile çöküyordu."""
    kicad_kapali_mi_dogrula(str(tmp_path / "yeni.kicad_sch"))


def test_windows_dalinda_tasklist_kullanilir(monkeypatch):
    monkeypatch.setattr("sematik_wire_motoru_old.platform.system", lambda: "Windows")

    cagrilan = {}

    def sahte_run(komut, **kwargs):
        cagrilan["komut"] = komut
        return subprocess.CompletedProcess(
            komut, 0,
            stdout='"kicad.exe","1234","Console","1","50,000 K"\n"notepad.exe","1","Console","1","1 K"\n',
            stderr="",
        )

    monkeypatch.setattr("sematik_wire_motoru_old.subprocess.run", sahte_run)
    sonuc = _calisan_kicad_surecleri()
    assert cagrilan["komut"][0] == "tasklist"
    assert any("kicad.exe" in s for s in sonuc)
    assert not any("notepad" in s for s in sonuc)


def test_unix_dalinda_pgrep_kullanilir(monkeypatch):
    monkeypatch.setattr("sematik_wire_motoru_old.platform.system", lambda: "Linux")

    cagrilan = {}

    def sahte_run(komut, **kwargs):
        cagrilan["komut"] = komut
        return subprocess.CompletedProcess(komut, 0, stdout="12345 kicad\n", stderr="")

    monkeypatch.setattr("sematik_wire_motoru_old.subprocess.run", sahte_run)
    sonuc = _calisan_kicad_surecleri()
    assert cagrilan["komut"][0] == "pgrep"
    assert sonuc == ["12345 kicad"]


def test_kontrol_araci_bulunamazsa_cokme_yerine_uyari_doner(monkeypatch):
    """Aracın kendisi (tasklist/pgrep) yoksa fonksiyon YİNE DE çökmemeli —
    ama sessizce 'süreç yok' da SAYMAMALI, [UYARI] ile işaretlemeli."""
    monkeypatch.setattr("sematik_wire_motoru_old.platform.system", lambda: "Linux")

    def patlayan_run(komut, **kwargs):
        raise FileNotFoundError("pgrep bulunamadı")

    monkeypatch.setattr("sematik_wire_motoru_old.subprocess.run", patlayan_run)
    sonuc = _calisan_kicad_surecleri()
    assert len(sonuc) == 1 and sonuc[0].startswith("[UYARI]")


def test_uyari_satiri_kicad_calisiyor_sayilmaz(monkeypatch, tmp_path):
    """[UYARI] satırı 'KiCad çalışıyor' hatasını TETİKLEMEMELİ — aracın
    eksikliği ile gerçek bir çalışan KiCad süreci farklı şeylerdir."""
    monkeypatch.setattr(
        "sematik_wire_motoru_old._calisan_kicad_surecleri",
        lambda: ["[UYARI] 'pgrep' çalıştırılamadı — çalışan KiCad süreci kontrol edilemedi."],
    )
    kicad_kapali_mi_dogrula(str(tmp_path / "x.kicad_sch"))


def test_gercek_kicad_sureci_varsa_yazma_engellenir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sematik_wire_motoru_old._calisan_kicad_surecleri",
        lambda: ['"kicad.exe","1234"'],
    )
    with pytest.raises(RuntimeError, match="KiCad çalışıyor"):
        kicad_kapali_mi_dogrula(str(tmp_path / "x.kicad_sch"))


def test_force_ile_surec_kontrolu_atlanir(monkeypatch, tmp_path):
    def hic_cagrilmamali():
        raise AssertionError("force=True iken süreç kontrolü hiç ÇAĞRILMAMALI")

    monkeypatch.setattr("sematik_wire_motoru_old._calisan_kicad_surecleri", hic_cagrilmamali)
    kicad_kapali_mi_dogrula(str(tmp_path / "x.kicad_sch"), force=True)
