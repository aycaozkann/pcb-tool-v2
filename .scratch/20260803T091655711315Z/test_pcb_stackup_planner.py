"""
pcb_stackup_planner.py için test suite.
Çalıştırmak için:  pytest -v test_pcb_stackup_planner.py
"""

import pytest

from pcb_stackup_planner import (
    Net,
    Komponent,
    MekanikVeTermalKisitlar,
    SinyalTuru,
    KilifTuru,
    ViaTipi,
    sinyalleri_grupla,
    katman_sayisini_hesapla,
    dizilimi_olustur,
    capraz_dogrulama_yap,
    fiziksel_dogrulama_yap,
    bakir_dengesi_kontrolu,
    stackup_planla,
    iz_genisligi_hesapla_mm,
    guc_hatlari_icin_iz_genisligi_kontrolu,
    FabrikaProfili,
    FABRIKA_PROFILLERI,
    fabrika_dfm_kontrolu,
    dekuplaj_kontrolu,
    AraBirimTuru,
    DiferansiyelCift,
    ViaKullanimi,
    empedans_hedefi_getir,
    length_matching_kontrolu,
    via_stub_analizi,
    FrekansBandi,
    AntenYerlesimi,
    KristalYerlesimi,
    RFHattiStitching,
    anten_keepout_kontrolu,
    kristal_yerlesim_kontrolu,
    rf_stitching_araligi_hesapla_mm,
    rf_stitching_kontrolu,
    YalitimGereksinimi,
    YuksekAkimIzi,
    TermalYonetim,
    gerekli_izolasyon_mesafesi_mm,
    izolasyon_kontrolu,
    gerekli_bakir_agirligi_oz,
    guc_elektronigi_bakir_kontrolu,
    termal_via_sayisi_hesapla,
    termal_yonetim_kontrolu,
)


# ------------------------------------------------------------------
# sinyalleri_grupla
# ------------------------------------------------------------------

def test_sinyalleri_grupla_temel_dagilim():
    sinyaller = [
        Net("3V3", SinyalTuru.GUC),
        Net("GND", SinyalTuru.GND),
        Net("CLK", SinyalTuru.HIZLI_DIJITAL),
        Net("WIFI_ANT", SinyalTuru.RF),
        Net("ADC_IN", SinyalTuru.ANALOG),
        Net("LED", SinyalTuru.YAVAS_DIJITAL),
    ]
    hafiza = sinyalleri_grupla(sinyaller)

    assert len(hafiza["Guc_Alanlari"]) == 1
    assert len(hafiza["GND_Alanlari"]) == 1
    assert len(hafiza["Analog_Sinyaller"]) == 1
    assert len(hafiza["Standart_IO"]) == 1
    # RF hem kendi grubunda hem kritik sinyallerde sayılmalı
    assert len(hafiza["RF_Sinyaller"]) == 1
    assert len(hafiza["Kritik_Sinyaller"]) == 2  # CLK + WIFI_ANT


def test_sinyalleri_grupla_bos_liste():
    hafiza = sinyalleri_grupla([])
    for grup in hafiza.values():
        assert grup == []


# ------------------------------------------------------------------
# katman_sayisini_hesapla
# ------------------------------------------------------------------

def test_minimum_iki_katman_basit_kart():
    sinyaller = [Net("3V3", SinyalTuru.GUC), Net("GND", SinyalTuru.GND),
                 Net("LED", SinyalTuru.YAVAS_DIJITAL)]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, []) == 2


def test_hizli_sinyal_dort_katman_ister():
    sinyaller = [Net("GND", SinyalTuru.GND), Net("CLK", SinyalTuru.HIZLI_DIJITAL)]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, []) == 4


def test_fine_pitch_bga_sekiz_katman_ister():
    sinyaller = [Net("GND", SinyalTuru.GND)]
    komponentler = [Komponent("U1", KilifTuru.FINE_PITCH_BGA, pin_sayisi=200)]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, komponentler) == 8


def test_coklu_fine_pitch_bga_on_katman_ister():
    sinyaller = [Net("GND", SinyalTuru.GND)]
    komponentler = [
        Komponent("U1", KilifTuru.FINE_PITCH_BGA, pin_sayisi=300),
        Komponent("U2", KilifTuru.FINE_PITCH_BGA, pin_sayisi=300),
    ]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, komponentler) == 10


