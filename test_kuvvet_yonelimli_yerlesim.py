"""kuvvet_yonelimli_yerlesim.py için test suite.
Çalıştırmak için:  pytest -v test_kuvvet_yonelimli_yerlesim.py
"""

import math

import pytest

from bulgu_sozlesmesi import BulguDurumu

from kuvvet_yonelimli_yerlesim import (
    Komponent,
    MesafeKisiti,
    Net,
    baslangic_yerlesimi_uret,
    cakisma_kontrolu,
    duzlem_neti_mi,
    kisitlari_dogrula,
    kumeleri_bul,
    netlistten_graf_kur,
    oz_testleri_calistir,
    ratsnest_uzunlugu_toplami,
    yerlesim_coz,
    yerlesim_raporu_uret,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Graf kurulumu
# ------------------------------------------------------------------

def test_iki_pinli_net_tek_kenar_uretir():
    kenarlar = netlistten_graf_kur([Net("SDA", ["U1", "U2"])])
    assert kenarlar == {("U1", "U2"): 1.0}


def test_cok_pinli_net_agirligi_bolusturur():
    """4 pinli net: her kenar 1/(4-1) = 0.333 ağırlık alır — 2 pinli kritik
    bir neti ezmemesi için."""
    kenarlar = netlistten_graf_kur([Net("BUS", ["U1", "U2", "U3", "U4"])])
    assert len(kenarlar) == 6  # C(4,2)
    for w in kenarlar.values():
        assert w == pytest.approx(1 / 3)


def test_gnd_ve_guc_netleri_grafige_girmez():
    assert duzlem_neti_mi("GND")
    assert duzlem_neti_mi("+3V3")
    assert not duzlem_neti_mi("GND_SENSE")  # gerçekten çizilen sense hattı
    assert netlistten_graf_kur([Net("GND", ["U1", "U2", "U3"])]) == {}


def test_duzlem_atlamasi_kapatilabilir():
    kenarlar = netlistten_graf_kur([Net("GND", ["U1", "U2"])], duzlem_netlerini_atla=False)
    assert kenarlar == {("U1", "U2"): 1.0}


def test_tek_pinli_net_kenar_uretmez():
    assert netlistten_graf_kur([Net("NC", ["U1"])]) == {}


def test_ayni_cift_birden_fazla_netten_agirlik_toplar():
    kenarlar = netlistten_graf_kur([Net("SDA", ["U1", "U2"]), Net("SCL", ["U1", "U2"])])
    assert kenarlar[("U1", "U2")] == pytest.approx(2.0)


# ------------------------------------------------------------------
# Kümeleme
# ------------------------------------------------------------------

def test_kumeleme_iki_bagimsiz_grubu_ayirir():
    kenarlar = netlistten_graf_kur([Net("A", ["U1", "C1"]), Net("B", ["U2", "C2"])])
    kumeler = kumeleri_bul(kenarlar, ["U1", "C1", "U2", "C2"])
    assert sorted(kumeler) == [["C1", "U1"], ["C2", "U2"]]


def test_baglantisiz_komponent_tek_elemanli_kume_olarak_doner():
    """Kapsam kaybı yok — bağlantısız parça sessizce düşürülmez."""
    kenarlar = netlistten_graf_kur([Net("A", ["U1", "C1"])])
    kumeler = kumeleri_bul(kenarlar, ["U1", "C1", "TP1"])
    assert ["TP1"] in kumeler


def test_zayif_kenar_kume_sinirini_gecmez():
    """10 pinli bir bus'tan gelen 0.111 ağırlıklı bağlar (eşik 0.5) küme
    birleştirmemeli — aksi halde her şey tek dev kümeye girer."""
    kenarlar = netlistten_graf_kur([Net("BUS", [f"U{i}" for i in range(10)])])
    kumeler = kumeleri_bul(kenarlar, [f"U{i}" for i in range(10)], agirlik_esigi=0.5)
    assert len(kumeler) == 10


# ------------------------------------------------------------------
# Başlangıç yerleşimi / determinizm
# ------------------------------------------------------------------

def test_baslangic_yerlesimi_deterministik():
    komponentler = [Komponent(f"U{i}") for i in range(10)]
    a = baslangic_yerlesimi_uret(komponentler, 30.0, 30.0)
    b = baslangic_yerlesimi_uret(komponentler, 30.0, 30.0)
    assert a == b


def test_baslangic_yerlesimi_sabit_komponente_dokunmaz():
    komponentler = [Komponent("J1", x=1.0, y=2.0, sabit=True), Komponent("U1")]
    koord = baslangic_yerlesimi_uret(komponentler, 30.0, 30.0)
    assert koord["J1"] == (1.0, 2.0)


def test_baslangic_yerlesimi_gecersiz_kart_boyutu_reddeder():
    with pytest.raises(ValueError):
        baslangic_yerlesimi_uret([Komponent("U1")], 0.0, 10.0)


def test_yerlesim_coz_deterministik():
    komponentler = [Komponent(f"U{i}") for i in range(8)]
    netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3", "U4"])]
    s1 = yerlesim_coz(komponentler, netler, 40.0, 40.0)
    s2 = yerlesim_coz([Komponent(f"U{i}") for i in range(8)], netler, 40.0, 40.0)
    assert s1.koordinatlar == s2.koordinatlar


# ------------------------------------------------------------------
# Fizik motoru — asıl iş
# ------------------------------------------------------------------

def test_motor_ratsnest_uzunlugunu_kisaltir():
    komponentler = [Komponent(f"U{i}", 2.0, 2.0) for i in range(10)]
    netler = [Net("A", ["U0", "U9"]), Net("B", ["U1", "U8"]), Net("C", ["U2", "U7"])]
    sonuc = yerlesim_coz(komponentler, netler, 60.0, 60.0)
    assert sonuc.son_ratsnest_mm < sonuc.baslangic_ratsnest_mm
    assert sonuc.iyilesme_orani > 0.2


def test_bagli_komponentler_bagimsizlardan_daha_yakin_biter():
    komponentler = [Komponent(r, 1.0, 1.0) for r in ("U1", "C1", "U2")]
    netler = [Net("VDD_SENSE", ["U1", "C1"])]  # U2 hiçbir şeye bağlı değil
    sonuc = yerlesim_coz(komponentler, netler, 40.0, 40.0)
    k = sonuc.koordinatlar
    bagli = math.dist(k["U1"], k["C1"])
    bagimsiz = math.dist(k["U1"], k["U2"])
    assert bagli < bagimsiz


def test_sabit_komponent_hic_hareket_etmez():
    komponentler = [
        Komponent("J1", 5.0, 5.0, x=2.5, y=2.5, sabit=True),
        Komponent("U1", 2.0, 2.0),
    ]
    sonuc = yerlesim_coz(komponentler, [Net("D+", ["J1", "U1"])], 40.0, 40.0)
    assert sonuc.koordinatlar["J1"] == (2.5, 2.5)


def test_koordinatlar_kart_sinirlari_icinde_kalir():
    komponentler = [Komponent(f"U{i}", 4.0, 4.0) for i in range(12)]
    netler = [Net("A", [f"U{i}" for i in range(12)], agirlik=5.0)]
    sonuc = yerlesim_coz(komponentler, netler, 30.0, 20.0)
    for x, y in sonuc.koordinatlar.values():
        assert 2.0 - 1e-6 <= x <= 28.0 + 1e-6
        assert 2.0 - 1e-6 <= y <= 18.0 + 1e-6


def test_agir_net_altinda_bile_cakisma_kalmaz():
    """REGRESYON TESTİ (gerçek bir hata yakaladı): ağırlığı 10 olan 6 pinli
    bir net, saf kuvvet dengesinde çekimin itmeyi EZMESİNE ve 6 çiftin
    6'sının da çakışmasına yol açıyordu. `_cakismalari_ayir()` ayırma geçişi
    bu yüzden eklendi — kart yeterince büyükken çakışma SIFIR olmalı."""
    komponentler = [Komponent(f"U{i}", 3.0, 3.0) for i in range(6)]
    netler = [Net("CLK", [f"U{i}" for i in range(6)], agirlik=10.0)]
    sonuc = yerlesim_coz(komponentler, netler, 50.0, 50.0)
    bulgu = cakisma_kontrolu(komponentler, sonuc.koordinatlar)
    assert bulgu.durum == BulguDurumu.PASS, bulgu.ihlaller


def test_ayirma_kart_cok_kucukse_sessizce_basarili_saymaz():
    """Kart fiziksel olarak yetmiyorsa ayırma çakışmayı çözemez ve bu
    DÜRÜSTÇE FAIL olarak raporlanır — sessiz 'ayırdım sayılır' yok."""
    komponentler = [Komponent(f"U{i}", 5.0, 5.0) for i in range(6)]
    netler = [Net("CLK", [f"U{i}" for i in range(6)])]
    sonuc = yerlesim_coz(komponentler, netler, 8.0, 8.0)
    assert cakisma_kontrolu(komponentler, sonuc.koordinatlar).durum == BulguDurumu.FAIL


def test_bos_netlist_hata_firlatmaz():
    sonuc = yerlesim_coz([], [], 10.0, 10.0)
    assert sonuc.koordinatlar == {}
    assert sonuc.iyilesme_orani == 0.0


def test_maks_kisiti_mesafeyi_kisaltir():
    """Decoupling kuralı (<=1.5mm): U1 ile C1 arasında ÇEKEN bir net YOK
    (C1'in besleme rayı bir düzlem, grafiğe girmiyor) — onları yaklaştıran
    tek şey kısıt kuvvetidir. Kısıt gerçekten bağlayıcı olmalı ki test bir
    şey ölçsün (ilk taslakta net çekimi zaten 1.3mm veriyordu, kısıt hiç
    devreye girmiyordu — o test boştu)."""
    komponentler = [Komponent("U1", 1.0, 1.0), Komponent("C1", 1.0, 1.0), Komponent("U2", 1.0, 1.0)]
    netler = [Net("GND", ["U1", "C1"]), Net("SIG", ["U2", "C1"], agirlik=8.0)]
    kisitsiz = yerlesim_coz(komponentler, netler, 40.0, 40.0)
    kisitli = yerlesim_coz(
        komponentler, netler, 40.0, 40.0,
        kisitlar=[MesafeKisiti("U1", "C1", maks_mm=1.5, aciklama="decoupling")],
    )
    assert math.dist(kisitli.koordinatlar["U1"], kisitli.koordinatlar["C1"]) < \
        math.dist(kisitsiz.koordinatlar["U1"], kisitsiz.koordinatlar["C1"])


def test_min_kisiti_mesafeyi_uzatir():
    """LDO <-> I2C >=10mm izolasyon kuralı."""
    komponentler = [Komponent("U5", 2.0, 2.0), Komponent("U1", 2.0, 2.0)]
    netler = [Net("EN", ["U5", "U1"])]
    kisitsiz = yerlesim_coz(komponentler, netler, 60.0, 60.0)
    kisitli = yerlesim_coz(
        komponentler, netler, 60.0, 60.0,
        kisitlar=[MesafeKisiti("U5", "U1", min_mm=10.0, aciklama="LDO izolasyonu")],
    )
    assert math.dist(kisitli.koordinatlar["U5"], kisitli.koordinatlar["U1"]) > \
        math.dist(kisitsiz.koordinatlar["U5"], kisitsiz.koordinatlar["U1"])


# ------------------------------------------------------------------
# Sert kapılar (Bulgu sözleşmesi)
# ------------------------------------------------------------------

def test_cakisma_kontrolu_temiz_yerlesimde_pass():
    komponentler = [Komponent("U1", 2.0, 2.0), Komponent("U2", 2.0, 2.0)]
    bulgu = cakisma_kontrolu(komponentler, {"U1": (0.0, 0.0), "U2": (10.0, 0.0)})
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.gecti_mi


def test_cakisma_kontrolu_ust_uste_binende_fail():
    komponentler = [Komponent("U1", 2.0, 2.0), Komponent("U2", 2.0, 2.0)]
    bulgu = cakisma_kontrolu(komponentler, {"U1": (0.0, 0.0), "U2": (0.5, 0.0)})
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["a"] == "U1"


def test_cakisma_kontrolu_bos_yerlesimde_kapsam_yok():
    """'Hiç komponent yok' sessizce PASS sayılamaz."""
    bulgu = cakisma_kontrolu([], {})
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert not bulgu.gecti_mi


def test_kisitlari_dogrula_ihlali_olcer():
    kisitlar = [MesafeKisiti("U1", "C1", maks_mm=1.5, aciklama="decoupling")]
    bulgu = kisitlari_dogrula(kisitlar, {"U1": (0.0, 0.0), "C1": (5.0, 0.0)})
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["olculen_mm"] == 5.0
    assert bulgu.ihlaller[0]["tip"] == "maks"


def test_kisitlari_dogrula_saglananda_pass():
    kisitlar = [MesafeKisiti("U1", "C1", maks_mm=1.5)]
    bulgu = kisitlari_dogrula(kisitlar, {"U1": (0.0, 0.0), "C1": (1.0, 0.0)})
    assert bulgu.durum == BulguDurumu.PASS


def test_kisit_listesi_bossa_kapsam_yok():
    bulgu = kisitlari_dogrula([], {"U1": (0.0, 0.0)})
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


def test_min_kisit_ihlali_raporlanir():
    kisitlar = [MesafeKisiti("U5", "U1", min_mm=10.0)]
    bulgu = kisitlari_dogrula(kisitlar, {"U5": (0.0, 0.0), "U1": (3.0, 0.0)})
    assert bulgu.ihlaller[0]["tip"] == "min"


# ------------------------------------------------------------------
# Rapor + öz test
# ------------------------------------------------------------------

def test_rapor_uyari_notunu_icerir():
    komponentler = [Komponent("U1"), Komponent("C1")]
    netler = [Net("VDD_SENSE", ["U1", "C1"])]
    sonuc = yerlesim_coz(komponentler, netler, 20.0, 20.0)
    kenarlar = netlistten_graf_kur(netler)
    rapor = yerlesim_raporu_uret(
        sonuc,
        kumeleri_bul(kenarlar, ["U1", "C1"]),
        [cakisma_kontrolu(komponentler, sonuc.koordinatlar)],
    )
    assert "TOHUM yerleşimdir" in rapor
    assert "z_kontrolu_yap" in rapor
    assert "courtyard_cakismasi" in rapor


def test_ratsnest_uzunlugu_bilinen_deger():
    kenarlar = {("U1", "U2"): 2.0}
    assert ratsnest_uzunlugu_toplami({"U1": (0.0, 0.0), "U2": (3.0, 4.0)}, kenarlar) == 10.0


def test_ratsnest_eksik_koordinati_atlar():
    assert ratsnest_uzunlugu_toplami({"U1": (0.0, 0.0)}, {("U1", "U2"): 1.0}) == 0.0


def test_fault_injection_gercekten_kirilir():
    """Çekim katsayısı 0 iken motor iyileştirme YAPAMAMALI — bu, iyileşme
    testinin boş olmadığının kanıtı."""
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
