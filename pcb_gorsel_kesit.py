#!/usr/bin/env python3
"""
pcb_gorsel_kesit.py
======================
Claude Code'a (bu proje üzerinde çalışan HERHANGİ bir ajana) gerçek
"görme" yeteneği kazandıran modül — 2026-07-30'da ESP32-C3 Smart Band
kartında U2'nin (LGA-14, 0.5mm pitch) çevresini koordinat-bazlı "kör"
routing ile bağlamaya çalışırken (4 ayrı başarısız deneme, hepsi güvenle
geri alındı — bkz. `HAFIZA/Hafiza_Defteri.md`) doğdu. O oturumda "board'u
gerçekten GÖREBİLSEM bu kadar tahmin etmezdim" sorusuna verilen cevap.

NEDEN BU ZİNCİR (basitten karmaşığa denenip elenen alternatifler):
-------------------------------------------------------------------------
- `mcp__kicad__get_board_2d_view` (inline mod): görüntü MCP mesaj boyutu
  sınırını (yaklaşık) aşıyor, büyük/yoğun kartlarda kullanılamaz.
- `mcp__kicad__get_board_2d_view` (PNG, file mod): bu makinede PNG
  dönüştürücü (pymupdf/inkscape/imagemagick) YOK, sessizce SVG'ye düşüyor.
- SVG'yi doğrudan `Read` ile "görmek": `Read` SVG'yi XML METNİ olarak
  okur, GÖRSEL olarak RENDER ETMEZ — ajan pikselleri göremez, sadece
  vektör komutlarını (koordinat listesi) okur, ki bu zaten elimizdeki
  kör-koordinat sorununun ta kendisi.
- Çözüm: `kicad-cli`'nin KENDİSİ zaten SVG/PDF üretebiliyor (network YOK,
  100% yerel) — sadece SVG'yi RASTER (PNG) formatına çevirecek bir
  aracın eksikliği vardı. `svglib`+`reportlab` (saf Python, native
  bağımlılık yok, pip ile kurulur) SVG->PDF yapıyor; bu makinede zaten
  kurulu olan `poppler` (`pdftocairo`) PDF->PNG yapıyor. İkisi birlikte,
  hiçbir yerel GUI aracı (Inkscape/ImageMagick) kurulu olmasa bile
  çalışıyor — TAŞINABİLİRLİK bu projenin genel felsefesiyle (bkz.
  `arac_yollari.py`) birebir uyumlu.

DOĞRULUK NOTU (dürüstlük çerçevesi — bu proje genelindeki disiplin):
-------------------------------------------------------------------------
`kicad-cli pcb export svg --page-size-mode 2 --fit-page-to-board`'un
ürettiği SVG'nin (0,0) köşesinin board'un Edge.Cuts bbox'unun
(x_min, y_min) köşesine, 1 SVG biriminin TAM 1mm'ye oturduğu VARSAYIMI
bu projede `ESP32C3_SmartBand.kicad_pcb`'ye karşı AMPİRİK olarak
doğrulandı: `mcp__kicad__get_board_extents()` (-21.05, -21.05) ile
SVG viewBox'ın ima ettiği yarı-genişlik (~20.9931) arasında ~0.06mm'lik
bir fark var (dairesel kenarın yay-örneklemesinden kaynaklanıyor,
`edge_cuts_sinirlarini_bul()`'un KENDİ sınırındaki not budur).
**BU FONKSİYON SADECE GÖRSEL YÖNLENDİRME İÇİNDİR** — ölçüm/DRC/üretim
kararı için KULLANILMAMALI, o kararlar zaten `kicad_koprusu.py`/
`pcbnew_koprusu.py`'nin gerçek `kicad-cli`/`pcbnew` tabanlı fonksiyonlarına
aittir. Bu modülün TEK işi: bir mm bölgesini bir PNG'ye çevirip, `Read`
aracıyla (veya herhangi bir görüntü okuyabilen ajanla) gerçekten
GÖRÜLEBİLİR kılmak.

Kullanım (özet):
    from pcb_gorsel_kesit import bolge_goruntule
    bolge_goruntule(
        "ESP32C3_SmartBand.kicad_pcb", "u2_kesit.png",
        x1_mm=1, y1_mm=-5, x2_mm=15, y2_mm=4,
        katmanlar=["F.Cu", "Edge.Cuts"], buyutme=2.0,
    )
    # sonra: Read tool ile "u2_kesit.png" oku — ajan artık GERÇEKTEN görür.

CLI:
    uv run python pcb_gorsel_kesit.py board.kicad_pcb --bolge 1,-5,15,4 \
        --katmanlar F.Cu,Edge.Cuts --cikti kesit.png --buyutme 2
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from arac_yollari import kicad_cli_yolunu_bul, pdftocairo_yolunu_bul


@dataclass(frozen=True)
class SinirKutusu:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError(f"Geçersiz sınır kutusu: {self}")

    @property
    def genislik(self) -> float:
        return self.x_max - self.x_min

    @property
    def yukseklik(self) -> float:
        return self.y_max - self.y_min


def edge_cuts_sinirlarini_bul(pcb_yolu: str) -> SinirKutusu:
    """`.kicad_pcb`'yi regex ile tarayıp Edge.Cuts katmanındaki çizim
    öğelerinin (gr_line/gr_arc/gr_circle/gr_rect/gr_poly) kapsadığı
    bbox'u hesaplar. `pcbnew` GEREKTİRMEZ (`sch_wire.py`'nin S-Expr
    parse felsefesiyle AYNI — bu ortamda pcbnew kurulu değil).

    SINIR (bilerek basit tutuldu): yaylar için sadece start/mid/end
    kontrol noktaları kullanılır, gerçek yayın dışbükey noktası değil —
    dairesel/eğri bir kenarda hesaplanan bbox GERÇEK bbox'tan biraz DAR
    çıkabilir (bu projede ~0.06mm ölçüldü). Bu fonksiyon SADECE ekran
    kesiti kırpma için kullanılır; ölçüm/DRC amaçlı DEĞİLDİR.
    """
    metin = Path(pcb_yolu).read_text(encoding="utf-8")
    return _sinirlari_metinden_cikar(metin)


def _blok_sinirini_bul(metin: str, baslangic: int) -> int:
    """`baslangic` indeksindeki `(` ile eşleşen kapanış `)`'nin indeksini
    PARANTEZ DERİNLİĞİ sayarak bulur (string içindeki parantezleri atlar).

    NEDEN (naif regex DEĞİL): `(gr_circle (center 0 0) (end 21 0)
    (stroke (width 0.1) (type default)) ...)` gibi İÇ İÇE bloklarda,
    "satır sonu + kapanan parantez" arayan bir regex `(stroke ...)`'un
    KENDİ kapanışında durur — `gr_circle`'ın asıl kapanışına hiç
    ulaşmaz. Bu proje genelinde `sch_wire.py::_block()` ile AYNI çözüm
    (derinlik sayacı) kullanılır; burada bağımsız bir kopyası var çünkü
    bu modül `sch_wire.py`'ye (şematik'e özgü) bağımlı OLMAMALI.
    """
    derinlik = 0
    i = baslangic
    n = len(metin)
    while i < n:
        c = metin[i]
        if c == '"':
            i += 1
            while i < n and metin[i] != '"':
                i += 2 if metin[i] == "\\" else 1
        elif c == "(":
            derinlik += 1
        elif c == ")":
            derinlik -= 1
            if derinlik == 0:
                return i
        i += 1
    raise ValueError("S-expression bloğu kapanmadan dosya sonuna ulaşıldı (bozuk .kicad_pcb?)")


def _sinirlari_metinden_cikar(metin: str) -> SinirKutusu:
    noktalar: list[tuple[float, float]] = []
    for basla_m in re.finditer(r'\((gr_line|gr_arc|gr_circle|gr_rect|gr_poly)\b', metin):
        blok_baslangic = basla_m.start()
        blok_bitis = _blok_sinirini_bul(metin, blok_baslangic)
        blok = metin[blok_baslangic:blok_bitis + 1]
        if "Edge.Cuts" not in blok:
            continue
        yerel_noktalar = [
            (float(m.group(1)), float(m.group(2)))
            for m in re.finditer(r'\((?:start|end|mid|center|xy)\s+(-?[\d.]+)\s+(-?[\d.]+)\)', blok)
        ]
        merkez_m = re.search(r'\(center\s+(-?[\d.]+)\s+(-?[\d.]+)\)', blok)
        uc_m = re.search(r'\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', blok)
        if basla_m.group(1) == "gr_circle" and merkez_m and uc_m:
            # Dairenin KENDİSİ (center+end=yarıçap noktası) sadece TEK bir
            # noktayı (end) değil, TÜM çevreyi kapsar — bbox'a merkez±yarıçap
            # eklenmeli, yoksa bbox dairenin bir kenarına sıkışıp kalır.
            cx, cy = merkez_m.group(1), merkez_m.group(2)
            cx, cy = float(cx), float(cy)
            ex, ey = float(uc_m.group(1)), float(uc_m.group(2))
            r = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            noktalar += [(cx - r, cy - r), (cx + r, cy + r)]
        else:
            noktalar += yerel_noktalar
    if not noktalar:
        raise ValueError(
            "Edge.Cuts üzerinde hiç nokta bulunamadı — board outline yok, "
            "farklı bir katmanda, veya .kicad_pcb formatı beklenenden farklı."
        )
    xs = [p[0] for p in noktalar]
    ys = [p[1] for p in noktalar]
    return SinirKutusu(min(xs), min(ys), max(xs), max(ys))


def bolge_goruntule(
    pcb_yolu: str,
    hedef_png: str,
    x1_mm: float,
    y1_mm: float,
    x2_mm: float,
    y2_mm: float,
    katmanlar: Sequence[str] = ("F.Cu", "Edge.Cuts"),
    dpi: int = 1200,
    buyutme: float = 2.0,
    kicad_cli: str | None = None,
    pdftocairo: str | None = None,
    gecici_dizin: str | None = None,
) -> str:
    """Board'un (x1_mm,y1_mm)-(x2_mm,y2_mm) dikdörtgenini GERÇEK bir PNG
    görüntüsü olarak üretir — dosya başlığındaki zincire bakınız.
    Dönen değer: yazılan PNG dosyasının yolu (verilen `hedef_png` ile aynı).
    """
    from PIL import Image

    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
    except ImportError as exc:
        raise ImportError(
            "svglib/reportlab kurulu değil — `uv add --dev svglib reportlab` "
            "ile ekle (bu proje dev grubuna zaten eklenmiş olmalı, bkz. "
            "pyproject.toml)."
        ) from exc

    sinir = edge_cuts_sinirlarini_bul(pcb_yolu)
    gecici = Path(gecici_dizin) if gecici_dizin else Path(hedef_png).resolve().parent
    gecici.mkdir(parents=True, exist_ok=True)
    svg_yolu = gecici / "_pcb_gorsel_kesit_tam.svg"
    pdf_yolu = gecici / "_pcb_gorsel_kesit_tam.pdf"
    png_tam_yolu = gecici / "_pcb_gorsel_kesit_tam.png"

    cli = kicad_cli_yolunu_bul(kicad_cli)
    komut = [
        cli, "pcb", "export", "svg",
        "--layers", ",".join(katmanlar),
        "--page-size-mode", "2", "--fit-page-to-board", "--mode-single",
        "-o", str(svg_yolu), pcb_yolu,
    ]
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    if sonuc.returncode != 0 or not svg_yolu.exists():
        raise RuntimeError(f"kicad-cli SVG dışa aktarımı başarısız:\n{sonuc.stdout}\n{sonuc.stderr}")

    cizim = svg2rlg(str(svg_yolu))
    renderPDF.drawToFile(cizim, str(pdf_yolu))

    pdftocairo_yol = pdftocairo_yolunu_bul(pdftocairo)
    sonuc2 = subprocess.run(
        [pdftocairo_yol, "-png", "-r", str(dpi), "-singlefile",
         str(pdf_yolu), str(png_tam_yolu.with_suffix(""))],
        capture_output=True, text=True,
    )
    if sonuc2.returncode != 0 or not png_tam_yolu.exists():
        raise RuntimeError(f"pdftocairo PNG dışa aktarımı başarısız:\n{sonuc2.stdout}\n{sonuc2.stderr}")

    tam = Image.open(png_tam_yolu)
    px_per_mm = tam.width / sinir.genislik

    def px(x_mm: float, y_mm: float) -> tuple[float, float]:
        return ((x_mm - sinir.x_min) * px_per_mm, (y_mm - sinir.y_min) * px_per_mm)

    px_x1, px_y1 = px(min(x1_mm, x2_mm), min(y1_mm, y2_mm))
    px_x2, px_y2 = px(max(x1_mm, x2_mm), max(y1_mm, y2_mm))
    px_x1, px_y1 = max(0, int(px_x1)), max(0, int(px_y1))
    px_x2, px_y2 = min(tam.width, int(px_x2)), min(tam.height, int(px_y2))
    if px_x2 <= px_x1 or px_y2 <= px_y1:
        raise ValueError(
            f"İstenen bölge ({x1_mm},{y1_mm})-({x2_mm},{y2_mm}) board "
            f"sınırlarının ({sinir.x_min},{sinir.y_min})-"
            f"({sinir.x_max},{sinir.y_max}) dışında/geçersiz."
        )
    kesit = tam.crop((px_x1, px_y1, px_x2, px_y2))
    if buyutme != 1.0:
        kesit = kesit.resize(
            (max(1, int(kesit.width * buyutme)), max(1, int(kesit.height * buyutme))),
            Image.LANCZOS,
        )
    kesit.save(hedef_png)

    for gecici_dosya in (svg_yolu, pdf_yolu, png_tam_yolu):
        gecici_dosya.unlink(missing_ok=True)

    return hedef_png


# ------------------------------------------------------------------
# ÖZ-TEST (sadece pcbnew/kicad-cli GEREKTİRMEYEN bbox ayrıştırıcı kısmı —
# `bolge_goruntule()`'nin uçtan uca akışı GERÇEK kicad-cli + svglib +
# poppler gerektirir, bu ortamda `test_sch_wire.py` ile AYNI disiplinle
# SENİN makinende ayrıca doğrulanmalı.)
# ------------------------------------------------------------------

_SENTETIK_KART = """(kicad_pcb
  (gr_line (start -10 -5) (end 10 -5) (layer "Edge.Cuts") (uuid "a"))
  (gr_line (start 10 -5) (end 10 5) (layer "Edge.Cuts") (uuid "b"))
  (gr_line (start 10 5) (end -10 5) (layer "Edge.Cuts") (uuid "c"))
  (gr_line (start -10 5) (end -10 -5) (layer "Edge.Cuts") (uuid "d"))
  (gr_line (start 0 0) (end 1 1) (layer "F.Cu") (uuid "e"))
)
"""


_SENTETIK_YUVARLAK_KART = """(kicad_pcb
  (gr_circle
    (center 0 0)
    (end 21 0)
    (stroke (width 0.1) (type default))
    (fill no)
    (layer "Edge.Cuts")
    (uuid "x")
  )
)
"""


def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: F.Cu üzerindeki bir çizgi Edge.Cuts sınırını
    GENİŞLETMEMELİ — ayrıştırıcı katman filtresini gerçekten uyguluyor mu?"""
    sinir = _sinirlari_metinden_cikar(_SENTETIK_KART)
    return sinir.x_min == -10 and sinir.x_max == 10 and sinir.y_min == -5 and sinir.y_max == 5


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    sinir = _sinirlari_metinden_cikar(_SENTETIK_KART)
    if (sinir.x_min, sinir.y_min, sinir.x_max, sinir.y_max) != (-10, -5, 10, 5):
        hatalar.append(f"sentetik kart bbox yanlış: {sinir}")
    if sinir.genislik != 20 or sinir.yukseklik != 10:
        hatalar.append("genislik/yukseklik property'leri yanlış")

    try:
        SinirKutusu(0, 0, 0, 5)
        hatalar.append("sıfır genişlikli SinirKutusu reddedilmedi")
    except ValueError:
        pass

    try:
        _sinirlari_metinden_cikar("(kicad_pcb (gr_line (start 0 0) (end 1 1) (layer \"F.Cu\")))")
        hatalar.append("Edge.Cuts olmayan kart hata fırlatmadı")
    except ValueError:
        pass

    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: F.Cu çizgisi Edge.Cuts bbox'unu etkiledi")

    # İÇ İÇE BLOK REGRESYONU: gr_circle içindeki (stroke (width..) (type..))
    # gibi iç içe bloklar, derinlik-sayacı olmayan naif bir regex'i
    # `stroke`'un KENDİ kapanışında durdurup gr_circle'ın asıl kapanışına
    # hiç ulaşmadan yanlış/eksik bbox üretebilir (bu modülün GERÇEK
    # ESP32C3_SmartBand.kicad_pcb'ye karşı ilk denemesinde YAKALANAN bir
    # regresyondu — dairesel board kenarı).
    sinir_daire = _sinirlari_metinden_cikar(_SENTETIK_YUVARLAK_KART)
    if (sinir_daire.x_min, sinir_daire.y_min, sinir_daire.x_max, sinir_daire.y_max) != (-21, -21, 21, 21):
        hatalar.append(f"dairesel (gr_circle) board kenarı bbox'u yanlış: {sinir_daire}")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pcb", nargs="?", help=".kicad_pcb yolu (--oztest ile birlikte gerekmez)")
    p.add_argument("--bolge", help="x1,y1,x2,y2 (mm), örn: 1,-5,15,4")
    p.add_argument("--katmanlar", default="F.Cu,Edge.Cuts")
    p.add_argument("--cikti", default="kesit.png")
    p.add_argument("--dpi", type=int, default=1200)
    p.add_argument("--buyutme", type=float, default=2.0)
    p.add_argument("--oztest", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _olustur_parser().parse_args(argv)

    hatalar = oz_testleri_calistir()
    for h in hatalar:
        print(f"ÖZ-TEST FAIL: {h}", file=sys.stderr)
    if hatalar:
        return 1
    print("ÖZ-TEST PASS: Edge.Cuts sınır ayrıştırıcı temiz.")

    if args.oztest:
        return 0
    if not args.pcb or not args.bolge:
        print("Kullanım: pcb_gorsel_kesit.py board.kicad_pcb --bolge x1,y1,x2,y2 [--cikti kesit.png]")
        return 0

    x1, y1, x2, y2 = (float(v) for v in args.bolge.split(","))
    yol = bolge_goruntule(
        args.pcb, args.cikti, x1, y1, x2, y2,
        katmanlar=args.katmanlar.split(","), dpi=args.dpi, buyutme=args.buyutme,
    )
    print(f"Yazıldı: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
