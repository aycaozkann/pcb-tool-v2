"""degisiklik_gunlugu_uret.py için test suite.
Çalıştırmak için:  pytest -v test_degisiklik_gunlugu_uret.py

`test_gercek_repo_*` testleri, bu makinedeki GERÇEK git deposuna
(aycaozkann/Pcb_desing, üzerinde çalıştığımız repo) karşı koşar — sahte/mock
git log DEĞİL. Depo taşınırsa/farklı bir makinede farklı geçmişle
çalıştırılırsa bu testler farklı sayılar bulabilir; bu yüzden onlar
YAPISAL özellikleri (hiç çökmemek, en az 1 commit bulmak, alan sayısı)
doğrular, belirli bir commit sayısını SABİTLEMEZ.
"""

import os
from pathlib import Path

import pytest

from degisiklik_gunlugu_uret import (
    Commit,
    _ALAN_AYRAC,
    _KAYIT_AYRAC,
    _govdeyi_temizle,
    changelog_markdown_uret,
    changelog_yaz,
    git_log_al,
    git_log_ayristir,
    gune_gore_grupla,
    oz_testleri_calistir,
    _testin_bos_olmadigini_kanitla,
)

def _git_deposu_kokunu_bul(baslangic: Path) -> Path:
    """`.git` dizinini yukarı doğru arayarak GERÇEK depo kökünü bulur.

    ESKİ HALİ `Path(__file__).resolve().parent.parent` idi — bu, aracın HER
    ZAMAN `<repo_kök>/pcb-tool-v2/` gibi TAM olarak bir seviye iç içe
    olduğunu VARSAYIYORDU. Bu araç başka bir projeye (ör. ESP32-C3 Smart
    Board kartının kendi klasörüne, `.git`'in doğrudan araç klasörünün
    İÇİNDE olduğu bir düzende) taşındığında bu varsayım YANLIŞ çıktı ve
    `git log` "not a git repository" hatasıyla çöktü. Artık `.git`
    yukarı doğru ARANIR, derinlik SABİTLENMEZ.
    """
    p = baslangic
    while True:
        if (p / ".git").exists():
            return p
        if p.parent == p:
            return baslangic  # .git bulunamadı — eski davranışa düş
        p = p.parent


# Bu test dosyasının bulunduğu dizin, git deposunun İÇİNDE bir yerde.
_REPO_KOKU = str(_git_deposu_kokunu_bul(Path(__file__).resolve().parent))

# Araç klasörünün depo köküne göre GÖRECELİ yolu — HARDCODE "pcb-tool-v2"
# yerine dinamik hesaplanır (bkz. yukarıdaki _git_deposu_kokunu_bul notu):
# bu araç `.git`'in doğrudan İÇİNDE olduğu bir depoya (ör. ESP32 kart
# klasörü) taşınırsa görece yol "." olur — o durumda alt-yol filtresi
# testi anlamsızdır (filtrelenecek bir ÜST klasör yok), ilgili test bunu
# `pytest.skip` ile açıkça işaretler.
_ARAC_GORECELI_YOL = os.path.relpath(Path(__file__).resolve().parent, _REPO_KOKU)


# ------------------------------------------------------------------
# Ayrıştırma — sentetik veri (kenar durumları)
# ------------------------------------------------------------------

def _kayit(hash_tam="h1234567890", hash_kisa="h123456", tarih="2026-07-30",
           yazar="Ayca", konu="konu", govde="") -> str:
    return _ALAN_AYRAC.join([hash_tam, hash_kisa, tarih, yazar, konu, govde]) + _KAYIT_AYRAC


def test_tek_commit_dogru_ayristirilir():
    commitler = git_log_ayristir(_kayit())
    assert len(commitler) == 1
    assert commitler[0] == Commit("h1234567890", "h123456", "2026-07-30", "Ayca", "konu", "")


def test_govdeli_commit_govdeyi_korur():
    commitler = git_log_ayristir(_kayit(govde="ilk satır\nikinci satır"))
    assert commitler[0].govde == "ilk satır\nikinci satır"


def test_bos_girdi_bos_liste():
    assert git_log_ayristir("") == []
    assert git_log_ayristir("   \n  ") == []


def test_eksik_alanli_kayit_sessizce_atlanir():
    """5'ten az alanlı bozuk bir kayıt çökmemeli, sadece atlanmalı."""
    bozuk = f"sadece-iki-alan{_ALAN_AYRAC}x{_KAYIT_AYRAC}"
    assert git_log_ayristir(bozuk) == []


def test_bozuk_kayittan_sonraki_iyi_kayit_bozulmaz():
    ham = f"kisa{_KAYIT_AYRAC}" + _kayit()
    commitler = git_log_ayristir(ham)
    assert len(commitler) == 1
    assert commitler[0].hash_kisa == "h123456"


