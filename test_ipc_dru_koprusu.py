"""ipc_dru_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_ipc_dru_koprusu.py

NOT: `track_width`/`clearance`/`annular_width` constraint'lerinin GERÇEK
`kicad-cli pcb drc` (KiCad 10.0.4) tarafından UYGULANDIĞI (parse değil,
gerçek ihlal üretimi) bu makinede, `ESP32C3_SmartBand.kicad_pcb`'ye karşı
GERÇEKTEN doğrulandı (bkz. modülün başlığındaki DOĞRULAMA DURUMU notu) —
proje sahibinin gerçek `.kicad_dru` dosyası GÜVENLİ ŞEKİLDE YEDEKLENİP
GERİ YÜKLENDİ, test paketine dahil edilmedi (gerçek proje dosyalarına
dokunmak otomatik test koşumunun İŞİ DEĞİLDİR). Buradaki testler o
doğrulamada kullanılan GERÇEK içerik üretim mantığını (sıralama, kaçınılan
tuzaklar) izole olarak kilitler.
"""

from pathlib import Path

import pytest

from ipc2152_hesaplayici import KatmanTipi as Ipc2152KatmanTipi, ipc2152_min_iz_genisligi_mm
from ipc2221_clearance_hesaplayici import (
    KatmanTipi as Ipc2221KatmanTipi,
    clearance_hesapla_mm,
)
from ipc6012_dfm_motoru import SINIF_LIMITLERI, Ipc6012Sinifi

from ipc_dru_koprusu import (
    DruKurali,
    KuralOnceligi,
    ipc2152_kuraline_cevir,
    ipc2221_kuraline_cevir,
    ipc6012_kuraline_cevir,
    istisna_kurali_uret,
    kural_dosyasi_olustur,
    oz_testleri_calistir,
    _kicad_dru_govdesi_uret,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# DruKurali — girdi doğrulaması (üç sessiz tuzağa karşı savunma)
# ------------------------------------------------------------------

def test_negatif_deger_reddedilir():
    with pytest.raises(ValueError):
        DruKurali("X", "A.NetClass == 'Y'", "clearance", -0.1)


def test_sifir_deger_reddedilir():
    with pytest.raises(ValueError):
        DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.0)


def test_isimde_noktali_virgul_reddedilir():
    """Tuzak #3: ';' KiCad'de yorum karakteri DEĞİL, parse'ı çökertir —
    bu modül bunun kaynağa hiç sızmasına izin vermez."""
    with pytest.raises(ValueError, match=";"):
        DruKurali("Kötü;İsim", "A.NetClass == 'Y'", "clearance", 0.2)


def test_kosulda_noktali_virgul_reddedilir():
    with pytest.raises(ValueError):
        DruKurali("X", "A.NetClass == 'Y';DROP", "clearance", 0.2)


def test_isimde_satir_sonu_reddedilir():
    with pytest.raises(ValueError):
        DruKurali("X\nY", "A.NetClass == 'Y'", "clearance", 0.2)


def test_blok_dogru_sexpr_uretir():
    kural = DruKurali("Test Kuralı", "A.NetClass == 'GUC'", "track_width", 0.25)
    blok = kural.blok()
    assert '(rule "Test Kuralı"' in blok
    assert '(condition "A.NetClass == \'GUC\'")' in blok
    assert "(constraint track_width (min 0.25mm)))" in blok


# ------------------------------------------------------------------
# _kicad_dru_govdesi_uret — üç sessiz tuzağa karşı YAPISAL garanti
# ------------------------------------------------------------------

def test_version_basligi_her_zaman_ilk_satir():
    """Tuzak #1: '(version 1)' yoksa dosyanın TAMAMI yok sayılır."""
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2)
    metin = _kicad_dru_govdesi_uret([kural])
    assert metin.startswith("(version 1)")


def test_priority_token_asla_uretilmez():
    """Tuzak #2: '(priority N)' geçersiz bir token — bu modül onu HİÇ
    üretmez, `DruKurali`'de böyle bir alan bile YOK."""
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2)
    metin = _kicad_dru_govdesi_uret([kural])
    assert "priority" not in metin


def test_yorum_karakteri_hash_kullanir_noktali_virgul_degil():
    """Tuzak #3: yorum karakteri '#' olmalı, ';' parse'ı çökertir."""
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2, aciklama="bir not")
    metin = _kicad_dru_govdesi_uret([kural])
    assert "# bir not" in metin
    assert ";" not in metin


