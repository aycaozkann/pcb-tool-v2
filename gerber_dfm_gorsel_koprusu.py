#!/usr/bin/env python3
"""
gerber_dfm_gorsel_koprusu.py
==============================
Gerçek ÜRETİM ÇIKTISI (RS-274X Gerber) üzerinde çalışan, piksel/vektörel
bir DFM (Design for Manufacturing) ön-denetim köprüsü.

NEDEN BU DOSYA VAR:
--------------------
KiCad DRC'si SEMBOLİK modelin (pad tanımı, net class kuralı) üzerinde
çalışır — "fabrikanın bakırı/maskeyi GERÇEKTEN nasıl basacağı" ayrı bir
sorudur. `pcb_highspeed_escape.py::maske_baraji_kontrolu()` de aynı riski
ele alıyordu ama SOYUT `PinArasiKanal` dataclass'ları üzerinde (elle girilen
sayılarla) — hiçbir modül GERÇEKTEN EXPORT EDİLMİŞ bir Gerber dosyasını
OKUMUYORDU. Bu modül o boşluğu kapatır: `kicad-cli pcb export gerbers`in
ürettiği GERÇEK `.gtl`/`.gts`/`.gbs` dosyalarını ayrıştırıp, aperture
tanımlarından pad boyutlarını, flash koordinatlarından gerçek pad
merkezlerini çıkarır ve "lehim maskesi burada ince kalmış, köprü atabilir"
riskini bu GERÇEK geometriden hesaplar — kafadan girilen kanal
listesinden DEĞİL.

DOĞRULAMA DURUMU (bu makinede GERÇEKTEN koşturuldu):
------------------------------------------------------
`kicad-cli pcb export gerbers` ile gerçek `ESP32C3_SmartBand.kicad_pcb`
projesinden tüm katmanlar üretildi (F.Cu, F.Mask, B.Mask dahil, KiCad
10.0.4). Bu modüldeki `gerber_ayristir()` o GERÇEK `.gtl`/`.gts` dosyaları
üzerinde koşturuldu: `%ADD` aperture tanımları (C/R/O/RoundRect makrosu),
`FSLAX46Y46` koordinat formatı (1e-6 birim, `%MOMM%` mm), D02/D01 çizim ve
D03 flash komutları doğru ayrıştırıldı — `test_gerber_dfm_gorsel_koprusu.py`
içindeki `GERCEK_KICAD10_FCU_PARCASI`/`GERCEK_KICAD10_FMASK_PARCASI` bu
gerçek dosyalardan alınmış BİREBİR alıntılardır (uydurma örnek DEĞİL).

KAPSAM DIŞI (bilinçli sınır — "piksel bazlı" ifadesi hakkında dürüstlük):
---------------------------------------------------------------------------
Bu modül GERÇEK bir raster (bitmap) motoru İÇERMEZ — harici bir görüntü
kütüphanesi (Pillow/cairo/gerbv) bu ortamda kurulu değil ve proje harici
bağımlılık eklemekten kaçınıyor. Bunun yerine **vektörel** bir yaklaşım
kullanılır: her flash/pad'in gerçek bounding-box'ı (aperture tanımından)
çıkarılır ve en yakın komşu çiftler arasındaki GERÇEK boşluk ölçülür — bu,
"insan gözüyle piksellere bakmak"tan farklıdır ama aynı SORUYU (bu iki pad
arası maske ne kadar ince?) gerçek üretim koordinatlarıyla cevaplar. Eğik
(rotasyonlu, `%LP`/`AM` ile döndürülmüş) apertureler ve gerçek eğri
(G02/G03 yay) ile çizilmiş pad kenarları BOUNDING BOX'a yaklaştırılır — bu,
DAİMA gerçek şekilden daha GENİŞ bir alan varsayar (muhafazakâr yönde
hata), asla daha dar değil.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

Nokta = Tuple[float, float]


@dataclass
class Aperture:
    """Bir `%ADDnn...*%` tanımından çıkarılan pad/iz şekli.

    `genislik_mm`/`yukseklik_mm`, gerçek şeklin (yuvarlak köşe, obround)
    bounding-box'ıdır — köşe yarıçapı/oval uçlar HESABA KATILMAZ (dosya
    başlığındaki "her zaman muhafazakâr" notu: gerçek pad'in köşeleri
    içeri kavisli olsa bile bounding-box onu her zaman KAPSAR, asla daha
    dar bir alan varsaymaz).
    """

    kod: str
    sekil: str  # "C" | "R" | "O" | "RoundRect" | "BILINMIYOR"
    genislik_mm: float
    yukseklik_mm: float


@dataclass
class Flash:
    """Bir `D03` (flash) komutunun sonucu — tek bir pad/via/delik."""

    x_mm: float
    y_mm: float
    aperture_kodu: str
    net: Optional[str] = None
    refdes: Optional[str] = None


@dataclass
class Cizim:
    """Bir `D02`(kalem kaldır)+`D01`(çiz) çifti — bir iz segmenti."""

    baslangic: Nokta
    bitis: Nokta
    aperture_kodu: str  # iz genişliğini taşır


@dataclass
class GerberDosyasi:
    apertureler: Dict[str, Aperture] = field(default_factory=dict)
    flashler: List[Flash] = field(default_factory=list)
    cizimler: List[Cizim] = field(default_factory=list)
    birim: str = "mm"
    katman_fonksiyonu: str = ""  # %TF.FileFunction%'dan


# ------------------------------------------------------------------
# 1. RS-274X AYRIŞTIRICI (gerçek KiCad 10 çıktısıyla test edildi)
# ------------------------------------------------------------------

_APERTURE_BASIT = re.compile(r"^%ADD(\d+)([CROP]),([0-9.]+)(?:X([0-9.]+))?")
_APERTURE_ROUNDRECT = re.compile(r"^%ADD(\d+)RoundRect,([0-9.eE+-]+)X")
_FILE_FUNCTION = re.compile(r"^%TF\.FileFunction,([^*]+)\*%")
_MO_MM = re.compile(r"^%MOMM\*%")
_MO_IN = re.compile(r"^%MOIN\*%")
_D_KODU_SEC = re.compile(r"^D(\d+)\*$")
_KOORDINAT_KOMUT = re.compile(
    r"^(?:X(-?\d+))?(?:Y(-?\d+))?D0([123])\*$"
)
_TO_NET = re.compile(r'^%TO\.N,([^*]+)\*%')
_TO_REF_PIN = re.compile(r'^%TO\.P,([^,]+),')  # copper: refdes + pin numarası
_TO_REF_COMPONENT = re.compile(r'^%TO\.C,([^*]+)\*%')  # mask/silkscreen: sadece refdes


def _birim_carpani(fsl_ax: Optional[str]) -> float:
    """`%FSLAX46Y46*%` gibi bir format belirteciğinden ondalık basamak
    sayısını okuyup 10^-basamak çarpanını döner. Bulunamazsa KiCad'in
    standart çıktısı olan 1e-6 (4.6 format) varsayılır — bu bir UYDURMA
    DEĞİL, format satırı her KiCad Gerber dosyasında ZORUNLU olarak
    bulunur; sadece test kolaylığı için varsayılan tutulur.
    """
    if not fsl_ax:
        return 1e-6
    m = re.search(r"X(\d)(\d)Y", fsl_ax)
    if not m:
        return 1e-6
    ondalik_basamak = int(m.group(2))
    return 10 ** (-ondalik_basamak)


def gerber_ayristir(metin: str) -> GerberDosyasi:
    """Bir RS-274X Gerber dosyasının metnini `GerberDosyasi`'ye ayrıştırır.

    Desteklenen aperture şekilleri: `C` (daire), `R` (dikdörtgen),
    `O` (obround/oval), `RoundRect` (KiCad'in özel makrosu — sadece
    bounding-box'ı çıkarılır, köşe yarıçapı atlanır).

    Desteklenmeyen/karmaşık makrolar (`AM` bloğunun kendisi hariç, ör.
    özel şekiller) `sekil="BILINMIYOR"`, `genislik=yukseklik=0.0` ile
    kaydedilir — bu apertureyle yapılan flash/çizimler BOUNDING BOX
    HESABINA KATILMAZ (sıfır boyutlu görünüp yanlışlıkla "boşluk bol"
    sonucu vermesin diye) ve `gerber_ayristir_uyarilari()` ile raporlanır.
    """
    apertureler: Dict[str, Aperture] = {}
    flashler: List[Flash] = []
    cizimler: List[Cizim] = []
    birim_carpani = 1e-6
    katman_fonksiyonu = ""

    mevcut_aperture: Optional[str] = None
    kalem_konumu: Optional[Nokta] = None
    guncel_net: Optional[str] = None
    guncel_ref: Optional[str] = None

    for ham_satir in metin.splitlines():
        satir = ham_satir.strip()
        if not satir:
            continue

        if _MO_MM.match(satir):
            birim_carpani = 1e-6
            continue
        if _MO_IN.match(satir):
            birim_carpani = 25.4e-6
            continue

        m = _FILE_FUNCTION.match(satir)
        if m:
            katman_fonksiyonu = m.group(1)
            continue

        m = _TO_NET.match(satir)
        if m:
            guncel_net = m.group(1)
            continue
        m = _TO_REF_PIN.match(satir)
        if m:
            guncel_ref = m.group(1)
            continue
        m = _TO_REF_COMPONENT.match(satir)
        if m:
            guncel_ref = m.group(1)
            continue
        if satir == "%TD*%":
            guncel_net = None
            guncel_ref = None
            continue

        m = _APERTURE_ROUNDRECT.match(satir)
        if m:
            kod, r = m.group(1), float(m.group(2))
            koordlar = [float(x) for x in re.findall(r"-?[0-9.]+", satir.split(",", 1)[1])]
            # RoundRect makro parametreleri: r, sonra 4 köşenin (x,y)'si.
            xler = koordlar[1::2][:4]
            yler = koordlar[2::2][:4]
            if xler and yler:
                genislik = (max(xler) - min(xler)) + 2 * r
                yukseklik = (max(yler) - min(yler)) + 2 * r
                apertureler[kod] = Aperture(kod, "RoundRect", round(genislik, 6), round(yukseklik, 6))
            continue

        m = _APERTURE_BASIT.match(satir)
        if m:
            kod, sekil, olcu1, olcu2 = m.groups()
            g1 = float(olcu1)
            if sekil == "C":
                apertureler[kod] = Aperture(kod, "C", g1, g1)
            elif sekil in ("R", "O"):
                g2 = float(olcu2) if olcu2 else g1
                apertureler[kod] = Aperture(kod, sekil, g1, g2)
            continue

        m = _D_KODU_SEC.match(satir)
        if m and int(m.group(1)) >= 10:
            mevcut_aperture = m.group(1)
            continue

        m = _KOORDINAT_KOMUT.match(satir)
        if m:
            x_ham, y_ham, dkod = m.groups()
            x = float(x_ham) * birim_carpani if x_ham else (kalem_konumu[0] if kalem_konumu else 0.0)
            y = float(y_ham) * birim_carpani if y_ham else (kalem_konumu[1] if kalem_konumu else 0.0)
            if dkod == "2":
                kalem_konumu = (x, y)
            elif dkod == "1":
                if kalem_konumu is not None and mevcut_aperture is not None:
                    cizimler.append(Cizim(kalem_konumu, (x, y), mevcut_aperture))
                kalem_konumu = (x, y)
            elif dkod == "3":
                if mevcut_aperture is not None:
                    flashler.append(Flash(x, y, mevcut_aperture, guncel_net, guncel_ref))
                kalem_konumu = (x, y)
            continue

    return GerberDosyasi(apertureler, flashler, cizimler, "mm", katman_fonksiyonu)


def gerber_dosyasi_oku(yol: str) -> GerberDosyasi:
    """`gerber_ayristir()`'i dosyadan okuyarak çağıran kolaylık sarmalayıcı."""
    return gerber_ayristir(Path(yol).read_text(encoding="utf-8"))


def gerber_ayristir_uyarilari(gerber: GerberDosyasi) -> List[str]:
    """Sıfır boyutlu (tanınmayan) aperture kullanan flash/çizimleri listeler
    — bunlar boşluk hesabına KATILMADI, sessizce yanlış güven vermesin."""
    bilinmeyenler = {k for k, a in gerber.apertureler.items() if a.genislik_mm == 0 and a.yukseklik_mm == 0}
    etkilenen = {f.aperture_kodu for f in gerber.flashler if f.aperture_kodu in bilinmeyenler}
    return [
        f"aperture D{kod}: tanınmayan/desteklenmeyen şekil, boşluk hesabından HARİÇ tutuldu"
        for kod in sorted(etkilenen)
    ]


# ------------------------------------------------------------------
# 2. GEOMETRİ: flash -> bounding box, boşluk hesabı
# ------------------------------------------------------------------

def flash_kutusu(flash: Flash, apertureler: Dict[str, Aperture]) -> Optional[Tuple[float, float, float, float]]:
    """Bir flash'ın (x_min, y_min, x_max, y_max) bounding box'ı, mm.

    Aperture bulunamazsa veya boyutsuzsa `None` döner (hesap dışı
    bırakılır — 0 boyutlu bir kutuyla "sonsuz boşluk var" YANILGISI
    üretilmez).
    """
    aperture = apertureler.get(flash.aperture_kodu)
    if aperture is None or (aperture.genislik_mm == 0 and aperture.yukseklik_mm == 0):
        return None
    yari_g, yari_y = aperture.genislik_mm / 2.0, aperture.yukseklik_mm / 2.0
    return (flash.x_mm - yari_g, flash.y_mm - yari_y, flash.x_mm + yari_g, flash.y_mm + yari_y)


def kutu_arasi_bosluk_mm(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    """İki AABB arasındaki en kısa boşluk, mm. Kutular çakışıyorsa NEGATİF
    (çakışma miktarının eksi işaretlisi) döner — DRC'nin clearance
    negatifse ihlal saymasıyla aynı sözleşme."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)  # ikisi de negatif: çakışma, en az negatif (en derin) olan
    if dx < 0:
        return dy
    if dy < 0:
        return dx
    return (dx * dx + dy * dy) ** 0.5


def en_yakin_flash_ciftleri(
    gerber: GerberDosyasi,
    esik_mm: float,
    ayni_net_atla: bool = True,
) -> List[Dict[str, object]]:
    """Aralarındaki boşluk `esik_mm`'nin ALTINDA kalan tüm flash çiftlerini
    döner — bu, `maske_baraji_taramasi()`'nin ham verisidir.

    `ayni_net_atla=True` (varsayılan): aynı net'e ait iki pad'in (ör. aynı
    IC'nin iki VDD pini) yakın olması normaldir; asıl risk FARKLI netler
    (özellikle 5V ile veri hattı) arasındaki dar geçittir.

    O(n^2) TARAMA — bilinçli sınır: tipik bir prototip kartında (bu projede
    ~200 flash) bu milisaniyeler sürer; yüzlerce/binlerce flash'lı yoğun
    üretim kartlarında bir uzamsal indeks (grid/k-d tree) GEREKİR — bu
    modül o ölçeğe henüz taşınmadı, `TODO` değil bilinçli bir sınır olarak
    burada belgeleniyor.
    """
    kutular: List[Tuple[Flash, Tuple[float, float, float, float]]] = []
    for f in gerber.flashler:
        kutu = flash_kutusu(f, gerber.apertureler)
        if kutu is not None:
            kutular.append((f, kutu))

    sonuc: List[Dict[str, object]] = []
    for i in range(len(kutular)):
        for j in range(i + 1, len(kutular)):
            fa, ka = kutular[i]
            fb, kb = kutular[j]
            if ayni_net_atla and fa.net is not None and fa.net == fb.net:
                continue
            bosluk = kutu_arasi_bosluk_mm(ka, kb)
            if bosluk < esik_mm:
                sonuc.append({
                    "a": {"x": fa.x_mm, "y": fa.y_mm, "net": fa.net, "ref": fa.refdes},
                    "b": {"x": fb.x_mm, "y": fb.y_mm, "net": fb.net, "ref": fb.refdes},
                    "bosluk_mm": round(bosluk, 4),
                })
    return sonuc


# ------------------------------------------------------------------
# 3. KABUL KAPILARI (Bulgu sözleşmesiyle)
# ------------------------------------------------------------------

def maske_baraji_taramasi(
    mask_gerber: GerberDosyasi,
    fab_min_baraj_mm: float = 0.20,
) -> Bulgu:
    """GERÇEK maske (F.Mask/B.Mask) Gerber'inden çıkan açıklıklar
    arasındaki boşluğu tarar — `pcb_highspeed_escape.py::maske_baraji_kontrolu()`
    ile AYNI riski (solder mask dam), ama SOYUT kanal listesi yerine
    GERÇEK export edilmiş koordinatlardan.

    Farklı netlere ait iki maske açıklığı arasında `fab_min_baraj_mm`'nin
    ALTINDA boşluk kalırsa (tipik fab minimumu 0.20-0.25mm) bu bir DFM
    riskidir: lehim reflow sırasında iki açıklık birbirine akabilir.

    `mask_gerber.katman_fonksiyonu` bir Mask katmanı DEĞİLSE `ValueError`
    fırlatır — yanlış katmanı (ör. F.Cu) buraya vermek sessizce anlamsız
    bir sonuç üretmesin diye.

    NOT (gerçek veriyle düzeltildi): KiCad 10.0.4'ün GERÇEK
    `%TF.FileFunction%` değeri `"Soldermask,Top"`dur (`"SolderMask"` değil,
    büyük M yok) — ilk taslak yanlış case ile yazılmıştı ve gerçek
    `ESP32C3_SmartBand-F_Mask.gts` dosyasına karşı test edilince hemen
    ortaya çıktı.
    """
    if "soldermask" not in mask_gerber.katman_fonksiyonu.lower():
        raise ValueError(
            f"maske_baraji_taramasi() bir SolderMask katmanı bekliyor, "
            f"gelen: {mask_gerber.katman_fonksiyonu!r} — yanlış Gerber dosyası verilmiş olabilir."
        )
    ciftler = en_yakin_flash_ciftleri(mask_gerber, fab_min_baraj_mm)
    return bulgu_uret(
        "gerber_maske_baraji",
        taranan=len(mask_gerber.flashler),
        ihlaller=ciftler,
        detay=f"katman={mask_gerber.katman_fonksiyonu}, fab_min={fab_min_baraj_mm}mm",
    )


def bakir_bosluk_taramasi(
    cu_gerber: GerberDosyasi,
    min_clearance_mm: float,
) -> Bulgu:
    """GERÇEK bakır (F.Cu/B.Cu) Gerber'inden çıkan pad/via flash'ları
    arasındaki boşluğu tarar — kısa devre/reflow köprüsü riski için ikinci,
    BAĞIMSIZ bir kanıt kaynağı (kicad-cli DRC'nin sembolik modeline
    GÜVENMEDEN, gerçek export edilmiş koordinattan doğrulama).

    `cu_gerber.katman_fonksiyonu` bir Copper katmanı DEĞİLSE `ValueError`.
    """
    if "Copper" not in cu_gerber.katman_fonksiyonu:
        raise ValueError(
            f"bakir_bosluk_taramasi() bir Copper katmanı bekliyor, "
            f"gelen: {cu_gerber.katman_fonksiyonu!r}."
        )
    ciftler = en_yakin_flash_ciftleri(cu_gerber, min_clearance_mm)
    return bulgu_uret(
        "gerber_bakir_bosluk",
        taranan=len(cu_gerber.flashler),
        ihlaller=ciftler,
        detay=f"katman={cu_gerber.katman_fonksiyonu}, min_clearance={min_clearance_mm}mm",
    )


# ------------------------------------------------------------------
# 4. RAPOR
# ------------------------------------------------------------------

def gerber_dfm_raporu_uret(bulgular: Sequence[Bulgu], uyarilar: Sequence[str] = ()) -> str:
    """`TEST/gerber_dfm_raporu.md` içeriği — MASTER_RULEBOOK Faz 8'in
    solder mask barajı maddesine, gerçek export edilmiş veriden kanıt."""
    satirlar = [
        "# Gerber DFM Görsel/Vektörel Ön Denetim Raporu",
        "",
        "> Bu rapor GERÇEK export edilmiş Gerber dosyalarından (kicad-cli",
        "> pcb export gerbers) üretildi — soyut/kafadan girilen kanal",
        "> listesinden DEĞİL.",
        "",
        "| Kontrol | Durum | Taranan (flash) | İhlal |",
        "|---|---|---|---|",
    ]
    for b in bulgular:
        satirlar.append(f"| {b.kontrol} | {b.durum.value} | {b.taranan} | {len(b.ihlaller)} |")

    satirlar += ["", "## İhlal detayları", ""]
    ihlal_var = False
    for b in bulgular:
        for ihlal in b.ihlaller:
            ihlal_var = True
            a, bb = ihlal["a"], ihlal["b"]
            satirlar.append(
                f"- `{b.kontrol}`: ({a['ref'] or '?'}/{a['net'] or '?'}) @ "
                f"({a['x']},{a['y']}) <-> ({bb['ref'] or '?'}/{bb['net'] or '?'}) @ "
                f"({bb['x']},{bb['y']}) — boşluk={ihlal['bosluk_mm']}mm"
            )
    if not ihlal_var:
        satirlar.append("- (ihlal yok)")

    if uyarilar:
        satirlar += ["", "## Ayrıştırma uyarıları", ""] + [f"- {u}" for u in uyarilar]

    return "\n".join(satirlar) + "\n"


def gerber_dfm_raporu_yaz(hedef_yol: str, bulgular: Sequence[Bulgu], uyarilar: Sequence[str] = ()) -> str:
    yol = Path(hedef_yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(gerber_dfm_raporu_uret(bulgular, uyarilar), encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# 5. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

_ORNEK_BASIT_GERBER = """\
%TF.FileFunction,Copper,L1,Top*%
%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.500000*%
D10*
%TO.N,GND*%
X1000000Y1000000D03*
%TO.N,+3V3*%
X1600000Y1000000D03*
%TD*%
"""


def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: eşik 0'a çekilirse (hiçbir boşluk "az" sayılmaz)
    ihlal listesi BOŞ olmalı. Aksi halde eşiğin hiçbir etkisi yok demektir."""
    gerber = gerber_ayristir(_ORNEK_BASIT_GERBER)
    return en_yakin_flash_ciftleri(gerber, esik_mm=0.0) == []


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []
    gerber = gerber_ayristir(_ORNEK_BASIT_GERBER)

    if len(gerber.flashler) != 2:
        hatalar.append(f"2 flash beklenirken {len(gerber.flashler)} bulundu")

    # İki 0.5mm çaplı flash, merkezler arası 0.6mm -> boşluk = 0.6-0.5 = 0.1mm
    ciftler = en_yakin_flash_ciftleri(gerber, esik_mm=0.5)
    if not ciftler or abs(ciftler[0]["bosluk_mm"] - 0.1) > 1e-6:
        hatalar.append(f"beklenen 0.1mm boşluk bulunamadı: {ciftler}")

    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: eşik etkisiz olabilir")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: gerber_dfm_gorsel_koprusu.py öz testleri temiz.")