def test_trailer_satiri_govdeden_cikarilir():
    temiz = _govdeyi_temizle("asıl mesaj\n\nCo-Authored-By: X <x@example.com>")
    assert "Co-Authored-By" not in temiz
    assert "asıl mesaj" in temiz


def test_signed_off_by_de_temizlenir():
    temiz = _govdeyi_temizle("mesaj\nSigned-off-by: Y <y@example.com>")
    assert "Signed-off-by" not in temiz


def test_trailer_olmayan_govde_degismez():
    assert _govdeyi_temizle("sadece normal metin") == "sadece normal metin"


# ------------------------------------------------------------------
# Günlere göre gruplama
# ------------------------------------------------------------------

def test_ayni_gunun_commitleri_tek_grupta():
    commitler = [
        Commit("a", "a1", "2026-07-30", "X", "birinci"),
        Commit("b", "b1", "2026-07-30", "X", "ikinci"),
        Commit("c", "c1", "2026-07-29", "X", "üçüncü"),
    ]
    gunler = gune_gore_grupla(commitler)
    assert len(gunler) == 2
    assert len(gunler[0].commitler) == 2
    assert gunler[0].tarih == "2026-07-30"
    assert gunler[1].tarih == "2026-07-29"


def test_bos_commit_listesi_bos_gun_listesi():
    assert gune_gore_grupla([]) == []


# ------------------------------------------------------------------
# Markdown üretimi
# ------------------------------------------------------------------

def test_markdown_uyari_notunu_icerir():
    md = changelog_markdown_uret([])
    assert "OTOMATİK üretilir" in md
    assert "henüz commit yok" in md


def test_markdown_commit_satirini_uretir():
    commitler = [Commit("h1234567890", "h123456", "2026-07-30", "Ayca", "bir özellik eklendi")]
    md = changelog_markdown_uret(commitler)
    assert "## 2026-07-30" in md
    assert "h123456" in md
    assert "bir özellik eklendi" in md
    assert "Ayca" in md


def test_markdown_govdeyi_alt_madde_yapar():
    commitler = [Commit("h", "h1", "2026-07-30", "X", "konu", "detay satırı")]
    md = changelog_markdown_uret(commitler)
    assert "  - detay satırı" in md


def test_markdown_proje_adini_yazar():
    md = changelog_markdown_uret([], proje_adi="pcb-tool-v2")
    assert "pcb-tool-v2" in md


# ------------------------------------------------------------------
# GERÇEK DEPO — bu makinedeki aycaozkann/Pcb_desing deposuna karşı
# ------------------------------------------------------------------

def test_gercek_repo_git_log_calisir_ve_commit_bulur():
    ham = git_log_al(_REPO_KOKU, maks_kayit=5)
    commitler = git_log_ayristir(ham)
    assert len(commitler) >= 1
    for c in commitler:
        assert len(c.hash_kisa) >= 4
        assert c.tarih  # boş olmamalı


def test_gercek_repo_yol_filtresi_calisir():
    """Araç klasörünün yolunu etkileyen commit'ler, TÜM depo geçmişinin
    bir ALT KÜMESİ olmalı — AMA SADECE araç klasörü depo kökünden FARKLI
    bir alt-klasördeyse (ör. `<repo>/pcb-tool-v2/`); araç `.git`'in
    doğrudan İÇİNDE olduğu bir depoda ise (ör. ESP32 kart klasörü) bu
    testin filtreleyecek bir üst klasörü yoktur."""
    if _ARAC_GORECELI_YOL in (".", ""):
        pytest.skip("araç klasörü depo köküyle aynı — alt-yol filtresi testi anlamsız")
    tum_commitler = git_log_ayristir(git_log_al(_REPO_KOKU))
    filtreli = git_log_ayristir(git_log_al(_REPO_KOKU, yol_filtresi=_ARAC_GORECELI_YOL))
    assert 0 < len(filtreli) <= len(tum_commitler)


def test_gercek_repo_maks_kayit_siniri_uygulanir():
    commitler = git_log_ayristir(git_log_al(_REPO_KOKU, maks_kayit=2))
    assert len(commitler) <= 2


def test_gercek_repo_olmayan_dizinde_hata_firlatir():
    with pytest.raises(RuntimeError):
        git_log_al("C:/bu/dizin/kesinlikle/yok/xyz123")


def test_gercek_repo_uctan_uca_dosyaya_yazilir(tmp_path):
    hedef = tmp_path / "DOCS" / "Changelog.md"
    filtre = None if _ARAC_GORECELI_YOL in (".", "") else _ARAC_GORECELI_YOL
    yol = changelog_yaz(
        str(hedef), repo_dizini=_REPO_KOKU, yol_filtresi=filtre, maks_kayit=10,
    )
    assert Path(yol).exists()
    icerik = Path(yol).read_text(encoding="utf-8")
    assert "Değişiklik Günlüğü" in icerik
    assert "##" in icerik  # en az bir tarih başlığı


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
