"""pcb_gorsel_kesit.py için test suite (pytest).

DÜRÜSTLÜK NOTU: `bolge_goruntule()`'nin uçtan uca akışı gerçek `kicad-cli`
+ `svglib`/`reportlab` + `pdftocairo` (poppler) gerektirir — bu testler
o zinciri GERÇEKTEN çalıştırır (hepsi bu makinede kurulu), ama
`edge_cuts_sinirlarini_bul()` (pcbnew/kicad-cli gerektirmeyen, saf metin
ayrıştırma) ayrıca izole test edilir ki gerçek araçlar eksik bir
makinede de bu kısmın doğruluğu kilitli kalsın.
"""

from __future__ import annotations

import shutil

import pytest

from pcb_gorsel_kesit import (
    SinirKutusu,
    _sinirlari_metinden_cikar,
    edge_cuts_sinirlarini_bul,
    oz_testleri_calistir,
)

_SENTETIK = """(kicad_pcb
  (gr_line (start -10 -5) (end 10 -5) (layer "Edge.Cuts") (uuid "a"))
  (gr_line (start 10 -5) (end 10 5) (layer "Edge.Cuts") (uuid "b"))
  (gr_line (start 10 5) (end -10 5) (layer "Edge.Cuts") (uuid "c"))
  (gr_line (start -10 5) (end -10 -5) (layer "Edge.Cuts") (uuid "d"))
  (gr_line (start 0 0) (end 1 1) (layer "F.Cu") (uuid "e"))
)
"""


def test_modulun_kendi_oz_testleri_temiz():
    assert oz_testleri_calistir() == []


def test_sinir_kutusu_pozitif_alan_zorunlu():
    with pytest.raises(ValueError):
        SinirKutusu(0, 0, 0, 10)


def test_edge_cuts_disindaki_katmanlar_yoksayilir():
    sinir = _sinirlari_metinden_cikar(_SENTETIK)
    assert (sinir.x_min, sinir.y_min, sinir.x_max, sinir.y_max) == (-10, -5, 10, 5)


def test_edge_cuts_yoksa_hata_verir():
    with pytest.raises(ValueError):
        _sinirlari_metinden_cikar('(kicad_pcb (gr_line (start 0 0) (end 1 1) (layer "F.Cu")))')


def test_edge_cuts_sinirlarini_bul_dosyadan_okur(tmp_path):
    pcb = tmp_path / "test.kicad_pcb"
    pcb.write_text(_SENTETIK, encoding="utf-8")
    sinir = edge_cuts_sinirlarini_bul(str(pcb))
    assert sinir.genislik == 20
    assert sinir.yukseklik == 10


@pytest.mark.skipif(
    not (shutil.which("pdftocairo") or True),  # arac_yollari kendi fallback'ini dener
    reason="poppler bulunamadı",
)
def test_bolge_goruntule_gercek_esp32_kartina_karsi(tmp_path):
    """Gerçek ESP32C3_SmartBand.kicad_pcb'ye karşı UÇTAN UCA test — bu
    makinede kicad-cli + svglib + poppler kuruluysa GERÇEKTEN koşar."""
    pytest.importorskip("svglib")
    pytest.importorskip("reportlab")
    import os

    board = (
        r"C:\Users\Dell\Desktop\ESP32-C3 Smart Board "
        r"(Li-IonLiPo + MPU6050 + GC9A01 yuvarlak ekran + USB-C)"
        r"\pcb-designer-tool\ESP32C3_SmartBand.kicad_pcb"
    )
    if not os.path.isfile(board):
        pytest.skip("ESP32C3_SmartBand.kicad_pcb bu makinede bulunamadı")

    from pcb_gorsel_kesit import bolge_goruntule

    cikti = tmp_path / "kesit.png"
    yol = bolge_goruntule(
        board, str(cikti), x1_mm=1, y1_mm=-5, x2_mm=15, y2_mm=4,
        katmanlar=["F.Cu", "Edge.Cuts"], dpi=300, buyutme=1.0,
    )
    from PIL import Image

    im = Image.open(yol)
    assert im.width > 50 and im.height > 50
