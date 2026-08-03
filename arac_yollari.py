"""Harici EDA araçlarının güvenli ve yapılandırılabilir yol çözümü."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


KICAD_CLI_ENV = "KICAD_CLI"
POPPLER_BIN_ENV = "POPPLER_BIN"


def _windows_kicad_adaylari() -> list[Path]:
    """Windows'taki sürüm bağımsız, yaygın KiCad CLI konumlarını döndürür."""
    if os.name != "nt":
        return []
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    kok = Path(program_files) / "KiCad"
    if not kok.is_dir():
        return []
    return sorted(kok.glob("*/bin/kicad-cli.exe"), reverse=True)


def _windows_poppler_adaylari() -> list[Path]:
    """Windows'ta winget ile kurulan poppler'ın (`pdftocairo`) yaygın
    konumunu arar (`pcb_gorsel_kesit.py`'nin PDF->PNG adımı için).
    scoop/choco ile kurulanlar zaten PATH'e eklenir, o yüzden burada
    SADECE winget'in PATH'e eklemediği `WinGet\\Packages\\...` düzeni
    taranır."""
    if os.name != "nt":
        return []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return []
    kok = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
    if not kok.is_dir():
        return []
    return sorted(kok.glob("*poppler*/**/pdftocairo.exe"), reverse=True)


def pdftocairo_yolunu_bul(istenen_yol: Optional[str] = None) -> str:
    """`pdftocairo` (poppler) yolunu çözer — `kicad_cli_yolunu_bul()` ile
    AYNI öncelik disiplini: parametre > `POPPLER_BIN` ortam değişkeni >
    PATH > Windows winget kurulum dizini taraması."""
    if istenen_yol:
        aday = Path(istenen_yol).expanduser()
        if aday.is_file():
            return str(aday)
        pathte = shutil.which(istenen_yol)
        if pathte:
            return pathte
        raise FileNotFoundError(f"İstenen pdftocairo bulunamadı: {istenen_yol}")

    ortam_yolu = os.environ.get(POPPLER_BIN_ENV)
    if ortam_yolu:
        return pdftocairo_yolunu_bul(ortam_yolu)

    pathte = shutil.which("pdftocairo")
    if pathte:
        return pathte

    for aday in _windows_poppler_adaylari():
        if aday.is_file():
            return str(aday)

    raise FileNotFoundError(
        "pdftocairo (poppler) bulunamadı. Kurulum: `winget install "
        "oschwartz10612.Poppler` (Windows) veya `apt install poppler-utils` "
        "(Linux) / `brew install poppler` (macOS); ya da POPPLER_BIN ortam "
        "değişkenini pdftocairo'nun tam yoluna ayarla."
    )


def kicad_cli_yolunu_bul(istenen_yol: Optional[str] = None) -> str:
    """KiCad CLI yolunu çözer.

    Öncelik: fonksiyon parametresi, ``KICAD_CLI`` ortam değişkeni, PATH,
    ardından Windows'un standart KiCad kurulum dizini. Bulunamazsa sessizce
    ``kicad-cli`` döndürmek yerine çalıştırılabilir bir hata üretir.
    """
    if istenen_yol:
        aday = Path(istenen_yol).expanduser()
        if aday.is_file():
            return str(aday)
        pathte = shutil.which(istenen_yol)
        if pathte:
            return pathte
        raise FileNotFoundError(f"İstenen KiCad CLI bulunamadı: {istenen_yol}")

    ortam_yolu = os.environ.get(KICAD_CLI_ENV)
    if ortam_yolu:
        return kicad_cli_yolunu_bul(ortam_yolu)

    pathte = shutil.which("kicad-cli")
    if pathte:
        return pathte

    for aday in _windows_kicad_adaylari():
        if aday.is_file():
            return str(aday)

    raise FileNotFoundError(
        "KiCad CLI bulunamadı. KiCad'i kur, KICAD_CLI ortam değişkenini "
        "kicad-cli.exe'nin tam yoluna ayarla veya programı PATH'e ekle."
    )


KICAD_PYTHON_ENV = "KICAD_PYTHON"


