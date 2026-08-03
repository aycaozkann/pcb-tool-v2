"""
ecad_mcad_termal_kopru.py için test suite.
Çalıştırmak için:  pytest -v test_ecad_mcad_termal_kopru.py
"""

import pytest

from pcb_stackup_planner import TermalYonetim

from ecad_mcad_termal_kopru import (
    TermalTemasBolgesi,
    soguturucu_yuzey_bul,
    KomponentTermalDurumu,
    termal_yonetim_ve_mask_kontrolu,
    b_mask_poligonu_pcb_ye_yaz,
    termal_ped_kalinligi_hesapla,
    termal_ped_bom_notu_uret,
    TermalKaynakVeHassasParca,
    FrezelemeYarigi,
    MIN_WEB_GENISLIGI_MM,
    termal_bariyer_gerekli_mi,
    edge_cuts_yarigi_oner,
    termal_bariyer_ozetle,
    edge_cuts_yarigi_pcb_ye_yaz,
)


KARE_YUZEY = TermalTemasBolgesi(
    isim="heatsink_boss_1",
    poligon=[(0, 0), (10, 0), (10, 10), (0, 10)],
    z_boslugu_mm=0.3,
)


# ------------------------------------------------------------------
# 1. soguturucu_yuzey_bul
# ------------------------------------------------------------------

def test_soguturucu_yuzey_bul_icerideki_noktayi_bulur():
    sonuc = soguturucu_yuzey_bul(5.0, 5.0, [KARE_YUZEY])
    assert sonuc is KARE_YUZEY


def test_soguturucu_yuzey_bul_disaridaki_nokta_none_doner():
    sonuc = soguturucu_yuzey_bul(50.0, 50.0, [KARE_YUZEY])
    assert sonuc is None


def test_soguturucu_yuzey_bul_bos_liste_sessizce_none_doner():
    # Kasa STEP verisi paylaşılmadıysa hata fırlatmaz.
    assert soguturucu_yuzey_bul(5.0, 5.0, []) is None


# ------------------------------------------------------------------
# 2. termal_yonetim_ve_mask_kontrolu
# ------------------------------------------------------------------

def _yonetim(guc_W: float, via: int = 10) -> TermalYonetim:
    return TermalYonetim(isim="U4", guc_yayilimi_W=guc_W, mevcut_termal_via_sayisi=via)


def test_mask_kontrolu_dusuk_guc_esigin_altinda_atlanir():
    durum = KomponentTermalDurumu(yonetim=_yonetim(0.2), x=5, y=5)
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert bulgular == []


def test_mask_kontrolu_kasa_temasi_yoksa_ek_hata_eklenmez():
    # Yüksek güç ama komponent kasa temas bölgesinin dışında.
    durum = KomponentTermalDurumu(yonetim=_yonetim(1.0), x=50, y=50)
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert not any("B.Mask" in b for b in bulgular)


def test_mask_kontrolu_acikligi_tanimsizsa_hata_doner():
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(1.0), x=5, y=5, b_mask_acikligi_tanimli_mi=False
    )
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert any("B.Mask açıklığı tanımlı değil" in b for b in bulgular)


def test_mask_kontrolu_hasl_kaplama_uyari_doner():
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(1.0),
        x=5,
        y=5,
        b_mask_acikligi_tanimli_mi=True,
        yuzey_kaplamasi="HASL",
    )
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert any("ENIG" in b for b in bulgular)


def test_mask_kontrolu_enig_ve_acik_maskeyle_temiz_gecer():
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(1.0),
        x=5,
        y=5,
        b_mask_acikligi_tanimli_mi=True,
        yuzey_kaplamasi="ENIG",
    )
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert bulgular == []


def test_mask_kontrolu_mevcut_via_kontrolunu_de_tasir():
    # via sayısı yetersizken via hatası da ayrıca gelmeye devam etmeli
    # (mevcut termal_yonetim_kontrolu() bozulmadı/hâlâ çağrılıyor).
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(3.0, via=1), x=5, y=5, b_mask_acikligi_tanimli_mi=True,
        yuzey_kaplamasi="ENIG",
    )
    bulgular = termal_yonetim_ve_mask_kontrolu(durum, [KARE_YUZEY], kritik_guc_esigi_W=0.5)
    assert any("TERMAL YÖNETİM HATASI" in b and "termal via gerekir" in b for b in bulgular)


# ------------------------------------------------------------------
# 3. b_mask_poligonu_pcb_ye_yaz
# ------------------------------------------------------------------

