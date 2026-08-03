"""emi_emc_kural_motoru.py için test suite (pytest)."""

from __future__ import annotations

import pytest

from bulgu_sozlesmesi import BulguDurumu
from emi_emc_kural_motoru import (
    UcWOlcumu,
    YirmiHOlcumu,
    genel_sonuc,
    h_20h_setback_mm,
    oz_testleri_calistir,
    stitching_max_araligi_mm,
    uc_w_kontrolu,
    via_araligi_kontrolu,
    w_3w,
    w_3w_karma_genislik,
    yirmi_h_kontrolu,
)


def test_modulun_kendi_oz_testleri_temiz():
    assert oz_testleri_calistir() == []


def test_w_3w_temel_carpim():
    s = w_3w(0.2, carpan=3.0)
    assert s.minimum_merkez_merkez_mm == pytest.approx(0.6)
    assert s.minimum_kenar_kenar_mm == pytest.approx(0.4)


def test_w_3w_negatif_genislik_reddedilir():
    with pytest.raises(ValueError):
        w_3w(-0.1)


def test_w_3w_karma_genislik_ortalama_kullanir():
    s = w_3w_karma_genislik(0.1, 0.3, carpan=3.0)
    assert s.iz_genisligi_mm == pytest.approx(0.2)


def test_uc_w_kontrolu_ihlali_yakalar():
    bulgu = uc_w_kontrolu([UcWOlcumu("D_P", "D_N", 0.2, 0.2, 0.3)])  # hedef 0.6mm, çok yakın
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["a"] == "D_P"


def test_20h_dielektrik_pozitif_zorunlu():
    with pytest.raises(ValueError):
        h_20h_setback_mm(0)


def test_20h_kontrolu_ters_sirali_katmanlari_yakalar():
    """Güç setback'i 'yeterince büyük' ama GND'den İÇERİDE değilse (setback
    farkı ters) yine FAIL vermeli — bu iki farklı kök nedeni ayırt eder."""
    hedef = h_20h_setback_mm(0.1)  # min_setback = 2.0mm
    bulgu = yirmi_h_kontrolu([
        YirmiHOlcumu("F.Cu-In1.Cu", 0.1, guc_kenar_setback_mm=10.0, gnd_kenar_setback_mm=9.5)
    ])
    assert bulgu.durum == BulguDurumu.FAIL
    assert "içeride değil" in bulgu.ihlaller[0]["sorunlar"][0] or any(
        "içeride değil" in s for s in bulgu.ihlaller[0]["sorunlar"]
    )


def test_stitching_yuksek_frekans_daha_siki_aralik_ister():
    dusuk = stitching_max_araligi_mm(1.0)
    yuksek = stitching_max_araligi_mm(10.0)
    assert yuksek.maksimum_aralik_mm < dusuk.maksimum_aralik_mm


def test_via_araligi_kontrolu_asimi_yakalar():
    hedef = stitching_max_araligi_mm(5.0)
    bulgu = via_araligi_kontrolu([hedef.maksimum_aralik_mm * 2], 5.0)
    assert bulgu.durum == BulguDurumu.FAIL


def test_bos_girdi_kapsam_yok():
    assert uc_w_kontrolu([]).durum == BulguDurumu.KAPSAM_YOK
    assert yirmi_h_kontrolu([]).durum == BulguDurumu.KAPSAM_YOK
    assert via_araligi_kontrolu([], 5.0).durum == BulguDurumu.KAPSAM_YOK


def test_genel_sonuc_oncelik_sirasi():
    from bulgu_sozlesmesi import Bulgu

    assert genel_sonuc([Bulgu("x", BulguDurumu.FAIL, 1, [{"m": 1}])]) == "FAIL"
    assert genel_sonuc([Bulgu("x", BulguDurumu.KAPSAM_YOK, 0, [])]) == "NEEDS_HUMAN"
    assert genel_sonuc([Bulgu("x", BulguDurumu.PASS, 1, [])]) == "PASS"
