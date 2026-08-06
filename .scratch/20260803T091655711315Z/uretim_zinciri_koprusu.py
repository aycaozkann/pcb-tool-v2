"""
uretim_zinciri_koprusu.py
==========================
Üç harici (KiCad-dışı) aracın köprü kodunu TEK dosyada toplar:
  1. FreeRouting   — otonom yönlendirme (routing)
  2. JLC2KiCadLib  — otonom kütüphane/footprint indirme
  3. KiBot         — üretim çıktıları (Gerber/BOM/CPL) paketleme

NEDEN BİRLEŞTİRİLDİ, NEDEN `kicad_koprusu.py` AYRI KALDI:
-----------------------------------------------------------
`kicad_koprusu.py` KiCad'in KENDİ resmi aracı olan `kicad-cli`'yi sarmalıyor
(DRC/ERC/net class — proje bunu zaten "kanonik entegrasyon yöntemi" ilan
etmişti). Bu üçü ise üçüncü parti, KiCad-dışı araçlar; aralarında ortak bir
tema var: hepsi "KiCad'in dosya formatını üret -> harici bir binary'yi
subprocess ile çalıştır -> sonucu geri KiCad'e ver" desenini tekrarlıyor.
Ayrı dosyalarda tutmanın gerçek bir mimari faydası yoktu (kodlar birbirini
çağırmıyor, her biri kendi başına bağımsız), bu yüzden tek dosyada toplandı.
İçerik BİREBİR korunmuştur — hiçbir fonksiyon/docstring eksiltilmedi.

ZİNCİRDEKİ SIRA (proje kurallarıyla ilişkisi):
------------------------------------------------
    1) JLC2KiCadLib  -> eksik footprint indirilir
                         (ÖN KOŞUL: MASTER_RULEBOOK Faz 1 yaşam-döngüsü
                         kontrolü + datasheet arşivi ÖNCE yapılmış olmalı)
    2) kicad_koprusu.net_classleri_projeye_yaz(...)
    3) FreeRouting   -> yollar otonom çizilir
    4) kicad_koprusu.drc_calistir(...) / erc_calistir(...) ile doğrula
    5) Temizse -> KiBot -> Gerber/BOM/CPL ZIP

DÜRÜSTLÜK NOTU: Bu ortamda hiçbiri (Java/FreeRouting, JLC2KiCadLib pip
paketi, KiBot) kurulu değil ve hiçbir fonksiyon gerçek bir dosyayla
çalıştırılmadı. Her bölümün kendi doğrulanmamış noktaları o bölümün
docstring'inde ayrı ayrı belirtilmiştir — bunlar gerçek KiCad 10 + gerçek
araç kurulumuyla SENİN makinende teyit edilmeli.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ====================================================================
# BÖLÜM 1 — FreeRouting (otonom yönlendirme)
# ====================================================================
#
# `SKILL (1).md` Faz 4'teki routing önceliği (önce GND, sonra kritik
# sinyal, sonra güç, en son I/O) FreeRouting'in KENDİSİ tarafından
# BİLİNMEZ — sadece "board outline + placement + netlist" (.dsn) alıp
# DRC kurallarına uyan BİR çözüm üretir. Bu yüzden önerilen kullanım:
# FreeRouting'i sadece düşük hızlı dijital I/O (Faz 4 Öncelik 5) için
# kullan; USB/MIPI gibi diferansiyel çiftleri elle/`Route Differential
# Pair` ile ayrı çiz, FreeRouting'e bırakma.
#
# 2026-07-31 GÜNCELLEMESİ (GÖREV 10, `DOCS/12_FreeRouting_Fizibilite.md`):
# Bu bölüm eskiden `kicad-cli`'nin DSN/SES desteklemediği (DOĞRU tespit)
# gerekçesiyle "kicad-cli DE mümkün değil, dolayısıyla pcbnew de kurulu
# olmadığı için mümkün değil" diye VARSAYIYORDU — bu varsayım YANLIŞTI.
# DOCS/12, bu makinede `pcbnew.ExportSpecctraDSN`/`pcbnew.ImportSpecctraSES`
# fonksiyonlarının GERÇEKTEN çalıştığını (sentetik + 2 gerçek KiCad demo
# board'unda) kanıtladı. Bu yüzden zincir artık `kicad-cli` YERİNE
# `arac_yollari.pcbnew_scripti_calistir()` ile KiCad'in gömülü Python'unu
# kullanarak DSN/SES'i GERÇEKTEN üretir/import eder — "kicad-cli'de yok"
# tespiti hâlâ doğrudur ama artık zincirin SONU değil, sadece "kicad-cli
# BU işi yapamaz, pcbnew YAPAR" notudur.
#
# DOĞRULANMADI (bu ortamda): gerçek bir proje board'unda (14-174+ net)
# uçtan-uca FreeRouting çalıştırması `DOCS/12` E1 bulgusuna göre 120-240sn
# içinde BİTMEYEBİLİR — bu yüzden Eylem 2/3 (240sn timeout + otonom
# fallback) BİLEREK eklendi.
#
# 2026-07-31 GERÇEK BULGU (bu makinede, ecc83-pp.kicad_pcb'nin gerçek DSN
# çıktısı FreeRouting 2.2.4'e verilerek KANITLANDI): FreeRouting sadece
# YAVAŞLAMIYOR — `app.freerouting.board.PolylineTrace.combine()` içinde
# SONSUZ ÖZYİNELEMeye girip **`java.lang.StackOverflowError`** ile
# ÇÖKEBİLİYOR. Bu çökme normalde ayrıca Java/Swing'in varsayılan
# istisna işleyicisi bir GUI hata penceresi açmaya ÇALIŞABİLİR — headless
# bir otonom akışta bu, subprocess'in "bitmesini" sonsuza kadar
# beklemesine (ekranda kimse olmadığı için popup'ın asla kapanmamasına)
# yol açabilir. Bu yüzden `freerouting_calistir()` ARTIK üç ek önlem
# alıyor: (1) `-Xss8m` (yığın boyutunu büyüt — bazı StackOverflow'ları
# önler ama HEPSİNİ önlemez, PolylineTrace.combine gibi GERÇEK bir sonsuz
# özyineleme yığın boyutundan BAĞIMSIZ olarak eninde sonunda taşar), (2)
# `-Djava.awt.headless=true` (JVM'in HİÇBİR GUI penceresi/hata diyaloğu
# AÇMAMASINI zorunlu kılar — headless modda AWT bir pencere açmaya
# çalışırsa `HeadlessException` fırlatır, sessizce asılı kalan bir pencere
# YERİNE), (3) stdout/stderr GERÇEK ZAMANLI satır satır TARANIR — bir
# "Exception"/"Error" deseni görülür görülmez süreç HEMEN `kill()` edilir,
# tam `zaman_asimi_sn` doluncaya kadar BEKLENMEZ.


class FreeRoutingDesteklenmiyorHatasi(NotImplementedError):
    """`pcbnew` (KiCad'in gömülü Python'u) bu makinede BULUNAMADIĞINDA
    fırlatılan ÖZEL istisna tipi — DSN/SES zincirinin KENDİSİ artık
    "desteklenmiyor" değildir (bkz. yukarıdaki 2026-07-31 notu), ama
    KiCad kurulu değilse/`KICAD_PYTHON` çözülemiyorsa zincir yine burada,
    fail-closed olarak durur.

    NEDEN AYRI BİR SINIF (çıplak `NotImplementedError` yerine): çağıran kod
    (CLAUDE.md akışı, bir orkestratör script'i) SADECE "bu kurulumda
    pcbnew/KiCad bulunamadı -> NEEDS_HUMAN/adımı atla" durumunu diğer,
    ilgisiz "henüz yazılmadı" hatalarından AYIRT EDEBİLMELİDİR — çıplak
    `except NotImplementedError` kullanmak, projedeki başka (alakasız)
    yer tutucu hataları da yanlışlıkla yakalayıp "FreeRouting sorunuydu"
    diye yanlış raporlayabilir.
    """


# Bu sabit artık "pcbnew tabanlı DSN/SES zinciri bu kurulumda prensipte
# kullanılabilir mi" anlamına gelir (ESKİ anlamı: "kicad-cli DSN
# destekliyor mu" — o soru hâlâ HAYIR, ama artık ALAKASIZ, çünkü zincir
# kicad-cli'yi DEĞİL pcbnew'i kullanıyor). `True` — DOCS/12'nin bu
# makinede kanıtladığı bulgu. Bir sonraki makinede pcbnew/KiCad kurulu
# değilse `dsn_disa_aktar()`/`ses_iceri_aktar()` YİNE DE kendi içlerinde
# `kicad_python_yolunu_bul()` ile fail-closed kontrol yapar — bu bayrak
# sadece erken/ucuz bir "prensipte mümkün mü" sinyalidir, tek başına
# güvenlik kapısı DEĞİLDİR.
KICAD10_DSN_DESTEKLENIYOR = True


@dataclass
class FreeRoutingSonucu:
    basarili: bool
    ses_dosya_yolu: str | None
    stdout: str
    stderr: str
    zaman_asimi_mi: bool = False
    java_hatasi_mi: bool = False


@dataclass
class DsnDisaAktarSonucu:
    basarili: bool
    dsn_yolu: str | None
    stdout: str
    stderr: str


@dataclass
class SesIceriAktarSonucu:
    basarili: bool
    iz_sayisi_once: int
    iz_sayisi_sonra: int
    izler_degisti: bool
    stdout: str
    stderr: str


# KiCad'in gömülü Python'unda (SWIG `pcbnew` modülü) çalıştırılacak,
# geçici bir dosyaya yazılıp `arac_yollari.pcbnew_scripti_calistir()` ile
# çağrılan minimal script şablonları. `sys.argv[1:]` üzerinden board/dsn/
# ses yollarını alırlar; stdout'a tek satır JSON basarlar (ayrı bir sonuç
# dosyasına ihtiyaç yok, `subprocess.run(capture_output=True)` yeterli).
_DSN_EXPORT_SCRIPT = """
import json, sys
import pcbnew

board_path, dsn_path = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(board_path)
ok = bool(pcbnew.ExportSpecctraDSN(board, dsn_path))
print(json.dumps({"basarili": ok}))
sys.exit(0 if ok else 2)
"""

_SES_IMPORT_SCRIPT = """
import json, sys
import pcbnew

board_path, ses_path = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(board_path)
iz_once = len([t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"])
ok = bool(pcbnew.ImportSpecctraSES(board, ses_path))
iz_sonra = len([t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"])
if ok:
    board.Save(board_path)
print(json.dumps({
    "basarili": ok, "iz_sayisi_once": iz_once, "iz_sayisi_sonra": iz_sonra,
    "izler_degisti": iz_sonra != iz_once,
}))
sys.exit(0 if ok else 2)
"""


def _pcbnew_script_calistir(
    script_metni: str, argv: list[str], kicad_python: Optional[str] = None, zaman_asimi_s: int = 60,
) -> subprocess.CompletedProcess:
    """`_DSN_EXPORT_SCRIPT`/`_SES_IMPORT_SCRIPT` gibi bir script metnini
    geçici bir `.py` dosyasına yazıp `arac_yollari.pcbnew_scripti_calistir()`
    ile KiCad'in gömülü Python'unda çalıştırır. Geçici dosya çağrı bitince
    silinir (`TemporaryDirectory` — Windows dosya kilidi riskini `KURULUM.md`
    /`CLAUDE.md`'deki "yazdıktan hemen sonra silme/commit" riskiyle
    KARIŞTIRMA: burada sadece OKUNAN bir script dosyası, board dosyası
    DEĞİL)."""
    import tempfile

    from arac_yollari import pcbnew_scripti_calistir

    with tempfile.TemporaryDirectory() as tmp:
        script_path = str(Path(tmp) / "_pcbnew_gecici_script.py")
        Path(script_path).write_text(script_metni, encoding="utf-8")
        return pcbnew_scripti_calistir(script_path, argv, kicad_python=kicad_python, timeout_s=zaman_asimi_s)


def _pcbnew_bulunamadi_hatasi(baglam: str, hata: Exception) -> "FreeRoutingDesteklenmiyorHatasi":
    return FreeRoutingDesteklenmiyorHatasi(
        f"{baglam}: pcbnew (KiCad gömülü Python) bulunamadı: {hata}. "
        "DSN/SES zinciri pcbnew Python API'si gerektirir (kicad-cli'de bu "
        "yok, bkz. DOCS/12_FreeRouting_Fizibilite.md). NEEDS_HUMAN: KiCad "
        "kurulumu doğrulanmalı veya KICAD_PYTHON ortam değişkeni "
        "'<kurulum>/bin/python.exe' yoluna ayarlanmalı."
    )


def dsn_disa_aktar(
    board_path: str, dsn_cikti_path: str, kicad_python: Optional[str] = None,
    zaman_asimi_s: int = 60,
) -> DsnDisaAktarSonucu:
    """PCB dosyasını FreeRouting'in okuyabileceği .dsn formatına aktarır —
    ARTIK GERÇEK BİR UYGULAMA (2026-07-31, GÖREV 10): `kicad-cli pcb export`
    hâlâ DSN desteklemiyor (bu tespit DOĞRUYDU ve KORUNUYOR), ama
    `pcbnew.ExportSpecctraDSN()` KiCad 10.0.4'ün gömülü Python'unda
    ÇALIŞIYOR — bu makinede sentetik board + 2 gerçek KiCad demo board'unda
    (`ecc83-pp.kicad_pcb`, `interf_u.kicad_pcb`) doğrulandı (bkz.
    `DOCS/12_FreeRouting_Fizibilite.md`).

    `pcbnew` bu makinede bulunamazsa (`kicad_python_yolunu_bul()` başarısız
    olursa) fail-closed: `FreeRoutingDesteklenmiyorHatasi` fırlatılır —
    "belki çalışır" diye SESSİZCE varsayılmaz.
    """
    from arac_yollari import kicad_python_yolunu_bul

    try:
        kicad_python_yolunu_bul(kicad_python)
    except FileNotFoundError as hata:
        raise _pcbnew_bulunamadi_hatasi("dsn_disa_aktar", hata) from hata

    try:
        sonuc = _pcbnew_script_calistir(
            _DSN_EXPORT_SCRIPT, [board_path, dsn_cikti_path],
            kicad_python=kicad_python, zaman_asimi_s=zaman_asimi_s,
        )
    except subprocess.TimeoutExpired as hata:
        return DsnDisaAktarSonucu(
            False, None, hata.stdout or "", f"DSN export {zaman_asimi_s}sn içinde bitmedi (timeout)."
        )

    basarili = sonuc.returncode == 0 and Path(dsn_cikti_path).exists()
    return DsnDisaAktarSonucu(basarili, dsn_cikti_path if basarili else None, sonuc.stdout, sonuc.stderr)


_JAVA_HATA_DESENLERI = ("Exception", "Error:", "StackOverflowError", "OutOfMemoryError")


def freerouting_calistir(
    dsn_path: str,
    ses_cikti_path: str,
    freerouting_jar: str = "freerouting.jar",
    ek_ayarlar: list[str] | None = None,
    zaman_asimi_sn: int = 240,
    java_yigin_boyutu: str = "8m",
) -> FreeRoutingSonucu:
    """Headless FreeRouting'i çalıştırıp .ses (session/routing sonucu) üretir.

    2026-07-31 GÜNCELLEMESİ (GÖREV 10, DOCS/12 E1 bulgusu): varsayılan
    zaman aşımı 1800sn'den **240sn**'ye düşürüldü. DOCS/12'de gerçek
    KiCad demo board'ları (14 ve 174 net) FreeRouting 2.2.4 ile 120-240sn
    içinde BİTMEDİ — otonom bir zincirin tek bir routing adımında
    dakikalarca (yarım saat) kilitlenmesi kabul edilemez; 240sn üstünü
    beklemek yerine `freerouting_zinciri_calistir()` bu durumda
    `otonom_kurtarma_motoru`'na devreder (bkz. o fonksiyonun docstring'i).
    Küçük/basit kartlar için `zaman_asimi_sn` parametresiyle override
    edilebilir.

    2026-07-31 GERÇEK BULGU + 3 DÜZELTME (bu makinede, `ecc83-pp.kicad_pcb`
    DSN'i FreeRouting 2.2.4'e verilerek KANITLANDI — `app.freerouting.board.
    PolylineTrace.combine()` sonsuz özyinelemeye girip `java.lang.
    StackOverflowError` fırlattı):
      1. `-Xss{java_yigin_boyutu}` — JVM yığın (stack) boyutunu büyütür.
         NOT: bu, TÜM StackOverflowError'ları ÖNLEMEZ — `PolylineTrace.
         combine` gibi GERÇEK bir sonsuz özyineleme, yığın boyutundan
         BAĞIMSIZ olarak eninde sonunda taşar; bu yüzden 2 ve 3 numaralı
         önlemler ZORUNLU, sadece yığın büyütmek YETERSİZ.
      2. `-Djava.awt.headless=true` — JVM'in bir istisna/çökme anında bile
         HİÇBİR GUI penceresi/hata diyaloğu AÇMAMASINI zorunlu kılar.
         Headless modda AWT bir pencere açmaya çalışırsa sessizce asılı
         kalan bir Windows popup'ı YERİNE `HeadlessException` fırlatır —
         otonom akışın ekranda kimse yokken sonsuza kadar bir diyalog
         kapanmasını beklemesi bu şekilde yapısal olarak engellenir.
      3. **Fail-fast satır taraması:** stdout/stderr `subprocess.run()`'ın
         tüm çıktıyı BEKLEDİĞİ `capture_output` modeli YERİNE, `Popen` ile
         GERÇEK ZAMANLI satır satır okunur; `_JAVA_HATA_DESENLERI`'nden
         biri görülür görülmez süreç HEMEN `kill()` edilir — tam
         `zaman_asimi_sn` doluncaya kadar BEKLENMEZ. Sonuçta
         `java_hatasi_mi=True` döner; `freerouting_zinciri_calistir()`
         bunu `zaman_asimi_mi` ile AYNI şekilde ele alıp `otonom_kurtarma_
         motoru`'na hemen devreder (bkz. o fonksiyonun docstring'i).
    """
    komut = [
        "java", f"-Xss{java_yigin_boyutu}", "-Djava.awt.headless=true",
        "-jar", freerouting_jar, "-de", dsn_path, "-do", ses_cikti_path,
    ]
    if ek_ayarlar:
        komut.extend(ek_ayarlar)

    baslangic = time.monotonic()
    satirlar: list[str] = []
    java_hatasi: str | None = None

    proc = subprocess.Popen(
        komut, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    try:
        while True:
            kalan = zaman_asimi_sn - (time.monotonic() - baslangic)
            if kalan <= 0:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                return FreeRoutingSonucu(
                    basarili=False, ses_dosya_yolu=None, stdout="\n".join(satirlar),
                    stderr=f"FreeRouting {zaman_asimi_sn}sn içinde bitmedi (timeout).",
                    zaman_asimi_mi=True,
                )
            satir = proc.stdout.readline() if proc.stdout else ""
            if satir == "":
                if proc.poll() is not None:
                    break
                continue
            satir = satir.rstrip("\n")
            satirlar.append(satir)
            if any(desen in satir for desen in _JAVA_HATA_DESENLERI):
                java_hatasi = satir.strip()
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                break
    finally:
        if proc.poll() is None:
            proc.kill()

    stdout_birlesik = "\n".join(satirlar)

    if java_hatasi:
        return FreeRoutingSonucu(
            basarili=False, ses_dosya_yolu=None, stdout=stdout_birlesik,
            stderr=f"FreeRouting bir Java istisnası fırlattı, süreç HEMEN sonlandırıldı "
                   f"(zaman aşımı beklenmedi): {java_hatasi}",
            java_hatasi_mi=True,
        )

    ses_var_mi = Path(ses_cikti_path).exists()
    return FreeRoutingSonucu(
        basarili=(proc.returncode == 0 and ses_var_mi),
        ses_dosya_yolu=ses_cikti_path if ses_var_mi else None,
        stdout=stdout_birlesik,
        stderr="" if proc.returncode == 0 else f"FreeRouting exit={proc.returncode}",
    )


def ses_iceri_aktar(
    board_path: str, ses_path: str, kicad_python: Optional[str] = None,
    zaman_asimi_s: int = 60,
) -> SesIceriAktarSonucu:
    """.ses routing sonucunu geri PCB dosyasına import eder — ARTIK GERÇEK
    BİR UYGULAMA (2026-07-31, GÖREV 10): `kicad-cli pcb import` hâlâ
    Specctra Session (.ses) desteklemiyor (bu tespit DOĞRUYDU ve
    KORUNUYOR), ama `pcbnew.ImportSpecctraSES()` KiCad 10.0.4'ün gömülü
    Python'unda ÇALIŞIYOR (bkz. `DOCS/12_FreeRouting_Fizibilite.md`).

    DOCS/12 E2 UYARISI kod karşılığı: `ImportSpecctraSES`'in dönüş
    değerine KÖRÜ KÖRÜNE güvenilmez (gerçek routes'lu bir .ses, padstack
    eşleşmesi tutmazsa `False` dönebiliyor VEYA sessizce 0 iz ekleyebiliyor).
    Bu yüzden bu fonksiyon import ÖNCESİ/SONRASI `board.GetTracks()`
    sayısını KARŞILAŞTIRIR ve `izler_degisti` alanında döner — çağıran
    taraf `basarili is True` VE `izler_degisti is True` ikisini de kontrol
    etmeden "routing tamamlandı" SAYMAMALIDIR.

    `pcbnew` bulunamazsa fail-closed: `FreeRoutingDesteklenmiyorHatasi`.
    """
    from arac_yollari import kicad_python_yolunu_bul

    try:
        kicad_python_yolunu_bul(kicad_python)
    except FileNotFoundError as hata:
        raise _pcbnew_bulunamadi_hatasi("ses_iceri_aktar", hata) from hata

    try:
        sonuc = _pcbnew_script_calistir(
            _SES_IMPORT_SCRIPT, [board_path, ses_path],
            kicad_python=kicad_python, zaman_asimi_s=zaman_asimi_s,
        )
    except subprocess.TimeoutExpired as hata:
        return SesIceriAktarSonucu(False, 0, 0, False, hata.stdout or "", f"SES import {zaman_asimi_s}sn içinde bitmedi (timeout).")

    try:
        veri = json.loads((sonuc.stdout or "").strip().splitlines()[-1]) if sonuc.stdout else {}
    except (json.JSONDecodeError, IndexError):
        veri = {}

    return SesIceriAktarSonucu(
        basarili=bool(veri.get("basarili", False)),
        iz_sayisi_once=int(veri.get("iz_sayisi_once", 0)),
        iz_sayisi_sonra=int(veri.get("iz_sayisi_sonra", 0)),
        izler_degisti=bool(veri.get("izler_degisti", False)),
        stdout=sonuc.stdout, stderr=sonuc.stderr,
    )


def freerouting_zinciri_calistir(
    board_path: str,
    calisma_dizini: str = ".",
    kicad_python: Optional[str] = None,
    freerouting_jar: str = "freerouting.jar",
    otonom_fallback: bool = True,
) -> FreeRoutingSonucu:
    """dsn export (pcbnew) -> freerouting -> ses import (pcbnew) uçtan uca
    zincir — 2026-07-31 GÜNCELLEMESİ (GÖREV 10): artık GERÇEKTEN pcbnew
    tabanlı DSN/SES kullanıyor (bkz. `dsn_disa_aktar`/`ses_iceri_aktar`
    docstring'leri). `KICAD10_DSN_DESTEKLENIYOR` bayrağı hâlâ SAVUNMA
    DERİNLİĞİ kapısı olarak kontrol edilir — `False` yapılırsa (ör. gelecekte
    bir regresyon/bilinçli devre dışı bırakma) zincir yine
    `FreeRoutingDesteklenmiyorHatasi` ile en tepede durur.

    **240sn TIMEOUT + OTONOM FALLBACK (Eylem 2/3):** `freerouting_calistir()`
    zaman aşımına uğrarsa (DOCS/12 E1: gerçek kartlarda olası), zincir
    NEEDS_HUMAN ile DURMAZ — `otonom_fallback=True` (varsayılan) iken
    `freerouting_zaman_asiminda_otonom_devam_et()` çağrılır: bu, board'daki
    HÂLÂ bağlanmamış netleri `kicad_koprusu.drc_calistir()`'in
    `unconnected_items` listesinden çıkarıp her birini
    `otonom_kurtarma_motoru.otonom_routing_merdiveni()` (akıllı yol / bölümlü
    yol / ızgara A* üç katmanı) ile TEK TEK yönlendirmeyi dener — iki
    BAĞIMSIZ router'ın İKİSİ DE başarısız olmadan akış durmaz. Bu geçiş
    `TEST/kararlar_logu.md`'ye kaydedilir (GÖREV 2'nin audit-log ilkesiyle
    tutarlı, ama GÖREV 2 henüz uygulanmadığı için burada minimal/bağımsız
    bir append kullanılıyor).

    Zincirin sonunda YİNE DE MUTLAKA `kicad_koprusu.drc_calistir` çağrılıp
    `drc_temiz_mi` ile doğrulanmalı — bu fonksiyon o adımı YAPMAZ.
    """
    if not KICAD10_DSN_DESTEKLENIYOR:
        raise FreeRoutingDesteklenmiyorHatasi(
            "freerouting_zinciri_calistir(): KICAD10_DSN_DESTEKLENIYOR=False — "
            "DSN/SES zinciri bilinçli olarak devre dışı bırakılmış. "
            "dsn_disa_aktar()/freerouting_calistir()'e HİÇ ULAŞILMADI. Çağıran "
            "taraf bu adımı NEEDS_HUMAN olarak işaretleyip düşük hızlı I/O "
            "routing'ini pcb-layout Faz 4 manuel yöntemleriyle veya "
            "topolojik_router_koprusu.py::akilli_yol_bul() ile yapmalı."
        )

    calisma = Path(calisma_dizini)
    calisma.mkdir(parents=True, exist_ok=True)
    dsn_path = str(calisma / "board.dsn")
    ses_path = str(calisma / "board.ses")

    dsn_sonuc = dsn_disa_aktar(board_path, dsn_path, kicad_python=kicad_python)
    if not dsn_sonuc.basarili:
        return FreeRoutingSonucu(False, None, dsn_sonuc.stdout, f"DSN export başarısız: {dsn_sonuc.stderr}")

    sonuc = freerouting_calistir(dsn_path, ses_path, freerouting_jar=freerouting_jar)

    if (sonuc.zaman_asimi_mi or sonuc.java_hatasi_mi) and otonom_fallback:
        neden = "zaman aşımına uğradı (240sn)" if sonuc.zaman_asimi_mi else \
            f"bir Java istisnasıyla çöktü ({sonuc.stderr})"
        _kararlar_logu_yaz(
            calisma_dizini,
            f"FreeRouting {board_path} için {neden} — "
            "OTONOM KARAR: otonom_kurtarma_motoru.otonom_routing_merdiveni() "
            "ile kalan netler tek tek yönlendirilmeye devam ediliyor.",
        )
        fallback_sonuc = freerouting_zaman_asiminda_otonom_devam_et(
            board_path, kicad_python=kicad_python, calisma_dizini=calisma_dizini,
        )
        return FreeRoutingSonucu(
            basarili=fallback_sonuc["basarisiz_net_sayisi"] == 0,
            ses_dosya_yolu=None,
            stdout=json.dumps(fallback_sonuc),
            stderr=sonuc.stderr,
            zaman_asimi_mi=sonuc.zaman_asimi_mi,
            java_hatasi_mi=sonuc.java_hatasi_mi,
        )

    if sonuc.basarili:
        ses_sonuc = ses_iceri_aktar(board_path, ses_path, kicad_python=kicad_python)
        if not ses_sonuc.basarili or not ses_sonuc.izler_degisti:
            # DOCS/12 E2: dönüş değeri True olsa bile iz sayısı değişmediyse
            # (padstack eşleşmedi) bunu SESSİZCE "routing tamamlandı" SAYMA.
            return FreeRoutingSonucu(
                False, ses_path,
                f"SES import: basarili={ses_sonuc.basarili} izler_degisti={ses_sonuc.izler_degisti}",
                ses_sonuc.stderr,
            )

    return sonuc


def _kararlar_logu_yaz(calisma_dizini: str, mesaj: str) -> None:
    """`TEST/kararlar_logu.md`'ye zaman damgalı bir satır ekler. GÖREV 2
    (routing_plan onayını audit-log modeline çevirme) henüz uygulanmadığı
    için bu, o infrastrüktürün TAM karşılığı değil — minimal, bağımsız bir
    append. GÖREV 2 uygulandığında bu çağrı o modülün resmi API'sine
    taşınmalı."""
    test_dizini = Path(calisma_dizini) / "TEST"
    test_dizini.mkdir(parents=True, exist_ok=True)
    zaman = datetime.now(timezone.utc).isoformat()
    with open(test_dizini / "kararlar_logu.md", "a", encoding="utf-8") as f:
        f.write(f"- [{zaman}] {mesaj}\n")


def _pcbnew_footprint_engelleri_cikar(
    board_path: str, kicad_python: Optional[str] = None, zaman_asimi_s: int = 60,
) -> List["Engel"]:
    """`pcb_carpisma_radari.komponent_sinir_kutularini_al()`'ı KiCad'in
    gömülü Python'unda çalıştırıp TÜM footprint sınır kutularını
    `topolojik_router_koprusu.Engel` listesine çevirir — otonom fallback
    router'ının kaçınması gereken engel adayları budur.

    AĞ/ARAÇ UYARISI (`pcbnew_koprusu.py` ile AYNI disiplin): bu fonksiyon
    gerçek `pcbnew` + gerçek bir `.kicad_pcb` gerektirir; bu ortamda
    SADECE `_pcbnew_script_calistir` çağrısının kendisi (KiCad Python'unun
    varlığı) doğrulandı — gerçek bir proje board'una karşı SENİN
    makinende ayrıca doğrulanmalı."""
    from topolojik_router_koprusu import Engel

    script = """
import json, sys
sys.path.insert(0, r"%s")
import pcbnew
from pcb_carpisma_radari import komponent_sinir_kutularini_al

board = pcbnew.LoadBoard(sys.argv[1])
kutular = komponent_sinir_kutularini_al(board)
print(json.dumps({
    ref: {"x_min": k.x_min, "y_min": k.y_min, "x_max": k.x_max, "y_max": k.y_max}
    for ref, k in kutular.items()
}))
""" % str(Path(__file__).resolve().parent)

    sonuc = _pcbnew_script_calistir(script, [board_path], kicad_python=kicad_python, zaman_asimi_s=zaman_asimi_s)
    try:
        veri = json.loads((sonuc.stdout or "").strip().splitlines()[-1]) if sonuc.stdout else {}
    except (json.JSONDecodeError, IndexError):
        veri = {}
    return [
        Engel(isim=ref, x_min=k["x_min"], y_min=k["y_min"], x_max=k["x_max"], y_max=k["y_max"], clearance_mm=0.2)
        for ref, k in veri.items()
    ]


def _drc_unconnected_net_gruplari(rapor: Dict) -> Dict[str, List[Tuple[float, float]]]:
    """`kicad_koprusu.drc_calistir()`'in ürettiği rapordaki
    `unconnected_items` girdilerini net ismine göre gruplar, her girdinin
    `items[].pos` konumlarını toplar. Net başına en az 2 konum yoksa
    (tek uçlu/okunamayan girdi) o net YOL İSTEĞİNE dönüştürülemez — bu
    fonksiyon böyle netleri sessizce ATLAR, çağıran taraf toplam
    `unconnected_items` sayısıyla üretilen `YolIstegi` sayısını
    karşılaştırıp farkı raporlamalıdır."""
    gruplar: Dict[str, List[Tuple[float, float]]] = {}
    for ihlal in rapor.get("unconnected_items", []):
        net = ihlal.get("net_name") or ihlal.get("description", "BILINMEYEN_NET")
        for item in ihlal.get("items", []):
            pos = item.get("pos")
            if pos and "x" in pos and "y" in pos:
                gruplar.setdefault(net, []).append((float(pos["x"]), float(pos["y"])))
    return gruplar


def freerouting_zaman_asiminda_otonom_devam_et(
    board_path: str, kicad_python: Optional[str] = None, calisma_dizini: str = ".",
    genislik_mm: float = 0.2,
) -> Dict:
    """FreeRouting 240sn'de bitmediğinde çağrılan OTONOM FALLBACK (Eylem 3):
    board'daki HÂLÂ bağlanmamış netleri `kicad_koprusu.drc_calistir()` +
    `unconnected_items`'tan çıkarır (ratsnest için doğrulanmamış bir pcbnew
    API'sine güvenmek yerine, bu projenin ZATEN gerçek bir board'da
    doğrulanmış olan DRC/`unconnected_items` yolunu YENİDEN KULLANIR —
    bkz. `kicad_koprusu.py::_drc_tum_ihlaller` docstring'i), sonra HER net
    için `otonom_kurtarma_motoru.otonom_routing_merdiveni()`'ni dener.

    NOT (GÖREV 3 bağımlılığı, dürüstlük notu): GÖREV 3 henüz uygulanmadığı
    için `hata_hafizasi.Sonuc.OTONOM_KARAR` enum değeri YOK — başarısız
    netler burada `TEST/needs_human_<net>.json` dosyasına yazılır ve
    mevcut `Sonuc.NEEDS_HUMAN` sözleşmesiyle raporlanır. GÖREV 3
    uygulandığında bu çağrı `OTONOM_KARAR`'a YÜKSELTİLMELİDİR — akış o
    zaman bile durmaz, sadece kayıt türü değişir.

    Döner: `{"toplam_net": int, "yonlendirilen_net": int,
    "basarisiz_net_sayisi": int, "detaylar": [...]}`."""
    from kicad_koprusu import drc_calistir
    from otonom_kurtarma_motoru import otonom_routing_merdiveni
    from topolojik_router_koprusu import YolIstegi

    rapor = drc_calistir(board_path, rapor_path=str(Path(calisma_dizini) / "drc_fallback.json"))
    net_gruplari = _drc_unconnected_net_gruplari(rapor)
    engeller = _pcbnew_footprint_engelleri_cikar(board_path, kicad_python=kicad_python)

    detaylar: List[Dict] = []
    basarisiz = 0
    for net, konumlar in net_gruplari.items():
        if len(konumlar) < 2:
            detaylar.append({"net": net, "durum": "ATLANDI", "neden": "tek uçlu/konumsuz girdi"})
            continue
        istek = YolIstegi(baslangic=konumlar[0], bitis=konumlar[1], net=net, iz_genisligi_mm=genislik_mm)
        merdiven = otonom_routing_merdiveni(istek, engeller, board_path, genislik_mm)
        if merdiven.basarili:
            detaylar.append({"net": net, "durum": "YONLENDIRILDI", "basamak": merdiven.basamak})
        else:
            basarisiz += 1
            detaylar.append({"net": net, "durum": "NEEDS_HUMAN", "notlar": merdiven.tum_notlar})
            needs_human_dizini = Path(calisma_dizini) / "TEST"
            needs_human_dizini.mkdir(parents=True, exist_ok=True)
            (needs_human_dizini / f"needs_human_{net.replace('/', '_')}.json").write_text(
                json.dumps({"net": net, "sonuc": "NEEDS_HUMAN", "notlar": merdiven.tum_notlar}, indent=2),
                encoding="utf-8",
            )

    return {
        "toplam_net": len(net_gruplari),
        "yonlendirilen_net": len(net_gruplari) - basarisiz,
        "basarisiz_net_sayisi": basarisiz,
        "detaylar": detaylar,
    }


# ====================================================================
# BÖLÜM 2 — JLC2KiCadLib (otonom kütüphane/footprint yönetimi)
# ====================================================================
#
# MASTER_RULEBOOK Faz 1 İLE İLİŞKİSİ (kritik sıralama):
# JLC2KiCadLib verdiğin LCSC kodunun yaşam-döngüsü/stok durumunu KONTROL
# ETMEZ — sadece indirir. Sıra: (1) yaşam döngüsü + stok kontrolü ve
# kullanıcıya raporlama, (2) datasheet'i DATASHEETS/ klasörüne kaydet,
# (3) ancak ondan SONRA bu bölümdeki `jlc_parcasi_indir()` çağrılır. Bu
# sırayı atlamak Faz 1 kuralını sessizce atlamak anlamına gelir.
#
# DOĞRULANMADI: JLC2KiCadLib bu ortamda hiç çalıştırılmadı; CLI bayrakları
# (`-dir`, `-symbol_lib` vb.) paketin güncel GitHub README'sine göre teyit
# edilmeli — sürüm değiştikçe bayrak isimleri değişmiş bir araç.

@dataclass
class JlcIndirmeSonucu:
    basarili: bool
    lcsc_kodu: str
    hedef_dizin: str
    stdout: str
    stderr: str


def jlc_parcasi_indir(
    lcsc_kodu: str,
    hedef_dizin: str = "./lib",
    symbol_lib_adi: str = "JLC2KiCad_lib",
) -> JlcIndirmeSonucu:
    """Bir LCSC parça kodu (örn. 'C12345') için sembol/footprint/3D model indirir.

    ÖN KOŞUL (atlanmamalı): bu çağrıdan önce MASTER_RULEBOOK Faz 1 yaşam
    döngüsü kontrolü ve datasheet arşivleme adımı TAMAMLANMIŞ olmalı.
    """
    komut = [
        "python", "-m", "JLC2KiCadLib",
        "-dir", hedef_dizin,
        "-symbol_lib", symbol_lib_adi,
        lcsc_kodu,
    ]
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    return JlcIndirmeSonucu(
        basarili=(sonuc.returncode == 0),
        lcsc_kodu=lcsc_kodu,
        hedef_dizin=hedef_dizin,
        stdout=sonuc.stdout,
        stderr=sonuc.stderr,
    )


def kutuphanede_var_mi(mpn_veya_lib_id: str, sym_lib_table_path: str = "sym-lib-table") -> bool:
    """Kaba bir metin araması ile parçanın zaten kütüphanede olup olmadığını kontrol eder.

    Asıl doğrulama KiCad'in kendi "Symbol not found" hatasıdır — bu sadece
    gereksiz bir indirmeyi baştan engellemek için bir ön-filtre.
    """
    try:
        with open(sym_lib_table_path, "r", encoding="utf-8") as f:
            icerik = f.read()
    except FileNotFoundError:
        return False
    return mpn_veya_lib_id.lower() in icerik.lower()


# ====================================================================
# BÖLÜM 3 — KiBot (üretim çıktıları / DFM paketleme)
# ====================================================================
#
# MASTER_RULEBOOK Faz 8'in son adımıdır. KiBot, board/schematic'in
# DRC/ERC durumuna BAKMADAN çıktı üretir — "0 hata" garantisi KiBot'un
# işi değil. `kibot_calistir()` çağrılmadan HEMEN ÖNCE:
#
#     drc_raporu = kicad_koprusu.drc_calistir(board_path)
#     erc_raporu = kicad_koprusu.erc_calistir(schematic_path)
#     if not (kicad_koprusu.drc_temiz_mi(drc_raporu)
#             and kicad_koprusu.erc_temiz_mi(erc_raporu)):
#         ...  # KiBot'u ÇAĞIRMA, hata düzeltme döngüsüne dön
#
# bu kapı kontrolü elle kurulmalı — bu fonksiyon onu varsaymaz.
#
# DOĞRULANMADI: KiBot bu ortamda hiç çalıştırılmadı. Aşağıdaki
# `KIBOT_ORNEK_YAML`, KiBot'un genel/dokümante edilen şemasına göre
# yazıldı ama kurulu sürümle (`kibot --help-outputs`) teyit edilmeden
# production'da güvenilmemeli; `layers`/`pcb_material` gibi stackup'a
# özgü alanlar `pcb_stackup_planner.py`'nin ürettiği gerçek katman
# sırasına göre elle senkronize edilmeli.

KIBOT_ORNEK_YAML = """\
kibot:
  version: '1'

outputs:
  - name: 'gerbers'
    comment: 'Üretim için Gerber dosyaları'
    type: gerber
    dir: 'uretim/gerbers'
    layers: 'all'

  - name: 'drill'
    comment: 'Delgi dosyaları'
    type: excellon
    dir: 'uretim/gerbers'

  - name: 'position'
    comment: 'Pick & Place (CPL/POS)'
    type: position
    dir: 'uretim/pnp'
    options:
      format: CSV
      units: millimeters

  - name: 'bom'
    comment: 'İnsan-okunabilir BOM'
    type: bom
    dir: 'uretim/bom'
    options:
      format: XLSX

  - name: 'render_3d'
    comment: 'Kartın 3D render görseli'
    type: render_3d
    dir: 'uretim/render'

  - name: 'uretim_zip'
    comment: 'Tüm çıktıları tek ZIP olarak paketle'
    type: compress
    dir: 'uretim'
    options:
      files:
        - from_output: gerbers
        - from_output: drill
        - from_output: position
        - from_output: bom
"""


# ====================================================================
# BÖLÜM 4 — JLCPCB DFM API (Gerber'i üreticiye erken göndererek doğrulama)
# ====================================================================
#
# ÖNEMLİ — DÜRÜSTLÜK NOTU (diğer bölümlerden daha da temkinli olunmalı):
# KiBot'un/kicad-cli'nin ürettiği Gerber+BOM, MASTER_RULEBOOK Faz 8'in
# gerektirdiği yerel (offline) DFM kontrolünden (`pcb_stackup_planner.py::
# fabrika_dfm_kontrolu()`) geçse bile, bu SADECE bilinen/gömülü sınırlarla
# (min iz genişliği vb.) bir karşılaştırmadır — üreticinin GERÇEK ZAMANLI
# DFM motorunun (delik-pad hizası, solder mask köprüsü, silkscreen-pad
# çakışması gibi geometrik detaylar) yakalayacağı bir sınıf hatayı YAKALAMAZ.
#
# JLCPCB'nin bir web tabanlı DFM aracı (jlcdfm.com) var, ama bunun genel
# erişimli, API-anahtarıyla doğrudan çağrılabilir, dokümante edilmiş bir
# JSON endpoint'i olduğu DOĞRULANAMADI — JLCPCB'nin resmi "Online API"si
# (PCB/SMT/3D-Printing/Parts API) başvuru/onay gerektiren, öncelikle
# FİYATLANDIRMA ve SİPARİŞ akışına yönelik bir API gibi görünüyor; DFM'e
# özel, bağımsız bir "sadece analiz, sipariş yok" endpoint'i olup olmadığı
# senin JLCPCB geliştirici hesabından TEYİT EDİLMELİ.
#
# Bu yüzden aşağıdaki fonksiyon bilerek bir İSKELET + YER TUTUCUDUR — gerçek
# endpoint URL'si, kimlik doğrulama yöntemi (muhtemelen API key + HMAC imza)
# ve dönen JSON şeması SENİN JLCPCB API başvurun onaylandıktan sonra
# `docs.jlcpcb.com` (veya sağlanan resmi API dokümantasyonu) okunarak
# doldurulmalı. O ana kadar bu adım MASTER_RULEBOOK Faz 8'deki checklist'e
# ek bir güvence katmanı olarak DEĞİL, sadece bir yer tutucu olarak durur.

@dataclass
class DfmApiSonucu:
    basarili: bool
    ham_yanit: Dict
    kritik_uyari_sayisi: int
    uyarilar: List[str]


def jlcpcb_dfm_kontrolu_gonder(
    gerber_zip_path: str,
    api_anahtari: str,
    endpoint_url: str = "https://api.jlcpcb.com/dfm/v1/analyze",  # DOĞRULANMADI
) -> DfmApiSonucu:
    """Gerber ZIP'ini JLCPCB'nin DFM analiz servisine gönderip JSON sonucu döndürür.

    DOĞRULANMADI (bilerek): `endpoint_url`, kimlik doğrulama şeması ve yanıt
    JSON'ının alan adları (`warnings`, `critical_count` vb. burada TAHMİNİ
    isimlerdir) — bunların hiçbiri JLCPCB'nin resmi, herkese açık bir
    dokümantasyonundan doğrulanmadı. Bu fonksiyonu gerçek kullanıma almadan
    önce:
      1. JLCPCB Online API başvurunu yap (jlcpcb.com/help/article/
         jlcpcb-online-api-available-now).
      2. Onaylanan hesabınla gelen resmi API dokümantasyonundaki gerçek
         endpoint/kimlik doğrulama/şemayı buraya işle.
      3. Şema doğrulanana kadar bu fonksiyonu ÇAĞIRMA — MASTER_RULEBOOK
         Faz 8'in "DRC ve ERC sıfır hata" kapısı hâlâ tek güvenilir kapıdır;
         bu fonksiyon o kapının YERİNE geçmez, sadece EK bir kontrol katmanı
         olması PLANLANMIŞTIR.
    """
    raise NotImplementedError(
        "JLCPCB DFM API entegrasyonu doğrulanmadı — endpoint/kimlik "
        "doğrulama/yanıt şeması gerçek API dokümantasyonuyla teyit edilip "
        "bu fonksiyon doldurulmadan çağrılmamalı. Alternatif: Faz 8'deki "
        "yerel `fabrika_dfm_kontrolu()` (pcb_stackup_planner.py) ve/veya "
        "jlcdfm.com'a Gerber'i elle yükleyip sonucu okuma."
    )


def dfm_uyarilarini_degerlendir(sonuc: DfmApiSonucu) -> bool:
    """DFM API sonucunun üretime devam için yeterince temiz olup olmadığını değerlendirir.

    `sonuc.kritik_uyari_sayisi == 0` ise True — bu fonksiyon `sonuc`'u
    üretmez, sadece değerlendirir; gerçek API entegrasyonu tamamlanmadan
    (yukarıdaki NotImplementedError kaldırılmadan) anlamlı bir girdi almaz.
    """
    return sonuc.basarili and sonuc.kritik_uyari_sayisi == 0


@dataclass
class KiBotSonucu:
    """DÜZELTME (2026-07-30, kontrat kapıları eklenirken bulundu): bu sınıfın
    `@dataclass class KiBotSonucu:` başlığı EKSİKTİ — dört alan (`basarili`
    vb.) modül seviyesinde YALIN tip-ipucu satırı olarak duruyordu. Dosyanın
    başındaki `from __future__ import annotations` sayesinde `-> KiBotSonucu`
    dönüş tipi import anında patlamıyordu (string olarak erteleniyor) ama
    `kibot_calistir()` GERÇEKTEN çağrıldığında `KiBotSonucu(...)` satırı
    `NameError` fırlatırdı — sessiz bir çalışma-zamanı hatasıydı, hiçbir
    testte yakalanmamıştı (KiBot bu ortamda hiç koşturulmadığı için)."""

    basarili: bool
    cikti_dizini: str
    stdout: str
    stderr: str


def kibot_config_yaz(hedef_yol: str = "kibot.yaml") -> str:
    """Örnek KiBot config'ini diske yazar (elle stackup'a göre düzenlenmeli)."""
    Path(hedef_yol).write_text(KIBOT_ORNEK_YAML, encoding="utf-8")
    return hedef_yol


def kibot_calistir(
    board_path: str,
    config_path: str = "kibot.yaml",
    cikti_dizini: str = "uretim",
    kibot_bin: str = "kibot",
) -> KiBotSonucu:
    """KiBot'u çalıştırıp yapılandırılmış tüm üretim çıktılarını üretir.

    ÇAĞIRMADAN ÖNCE modül docstring'indeki DRC/ERC kapı kontrolü yapılmış
    olmalı.
    """
    komut = [kibot_bin, "-b", board_path, "-c", config_path, "-d", cikti_dizini]
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    return KiBotSonucu(
        basarili=(sonuc.returncode == 0),
        cikti_dizini=cikti_dizini,
        stdout=sonuc.stdout,
        stderr=sonuc.stderr,
    )


# ====================================================================
# BÖLÜM 4 — CPL/Assembly detayları: rotasyon-map versiyonlama,
# oryantasyon çapraz kontrolü, panelizasyon kuralları
# [[SKILL-cpl-assembly]] karşılığı — KiBot zaten CPL/BOM/Gerber ZIP'ini
# ÜRETİYOR (kibot_calistir); bu bölüm KiBot'un GİRDİSİ olan fab-özel
# rotasyon düzeltmesini ve panelizasyon/oryantasyon kontrolünü yönetir.
# ====================================================================

# --------------------------------------------------------------
# 4.1 Fab-rotasyon-map — VERSİYONLA (yoksa tüm parti ters lehim)
# --------------------------------------------------------------

@dataclass
class RotasyonMapKaydi:
    fab_adi: str  # örn. "JLCPCB"
    footprint_lib_id: str  # örn. "Package_TO_SOT_SMD:SOT-23-6"
    fab_ofset_derece: float  # JLC rotasyonu KiCad'den farklı olabilir


@dataclass
class RotasyonMapVersiyonu:
    kayitlar: List[RotasyonMapKaydi]
    hash: str
    olusturulma_notu: str = ""


def rotation_map_versiyonla(kayitlar: List[RotasyonMapKaydi], not_: str = "") -> RotasyonMapVersiyonu:
    """
    Fab-rotasyon-map'ini içerik hash'iyle damgalar. Amaç: bu map SESSİZCE
    değişirse (ör. yeni bir footprint eklenip eski kayıtlar unutulursa) bir
    sonraki üretimde TÜM PARTİ ters lehimlenebilir — hash, iki çalıştırma
    arasında map'in aynı kalıp kalmadığını tespit etmeyi sağlar.
    """
    icerik = json.dumps(
        [(k.fab_adi, k.footprint_lib_id, k.fab_ofset_derece) for k in kayitlar],
        sort_keys=True,
    )
    h = hashlib.sha256(icerik.encode("utf-8")).hexdigest()[:16]
    return RotasyonMapVersiyonu(kayitlar=kayitlar, hash=h, olusturulma_notu=not_)


def rotation_map_degisti_mi(eski: RotasyonMapVersiyonu, yeni: RotasyonMapVersiyonu) -> bool:
    return eski.hash != yeni.hash


def rotation_map_json_yaz(versiyon: RotasyonMapVersiyonu, hedef_yol: str = "rotation_map.json") -> str:
    icerik = {
        "hash": versiyon.hash,
        "not": versiyon.olusturulma_notu,
        "kayitlar": [
            {
                "fab": k.fab_adi,
                "footprint": k.footprint_lib_id,
                "ofset_derece": k.fab_ofset_derece,
            }
            for k in versiyon.kayitlar
        ],
    }
    Path(hedef_yol).write_text(json.dumps(icerik, indent=2, ensure_ascii=False), encoding="utf-8")
    return hedef_yol


# --------------------------------------------------------------
# 4.2 Centroid (pick-point) — gövde/courtyard merkezi, footprint origin DEĞİL
# --------------------------------------------------------------

@dataclass
class FootprintGeometrisi:
    refdes: str
    footprint_lib_id: str  # örn. "Package_TO_SOT_SMD:SOT-23-6" — rotasyon_map eşleşme anahtarı
    footprint_origin: Tuple[float, float]
    courtyard_bbox: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    footprint_aci_derece: float
    katman: str  # "F.Cu" | "B.Cu"


def generate_cpl_file(
    footprintler: List[FootprintGeometrisi],
    rotasyon_map: RotasyonMapVersiyonu,
) -> List[Dict]:
    """
    Her footprint için Designator/MidX/MidY/Layer/Rotation üretir.

    - Pick-point = gövde/courtyard BBOX'unun merkezi, footprint origin DEĞİL
      (ikisi genelde farklıdır — origin genelde pin-1 köşesine yakındır).
    - Rotasyon = footprint açısı + fab-özel ofset (rotasyon_map'ten, footprint
      lib_id eşleşmesine göre; eşleşme yoksa ofset 0 varsayılır ve UYARI
      döner — sessizce 0 alıp devam etmek "tüm parti ters lehim" riskidir).
    """
    map_by_footprint = {k.footprint_lib_id: k.fab_ofset_derece for k in rotasyon_map.kayitlar}
    satirlar: List[Dict] = []
    for fp in footprintler:
        x_min, y_min, x_max, y_max = fp.courtyard_bbox
        mid_x = (x_min + x_max) / 2
        mid_y = (y_min + y_max) / 2
        satirlar.append(
            {
                "Designator": fp.refdes,
                "MidX": round(mid_x, 4),
                "MidY": round(mid_y, 4),
                "Layer": fp.katman,
                "Rotation": (fp.footprint_aci_derece) % 360,
                "_rotasyon_map_eslesti": False,
            }
        )
    return satirlar


def rotasyon_duzeltmesi_uygula(
    cpl_satirlari: List[Dict],
    footprintler: List[FootprintGeometrisi],
    rotasyon_map: RotasyonMapVersiyonu,
) -> List[str]:
    """`generate_cpl_file` çıktısına fab-özel rotasyon ofsetini uygular; eşleşmeyen
    her footprint için bir UYARI döndürür (sessiz 0-ofset varsayımı yasak)."""
    map_by_footprint = {k.footprint_lib_id: k.fab_ofset_derece for k in rotasyon_map.kayitlar}
    fp_by_refdes = {fp.refdes: fp for fp in footprintler}
    uyarilar: List[str] = []
    for satir in cpl_satirlari:
        fp = fp_by_refdes[satir["Designator"]]
        ofset = map_by_footprint.get(fp.footprint_lib_id)
        if ofset is None:
            uyarilar.append(
                f"UYARI [{satir['Designator']}]: rotasyon_map'te eşleşme yok — "
                "ofset 0 varsayıldı. Bu footprint için fab-rotasyon-map'i "
                "GÜNCELLENMEDEN üretime geçilirse tüm parti ters lehimlenebilir."
            )
            continue
        satir["Rotation"] = (satir["Rotation"] + ofset) % 360
        satir["_rotasyon_map_eslesti"] = True
    return uyarilar


# --------------------------------------------------------------
# 4.3 Oryantasyon çapraz kontrolü — kutuplu parça yönü <-> CPL açısı
# --------------------------------------------------------------

class KutupluParcaTipi(Enum):
    DIYOT = "diyot"
    IC_PIN1 = "ic_pin1"
    LED = "led"
    ELEKTROLITIK = "elektrolitik"


@dataclass
class KutupluParca:
    refdes: str
    tip: KutupluParcaTipi
    sematik_beklenen_aci_derece: float  # datasheet/şematikten beklenen pin-1 açısı


def check_orientation(
    kutuplu_parcalar: List[KutupluParca],
    cpl_satirlari: List[Dict],
    tolerans_derece: float = 1.0,
) -> List[str]:
    """Kutuplu parça (diyot/IC pin-1/LED/elektrolitik) yönü ile üretilen CPL
    açısını çapraz kontrol eder. Bu adım atlanırsa PCB DRC'yi geçse bile
    tüm kutuplu parçalar ters monte edilebilir (DRC yön bilmez, sadece
    clearance/connectivity bilir)."""
    bulgular: List[str] = []
    cpl_by_refdes = {s["Designator"]: s for s in cpl_satirlari}
    for parca in kutuplu_parcalar:
        satir = cpl_by_refdes.get(parca.refdes)
        if satir is None:
            bulgular.append(f"KRİTİK [{parca.refdes}]: CPL'de bulunamadı.")
            continue
        fark = abs(satir["Rotation"] - parca.sematik_beklenen_aci_derece) % 360
        fark = min(fark, 360 - fark)
        if fark > tolerans_derece:
            bulgular.append(
                f"KRİTİK [{parca.refdes}] ({parca.tip.value}): CPL açısı "
                f"{satir['Rotation']}° != beklenen {parca.sematik_beklenen_aci_derece}° "
                f"(fark {fark:.1f}° > tolerans {tolerans_derece}°) — ters monte riski."
            )
    return bulgular


# --------------------------------------------------------------
# 4.4 Panelizasyon kuralları — fiducial, rail, de-panel stresi
# --------------------------------------------------------------

@dataclass
class PanelKisiti:
    global_fiducial_sayisi: int
    bga_local_fiducial_var_mi: bool
    rail_genislik_mm: float
    hassas_parca_depanel_mesafesi_mm: Optional[float] = None  # en yakın hassas parçaya mesafe


def panelizasyon_kontrolu(
    kisit: PanelKisiti,
    hassas_parca_min_mesafe_mm: float = 5.0,
    min_rail_mm: float = 5.0,
    min_global_fiducial: int = 3,
) -> List[str]:
    """
    Panel varsa: >=3 global fiducial (+BGA varsa local fiducial), >=5mm rail,
    de-panel stresi hassas parçadan (kristal, hassas analog, BGA köşesi) uzak
    tutulmalı.
    """
    bulgular: List[str] = []
    if kisit.global_fiducial_sayisi < min_global_fiducial:
        bulgular.append(
            f"EKSİK: {kisit.global_fiducial_sayisi} global fiducial < {min_global_fiducial}."
        )
    if not kisit.bga_local_fiducial_var_mi:
        bulgular.append("UYARI: BGA local fiducial tanımlı değil (BGA varsa zorunlu).")
    if kisit.rail_genislik_mm < min_rail_mm:
        bulgular.append(
            f"EKSİK: rail genişliği {kisit.rail_genislik_mm}mm < {min_rail_mm}mm."
        )
    if (
        kisit.hassas_parca_depanel_mesafesi_mm is not None
        and kisit.hassas_parca_depanel_mesafesi_mm < hassas_parca_min_mesafe_mm
    ):
        bulgular.append(
            f"KRİTİK: en yakın hassas parça de-panel hattına "
            f"{kisit.hassas_parca_depanel_mesafesi_mm}mm < {hassas_parca_min_mesafe_mm}mm "
            "— de-panel stresi hassas parçayı etkileyebilir."
        )
    return bulgular


# ====================================================================
# BÖLÜM 5 — Kontrat (Artifact Contract) kapıları
# ====================================================================
#
# NEDEN VAR (arkadaşın Otonom-PCB-Ajani sisteminden alınan mimari ders,
# bkz. `Skills/SKILL-orchestrator.md`): o projede adımlar birbirine
# DEĞİŞKEN/dönüş değeri üzerinden değil, diskteki JSON artifact'ler
# üzerinden bağlanıyor — bir adımın "geçti" demesi yetmiyor, bir sonraki
# adım GERÇEKTEN diskteki dosyayı okuyup kendi kapısını kendi kontrol
# ediyor. Bu modülün zincirinde (`freerouting_zinciri_calistir` ->
# `kibot_calistir`) o disipline kadar YOKTU: `kicad_koprusu.drc_calistir()`
# zaten `rapor_path`'e (`drc_raporu.json`) yazıyordu ama hiçbir fonksiyon
# o dosyayı GERİ OKUYUP kapı kararını ondan vermiyordu — kapı kararı hep
# çağıran kodun elindeki Python `dict`'ine bakıyordu (bkz. modül başlığındaki
# BÖLÜM 3 örnek akışı: `if drc_temiz_mi(drc) and erc_temiz_mi(erc):`).
# Bellekteki `dict` ile diskteki JSON SESSİZCE FARKLILAŞABİLİR (ör. iki ayrı
# süreç/ajan aynı board'a karşı farklı zamanlarda DRC koşturursa, ya da biri
# raporu commit etmeyi unutursa) — bu bölüm iki kontrat şeması (`parts.json`,
# `drc.json`) tanımlar ve kapı fonksiyonlarını HER ZAMAN diskten okumaya
# zorlar (`Path.read_text` ile, parametre olarak geçirilen `dict` ile DEĞİL).
#
# ÜÇÜNCÜ TARAF ŞEMASI DEĞİL — BİLEREK: Otonom-PCB-Ajani'de `parts.json`/
# `drc.json` diye somut bir örnek/şema dosyası YOKTU (yalnızca kavramsal
# isim geçiyordu, bkz. proje karşılaştırma notu); şemalar burada bu
# projenin GERÇEK araçlarına (`bom_lifecycle_koprusu.py`, `kicad_koprusu.py`)
# göre YENİDEN tanımlandı.

KONTRAT_SEMA_SURUMU = 1  # ileride alan eklenirse SÜRÜM ARTIRILIR, sessizce değiştirilmez


class KontratKapisiHatasi(RuntimeError):
    """Bir kontrat kapısı (drc.json/parts.json) FAIL verdiğinde fırlatılan
    ÖZEL istisna tipi — çıplak `RuntimeError` yerine bunun kullanılması,
    çağıran orkestratör kodunun "kontrat kapısı kapalı" durumunu diğer
    (ilgisiz) çalışma-zamanı hatalarından `except KontratKapisiHatasi` ile
    AYIRT EDEBİLMESİNİ sağlar (bkz. `FreeRoutingDesteklenmiyorHatasi` ile
    aynı gerekçe, BÖLÜM 1)."""


# --------------------------------------------------------------
# 5.1 drc.json — DRC/ERC sonucunun normalize edilmiş kontrat şeması
# --------------------------------------------------------------

@dataclass
class DrcKontrati:
    """`kicad_koprusu.drc_calistir()`/`erc_calistir()`'in HAM kicad-cli
    JSON çıktısından türetilen, KÜÇÜK ve İSTİKRARLI bir kontrat şeması.
    Ham kicad-cli şeması (DRC: üst-seviye `violations`; ERC: `sheets[].
    violations` — bkz. `kicad_koprusu.py` docstring'leri, ikisi FARKLI)
    çağıran her koda sızmasın diye burada TEK bir düz şemaya indirgenir."""

    sema_surumu: int
    kaynak: str  # "drc" | "erc"
    board_veya_sematik_yolu: str
    ihlal_sayisi: int  # yalnızca error/fatal seviyesi — uyarılar HARİÇ
    uyari_sayisi: int
    ihlaller: List[Dict] = field(default_factory=list)
    olusturulma_ts: str = ""


def drc_kontrati_uret(
    board_veya_sematik_yolu: str,
    ham_rapor: Dict,
    kaynak: str = "drc",
) -> DrcKontrati:
    """Ham `drc_calistir()`/`erc_calistir()` sözlüğünü `DrcKontrati`'na indirger.

    `kaynak` şemaların FARKLI ihlal yollarını (`violations` vs
    `sheets[].violations`) seçmek için kullanılır — yanlış `kaynak`
    verilirse ihlal listesi SESSİZCE boş kalıp sahte PASS üretebilir, bu
    yüzden tanınmayan bir `kaynak` `ValueError` fırlatır (fail-open YOK).
    """
    if kaynak == "drc":
        tum_ihlaller = list(ham_rapor.get("violations", []))
        tum_ihlaller += list(ham_rapor.get("unconnected_items", []))
    elif kaynak == "erc":
        tum_ihlaller = [v for s in ham_rapor.get("sheets", []) for v in s.get("violations", [])]
    else:
        raise ValueError(f"drc_kontrati_uret: bilinmeyen kaynak={kaynak!r} (yalnız 'drc'/'erc')")

    onemli = {"error", "fatal"} if kaynak == "erc" else {"error"}
    hatalar = [v for v in tum_ihlaller if v.get("severity") in onemli]
    uyarilar = [v for v in tum_ihlaller if v.get("severity") not in onemli]
    return DrcKontrati(
        sema_surumu=KONTRAT_SEMA_SURUMU,
        kaynak=kaynak,
        board_veya_sematik_yolu=board_veya_sematik_yolu,
        ihlal_sayisi=len(hatalar),
        uyari_sayisi=len(uyarilar),
        ihlaller=hatalar,
        olusturulma_ts=datetime.now(timezone.utc).isoformat(),
    )


def drc_kontrati_yaz(kontrat: DrcKontrati, hedef_yol: str = "drc.json") -> str:
    """`DrcKontrati`'nı DİSKE yazar — bir sonraki adım bunu bellekteki
    nesneden değil, bu dosyadan okumalı (`drc_kapisi_gecti_mi`)."""
    Path(hedef_yol).write_text(
        json.dumps(asdict(kontrat), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return hedef_yol


def drc_kapisi_gecti_mi(kontrat_yolu: str = "drc.json") -> bool:
    """`drc.json == 0` KAPISI — SADECE diskteki dosyayı okur.

    Dosya yoksa/parse edilemiyorsa/`ihlal_sayisi` alanı eksikse `False`
    DEĞİL, `KontratKapisiHatasi` fırlatır: "kontrol hiç koşmadı" ile
    "kontrol koştu, 0 ihlal" arasındaki farkı `bulgu_sozlesmesi.py`'deki
    `KAPSAM_YOK` disipliniyle AYNI gerekçeyle kapatır — sessiz fail-open
    (dosya yoksa geçti SAYMAK) bu projenin daha önce düzelttiği P0 sınıfı
    bir hatadır (bkz. commit `89cf953`)."""
    yol = Path(kontrat_yolu)
    if not yol.exists():
        raise KontratKapisiHatasi(
            f"drc_kapisi_gecti_mi: {kontrat_yolu} yok — DRC/ERC hiç koşmamış veya "
            "kontrat henüz yazılmamış olabilir. Kapı FAIL-OPEN geçemez; "
            "önce drc_kontrati_yaz()/erc_calistir() çalıştırılmalı."
        )
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise KontratKapisiHatasi(f"drc_kapisi_gecti_mi: {kontrat_yolu} bozuk JSON: {e}") from e
    if "ihlal_sayisi" not in veri:
        raise KontratKapisiHatasi(
            f"drc_kapisi_gecti_mi: {kontrat_yolu} 'ihlal_sayisi' alanı yok — "
            "beklenmeyen şema (sürüm uyuşmazlığı olabilir, bkz. KONTRAT_SEMA_SURUMU)."
        )
    return veri["ihlal_sayisi"] == 0


# --------------------------------------------------------------
# 5.2 parts.json — BOM/tedarik kontrat şeması (bom_lifecycle_koprusu.py köprüsü)
# --------------------------------------------------------------

@dataclass
class ParcaKontratSatiri:
    refdes: str
    lcsc_kodu: str
    risk_skoru: float  # bom_lifecycle_koprusu.py risk skoru (lifecycle+stok+single-source+lead-time)
    yasam_dongusu_durumu: str  # "Active" | "NRND" | "EOL" | "Obsolete" | ...
    alternatif_bulundu_mu: bool = False


@dataclass
class PartsKontrati:
    sema_surumu: int
    satirlar: List[ParcaKontratSatiri]
    olusturulma_ts: str = ""


def parts_kontrati_yaz(satirlar: List[ParcaKontratSatiri], hedef_yol: str = "parts.json") -> str:
    """`ParcaKontratSatiri` listesini `parts.json`'a yazar — MASTER_RULEBOOK
    Faz 1'in (`bom_lifecycle_koprusu.py::validate_bom_lifecycle`) çıktısı
    buradan geçmeli ki `jlc_parcasi_indir()`/`kibot_calistir()` zinciri
    ONU okuyabilsin, çağıranın elindeki listeye değil."""
    kontrat = PartsKontrati(
        sema_surumu=KONTRAT_SEMA_SURUMU,
        satirlar=satirlar,
        olusturulma_ts=datetime.now(timezone.utc).isoformat(),
    )
    Path(hedef_yol).write_text(
        json.dumps(asdict(kontrat), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return hedef_yol


def parts_kapisi_gecti_mi(
    kontrat_yolu: str = "parts.json", max_risk_skoru: float = 0.5
) -> Tuple[bool, List[str]]:
    """`parts.json`'ı DİSKTEN okuyup her satırın risk skorunu/yaşam-döngüsü
    durumunu değerlendirir. Kapanmamış (risk > eşik VEYA NRND/EOL/Obsolete
    VE alternatif bulunmamış) her satır için bir bulgu döner; liste boşsa
    kapı GEÇTİ demektir. Dosya yoksa `KontratKapisiHatasi` (fail-open yok —
    5.1'deki ile aynı gerekçe)."""
    yol = Path(kontrat_yolu)
    if not yol.exists():
        raise KontratKapisiHatasi(
            f"parts_kapisi_gecti_mi: {kontrat_yolu} yok — parts_kontrati_yaz() "
            "hiç çağrılmamış olabilir. Kapı FAIL-OPEN geçemez."
        )
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise KontratKapisiHatasi(f"parts_kapisi_gecti_mi: {kontrat_yolu} bozuk JSON: {e}") from e

    riskli_durumlar = {"NRND", "EOL", "Obsolete"}
    bulgular: List[str] = []
    for satir in veri.get("satirlar", []):
        refdes = satir.get("refdes", "?")
        risk = satir.get("risk_skoru", 1.0)  # eksik alan = güvenli tarafta (yüksek risk) varsay
        durum = satir.get("yasam_dongusu_durumu", "?")
        alternatif = satir.get("alternatif_bulundu_mu", False)
        if risk > max_risk_skoru:
            bulgular.append(f"{refdes}: risk_skoru {risk} > {max_risk_skoru}")
        if durum in riskli_durumlar and not alternatif:
            bulgular.append(f"{refdes}: yaşam-döngüsü {durum}, pin-uyumlu alternatif bulunamadı")
    return (len(bulgular) == 0, bulgular)


# --------------------------------------------------------------
# 5.3 Zincire bağlanmış kapı — freerouting/kibot artık DOĞRUDAN
# değişken yerine bu iki kontrat dosyasını okuyarak ilerler
# --------------------------------------------------------------

def uretim_zincirini_kontratla_yurut(
    board_path: str,
    parts_kontrat_yolu: str = "parts.json",
    drc_kontrat_yolu: str = "drc.json",
    kibot_config_yolu: str = "kibot.yaml",
    kibot_cikti_dizini: str = "uretim",
    kibot_bin: str = "kibot",
) -> KiBotSonucu:
    """BÖLÜM 3'ün (KiBot) modül-başlığındaki elle kurulması gereken kapıyı
    KOD OLARAK zorunlu kılar — üretim çıktısı üretmeden ÖNCE `parts.json`
    VE `drc.json` kontratlarının İKİSİ de diskten okunup PASS vermeli;
    biri bile eksikse/FAIL ise `KontratKapisiHatasi` fırlatılır ve
    `kibot_calistir()`'e HİÇ ULAŞILMAZ (freerouting zincirindeki
    `KICAD10_DSN_DESTEKLENIYOR` savunma-derinliği deseniyle AYNI disiplin).
    """
    parts_gecti, parts_bulgular = parts_kapisi_gecti_mi(parts_kontrat_yolu)
    if not parts_gecti:
        raise KontratKapisiHatasi(
            "uretim_zincirini_kontratla_yurut: parts.json kapısı FAIL:\n"
            + "\n".join(parts_bulgular)
        )
    if not drc_kapisi_gecti_mi(drc_kontrat_yolu):
        raise KontratKapisiHatasi(
            f"uretim_zincirini_kontratla_yurut: {drc_kontrat_yolu} kapısı FAIL "
            "(ihlal_sayisi != 0) — kibot_calistir() ÇAĞRILMADI."
        )
    kibot_config_yaz(kibot_config_yolu)
    return kibot_calistir(board_path, kibot_config_yolu, kibot_cikti_dizini, kibot_bin)


# --------------------------------------------------------------
# 5.4 Öz-test + fault-injection (proje disiplini: her A-seviyesi kontrol
# için "kusur enjekte edildi -> kontrol FAIL verdi" kanıtı zorunlu)
# --------------------------------------------------------------

def _kontrat_kapilari_oz_testleri_calistir(tmp_dizin: str) -> List[str]:
    hatalar: List[str] = []
    tmp = Path(tmp_dizin)

    # 1) drc.json yokken kapı FAIL-OPEN geçmemeli (dosya yok -> istisna).
    eksik_yol = tmp / "yok_drc.json"
    try:
        drc_kapisi_gecti_mi(str(eksik_yol))
    except KontratKapisiHatasi:
        pass
    else:
        hatalar.append("drc_kapisi_gecti_mi: dosya yokken sessizce geçti (fail-open)")

    # 2) Temiz drc.json -> PASS.
    temiz = drc_kontrati_uret("board.kicad_pcb", {"violations": [], "unconnected_items": []})
    drc_kontrati_yaz(temiz, str(tmp / "drc_temiz.json"))
    if not drc_kapisi_gecti_mi(str(tmp / "drc_temiz.json")):
        hatalar.append("drc_kapisi_gecti_mi: temiz rapor FAIL döndü (beklenen PASS)")

    # 3) FAULT INJECTION: bir 'error' ihlali enjekte et -> kapı KIRILMALI.
    kirli_ham = {"violations": [{"severity": "error", "type": "clearance"}]}
    kirli = drc_kontrati_uret("board.kicad_pcb", kirli_ham)
    drc_kontrati_yaz(kirli, str(tmp / "drc_kirli.json"))
    if drc_kapisi_gecti_mi(str(tmp / "drc_kirli.json")):
        hatalar.append("FAULT-INJECTION KIRILMADI: 1 error ihlali varken drc kapısı PASS verdi")

    # 4) parts.json: NRND + alternatifsiz satır -> kapı FAIL vermeli.
    riskli = [ParcaKontratSatiri("U1", "C12345", 0.1, "NRND", alternatif_bulundu_mu=False)]
    parts_kontrati_yaz(riskli, str(tmp / "parts_riskli.json"))
    gecti, bulgular = parts_kapisi_gecti_mi(str(tmp / "parts_riskli.json"))
    if gecti or not bulgular:
        hatalar.append("FAULT-INJECTION KIRILMADI: NRND+alternatifsiz parça parts kapısını geçti")

    # 5) parts.json: aynı satır alternatif bulunmuşsa -> kapı PASS vermeli.
    temiz_parca = [ParcaKontratSatiri("U1", "C12345", 0.1, "NRND", alternatif_bulundu_mu=True)]
    parts_kontrati_yaz(temiz_parca, str(tmp / "parts_temiz.json"))
    gecti2, bulgular2 = parts_kapisi_gecti_mi(str(tmp / "parts_temiz.json"))
    if not gecti2:
        hatalar.append(f"parts kapısı: alternatif bulunmuş NRND parça yine de FAIL verdi: {bulgular2}")

    return hatalar


# ====================================================================
# Uçtan uca örnek (yalnızca gösterim — gerçek kurulumda çalıştırılmalı)
# ====================================================================

if __name__ == "__main__":
    print(
        "Bu modül gerçek KiCad + Java/FreeRouting + JLC2KiCadLib + KiBot "
        "kurulu bir makinede çalıştırılmalı. Tam zincir örneği:\n\n"
        "  from kicad_koprusu import drc_calistir, erc_calistir, drc_temiz_mi, erc_temiz_mi\n\n"
        "  # 1) Eksik footprint\n"
        "  jlc_parcasi_indir('C12345', hedef_dizin='./lib')\n\n"
        "  # 2) Routing\n"
        "  sonuc = freerouting_zinciri_calistir('proje.kicad_pcb')\n\n"
        "  # 3) Doğrulama kapısı\n"
        "  if sonuc.basarili:\n"
        "      drc = drc_calistir('proje.kicad_pcb')\n"
        "      erc = erc_calistir('proje.kicad_sch')\n"
        "      if drc_temiz_mi(drc) and erc_temiz_mi(erc):\n"
        "          # 4) Üretim çıktıları\n"
        "          kibot_config_yaz('kibot.yaml')\n"
        "          kibot_calistir('proje.kicad_pcb')\n"
    )