def test_yuksek_pin_sayili_tek_bga_on_katman_ister():
    sinyaller = [Net("GND", SinyalTuru.GND)]
    komponentler = [Komponent("U1", KilifTuru.FINE_PITCH_BGA, pin_sayisi=800)]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, komponentler) == 10


def test_rf_sinyali_en_az_alti_katman_ister():
    sinyaller = [Net("GND", SinyalTuru.GND), Net("ANT", SinyalTuru.RF)]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, []) >= 6


def test_yuksek_akimli_guc_hatti_alti_katman_ister():
    sinyaller = [
        Net("GND", SinyalTuru.GND),
        Net("12V_MOTOR", SinyalTuru.GUC, maks_akim=5.0),
        Net("3V3", SinyalTuru.GUC, maks_akim=0.5),
    ]
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, []) >= 6


def test_coklu_voltaj_ve_cok_kritik_sinyal_alti_katman_ister():
    sinyaller = (
        [Net(f"CLK{i}", SinyalTuru.HIZLI_DIJITAL) for i in range(12)]
        + [Net("3V3", SinyalTuru.GUC), Net("5V0", SinyalTuru.GUC), Net("1V8", SinyalTuru.GUC)]
    )
    hafiza = sinyalleri_grupla(sinyaller)
    assert katman_sayisini_hesapla(hafiza, []) >= 6


# ------------------------------------------------------------------
# dizilimi_olustur
# ------------------------------------------------------------------

@pytest.mark.parametrize("katman_sayisi", [2, 4, 6, 8, 10])
def test_dizilim_dogru_sayida_katman_uretir(katman_sayisi):
    hafiza = sinyalleri_grupla([Net("GND", SinyalTuru.GND)])
    stackup = dizilimi_olustur(katman_sayisi, hafiza)
    assert len(stackup) == katman_sayisi
    for i in range(1, katman_sayisi + 1):
        assert f"Katman_{i}" in stackup


def test_dort_katman_l2_gnd_olmali():
    hafiza = sinyalleri_grupla([Net("CLK", SinyalTuru.HIZLI_DIJITAL), Net("GND", SinyalTuru.GND)])
    stackup = dizilimi_olustur(4, hafiza)
    assert "GND" in stackup["Katman_2"]


# ------------------------------------------------------------------
# capraz_dogrulama_yap (elektriksel DRC)
# ------------------------------------------------------------------

def test_l2_gnd_degilse_hata_verir():
    hafiza = sinyalleri_grupla([Net("CLK", SinyalTuru.HIZLI_DIJITAL), Net("GND", SinyalTuru.GND)])
    kirli_stackup = {"Katman_1": "SİNYAL", "Katman_2": "SİNYAL", "Katman_3": "GÜÇ", "Katman_4": "SİNYAL"}
    hatalar, _ = capraz_dogrulama_yap(kirli_stackup, hafiza, 4)
    assert any("dönüş yolu" in h for h in hatalar)


def test_gecerli_dizilimde_hata_olmamali():
    hafiza = sinyalleri_grupla([Net("CLK", SinyalTuru.HIZLI_DIJITAL), Net("GND", SinyalTuru.GND)])
    stackup = dizilimi_olustur(4, hafiza)
    hatalar, _ = capraz_dogrulama_yap(stackup, hafiza, 4)
    assert hatalar == []


def test_yan_yana_sinyal_katmani_uyari_verir():
    hafiza = sinyalleri_grupla([Net("GND", SinyalTuru.GND)])
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "SİNYAL", "Katman_3": "GND"}
    _, uyarilar = capraz_dogrulama_yap(stackup, hafiza, 3)
    assert any("DİK" in u for u in uyarilar)


def test_rf_sinyali_yetersiz_katmanda_hata_verir():
    hafiza = sinyalleri_grupla([Net("ANT", SinyalTuru.RF), Net("GND", SinyalTuru.GND)])
    stackup = dizilimi_olustur(4, hafiza)
    hatalar, _ = capraz_dogrulama_yap(stackup, hafiza, 4)
    assert any("RF" in h for h in hatalar)