def _windows_kicad_python_adaylari() -> list[Path]:
    """`kicad-cli.exe`'nin YANINDAKİ `python.exe`'yi bulur — bu proje
    boyunca gerçek `pcbnew` (SWIG) SADECE KiCad'in kendi gömülü Python
    dağıtımında bulunuyor (proje `uv` venv'inde `import pcbnew` HER ZAMAN
    `ModuleNotFoundError` verir, bu ortam-bağımlı bir eksiklik DEĞİL —
    `pcbnew` bir PyPI paketi olarak dağıtılmıyor). `kicad_cli_yolunu_bul()`
    ile AYNI kök dizin taramasını kullanır (`bin/kicad-cli.exe` bulunan her
    sürüm dizininde `bin/python.exe` da vardır)."""
    if os.name != "nt":
        return []
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    kok = Path(program_files) / "KiCad"
    if not kok.is_dir():
        return []
    return sorted(kok.glob("*/bin/python.exe"), reverse=True)


def kicad_python_yolunu_bul(istenen_yol: Optional[str] = None) -> str:
    """`pcbnew` içeren KiCad'in GÖMÜLÜ Python yorumlayıcısının yolunu
    çözer — `kicad_cli_yolunu_bul()` ile birebir aynı öncelik sırası
    (parametre -> `KICAD_PYTHON` ortam değişkeni -> standart Windows kurulum
    dizini). Bu proje `pcbnew` gerektiren HER script için (`pcbnew_koprusu.py`,
    `mcad_carpisma_koprusu.py`, `otonom_python_router.py`'nin yazma katmanı
    vb.) bu fonksiyonun döndürdüğü yorumlayıcıyla çağrılmalı — proje venv'inin
    kendi `python`'u ASLA `pcbnew` göremez."""
    if istenen_yol:
        aday = Path(istenen_yol).expanduser()
        if aday.is_file():
            return str(aday)
        raise FileNotFoundError(f"İstenen KiCad Python bulunamadı: {istenen_yol}")

    ortam_yolu = os.environ.get(KICAD_PYTHON_ENV)
    if ortam_yolu:
        return kicad_python_yolunu_bul(ortam_yolu)

    for aday in _windows_kicad_python_adaylari():
        if aday.is_file():
            return str(aday)

    raise FileNotFoundError(
        "KiCad'in gömülü Python yorumlayıcısı bulunamadı (pcbnew burada "
        "yaşar). KICAD_PYTHON ortam değişkenini "
        "'<KiCad kurulum dizini>/bin/python.exe' yoluna ayarla."
    )


def pcbnew_scripti_calistir(
    script_path: str, argv: Optional[List[str]] = None, kicad_python: Optional[str] = None,
    timeout_s: int = 120,
) -> subprocess.CompletedProcess:
    """Bir `.py` dosyasını KiCad'in gömülü (pcbnew'li) Python'uyla
    `subprocess.run()` ile çalıştırır — projenin geri kalanının kendi
    `uv`/venv Python'unda kalabilmesi için (`pcbnew` importu SADECE bu alt
    süreçte gerekir). `otonom_kurtarma_motoru.izole_calistir()`'in
    `subprocess` sandboxing FELSEFESİYLE aynı, ama fonksiyon değil TAM BİR
    SCRIPT DOSYASI çalıştırmak için (ör. `pcbnew_koprusu.py --json ...`
    CLI'sini elle `kicad-cli`/`python.exe` zinciriyle çağırmak yerine)."""
    yol = kicad_python_yolunu_bul(kicad_python)
    komut = [yol, script_path] + (argv or [])
    return subprocess.run(komut, capture_output=True, text=True, timeout=timeout_s)


def kicad_cli_surumu_dogrula(kicad_cli: Optional[str] = None) -> tuple[str, str]:
    """Çözülen CLI'yi gerçek ``--version`` komutuyla doğrular."""
    yol = kicad_cli_yolunu_bul(kicad_cli)
    sonuc = subprocess.run([yol, "--version"], capture_output=True, text=True, timeout=15)
    metin = (sonuc.stdout or sonuc.stderr).strip()
    if sonuc.returncode != 0:
        raise RuntimeError(f"KiCad CLI sürümü okunamadı ({yol}): {metin}")
    return yol, metin


def ortam_on_kontrolu(kicad_cli: Optional[str] = None) -> list[str]:
    """KiCad CLI için taşınabilir, fail-closed ortam ön kontrolü."""
    yol, surum = kicad_cli_surumu_dogrula(kicad_cli)
    return [f"PASS KiCad CLI: {yol}", f"PASS sürüm: {surum}", f"PASS Python: {sys.version.split()[0]}"]


