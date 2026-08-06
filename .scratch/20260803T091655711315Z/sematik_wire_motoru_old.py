"""
sematik_wire_motoru_old.py (DEPRECATED — YERİNE `sch_wire.py` KULLANILIYOR)
=============================================================================
2026-07-30: Bu dosya artık BİRİNCİL şematik wire motoru DEĞİL. `Otonom-PCB-
Ajani` projesinden alınan `sch_wire.py` (aynı mimari, İngilizce isimlendirme
+ Windows/kicad-cli-yolu düzeltmeleri bu dosyadan oraya taşındı) onun yerini
aldı — bkz. `CLAUDE.md` madde 4. Bu dosya SİLİNMEDİ, yalnızca regresyon
referansı/tarihçe için tutuluyor; yeni kod bunu import ETMEMELİ.

sematik_wire_motoru.py (orijinal başlık, aşağıda korunmuştur)
========================
PROJENİN İKİNCİ BÜYÜK MİMARİ BOŞLUĞUNU KAPATAN MODÜL.

`CLAUDE.md` şematik üretimini `mcp__kicad__*` (mixelpixx/KiCAD-MCP-Server)
araçlarına bırakıyordu — ama `kicad_koprusu.py`'nin kendi Ek-A notu bu
MCP'nin bilinen hatalarını listeliyor (`sync_schematic_to_board` yanlış
nete pin yazabiliyor vb.) ve "her kritik neti kicad-cli ile bağımsız
doğrula" diyor. Yani MCP'ye GÜVENMEMEK vardı ama YERİNE GEÇECEK KOD yoktu.

Bu dosya o kodu sağlar: KiCad 10 şematiğine (`.kicad_sch`, S-Expression
formatı) GERÇEK `(wire)` / `(junction)` / `(label)` / güç sembolü üreten,
harici bağımlılığı olmayan (sadece stdlib + `kicad-cli` subprocess) bir
kütüphane.

KANIT DİSİPLİNİ (proje CLAUDE.md honesty çerçevesiyle birebir uyumlu):
Görsel çizgi bağlantı DEMEK DEĞİLDİR. Bağlantının TEK kanıtı
`kicad-cli sch export netlist` çıktısıdır -> `netlist_nets()` +
`dogrula_netler()`. Bu modülün ürettiği hiçbir wire, netlist ile
doğrulanmadan "bağlandı" sayılmamalı.

Kullanım (özet):
    kutuphane = kutuphane_yukle("/usr/share/kicad/symbols/Device.kicad_sym")
    sch = SematikUretici(proje="demo")
    sch.gom(kutuphane["R"], "Device:R")
    r1 = sch.yerlestir("R1", "Device:R", 100, 100, deger="5k1")
    sch.pin_pin_baglantisi(r1.pin("2"), r2.pin("1"))
    sch.etiket(r1.pin("2"), "USB_CC1")
    sch.yaz("demo.kicad_sch")   # .bak + KiCad-kapalı kontrolü

AĞ/ARAÇ UYARISI: `kicad-cli` gerektiren fonksiyonlar (`netlist_nets`,
`dogrula_netler`, `erc_calistir`) bu ortamda ÇALIŞTIRILAMADI (KiCad kurulu
değil) — sadece S-Expr üretim/parse tarafı (kicad-cli gerektirmeyen kısım)
bu ortamda test edildi. Gerçek doğrulama SENİN makinende, gerçek
`kicad-cli` ile yapılmalı (bkz. `KURULUM.md` madde 1).
"""

from __future__ import annotations

import math
import os
import platform
import re
import shutil
import subprocess
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from arac_yollari import kicad_cli_yolunu_bul

GRID = 1.27          # KiCad şematik bağlantı grid'i (mm). 2.54 tercih edilir.
STUB = 2.54          # pin ucundan çıkan varsayılan kısa wire


# --------------------------------------------------------------------------- #
# S-Expression yardımcıları
# --------------------------------------------------------------------------- #
def sexpr_parse(text: str, start: int = 0):
    """Metni iç içe liste ağacına çevirir. Atomlar str olarak kalır."""
    tokens = re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text[start:])
    stack: List[list] = []
    root = None
    for m in tokens:
        tok = m.group(0)
        if tok == "(":
            node: list = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif tok == ")":
            root = stack.pop()
            if not stack:
                return root
        else:
            if stack:
                stack[-1].append(tok)
    return root