def test_dort_voltaj_tek_guc_katmaninda_hata_verir():
    hafiza = sinyalleri_grupla([
        Net("3V3", SinyalTuru.GUC), Net("5V0", SinyalTuru.GUC),
        Net("1V8", SinyalTuru.GUC), Net("12V", SinyalTuru.GUC),
    ])
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND", "Katman_3": "GÜÇ", "Katman_4": "SİNYAL"}
    hatalar, _ = capraz_dogrulama_yap(stackup, hafiza, 4)
    assert any("bölünemez" in h for h in hatalar)


# ------------------------------------------------------------------
# fiziksel_dogrulama_yap (DFM)
# ------------------------------------------------------------------

def test_cok_ince_kart_cok_katmanla_hata_verir():
    kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=0.8)
    stackup = {f"Katman_{i}": "GND" for i in range(1, 9)}
    hatalar = fiziksel_dogrulama_yap(stackup, kisitlar, [], 8)
    assert any("MEKANİK HATA" in h for h in hatalar)


def test_yeterli_kalinlikta_mekanik_hata_olmamali():
    kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=2.0)
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND", "Katman_3": "GÜÇ", "Katman_4": "SİNYAL"}
    hatalar = fiziksel_dogrulama_yap(stackup, kisitlar, [], 4)
    assert not any("MEKANİK HATA" in h for h in hatalar)


def test_asimetrik_bakir_dagilimi_hata_verir():
    kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=3.0, bakir_denge_toleransi=5.0)
    # Üst yarı tamamen SİNYAL (yoğun), alt yarı tamamen GND (daha az yoğun) -> asimetrik
    stackup = {
        "Katman_1": "SİNYAL", "Katman_2": "SİNYAL",
        "Katman_3": "GND", "Katman_4": "GND",
    }
    hatalar = fiziksel_dogrulama_yap(stackup, kisitlar, [], 4)
    assert any("bükülecektir" in h for h in hatalar)


def test_boydan_boya_via_yuksek_aspect_ratio_hata_verir():
    kisitlar = MekanikVeTermalKisitlar(
        hedef_kalinlik_mm=3.0,  # 3.0 / 0.2 = 15:1, sınırı (8:1) aşar
        kabul_edilen_via_tipi=ViaTipi.SADECE_BOYDAN_BOYA,
    )
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND"}
    hatalar = fiziksel_dogrulama_yap(stackup, kisitlar, [], 2)
    assert any("delme oranı" in h for h in hatalar)


def test_kor_gomulu_via_izinliyken_aspect_ratio_kontrolu_atlanir():
    kisitlar = MekanikVeTermalKisitlar(
        hedef_kalinlik_mm=3.0,
        kabul_edilen_via_tipi=ViaTipi.KOR_VE_GOMULU_IZINLI,
    )
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND"}
    hatalar = fiziksel_dogrulama_yap(stackup, kisitlar, [], 2)
    assert not any("delme oranı" in h for h in hatalar)


# ------------------------------------------------------------------
# bakir_dengesi_kontrolu
# ------------------------------------------------------------------

def test_simetrik_dizilim_sifira_yakin_fark_verir():
    stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND", "Katman_3": "GND", "Katman_4": "SİNYAL"}
    fark = bakir_dengesi_kontrolu(stackup, 4)
    assert fark == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------
# stackup_planla (uçtan uca entegrasyon)
# ------------------------------------------------------------------

def test_uctan_uca_basit_kart_gecerli_sonuc_dondurur():
    # Not: 2 katmanlı dizilimde bir yüz "SİNYAL+GÜÇ" karışık, diğeri sade "GND"
    # olduğu için bakır dengesi kontrolü asimetri buluyor ve algoritma 4 katmana
    # çıkıyor. Bu, gerçek DFM mantığına uygun beklenen bir davranıştır.
    sinyaller = [Net("3V3", SinyalTuru.GUC), Net("GND", SinyalTuru.GND),
                 Net("LED", SinyalTuru.YAVAS_DIJITAL)]
    kisitlar = MekanikVeTermalKisitlar()
    sonuc = stackup_planla(sinyaller, [], kisitlar)
    assert len(sonuc) == 4


def test_uctan_uca_fine_pitch_bga_sekiz_katmana_ulasir():
    sinyaller = [Net("GND", SinyalTuru.GND), Net("CLK", SinyalTuru.HIZLI_DIJITAL)]
    komponentler = [Komponent("U1", KilifTuru.FINE_PITCH_BGA, pin_sayisi=300)]
    kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=1.6)
    sonuc = stackup_planla(sinyaller, komponentler, kisitlar)
    assert len(sonuc) == 8