@dataclass
class AracDurumu:
    """Tek bir dış aracın ön-kontrol sonucu — `KURULUM.md`'nin hangi
    maddesine yönlendireceğini de taşır ki eksik bir araç bulunduğunda
    kullanıcıya "kurulu olduğunu varsay" yerine tam kurulum komutu
    gösterilebilsin (CLAUDE.md Faz -1 disiplini)."""

    isim: str
    gecti_mi: bool
    detay: str
    kurulum_maddesi: str

    def satir(self) -> str:
        durum = "PASS" if self.gecti_mi else "FAIL"
        return f"{durum} {self.isim}: {self.detay} (bkz. {self.kurulum_maddesi})" if not self.gecti_mi \
            else f"{durum} {self.isim}: {self.detay}"


def _komut_kontrol(isim: str, komut: List[str], kurulum_maddesi: str, zaman_asimi_s: int = 20) -> AracDurumu:
    """Bir CLI aracını `--version` (veya benzeri) bayrağıyla çağırıp
    PASS/FAIL üretir. Araç PATH'te yoksa VEYA çalıştırılamıyorsa (timeout,
    izin hatası vb.) hata FIRLATMAZ — `AracDurumu(gecti_mi=False, ...)`
    döner ki tek bir eksik araç TÜM ön-kontrolü kesmesin (`ortam_on_kontrolu()`
    ile aynı fail-closed-ama-devam-eden disiplin, tek fark: burada tek bir
    araç değil TÜM zincir raporlanıyor)."""
    yol = shutil.which(komut[0])
    if yol is None:
        return AracDurumu(isim, False, f"'{komut[0]}' bulunamadı (PATH'te değil)", kurulum_maddesi)
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi_s)
    except (OSError, subprocess.SubprocessError) as hata:
        return AracDurumu(isim, False, f"çalıştırılamadı: {hata}", kurulum_maddesi)
    metin = ((sonuc.stdout or "") + (sonuc.stderr or "")).strip()
    ilk_satir = metin.splitlines()[0] if metin else ""
    return AracDurumu(isim, sonuc.returncode == 0, ilk_satir or f"exit={sonuc.returncode}", kurulum_maddesi)


