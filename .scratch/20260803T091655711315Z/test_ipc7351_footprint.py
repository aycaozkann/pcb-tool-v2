"""ipc7351_footprint.py için test suite."""

import pytest

from ipc7351_footprint import (
    CipKomponentBoyutlari,
    YogunlukSeviyesi,
    land_pattern_hesapla,
    paket_isminden_hesapla,
    YAYGIN_CIP_PAKETLERI_MM,
)


def test_0603_nominal_makul_pad_boyutu_uretir():
    sonuc = paket_isminden_hesapla("0603", YogunlukSeviyesi.B_NOMINAL)
    # 0603 (1.6x0.8mm gövde) için tipik pad genişliği ~0.9-1.0mm, uzunluk ~0.9-1.1mm
    assert 0.7 <= sonuc.pad_genisligi_mm <= 1.2
    assert 0.7 <= sonuc.pad_uzunlugu_mm <= 1.3
    assert sonuc.pad_araligi_mm > sonuc.pad_uzunlugu_mm  # merkezler pad'den geniş aralıkta


def test_yogunluk_a_pad_b_den_buyuk_c_den_kucuk_degil():
    """Yoğunluk A (maksimum) en BÜYÜK, C (minimum) en KÜÇÜK pad'i vermeli —
    fillet hedefleri sırasıyla azaldığı için."""
    a = land_pattern_hesapla(YAYGIN_CIP_PAKETLERI_MM["0402"], YogunlukSeviyesi.A_MAKSIMUM)
    b = land_pattern_hesapla(YAYGIN_CIP_PAKETLERI_MM["0402"], YogunlukSeviyesi.B_NOMINAL)
    c = land_pattern_hesapla(YAYGIN_CIP_PAKETLERI_MM["0402"], YogunlukSeviyesi.C_MINIMUM)
    # Jt (toe fillet) A>B>C olduğu için Zmax (ve dolayısıyla pad uzunluğu) A>B>C
    assert a.pad_uzunlugu_mm >= b.pad_uzunlugu_mm >= c.pad_uzunlugu_mm
    assert a.zmax_mm > b.zmax_mm > c.zmax_mm


def test_bilinmeyen_paket_keyerror_firlatir_uydurmaz():
    with pytest.raises(KeyError):
        paket_isminden_hesapla("9999_YOK")


def test_gmin_negatifse_value_error_firlatir():
    # Bilerek çakışan (T çok büyük -> S negatif) bir geometri
    cakisan = CipKomponentBoyutlari(uzunluk_nom_mm=1.0, genislik_nom_mm=0.5,
                                     terminasyon_nom_mm=0.9, tolerans_mm=0.05)
    with pytest.raises(ValueError):
        land_pattern_hesapla(cakisan)


def test_elle_verilen_boyutlarla_hesaplanabilir():
    ozel = CipKomponentBoyutlari(uzunluk_nom_mm=3.2, genislik_nom_mm=2.5,
                                  terminasyon_nom_mm=0.6, tolerans_mm=0.1)
    sonuc = land_pattern_hesapla(ozel, YogunlukSeviyesi.B_NOMINAL)
    assert sonuc.pad_genisligi_mm > 0
    assert sonuc.pad_uzunlugu_mm > 0
