"""bulgu_sozlesmesi.py için test suite."""

import pytest

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret, liste_sonucundan_bulgu_uret, ozet_rapor


def test_taranan_sifir_iken_durum_pass_olamaz():
    with pytest.raises(ValueError):
        Bulgu("test", BulguDurumu.PASS, 0)


def test_taranan_sifirsa_bulgu_uret_kapsam_yok_doner():
    b = bulgu_uret("test", 0)
    assert b.durum == BulguDurumu.KAPSAM_YOK
    assert b.gecti_mi is False


def test_taranan_var_ihlal_yoksa_pass():
    b = bulgu_uret("test", 5, [])
    assert b.durum == BulguDurumu.PASS
    assert b.gecti_mi is True


def test_taranan_var_ihlal_varsa_fail():
    b = bulgu_uret("test", 5, [{"mesaj": "x"}])
    assert b.durum == BulguDurumu.FAIL
    assert b.gecti_mi is False


def test_kapsam_yok_gecti_mi_false_dondurur():
    """KAPSAM_YOK bilerek False'tur — 'kontrol edilmedi' bir başarı değildir."""
    b = bulgu_uret("test", 0)
    assert b.gecti_mi is False


def test_liste_sonucundan_bulgu_uret_bos_liste_pass():
    b = liste_sonucundan_bulgu_uret("eski_kontrol", [], taranan=3)
    assert b.durum == BulguDurumu.PASS


def test_liste_sonucundan_bulgu_uret_dolu_liste_fail():
    b = liste_sonucundan_bulgu_uret("eski_kontrol", ["KRİTİK: x"], taranan=3)
    assert b.durum == BulguDurumu.FAIL
    assert b.ihlaller[0]["mesaj"] == "KRİTİK: x"


def test_ozet_rapor_sayimi_dogru():
    bulgular = [
        bulgu_uret("a", 5, []),
        bulgu_uret("b", 5, [{"x": 1}]),
        bulgu_uret("c", 0, []),
    ]
    rapor = ozet_rapor(bulgular)
    assert rapor["ozet"]["PASS"] == 1
    assert rapor["ozet"]["FAIL"] == 1
    assert rapor["ozet"]["KAPSAM_YOK"] == 1
    assert len(rapor["kontroller"]) == 3
