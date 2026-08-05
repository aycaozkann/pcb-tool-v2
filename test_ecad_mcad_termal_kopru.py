"""
ecad_mcad_termal_kopru.py için test suite.
Çalıştırmak için:  pytest -v test_ecad_mcad_termal_kopru.py
"""

import pytest

from pcb_stackup_planner import TermalYonetim

from bulgu_sozlesmesi import BulguDurumu

from ecad_mcad_termal_kopru import (
    TermalTemasBolgesi,
    soguturucu_yuzey_bul,
    KomponentTermalDurumu,
    termal_yonetim_ve_mask_kontrolu,
    termal_mekanik_taramasi_calistir,
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
    JunctionSicakligiGirdisi,
    junction_sicakligi_hesapla_c,
    junction_sicakligi_kontrolu,
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
# 2b. termal_mekanik_taramasi_calistir (bulgu_sozlesmesi entegrasyonu)
# ------------------------------------------------------------------

def test_tarama_komponent_yoksa_kapsam_yok_doner():
    bulgu = termal_mekanik_taramasi_calistir([], [KARE_YUZEY])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert bulgu.taranan == 0
    assert bulgu.ihlaller == []


def test_tarama_temiz_komponentlerle_pass_doner():
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(1.0), x=5, y=5, b_mask_acikligi_tanimli_mi=True,
        yuzey_kaplamasi="ENIG",
    )
    bulgu = termal_mekanik_taramasi_calistir([durum], [KARE_YUZEY])
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.taranan == 1
    assert bulgu.ihlaller == []


def test_tarama_ihlalli_komponentle_fail_doner_ve_isim_tasir():
    durum = KomponentTermalDurumu(
        yonetim=_yonetim(1.0), x=5, y=5, b_mask_acikligi_tanimli_mi=False,
    )
    bulgu = termal_mekanik_taramasi_calistir([durum], [KARE_YUZEY])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.taranan == 1
    assert len(bulgu.ihlaller) == 1
    assert bulgu.ihlaller[0]["komponent"] == durum.yonetim.isim
    assert "B.Mask açıklığı tanımlı değil" in bulgu.ihlaller[0]["mesaj"]


def test_tarama_birden_fazla_komponent_karisik_sonuc():
    temiz = KomponentTermalDurumu(
        yonetim=_yonetim(1.0, via=99), x=5, y=5, b_mask_acikligi_tanimli_mi=True,
        yuzey_kaplamasi="ENIG",
    )
    hatali = KomponentTermalDurumu(
        yonetim=_yonetim(1.0), x=5, y=5, b_mask_acikligi_tanimli_mi=False,
    )
    bulgu = termal_mekanik_taramasi_calistir([temiz, hatali], [KARE_YUZEY])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.taranan == 2
    assert len(bulgu.ihlaller) == 1


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


# ------------------------------------------------------------------
# FAZ 0.5-4: junction_sicakligi_hesapla_c / junction_sicakligi_kontrolu
# ------------------------------------------------------------------

def test_rtheta_verisi_yoksa_hesaplanamaz_ve_kapsam_yok():
    """Datasheet Rθ verisi olmadan bir sayı UYDURULMAZ."""
    girdi = JunctionSicakligiGirdisi(isim="U1", guc_W=1.0)
    tj, sebep = junction_sicakligi_hesapla_c(girdi)
    assert tj is None
    assert "UYDURULAMAZ" in sebep

    bulgu = junction_sicakligi_kontrolu(girdi)
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert bulgu.taranan == 0


def test_rtheta_ja_ile_basit_hesap():
    """Tj = Ta + P*RθJA — ders kitabı örneği: 25 + 1.0*40 = 65°C."""
    girdi = JunctionSicakligiGirdisi(
        isim="U2_LDO", guc_W=1.0, r_theta_ja_c_per_w=40.0, ortam_sicakligi_c=25.0,
    )
    tj, yontem = junction_sicakligi_hesapla_c(girdi)
    assert tj == pytest.approx(65.0)
    assert "RθJA" in yontem


def test_kasa_temasi_varsa_rtheta_jc_yolu_tercih_edilir():
    """RθJC + kasa temas sıcaklığı İKİSİ de verilmişse, RθJA verilmiş olsa
    BİLE kasa-temaslı yol TERCİH EDİLİR (gerçek referans nokta kasadır)."""
    girdi = JunctionSicakligiGirdisi(
        isim="U3_MOSFET", guc_W=2.0,
        r_theta_ja_c_per_w=40.0,       # verilse bile kullanılmamalı
        r_theta_jc_c_per_w=5.0,
        kasa_temas_sicakligi_c=45.0,   # ölçülen/verilen kasa sıcaklığı
        ortam_sicakligi_c=25.0,
    )
    tj, yontem = junction_sicakligi_hesapla_c(girdi)
    assert tj == pytest.approx(45.0 + 2.0 * 5.0)  # 55°C, RθJA yolunun 105°C'siyle KARIŞTIRILMAMALI
    assert "RθJC" in yontem


def test_maks_tj_verilmezse_pass_fail_karari_verilmez_kapsam_yok():
    """Tj hesaplanabilir ama sınır (Tj_max) yoksa PASS/FAIL UYDURULMAZ —
    hesaplanan değer yine de `detay`'da RAPORLANIR (25 + 0.5*60 = 55.0)."""
    girdi = JunctionSicakligiGirdisi(isim="U4", guc_W=0.5, r_theta_ja_c_per_w=60.0)
    bulgu = junction_sicakligi_kontrolu(girdi)
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert "55.0" in bulgu.detay


def test_tj_sinirin_altindaysa_pass():
    girdi = JunctionSicakligiGirdisi(
        isim="U5", guc_W=1.0, r_theta_ja_c_per_w=30.0, ortam_sicakligi_c=25.0,
        maks_izin_verilen_tj_c=125.0,
    )
    bulgu = junction_sicakligi_kontrolu(girdi)
    assert bulgu.durum == BulguDurumu.PASS


def test_tj_siniri_asarsa_fail_ve_ihlal_detayli_raporlanir():
    girdi = JunctionSicakligiGirdisi(
        isim="U6_ASIRI_ISINAN", guc_W=3.0, r_theta_ja_c_per_w=40.0, ortam_sicakligi_c=25.0,
        maks_izin_verilen_tj_c=125.0,  # Tj = 25 + 3*40 = 145 > 125
    )
    bulgu = junction_sicakligi_kontrolu(girdi)
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["isim"] == "U6_ASIRI_ISINAN"
    assert bulgu.ihlaller[0]["tj_c"] == pytest.approx(145.0)


def test_fault_injection_yanlis_esik_gercekten_fail_uretir():
    """Fault-injection: kasıtlı olarak düşük bir Tj_max verip testin
    GERÇEKTEN bir şey kontrol ettiğini kanıtlar (projenin genel deseni)."""
    girdi = JunctionSicakligiGirdisi(
        isim="U7", guc_W=0.1, r_theta_ja_c_per_w=10.0, ortam_sicakligi_c=25.0,
        maks_izin_verilen_tj_c=1.0,  # bilerek imkansız derecede düşük
    )
    bulgu = junction_sicakligi_kontrolu(girdi)
    assert bulgu.durum == BulguDurumu.FAIL