def test_aciklamada_noktali_virgul_serbesttir():
    """REGRESYON: ilk taslak aciklama alanında ';' karakterini de
    yasaklıyordu — ama aciklama HER ZAMAN '# ' önekiyle bir yorum satırına
    sarılır, o satırın İÇİNDEKİ ';' KiCad'de TAMAMEN zararsızdır. Gerçek
    kullanım (ör. IPC-6012 kaynak notları) doğal metinde ';' içerebilir —
    bu artık reddedilmemeli."""
    kural = DruKurali(
        "X", "A.NetClass == 'Y'", "clearance", 0.2,
        aciklama="birinci not; ikinci not",
    )
    assert "birinci not; ikinci not" in kural.blok()


def test_aciklamadaki_her_satir_kendi_hash_onekini_alir():
    """Çok satırlı bir açıklamanın İKİNCİ satırı önekSİZ kalırsa geçersiz
    bir s-expression token'ı gibi ayrıştırılıp TÜM dosyanın çökmesine yol
    açabilir — her satır KENDİ '#' önekini almalı."""
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2, aciklama="birinci satır\nikinci satır")
    blok = kural.blok()
    for satir in blok.splitlines():
        if satir in ("birinci satır", "ikinci satır"):
            pytest.fail(f"önekSİZ satır bulundu: {satir!r}")
    assert "# birinci satır" in blok
    assert "# ikinci satır" in blok


def test_baslik_yorumu_de_hash_ile_yazilir():
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2)
    metin = _kicad_dru_govdesi_uret([kural], baslik_yorumu="Çok satırlı\nbaşlık notu")
    assert "# Çok satırlı" in metin
    assert "# başlık notu" in metin


def test_istisna_kurallari_genel_kurallardan_once_yazilir():
    """Tuzak #2'nin doğrudan sonucu: 'priority' yok, sıra KiCad'de kuralı
    belirler — istisna kuralları HER ZAMAN önce gelmeli."""
    genel = DruKurali("Genel Kural", "A.NetClass == 'GUC'", "track_width", 0.25, oncelik=KuralOnceligi.GENEL)
    istisna = DruKurali("İstisna Kural", "A.Reference == 'J2'", "clearance", 0.13, oncelik=KuralOnceligi.ISTISNA)
    # BİLEREK ters sırada veriyoruz — fonksiyon kendi sıralamasını yapmalı.
    metin = _kicad_dru_govdesi_uret([genel, istisna])
    assert metin.index('"İstisna Kural"') < metin.index('"Genel Kural"')


def test_ayni_oncelik_grubunda_giris_sirasi_korunur():
    """Kararlı (stable) sıralama: aynı öncelik grubundaki kurallar
    kendi aralarında verildiği sırayı korumalı."""
    a = DruKurali("A", "A.NetClass == 'X'", "clearance", 0.1)
    b = DruKurali("B", "A.NetClass == 'Y'", "clearance", 0.2)
    metin = _kicad_dru_govdesi_uret([a, b])
    assert metin.index('"A"') < metin.index('"B"')


# ------------------------------------------------------------------
# kural_dosyasi_olustur — dosyaya yazma
# ------------------------------------------------------------------

def test_bos_kural_listesi_reddedilir():
    with pytest.raises(ValueError):
        kural_dosyasi_olustur("x.kicad_dru", [])


def test_dosyaya_yazilir_ve_version_basligi_icerir(tmp_path):
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2)
    hedef = tmp_path / "proje.kicad_dru"
    yol = kural_dosyasi_olustur(str(hedef), [kural])
    assert Path(yol).exists()
    icerik = Path(yol).read_text(encoding="utf-8")
    assert icerik.startswith("(version 1)")


def test_mevcut_dosya_yedeklenir(tmp_path):
    hedef = tmp_path / "proje.kicad_dru"
    hedef.write_text("(version 1)\n# eski içerik\n", encoding="utf-8")
    kural = DruKurali("Yeni", "A.NetClass == 'Y'", "clearance", 0.2)
    kural_dosyasi_olustur(str(hedef), [kural], yedek_al=True)
    yedek = hedef.with_suffix(hedef.suffix + ".bak")
    assert yedek.exists()
    assert "eski içerik" in yedek.read_text(encoding="utf-8")


def test_yedek_al_false_ise_yedek_olusturulmaz(tmp_path):
    hedef = tmp_path / "proje.kicad_dru"
    hedef.write_text("(version 1)\n", encoding="utf-8")
    kural = DruKurali("Yeni", "A.NetClass == 'Y'", "clearance", 0.2)
    kural_dosyasi_olustur(str(hedef), [kural], yedek_al=False)
    assert not hedef.with_suffix(hedef.suffix + ".bak").exists()


