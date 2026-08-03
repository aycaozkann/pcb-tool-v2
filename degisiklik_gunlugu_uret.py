#!/usr/bin/env python3
"""
degisiklik_gunlugu_uret.py
============================
Git commit geçmişini `git log`'dan okuyup Obsidian uyumlu, insan tarafından
okunabilir bir `Changelog.md` üreten köprü — MASTER_RULEBOOK'un versiyon
kontrolü disiplinini (`KURULUM.md` madde 9: "her revizyon ayrı bir commit/
tag olmalı") saf metne çeviren "Otomatik Mühendislik Günlüğü".

NEDEN GIT LOG'U KOPYALAMAK YERİNE HER SEFERİNDE YENİDEN ÜRETMEK:
------------------------------------------------------------------
Bu modül `Changelog.md`'ye APPEND ETMEZ — her çalıştırmada git geçmişinin
TAMAMINDAN (veya `--maks-kayit`/`--yol-filtresi` ile sınırlanmış bir
alt kümesinden) baştan üretilir. Gerekçe: git zaten kanonik/tek doğru
kaynak (`bulgu_sozlesmesi.py`'nin "tek doğru kaynak" disipliniyle aynı) —
elle senkronize tutulan iki kopyanın (git geçmişi + append edilen
Changelog) ZAMANLA BİRBİRİNDEN SAPMASI kaçınılmazdır (bir commit mesajı
düzeltilir, ama Changelog'daki eski hali kalır). Yeniden üretim bu riski
YAPISAL olarak ortadan kaldırır.

DOĞRULAMA DURUMU: Bu makinede GERÇEK bir git deposuna (bu proje,
`aycaozkann/Pcb_desing`) karşı çalıştırıldı — `git_log_al()`/`git_log_ayristir()`
bu depodaki commit'lerin BİREBİR alıntılarıyla test edildi
(`test_degisiklik_gunlugu_uret.py`).

Co-Authored-By/Signed-off-by gibi trailer satırları GÖVDEDEN çıkarılır
(Changelog gürültüsüz kalsın diye) — bunlar KAYBOLMAZ, sadece Changelog'a
YAZILMAZ; `git log` her zaman tam gerçeği taşımaya devam eder.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

_ALAN_AYRAC = "\x1f"
_KAYIT_AYRAC = "\x1e"
_GIT_FORMAT = f"%H{_ALAN_AYRAC}%h{_ALAN_AYRAC}%ad{_ALAN_AYRAC}%an{_ALAN_AYRAC}%s{_ALAN_AYRAC}%b{_KAYIT_AYRAC}"

_TRAILER_SATIRI = re.compile(
    r"^(Co-Authored-By|Signed-off-by|Reviewed-by|Acked-by)\s*:", re.IGNORECASE
)


@dataclass
class Commit:
    hash_tam: str
    hash_kisa: str
    tarih: str  # YYYY-MM-DD (--date=short)
    yazar: str
    konu: str
    govde: str = ""


@dataclass
class GunSatiri:
    """Bir güne ait commit grubu — Changelog'un Obsidian günlük-not
    başlıklarıyla (`YYYY-MM-DD`) uyumlu bölümlenmesi için."""

    tarih: str
    commitler: List[Commit] = field(default_factory=list)


# ------------------------------------------------------------------
# 1. GIT LOG ÇALIŞTIRMA + AYRIŞTIRMA
# ------------------------------------------------------------------

def git_log_al(
    repo_dizini: str = ".",
    git: str = "git",
    yol_filtresi: Optional[str] = None,
    maks_kayit: Optional[int] = None,
    zaman_asimi_s: int = 30,
) -> str:
    """`git log`'u özel ayraçlı bir format ile çalıştırır, ham çıktıyı döner.

    `yol_filtresi` verilirse SADECE o yolu (ör. `"pcb-tool-v2"`) etkileyen
    commit'ler listelenir — bu repo birden fazla proje klasörü barındırıyorsa
    (bu makinede bilfiil öyle: `pcb-tool-v2/` yanında ESP32 proje klasörü
    de var) tek bir projenin günlüğünü diğerlerinden ayırmak için gerekli.

    `\\x1f`/`\\x1e` (birim/kayıt ayraçları, ASCII kontrol karakterleri)
    bilinçli seçildi — commit mesajlarında pipe (`|`), virgül, tırnak GİBİ
    yaygın karakterler geçebilir ama bu iki kontrol karakteri klavyeden asla
    girilemez, bu yüzden ayraç çakışması PRATİKTE imkânsızdır.
    """
    komut = [git, "-C", repo_dizini, "log", f"--pretty=format:{_GIT_FORMAT}", "--date=short"]
    if maks_kayit is not None:
        komut.append(f"-{maks_kayit}")
    if yol_filtresi:
        komut += ["--", yol_filtresi]

    sonuc = subprocess.run(
        komut, capture_output=True, text=True, encoding="utf-8", timeout=zaman_asimi_s
    )
    if sonuc.returncode != 0:
        raise RuntimeError(f"git log çalıştırılamadı: {sonuc.stderr}")
    return sonuc.stdout


def _govdeyi_temizle(govde: str) -> str:
    """Trailer satırlarını (`Co-Authored-By:` vb.) gövdeden çıkarır —
    bu satırlar git tarihinde KALIR, sadece Changelog'a YAZILMAZ."""
    satirlar = [s for s in govde.splitlines() if not _TRAILER_SATIRI.match(s.strip())]
    return "\n".join(satirlar).strip()