def tirnaksiz(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == '"':
        return tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return tok


def tirnakli(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sayi(v: float) -> str:
    """Grid drift'i engelle: 2 ondalık, kayan-nokta artığı yok.
    195.57999999999998 gibi kalıntılar wire ucunu pin'den ayırıp sessiz
    kopukluk yaratır."""
    v = round(float(v) + 0.0, 2)
    return f"{v:g}"


def _bul(node, anahtar: str):
    for c in node:
        if isinstance(c, list) and c and c[0] == anahtar:
            return c
    return None


def _bul_hepsi(node, anahtar: str):
    return [c for c in node if isinstance(c, list) and c and c[0] == anahtar]


# --------------------------------------------------------------------------- #
# Sembol / pin modeli
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Pin:
    numara: str
    isim: str
    x: float          # lib koordinatı (Y YUKARI)
    y: float
    aci: float        # pin'in gövdeye BAKAN yönü (KiCad konvansiyonu)
    uzunluk: float
    etype: str        # passive / power_in / input / ...
    unit: int


@dataclass
class KutuphaneSembolu:
    isim: str
    pinler: List[Pin]
    metin: str        # ham S-Expr bloğu (lib_symbols'a gömmek için)

    def pin(self, numara: str) -> Pin:
        for p in self.pinler:
            if p.numara == numara:
                return p
        raise KeyError(f"{self.isim}: pin {numara!r} yok "
                       f"(mevcut: {[p.numara for p in self.pinler]})")


def _blok(text: str, start: int) -> str:
    """Parantez-derinliği sayarak blok sınırı bulur (naif regex S-Expr'i keser)."""
    depth, i = 0, start
    while True:
        if text[i] == '"':
            i += 1
            while text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


def kutuphane_yukle(path: str) -> Dict[str, KutuphaneSembolu]:
    """.kicad_sym veya .kicad_sch (lib_symbols) içindeki sembolleri okur."""
    text = open(path, encoding="utf-8").read()
    out: Dict[str, KutuphaneSembolu] = {}
    for m in re.finditer(r'\(symbol "([^"]+)"', text):
        isim = m.group(1)
        if "_" in isim and re.search(r"_\d+_\d+$", isim):
            continue  # alt-birim gövdesi (R_1_1)
        raw = _blok(text, m.start())
        agac = sexpr_parse(raw)
        pinler: List[Pin] = []
        for sub in _bul_hepsi(agac, "symbol"):
            unit = 1
            um = re.match(r'^"?.*_(\d+)_(\d+)"?$', tirnaksiz(sub[1]))
            if um:
                unit = int(um.group(1)) or 1
            for p in _bul_hepsi(sub, "pin"):
                at = _bul(p, "at")
                ln = _bul(p, "length")
                nm = _bul(p, "name")
                nb = _bul(p, "number")
                if not (at and nb):
                    continue
                pinler.append(Pin(
                    numara=tirnaksiz(nb[1]),
                    isim=tirnaksiz(nm[1]) if nm else "",
                    x=float(at[1]), y=float(at[2]),
                    aci=float(at[3]) if len(at) > 3 else 0.0,
                    uzunluk=float(ln[1]) if ln else 2.54,
                    etype=p[1], unit=unit,
                ))
        if pinler or isim not in out:
            out[isim] = KutuphaneSembolu(isim=isim, pinler=pinler, metin=raw)
    return out


# --------------------------------------------------------------------------- #
# Yerleşim ve pin ankraj geometrisi
# --------------------------------------------------------------------------- #
def _donusum(px: float, py: float, rot: float, mirror: str) -> Tuple[float, float]:
    """Lib koordinatını (Y yukarı) sheet-yönelimli vektöre çevirir.

    SIRA KRİTİK: önce ROTASYON, sonra MIRROR (KiCad mirror'ı döndürülmüş
    sembolün ekran eksenine uygular). Ters sırada 90/270 + mirror
    kombinasyonlarında pin 1 ile pin 2 yer değiştirir — netlist sessizce
    yanlış olur, şematik göz kontrolünde doğru görünür.
      mirror x -> yatay eksende yansı (y -> -y), mirror y -> x -> -x
    """
    a = math.radians(rot)
    px, py = (px * math.cos(a) - py * math.sin(a),
              px * math.sin(a) + py * math.cos(a))
    if mirror == "x":
        py = -py
    elif mirror == "y":
        px = -px
    return px, -py  # sheet Y AŞAĞI


@dataclass
class PinRef:
    ref: str
    pin: Pin
    x: float          # sheet koordinatı: pin'in ELEKTRİKSEL ankrajı
    y: float
    dx: float         # gövdeden DIŞARI birim yön (wire bu yöne çıkar)
    dy: float

    @property
    def xy(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def disari(self, mesafe: float = STUB) -> Tuple[float, float]:
        return (round(self.x + self.dx * mesafe, 2), round(self.y + self.dy * mesafe, 2))

    @property
    def disari_acisi(self) -> float:
        """Etiket rotasyonu için: 0=sağ, 90=yukarı, 180=sol, 270=aşağı."""
        return round(math.degrees(math.atan2(-self.dy, self.dx)) % 360, 0)


@dataclass
class Yerlesim:
    ref: str
    lib_id: str
    x: float
    y: float
    rot: float
    mirror: str
    unit: int
    sym: KutuphaneSembolu

    def pin(self, numara: str) -> PinRef:
        p = self.sym.pin(numara)
        ax, ay = _donusum(p.x, p.y, self.rot, self.mirror)
        # pin'in DIŞ yönü = gövdeye bakan açının tersi
        ox, oy = _donusum(math.cos(math.radians(p.aci + 180)),
                          math.sin(math.radians(p.aci + 180)), self.rot, self.mirror)
        n = math.hypot(ox, oy) or 1.0
        return PinRef(self.ref, p,
                      round(self.x + ax, 2), round(self.y + ay, 2),
                      round(ox / n, 6), round(oy / n, 6))


# --------------------------------------------------------------------------- #
# Ortogonal yönlendirme
# --------------------------------------------------------------------------- #
def snap(v: float, grid: float = GRID) -> float:
    return round(round(v / grid) * grid, 2)


def ortogonal_rota(a: Tuple[float, float], b: Tuple[float, float],
                   a_yon: Optional[Tuple[float, float]] = None) -> List[Tuple[float, float]]:
    """İki nokta arası ortogonal (L / Z) poli-çizgi. Çapraz (diagonal) wire
    ÇİZİLMEZ: okunmaz ve KiCad'de otomatik junction yerleşimini zorlaştırır."""
    ax, ay = a
    bx, by = b
    if abs(ax - bx) < 0.005 or abs(ay - by) < 0.005:
        return [a, b]
    once_yatay = True
    if a_yon is not None:
        once_yatay = abs(a_yon[0]) > abs(a_yon[1])
    orta = (bx, ay) if once_yatay else (ax, by)
    return [a, orta, b]


def _on_segmentte_mi(p, a, b, eps: float = 0.005) -> bool:
    if abs(a[0] - b[0]) < eps:      # dikey
        return abs(p[0] - a[0]) < eps and min(a[1], b[1]) - eps < p[1] < max(a[1], b[1]) + eps
    if abs(a[1] - b[1]) < eps:      # yatay
        return abs(p[1] - a[1]) < eps and min(a[0], b[0]) - eps < p[0] < max(a[0], b[0]) + eps
    return False


# --------------------------------------------------------------------------- #
# Şematik üretici
# --------------------------------------------------------------------------- #
@dataclass
class SematikUretici:
    proje: str
    kagit: str = "A4"
    uuid_ns: str = "sematik_wire_motoru"
    _gomulu: Dict[str, str] = field(default_factory=dict)
    _semboller: List[str] = field(default_factory=list)
    _ogeler: List[str] = field(default_factory=list)
    _yerlesenler: Dict[str, Yerlesim] = field(default_factory=dict)
    _wire_noktalari: List[List[Tuple[float, float]]] = field(default_factory=list)
    _sheet_uuid: str = ""

    def __post_init__(self):
        self._sheet_uuid = self._u("sheet")

    # -- uuid: deterministik (idempotent yeniden üretim) ---------------------- #
    def _u(self, key: str) -> str:
        return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{self.uuid_ns}/{self.proje}/{key}"))

    # -- kütüphane ------------------------------------------------------------ #
    def gom(self, sym: KutuphaneSembolu, lib_id: str) -> None:
        """lib_symbols'a sembolü gömer. lib_id 'Device:R' biçiminde olmalı."""
        body = re.sub(r'^\(symbol "[^"]+"', f"(symbol {tirnakli(lib_id)}", sym.metin, count=1)
        self._gomulu[lib_id] = "\t\t" + body.replace("\n", "\n\t\t")
        self._kutuphaneler = getattr(self, "_kutuphaneler", {})
        self._kutuphaneler[lib_id] = sym

    # -- yerleşim --------------------------------------------------------------- #
    def yerlestir(self, ref: str, lib_id: str, x: float, y: float, *,
                  deger: str = "", footprint: str = "", rot: float = 0,
                  mirror: str = "", unit: int = 1, dnp: bool = False,
                  ref_gizle: bool = False) -> Yerlesim:
        sym = getattr(self, "_kutuphaneler", {})[lib_id]
        x, y = snap(x), snap(y)
        p = Yerlesim(ref, lib_id, x, y, rot, mirror, unit, sym)
        self._yerlesenler[ref] = p
        u = self._u(f"sym/{ref}")
        L = [f"\t(symbol",
             f"\t\t(lib_id {tirnakli(lib_id)})",
             f"\t\t(at {sayi(x)} {sayi(y)} {sayi(rot)})"]
        if mirror:
            L.append(f"\t\t(mirror {mirror})")
        L += [f"\t\t(unit {unit})", "\t\t(exclude_from_sim no)", "\t\t(in_bom yes)",
              "\t\t(on_board yes)", f"\t\t(dnp {'yes' if dnp else 'no'})",
              f"\t\t(uuid {tirnakli(u)})"]
        for isim, val, dy, gizle in (("Reference", ref, -5.08, ref_gizle),
                                     ("Value", deger or ref, 5.08, False),
                                     ("Footprint", footprint, 0, True),
                                     ("Datasheet", "", 0, True)):
            L += [f"\t\t(property {tirnakli(isim)} {tirnakli(val)}",
                  f"\t\t\t(at {sayi(x)} {sayi(y + dy)} 0)",
                  "\t\t\t(effects (font (size 1.27 1.27))" + (" (hide yes))" if gizle else ")"),
                  "\t\t)"]
        for pin in sym.pinler:
            if pin.unit in (0, unit):
                L.append(f"\t\t(pin {tirnakli(pin.numara)} (uuid {tirnakli(self._u(f'pin/{ref}/{pin.numara}'))}))")
        L += ["\t\t(instances",
              f"\t\t\t(project {tirnakli(self.proje)}",
              f"\t\t\t\t(path {tirnakli('/' + self._sheet_uuid)}",
              f"\t\t\t\t\t(reference {tirnakli(ref)}) (unit {unit})",
              "\t\t\t\t)", "\t\t\t)", "\t\t)", "\t)"]
        self._semboller.append("\n".join(L))
        return p

    # -- bağlantı --------------------------------------------------------------- #
    def wire(self, noktalar: List[Tuple[float, float]], key: Optional[str] = None) -> None:
        """Poli-çizgiyi segment segment yazar. Uçlar TAM eşleşmeli (sayi() yuvarlar)."""
        noktalar = [(round(x, 2), round(y, 2)) for x, y in noktalar]
        self._wire_noktalari.append(noktalar)
        for i, (a, b) in enumerate(zip(noktalar, noktalar[1:])):
            if a == b:
                continue
            k = key or f"{a[0]},{a[1]}-{b[0]},{b[1]}"
            self._ogeler.append("\n".join([
                "\t(wire",
                f"\t\t(pts (xy {sayi(a[0])} {sayi(a[1])}) (xy {sayi(b[0])} {sayi(b[1])}))",
                "\t\t(stroke (width 0) (type default))",
                f"\t\t(uuid {tirnakli(self._u(f'wire/{k}/{i}'))})",
                "\t)"]))

    def baglan(self, a, b, key: Optional[str] = None) -> List[Tuple[float, float]]:
        """PinRef veya (x,y) alan iki ucu ortogonal wire ile bağlar."""
        a_yon = (a.dx, a.dy) if isinstance(a, PinRef) else None
        pa = a.xy if isinstance(a, PinRef) else (snap(a[0]), snap(a[1]))
        pb = b.xy if isinstance(b, PinRef) else (snap(b[0]), snap(b[1]))
        noktalar = ortogonal_rota(pa, pb, a_yon)
        self.wire(noktalar, key)
        return noktalar

    def pin_pin_baglantisi(self, a: PinRef, b: PinRef) -> None:
        """İki pin arası: önce her pinden kısa stub, sonra ortogonal birleşim."""
        sa, sb = a.disari(), b.disari()
        self.wire([a.xy, sa], key=f"stub/{a.ref}/{a.pin.numara}")
        self.wire([b.xy, sb], key=f"stub/{b.ref}/{b.pin.numara}")
        self.wire(ortogonal_rota(sa, sb, (a.dx, a.dy)),
                  key=f"link/{a.ref}{a.pin.numara}-{b.ref}{b.pin.numara}")

    def junction(self, at: Tuple[float, float]) -> None:
        self._ogeler.append("\n".join([
            "\t(junction",
            f"\t\t(at {sayi(at[0])} {sayi(at[1])}) (diameter 0) (color 0 0 0 0)",
            f"\t\t(uuid {tirnakli(self._u(f'junction/{at[0]},{at[1]}'))})",
            "\t)"]))

    def otomatik_junction(self) -> List[Tuple[float, float]]:
        """T-bağlantı noktalarına junction koyar. Junction'sız kesişen iki
        wire KiCad'de BAĞLI DEĞİLDİR (sessiz kopukluk kaynağı #1)."""
        uclar: Dict[Tuple[float, float], int] = {}
        segmentler: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        for noktalar in self._wire_noktalari:
            for a, b in zip(noktalar, noktalar[1:]):
                segmentler.append((a, b))
                for p in (a, b):
                    uclar[p] = uclar.get(p, 0) + 1
        eklenen = []
        for p, n in sorted(uclar.items()):
            deginen = n
            for a, b in segmentler:
                if p in (a, b):
                    continue
                if _on_segmentte_mi(p, a, b):
                    deginen += 2
            if deginen >= 3:
                self.junction(p)
                eklenen.append(p)
        return eklenen

    # -- etiket / güç / NC -------------------------------------------------------- #
    def etiket(self, at, metin: str, tur: str = "label") -> None:
        """tur: label (yerel) | global_label | hierarchical_label.
        Etiket wire'ın UCUNA oturmalı; havada duran etiket bağlanmaz."""
        if isinstance(at, PinRef):
            x, y = at.disari()
            self.wire([at.xy, (x, y)], key=f"stub/{at.ref}/{at.pin.numara}")
            ang = at.disari_acisi
        else:
            x, y = round(at[0], 2), round(at[1], 2)
            ang = 0
        just = "left" if ang in (0, 90) else "right"
        extra = "\t\t(shape input)\n" if tur != "label" else ""
        self._ogeler.append(
            f"\t({tur} {tirnakli(metin)}\n{extra}"
            f"\t\t(at {sayi(x)} {sayi(y)} {sayi(ang)})\n"
            f"\t\t(effects (font (size 1.27 1.27)) (justify {just} bottom))\n"
            f"\t\t(uuid {tirnakli(self._u(f'lbl/{tur}/{metin}/{x},{y}'))})\n\t)")

    def guc_sembolu(self, at, lib_id: str = "power:GND", ref: Optional[str] = None,
                    rot: float = 0, mesafe: float = STUB,
                    yon: Tuple[float, float] = (0, -1)) -> Yerlesim:
        """Güç sembolü + hedefe wire. `at` bir PinRef veya (x,y) olabilir;
        nokta verilirse sembol `yon` yönünde `mesafe` kadar öteye konur
        (varsayılan yukarı) ve araya wire çekilir.

        GND/rail'i çıplak label ile bağlama: güç sembolü ERC'nin
        'power input not driven' kontrolünü besleyen TEK yapıdır.
        """
        ref = ref or f"#PWR{len([r for r in self._yerlesenler if r.startswith('#PWR')]) + 1:03d}"
        if isinstance(at, PinRef):
            hedef, (x, y) = at.xy, at.disari(mesafe)
            key = f"{at.ref}/{at.pin.numara}"
        else:
            hedef = (snap(at[0]), snap(at[1]))
            x, y = round(hedef[0] + yon[0] * mesafe, 2), round(hedef[1] + yon[1] * mesafe, 2)
            key = f"{hedef[0]},{hedef[1]}"
        sym = getattr(self, "_kutuphaneler", {})[lib_id]
        pin0 = sym.pinler[0] if sym.pinler else None
        p = self.yerlestir(ref, lib_id, x, y, deger=lib_id.split(":")[-1], rot=rot)
        ankraj = p.pin(pin0.numara).xy if pin0 else (x, y)
        self.wire([hedef, ankraj], key=f"pwr/{ref}/{key}")
        return p

    def guc_bayragi(self, at, ref: Optional[str] = None,
                    yon: Tuple[float, float] = (0, -1)) -> Yerlesim:
        """PWR_FLAG — SADECE gerçek kart-dışı besleme noktasında (konnektör /
        batarya terminali / harici regülatör girişi), ray başına EN FAZLA BİR.

        YASAK kullanım: 'power input not driven' hatasını, rayın gerçekten
        beslenmediği yerde susturmak (MASTER_RULEBOOK Faz 3: "PWR_FLAG
        yalnızca kök neden bulunduktan sonra eklenecektir"). O hata gerçek
        bir kopukluğun sinyalidir (bring-up'ta ölü ray).
        """
        ref = ref or f"#FLG{len([r for r in self._yerlesenler if r.startswith('#FLG')]) + 1:03d}"
        return self.guc_sembolu(at, "power:PWR_FLAG", ref=ref, yon=yon)

    def no_connect(self, at: PinRef) -> None:
        self._ogeler.append(
            f"\t(no_connect (at {sayi(at.x)} {sayi(at.y)}) "
            f"(uuid {tirnakli(self._u(f'nc/{at.ref}/{at.pin.numara}'))}))")

    # -- çıktı --------------------------------------------------------------- #
    def render(self) -> str:
        libs = "\n".join(self._gomulu.values())
        return "\n".join([
            "(kicad_sch",
            "\t(version 20260306)",
            '\t(generator "sematik_wire_motoru")',
            '\t(generator_version "10.0")',
            f"\t(uuid {tirnakli(self._sheet_uuid)})",
            f"\t(paper {tirnakli(self.kagit)})",
            "\t(lib_symbols", libs, "\t)",
            *self._ogeler,
            *self._semboller,
            "\t(sheet_instances",
            '\t\t(path "/" (page "1"))',
            "\t)",
            ")", ""])

    def yaz(self, path: str, *, force: bool = False) -> str:
        kicad_kapali_mi_dogrula(path, force=force)
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(self.render())
        return path


# --------------------------------------------------------------------------- #
# Kilit + doğrulama (CLAUDE.md §0 ile birebir aynı disiplin)
# --------------------------------------------------------------------------- #
_KICAD_SUREC_ADLARI = ("kicad", "pcbnew", "eeschema")


def _calisan_kicad_surecleri() -> List[str]:
    """Çalışan KiCad süreçlerinin (varsa) satır listesini döner.

    REGRESYON DÜZELTMESİ: önceki sürüm koşulsuz `pgrep` çağırıyordu — bu
    Windows'ta HİÇ KURULU DEĞİL, dolayısıyla `subprocess.run(["pgrep",...])`
    yakalanmamış `FileNotFoundError` fırlatıp `yaz()` çağrısının TAMAMINI
    (dış inceleme raporunun P0 bulgusu — Windows'ta şematik yazma kilidi)
    kesiyordu. Artık platform algılanır: Windows'ta `tasklist`, diğerlerinde
    `pgrep` kullanılır; kontrol aracının KENDİSİ bulunamazsa (`FileNotFoundError`)
    bu bir GÜVENLİK KONTROLÜ EKSİKLİĞİDİR ama yazma işlemini durdurmaz —
    sessizce "hiç süreç yok" da SAYILMAZ, `[UYARI]` önekiyle döndürülen satır
    çağıran tarafından (ör. bir log'a) görünür kılınmalıdır.
    """
    if platform.system() == "Windows":
        try:
            r = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return ["[UYARI] 'tasklist' çalıştırılamadı — çalışan KiCad süreci kontrol edilemedi."]
        satirlar = []
        for ln in r.stdout.splitlines():
            kucuk = ln.lower()
            if any(ad in kucuk for ad in _KICAD_SUREC_ADLARI):
                satirlar.append(ln.strip())
        return satirlar

    try:
        r = subprocess.run(
            ["pgrep", "-a", "-f", "|".join(_KICAD_SUREC_ADLARI)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ["[UYARI] 'pgrep' çalıştırılamadı — çalışan KiCad süreci kontrol edilemedi."]
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def kicad_kapali_mi_dogrula(path: str, *, force: bool = False) -> None:
    """CLAUDE.md §0: açık KiCad + dosya yazımı sessizce birbirini ezer."""
    if force:
        return
    lck = os.path.join(os.path.dirname(os.path.abspath(path)),
                       "~" + os.path.basename(path) + ".lck")
    if os.path.exists(lck) or os.path.exists(path + ".lck"):
        raise RuntimeError(f"Kilit dosyası var, KiCad açık görünüyor: {path}")
    canli = [ln for ln in _calisan_kicad_surecleri() if not ln.startswith("[UYARI]")]
    if canli:
        raise RuntimeError("KiCad çalışıyor — yazmadan önce kapat:\n" + "\n".join(canli))


def netlist_nets(
    sch: str, workdir: Optional[str] = None, kicad_cli: Optional[str] = None
) -> Dict[str, set]:
    """kicad-cli ile netlist üretip {net: {'R1-1', ...}} döner.
    BAĞLANTININ TEK KANITI BUDUR — çizginin görünmesi bağlantı demek değildir."""
    out = (workdir or os.path.dirname(os.path.abspath(sch))) + "/_netlist.net"
    r = subprocess.run([kicad_cli_yolunu_bul(kicad_cli), "sch", "export", "netlist",
                        "--format", "kicadsexpr", "-o", out, sch],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"netlist export başarısız:\n{r.stdout}\n{r.stderr}")
    tree = sexpr_parse(open(out, encoding="utf-8").read())
    nets: Dict[str, set] = {}
    nl = _bul(tree, "nets")
    for net in _bul_hepsi(nl or [], "net"):
        isim = tirnaksiz(_bul(net, "name")[1]) if _bul(net, "name") else "?"
        uyeler = set()
        for node in _bul_hepsi(net, "node"):
            ref = tirnaksiz(_bul(node, "ref")[1])
            pin = tirnaksiz(_bul(node, "pin")[1])
            uyeler.add(f"{ref}-{pin}")
        nets[isim] = uyeler
    return nets


def dogrula_netler(
    sch: str, beklenen: Dict[str, set], kicad_cli: Optional[str] = None
) -> List[str]:
    """`beklenen` {net: {'R1-1',...}} ile gerçek netlist'i karşılaştırır.
    Dönen liste boşsa geçti. Alt-ajan self-report'una değil BUNA güven.

    İki tuzak burada normalize edilir:
      * YEREL label'lı net'ler netlist'te sheet yolu önekiyle gelir: `/VBUS`.
      * `#PWR*` güç sembolleri netlist'te node olarak GÖRÜNMEZ; bağlandığının
        kanıtı net'in o isimle (ör. `GND`) adlanmasıdır.
    """
    gercek = {k.lstrip("/"): v for k, v in netlist_nets(sch, kicad_cli=kicad_cli).items()}
    sorunlar = []
    for isim, istenen in beklenen.items():
        istenen = {m for m in istenen if not m.startswith("#")}
        gelen = gercek.get(isim.lstrip("/"))
        if gelen is None:
            sorunlar.append(f"NET YOK: {isim} (wire pin'e değmiyor olabilir)")
        elif not istenen <= gelen:
            sorunlar.append(f"EKSİK ÜYE {isim}: bekleniyor {sorted(istenen)}, gelen {sorted(gelen)}")
    return sorunlar


def erc_calistir(
    sch: str, out: Optional[str] = None, kicad_cli: Optional[str] = None
) -> dict:
    """kicad-cli sch erc -> json. PWR_FLAG ile susturmak YASAK (MASTER_RULEBOOK Faz 3)."""
    import json
    out = out or os.path.splitext(sch)[0] + "_erc.json"
    subprocess.run([kicad_cli_yolunu_bul(kicad_cli), "sch", "erc", "--format", "json",
                    "--severity-error", "--severity-warning", "-o", out, sch],
                   capture_output=True, text=True)
    return json.load(open(out, encoding="utf-8"))