def test_b_mask_poligonu_pcb_ye_yaz_dosyayi_gunceller_ve_yedek_alir(tmp_path):
    hedef = tmp_path / "proje.kicad_pcb"
    hedef.write_text("(kicad_pcb\n\t(version 20240108)\n)\n", encoding="utf-8")

    b_mask_poligonu_pcb_ye_yaz(str(hedef), "U4", [(0, 0), (2, 0), (2, 2), (0, 2)])

    icerik = hedef.read_text(encoding="utf-8")
    assert '(layer "B.Mask")' in icerik
    assert "(fill yes)" in icerik
    assert (tmp_path / "proje.kicad_pcb.bak").exists()


def test_b_mask_poligonu_pcb_ye_yaz_dosya_yoksa_hata_firlatir(tmp_path):
    with pytest.raises(FileNotFoundError):
        b_mask_poligonu_pcb_ye_yaz(str(tmp_path / "yok.kicad_pcb"), "U4", [(0, 0), (1, 0), (1, 1)])


def test_b_mask_poligonu_pcb_ye_yaz_az_nokta_hata_firlatir(tmp_path):
    hedef = tmp_path / "proje.kicad_pcb"
    hedef.write_text("(kicad_pcb\n)\n", encoding="utf-8")
    with pytest.raises(ValueError):
        b_mask_poligonu_pcb_ye_yaz(str(hedef), "U4", [(0, 0), (1, 1)])


# ------------------------------------------------------------------
# 4. termal_ped_kalinligi_hesapla / termal_ped_bom_notu_uret
# ------------------------------------------------------------------

def test_termal_ped_kalinligi_varsayilan_sikisma_orani():
    # 0.3 / (1 - 0.25) = 0.4
    assert termal_ped_kalinligi_hesapla(0.3) == pytest.approx(0.4)


def test_termal_ped_kalinligi_farkli_sikisma_orani():
    # 0.5 / (1 - 0.5) = 1.0
    assert termal_ped_kalinligi_hesapla(0.5, sikisma_orani=0.5) == pytest.approx(1.0)


def test_termal_ped_kalinligi_negatif_boşluk_hata_firlatir():
    with pytest.raises(ValueError):
        termal_ped_kalinligi_hesapla(-0.1)


def test_termal_ped_kalinligi_gecersiz_sikisma_orani_hata_firlatir():
    with pytest.raises(ValueError):
        termal_ped_kalinligi_hesapla(0.3, sikisma_orani=1.0)
    with pytest.raises(ValueError):
        termal_ped_kalinligi_hesapla(0.3, sikisma_orani=0.0)


def test_termal_ped_bom_notu_uret_format():
    assert termal_ped_bom_notu_uret("U4", 0.4) == "Thermal Pad — 0.4mm (U4)"


# ------------------------------------------------------------------
# 5. termal_bariyer_gerekli_mi / edge_cuts_yarigi_oner / özet / yazma
# ------------------------------------------------------------------

def _cift(ortak_bakir: bool, mesafe_x: float = 10.0, kenar_mesafesi: float = 5.0) -> TermalKaynakVeHassasParca:
    return TermalKaynakVeHassasParca(
        kaynak_isim="U4_LDO",
        kaynak_x=0.0,
        kaynak_y=0.0,
        hassas_isim="Y1_XTAL",
        hassas_x=mesafe_x,
        hassas_y=0.0,
        ortak_bakir_katmani=ortak_bakir,
        kart_kenarina_mesafe_mm=kenar_mesafesi,
    )


def test_termal_bariyer_gerekli_mi_ortak_bakir_yoksa_false():
    # Ortak bakır katmanı yoksa mesafeden bağımsız olarak hep False.
    assert termal_bariyer_gerekli_mi(_cift(ortak_bakir=False, mesafe_x=1.0)) is False
    assert termal_bariyer_gerekli_mi(_cift(ortak_bakir=False, mesafe_x=1000.0)) is False


def test_termal_bariyer_gerekli_mi_ortak_bakir_yakin_mesafede_true():
    assert termal_bariyer_gerekli_mi(_cift(ortak_bakir=True, mesafe_x=10.0)) is True


