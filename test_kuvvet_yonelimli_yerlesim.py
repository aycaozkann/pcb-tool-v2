"""kuvvet_yonelimli_yerlesim.py için test suite.
Çalıştırmak için:  pytest -v test_kuvvet_yonelimli_yerlesim.py
"""

import math

import pytest

from bulgu_sozlesmesi import BulguDurumu

from ecad_mcad_termal_kopru import KomponentTermalDurumu, TermalTemasBolgesi
from pcb_stackup_planner import TermalYonetim

from kuvvet_yonelimli_yerlesim import (
    Komponent,
    MesafeKisiti,
    Net,
    YerlesimKategorisi,
    YerlesimParametreSeti,
    YerlesimSkoru,
    YuksekHizKeepout,
    YUKSEK_HIZLI_VARSAYILAN_AGIRLIK,
    VARSAYILAN_PARAMETRE_SETLERI,
    baslangic_yerlesimi_uret,
    cakisma_kontrolu,
    coklu_yerlesim_dene,
    duzlem_neti_mi,
    hiyerarsik_yerlesim_coz,
    keepout_cakismasi_kontrolu,
    kisitlari_dogrula,
    kumeleri_bul,
    netlistten_graf_kur,
    oz_testleri_calistir,
    ratsnest_uzunlugu_toplami,
    termal_kisitlarini_uret,
    yerlesim_coz,
    yerlesim_raporu_uret,
    yerlesim_skoru,
    yuksek_hiz_keepout_hesapla,
    yuksek_hiz_keepout_kontrolu,
    yuksek_hizli_net_mi,
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


# ------------------------------------------------------------------
# hiyerarsik_yerlesim_coz (main.py Faz 4 entegrasyonu, 2026-08-03)
# ------------------------------------------------------------------

def test_hiyerarsik_yerlesim_tum_kategorileri_yerlestirir():
    komponentler = [Komponent(f"U{i}") for i in range(6)]
    kategoriler = {
        "U0": YerlesimKategorisi.GUC_DEKUPLAJ, "U1": YerlesimKategorisi.GUC_DEKUPLAJ,
        "U2": YerlesimKategorisi.KRITIK_HS, "U3": YerlesimKategorisi.KRITIK_HS,
        "U4": YerlesimKategorisi.DUSUK_HIZ_IO, "U5": YerlesimKategorisi.DUSUK_HIZ_IO,
    }
    netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3"]), Net("C", ["U4", "U5"])]
    sonuc = hiyerarsik_yerlesim_coz(komponentler, kategoriler, netler, 40.0, 40.0)
    assert set(sonuc.koordinatlar) == {"U0", "U1", "U2", "U3", "U4", "U5"}


def test_hiyerarsik_yerlesim_onceki_asama_kilitlenir():
    """Güç/dekuplaj (U0/U1) aşaması bittikten sonra, HS aşamasında (U2/U3)
    U0/U1'in konumu DEĞİŞMEMELİ — sonraki aşamalar önceki aşamayı sabit
    kilitler, geriye doğru hareket ettirmez."""
    komponentler = [Komponent(f"U{i}") for i in range(4)]
    kategoriler = {
        "U0": YerlesimKategorisi.GUC_DEKUPLAJ, "U1": YerlesimKategorisi.GUC_DEKUPLAJ,
        "U2": YerlesimKategorisi.KRITIK_HS, "U3": YerlesimKategorisi.KRITIK_HS,
    }
    netler = [Net("A", ["U0", "U1"]), Net("B", ["U1", "U2"]), Net("C", ["U2", "U3"])]

    sadece_guc = hiyerarsik_yerlesim_coz(
        komponentler[:2], {"U0": YerlesimKategorisi.GUC_DEKUPLAJ, "U1": YerlesimKategorisi.GUC_DEKUPLAJ},
        [Net("A", ["U0", "U1"])], 40.0, 40.0,
    )
    tam = hiyerarsik_yerlesim_coz(komponentler, kategoriler, netler, 40.0, 40.0)

    assert tam.koordinatlar["U0"] == sadece_guc.koordinatlar["U0"]
    assert tam.koordinatlar["U1"] == sadece_guc.koordinatlar["U1"]


def test_hiyerarsik_yerlesim_kategorisiz_sabit_komponent_korunur():
    sabit_konnektor = Komponent("J1", 10.0, 5.0, x=35.0, y=35.0, sabit=True)
    hareketli = Komponent("U0")
    kategoriler = {"U0": YerlesimKategorisi.GUC_DEKUPLAJ}
    netler = [Net("A", ["U0", "J1"])]
    sonuc = hiyerarsik_yerlesim_coz([sabit_konnektor, hareketli], kategoriler, netler, 40.0, 40.0)
    assert sonuc.koordinatlar["J1"] == (35.0, 35.0)


def test_hiyerarsik_yerlesim_bos_komponent_listesi():
    sonuc = hiyerarsik_yerlesim_coz([], {}, [], 40.0, 40.0)
    assert sonuc.koordinatlar == {}
    assert sonuc.iterasyon == 0


def test_hiyerarsik_yerlesim_ratsnest_iyilesir():
    komponentler = [Komponent(f"U{i}") for i in range(6)]
    kategoriler = {
        "U0": YerlesimKategorisi.GUC_DEKUPLAJ, "U1": YerlesimKategorisi.GUC_DEKUPLAJ,
        "U2": YerlesimKategorisi.KRITIK_HS, "U3": YerlesimKategorisi.KRITIK_HS,
        "U4": YerlesimKategorisi.DUSUK_HIZ_IO, "U5": YerlesimKategorisi.DUSUK_HIZ_IO,
    }
    netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3"]), Net("C", ["U4", "U5"])]
    sonuc = hiyerarsik_yerlesim_coz(komponentler, kategoriler, netler, 40.0, 40.0)
    assert sonuc.son_ratsnest_mm < sonuc.baslangic_ratsnest_mm


# ------------------------------------------------------------------
# termal_kisitlarini_uret (Faz 4b termal keepout -> yerleşim GİRDİSİ)
# ------------------------------------------------------------------

_KARE_YUZEY = TermalTemasBolgesi(
    isim="heatsink_boss_1", poligon=[(0, 0), (10, 0), (10, 10), (0, 10)], z_boslugu_mm=0.3,
)


def _termal_durum(isim: str, x: float, y: float, guc_w: float = 1.0) -> KomponentTermalDurumu:
    return KomponentTermalDurumu(
        yonetim=TermalYonetim(isim=isim, guc_yayilimi_W=guc_w, mevcut_termal_via_sayisi=10),
        x=x, y=y,
    )


def test_termal_kisitlarini_uret_yuzey_disindaki_komponent_kisit_uretmez():
    komponentler, kisitlar = termal_kisitlarini_uret([_termal_durum("U1", 50.0, 50.0)], [_KARE_YUZEY])
    assert komponentler == []
    assert kisitlar == []


def test_termal_kisitlarini_uret_yuzey_icindeki_komponent_kisit_uretir():
    komponentler, kisitlar = termal_kisitlarini_uret([_termal_durum("U1", 5.0, 5.0)], [_KARE_YUZEY])
    assert len(komponentler) == 1
    assert komponentler[0].sabit is True
    assert komponentler[0].x == 5.0 and komponentler[0].y == 5.0  # kare merkezi
    assert len(kisitlar) == 1
    assert kisitlar[0].ref_a == "U1"
    assert kisitlar[0].ref_b == komponentler[0].ref
    assert kisitlar[0].maks_mm == 3.0


def test_termal_kisitlarini_uret_veri_yoksa_bos_doner():
    komponentler, kisitlar = termal_kisitlarini_uret([], [])
    assert komponentler == []
    assert kisitlar == []


def test_termal_kisiti_yerlesime_gercekten_girdi_olur():
    """Üretilen (çapa komponent + kısıt), `yerlesim_coz()`'e geçince ısı
    kaynağı komponenti kasa temas merkezine GERÇEKTEN çeker — sadece
    veri üretimi değil, motora fiilen etki ettiğinin kanıtı."""
    komponentler, kisitlar = termal_kisitlarini_uret(
        [_termal_durum("U1", 35.0, 35.0)],
        [TermalTemasBolgesi(isim="boss", poligon=[(5, 5), (9, 5), (9, 9), (5, 9)], z_boslugu_mm=0.3)],
        maks_mesafe_mm=1.0,
    )
    hareketli = Komponent("U1", x=35.0, y=35.0)
    sonuc = yerlesim_coz([hareketli] + komponentler, [], 40.0, 40.0, kisitlar=kisitlar)
    ux, uy = sonuc.koordinatlar["U1"]
    # Başlangıçta (35,35) idi; çapa (7,7) civarında -> yaklaşmış olmalı.
    assert math.hypot(ux - 35.0, uy - 35.0) > 5.0


# ------------------------------------------------------------------
# HighSpeedRuleManager (Bölüm 6)
# ------------------------------------------------------------------

def test_yuksek_hizli_net_mi_diff_class():
    assert yuksek_hizli_net_mi("HERHANGI_BIR_ISIM", net_class="DIFF_90OHM")


def test_yuksek_hizli_net_mi_csi_mipi_isim():
    assert yuksek_hizli_net_mi("CAM0_CSI_D0")
    assert yuksek_hizli_net_mi("MIPI_CLK")


def test_yuksek_hizli_net_mi_p_n_kuyruk():
    assert yuksek_hizli_net_mi("HDMI0_TX0_P")
    assert yuksek_hizli_net_mi("ETH_TRD0_N")


def test_yuksek_hizli_net_mi_tek_karakter_govde_false_positive_onlenir():
    """`A_P` gibi 1 karakterlik gövdeli isimler kazara diferansiyel
    sayılmamalı - spesifikasyonun açıkça istediği false-positive önlemi."""
    assert not yuksek_hizli_net_mi("A_P")
    assert not yuksek_hizli_net_mi("N")


def test_yuksek_hizli_net_mi_sıradan_net_false():
    assert not yuksek_hizli_net_mi("GPIO5")
    assert not yuksek_hizli_net_mi("I2C_SCL")


def test_netlistten_graf_kur_yuksek_hizli_net_agirlik_otomatik_yukselir():
    """Elle agirlik verilmemiş (varsayılan 1.0) bir HS net, normal bir
    net'ten daha ağır bir kenar üretmeli - kullanıcı `agirlik=` yazmak
    ZORUNDA kalmamalı (görev A'nın ana amacı)."""
    kenarlar = netlistten_graf_kur([
        Net("HDMI0_TX0_P", ["U1", "U2"]),
        Net("GPIO5", ["U3", "U4"]),
    ])
    assert kenarlar[("U1", "U2")] > kenarlar[("U3", "U4")]
    assert kenarlar[("U1", "U2")] == pytest.approx(YUKSEK_HIZLI_VARSAYILAN_AGIRLIK)


def test_netlistten_graf_kur_elle_verilen_agirlik_ezilmez():
    """Kullanıcı bilinçli olarak agirlik=1.0 DIŞINDA bir değer verdiyse
    (örn. 0.5), otomatik HS yükseltmesi o değere DOKUNMAMALI."""
    kenarlar = netlistten_graf_kur([Net("HDMI0_TX0_P", ["U1", "U2"], agirlik=0.5)])
    assert kenarlar[("U1", "U2")] == pytest.approx(0.5)


def test_yuksek_hiz_keepout_hesapla_normal_net_icin_bos_doner():
    keepoutlar = yuksek_hiz_keepout_hesapla(
        Net("GPIO5", ["U1", "U2"]), {"U1": (0.0, 0.0), "U2": (10.0, 0.0)}, iz_genisligi_mm=0.2,
    )
    assert keepoutlar == []


def test_yuksek_hiz_keepout_hesapla_merkez_ve_yaricap():
    keepoutlar = yuksek_hiz_keepout_hesapla(
        Net("HDMI0_TX0_P", ["U1", "U2"]), {"U1": (0.0, 0.0), "U2": (10.0, 0.0)}, iz_genisligi_mm=0.2,
    )
    assert len(keepoutlar) == 1
    kp = keepoutlar[0]
    assert kp.merkez_x_mm == pytest.approx(5.0)
    assert kp.merkez_y_mm == pytest.approx(0.0)
    assert kp.yaricap_mm == pytest.approx(0.2 * 3.0 + 0.15)
    assert kp.kaynak_ref == "U1" and kp.hedef_ref == "U2"


def test_keepout_cakismasi_kontrolu_ucuncu_komponent_ihlal_eder():
    keepoutlar = [YuksekHizKeepout("TRD0", 5.0, 0.0, 1.0, kaynak_ref="D4", hedef_ref="D6")]
    komponentler = {
        "D4": Komponent("D4", 2.0, 2.0),
        "D6": Komponent("D6", 2.0, 2.0),
        "R1": Komponent("R1", 2.0, 2.0),
    }
    koordinatlar = {"D4": (0.0, 0.0), "D6": (10.0, 0.0), "R1": (5.0, 0.0)}
    ihlaller = keepout_cakismasi_kontrolu(koordinatlar, komponentler, keepoutlar)
    assert ihlaller == ["R1"]


def test_keepout_cakismasi_kontrolu_kendi_uclari_ihlal_sayilmaz():
    """D4/D6 - keepout'un KENDİ kaynak/hedefi - keepout'un merkezine ne
    kadar yakın olurlarsa olsunlar ihlalci sayılmamalı (bkz. YuksekHizKeepout
    docstring'i - aksi halde HER keepout kendi uçlarına karşı anlamsızca
    FAIL verirdi)."""
    keepoutlar = [YuksekHizKeepout("TRD0", 5.0, 0.0, 100.0, kaynak_ref="D4", hedef_ref="D6")]
    komponentler = {"D4": Komponent("D4", 2.0, 2.0), "D6": Komponent("D6", 2.0, 2.0)}
    koordinatlar = {"D4": (0.0, 0.0), "D6": (10.0, 0.0)}
    assert keepout_cakismasi_kontrolu(koordinatlar, komponentler, keepoutlar) == []


def test_yuksek_hiz_keepout_kontrolu_bulgu_sarmalayici():
    keepoutlar = [YuksekHizKeepout("TRD0", 5.0, 0.0, 1.0, kaynak_ref="D4", hedef_ref="D6")]
    komponentler = {"D4": Komponent("D4", 2.0, 2.0), "R1": Komponent("R1", 2.0, 2.0)}
    koordinatlar = {"D4": (0.0, 0.0), "R1": (5.0, 0.0)}
    bulgu = yuksek_hiz_keepout_kontrolu(koordinatlar, komponentler, keepoutlar)
    assert bulgu.kontrol == "yuksek_hiz_keepout_ihlali"
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller == [{"ref": "R1"}]


def test_yuksek_hiz_keepout_kontrolu_kapsam_yok_komponent_bossa():
    bulgu = yuksek_hiz_keepout_kontrolu({}, {}, [])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


def test_yerlesim_coz_keepout_ihlalini_reddeder():
    """FAULT-INJECTION BENZERİ KANIT: keepout olmadan güçlü bir çekim R1'i
    D4-D6 arasındaki koridora çeker (courtyard'lar çakışmadığı için itme
    devreye girmez); keepout VERİLDİĞİNDE aynı senaryoda R1 koridorun
    dışında KALMALI - yumuşak kuvvetin ezemediği somut bir kanıt."""
    komponentler = [
        Komponent("D4", 2.0, 2.0, x=5.0, y=20.0, sabit=True),
        Komponent("D6", 2.0, 2.0, x=45.0, y=20.0, sabit=True),
        Komponent("R1", 1.0, 1.0, x=25.0, y=5.0),
    ]
    # R1, D4 VE D6'nın İKİSİNE de bağlı -> keepout'suz denge noktası D4-D6
    # ORTASINA (tam olarak koridorun içine) çeker.
    netler = [
        Net("SIG_A", ["D4", "R1"], agirlik=20.0),
        Net("SIG_B", ["D6", "R1"], agirlik=20.0),
    ]

    keepoutlar = [YuksekHizKeepout("TRD0", 25.0, 20.0, 8.0, kaynak_ref="D4", hedef_ref="D6")]

    sonuc_keepoutsuz = yerlesim_coz(komponentler, netler, 50.0, 50.0, maks_iterasyon=200)
    sonuc_keepoutlu = yerlesim_coz(
        komponentler, netler, 50.0, 50.0, maks_iterasyon=200, keepoutlar=keepoutlar,
    )

    x, y = sonuc_keepoutlu.koordinatlar["R1"]
    mesafe_merkeze = math.hypot(x - 25.0, y - 20.0)
    r1_yaricap = math.hypot(1.0, 1.0) / 2.0
    assert mesafe_merkeze >= 8.0 + r1_yaricap - 1e-6, (
        "R1 keepout dairesinin İÇİNE girdi - SONSUZ itme uygulanmadı"
    )

    # Keepout'suz halde R1 gerçekten koridora girmiş olmalı (aksi halde bu
    # test hiçbir şey ölçmüyor demektir - fault-injection disiplini).
    xk, yk = sonuc_keepoutsuz.koordinatlar["R1"]
    assert math.hypot(xk - 25.0, yk - 20.0) < 8.0 + r1_yaricap


# ------------------------------------------------------------------
# FAZ 0.5-1: baslangic_aci_offset_rad
# ------------------------------------------------------------------

class TestBaslangicAciOffset:
    def test_offset_sifirsa_eski_davranisla_ayni(self):
        komponentler = [Komponent(f"U{i}") for i in range(5)]
        a = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0)
        b = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=0.0)
        assert a == b

    def test_farkli_offset_farkli_baslangic_uretir_ama_deterministik(self):
        komponentler = [Komponent(f"U{i}") for i in range(5)]
        a = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=0.0)
        b = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=math.pi / 3)
        assert a != b
        # aynı offset -> aynı sonuç (determinizm)
        b2 = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=math.pi / 3)
        assert b == b2

    def test_sabit_komponent_offsetten_etkilenmez(self):
        komponentler = [Komponent("J1", x=1.0, y=2.0, sabit=True), Komponent("U1")]
        a = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=0.0)
        b = baslangic_yerlesimi_uret(komponentler, 40.0, 40.0, baslangic_aci_offset_rad=1.0)
        assert a["J1"] == b["J1"] == (1.0, 2.0)


