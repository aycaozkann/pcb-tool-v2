"""ipc6012_dfm_motoru.py için test suite.
Çalıştırmak için:  pytest -v test_ipc6012_dfm_motoru.py
"""

import pytest

from bulgu_sozlesmesi import BulguDurumu
from pcb_highspeed_escape import FAB_MIN_MASKE_BARAJI_MM

from ipc6012_dfm_motoru import (
    DelikOlcumu,
    Ipc6012DfmMotoru,
    Ipc6012Sinifi,
    MaskeKanaliOlcumu,
    SINIF_LIMITLERI,
    SinifLimitleri,
    ViaOlcumu,
    kicad_via_verisinden_olcum_uret,
    oz_testleri_calistir,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Sınıf tanımı tutarlılığı
# ------------------------------------------------------------------

def test_class3_class2den_daha_siki():
    c2 = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_2]
    c3 = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_3]
    assert c3.min_annular_ring_mm >= c2.min_annular_ring_mm
    assert c3.maks_aspect_ratio <= c2.maks_aspect_ratio


def test_solder_mask_baraji_projenin_kabul_ettigi_sabitten_geliyor():
    """Kullanıcının 'genelde 0.1mm' varsayımı BİLİNÇLİ OLARAK kullanılmadı
    — mevcut projenin kabul ettiği FAB_MIN_MASKE_BARAJI_MM (0.20mm) esas."""
    assert SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_2].min_solder_mask_baraji_mm == FAB_MIN_MASKE_BARAJI_MM
    assert FAB_MIN_MASKE_BARAJI_MM != 0.1


def test_ozel_limitler_verilirse_varsayilani_ezer():
    ozel = SinifLimitleri(Ipc6012Sinifi.CLASS_2, 0.09, 0.15, 12.0, "test amaçlı özel limit")
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2, limitler=ozel)
    assert motor.limitler.min_annular_ring_mm == 0.09


# ------------------------------------------------------------------
# ViaOlcumu / DelikOlcumu türetilmiş alanlar
# ------------------------------------------------------------------

def test_annular_ring_hesabi_dogru():
    via = ViaOlcumu("V1", delik_capi_mm=0.3, pad_capi_mm=0.5)
    assert via.annular_ring_mm == pytest.approx(0.1)


def test_aspect_ratio_hesabi_dogru():
    delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.2)
    assert delik.aspect_ratio == pytest.approx(8.0)


# ------------------------------------------------------------------
# annular_ring_kontrolu
# ------------------------------------------------------------------

def test_annular_ring_yeterliyse_pass():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    via = ViaOlcumu("V1", delik_capi_mm=0.3, pad_capi_mm=0.5)  # annular=0.1mm > 0.05mm min
    bulgu = motor.annular_ring_kontrolu([via])
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.taranan == 1


def test_annular_ring_yetersizse_fail_detayli_ihlal_doner():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    via = ViaOlcumu("V_KOTU", delik_capi_mm=0.3, pad_capi_mm=0.32)  # annular=0.01mm < 0.05mm
    bulgu = motor.annular_ring_kontrolu([via])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["referans"] == "V_KOTU"
    assert bulgu.ihlaller[0]["eksik_mm"] == pytest.approx(0.04)


def test_annular_ring_bos_listede_kapsam_yok():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    bulgu = motor.annular_ring_kontrolu([])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert not bulgu.gecti_mi


def test_annular_ring_karisik_listede_sadece_kotu_olan_ihlal():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    iyi = ViaOlcumu("V_IYI", delik_capi_mm=0.3, pad_capi_mm=0.5)
    kotu = ViaOlcumu("V_KOTU", delik_capi_mm=0.3, pad_capi_mm=0.32)
    bulgu = motor.annular_ring_kontrolu([iyi, kotu])
    assert bulgu.taranan == 2
    assert len(bulgu.ihlaller) == 1
    assert bulgu.ihlaller[0]["referans"] == "V_KOTU"


# ------------------------------------------------------------------
# solder_mask_baraji_kontrolu
# ------------------------------------------------------------------

def test_solder_mask_baraji_yeterliyse_pass():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    olcum = MaskeKanaliOlcumu("ESD_dizisi_pin2-3", baraj_genisligi_mm=0.25)
    assert motor.solder_mask_baraji_kontrolu([olcum]).durum == BulguDurumu.PASS


