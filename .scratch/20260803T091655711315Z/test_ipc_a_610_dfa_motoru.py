"""ipc_a_610_dfa_motoru.py için test suite (pytest)."""

from __future__ import annotations

import pytest

from bulgu_sozlesmesi import BulguDurumu
from ipc_a_610_dfa_motoru import (
    IpcA610DfaMotoru,
    KomponentTipi,
    MontajSinifi,
    PaketBoyutlari,
    YerlesikKomponent,
    minimum_clearance_hesapla,
    minimum_kenar_clearance_mm,
    oz_testleri_calistir,
)


def test_modulun_kendi_oz_testleri_temiz():
    assert oz_testleri_calistir() == []


def test_paket_boyutlari_pozitif_zorunlu():
    with pytest.raises(ValueError):
        PaketBoyutlari(0, 1, 1)


def test_konnektor_her_zaman_buyuk_clearance_ister():
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    smd = minimum_clearance_hesapla(KomponentTipi.SMD_PASIF, KomponentTipi.SMD_PASIF, kucuk, kucuk)
    konn = minimum_clearance_hesapla(KomponentTipi.SMD_PASIF, KomponentTipi.KONNEKTOR, kucuk, kucuk)
    assert konn.minimum_clearance_mm > smd.minimum_clearance_mm


def test_kenar_keepout_konnektor_en_buyuk():
    assert minimum_kenar_clearance_mm(KomponentTipi.KONNEKTOR) > minimum_kenar_clearance_mm(KomponentTipi.SMD_PASIF)


def test_yerlesim_ihlali_dogru_ciftler_arasinda_raporlanir():
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    motor = IpcA610DfaMotoru()
    yerlesim = [
        YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0, 0),
        YerlesikKomponent("R2", KomponentTipi.SMD_PASIF, kucuk, 1.05, 0),  # çok yakın -> FAIL
        YerlesikKomponent("R3", KomponentTipi.SMD_PASIF, kucuk, 50, 50),  # çok uzak -> temiz
    ]
    bulgu = motor.komponent_clearance_kontrolu(yerlesim)
    assert bulgu.durum == BulguDurumu.FAIL
    refs = {(v["a"], v["b"]) for v in bulgu.ihlaller}
    assert ("R1", "R2") in refs
    assert not any("R3" in (v["a"], v["b"]) for v in bulgu.ihlaller)


def test_kenar_kontrolu_bos_kenar_listesi_kapsam_yok():
    motor = IpcA610DfaMotoru()
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    bulgu = motor.kenar_clearance_kontrolu(
        [YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0, 0)], []
    )
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


def test_kenar_kontrolu_ihlali_yakalar():
    motor = IpcA610DfaMotoru()
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    kenar = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 50.0)]
    yerlesim = [YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0.5, 50.0)]  # kenara çok yakın
    bulgu = motor.kenar_clearance_kontrolu(yerlesim, kenar)
    assert bulgu.durum == BulguDurumu.FAIL


def test_genel_sonuc_fail_kapsam_yok_ve_pass_oncelik_sirasi():
    motor = IpcA610DfaMotoru()
    from bulgu_sozlesmesi import Bulgu

    fail_var = [Bulgu("x", BulguDurumu.FAIL, 1, [{"m": 1}]), Bulgu("y", BulguDurumu.KAPSAM_YOK, 0, [])]
    assert motor.genel_sonuc(fail_var) == "FAIL"

    kapsam_yok_var = [Bulgu("x", BulguDurumu.PASS, 1, []), Bulgu("y", BulguDurumu.KAPSAM_YOK, 0, [])]
    assert motor.genel_sonuc(kapsam_yok_var) == "NEEDS_HUMAN"

    hepsi_temiz = [Bulgu("x", BulguDurumu.PASS, 1, [])]
    assert motor.genel_sonuc(hepsi_temiz) == "PASS"
