"""ipc7351_footprint.py için test suite."""

import pytest

from ipc7351_footprint import (
    BgaKomponentBoyutlari,
    CipKomponentBoyutlari,
    GullwingKomponentBoyutlari,
    YogunlukSeviyesi,
    bga_land_pattern_hesapla,
    gullwing_land_pattern_hesapla,
    land_pattern_hesapla,
    paket_isminden_hesapla,
    qfn_land_pattern_hesapla,
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


# ------------------------------------------------------------------
# Gullwing / QFP (SOIC, TSOP, TQFP vb.)
# ------------------------------------------------------------------

_SOIC8 = GullwingKomponentBoyutlari(
    pin_sayisi=8, pitch_mm=1.27, lead_span_nom_mm=6.0,
    lead_genislik_nom_mm=0.4, lead_uzunluk_nom_mm=0.5, tolerans_mm=0.1,
)


def test_gullwing_soic8_makul_pad_boyutu_uretir():
    sonuc = gullwing_land_pattern_hesapla(_SOIC8, YogunlukSeviyesi.B_NOMINAL)
    assert sonuc.pad_genisligi_mm > 0
    assert sonuc.pad_uzunlugu_mm > 0
    assert sonuc.pad_araligi_mm > sonuc.pad_uzunlugu_mm


def test_gullwing_pitch_hesaba_katilmaz_dogrudan_tasinir():
    """Pitch, IPC-7351 Zmax/Gmin/Xmax formülünün bir GİRDİSİ değildir —
    `komponent.pitch_mm` sonuç nesnesine hiç yansımaz (aynı sıra içindeki
    pad aralığı footprint üretiminde AYRICA kullanılmalı)."""
    farkli_pitch = GullwingKomponentBoyutlari(
        pin_sayisi=8, pitch_mm=0.5, lead_span_nom_mm=6.0,
        lead_genislik_nom_mm=0.4, lead_uzunluk_nom_mm=0.5, tolerans_mm=0.1,
    )
    a = gullwing_land_pattern_hesapla(_SOIC8)
    b = gullwing_land_pattern_hesapla(farkli_pitch)
    assert a == b  # pitch dışında her şey aynı -> sonuç birebir aynı olmalı


def test_gullwing_yogunluk_siralamasi_korunur():
    a = gullwing_land_pattern_hesapla(_SOIC8, YogunlukSeviyesi.A_MAKSIMUM)
    b = gullwing_land_pattern_hesapla(_SOIC8, YogunlukSeviyesi.B_NOMINAL)
    c = gullwing_land_pattern_hesapla(_SOIC8, YogunlukSeviyesi.C_MINIMUM)
    assert a.pad_uzunlugu_mm >= b.pad_uzunlugu_mm >= c.pad_uzunlugu_mm


# ------------------------------------------------------------------
# QFN (no-lead)
# ------------------------------------------------------------------

_QFN16 = GullwingKomponentBoyutlari(
    pin_sayisi=16, pitch_mm=0.5, lead_span_nom_mm=3.0,
    lead_genislik_nom_mm=0.25, lead_uzunluk_nom_mm=0.4, tolerans_mm=0.05,
)


def test_qfn_makul_pad_boyutu_uretir():
    sonuc = qfn_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.B_NOMINAL)
    assert sonuc.pad_genisligi_mm > 0
    assert sonuc.pad_uzunlugu_mm > 0


def test_qfn_ayni_geometride_gullwingden_daha_dar_pad_uretir():
    """QFN'nin toe fillet'i (Jt) gullwing'den küçüktür (görünür bacak yok,
    pad lead'i çok az aşar) -> AYNI L/W/T geometrisinde QFN'nin Zmax'i
    (ve dolayısıyla pad uzunluğu) gullwing'den KÜÇÜK olmalı."""
    qfn_sonuc = qfn_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.B_NOMINAL)
    gullwing_sonuc = gullwing_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.B_NOMINAL)
    assert qfn_sonuc.zmax_mm < gullwing_sonuc.zmax_mm
    assert qfn_sonuc.pad_uzunlugu_mm < gullwing_sonuc.pad_uzunlugu_mm


def test_qfn_yogunluk_siralamasi_korunur():
    a = qfn_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.A_MAKSIMUM)
    b = qfn_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.B_NOMINAL)
    c = qfn_land_pattern_hesapla(_QFN16, YogunlukSeviyesi.C_MINIMUM)
    assert a.pad_uzunlugu_mm >= b.pad_uzunlugu_mm >= c.pad_uzunlugu_mm


# ------------------------------------------------------------------
# BGA
# ------------------------------------------------------------------

_BGA_0P5MM = BgaKomponentBoyutlari(pin_sayisi=64, pitch_mm=0.5, top_capi_nom_mm=0.3)


def test_bga_nsmd_pad_capi_080_carpani():
    sonuc = bga_land_pattern_hesapla(_BGA_0P5MM, maske_tipi="NSMD")
    assert sonuc.pad_capi_mm == round(0.3 * 0.80, 4)
    assert sonuc.maske_tipi == "NSMD"
    assert sonuc.pitch_mm == 0.5


def test_bga_smd_pad_capi_tam_top_capi():
    sonuc = bga_land_pattern_hesapla(_BGA_0P5MM, maske_tipi="SMD")
    assert sonuc.pad_capi_mm == 0.3
    assert sonuc.maske_tipi == "SMD"


def test_bga_gecersiz_maske_tipi_value_error():
    with pytest.raises(ValueError):
        bga_land_pattern_hesapla(_BGA_0P5MM, maske_tipi="XYZ")


def test_bga_negatif_top_capi_value_error_firlatir_uydurmaz():
    negatif = BgaKomponentBoyutlari(pin_sayisi=64, pitch_mm=0.5, top_capi_nom_mm=-0.1)
    with pytest.raises(ValueError):
        bga_land_pattern_hesapla(negatif)