def test_solder_mask_baraji_yetersizse_fail():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    olcum = MaskeKanaliOlcumu("ESD_dizisi_pin2-3", baraj_genisligi_mm=0.10)
    bulgu = motor.solder_mask_baraji_kontrolu([olcum])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["tanim"] == "ESD_dizisi_pin2-3"


# ------------------------------------------------------------------
# aspect_ratio_kontrolu
# ------------------------------------------------------------------

def test_aspect_ratio_sinir_altindaysa_pass():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)  # maks 10:1
    delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.3)  # ~5.33:1
    assert motor.aspect_ratio_kontrolu([delik]).durum == BulguDurumu.PASS


def test_aspect_ratio_asilirsa_fail():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_3)  # maks 8:1
    delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.15)  # ~10.67:1
    bulgu = motor.aspect_ratio_kontrolu([delik])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["olculen_oran"] == pytest.approx(10.667, abs=0.01)


def test_ayni_delik_class2de_pass_class3te_fail_olabilir():
    """Sınıf seçiminin GERÇEKTEN sonucu değiştirdiğinin kanıtı — aynı
    fiziksel delik, daha sıkı Class 3 limitiyle FAIL, Class 2 ile PASS
    olabilmeli."""
    delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.18)  # ~8.89:1

    c2_motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)  # maks 10:1
    c3_motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_3)  # maks 8:1

    assert c2_motor.aspect_ratio_kontrolu([delik]).durum == BulguDurumu.PASS
    assert c3_motor.aspect_ratio_kontrolu([delik]).durum == BulguDurumu.FAIL


# ------------------------------------------------------------------
# tum_kontrolleri_calistir / genel_sonuc
# ------------------------------------------------------------------

def test_genel_sonuc_hepsi_temizse_pass():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    via = ViaOlcumu("V1", delik_capi_mm=0.3, pad_capi_mm=0.5)
    maske = MaskeKanaliOlcumu("K1", baraj_genisligi_mm=0.3)
    delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.3)
    bulgular = motor.tum_kontrolleri_calistir([via], [maske], [delik])
    assert motor.genel_sonuc(bulgular) == "PASS"


def test_genel_sonuc_bir_ihlal_varsa_fail():
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    kotu_via = ViaOlcumu("V_KOTU", delik_capi_mm=0.3, pad_capi_mm=0.32)
    iyi_maske = MaskeKanaliOlcumu("K1", baraj_genisligi_mm=0.3)
    iyi_delik = DelikOlcumu("H1", kart_kalinligi_mm=1.6, delik_capi_mm=0.3)
    bulgular = motor.tum_kontrolleri_calistir([kotu_via], [iyi_maske], [iyi_delik])
    assert motor.genel_sonuc(bulgular) == "FAIL"


def test_genel_sonuc_bos_kumede_needs_human_pass_degil():
    """Hiç ölçüm verilmemiş olması sessizce PASS SAYILAMAZ."""
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    bulgular = motor.tum_kontrolleri_calistir()
    assert motor.genel_sonuc(bulgular) == "NEEDS_HUMAN"


def test_genel_sonuc_kismi_veri_needs_human():
    """Üç kontrolden ikisi veri aldı, biri almadı -> genel sonuç yine de
    NEEDS_HUMAN (kısmi kapsam sessizce PASS sayılamaz)."""
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    via = ViaOlcumu("V1", delik_capi_mm=0.3, pad_capi_mm=0.5)
    bulgular = motor.tum_kontrolleri_calistir(via_olcumleri=[via])  # maske/delik boş
    assert motor.genel_sonuc(bulgular) == "NEEDS_HUMAN"


# ------------------------------------------------------------------
# kicad_via_verisinden_olcum_uret
# ------------------------------------------------------------------

def test_kicad_via_verisi_donusumu():
    ham = [{"ref": "V1", "delik_mm": 0.3, "pad_mm": 0.5}]
    olcumler = kicad_via_verisinden_olcum_uret(ham)
    assert len(olcumler) == 1
    assert olcumler[0].referans == "V1"
    assert olcumler[0].annular_ring_mm == pytest.approx(0.1)


def test_kicad_via_verisi_ref_eksikse_soru_isareti():
    ham = [{"delik_mm": 0.3, "pad_mm": 0.5}]
    olcumler = kicad_via_verisinden_olcum_uret(ham)
    assert olcumler[0].referans == "?"


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