# ------------------------------------------------------------------
# FAZ 0.5-1: yerlesim_skoru / coklu_yerlesim_dene
# ------------------------------------------------------------------

class TestYerlesimSkoru:
    def test_ratsnest_uzunlugu_dogrudan_skora_yansir(self):
        komponentler = [Komponent(f"U{i}") for i in range(4)]
        netler = [Net("A", ["U0", "U1"])]
        sonuc = yerlesim_coz(komponentler, netler, 30.0, 30.0)
        skor = yerlesim_skoru(sonuc, netler, komponentler)
        assert skor.ratsnest_mm == sonuc.son_ratsnest_mm
        assert skor.toplam_skor >= skor.ratsnest_mm  # diğer terimler negatif OLAMAZ

    def test_keepout_ihlali_skoru_agir_cezalandirir(self):
        komponentler = [Komponent("A"), Komponent("B", x=5.0, y=5.0)]
        netler = [Net("SIG", ["A", "B"])]
        koordinatlar = {"A": (0.0, 0.0), "B": (5.0, 5.0)}
        from kuvvet_yonelimli_yerlesim import YerlesimSonucu
        sonuc = YerlesimSonucu(koordinatlar, 1, True, 0.0, 10.0, 10.0)

        keepout_yok = yerlesim_skoru(sonuc, netler, komponentler, keepoutlar=[])
        keepout_var = yerlesim_skoru(
            sonuc, netler, komponentler,
            keepoutlar=[YuksekHizKeepout("HS", 2.5, 2.5, 10.0)],  # her ikisini de kapsar
        )
        assert keepout_var.keepout_ihlal_sayisi == 2
        assert keepout_var.toplam_skor > keepout_yok.toplam_skor

    def test_termal_kisit_ihlali_skoru_yukseltir(self):
        from kuvvet_yonelimli_yerlesim import YerlesimSonucu
        sonuc = YerlesimSonucu({"U1": (0.0, 0.0), "_CAPA": (10.0, 0.0)}, 1, True, 0.0, 5.0, 5.0)
        kisit_gevsek = [MesafeKisiti("U1", "_CAPA", maks_mm=20.0)]
        kisit_siki = [MesafeKisiti("U1", "_CAPA", maks_mm=5.0)]

        skor_gevsek = yerlesim_skoru(sonuc, [], [], termal_kisitlar=kisit_gevsek)
        skor_siki = yerlesim_skoru(sonuc, [], [], termal_kisitlar=kisit_siki)
        assert skor_siki.termal_yayilim_skoru > skor_gevsek.termal_yayilim_skoru

    def test_hs_net_kompakt_degilse_skor_yukselir(self):
        from kuvvet_yonelimli_yerlesim import YerlesimSonucu
        netler = [Net("MIPI_D0_P", ["U0", "U1"])]
        yakin = YerlesimSonucu({"U0": (0.0, 0.0), "U1": (1.0, 0.0)}, 1, True, 0.0, 1.0, 1.0)
        uzak = YerlesimSonucu({"U0": (0.0, 0.0), "U1": (30.0, 0.0)}, 1, True, 0.0, 30.0, 30.0)

        skor_yakin = yerlesim_skoru(yakin, netler, [])
        skor_uzak = yerlesim_skoru(uzak, netler, [])
        assert skor_uzak.hs_kompaktlik_skoru > skor_yakin.hs_kompaktlik_skoru


