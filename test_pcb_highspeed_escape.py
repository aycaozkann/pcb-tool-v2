"""
pcb_highspeed_escape.py için test suite.
Çalıştırmak için: pytest -v test_pcb_highspeed_escape.py
"""

import pytest

from pcb_highspeed_escape import (
    PinArasiKanal,
    kanal_genisligi_hesapla_mm,
    maske_baraji_hesapla_mm,
    maske_baraji_kontrolu,
    maksimum_iz_genisligi_icin_baraj_mm,
    DiferansiyelPadAcilimi,
    acilma_gerekli_mi,
    acilma_mesafesi_hesapla_mm,
    RotaSegmenti,
    donus_acisi_hesapla,
    dik_acili_koseleri_bul,
    skew_mm_den_ps_e_cevir,
    meander_gerekli_mi,
    meander_ekleme_mesafesi_hesapla_mm,
    gnd_dolgu_min_clearance_mm,
    KartYolSegmenti,
    coklu_kart_skew_butcesi_hesapla,
    FR4_MIKROSERIT_HIZ_MM_NS,
    VARSAYILAN_KABLO_HIZ_MM_NS,
    VARSAYILAN_VIA_GECIS_GECIKMESI_PS,
)


# ------------------------------------------------------------------
# Maske barajı — dokümandaki referans tabloya karşı doğrulama
# (SOT-23-6: pad_sutun_araligi=2.274mm, pad_uzunlugu=1.32mm)
# ------------------------------------------------------------------

SOT23_6_KANAL = PinArasiKanal(pad_sutun_araligi_mm=2.274, pad_uzunlugu_mm=1.32, mask_expansion_mm=0.05)


def test_kanal_genisligi_sot23_6():
    assert kanal_genisligi_hesapla_mm(SOT23_6_KANAL) == pytest.approx(0.954, abs=1e-6)


@pytest.mark.parametrize(
    "iz_mm,beklenen_baraj_mm",
    [
        (0.40, 0.177),
        (0.30, 0.227),
        (0.25, 0.252),
    ],
)
def test_maske_baraji_referans_tablosu(iz_mm, beklenen_baraj_mm):
    baraj = maske_baraji_hesapla_mm(SOT23_6_KANAL, iz_mm)
    assert baraj == pytest.approx(beklenen_baraj_mm, abs=1e-3)


def test_maske_baraji_kontrolu_ihlal_yakalar():
    bulgular = maske_baraji_kontrolu(SOT23_6_KANAL, 0.40, fab_min_baraj_mm=0.20)
    assert len(bulgular) == 1
    assert "KRİTİK" in bulgular[0]


def test_maske_baraji_kontrolu_gecerli_izde_bos_liste():
    assert maske_baraji_kontrolu(SOT23_6_KANAL, 0.25, fab_min_baraj_mm=0.20) == []


def test_kanal_yoksa_kritik_uyari():
    dar_kanal = PinArasiKanal(pad_sutun_araligi_mm=1.0, pad_uzunlugu_mm=1.2)
    bulgular = maske_baraji_kontrolu(dar_kanal, 0.2)
    assert "short" in bulgular[0]


def test_maksimum_iz_genisligi_geri_cozum_tutarli():
    fab_min = 0.20
    iz_max = maksimum_iz_genisligi_icin_baraj_mm(SOT23_6_KANAL, fab_min)
    baraj = maske_baraji_hesapla_mm(SOT23_6_KANAL, iz_max)
    assert baraj == pytest.approx(fab_min, abs=1e-6)


# ------------------------------------------------------------------
# Pad açılımı
# ------------------------------------------------------------------

def test_acilma_gerekli_sot23_6_ornegi():
    # dokümandaki gerçek örnek: pad boyu 0.60mm, çift adımı 0.62mm
    acilim = DiferansiyelPadAcilimi(pad_boyu_mm=0.60, cift_adimi_mm=0.62)
    assert acilma_gerekli_mi(acilim) is False  # 0.60 < 0.62, henüz gerekmiyor
    acilim2 = DiferansiyelPadAcilimi(pad_boyu_mm=0.62, cift_adimi_mm=0.62)
    assert acilma_gerekli_mi(acilim2) is True


def test_acilma_mesafesi_gerekmiyorsa_none():
    acilim = DiferansiyelPadAcilimi(pad_boyu_mm=0.5, cift_adimi_mm=0.62)
    assert acilma_mesafesi_hesapla_mm(acilim) is None


# ------------------------------------------------------------------
# 90 derece köşe tespiti
# ------------------------------------------------------------------

