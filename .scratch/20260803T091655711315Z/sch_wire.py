"""sch_wire — KiCad 10 şematiğine GERÇEK çizgi (wire) çizen yardımcı kütüphane.

Neden var: ajan script'leri şimdiye kadar sadece `(label ...)` koyup pin'leri
"uçan net" ile bağlıyordu; şematikte hiç `(wire ...)` yoktu. Bu modül pin
koordinat geometrisini (lib->sheet dönüşümü, rotasyon, mirror, Y-flip) doğru
çözer ve ortogonal wire + junction + label + power sembolü üretir.

Kanıt disiplini: görsel çizgi bağlantı DEĞİLDİR. Bağlantının tek kanıtı
`kicad-cli sch export netlist` çıktısıdır -> `netlist_nets()` + `verify_nets()`.

Kullanım (özet):
    lib   = load_lib_symbols("/usr/share/kicad/symbols/Device.kicad_sym")
    sch   = SchBuilder(project="demo")
    sch.embed(lib["R"], "Device:R")
    r1    = sch.place("R1", "Device:R", 100, 100, value="5k1")
    sch.connect(r1.pin("1"), (100, 80))          # pin -> nokta
    sch.wire_pins(r1.pin("2"), r2.pin("1"))      # pin -> pin (ortogonal)
    sch.label(r1.pin("2"), "USB_CC1")
    sch.write("demo.kicad_sch")                  # .bak + KiCad-kapalı kontrolü

PROJE ENTEGRASYON NOTU (bu proje için, orijinal script üzerinde YAPILAN
İKİ DÜZELTME): dış projeden (`Otonom-PCB-Ajani`) alınan bu dosya, projenin
önceki şematik wire motoru `sematik_wire_motoru_old.py`'de zaten bulunan
iki P0 düzeltmeyi İÇERMİYORDU — buraya taşındı:
  1. `assert_kicad_closed()` koşulsuz `pgrep` çağırıyordu; `pgrep`
     Windows'ta YOK, bu da `FileNotFoundError` ile `write()`'ın TAMAMINI
     kesiyordu. Artık `_calisan_kicad_surecleri()` platformu algılar
     (Windows: `tasklist`, diğer: `pgrep`).
  2. `netlist_nets`/`run_erc` düz `"kicad-cli"` çağırıyordu (yalnızca PATH'te
     ise çalışır). Artık `arac_yollari.kicad_cli_yolunu_bul()` ile çözülüyor
     (parametre > `KICAD_CLI` env > PATH > Windows varsayılan kurulum yolu).
Bu iki düzeltme DIŞINDA dosyanın mantığı (S-Expr üretimi, rotasyon/mirror
geometrisi, netlist doğrulama) orijinaliyle birebir aynıdır.
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

from arac_yollari import kicad_cli_yolunu_bul

GRID = 1.27          # KiCad şematik bağlantı grid'i (mm). 2.54 tercih edilir.
STUB = 2.54          # pin ucundan çıkan varsayılan kısa wire


# --------------------------------------------------------------------------- #
# S-Expression                                                                 #
# --------------------------------------------------------------------------- #
def parse_sexpr(text: str, start: int = 0):
    """Metni iç içe liste ağacına çevirir. Atomlar str olarak kalır."""
    tokens = re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text[start:])
    stack: list[list] = []
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


def unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == '"':
        return tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return tok


def q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def num(v: float) -> str:
    """Grid drift'i engelle: 2 ondalık, -0 yok. 195.57999999999998 gibi
    kayan nokta artıkları wire ucu ile pin'i ayırıp sessiz kopukluk yaratır."""
    v = round(float(v) + 0.0, 2)
    return f"{v:g}"


def find(node, key: str):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key: str):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


# --------------------------------------------------------------------------- #
# Sembol / pin modeli                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    x: float          # lib koordinatı (Y YUKARI)
    y: float
    angle: float      # pin'in gövdeye BAKAN yönü (KiCad konvansiyonu)
    length: float
    etype: str        # passive / power_in / input / ...
    unit: int


@dataclass
class LibSymbol:
    name: str
    pins: list[Pin]
    text: str         # ham S-Expr bloğu (lib_symbols'a gömmek için)

    def pin(self, number: str) -> Pin:
        for p in self.pins:
            if p.number == number:
                return p
        raise KeyError(f"{self.name}: pin {number!r} yok "
                       f"(mevcut: {[p.number for p in self.pins]})")


