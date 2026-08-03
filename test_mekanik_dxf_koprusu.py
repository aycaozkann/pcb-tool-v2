"""mekanik_dxf_koprusu.py için test suite."""

import pytest

from mekanik_dxf_koprusu import (
    DxfOutline,
    import_board_outline,
    poligon_kapali_mi,
    TavanHaritasiBolgesi,
    derive_keepouts,
    KomponentYukseklik,
    z_kontrolu_yap,
    IpdToleransBileseni,
    ipd_tolerans_zinciri_hesapla,
    optik_merkez_ofseti_uygula,
)


KARE_OUTLINE = DxfOutline(
    nokta_listesi=[(0, 0), (50, 0), (50, 30), (0, 30), (0, 0)],
    delik_listesi=[(5, 5, 2.0), (45, 25, 2.0)],
)


def test_poligon_kapali_mi_kapali_dogru_algilar():
    assert poligon_kapali_mi(KARE_OUTLINE.nokta_listesi) is True


def test_poligon_kapali_mi_acik_yanlis_doner():
    acik = [(0, 0), (50, 0), (50, 30)]
    assert poligon_kapali_mi(acik) is False


def test_import_board_outline_mil_den_mm_e_cevirir():
    mil_outline = DxfOutline(
        nokta_listesi=[(0, 0), (1000, 0), (1000, 1000), (0, 1000)],
        birim="mil",
        delik_listesi=[(100, 100, 80)],
    )
    sonuc = import_board_outline(mil_outline)
    assert sonuc.birim == "mm"
    assert sonuc.nokta_listesi[1][0] == pytest.approx(25.4, abs=1e-6)


def test_import_board_outline_capa_kontrolu_gecer():
    sonuc = import_board_outline(KARE_OUTLINE, bilinen_delik_koordinati=(5.1, 5.0))
    assert sonuc.delik_listesi[0][:2] == (5, 5)


def test_import_board_outline_capa_kontrolu_hata_firlatir():
    with pytest.raises(ValueError):
        import_board_outline(KARE_OUTLINE, bilinen_delik_koordinati=(20, 20))


def test_derive_keepouts_tavan_haritasindan_yukseklik_alir():
    tavan = [TavanHaritasiBolgesi(poligon=KARE_OUTLINE.nokta_listesi[:-1], tavan_z_mm=4.0)]
    bolgeler = derive_keepouts(KARE_OUTLINE.delik_listesi, tavan_haritasi=tavan, clearance_mm=0.3)
    assert len(bolgeler) == 2
    assert bolgeler[0].max_allowed_height_mm == pytest.approx(3.7)
    assert bolgeler[0].kaynak == "step_tavan_haritasi"


def test_derive_keepouts_sabit_kutu_yuksekligi_fallback():
    bolgeler = derive_keepouts(KARE_OUTLINE.delik_listesi, global_max_height_mm=5.0, clearance_mm=0.5)
    assert bolgeler[0].max_allowed_height_mm == pytest.approx(4.5)
    assert bolgeler[0].kaynak == "sabit_kutu_yuksekligi"


def test_z_kontrolu_ihlali_yakalar():
    tavan = [TavanHaritasiBolgesi(poligon=KARE_OUTLINE.nokta_listesi[:-1], tavan_z_mm=4.0)]
    bolgeler = derive_keepouts(KARE_OUTLINE.delik_listesi, tavan_haritasi=tavan)
    komp_ihlal = KomponentYukseklik(refdes="U1", x=5, y=5, body_height_mm=5.0)
    komp_ok = KomponentYukseklik(refdes="U2", x=5, y=5, body_height_mm=2.0)
    bulgular = z_kontrolu_yap([komp_ihlal, komp_ok], bolgeler)
    assert len(bulgular) == 1
    assert "U1" in bulgular[0]


def test_ipd_tolerans_zinciri_worst_case_toplamdir():
    bilesenler = [IpdToleransBileseni("a", 0.1), IpdToleransBileseni("b", 0.2)]
    sonuc = ipd_tolerans_zinciri_hesapla(60.0, bilesenler, rss_mi=False)
    assert sonuc["toplam_tolerans_mm"] == pytest.approx(0.3)
    assert sonuc["yontem"] == "worst_case"


def test_ipd_tolerans_zinciri_rss_kucuktur_worst_caseden():
    bilesenler = [IpdToleransBileseni("a", 0.1), IpdToleransBileseni("b", 0.2)]
    rss = ipd_tolerans_zinciri_hesapla(60.0, bilesenler, rss_mi=True)
    worst = ipd_tolerans_zinciri_hesapla(60.0, bilesenler, rss_mi=False)
    assert rss["toplam_tolerans_mm"] < worst["toplam_tolerans_mm"]


def test_optik_merkez_ofseti_uygula():
    sonuc = optik_merkez_ofseti_uygula((10.0, 10.0), (0.5, -0.3))
    assert sonuc == (10.5, 9.7)


# ------------------------------------------------------------------
# FAULT-INJECTION — z_kontrolu_yap'ın gerçekten bir şey kontrol ettiğini
# kanıtla (CLAUDE.md honesty §6 ile aynı disiplin: "test yazdıysan boş
# olmadığını fault-injection ile kanıtla"). Önce TEMİZ bir senaryo kurulur,
# sonra bilerek bozulur; kontrol PASS'ten FAIL'e GEÇMELİDİR.
# ------------------------------------------------------------------

def test_z_kontrolu_fault_injection_temiz_senaryo_once_pass_sonra_fail():
    tavan = [TavanHaritasiBolgesi(poligon=KARE_OUTLINE.nokta_listesi[:-1], tavan_z_mm=4.0)]
    bolgeler = derive_keepouts(KARE_OUTLINE.delik_listesi, tavan_haritasi=tavan, clearance_mm=0.3)

    # 1) TEMİZ senaryo: parça izin verilen yüksekliğin altında -> bulgu YOK
    komp_temiz = KomponentYukseklik(refdes="U1", x=5, y=5, body_height_mm=1.0)
    bulgular_temiz = z_kontrolu_yap([komp_temiz], bolgeler)
    assert bulgular_temiz == [], "fault enjekte edilmeden önce test zaten FAIL veriyor — senaryo geçersiz"

    # 2) FAULT INJECTION: aynı parçanın yüksekliğini izin verilenin üzerine çıkar
    komp_bozuk = KomponentYukseklik(refdes="U1", x=5, y=5, body_height_mm=999.0)
    bulgular_bozuk = z_kontrolu_yap([komp_bozuk], bolgeler)
    assert len(bulgular_bozuk) == 1, (
        "FAIL: enjekte edilen yükseklik ihlali yakalanmadı — kontrol boş olabilir"
    )
    assert "U1" in bulgular_bozuk[0]


def test_capa_kontrolu_fault_injection_once_gecer_sonra_hata_firlatir():
    # 1) TEMİZ: bilinen delik koordinatı outline'daki gerçek delikle örtüşüyor
    import_board_outline(KARE_OUTLINE, bilinen_delik_koordinati=(5.0, 5.0))  # hata fırlatmamalı

    # 2) FAULT INJECTION: bilinen koordinatı kasıtlı olarak çok uzağa taşı
    with pytest.raises(ValueError):
        import_board_outline(KARE_OUTLINE, bilinen_delik_koordinati=(500.0, 500.0))