def test_90_derece_kose_yakalanir():
    yatay = RotaSegmenti(0, 0, 10, 0)
    dikey = RotaSegmenti(10, 0, 10, 10)
    assert donus_acisi_hesapla(yatay, dikey) == pytest.approx(90.0)
    kotu = dik_acili_koseleri_bul([yatay, dikey])
    assert kotu == [0]


def test_45_derece_kose_temiz():
    yatay = RotaSegmenti(0, 0, 10, 0)
    capraz = RotaSegmenti(10, 0, 17.07, 7.07)  # ~45 derece
    kotu = dik_acili_koseleri_bul([yatay, capraz])
    assert kotu == []


def test_duz_hat_kose_uretmez():
    a = RotaSegmenti(0, 0, 10, 0)
    b = RotaSegmenti(10, 0, 20, 0)
    assert dik_acili_koseleri_bul([a, b]) == []


# ------------------------------------------------------------------
# ps cinsinden skew — dokümandaki gerçek örnek
# ------------------------------------------------------------------

def test_skew_mm_den_ps_e_gercek_ornek():
    # 1.47mm = 8.8ps (USB 2.0 HS örneği)
    assert skew_mm_den_ps_e_cevir(1.47) == pytest.approx(8.8, abs=0.1)


def test_meander_gereksiz_kucuk_skew_de():
    assert meander_gerekli_mi(1.47, butce_ps=100) is False
    assert meander_ekleme_mesafesi_hesapla_mm(1.47, butce_ps=100) == 0.0


def test_meander_gerekli_buyuk_skew_de():
    assert meander_gerekli_mi(30.0, butce_ps=100) is True
    ek = meander_ekleme_mesafesi_hesapla_mm(30.0, butce_ps=100)
    assert ek > 0


# ------------------------------------------------------------------
# GND dolgu clearance
# ------------------------------------------------------------------

def test_gnd_dolgu_clearance_oranli():
    assert gnd_dolgu_min_clearance_mm(0.4) == pytest.approx(0.5, abs=1e-6)


# ------------------------------------------------------------------
# FAULT-INJECTION — maske_baraji_kontrolu ve dik_acili_koseleri_bul'un
# gerçekten çalıştığını (her zaman PASS vermediğini) kanıtla.
# ------------------------------------------------------------------

def test_maske_baraji_fault_injection_once_temiz_sonra_ihlal():
    # 1) TEMİZ: dokümandaki kabul edilen değer (0.25mm iz -> baraj 0.252mm)
    temiz = maske_baraji_kontrolu(SOT23_6_KANAL, 0.25, fab_min_baraj_mm=0.20)
    assert temiz == [], "fault enjekte etmeden önce zaten FAIL — senaryo geçersiz"

    # 2) FAULT INJECTION: iz genişliğini kasıtlı olarak aşırı büyüt (baraj çöker)
    bozuk = maske_baraji_kontrolu(SOT23_6_KANAL, 0.90, fab_min_baraj_mm=0.20)
    assert len(bozuk) == 1, "FAIL: enjekte edilen maske barajı ihlali yakalanmadı"
    assert "KRİTİK" in bozuk[0]


def test_90_derece_kose_fault_injection_once_temiz_sonra_ihlal():
    # 1) TEMİZ: düz hat, köşe yok
    a = RotaSegmenti(0, 0, 10, 0)
    b_duz = RotaSegmenti(10, 0, 20, 0)
    assert dik_acili_koseleri_bul([a, b_duz]) == [], "senaryo zaten FAIL — geçersiz"

    # 2) FAULT INJECTION: ikinci segmenti 90 derece döndür
    b_bozuk = RotaSegmenti(10, 0, 10, 10)
    kotu = dik_acili_koseleri_bul([a, b_bozuk])
    assert kotu == [0], "FAIL: enjekte edilen 90 derece köşe yakalanmadı"


# ------------------------------------------------------------------
# FAZ 0.5 #35 — coklu_kart_skew_butcesi_hesapla()
# ------------------------------------------------------------------

def test_bos_yol_listesi_reddedilir():
    with pytest.raises(ValueError):
        coklu_kart_skew_butcesi_hesapla([], butce_ps=1000.0)


def test_tek_kart_skew_sifir():
    yollar = [KartYolSegmenti("cam0", host_pcb_uzunluk_mm=20.0, kart_pcb_uzunluk_mm=10.0)]
    sonuc = coklu_kart_skew_butcesi_hesapla(yollar, butce_ps=1000.0)
    assert sonuc.maks_skew_ps == 0.0
    assert sonuc.en_hizli_kart == sonuc.en_yavas_kart == "cam0"
    assert sonuc.butce_asildi_mi is False