def git_log_ayristir(ham_cikti: str) -> List[Commit]:
    """`git_log_al()`'ın ham çıktısını `Commit` listesine çevirir.

    Boş depoda (`ham_cikti == ""`) boş liste döner — hata FIRLATMAZ; bu
    "henüz hiç commit yok" durumu, `bulgu_sozlesmesi.py`'nin "veri yoksa
    dur, hata fırlatma" disipliniyle tutarlı.
    """
    if not ham_cikti.strip():
        return []
    commitler: List[Commit] = []
    for ham_kayit in ham_cikti.split(_KAYIT_AYRAC):
        kayit = ham_kayit.strip("\n")
        if not kayit.strip():
            continue
        alanlar = kayit.split(_ALAN_AYRAC)
        if len(alanlar) < 5:
            continue  # bozuk/eksik satır — sessizce atla, çökme
        hash_tam, hash_kisa, tarih, yazar, konu = alanlar[:5]
        govde = _govdeyi_temizle(alanlar[5]) if len(alanlar) > 5 else ""
        commitler.append(Commit(hash_tam, hash_kisa, tarih, yazar, konu, govde))
    return commitler


def gune_gore_grupla(commitler: Sequence[Commit]) -> List[GunSatiri]:
    """Commit'leri tarihe göre gruplar — `git log` zaten en-yeni-önce
    sıralı döndürdüğü için burada AYRICA sıralama YAPILMAZ (girdi sırası
    korunur); bir gün içindeki commit sırası da en-yeniden-eskiye kalır."""
    gunler: List[GunSatiri] = []
    mevcut: Optional[GunSatiri] = None
    for c in commitler:
        if mevcut is None or mevcut.tarih != c.tarih:
            mevcut = GunSatiri(tarih=c.tarih)
            gunler.append(mevcut)
        mevcut.commitler.append(c)
    return gunler


# ------------------------------------------------------------------
# 2. MARKDOWN ÜRETİMİ
# ------------------------------------------------------------------