def test_ust_dizin_yoksa_olusturulur(tmp_path):
    hedef = tmp_path / "alt" / "dizin" / "proje.kicad_dru"
    kural = DruKurali("X", "A.NetClass == 'Y'", "clearance", 0.2)
    kural_dosyasi_olustur(str(hedef), [kural])
    assert hedef.exists()


# ------------------------------------------------------------------
# IPC sonuçlarını DruKurali'na çeviren yardımcılar
# ------------------------------------------------------------------

def test_ipc2152_kuraline_cevir():
    sonuc = ipc2152_min_iz_genisligi_mm(5.0, 10.0, Ipc2152KatmanTipi.DIS)
    kural = ipc2152_kuraline_cevir("HIGH_CURRENT", sonuc)
    assert kural.constraint_tipi == "track_width"
    assert kural.min_deger_mm == sonuc.genislik_mm
    assert "HIGH_CURRENT" in kural.kosul
    assert "IPC-2152" in kural.aciklama


def test_ipc2221_kuraline_cevir():
    sonuc = clearance_hesapla_mm(300, Ipc2221KatmanTipi.DIS)
    kural = ipc2221_kuraline_cevir("MAINS_L", "MAINS_N", sonuc)
    assert kural.constraint_tipi == "clearance"
    assert kural.min_deger_mm == sonuc.clearance_mm
    assert "MAINS_L" in kural.kosul and "MAINS_N" in kural.kosul


def test_ipc6012_kuraline_cevir_annular_width_uretir():
    limitler = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_2]
    kurallar = ipc6012_kuraline_cevir(limitler)
    assert len(kurallar) == 1
    assert kurallar[0].constraint_tipi == "annular_width"
    assert kurallar[0].min_deger_mm == limitler.min_annular_ring_mm


def test_istisna_kurali_uret_dogru_referans_kosulu():
    kural = istisna_kurali_uret("J2 İstisnası", "J2", 0.13)
    assert kural.kosul == "A.Reference == 'J2' && B.Reference == 'J2'"
    assert kural.oncelik == KuralOnceligi.ISTISNA


# ------------------------------------------------------------------
# Uçtan uca: üç IPC modülünden gerçek bir .kicad_dru üretimi
# ------------------------------------------------------------------

def test_uctan_uca_uc_ipc_modulunden_dosya_uretilir(tmp_path):
    ipc2152_sonuc = ipc2152_min_iz_genisligi_mm(8.0, 10.0, Ipc2152KatmanTipi.DIS)
    ipc2221_sonuc = clearance_hesapla_mm(100, Ipc2221KatmanTipi.DIS)
    limitler = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_2]

    kurallar = [
        ipc2152_kuraline_cevir("GUC", ipc2152_sonuc),
        ipc2221_kuraline_cevir("MAINS_L", "MAINS_N", ipc2221_sonuc),
        *ipc6012_kuraline_cevir(limitler),
        istisna_kurali_uret("J2 İstisnası", "J2", 0.13, aciklama="USB-C pad-içi istisna"),
    ]
    hedef = tmp_path / "test_projesi.kicad_dru"
    yol = kural_dosyasi_olustur(str(hedef), kurallar, baslik_yorumu="Test projesi IPC kuralları")

    icerik = Path(yol).read_text(encoding="utf-8")
    assert icerik.startswith("(version 1)")
    assert "priority" not in icerik
    # ';' YALNIZCA '#' önekli yorum satırlarının İÇİNDE serbesttir (ör.
    # IPC-6012 kaynak notu doğal metinde ';' içerir) — yapısal
    # (rule/condition/constraint) satırlarda ASLA görünmemeli.
    for satir in icerik.splitlines():
        if ";" in satir:
            assert satir.strip().startswith("#"), f"';' yorum DIŞINDA bir satırda: {satir!r}"
    # İstisna (ISTISNA öncelikli) kural, GENEL öncelikli üç kuraldan
    # HER BİRİNDEN önce yazılmış olmalı (tuzak #2'nin doğrudan sonucu).
    istisna_konumu = icerik.index('"J2 İstisnası"')
    assert istisna_konumu < icerik.index("IPC-2152")
    assert istisna_konumu < icerik.index("IPC-2221")
    assert istisna_konumu < icerik.index("IPC-6012")
    assert "annular_width" in icerik
    assert "track_width" in icerik
    assert "clearance" in icerik


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