def test_uctan_uca_cok_ince_kart_daha_fazla_katmana_ihtiyac_gostermeli():
    # 8 katman ister ama 0.8mm'ye sığmaz (min ~1.2mm) -> algoritma daha ince bir
    # dizilime düşemeyeceği için bu senaryoda RuntimeError bekleriz (kısıtlar çelişkili).
    sinyaller = [Net("GND", SinyalTuru.GND)]
    komponentler = [Komponent("U1", KilifTuru.FINE_PITCH_BGA, pin_sayisi=200)]
    kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=0.8)
    with pytest.raises(RuntimeError):
        stackup_planla(sinyaller, komponentler, kisitlar, maks_deneme=3)


# ------------------------------------------------------------------
# FAZ 1: iz_genisligi_hesapla_mm (IPC-2221)
# ------------------------------------------------------------------

def test_daha_yuksek_akim_daha_genis_iz_ister():
    dar = iz_genisligi_hesapla_mm(akim_A=1.0)
    genis = iz_genisligi_hesapla_mm(akim_A=5.0)
    assert genis > dar


def test_ic_katman_disa_gore_daha_genis_iz_ister():
    # Aynı akım için iç katman, dış katmana göre daha geniş iz gerektirir
    # (ısıyı atması daha zor olduğu için k katsayısı daha düşüktür).
    dis = iz_genisligi_hesapla_mm(akim_A=2.0, dis_katman_mi=True)
    ic = iz_genisligi_hesapla_mm(akim_A=2.0, dis_katman_mi=False)
    assert ic > dis


def test_daha_kalin_bakir_daha_dar_iz_yeterli_olur():
    ince_bakir = iz_genisligi_hesapla_mm(akim_A=3.0, bakir_agirligi_oz=1.0)
    kalin_bakir = iz_genisligi_hesapla_mm(akim_A=3.0, bakir_agirligi_oz=2.0)
    assert kalin_bakir < ince_bakir


def test_sifir_akim_sifir_genislik_dondurur():
    assert iz_genisligi_hesapla_mm(akim_A=0.0) == 0.0


def test_guc_hatlari_icin_iz_genisligi_kontrolu_sadece_akimi_olan_netleri_kapsar():
    sinyaller = [
        Net("3V3", SinyalTuru.GUC, maks_akim=1.5),
        Net("VBAT", SinyalTuru.GUC, maks_akim=0.0),  # akım belirtilmemiş, atlanmalı
        Net("GND", SinyalTuru.GND),
    ]
    hafiza = sinyalleri_grupla(sinyaller)
    oneriler = guc_hatlari_icin_iz_genisligi_kontrolu(hafiza)
    assert "3V3" in oneriler
    assert "VBAT" not in oneriler
    assert oneriler["3V3"] > 0


# ------------------------------------------------------------------
# FAZ 1: fabrika_dfm_kontrolu
# ------------------------------------------------------------------

def test_uygun_tasarim_degerleri_hata_vermez():
    profil = FABRIKA_PROFILLERI["JLCPCB_GELISMIS"]
    hatalar = fabrika_dfm_kontrolu(
        tasarim_iz_genisligi_mm=0.15,
        tasarim_iz_araligi_mm=0.15,
        tasarim_delik_capi_mm=0.25,
        profil=profil,
    )
    assert hatalar == []


def test_dar_iz_genisligi_dfm_hatasi_verir():
    profil = FABRIKA_PROFILLERI["JLCPCB_STANDART"]
    hatalar = fabrika_dfm_kontrolu(
        tasarim_iz_genisligi_mm=0.05,
        tasarim_iz_araligi_mm=0.2,
        tasarim_delik_capi_mm=0.4,
        profil=profil,
    )
    assert any("İz genişliği" in h for h in hatalar)


def test_kucuk_delik_capi_dfm_hatasi_verir():
    profil = FABRIKA_PROFILLERI["PCBWAY_STANDART"]
    hatalar = fabrika_dfm_kontrolu(
        tasarim_iz_genisligi_mm=0.2,
        tasarim_iz_araligi_mm=0.2,
        tasarim_delik_capi_mm=0.1,
        profil=profil,
    )
    assert any("Delik çapı" in h for h in hatalar)