class TestCokluYerlesimDene:
    def test_determinizm_ayni_netlist_ayni_sonuc(self):
        komponentler = [Komponent(f"U{i}") for i in range(8)]
        netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3", "U4"])]

        s1 = coklu_yerlesim_dene(komponentler, netler, 40.0, 40.0)
        s2 = coklu_yerlesim_dene([Komponent(f"U{i}") for i in range(8)], netler, 40.0, 40.0)

        assert s1.en_iyi_isim == s2.en_iyi_isim
        assert s1.tum_sonuclar[s1.en_iyi_isim].koordinatlar == s2.tum_sonuclar[s2.en_iyi_isim].koordinatlar

    def test_tum_parametre_setleri_icin_sonuc_ve_skor_doner(self):
        komponentler = [Komponent(f"U{i}") for i in range(6)]
        netler = [Net("A", ["U0", "U1"])]
        sonuc = coklu_yerlesim_dene(komponentler, netler, 40.0, 40.0)
        assert set(sonuc.tum_sonuclar) == {p.isim for p in VARSAYILAN_PARAMETRE_SETLERI}
        assert set(sonuc.tum_skorlar) == {p.isim for p in VARSAYILAN_PARAMETRE_SETLERI}

    def test_en_iyi_isim_gercekten_en_dusuk_skora_sahip(self):
        komponentler = [Komponent(f"U{i}") for i in range(6)]
        netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3"])]
        sonuc = coklu_yerlesim_dene(komponentler, netler, 40.0, 40.0)
        en_dusuk = min(s.toplam_skor for s in sonuc.tum_skorlar.values())
        assert sonuc.tum_skorlar[sonuc.en_iyi_isim].toplam_skor == en_dusuk

    def test_ozel_parametre_seti_verilebilir(self):
        komponentler = [Komponent(f"U{i}") for i in range(4)]
        netler = [Net("A", ["U0", "U1"])]
        ozel = [YerlesimParametreSeti("tek_deneme", cekim_katsayisi=0.1)]
        sonuc = coklu_yerlesim_dene(komponentler, netler, 30.0, 30.0, parametre_setleri=ozel)
        assert sonuc.en_iyi_isim == "tek_deneme"
        assert list(sonuc.tum_sonuclar) == ["tek_deneme"]

    def test_bos_parametre_listesi_reddedilir(self):
        komponentler = [Komponent("U0")]
        with pytest.raises(ValueError):
            coklu_yerlesim_dene(komponentler, [], 30.0, 30.0, parametre_setleri=[])
