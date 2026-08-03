"""
test_gercek_board_dogrulama.py
================================
GÖREV 2 (kullanıcı isteği, 2026-07-31): GÖREV 10/11'de mock'larla test
edilen `freerouting_zaman_asiminda_otonom_devam_et()` ve
`en_yakin_footprint_bul()`'ın GERÇEK bir `.kicad_pcb` üzerinde ÇÖKMEDEN
çalıştığını kanıtlayan, bu makinede GERÇEKTEN koşan testler.

`test_uretim_zinciri_freerouting.py` BİLEREK sadece mock kullanıyor
(dosyanın kendi docstring'i) — bu dosya onun YERİNE değil YANINA durur,
gerçek-donanım kanıtı için ayrı tutuldu.

KiCad'in `multichannel_mixer-unrouted.kicad_pcb` demo board'u (gerçek,
kısmen yönlendirilmemiş bir board — sentetik/tam-yönlendirilmiş demo'lardan
FARKLI olarak GERÇEK `unconnected_items` üretir) kullanılıyor.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from drc_ozetleyici import en_yakin_footprint_bul
from uretim_zinciri_koprusu import freerouting_zaman_asiminda_otonom_devam_et


def _kicad_python_var_mi() -> bool:
    try:
        from arac_yollari import kicad_python_yolunu_bul

        kicad_python_yolunu_bul()
        return True
    except FileNotFoundError:
        return False


def _kicad_demo_board_bul(isim: str) -> Path | None:
    import os

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    kok = Path(program_files) / "KiCad"
    if not kok.is_dir():
        return None
    adaylar = sorted(kok.glob(f"*/share/kicad/demos/**/{isim}"), reverse=True)
    return adaylar[0] if adaylar else None


pytestmark = pytest.mark.skipif(
    not _kicad_python_var_mi(), reason="Bu makinede KiCad'in gömülü Python'u (pcbnew) bulunamadı",
)


@pytest.fixture
def unrouted_board(tmp_path):
    kaynak = _kicad_demo_board_bul("multichannel_mixer-unrouted.kicad_pcb")
    if kaynak is None:
        pytest.skip("multichannel_mixer-unrouted.kicad_pcb demo board'u bulunamadı")
    hedef = tmp_path / "unrouted.kicad_pcb"
    shutil.copy(kaynak, hedef)
    return hedef


def test_en_yakin_footprint_bul_gercek_boardda_cokmez(unrouted_board):
    """GÖREV 2: mock'lardan bağımsız, GERÇEK bir board'da çökmeden çalışıp
    anlamlı bir footprint referansı döndürdüğünü kanıtlar."""
    ref = en_yakin_footprint_bul((100.0, 80.0), board_path=str(unrouted_board))
    assert ref is not None
    assert isinstance(ref, str)
    assert len(ref) > 0


def test_freerouting_fallback_gercek_boardda_cokmez_ve_dosya_yazar(unrouted_board, tmp_path):
    """GÖREV 2: `freerouting_zaman_asiminda_otonom_devam_et()`'in GERÇEK,
    kısmen yönlendirilmemiş bir board'da (a) exception FIRLATMADIĞINI,
    (b) yapısal olarak doğru bir sonuç sözlüğü ürettiğini, (c) başarısız
    netler için gerçekten `TEST/needs_human_*.json` dosyası yazdığını
    kanıtlar (mock DEĞİL — gerçek DRC + gerçek pcbnew footprint extraction
    + gerçek otonom_kurtarma_motoru denemesi)."""
    sonuc = freerouting_zaman_asiminda_otonom_devam_et(
        str(unrouted_board), calisma_dizini=str(tmp_path),
    )

    assert isinstance(sonuc, dict)
    for anahtar in ("toplam_net", "yonlendirilen_net", "basarisiz_net_sayisi", "detaylar"):
        assert anahtar in sonuc
    assert sonuc["toplam_net"] == sonuc["yonlendirilen_net"] + sonuc["basarisiz_net_sayisi"]
    assert isinstance(sonuc["detaylar"], list)

    if sonuc["basarisiz_net_sayisi"] > 0:
        needs_human_dosyalari = list((tmp_path / "TEST").glob("needs_human_*.json"))
        assert len(needs_human_dosyalari) == sonuc["basarisiz_net_sayisi"], (
            "Başarısız net sayısı ile yazılan needs_human_*.json dosya sayısı UYUŞMUYOR "
            "— bu, bazı başarısız netlerin sessizce KAYBOLDUĞU anlamına gelebilir."
        )
        icerik = json.loads(needs_human_dosyalari[0].read_text(encoding="utf-8"))
        assert icerik["sonuc"] == "NEEDS_HUMAN"
        assert "notlar" in icerik and len(icerik["notlar"]) > 0
