"""ipc_dru_koprusu.py'nin Görev 3 eklentileri için test suite:
`uc_w_kuraline_cevir` (EMI 3W) ve `dfa_courtyard_kuraline_cevir` (IPC-A-610 DFA).
"""

from __future__ import annotations

from emi_emc_kural_motoru import w_3w
from ipc_a_610_dfa_motoru import (
    KomponentTipi,
    MontajSinifi,
    PaketBoyutlari,
    minimum_clearance_hesapla,
)
from ipc_dru_koprusu import (
    KuralOnceligi,
    _kicad_dru_govdesi_uret,
    dfa_courtyard_kuraline_cevir,
    kural_dosyasi_olustur,
    uc_w_kuraline_cevir,
)


def test_uc_w_kuraline_cevir_kenar_kenar_kullanir():
    sonuc = w_3w(0.2, carpan=3.0)  # merkez-merkez 0.6, kenar-kenar 0.4
    kural = uc_w_kuraline_cevir("USB_HS", "USB_HS", sonuc)
    assert kural.min_deger_mm == sonuc.minimum_kenar_kenar_mm
    assert kural.min_deger_mm != sonuc.minimum_merkez_merkez_mm
    assert kural.constraint_tipi == "clearance"
    assert "A.NetClass == 'USB_HS'" in kural.kosul
    assert "B.NetClass == 'USB_HS'" in kural.kosul


def test_uc_w_kurali_gecerli_kicad_dru_metni_uretir():
    sonuc = w_3w(0.15)
    metin = _kicad_dru_govdesi_uret([uc_w_kuraline_cevir("SPI", "SPI", sonuc)])
    assert metin.startswith("(version 1)")
    assert "(priority" not in metin
    assert ";" not in metin.replace("SPI-SPI", "")  # sadece isimde geçebilecek ';' yok zaten


def test_dfa_courtyard_kuraline_cevir_istisna_onceligi():
    kucuk = PaketBoyutlari(2.0, 1.0, 0.5)
    sonuc = minimum_clearance_hesapla(
        KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kucuk, kucuk, MontajSinifi.CLASS_2
    )
    kural = dfa_courtyard_kuraline_cevir("U1", "U2", sonuc)
    assert kural.oncelik == KuralOnceligi.ISTISNA
    assert kural.constraint_tipi == "courtyard_clearance"
    assert kural.min_deger_mm == sonuc.minimum_clearance_mm
    assert "A.Reference == 'U1'" in kural.kosul
    assert "B.Reference == 'U2'" in kural.kosul


def test_dfa_kurali_genel_kuraldan_once_yazilir(tmp_path):
    kucuk = PaketBoyutlari(2.0, 1.0, 0.5)
    dfa_sonuc = minimum_clearance_hesapla(
        KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kucuk, kucuk
    )
    genel = uc_w_kuraline_cevir("SPI", "SPI", w_3w(0.2))
    istisna = dfa_courtyard_kuraline_cevir("U1", "U2", dfa_sonuc)

    yol = kural_dosyasi_olustur(str(tmp_path / "test.kicad_dru"), [genel, istisna])
    metin = (tmp_path / "test.kicad_dru").read_text(encoding="utf-8")
    assert metin.index('"DFA U1-U2 Courtyard Clearance"') < metin.index('"EMI 3W SPI-SPI Crosstalk Clearance"')