def test_esit_uzunluklu_kartlar_sifir_skew():
    # 6 kamera, HEPSİ birebir aynı host-PCB + kablo + kart-PCB + via sayısı
    yollar = [
        KartYolSegmenti(f"cam{i}", host_pcb_uzunluk_mm=15.0, kablo_uzunluk_mm=50.0,
                         kart_pcb_uzunluk_mm=8.0, katman_gecis_sayisi=1)
        for i in range(6)
    ]
    sonuc = coklu_kart_skew_butcesi_hesapla(yollar, butce_ps=100.0)
    assert sonuc.maks_skew_ps == 0.0
    assert sonuc.butce_asildi_mi is False
    assert len(sonuc.kart_sonuclari) == 6


def test_farkli_kablo_uzunlugu_skew_uretir_ve_bileşenlere_dogru_dagilir():
    kisa = KartYolSegmenti("cam_yakin", host_pcb_uzunluk_mm=10.0, kablo_uzunluk_mm=50.0,
                            kart_pcb_uzunluk_mm=5.0, katman_gecis_sayisi=0)
    uzun = KartYolSegmenti("cam_uzak", host_pcb_uzunluk_mm=10.0, kablo_uzunluk_mm=250.0,
                            kart_pcb_uzunluk_mm=5.0, katman_gecis_sayisi=0)

    sonuc = coklu_kart_skew_butcesi_hesapla([kisa, uzun], butce_ps=50.0)

    beklenen_pcb_ps = skew_mm_den_ps_e_cevir(15.0)  # host+kart PCB, ikisinde de aynı
    beklenen_kablo_fark_ps = (
        skew_mm_den_ps_e_cevir(250.0, VARSAYILAN_KABLO_HIZ_MM_NS)
        - skew_mm_den_ps_e_cevir(50.0, VARSAYILAN_KABLO_HIZ_MM_NS)
    )
    assert sonuc.kart_sonuclari["cam_yakin"].pcb_gecikme_ps == pytest.approx(beklenen_pcb_ps, abs=1e-3)
    assert sonuc.en_yavas_kart == "cam_uzak"
    assert sonuc.en_hizli_kart == "cam_yakin"
    assert sonuc.maks_skew_ps == pytest.approx(beklenen_kablo_fark_ps, abs=1e-3)
    assert sonuc.butce_asildi_mi is True  # 50ps bütçe, kablo farkı tek başına çok daha büyük


def test_katman_gecisi_via_gecikmesi_ekler():
    via_yok = KartYolSegmenti("a", host_pcb_uzunluk_mm=10.0, katman_gecis_sayisi=0)
    via_var = KartYolSegmenti("b", host_pcb_uzunluk_mm=10.0, katman_gecis_sayisi=3)

    sonuc = coklu_kart_skew_butcesi_hesapla([via_yok, via_var], butce_ps=1e6)

    assert sonuc.kart_sonuclari["b"].via_gecikme_ps == pytest.approx(
        3 * VARSAYILAN_VIA_GECIS_GECIKMESI_PS, abs=1e-6
    )
    assert sonuc.kart_sonuclari["a"].via_gecikme_ps == 0.0
    assert sonuc.maks_skew_ps == pytest.approx(3 * VARSAYILAN_VIA_GECIS_GECIKMESI_PS, abs=1e-3)


def test_butce_asilmadiginda_false_doner():
    yollar = [
        KartYolSegmenti("a", host_pcb_uzunluk_mm=10.0),
        KartYolSegmenti("b", host_pcb_uzunluk_mm=10.5),
    ]
    sonuc = coklu_kart_skew_butcesi_hesapla(yollar, butce_ps=1000.0)
    assert sonuc.butce_asildi_mi is False


def test_ozel_hiz_parametreleri_kullanilir():
    yol = KartYolSegmenti("a", host_pcb_uzunluk_mm=0.0, kablo_uzunluk_mm=100.0)
    varsayilan = coklu_kart_skew_butcesi_hesapla([yol], butce_ps=1e6)
    ozel_hiz = coklu_kart_skew_butcesi_hesapla([yol], butce_ps=1e6, kablo_hiz_mm_ns=100.0)
    # Daha DÜŞÜK kablo hızı -> AYNI mesafe için DAHA BÜYÜK gecikme
    assert ozel_hiz.kart_sonuclari["a"].kablo_gecikme_ps > varsayilan.kart_sonuclari["a"].kablo_gecikme_ps
