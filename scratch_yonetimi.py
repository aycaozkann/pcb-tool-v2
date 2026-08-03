"""
scratch_yonetimi.py
====================
Scratch/canonical ayrımı — GÖREV 1 (governance katmanı, 2026-08-03).

NEDEN BU DOSYA VAR: `ProjectE`/`Otonom-PCB-Ajani` mimarisinde hiçbir otonom
oturum kanonik `.kicad_pro/.kicad_sch/.kicad_pcb` dosyalarına DİREKT
yazmaz — önce proje klasörünün bir scratch kopyasında çalışılır, kanonik
dosyaya geçiş (`main.py promote`) sadece TÜM kapılar (DRC/ERC + proje-özel
kontrat, bkz. `bagimsiz_dogrulama.py`) geçtiğinde olur. Bu, "aracın kendi
kendini yanıltıp temiz olmayan bir şeyi canlıya yazması"nı YAPISAL olarak
imkansız kılar — promotion olmadan kanonik dosya asla değişmez.

Bu modül `pcbnew` GEREKTİRMEZ — düz dosya kopyalama, `sch_wire.py`/
`coupled_astar_router.py` ile aynı "harici bağımlılık yok" felsefesi.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

SCRATCH_KOK_ADI = ".scratch"

# Bir proje kopyalanırken ASLA scratch'e taşınmaması gereken dizinler —
# git geçmişi, önceki scratch'ler, editör/IDE durumu.
VARSAYILAN_HARIC_TUT: Tuple[str, ...] = (SCRATCH_KOK_ADI, ".git", "__pycache__", ".obsidian", ".vscode", ".pytest_cache")


def scratch_id_uret() -> str:
    """Sıralanabilir, çakışma riski düşük bir kimlik: UTC zaman damgası."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def scratch_kok_dizini(project_dir: str) -> Path:
    return Path(project_dir).resolve() / SCRATCH_KOK_ADI


def scratch_olustur(
    project_dir: str,
    scratch_id: Optional[str] = None,
    haric_tut: Tuple[str, ...] = VARSAYILAN_HARIC_TUT,
) -> Path:
    """`project_dir`'i `<project_dir>/.scratch/<scratch_id>/` altına
    kopyalar, yeni kopyanın yolunu döner. Bu çağrı sırasında kanonik
    dosyalar SADECE OKUNUR — hiçbir kanonik dosyaya yazma/silme işlemi
    yapılmaz (kopyalama tek yönlüdür: kanonik → scratch)."""
    kaynak = Path(project_dir).resolve()
    if not kaynak.is_dir():
        raise FileNotFoundError(f"proje dizini yok: {kaynak}")
    sid = scratch_id or scratch_id_uret()
    hedef = scratch_kok_dizini(project_dir) / sid
    if hedef.exists():
        raise FileExistsError(f"scratch zaten var: {hedef} — farklı bir scratch_id kullan")
    hedef.parent.mkdir(parents=True, exist_ok=True)

    def yoksay(dizin: str, isimler: list) -> list:
        return [i for i in isimler if i in haric_tut]

    shutil.copytree(kaynak, hedef, ignore=yoksay)
    return hedef


def scratch_yolunu_dogrula(scratch_path: Path, project_dir: str) -> None:
    """Bir işlemin GERÇEKTEN scratch içinde çalıştığını (kanonik dizine
    kaçmadığını) doğrular. `scratch_path`, `project_dir/.scratch/` altında
    DEĞİLSE `ValueError` fırlatır — `kanonige_yukselt()`'in fail-closed
    ön koşulu budur, sessizce atlanmaz."""
    scratch_kok = scratch_kok_dizini(project_dir)
    try:
        Path(scratch_path).resolve().relative_to(scratch_kok.resolve())
    except ValueError as hata:
        raise ValueError(
            f"{scratch_path} scratch dizini ({scratch_kok}) içinde DEĞİL — "
            "kanonik dosyaya kazara yazma riski nedeniyle işlem durduruldu."
        ) from hata


def kanonige_yukselt(
    scratch_path: Path,
    project_dir: str,
    kalici_haric_tut: Tuple[str, ...] = (SCRATCH_KOK_ADI,),
) -> None:
    """Scratch'ten kanonik `project_dir`'e dosyaları kopyalar.

    BU FONKSİYON KENDİ BAŞINA HİÇBİR KAPI KONTROLÜ YAPMAZ — sadece
    `scratch_path`'in gerçekten scratch içinde olduğunu doğrular
    (`scratch_yolunu_dogrula`) ve kopyalar. DRC/ERC/proje-kontratı
    kapılarının GEÇTİĞİNİ doğrulamak `main.py::cmd_promote`'un işidir;
    bu fonksiyon sadece "kapılar zaten geçti, şimdi kopyala" adımıdır."""
    scratch_yolunu_dogrula(scratch_path, project_dir)
    hedef = Path(project_dir).resolve()
    kaynak = Path(scratch_path).resolve()
    for oge in kaynak.iterdir():
        if oge.name in kalici_haric_tut:
            continue
        hedef_oge = hedef / oge.name
        if oge.is_dir():
            shutil.copytree(oge, hedef_oge, dirs_exist_ok=True)
        else:
            shutil.copy2(oge, hedef_oge)


def scratch_listele(project_dir: str) -> list:
    """Var olan scratch id'lerini (en yeni önce) döner — `promote
    --scratch-id` için kullanıcıya seçenek göstermek amaçlı."""
    kok = scratch_kok_dizini(project_dir)
    if not kok.is_dir():
        return []
    return sorted((p.name for p in kok.iterdir() if p.is_dir()), reverse=True)