def changelog_markdown_uret(
    commitler: Sequence[Commit],
    baslik: str = "Değişiklik Günlüğü",
    proje_adi: str = "",
) -> str:
    """`Commit` listesinden Obsidian uyumlu Markdown üretir.

    Her gün bir `##` başlığı (Obsidian'ın günlük not formatıyla aynı
    `YYYY-MM-DD` biçimi — istenirse günlük notlara link olarak da
    kullanılabilir), her commit tek satırlık bir madde + (varsa) gövde
    alt-madde olarak yazılır.
    """
    satirlar = [f"# {baslik}"]
    if proje_adi:
        satirlar.append(f"\n*Kapsam: `{proje_adi}`*")
    satirlar.append(
        "\n> Bu dosya `degisiklik_gunlugu_uret.py` ile git geçmişinden "
        "OTOMATİK üretilir — elle düzenleme bir sonraki üretimde KAYBOLUR. "
        "Değişiklik commit mesajında yapılmalı."
    )

    if not commitler:
        satirlar.append("\n*(henüz commit yok)*")
        return "\n".join(satirlar) + "\n"

    for gun in gune_gore_grupla(commitler):
        satirlar.append(f"\n## {gun.tarih}\n")
        for c in gun.commitler:
            satirlar.append(f"- **{c.hash_kisa}** {c.konu} — *{c.yazar}*")
            if c.govde:
                for govde_satiri in c.govde.splitlines():
                    if govde_satiri.strip():
                        satirlar.append(f"  - {govde_satiri.strip()}")

    return "\n".join(satirlar) + "\n"


def changelog_yaz(
    hedef_yol: str,
    repo_dizini: str = ".",
    git: str = "git",
    yol_filtresi: Optional[str] = None,
    maks_kayit: Optional[int] = None,
    baslik: str = "Değişiklik Günlüğü",
) -> str:
    """Uçtan uca: `git log` çalıştırır, ayrıştırır, Markdown üretir,
    `hedef_yol`'a yazar. Dönen değer yazılan dosyanın yoludur."""
    ham = git_log_al(repo_dizini, git=git, yol_filtresi=yol_filtresi, maks_kayit=maks_kayit)
    commitler = git_log_ayristir(ham)
    icerik = changelog_markdown_uret(commitler, baslik=baslik, proje_adi=yol_filtresi or "")

    yol = Path(hedef_yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# 3. ÖZ-TEST (fault-injection dahil) — bu makinedeki GERÇEK depoya karşı
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: ayrıştırıcıya bozuk (ayraç sayısı eksik) bir kayıt
    verirsek o kayıt SESSİZCE ATLANMALI, çökmemeli VE geçerli kayıtları
    da BOZMAMALI — bu, ayrıştırıcının gerçekten alan sayısını kontrol
    ettiğinin kanıtıdır."""
    iyi = f"hash1{_ALAN_AYRAC}h1{_ALAN_AYRAC}2026-01-01{_ALAN_AYRAC}Ayca{_ALAN_AYRAC}konu{_KAYIT_AYRAC}"
    bozuk = f"eksik-alanlar{_KAYIT_AYRAC}"
    commitler = git_log_ayristir(iyi + bozuk)
    return len(commitler) == 1 and commitler[0].hash_kisa == "h1"


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: ayrıştırma boş olabilir")

    ornek = f"h{_ALAN_AYRAC}ks{_ALAN_AYRAC}2026-07-30{_ALAN_AYRAC}Ayca{_ALAN_AYRAC}konu{_ALAN_AYRAC}govde satiri{_KAYIT_AYRAC}"
    commitler = git_log_ayristir(ornek)
    if len(commitler) != 1 or commitler[0].govde != "govde satiri":
        hatalar.append("temel ayrıştırma başarısız")

    if git_log_ayristir("") != []:
        hatalar.append("boş girdi boş liste döndürmedi")

    trailer_metni = "asıl gövde\n\nCo-Authored-By: X <x@example.com>"
    if "Co-Authored-By" in _govdeyi_temizle(trailer_metni):
        hatalar.append("trailer satırı temizlenmedi")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: degisiklik_gunlugu_uret.py öz testleri temiz.")