def test_farkli_fabrika_profilleri_farkli_limitler_verir():
    standart = FABRIKA_PROFILLERI["JLCPCB_STANDART"]
    gelismis = FABRIKA_PROFILLERI["JLCPCB_GELISMIS"]
    assert gelismis.min_iz_genisligi_mm < standart.min_iz_genisligi_mm


# ------------------------------------------------------------------
# FAZ 1: dekuplaj_kontrolu
# ------------------------------------------------------------------

def test_yetersiz_decoupling_hata_verir():
    komponentler = [
        Komponent("U1", KilifTuru.QFN, pin_sayisi=32, guc_pini_sayisi=4,
                  dekuplaj_kapasitor_sayisi=1),
    ]
    hatalar = dekuplaj_kontrolu(komponentler)
    assert any("DEKUPLAJ HATASI" in h for h in hatalar)


def test_yeterli_decoupling_ve_dusuk_pin_sayisinda_hata_olmamali():
    komponentler = [
        Komponent("U1", KilifTuru.QFN, pin_sayisi=32, guc_pini_sayisi=2,
                  dekuplaj_kapasitor_sayisi=2),
    ]
    hatalar = dekuplaj_kontrolu(komponentler)
    assert hatalar == []


def test_yuksek_pinli_komponent_bulk_kapasitor_uyarisi_verir():
    komponentler = [
        Komponent("U1_SoC", KilifTuru.FINE_PITCH_BGA, pin_sayisi=400,
                  guc_pini_sayisi=8, dekuplaj_kapasitor_sayisi=8),  # decoupling yeterli
    ]
    hatalar = dekuplaj_kontrolu(komponentler)
    # decoupling yeterli olsa da yüksek pinli komponent için bulk kapasitör uyarısı beklenir
    assert any("BULK KAPASİTÖR" in h for h in hatalar)


def test_guc_pini_sifir_ise_dekuplaj_hatasi_verilmez():
    komponentler = [Komponent("R1", KilifTuru.STANDART, pin_sayisi=2)]
    hatalar = dekuplaj_kontrolu(komponentler)
    assert hatalar == []


# ------------------------------------------------------------------
# FAZ 2: empedans_hedefi_getir
# ------------------------------------------------------------------

def test_usb3_empedans_hedefi_dogru():
    cift = DiferansiyelCift("USB", AraBirimTuru.USB3_x, 40.0, 40.0, veri_hizi_Gbps=5.0)
    assert empedans_hedefi_getir(cift) == 90.0


def test_hdmi_empedans_hedefi_dogru():
    cift = DiferansiyelCift("HDMI", AraBirimTuru.HDMI, 40.0, 40.0)
    assert empedans_hedefi_getir(cift) == 100.0


def test_override_verilirse_kullanilir():
    cift = DiferansiyelCift(
        "OZEL", AraBirimTuru.USB3_x, 40.0, 40.0, hedef_empedans_ohm_override=95.0
    )
    assert empedans_hedefi_getir(cift) == 95.0


# ------------------------------------------------------------------
# FAZ 2: length_matching_kontrolu
# ------------------------------------------------------------------

def test_tolerans_icindeki_uzunluk_farki_hata_vermez():
    cift = DiferansiyelCift("USB", AraBirimTuru.USB3_x, 40.0, 40.1, veri_hizi_Gbps=5.0)
    assert length_matching_kontrolu(cift) == []


def test_tolerans_disindaki_uzunluk_farki_hata_verir():
    # USB3 toleransı 0.5mm; burada 0.8mm fark var
    cift = DiferansiyelCift("USB", AraBirimTuru.USB3_x, 42.0, 41.2, veri_hizi_Gbps=5.0)
    hatalar = length_matching_kontrolu(cift)
    assert any("LENGTH MATCHING HATASI" in h for h in hatalar)


def test_pcie_dar_toleransta_kucuk_fark_bile_hata_verir():
    # PCIe toleransı 0.13mm gibi çok sıkı; 0.2mm fark hata vermeli
    cift = DiferansiyelCift("PCIE", AraBirimTuru.PCIE, 30.0, 30.2, veri_hizi_Gbps=16.0)
    hatalar = length_matching_kontrolu(cift)
    assert any("LENGTH MATCHING HATASI" in h for h in hatalar)