def _block(text: str, start: int) -> str:
    """Parantez-derinliği sayarak blok sınırı bul (naif regex S-Expr'i keser)."""
    depth, i = 0, start
    while True:
        if text[i] == '"':                       # string içindeki parantezi atla
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


def load_lib_symbols(path: str) -> dict[str, LibSymbol]:
    """.kicad_sym veya .kicad_sch (lib_symbols) içindeki sembolleri okur."""
    text = open(path, encoding="utf-8").read()
    out: dict[str, LibSymbol] = {}
    for m in re.finditer(r'\(symbol "([^"]+)"', text):
        name = m.group(1)
        if "_" in name and re.search(r"_\d+_\d+$", name):
            continue                              # alt-birim gövdesi (R_1_1)
        raw = _block(text, m.start())
        tree = parse_sexpr(raw)
        pins: list[Pin] = []
        for sub in find_all(tree, "symbol"):      # R_0_1 / R_1_1 alt blokları
            unit = 1
            um = re.match(r'^"?.*_(\d+)_(\d+)"?$', unquote(sub[1]))
            if um:
                unit = int(um.group(1)) or 1
            for p in find_all(sub, "pin"):
                at = find(p, "at")
                ln = find(p, "length")
                nm = find(p, "name")
                nb = find(p, "number")
                if not (at and nb):
                    continue
                pins.append(Pin(
                    number=unquote(nb[1]),
                    name=unquote(nm[1]) if nm else "",
                    x=float(at[1]), y=float(at[2]),
                    angle=float(at[3]) if len(at) > 3 else 0.0,
                    length=float(ln[1]) if ln else 2.54,
                    etype=p[1], unit=unit,
                ))
        if pins or name not in out:
            out[name] = LibSymbol(name=name, pins=pins, text=raw)
    return out


# --------------------------------------------------------------------------- #
# Yerleşim ve pin ankraj geometrisi                                            #
# --------------------------------------------------------------------------- #
def _xform(px: float, py: float, rot: float, mirror: str) -> tuple[float, float]:
    """Lib koordinatını (Y yukarı) sheet-yönelimli vektöre çevirir.

    SIRA KRİTİK: önce ROTASYON, sonra MIRROR (KiCad mirror'ı döndürülmüş
    sembolün ekran eksenine uygular). Ters sırada 90/270 + mirror
    kombinasyonlarında pin 1 ile pin 2 yer değiştirir — netlist sessizce
    yanlış olur, şematik göz kontrolünde doğru görünür.
      mirror x -> yatay eksende yansı (y -> -y),  mirror y -> x -> -x
    """
    a = math.radians(rot)
    px, py = (px * math.cos(a) - py * math.sin(a),
              px * math.sin(a) + py * math.cos(a))
    if mirror == "x":
        py = -py
    elif mirror == "y":
        px = -px
    return px, -py                                # sheet Y AŞAĞI


@dataclass
class PinRef:
    ref: str
    pin: Pin
    x: float          # sheet koordinatı: pin'in ELEKTRİKSEL ankrajı
    y: float
    dx: float         # gövdeden DIŞARI birim yön (wire bu yöne çıkar)
    dy: float

    @property
    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)

    def out(self, dist: float = STUB) -> tuple[float, float]:
        return (round(self.x + self.dx * dist, 2), round(self.y + self.dy * dist, 2))

    @property
    def out_angle(self) -> float:
        """Label rotasyonu için: 0=sağ, 90=yukarı, 180=sol, 270=aşağı."""
        return round(math.degrees(math.atan2(-self.dy, self.dx)) % 360, 0)


@dataclass
class Placed:
    ref: str
    lib_id: str
    x: float
    y: float
    rot: float
    mirror: str
    unit: int
    sym: LibSymbol

    def pin(self, number: str) -> PinRef:
        p = self.sym.pin(number)
        ax, ay = _xform(p.x, p.y, self.rot, self.mirror)
        # pin'in DIŞ yönü = gövdeye bakan açının tersi
        ox, oy = _xform(math.cos(math.radians(p.angle + 180)),
                        math.sin(math.radians(p.angle + 180)), self.rot, self.mirror)
        n = math.hypot(ox, oy) or 1.0
        return PinRef(self.ref, p,
                      round(self.x + ax, 2), round(self.y + ay, 2),
                      round(ox / n, 6), round(oy / n, 6))


