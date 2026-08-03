"""ipc2152_hesaplayici.py için test suite.
Çalıştırmak için:  pytest -v test_ipc2152_hesaplayici.py
"""

import pytest

from pcb_stackup_planner import iz_genisligi_hesapla_mm

from ipc2152_hesaplayici import (
    Ipc2152Sonucu,
    KatmanTipi,
    VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI,
    ic_dis_karsilastirmasi_uret,
    ipc2152_min_iz_genisligi_mm,
    oz_testleri_calistir,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Tek-kaynak-gerçeklik: pcb_stackup_planner ile tutarlılık
# ------------------------------------------------------------------

def test_dis_katmanda_temel_formulle_birebir_eslesir():
    """Dış katmanda derating katsayısı 1.0 olduğu için sonuç, ÇEKİRDEK
    olarak kullanılan `iz_genisligi_hesapla_mm()` ile BİREBİR aynı olmalı
    — iki modül arasında sessiz sapma YOK."""
    beklenen = iz_genisligi_hesapla_mm(5.0, 10.0, 1.0, dis_katman_mi=True)
    sonuc = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS)
    assert sonuc.genislik_mm == pytest.approx(round(beklenen, 4))


def test_ic_katmanda_derating_uygulanir():
    temel = iz_genisligi_hesapla_mm(5.0, 10.0, 1.0, dis_katman_mi=False)
    sonuc = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.IC)
    assert sonuc.genislik_mm == pytest.approx(
        round(temel * VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI, 4)
    )


def test_ozel_derating_katsayisi_kullanilir():
    sonuc = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.IC, ic_katman_derating_katsayisi=1.5)
    assert sonuc.ic_katman_derating_katsayisi == 1.5


# ------------------------------------------------------------------
# Fiziksel tutarlılık
# ------------------------------------------------------------------

def test_ic_katman_dis_katmandan_daha_dar_olamaz():
    sonuclar = ic_dis_karsilastirmasi_uret(8.0, 15.0)
    assert sonuclar["internal"].genislik_mm >= sonuclar["external"].genislik_mm


def test_akim_arttikca_genislik_artar():
    dusuk = ipc2152_min_iz_genisligi_mm(1.0, 10.0, KatmanTipi.DIS)
    yuksek = ipc2152_min_iz_genisligi_mm(10.0, 10.0, KatmanTipi.DIS)
    assert yuksek.genislik_mm > dusuk.genislik_mm


def test_sicaklik_artisi_arttikca_genislik_azalir():
    """Daha fazla sıcaklık artışına izin verilirse (daha toleranslı) daha
    dar bir iz yeterli olur."""
    dar_tolerans = ipc2152_min_iz_genisligi_mm(5.0, 5.0, KatmanTipi.DIS)
    genis_tolerans = ipc2152_min_iz_genisligi_mm(5.0, 30.0, KatmanTipi.DIS)
    assert genis_tolerans.genislik_mm < dar_tolerans.genislik_mm


def test_bakir_kalinligi_arttikca_genislik_azalir():
    ince = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS, bakir_kalinligi_oz=1.0)
    kalin = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS, bakir_kalinligi_oz=2.0)
    assert kalin.genislik_mm < ince.genislik_mm


def test_sonuc_dataclass_alanlari_dolu():
    sonuc = ipc2152_min_iz_genisligi_mm(3.0, 10.0, KatmanTipi.DIS)
    assert isinstance(sonuc, Ipc2152Sonucu)
    assert sonuc.kesit_alani_mil2 > 0
    assert sonuc.katman_tipi == KatmanTipi.DIS
    assert "IPC-2221" in sonuc.model


# ------------------------------------------------------------------
# Girdi doğrulaması — sessiz 0/negatif genişlik üretilmemeli
# ------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"akim_A": 0.0},
    {"akim_A": -5.0},
    {"delta_t_C": 0.0},
    {"delta_t_C": -1.0},
    {"bakir_kalinligi_oz": 0.0},
    {"bakir_kalinligi_oz": -1.0},
])
def test_gecersiz_girdi_value_error_firlatir(kwargs):
    varsayilan = {"akim_A": 5.0, "delta_t_C": 10.0, "katman_tipi": KatmanTipi.DIS, "bakir_kalinligi_oz": 1.0}
    varsayilan.update(kwargs)
    with pytest.raises(ValueError):
        ipc2152_min_iz_genisligi_mm(**varsayilan)


def test_derating_katsayisi_1den_kucuk_reddedilir():
    """İç katman FİZİKSEL OLARAK dış katmandan daha az pay isteyemez —
    bu yüzden derating katsayısı < 1.0 kabul edilemez."""
    with pytest.raises(ValueError):
        ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.IC, ic_katman_derating_katsayisi=0.5)


def test_ic_dis_karsilastirmasi_iki_anahtar_doner():
    sonuclar = ic_dis_karsilastirmasi_uret(5.0, 10.0)
    assert set(sonuclar) == {"internal", "external"}


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
