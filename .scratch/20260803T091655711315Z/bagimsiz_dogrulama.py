"""
bagimsiz_dogrulama.py
======================
KiCad DRC/ERC'den TAMAMEN BAĞIMSIZ, PROJEYE ÖZEL kontratı ölçen ikinci
doğrulama katmanı — GÖREV 2 (governance katmanı, 2026-08-03).

NEDEN BU DOSYA VAR: KiCad'in genel DRC'si sadece jenerik kuralları bilir
(clearance/short/crossing/dangling-via). "Bu net class'ta iz genişliği HER
YERDE tam 0.2mm olmalı", "ETH_TRD0 çiftinin P/N uzunluk farkı
MASTER_RULEBOOK'un 15mm skew kuralını aşmamalı", "bu net sadece F.Cu'da
olmalı, başka katmanda segmenti varsa bu bir sızıntıdır" gibi PROJEYE ÖZEL
kontrat maddelerini KiCad DRC'si bilmez — "DRC temiz" demesi bu maddelerin
de doğru olduğu anlamına GELMEZ. Bu modül `.kicad_pcb`'yi KiCad'in ürettiği
DRC JSON'una hiç dokunmadan, kendi S-expr ayrıştırıcısıyla (pcbnew
GEREKMEZ — `sch_wire.py`/`coupled_astar_router.py` ile aynı felsefe)
okuyup projenin `DOCS/01_Design_Requirements.md` +
`DOCS/02_Stackup_and_Impedance.md`'sinden türetilen kontrata karşı ölçer.

`bulgu_sozlesmesi.Bulgu` kullanır: kontrat maddesi yoksa/parse
edilemezse `KAPSAM_YOK` — asla sessizce PASS sayılmaz (MASTER_RULEBOOK
"Rapor-Veri Tutarlılığı" maddesiyle aynı disiplin: yokluk iddiası ölçülmeden
yazılamaz).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret, ozet_rapor

MASTER_RULEBOOK_SKEW_TOLERANSI_MM = 15.0  # bkz. MASTER_RULEBOOK "Diferansiyel Faz Uyumu"


# ---------------------------------------------------------------------
# 1. Kontrat okuma — DOCS/02_Stackup_and_Impedance.md §3 tablosu
# ---------------------------------------------------------------------

@dataclass
class DiffCiftKontrati:
    """Bir diferansiyel çift (veya tek net) için proje-özel kontrat.
    `hedef_genislik_mm`/`skew_toleransi_mm` alanları None ise o ölçüm
    çağıran tarafından atlanır (kontratta belirtilmemiş demektir —
    UYDURULMAZ)."""

    isim: str
    hedef_genislik_mm: Optional[float] = None
    skew_toleransi_mm: float = MASTER_RULEBOOK_SKEW_TOLERANSI_MM
    zorunlu_katmanlar: Optional[frozenset] = None


_TABLO_SATIR_RE = re.compile(r"^\|(.+)\|\s*$")


def _markdown_tablo_satirlarini_oku(metin: str, baslik_iceren: str) -> List[List[str]]:
    """`baslik_iceren` alt başlığından sonraki İLK markdown tablosunun veri
    satırlarını (başlık + `---` ayırıcı satır HARİÇ) hücre listeleri olarak
    döner. Başlık/tablo bulunamazsa veya tüm satırlar boş/`-` ise boş liste
    döner — bu durumda çağıran taraf KAPSAM_YOK üretmelidir, PASS DEĞİL."""
    idx = metin.find(baslik_iceren)
    if idx == -1:
        return []
    satirlar = metin[idx:].splitlines()
    tablo_satirlari = [s for s in satirlar if _TABLO_SATIR_RE.match(s.strip())]
    if len(tablo_satirlari) < 2:
        return []
    veri: List[List[str]] = []
    for satir in tablo_satirlari[2:]:  # [0]=başlık satırı, [1]=--- ayırıcı
        hucreler = [h.strip() for h in satir.strip().strip("|").split("|")]
        if any(h and h != "-" for h in hucreler):
            veri.append(hucreler)
    return veri


def kontrati_oku(project_dir: str) -> List[DiffCiftKontrati]:
    """`project_dir/DOCS/02_Stackup_and_Impedance.md` §3 "Empedans
    Kontrollü Hatlar" tablosundan (`| Net/Çift | Arayüz | Hedef Z (Ω) |
    Çözülen W/S (mm) | ulasilabilir_mi | Length-match toleransı |`)
    kontrat listesini çıkarır. Dosya yoksa/tablo boşsa (henüz doldurulmamış
    TASLAK şablon) boş liste döner."""
    yol = Path(project_dir) / "DOCS" / "02_Stackup_and_Impedance.md"
    if not yol.exists():
        return []
    metin = yol.read_text(encoding="utf-8")
    satirlar = _markdown_tablo_satirlarini_oku(metin, "Empedans Kontrollü Hatlar")
    kontratlar: List[DiffCiftKontrati] = []
    for hucreler in satirlar:
        if len(hucreler) < 6 or not hucreler[0]:
            continue
        isim = hucreler[0]
        genislik = None
        m = re.match(r"([\d.]+)", hucreler[3])
        if m:
            genislik = float(m.group(1))
        tol_m = re.search(r"([\d.]+)\s*mm", hucreler[5])
        tol = float(tol_m.group(1)) if tol_m else MASTER_RULEBOOK_SKEW_TOLERANSI_MM
        kontratlar.append(DiffCiftKontrati(isim=isim, hedef_genislik_mm=genislik, skew_toleransi_mm=tol))
    return kontratlar


def katman_kontratini_oku(project_dir: str) -> Dict[str, frozenset]:
    """Opsiyonel `project_dir/DOCS/katman_kontrati.json` — `{"NET_DESENI":
    ["F.Cu"]}` biçiminde, hangi net deseninin hangi katman(lar)la SINIRLI
    olması gerektiğini tanımlar. Dosya yoksa boş sözlük (KAPSAM_YOK) —
    UYDURULMAZ, çünkü hangi netin hangi katmanda kalması gerektiği genel
    DOCS şablonlarında yok, proje-özel bir karardır."""
    import json

    yol = Path(project_dir) / "DOCS" / "katman_kontrati.json"
    if not yol.exists():
        return {}
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return {desen: frozenset(katmanlar) for desen, katmanlar in veri.items()}


# ---------------------------------------------------------------------
# 2. Board okuma — .kicad_pcb'yi pcbnew OLMADAN S-expr ile ayrıştır
# ---------------------------------------------------------------------

@dataclass
class IzSegmenti:
    net: str
    katman: str
    genislik_mm: float
    x1: float
    y1: float
    x2: float
    y2: float
    tip: str  # "segment" | "via" | "arc"

    @property
    def uzunluk_mm(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


def _blok_carpimlarini_bul(text: str, tag: str) -> List[str]:
    """Parantez derinliğini sayarak `(tag ...)` bloklarını (iç içe
    parantezlere karşı GÜVENLİ, `coupled_astar_router.py::extract_blocks`
    ile aynı teknik) çıkarır."""
    out: List[str] = []
    for m in re.finditer(r"\(" + tag + r"\b", text):
        start = m.start()
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append(text[start:i + 1])
    return out


def board_izlerini_oku(board_path: str) -> Dict[str, List[IzSegmenti]]:
    """`.kicad_pcb`'deki `segment`/`via`/`arc` bloklarını net adına göre
    gruplayarak döner. Net adı olmayan (net="") öğeler atlanır."""
    content = Path(board_path).read_text(encoding="utf-8")
    izler: Dict[str, List[IzSegmenti]] = {}

    def ekle(net: str, seg: IzSegmenti) -> None:
        izler.setdefault(net, []).append(seg)

    for blok in _blok_carpimlarini_bul(content, "segment"):
        net_m = re.search(r'\(net "([^"]*)"\)', blok)
        st = re.search(r"\(start ([\d.\-]+) ([\d.\-]+)\)", blok)
        en = re.search(r"\(end ([\d.\-]+) ([\d.\-]+)\)", blok)
        w = re.search(r"\(width ([\d.]+)\)", blok)
        layer = re.search(r'\(layer "([^"]*)"\)', blok)
        if not (net_m and st and en and w and layer) or not net_m.group(1):
            continue
        ekle(net_m.group(1), IzSegmenti(
            net=net_m.group(1), katman=layer.group(1), genislik_mm=float(w.group(1)),
            x1=float(st.group(1)), y1=float(st.group(2)),
            x2=float(en.group(1)), y2=float(en.group(2)), tip="segment",
        ))

    for blok in _blok_carpimlarini_bul(content, "arc"):
        net_m = re.search(r'\(net "([^"]*)"\)', blok)
        st = re.search(r"\(start ([\d.\-]+) ([\d.\-]+)\)", blok)
        en = re.search(r"\(end ([\d.\-]+) ([\d.\-]+)\)", blok)
        w = re.search(r"\(width ([\d.]+)\)", blok)
        layer = re.search(r'\(layer "([^"]*)"\)', blok)
        if not (net_m and st and en and w and layer) or not net_m.group(1):
            continue
        ekle(net_m.group(1), IzSegmenti(
            net=net_m.group(1), katman=layer.group(1), genislik_mm=float(w.group(1)),
            x1=float(st.group(1)), y1=float(st.group(2)),
            x2=float(en.group(1)), y2=float(en.group(2)), tip="arc",
        ))

    for blok in _blok_carpimlarini_bul(content, "via"):
        net_m = re.search(r'\(net "([^"]*)"\)', blok)
        at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)\)", blok)
        size = re.search(r"\(size ([\d.]+)\)", blok)
        layers = re.search(r"\(layers ([^\)]*)\)", blok)
        if not (net_m and at and size) or not net_m.group(1):
            continue
        # via'nın bulunduğu katmanlar (F.Cu/In2.Cu vb.) — sızıntı kontrolü
        # bir via'yı "yanlış katman" saymamalı, via zaten katman DEĞİŞTİRİR;
        # bu yüzden via'yı ayrı bir tip olarak işaretliyoruz, uzunluğu 0'dır.
        katman_str = layers.group(1) if layers else ""
        x, y = float(at.group(1)), float(at.group(2))
        ekle(net_m.group(1), IzSegmenti(
            net=net_m.group(1), katman=katman_str, genislik_mm=float(size.group(1)),
            x1=x, y1=y, x2=x, y2=y, tip="via",
        ))

    return izler


# ---------------------------------------------------------------------
# 3. Ölçümler — (a) iz genişliği dağılımı, (b) diff-pair skew, (c) katman sızıntısı
# ---------------------------------------------------------------------

def net_class_genislik_kontrolu(
    izler: Dict[str, List[IzSegmenti]], net_isim_deseni: str,
    beklenen_genislik_mm: float, tolerans_mm: float = 0.005,
) -> Bulgu:
    """(a) Deseniyle eşleşen TÜM net'lerin segment (via HARİÇ) genişlik
    dağılımını ölçer — tek bir sabit değer beklenirken varyans varsa
    (ör. bir kısmı 0.2mm bir kısmı 0.25mm çizilmiş) FAIL."""
    desen = re.compile(net_isim_deseni)
    eslesen = [s for net, segs in izler.items() if desen.search(net) for s in segs if s.tip == "segment"]
    if not eslesen:
        return bulgu_uret(f"iz_genisligi[{net_isim_deseni}]", 0)
    ihlaller = [
        {"net": s.net, "katman": s.katman, "olcum_mm": s.genislik_mm,
         "beklenen_mm": beklenen_genislik_mm, "fark_mm": round(abs(s.genislik_mm - beklenen_genislik_mm), 4)}
        for s in eslesen if abs(s.genislik_mm - beklenen_genislik_mm) > tolerans_mm
    ]
    return bulgu_uret(
        f"iz_genisligi[{net_isim_deseni}]", len(eslesen), ihlaller,
        f"beklenen={beklenen_genislik_mm}mm tolerans=±{tolerans_mm}mm",
    )


def _net_uzunlugu(segs: List[IzSegmenti]) -> float:
    return sum(s.uzunluk_mm for s in segs if s.tip in ("segment", "arc"))


def diff_cift_skew_kontrolu(
    izler: Dict[str, List[IzSegmenti]], cift_isim: str,
    p_sonek: str = "_P", n_sonek: str = "_N",
    tolerans_mm: float = MASTER_RULEBOOK_SKEW_TOLERANSI_MM,
) -> Bulgu:
    """(b) MASTER_RULEBOOK "Diferansiyel Faz Uyumu" kuralına göre P/N
    toplam iz uzunluğu farkını ölçer. Her iki net de board'da hiç
    yoksa (henüz routelanmamış) KAPSAM_YOK — "skew 0" diye YALANDAN
    PASS verilmez."""
    p_net, n_net = f"{cift_isim}{p_sonek}", f"{cift_isim}{n_sonek}"
    p_segs, n_segs = izler.get(p_net, []), izler.get(n_net, [])
    if not p_segs or not n_segs:
        return bulgu_uret(f"skew[{cift_isim}]", 0, detay=f"{p_net}/{n_net} routelanmamış")
    uzunluk_p, uzunluk_n = _net_uzunlugu(p_segs), _net_uzunlugu(n_segs)
    skew = abs(uzunluk_p - uzunluk_n)
    ihlaller = []
    if skew > tolerans_mm:
        ihlaller.append({
            "cift": cift_isim, "uzunluk_p_mm": round(uzunluk_p, 3),
            "uzunluk_n_mm": round(uzunluk_n, 3), "skew_mm": round(skew, 3),
            "tolerans_mm": tolerans_mm,
        })
    return bulgu_uret(f"skew[{cift_isim}]", 1, ihlaller, f"tolerans={tolerans_mm}mm")


def katman_sizintisi_kontrolu(
    izler: Dict[str, List[IzSegmenti]], net_isim_deseni: str, izinli_katmanlar: frozenset,
) -> Bulgu:
    """(c) Deseniyle eşleşen net(ler)in TÜM segment/arc'ları (via HARİÇ —
    via zaten katman değiştirmek için var, "sızıntı" değil) `izinli_katmanlar`
    dışında bir katmanda mı diye bakar."""
    desen = re.compile(net_isim_deseni)
    eslesen = [s for net, segs in izler.items() if desen.search(net) for s in segs if s.tip in ("segment", "arc")]
    if not eslesen:
        return bulgu_uret(f"katman_sizintisi[{net_isim_deseni}]", 0)
    ihlaller = [
        {"net": s.net, "katman": s.katman, "tip": s.tip}
        for s in eslesen if s.katman not in izinli_katmanlar
    ]
    return bulgu_uret(
        f"katman_sizintisi[{net_isim_deseni}]", len(eslesen), ihlaller,
        f"izinli={sorted(izinli_katmanlar)}",
    )


# ---------------------------------------------------------------------
# 4. Orkestratör
# ---------------------------------------------------------------------

def bagimsiz_dogrulama_calistir(board_path: str, project_dir: str) -> Dict[str, Any]:
    """Projenin `DOCS/02_Stackup_and_Impedance.md` kontratına + (varsa)
    `DOCS/katman_kontrati.json`'a karşı board'u ölçer. `bulgu_sozlesmesi.
    ozet_rapor()` formatında JSON-hazır sözlük döner."""
    kontratlar = kontrati_oku(project_dir)
    katman_kontrati = katman_kontratini_oku(project_dir)
    izler = board_izlerini_oku(board_path)

    bulgular: List[Bulgu] = []
    if not kontratlar:
        bulgular.append(bulgu_uret(
            "proje_kontrati", 0,
            detay="DOCS/02_Stackup_and_Impedance.md bulunamadı veya "
                  "'Empedans Kontrollü Hatlar' tablosu boş (TASLAK şablon)",
        ))
    for k in kontratlar:
        desen = re.escape(k.isim)
        if k.hedef_genislik_mm is not None:
            bulgular.append(net_class_genislik_kontrolu(izler, desen, k.hedef_genislik_mm))
        bulgular.append(diff_cift_skew_kontrolu(izler, k.isim, tolerans_mm=k.skew_toleransi_mm))

    for desen, katmanlar in katman_kontrati.items():
        bulgular.append(katman_sizintisi_kontrolu(izler, desen, katmanlar))
    if not katman_kontrati:
        bulgular.append(bulgu_uret(
            "katman_kontrati", 0,
            detay="DOCS/katman_kontrati.json yok — katman sızıntısı kontrolü atlandı",
        ))

    return ozet_rapor(bulgular)


def dogrulama_temiz_mi(ozet: Dict[str, Any]) -> bool:
    """Herhangi bir kontrol FAIL ise False. KAPSAM_YOK 'temiz' SAYILMAZ
    ama tek başına bu fonksiyonu da False YAPMAZ — kontrat hiç yoksa bu,
    KiCad DRC'nin zaten bilmediği bir kontrolün eksikliğidir, FAIL değil.
    Çağıran taraf (`main.py::cmd_promote`) KAPSAM_YOK durumunu AYRICA,
    açıkça "kontrat kontrolü yapılmadı" diye raporlamalıdır — sessizce
    PASS'a karıştırılmaz."""
    return not any(k["durum"] == BulguDurumu.FAIL.value for k in ozet["kontroller"])


def kapsam_yok_maddeleri(ozet: Dict[str, Any]) -> List[str]:
    return [k["kontrol"] for k in ozet["kontroller"] if k["durum"] == BulguDurumu.KAPSAM_YOK.value]
