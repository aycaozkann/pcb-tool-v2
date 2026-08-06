"""ipc2221_clearance_hesaplayici.py için test suite.
Çalıştırmak için:  pytest -v test_ipc2221_clearance_hesaplayici.py
"""

import pytest

from ipc2221_clearance_hesaplayici import (
    Guven,
    KaplamaDurumu,
    KatmanTipi,
    _KAPLI_TABAN_MM,
    clearance_hesapla_mm,
    oz_testleri_calistir,
    tum_kombinasyonlari_uret,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Tek-kaynak-gerçeklik: pcb_stackup_planner ile birebir eşleşme
# ------------------------------------------------------------------

@pytest.mark.parametrize("v,beklenen_mm", [(15, 0.05), (30, 0.05), (50, 0.10), (100, 0.10), (500, 0.50)])
def test_dis_kaplamasiz_mevcut_tabloyla_birebir_eslesir(v, beklenen_mm):
    """Bu ortak noktalarda `pcb_stackup_planner.IPC2221_HARICI_MESAFE_TABLOSU_MM`
    ile SESSİZ SAPMA olmamalı."""
    from pcb_stackup_planner import gerekli_izolasyon_mesafesi_mm

    sonuc = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    assert sonuc.clearance_mm == pytest.approx(beklenen_mm)
    assert sonuc.clearance_mm == pytest.approx(gerekli_izolasyon_mesafesi_mm(v))
    assert sonuc.guven == Guven.MEVCUT_KOD_ILE_TUTARLI


# ------------------------------------------------------------------
# Basamak (step) davranışı — varsayılan, standart-sadık mod
# ------------------------------------------------------------------

def test_bant_icindeki_her_deger_ayni_sonucu_verir():
    """Basamak modunda 16V ile 30V AYNI clearance'ı vermeli (aynı bant)."""
    a = clearance_hesapla_mm(16, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    b = clearance_hesapla_mm(30, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    assert a.clearance_mm == b.clearance_mm
    assert a.interpolasyon_kullanildi is False


def test_tablo_ustundeki_voltaj_dogrusal_ekstrapole_edilir():
    sonuc = clearance_hesapla_mm(1000, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    # 500V -> 0.5mm, 1000V = 2x500V -> ~1.0mm (basit doğrusal ölçekleme)
    assert sonuc.clearance_mm == pytest.approx(1.0)
    assert sonuc.guven == Guven.MUHAFAZAKAR_VARSAYIM


def test_sifir_voltaj_gecerli_ve_pozitif_clearance_doner():
    sonuc = clearance_hesapla_mm(0, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    assert sonuc.clearance_mm > 0


def test_negatif_voltaj_reddedilir():
    with pytest.raises(ValueError):
        clearance_hesapla_mm(-5, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)


# ------------------------------------------------------------------
# İnterpolasyon modu
# ------------------------------------------------------------------

def test_interpolasyon_bant_ortasinda_ara_deger_uretir():
    """100V(0.10mm) ile 300V(0.40mm) arasında, 200V için interpolasyonlu
    değer basamak değerinden (0.40mm, üst banda yuvarlanmış) FARKLI ve
    ARADA olmalı."""
    basamak = clearance_hesapla_mm(200, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=False)
    interp = clearance_hesapla_mm(200, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=True)
    assert basamak.clearance_mm == pytest.approx(0.40)
    assert 0.10 < interp.clearance_mm < 0.40
    assert interp.interpolasyon_kullanildi is True
    assert basamak.interpolasyon_kullanildi is False


def test_interpolasyon_bant_sinirinda_tam_tablo_degerini_verir():
    interp = clearance_hesapla_mm(100, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=True)
    assert interp.clearance_mm == pytest.approx(0.10)


def test_interpolasyon_dusuk_guvenli_uc_noktayi_miras_alir():
    """REGRESYON: ilk taslakta `min()`/rank karışıklığı yüzünden interpolasyon
    YANLIŞLIKLA daha YÜKSEK güven seviyesini (MEVCUT_KOD_ILE_TUTARLI)
    raporluyordu — 100V(güven=MEVCUT_KOD_ILE_TUTARLI) ile 300V(güven=
    MUHAFAZAKAR_VARSAYIM) arasında interpolasyon yapılınca sonucun güveni
    İKİSİNİN EN AZ GÜVENİLİR olanı (MUHAFAZAKAR_VARSAYIM) olmalı."""
    interp = clearance_hesapla_mm(200, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=True)
    assert interp.guven == Guven.MUHAFAZAKAR_VARSAYIM


def test_interpolasyon_sifirdan_ilk_bandada_calisir():
    """0V ile ilk bant üst sınırı (15V) arasında interpolasyon (5V) NaN/hata
    üretmemeli."""
    sonuc = clearance_hesapla_mm(5, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=True)
    assert sonuc.clearance_mm > 0


# ------------------------------------------------------------------
# Kaplama durumu — taban etkisi (fiziksel gerçeklik nüansı)
# ------------------------------------------------------------------

def test_yuksek_voltajda_kapli_kaplamasizdan_kucuk():
    """Taban değerin (0.13mm) ÜSTÜNDEKİ bantlarda kaplama gerçekten
    mesafeyi AZALTMALI."""
    kaplamasiz = clearance_hesapla_mm(500, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    kapli = clearance_hesapla_mm(500, KatmanTipi.DIS, KaplamaDurumu.KAPLI)
    assert kapli.clearance_mm < kaplamasiz.clearance_mm


def test_dusuk_voltajda_kapli_taban_degerinde_kalir():
    """15V'ta kaplamasızın elektriksel minimumu (0.05mm) kaplı tabandan
    (0.13mm) zaten küçük — kaplı değer TABANDA kalmalı, ondan daha
    KÜÇÜLMEMELİ (üretim/işleme tabanı fiziksel bir alt sınırdır)."""
    kapli = clearance_hesapla_mm(15, KatmanTipi.DIS, KaplamaDurumu.KAPLI)
    assert kapli.clearance_mm == pytest.approx(_KAPLI_TABAN_MM)


def test_ic_katman_kaplama_kombinasyonu_reddedilir():
    """İç katmanlar conformal coating'e maruz KALMAZ — bu kombinasyon
    anlamsızdır, sessizce dış-kaplı değeri DÖNMEMELİ."""
    with pytest.raises(ValueError, match="tanımsızdır"):
        clearance_hesapla_mm(50, KatmanTipi.IC, KaplamaDurumu.KAPLI)


# ------------------------------------------------------------------
# İç katman
# ------------------------------------------------------------------

def test_ic_katman_dis_katmandan_asla_daha_dar_degil():
    for v in (15, 50, 100, 300, 500):
        dis = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
        ic = clearance_hesapla_mm(v, KatmanTipi.IC, KaplamaDurumu.KAPLAMASIZ)
        assert ic.clearance_mm >= dis.clearance_mm


def test_ic_katman_guveni_muhafazakar_varsayim():
    """İç katman değerleri bu modülde dış/kaplamasızdan KOPYALANDI (gerçek
    resmi tablo doğrulanamadı) — güven seviyesi bunu AÇIKÇA yansıtmalı."""
    sonuc = clearance_hesapla_mm(50, KatmanTipi.IC, KaplamaDurumu.KAPLAMASIZ)
    assert sonuc.guven == Guven.MUHAFAZAKAR_VARSAYIM


# ------------------------------------------------------------------
# Creepage
# ------------------------------------------------------------------

def test_creepage_varsayilan_clearancee_esittir():
    sonuc = clearance_hesapla_mm(100, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
    assert sonuc.creepage_mm == pytest.approx(sonuc.clearance_mm)


def test_creepage_katsayisi_uygulanir():
    sonuc = clearance_hesapla_mm(100, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, creepage_katsayisi=1.5)
    assert sonuc.creepage_mm == pytest.approx(sonuc.clearance_mm * 1.5)


def test_creepage_katsayisi_1den_kucuk_reddedilir():
    with pytest.raises(ValueError):
        clearance_hesapla_mm(100, KatmanTipi.DIS, creepage_katsayisi=0.9)


def test_creepage_her_zaman_clearancetan_buyuk_esit():
    for katsayi in (1.0, 1.1, 2.0):
        sonuc = clearance_hesapla_mm(300, KatmanTipi.DIS, creepage_katsayisi=katsayi)
        assert sonuc.creepage_mm >= sonuc.clearance_mm


# ------------------------------------------------------------------
# tum_kombinasyonlari_uret
# ------------------------------------------------------------------

def test_tum_kombinasyonlari_uret_gecerli_uc_anahtar_doner():
    sonuclar = tum_kombinasyonlari_uret(100)
    assert set(sonuclar) == {"external_uncoated", "internal_uncoated", "external_conformal_coated"}


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