# ------------------------------------------------------------------
# FAZ 2: via_stub_analizi
# ------------------------------------------------------------------

def test_boydan_boya_via_yuksek_hizda_derin_stub_uyari_verir():
    via = ViaKullanimi("PCIE_TX0", baslangic_katman=1, bitis_katman=3, veri_hizi_Gbps=16.0)
    uyarilar = via_stub_analizi(via, toplam_katman=8, via_tipi=ViaTipi.SADECE_BOYDAN_BOYA)
    assert any("VIA STUB UYARISI" in u for u in uyarilar)


def test_kor_gomulu_via_stub_uyarisi_vermez():
    via = ViaKullanimi("PCIE_TX0", baslangic_katman=1, bitis_katman=3, veri_hizi_Gbps=16.0)
    uyarilar = via_stub_analizi(via, toplam_katman=8, via_tipi=ViaTipi.KOR_VE_GOMULU_IZINLI)
    assert uyarilar == []


def test_dusuk_hizda_stub_uyarisi_verilmez():
    via = ViaKullanimi("I2C_SDA", baslangic_katman=1, bitis_katman=3, veri_hizi_Gbps=0.4)
    uyarilar = via_stub_analizi(via, toplam_katman=8, via_tipi=ViaTipi.SADECE_BOYDAN_BOYA)
    assert uyarilar == []


def test_stub_kisa_ise_yuksek_hizda_bile_uyari_verilmez():
    # Sinyal katman 7'de bitiyor, toplam 8 katman -> stub sadece 1 katman (~0.15mm), eşik altı
    via = ViaKullanimi("PCIE_TX0", baslangic_katman=1, bitis_katman=7, veri_hizi_Gbps=16.0)
    uyarilar = via_stub_analizi(via, toplam_katman=8, via_tipi=ViaTipi.SADECE_BOYDAN_BOYA)
    assert uyarilar == []


# ------------------------------------------------------------------
# FAZ 3: anten_keepout_kontrolu
# ------------------------------------------------------------------

def test_yetersiz_bakir_mesafesi_hata_verir():
    anten = AntenYerlesimi(
        "WIFI_ANT", FrekansBandi.WIFI_BLE_2_4GHZ,
        kenara_mesafe_mm=3.0, en_yakin_bakir_mesafe_mm=2.0,  # 5mm gerekir
    )
    hatalar = anten_keepout_kontrolu(anten)
    assert any("bakır/GND dökümüne" in h for h in hatalar)


def test_yetersiz_kenar_mesafesi_hata_verir():
    anten = AntenYerlesimi(
        "WIFI_ANT", FrekansBandi.WIFI_BLE_2_4GHZ,
        kenara_mesafe_mm=1.0, en_yakin_bakir_mesafe_mm=6.0,  # kenar mesafesi 3mm gerekir
    )
    hatalar = anten_keepout_kontrolu(anten)
    assert any("Kart kenarına" in h for h in hatalar)


def test_yeterli_keepout_hata_vermez():
    anten = AntenYerlesimi(
        "WIFI_ANT", FrekansBandi.WIFI_BLE_2_4GHZ,
        kenara_mesafe_mm=4.0, en_yakin_bakir_mesafe_mm=6.0,
    )
    assert anten_keepout_kontrolu(anten) == []


def test_subghz_anten_daha_genis_keepout_ister():
    # Aynı bakır mesafesi 2.4GHz için yeterli olabilir ama sub-GHz için olmayabilir
    anten_24 = AntenYerlesimi("A1", FrekansBandi.WIFI_BLE_2_4GHZ, 4.0, 6.0)
    anten_subghz = AntenYerlesimi("A2", FrekansBandi.SUBGHZ_433, 4.0, 6.0)
    assert anten_keepout_kontrolu(anten_24) == []
    assert anten_keepout_kontrolu(anten_subghz) != []


# ------------------------------------------------------------------
# FAZ 3: kristal_yerlesim_kontrolu
# ------------------------------------------------------------------

def test_ic_pinine_uzak_kristal_hata_verir():
    kristal = KristalYerlesimi("XTAL1", ic_pinine_mesafe_mm=12.0,
                                gurultu_kaynagina_mesafe_mm=10.0)
    hatalar = kristal_yerlesim_kontrolu(kristal)
    assert any("XTAL pinlerine" in h for h in hatalar)