def _python_import_kontrol(isim: str, import_ifadesi: str, kurulum_maddesi: str) -> AracDurumu:
    """`python3 -c "import X"` ile aynı kontrolü, GÜNCEL Python
    yorumlayıcısıyla (`sys.executable`) yapar — bash sürümünün
    `python3 -c "import pcbnew, kipy"` deseniyle birebir eşdeğer."""
    try:
        sonuc = subprocess.run(
            [sys.executable, "-c", f"import {import_ifadesi}"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as hata:
        return AracDurumu(isim, False, f"çalıştırılamadı: {hata}", kurulum_maddesi)
    if sonuc.returncode == 0:
        return AracDurumu(isim, True, "import OK", kurulum_maddesi)
    hata_satiri = (sonuc.stderr or "").strip().splitlines()
    return AracDurumu(isim, False, hata_satiri[-1] if hata_satiri else "import başarısız", kurulum_maddesi)


def _pcbnew_kontrol() -> AracDurumu:
    """`pcbnew`'i proje venv'inin `sys.executable`'ıyla DEĞİL,
    `kicad_python_yolunu_bul()`'un çözdüğü KiCad gömülü yorumlayıcısıyla
    kontrol eder. DÜZELTME (2026-07-31): eskiden `_python_import_kontrol`
    ile `sys.executable` kullanılıyordu — `pcbnew` bir PyPI paketi
    OLMADIĞI için bu, KiCad TAM KURULU ve `pcbnew` GERÇEKTEN kullanılabilir
    olsa BİLE her zaman FAIL üretiyordu (`kipy` de aynı çağrıya
    eklenmişti ve o ayrı bir opsiyonel IPC paketi — birinin eksikliği
    diğerinin PASS'ini gizliyordu). `kipy` artık AYRI ve opsiyonel olarak
    raporlanır (`_kipy_kontrol`), bu fonksiyon SADECE `pcbnew`'e bakar."""
    try:
        yol = kicad_python_yolunu_bul()
    except FileNotFoundError as hata:
        return AracDurumu("pcbnew (gerçek-board kontrolleri)", False, str(hata), "KURULUM.md madde 1")
    try:
        sonuc = subprocess.run(
            [yol, "-c", "import pcbnew; print(pcbnew.GetBuildVersion())"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as hata:
        return AracDurumu("pcbnew (gerçek-board kontrolleri)", False, f"çalıştırılamadı: {hata}", "KURULUM.md madde 1")
    if sonuc.returncode == 0:
        return AracDurumu("pcbnew (gerçek-board kontrolleri)", True, f"{yol} ({sonuc.stdout.strip()})", "KURULUM.md madde 1")
    hata_satiri = (sonuc.stderr or "").strip().splitlines()
    return AracDurumu(
        "pcbnew (gerçek-board kontrolleri)", False,
        hata_satiri[-1] if hata_satiri else "import başarısız", "KURULUM.md madde 1",
    )


def _kipy_kontrol() -> AracDurumu:
    """`kipy` (canlı KiCad IPC API'si, `pip install kicad-python`) proje
    venv'ine kurulur — `pcbnew`'in AKSİNE bu gerçek bir PyPI paketidir,
    bu yüzden `sys.executable` ile kontrolü DOĞRUDUR (bkz. `_pcbnew_kontrol`
    docstring'i, ikisini karıştırmamak için AYRIŞTIRILDI)."""
    return _python_import_kontrol("kipy (canlı KiCad IPC, opsiyonel)", "kipy", "KURULUM.md madde 2")


def tum_araclari_kontrol_et(kicad_cli: Optional[str] = None) -> List[AracDurumu]:
    """`KURULUM.md`'nin "Hızlı toplu doğrulama" bölümündeki TÜM araçları
    kontrol eder ve `AracDurumu` listesi döner.

    Bash'teki `A && B && C` zincirinden BİLİNÇLİ OLARAK FARKLI bir tasarım:
    orada ilk başarısız komut zinciri KESER ve sonraki araçlar hiç
    kontrol edilmez — kullanıcı "hangi ARAÇLARIN eksik olduğunu" değil
    sadece "İLK eksik aracı" görür. Burada HER araç bağımsız denenir, tek
    bir eksik/başarısız araç DİĞERLERİNİN kontrol edilmesini ENGELLEMEZ —
    tek bir çağrıda TAM tablo elde edilir. Bu aynı zamanda Windows
    PowerShell 5.1'in `&&` DESTEKLEMEMESİ sorununu da yapısal olarak
    çözer (bkz. `KURULUM.md` "Hızlı toplu doğrulama — PowerShell" notu):
    bash zincirleme sözdizimine hiç ihtiyaç kalmaz, tek bir Python
    çağrısı yeterlidir.
    """
    sonuclar: List[AracDurumu] = []

    try:
        yol, surum = kicad_cli_surumu_dogrula(kicad_cli)
        sonuclar.append(AracDurumu("KiCad CLI", True, f"{yol} ({surum})", "KURULUM.md madde 1"))
    except (FileNotFoundError, RuntimeError) as hata:
        sonuclar.append(AracDurumu("KiCad CLI", False, str(hata), "KURULUM.md madde 1"))

    sonuclar.append(_pcbnew_kontrol())
    sonuclar.append(_kipy_kontrol())
    sonuclar.append(_komut_kontrol("Node.js", ["node", "--version"], "KURULUM.md madde 3"))
    sonuclar.append(_komut_kontrol("Java", ["java", "-version"], "KURULUM.md madde 6"))
    sonuclar.append(_python_import_kontrol("JLC2KiCadLib", "JLC2KiCadLib", "KURULUM.md madde 7"))
    sonuclar.append(_komut_kontrol("KiBot", ["kibot", "--version"], "KURULUM.md madde 8"))
    sonuclar.append(_komut_kontrol("uv", ["uv", "--version"], "KURULUM.md madde 5"))
    sonuclar.append(_komut_kontrol(
        "pytest (dev grubu)", ["uv", "run", "--group", "dev", "pytest", "--version"],
        "KURULUM.md madde 5b", zaman_asimi_s=60,
    ))
    sonuclar.append(_komut_kontrol("git", ["git", "--version"], "KURULUM.md madde 9"))

    try:
        yol = pdftocairo_yolunu_bul()
        sonuclar.append(AracDurumu("pdftocairo (poppler)", True, yol, "KURULUM.md madde 11"))
    except FileNotFoundError as hata:
        sonuclar.append(AracDurumu("pdftocairo (poppler)", False, str(hata), "KURULUM.md madde 11"))
    sonuclar.append(_python_import_kontrol(
        "svglib/reportlab (dev grubu)", "svglib, reportlab", "KURULUM.md madde 11",
    ))

    return sonuclar