def test_termal_bariyer_gerekli_mi_ortak_bakir_uzak_mesafede_de_true():
    # KASITLI: mesafe-bazlı bir "güvenli eşik" YOK (bkz. fonksiyonun
    # docstring'i) — kaynaksız bir fizik sabiti uydurmak yerine bu proje
    # ortak kalın bakır katmanını TEK BAŞINA yeterli kabul eder, ne kadar
    # uzakta olursa olsun. Bu test, mesafenin karara HİÇ etki etmediğini
    # doğruluyor (önceki bir taslakta burada uydurma bir "3x zıt-köşe
    # mesafesi" eşiği vardı ve bu test False bekliyordu — kaldırıldı).
    assert termal_bariyer_gerekli_mi(_cift(ortak_bakir=True, mesafe_x=100.0)) is True
    assert termal_bariyer_gerekli_mi(_cift(ortak_bakir=True, mesafe_x=100_000.0)) is True


def test_termal_bariyer_gerekli_mi_karar_mesafeye_duyarsizdir():
    # Aynı ortak_bakir_katmani değeriyle, sadece mesafeyi değiştirerek
    # sonucun DEĞİŞMEDİĞİNİ doğrudan doğrular.
    yakin = termal_bariyer_gerekli_mi(_cift(ortak_bakir=True, mesafe_x=0.001))
    uzak = termal_bariyer_gerekli_mi(_cift(ortak_bakir=True, mesafe_x=500.0))
    assert yakin is uzak is True


def test_edge_cuts_yarigi_oner_bariyer_gerekmiyorsa_none():
    assert edge_cuts_yarigi_oner(_cift(ortak_bakir=False)) is None


def test_edge_cuts_yarigi_oner_yeterli_web_ile_yarik_doner():
    yarik = edge_cuts_yarigi_oner(_cift(ortak_bakir=True, kenar_mesafesi=5.0), yarik_genisligi_mm=1.0)
    assert isinstance(yarik, FrezelemeYarigi)
    assert yarik.web_genisligi_mm == pytest.approx(4.0)
    assert yarik.web_genisligi_mm >= MIN_WEB_GENISLIGI_MM


def test_edge_cuts_yarigi_oner_yetersiz_web_none_doner():
    # kenar mesafesi çok küçük -> web MIN_WEB_GENISLIGI_MM altında kalır
    yarik = edge_cuts_yarigi_oner(_cift(ortak_bakir=True, kenar_mesafesi=1.0), yarik_genisligi_mm=1.0)
    assert yarik is None


def test_termal_bariyer_ozetle_gerekmiyor_mesaji():
    ozet = termal_bariyer_ozetle(_cift(ortak_bakir=False), None)
    assert "gerekmiyor" in ozet


def test_termal_bariyer_ozetle_needs_human_mesaji():
    cift = _cift(ortak_bakir=True, kenar_mesafesi=1.0)
    yarik = edge_cuts_yarigi_oner(cift, yarik_genisligi_mm=1.0)
    assert yarik is None
    ozet = termal_bariyer_ozetle(cift, yarik)
    assert "NEEDS_HUMAN" in ozet


def test_termal_bariyer_ozetle_basarili_oneri_mesaji():
    cift = _cift(ortak_bakir=True, kenar_mesafesi=5.0)
    yarik = edge_cuts_yarigi_oner(cift, yarik_genisligi_mm=1.0)
    ozet = termal_bariyer_ozetle(cift, yarik)
    assert "önerildi" in ozet


def test_edge_cuts_yarigi_pcb_ye_yaz_iki_gr_line_ekler(tmp_path):
    hedef = tmp_path / "proje.kicad_pcb"
    hedef.write_text("(kicad_pcb\n\t(version 20240108)\n)\n", encoding="utf-8")

    yarik = FrezelemeYarigi(
        isim="termal_bariyer_test",
        baslangic=(5.0, -2.0),
        bitis=(5.0, 2.0),
        genislik_mm=1.0,
        web_genisligi_mm=4.0,
    )
    edge_cuts_yarigi_pcb_ye_yaz(str(hedef), yarik)

    icerik = hedef.read_text(encoding="utf-8")
    assert icerik.count('(layer "Edge.Cuts")') == 2
    assert (tmp_path / "proje.kicad_pcb.bak").exists()


def test_edge_cuts_yarigi_pcb_ye_yaz_dosya_yoksa_hata_firlatir(tmp_path):
    yarik = FrezelemeYarigi("x", (0, 0), (1, 1), 1.0, 4.0)
    with pytest.raises(FileNotFoundError):
        edge_cuts_yarigi_pcb_ye_yaz(str(tmp_path / "yok.kicad_pcb"), yarik)