def test_gurultuye_yakin_ve_guard_ring_yoksa_hata_verir():
    kristal = KristalYerlesimi("XTAL1", ic_pinine_mesafe_mm=5.0,
                                gurultu_kaynagina_mesafe_mm=2.0, guard_ring_var_mi=False)
    hatalar = kristal_yerlesim_kontrolu(kristal)
    assert any("guard ring" in h for h in hatalar)


def test_gurultuye_yakin_ama_guard_ring_varsa_hata_vermez():
    kristal = KristalYerlesimi("XTAL1", ic_pinine_mesafe_mm=5.0,
                                gurultu_kaynagina_mesafe_mm=2.0, guard_ring_var_mi=True)
    assert kristal_yerlesim_kontrolu(kristal) == []


def test_iyi_yerlestirilmis_kristal_hata_vermez():
    kristal = KristalYerlesimi("XTAL1", ic_pinine_mesafe_mm=4.0,
                                gurultu_kaynagina_mesafe_mm=8.0)
    assert kristal_yerlesim_kontrolu(kristal) == []


# ------------------------------------------------------------------
# FAZ 3: rf_stitching_araligi_hesapla_mm / rf_stitching_kontrolu
# ------------------------------------------------------------------

def test_yuksek_frekans_daha_dar_stitching_araligi_ister():
    aralik_2_4ghz = rf_stitching_araligi_hesapla_mm(2.4)
    aralik_5ghz = rf_stitching_araligi_hesapla_mm(5.0)
    assert aralik_5ghz < aralik_2_4ghz


def test_sifir_frekans_sonsuz_aralik_dondurur():
    assert rf_stitching_araligi_hesapla_mm(0.0) == float("inf")


def test_genis_stitching_araligi_hata_verir():
    hat = RFHattiStitching("WIFI_RF", frekans_GHz=2.4, stitching_via_araligi_mm=100.0)
    hatalar = rf_stitching_kontrolu(hat)
    assert any("RF STITCHING HATASI" in h for h in hatalar)


def test_dar_stitching_araligi_hata_vermez():
    hat = RFHattiStitching("WIFI_RF", frekans_GHz=2.4, stitching_via_araligi_mm=1.0)
    assert rf_stitching_kontrolu(hat) == []


# ------------------------------------------------------------------
# FAZ 4: gerekli_izolasyon_mesafesi_mm / izolasyon_kontrolu
# ------------------------------------------------------------------

def test_yuksek_voltaj_daha_genis_mesafe_ister():
    assert gerekli_izolasyon_mesafesi_mm(500) > gerekli_izolasyon_mesafesi_mm(50)


def test_dusuk_voltaj_dar_mesafe_yeterli():
    assert gerekli_izolasyon_mesafesi_mm(10) == 0.05


def test_yetersiz_yalitim_mesafesi_hata_verir():
    gereksinim = YalitimGereksinimi("AC-GND", gerilim_farki_V=230.0, tasarim_mesafesi_mm=0.2)
    hatalar = izolasyon_kontrolu(gereksinim)
    assert any("YALITIM HATASI" in h for h in hatalar)


def test_yeterli_yalitim_mesafesi_hata_vermez():
    gereksinim = YalitimGereksinimi("AC-GND", gerilim_farki_V=230.0, tasarim_mesafesi_mm=1.0)
    assert izolasyon_kontrolu(gereksinim) == []


def test_cok_yuksek_voltajda_tablo_disi_olcekleme_calisir():
    # Tablodaki en yüksek satır 1000V/1.5mm; 2000V için orantısal ölçekleme beklenir
    mesafe = gerekli_izolasyon_mesafesi_mm(2000)
    assert mesafe == pytest.approx(3.0, rel=0.01)


# ------------------------------------------------------------------
# FAZ 4: gerekli_bakir_agirligi_oz / guc_elektronigi_bakir_kontrolu
# ------------------------------------------------------------------

def test_daha_yuksek_akim_daha_kalin_bakir_ister():
    dar_akim = gerekli_bakir_agirligi_oz(akim_A=2.0, mevcut_genislik_mm=2.0)
    genis_akim = gerekli_bakir_agirligi_oz(akim_A=20.0, mevcut_genislik_mm=2.0)
    assert genis_akim > dar_akim