# --------------------------------------------------------------------------- #
# Ortogonal yönlendirme                                                        #
# --------------------------------------------------------------------------- #
def snap(v: float, grid: float = GRID) -> float:
    return round(round(v / grid) * grid, 2)


def route(a: tuple[float, float], b: tuple[float, float],
          a_dir: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    """İki nokta arası ortogonal (L / Z) poli-çizgi. Diyagonal wire çizme:
    okunmaz ve KiCad'de otomatik junction yerleşimini zorlaştırır."""
    ax, ay = a
    bx, by = b
    if abs(ax - bx) < 0.005 or abs(ay - by) < 0.005:
        return [a, b]
    horizontal_first = True
    if a_dir is not None:
        horizontal_first = abs(a_dir[0]) > abs(a_dir[1])
    if horizontal_first:
        mid = (bx, ay)
    else:
        mid = (ax, by)
    return [a, mid, b]


# --------------------------------------------------------------------------- #
# Şematik üretici                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class SchBuilder:
    project: str
    paper: str = "A4"
    uuid_ns: str = "sch_wire"
    _embedded: dict[str, str] = field(default_factory=dict)
    _symbols: list[str] = field(default_factory=list)
    _items: list[str] = field(default_factory=list)
    _placed: dict[str, Placed] = field(default_factory=dict)
    _wire_pts: list[list[tuple[float, float]]] = field(default_factory=list)
    _sheet_uuid: str = ""

    def __post_init__(self):
        self._sheet_uuid = self._u("sheet")

    # -- uuid: deterministik (idempotent yeniden üretim) --------------------- #
    def _u(self, key: str) -> str:
        return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{self.uuid_ns}/{self.project}/{key}"))

    # -- kütüphane ----------------------------------------------------------- #
    def embed(self, sym: LibSymbol, lib_id: str) -> None:
        """lib_symbols'a sembolü gömer. lib_id 'Device:R' biçiminde olmalı."""
        body = re.sub(r'^\(symbol "[^"]+"', f"(symbol {q(lib_id)}", sym.text, count=1)
        self._embedded[lib_id] = "\t\t" + body.replace("\n", "\n\t\t")
        self._libs = getattr(self, "_libs", {})
        self._libs[lib_id] = sym

    # -- yerleşim ------------------------------------------------------------ #
    def place(self, ref: str, lib_id: str, x: float, y: float, *,
              value: str = "", footprint: str = "", rot: float = 0,
              mirror: str = "", unit: int = 1, dnp: bool = False,
              hide_ref: bool = False) -> Placed:
        sym = getattr(self, "_libs", {})[lib_id]
        x, y = snap(x), snap(y)
        p = Placed(ref, lib_id, x, y, rot, mirror, unit, sym)
        self._placed[ref] = p
        u = self._u(f"sym/{ref}")
        L = [f"\t(symbol",
             f"\t\t(lib_id {q(lib_id)})",
             f"\t\t(at {num(x)} {num(y)} {num(rot)})"]
        if mirror:
            L.append(f"\t\t(mirror {mirror})")
        L += [f"\t\t(unit {unit})", "\t\t(exclude_from_sim no)", "\t\t(in_bom yes)",
              "\t\t(on_board yes)", f"\t\t(dnp {'yes' if dnp else 'no'})",
              f"\t\t(uuid {q(u)})"]
        for name, val, dy, hide in (("Reference", ref, -5.08, hide_ref),
                                    ("Value", value or ref, 5.08, False),
                                    ("Footprint", footprint, 0, True),
                                    ("Datasheet", "", 0, True)):
            L += [f"\t\t(property {q(name)} {q(val)}",
                  f"\t\t\t(at {num(x)} {num(y + dy)} 0)",
                  "\t\t\t(effects (font (size 1.27 1.27))" + (" (hide yes))" if hide else ")"),
                  "\t\t)"]
        for pin in sym.pins:
            if pin.unit in (0, unit):
                L.append(f"\t\t(pin {q(pin.number)} (uuid {q(self._u(f'pin/{ref}/{pin.number}'))}))")
        L += ["\t\t(instances",
              f"\t\t\t(project {q(self.project)}",
              f"\t\t\t\t(path {q('/' + self._sheet_uuid)}",
              f"\t\t\t\t\t(reference {q(ref)}) (unit {unit})",
              "\t\t\t\t)", "\t\t\t)", "\t\t)", "\t)"]
        self._symbols.append("\n".join(L))
        return p

    # -- bağlantı ------------------------------------------------------------ #
    def wire(self, pts: list[tuple[float, float]], key: str | None = None) -> None:
        """Poli-çizgiyi segment segment yazar. Uçlar TAM eşleşmeli (num() yuvarlar)."""
        pts = [(round(x, 2), round(y, 2)) for x, y in pts]
        self._wire_pts.append(pts)
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            if a == b:
                continue
            k = key or f"{a[0]},{a[1]}-{b[0]},{b[1]}"
            self._items.append("\n".join([
                "\t(wire",
                f"\t\t(pts (xy {num(a[0])} {num(a[1])}) (xy {num(b[0])} {num(b[1])}))",
                "\t\t(stroke (width 0) (type default))",
                f"\t\t(uuid {q(self._u(f'wire/{k}/{i}'))})",
                "\t)"]))

    def connect(self, a, b, key: str | None = None) -> list[tuple[float, float]]:
        """PinRef veya (x,y) alan iki ucu ortogonal wire ile bağlar."""
        a_dir = (a.dx, a.dy) if isinstance(a, PinRef) else None
        pa = a.xy if isinstance(a, PinRef) else (snap(a[0]), snap(a[1]))
        pb = b.xy if isinstance(b, PinRef) else (snap(b[0]), snap(b[1]))
        pts = route(pa, pb, a_dir)
        self.wire(pts, key)
        return pts

    def wire_pins(self, a: PinRef, b: PinRef) -> None:
        """İki pin arası: önce her pin'den kısa stub, sonra ortogonal birleşim."""
        sa, sb = a.out(), b.out()
        self.wire([a.xy, sa], key=f"stub/{a.ref}/{a.pin.number}")
        self.wire([b.xy, sb], key=f"stub/{b.ref}/{b.pin.number}")
        self.wire(route(sa, sb, (a.dx, a.dy)), key=f"link/{a.ref}{a.pin.number}-{b.ref}{b.pin.number}")

    def junction(self, at: tuple[float, float]) -> None:
        self._items.append("\n".join([
            "\t(junction",
            f"\t\t(at {num(at[0])} {num(at[1])}) (diameter 0) (color 0 0 0 0)",
            f"\t\t(uuid {q(self._u(f'junction/{at[0]},{at[1]}'))})",
            "\t)"]))

    def auto_junctions(self) -> list[tuple[float, float]]:
        """T-bağlantı noktalarına junction koyar. Junction'sız kesişen iki wire
        KiCad'de BAĞLI DEĞİLDİR (sessiz kopukluk kaynağı #1)."""
        ends: dict[tuple[float, float], int] = {}
        segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for pts in self._wire_pts:
            for a, b in zip(pts, pts[1:]):
                segs.append((a, b))
                for p in (a, b):
                    ends[p] = ends.get(p, 0) + 1
        added = []
        for p, n in sorted(ends.items()):
            touching = n
            for a, b in segs:                       # uç, başka segmentin ortasında mı?
                if p in (a, b):
                    continue
                if _on_segment(p, a, b):
                    touching += 2
            if touching >= 3:
                self.junction(p)
                added.append(p)
        return added

    # -- etiket / güç / NC ---------------------------------------------------- #
    def label(self, at, text: str, kind: str = "label") -> None:
        """kind: label (yerel) | global_label | hierarchical_label.
        Etiket wire'ın UCUNA oturmalı; havada duran etiket bağlanmaz."""
        if isinstance(at, PinRef):
            x, y = at.out()
            self.wire([at.xy, (x, y)], key=f"stub/{at.ref}/{at.pin.number}")
            ang = at.out_angle
        else:
            x, y = round(at[0], 2), round(at[1], 2)
            ang = 0
        just = "left" if ang in (0, 90) else "right"
        extra = "\t\t(shape input)\n" if kind != "label" else ""
        self._items.append(
            f"\t({kind} {q(text)}\n{extra}"
            f"\t\t(at {num(x)} {num(y)} {num(ang)})\n"
            f"\t\t(effects (font (size 1.27 1.27)) (justify {just} bottom))\n"
            f"\t\t(uuid {q(self._u(f'lbl/{kind}/{text}/{x},{y}'))})\n\t)")

    def power(self, at, lib_id: str = "power:GND", ref: str | None = None,
              rot: float = 0, dist: float = STUB,
              direction: tuple[float, float] = (0, -1)) -> Placed:
        """Güç sembolü + hedefe wire. `at` bir PinRef veya (x,y) olabilir;
        nokta verilirse sembol `direction` yönünde `dist` kadar öteye konur
        (varsayılan yukarı) ve araya wire çekilir.

        GND/rail'i çıplak label ile bağlama: power sembolü ERC'nin
        'power input not driven' kontrolünü besleyen tek yapıdır.
        """
        ref = ref or f"#PWR{len([r for r in self._placed if r.startswith('#PWR')]) + 1:03d}"
        if isinstance(at, PinRef):
            target, (x, y) = at.xy, at.out(dist)
            key = f"{at.ref}/{at.pin.number}"
        else:
            target = (snap(at[0]), snap(at[1]))
            x, y = round(target[0] + direction[0] * dist, 2), round(target[1] + direction[1] * dist, 2)
            key = f"{target[0]},{target[1]}"
        sym = getattr(self, "_libs", {})[lib_id]
        pin0 = sym.pins[0] if sym.pins else None
        p = self.place(ref, lib_id, x, y, value=lib_id.split(":")[-1], rot=rot)
        # sembolün pin ankrajı sembol orijininde olmayabilir -> gerçek ankrajdan çek
        anchor = p.pin(pin0.number).xy if pin0 else (x, y)
        self.wire([target, anchor], key=f"pwr/{ref}/{key}")
        return p

    def pwr_flag(self, at, ref: str | None = None,
                 direction: tuple[float, float] = (0, -1)) -> Placed:
        """PWR_FLAG — SADECE gerçek kart-dışı besleme noktasında (konnektör /
        batarya terminali / harici regülatör girişi), ray başına EN FAZLA BİR.

        YASAK kullanım: 'power input not driven' hatasını, rayın gerçekten
        beslenmediği yerde susturmak. O hata gerçek bir kopukluğun sinyalidir
        (bring-up'ta ölü ray). Önce net'i kaynağına bağla; PWR_FLAG'i ancak
        kaynak şematik dışındaysa ve bunu yorumla belgeliyorsan kullan.
        """
        ref = ref or f"#FLG{len([r for r in self._placed if r.startswith('#FLG')]) + 1:03d}"
        return self.power(at, "power:PWR_FLAG", ref=ref, direction=direction)

    def no_connect(self, at: PinRef) -> None:
        self._items.append(
            f"\t(no_connect (at {num(at.x)} {num(at.y)}) "
            f"(uuid {q(self._u(f'nc/{at.ref}/{at.pin.number}'))}))")

    # -- çıktı ---------------------------------------------------------------- #
    def render(self) -> str:
        libs = "\n".join(self._embedded.values())
        return "\n".join([
            "(kicad_sch",
            "\t(version 20260306)",
            '\t(generator "sch_wire")',
            '\t(generator_version "10.0")',
            f"\t(uuid {q(self._sheet_uuid)})",
            f"\t(paper {q(self.paper)})",
            "\t(lib_symbols", libs, "\t)",
            *self._items,
            *self._symbols,
            "\t(sheet_instances",
            '\t\t(path "/" (page "1"))',
            "\t)",
            ")", ""])

    def write(self, path: str, *, force: bool = False) -> str:
        assert_kicad_closed(path, force=force)
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(self.render())
        return path


def _on_segment(p, a, b, eps: float = 0.005) -> bool:
    if abs(a[0] - b[0]) < eps:                     # dikey
        return abs(p[0] - a[0]) < eps and min(a[1], b[1]) - eps < p[1] < max(a[1], b[1]) + eps
    if abs(a[1] - b[1]) < eps:                     # yatay
        return abs(p[1] - a[1]) < eps and min(a[0], b[0]) - eps < p[0] < max(a[0], b[0]) + eps
    return False


# --------------------------------------------------------------------------- #
# Kilit + doğrulama                                                            #
# --------------------------------------------------------------------------- #
_KICAD_SUREC_ADLARI = ("kicad", "pcbnew", "eeschema")


def _calisan_kicad_surecleri() -> list[str]:
    """Çalışan KiCad süreçlerinin (varsa) satır listesini döner.

    WINDOWS DÜZELTMESİ (sematik_wire_motoru_old.py'den taşındı — bu dosyanın
    ORİJİNALİ koşulsuz `pgrep` çağırıyordu; `pgrep` Windows'ta KURULU DEĞİL,
    dolayısıyla `subprocess.run(["pgrep",...])` yakalanmamış
    `FileNotFoundError` fırlatıp `write()`'ın TAMAMINI kesiyordu. Platform
    algılanır: Windows'ta `tasklist`, diğerlerinde `pgrep` kullanılır."""
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


def assert_kicad_closed(path: str, *, force: bool = False) -> None:
    """CLAUDE.md §0: açık KiCad + dosya yazımı sessizce birbirini ezer."""
    if force:
        return
    lck = os.path.join(os.path.dirname(os.path.abspath(path)),
                       "~" + os.path.basename(path) + ".lck")
    if os.path.exists(lck) or os.path.exists(path + ".lck"):
        raise RuntimeError(f"Kilit dosyası var, KiCad açık görünüyor: {path}")
    live = [ln for ln in _calisan_kicad_surecleri() if not ln.startswith("[UYARI]")]
    if live:
        raise RuntimeError("KiCad çalışıyor — yazmadan önce kapat:\n" + "\n".join(live))


def netlist_nets(sch: str, workdir: str | None = None, kicad_cli: str | None = None) -> dict[str, set[str]]:
    """kicad-cli ile netlist üretip {net: {'R1-1', ...}} döner.
    BAĞLANTININ TEK KANITI BUDUR — çizginin görünmesi bağlantı demek değildir."""
    out = (workdir or os.path.dirname(os.path.abspath(sch))) + "/_netlist.net"
    r = subprocess.run([kicad_cli_yolunu_bul(kicad_cli), "sch", "export", "netlist",
                        "--format", "kicadsexpr", "-o", out, sch],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"netlist export başarısız:\n{r.stdout}\n{r.stderr}")
    tree = parse_sexpr(open(out, encoding="utf-8").read())
    nets: dict[str, set[str]] = {}
    nl = find(tree, "nets")
    for net in find_all(nl or [], "net"):
        name = unquote(find(net, "name")[1]) if find(net, "name") else "?"
        members = set()
        for node in find_all(net, "node"):
            ref = unquote(find(node, "ref")[1])
            pin = unquote(find(node, "pin")[1])
            members.add(f"{ref}-{pin}")
        nets[name] = members
    return nets


def verify_nets(sch: str, expected: dict[str, set[str]], kicad_cli: str | None = None) -> list[str]:
    """expected {net: {'R1-1',...}} ile gerçek netlist'i karşılaştırır.
    Dönen liste boşsa geçti. Alt-ajan self-report'una değil BUNA güven.

    İki tuzak burada normalize edilir:
      * YEREL label'lı net'ler netlist'te sheet yolu önekiyle gelir: `/VBUS`.
        (global label ve power sembolü isimleri öneksizdir.)
      * `#PWR*` güç sembolleri netlist'te node olarak GÖRÜNMEZ; power sembolünün
        bağlandığının kanıtı, net'in o isimle (ör. `GND`) adlanmasıdır.
    """
    actual = {k.lstrip("/"): v for k, v in netlist_nets(sch, kicad_cli=kicad_cli).items()}
    problems = []
    for name, want in expected.items():
        want = {m for m in want if not m.startswith("#")}
        got = actual.get(name.lstrip("/"))
        if got is None:
            problems.append(f"NET YOK: {name} (wire pin'e değmiyor olabilir)")
        elif not want <= got:
            problems.append(f"EKSİK ÜYE {name}: bekleniyor {sorted(want)}, gelen {sorted(got)}")
    return problems


def run_erc(sch: str, out: str | None = None, kicad_cli: str | None = None) -> dict:
    """kicad-cli sch erc -> json. PWR_FLAG ile susturmak YASAK."""
    import json
    out = out or os.path.splitext(sch)[0] + "_erc.json"
    subprocess.run([kicad_cli_yolunu_bul(kicad_cli), "sch", "erc", "--format", "json",
                    "--severity-error", "--severity-warning", "-o", out, sch],
                   capture_output=True, text=True)
    return json.load(open(out, encoding="utf-8"))
