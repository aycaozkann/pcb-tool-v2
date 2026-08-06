"""empedans_cozucu.py için test suite. Çalıştırmak için: pytest -v test_empedans_cozucu.py"""

import pytest

from empedans_cozucu import (
    zdiff_mikroserit,
    zdiff_stripline,
    z0_mikroserit,
    hedefe_gore_coz,
    stackup_tara,
    oz_testleri_calistir,
    _testin_bos_olmadigini_kanitla,
)


def test_z0_mikroserit_pozitif_deger_dondurur():
    assert z0_mikroserit(0.4, 0.035, 1.6, 4.5) > 0


def test_zdiff_mikroserit_referans_deger_yuzde10_icinde():
    # 1.6mm FR4, 0.4mm iz/aralık -> ölçülmüş referans ~184 ohm
    z = zdiff_mikroserit(0.4, 0.4, 0.035, 1.6, 4.5)
    assert abs(z - 184.0) / 184.0 <= 0.10


def test_zdiff_h_arttikca_artar():
    dusuk = zdiff_mikroserit(0.4, 0.4, 0.035, 0.8, 4.5)
    yuksek = zdiff_mikroserit(0.4, 0.4, 0.035, 1.6, 4.5)
    assert yuksek > dusuk


def test_zdiff_w_arttikca_azalir():
    dar = zdiff_mikroserit(0.3, 0.4, 0.035, 1.6, 4.5)
    genis = zdiff_mikroserit(0.5, 0.4, 0.035, 1.6, 4.5)
    assert genis < dar


def test_zdiff_s_arttikca_artar():
    yakin = zdiff_mikroserit(0.4, 0.2, 0.035, 1.6, 4.5)
    uzak = zdiff_mikroserit(0.4, 0.6, 0.035, 1.6, 4.5)
    assert uzak > yakin


def test_zdiff_stripline_calisir_ve_pozitif():
    assert zdiff_stripline(0.15, 0.15, 0.035, 0.5, 4.3) > 0


def test_gecersiz_geometri_value_error_firlatir():
    with pytest.raises(ValueError):
        zdiff_mikroserit(50.0, 0.4, 0.035, 0.1, 4.5)  # log argümanı <= 1


def test_hedefe_gore_coz_en_iyi_5_sonucu_dondurur():
    sonuclar = hedefe_gore_coz(
        hedef_ohm=100.0, h=0.2, er=4.3, t=0.035,
        w_araligi=(0.05, 0.5, 0.01), s_araligi=(0.05, 0.5, 0.01),
        fab_min_w=0.09, fab_min_s=0.09,
    )
    assert len(sonuclar) <= 5
    assert sonuclar == sorted(sonuclar, key=lambda x: x["hata_yuzde"])


def test_stackup_tara_ulasilamayan_h_isaretlenir():
    # Çok ince dielektrikte çok yüksek hedef empedansa (500 ohm) fab
    # sınırlarıyla ulaşılamaz -> ULASILAMAZ olarak işaretlenmeli, sessizce
    # "en yakın sonuç" ile PASS gibi gösterilmemeli.
    rapor = stackup_tara(
        hedef_ohm=500.0, er=4.5, t=0.035,
        w_araligi=(0.1, 1.0, 0.05), s_araligi=(0.1, 1.0, 0.05),
        fab_min_w=0.127, fab_min_s=0.127, h_adaylari=(0.1,),
    )
    assert rapor["stackuplar"][0]["durum"] == "ULASILAMAZ"
    assert 0.1 in rapor["ulasilamayan_h_mm"]


def test_stackup_tara_ulasilabilir_hedef_pass_verir():
    rapor = stackup_tara(
        hedef_ohm=100.0, er=4.3, t=0.035,
        w_araligi=(0.05, 1.0, 0.01), s_araligi=(0.05, 1.0, 0.01),
        fab_min_w=0.09, fab_min_s=0.09, h_adaylari=(0.2, 0.3),
    )
    assert any(s["durum"] == "ULASILABILIR" for s in rapor["stackuplar"])


# ------------------------------------------------------------------
# FAULT-INJECTION — testin gerçekten bir şey kanıtladığını göster
# (CLAUDE.md honesty §6: "test yazdıysan boş olmadığını fault-injection
# ile kanıtla" ilkesinin bu modüldeki karşılığı)
# ------------------------------------------------------------------

def test_referans_testi_yanlis_katsayiyi_gercekten_reddediyor():
    """Bilerek yanlış (60/87 karışıklığı) bir katsayı ile hesaplanan Zdiff,
    referans testten GEÇMEMELİ. Eğer geçerse referans testimiz boştur —
    her zaman PASS veren bir test hiçbir şeyi doğrulamıyor demektir."""
    assert _testin_bos_olmadigini_kanitla() is True


def test_oz_testleri_calistir_hata_vermeden_biter():
    oz_testleri_calistir()  # AssertionError fırlatmamalı