def test_gerekli_bakir_sifir_akimda_sifir():
    assert gerekli_bakir_agirligi_oz(akim_A=0.0, mevcut_genislik_mm=2.0) == 0.0


def test_yuksek_akim_dar_izde_ekonomik_siniri_asar():
    iz = YuksekAkimIzi(isim="MOTOR_12V", akim_A=15.0, mevcut_genislik_mm=2.0)
    hatalar = guc_elektronigi_bakir_kontrolu(iz)
    assert any("GÜÇ ELEKTRONİĞİ HATASI" in h for h in hatalar)


def test_dusuk_akim_genis_izde_ekonomik_sinir_asilmaz():
    iz = YuksekAkimIzi(isim="LED_LINE", akim_A=0.5, mevcut_genislik_mm=2.0)
    assert guc_elektronigi_bakir_kontrolu(iz) == []


# ------------------------------------------------------------------
# FAZ 4: termal_via_sayisi_hesapla / termal_yonetim_kontrolu
# ------------------------------------------------------------------

def test_termal_via_sayisi_gucle_orantili_artar():
    assert termal_via_sayisi_hesapla(3.0) > termal_via_sayisi_hesapla(1.0)


def test_sifir_guc_sifir_via_gerektirir():
    assert termal_via_sayisi_hesapla(0.0) == 0


def test_yetersiz_termal_via_hata_verir():
    termal = TermalYonetim(isim="U3_MOSFET", guc_yayilimi_W=4.0, mevcut_termal_via_sayisi=5)
    hatalar = termal_yonetim_kontrolu(termal)
    assert any("TERMAL YÖNETİM HATASI" in h for h in hatalar)


def test_yeterli_termal_via_hata_vermez():
    termal = TermalYonetim(isim="U3_MOSFET", guc_yayilimi_W=1.0, mevcut_termal_via_sayisi=10)
    assert termal_yonetim_kontrolu(termal) == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))


# ------------------------------------------------------------------
# empedans_geometrisi_coz — empedans_cozucu.py entegrasyonu
# ------------------------------------------------------------------

from pcb_stackup_planner import empedans_geometrisi_coz, DiferansiyelCift, AraBirimTuru


def test_empedans_geometrisi_coz_ulasilabilir_hedefte_sonuc_dondurur():
    cift = DiferansiyelCift(
        isim="USB_D+/D-", arayuz=AraBirimTuru.USB2_0,
        uzunluk_pozitif_mm=10.0, uzunluk_negatif_mm=10.0,
    )
    sonuc = empedans_geometrisi_coz(cift, h_mm=0.2, er=4.3, fab_min_w_mm=0.09, fab_min_s_mm=0.09)
    assert sonuc["hedef_ohm"] == 90.0  # USB2_0 hedefi
    assert sonuc["ulasilabilir_mi"] is True
    assert sonuc["en_iyi"]["hata_yuzde"] < 5.0  # makul bir yakınlık


def test_empedans_geometrisi_coz_ulasilamaz_hedefte_none_dondurur():
    cift = DiferansiyelCift(
        isim="ASIRI_DAR", arayuz=AraBirimTuru.USB2_0,
        uzunluk_pozitif_mm=10.0, uzunluk_negatif_mm=10.0,
        # h=0.1mm'de fab-sınırlı (w,s) grid'inin ulaşabildiği tavan ~106 ohm
        # (bkz. z0_mikroserit(min_w, maks_s)) -> 1000 ohm kesin ULASILAMAZ.
        hedef_empedans_ohm_override=1000.0,
    )
    sonuc = empedans_geometrisi_coz(cift, h_mm=0.1, er=4.5, fab_min_w_mm=0.127, fab_min_s_mm=0.127)
    assert sonuc["ulasilabilir_mi"] is False
    assert sonuc["en_iyi"] is None


def test_empedans_geometrisi_coz_override_hedefi_kullanir():
    cift = DiferansiyelCift(
        isim="OZEL", arayuz=AraBirimTuru.USB2_0,
        uzunluk_pozitif_mm=5.0, uzunluk_negatif_mm=5.0,
        hedef_empedans_ohm_override=100.0,
    )
    sonuc = empedans_geometrisi_coz(cift, h_mm=0.3, er=4.3, fab_min_w_mm=0.09, fab_min_s_mm=0.09)
    assert sonuc["hedef_ohm"] == 100.0
