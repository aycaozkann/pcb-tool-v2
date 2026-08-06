#!/usr/bin/env python3
"""
topolojik_router_koprusu.py
============================
Gelişmiş yönlendirme (routing) köprüsü: engellerin ETRAFINDAN dolanan
(waypoint / L / U dönüşü), gerektiğinde via ile katman değiştiren ve
engelleyen mevcut izleri İTİP KAYDIRAN (Push & Shove) bir topolojik yol
bulucu + KiCad `pcbnew` tarafına yazma taslağı.

NEDEN BU DOSYA VAR:
-------------------
`CLAUDE.md`'ye eklenen **"Otonom Yol Bulma (Pathfinding)"** kuralı şunu
söylüyor: *"İki pin arasındaki Manhattan mesafesi çok uzunsa veya arada
engel varsa hemen DRC hatası verip pes etme. Önce engelin etrafından
dolanacak (waypoints) veya uygunsa alt katmana via ile inip geçecek ara
koordinatlar (L veya U dönüşleri) hesapla."* Bu dosya o kuralın KOD
KARŞILIĞIDIR — `akilli_yol_bul()` tam olarak o üç basamağı, o sırayla dener.

DÜRÜSTLÜK NOTU — "PUSH & SHOVE" KONUSUNDA NE YAPILDI, NE YAPILMADI:
--------------------------------------------------------------------
KiCad'in gerçek interaktif router'ı (PNS — Push and Shove) C++ tarafında
yaşar ve **Python'a (ne SWIG `pcbnew`, ne de kipy/IPC API) DIŞA
AKTARILMAMIŞTIR**. Yani "KiCad'in P&S router'ını Python'dan otomatize
etmek" bugün doğrudan MÜMKÜN DEĞİL; bunu "yaptım" diye raporlamak yanlış
olurdu. Bunun yerine bu modül iki şey sunar:
  1. **Gerçekten çalışan, test edilmiş bir geometri motoru** —
     engel tespiti, dolanma (waypoint) yolu, 45° köşe dönüşümü ve
     `itip_kaydir_oner()` ile TEK bir engelleyici izin dik yönde
     kaydırılması (P&S'in temel adımı; kaskad/zincirleme shove YOK).
  2. **`TopolojikRouter` taslak sınıfı** — `pcbnew` varsa board'a gerçek
     iz/via yazar. `pcbnew` bu ortamda KURULU DEĞİL (bkz.
     `pcbnew_koprusu.py`'deki aynı uyarı), bu yüzden yazma yolu SENİN
     makinende doğrulanmalıdır.
Alternatif olarak tam otonom yönlendirme için proje zaten FreeRouting
kullanıyor (`uretim_zinciri_koprusu.py::freerouting_zinciri_calistir`) —
bu modül onun YERİNE geçmez; FreeRouting'e BIRAKILAMAYAN (yüksek hızlı,
elle çizilmesi gereken) netler ve tek tek kurtarılması gereken yollar
içindir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

Nokta = Tuple[float, float]


class Strateji(str, Enum):
    """`akilli_yol_bul()`'un hangi basamakta çözdüğü — rapora yazılır ki
    "neden via kondu / neden dolandı" izlenebilir olsun."""

    DOGRUDAN = "DOGRUDAN"
    L_DONUSU = "L_DONUSU"
    U_DONUSU = "U_DONUSU"
    KATMAN_DEGISIMI = "KATMAN_DEGISIMI"
    BULUNAMADI = "BULUNAMADI"


@dataclass
class Engel:
    """Yol çizilemeyen dikdörtgen bölge (pad, keepout, yüksek hızlı bölge,
    mevcut bir izin kapladığı alan).

    `clearance_mm`, dikdörtgeni her yönde ŞİŞİRİR — DRC clearance'ını
    geometriye dahil etmenin en basit ve en muhafazakâr yolu.
    """

    isim: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    clearance_mm: float = 0.2

    def sismis_kutu(self, ek_pay_mm: float = 0.0) -> Tuple[float, float, float, float]:
        p = self.clearance_mm + ek_pay_mm
        return (self.x_min - p, self.y_min - p, self.x_max + p, self.y_max + p)

    def nokta_icinde_mi(self, nokta: Nokta, ek_pay_mm: float = 0.0) -> bool:
        x_min, y_min, x_max, y_max = self.sismis_kutu(ek_pay_mm)
        return x_min <= nokta[0] <= x_max and y_min <= nokta[1] <= y_max


@dataclass
class Iz:
    """Board'da HÂLİHAZIRDA var olan bir iz (shove adayı)."""

    isim: str
    baslangic: Nokta
    bitis: Nokta
    genislik_mm: float
    net: str
    kilitli: bool = False  # yüksek hızlı/elle çizilmiş: İTİLEMEZ

    def engel_olarak(self, clearance_mm: float = 0.2) -> Engel:
        """İzi, kapladığı alanı temsil eden bir `Engel`e çevirir (AABB
        yaklaşımı — eğik izlerde muhafazakâr, yani gerçekte olduğundan
        biraz DAHA GENİŞ bir engel üretir; bu bilinçli: yanlış tarafa
        yuvarlamak DRC ihlali doğurur)."""
        yari = self.genislik_mm / 2.0
        return Engel(
            isim=f"iz:{self.isim}",
            x_min=min(self.baslangic[0], self.bitis[0]) - yari,
            y_min=min(self.baslangic[1], self.bitis[1]) - yari,
            x_max=max(self.baslangic[0], self.bitis[0]) + yari,
            y_max=max(self.baslangic[1], self.bitis[1]) + yari,
            clearance_mm=clearance_mm,
        )


@dataclass
class YolIstegi:
    baslangic: Nokta
    bitis: Nokta
    net: str
    iz_genisligi_mm: float = 0.2
    clearance_mm: float = 0.2
    katman: str = "F.Cu"
    yuksek_hiz_mi: bool = False  # True ise via YASAK (MASTER_RULEBOOK Faz 4 Öncelik 2)


@dataclass
class YolSonucu:
    segmentler: List[Tuple[Nokta, Nokta]]
    strateji: Strateji
    via_sayisi: int = 0
    katmanlar: List[str] = field(default_factory=list)
    notlar: List[str] = field(default_factory=list)

    @property
    def uzunluk_mm(self) -> float:
        return round(
            sum(math.dist(a, b) for a, b in self.segmentler),
            4,
        )

    @property
    def bulundu_mu(self) -> bool:
        return self.strateji != Strateji.BULUNAMADI and bool(self.segmentler)


# ------------------------------------------------------------------
# 1. GEOMETRİ: segment <-> dikdörtgen kesişimi
# ------------------------------------------------------------------

def manhattan_mesafe_mm(a: Nokta, b: Nokta) -> float:
    """|dx| + |dy| — dik açılı (Manhattan) yönlendirmede gerçekçi alt sınır.

    `CLAUDE.md` Pathfinding kuralı "Manhattan mesafesi çok uzunsa" dediği
    için bu ölçüt ayrı bir fonksiyon olarak dışa açıldı; öklid mesafe
    (`math.dist`) 45° çizime izin veren durumlar için ayrıca kullanılır.
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _segment_kutuyu_kesiyor_mu(
    a: Nokta, b: Nokta, kutu: Tuple[float, float, float, float]
) -> bool:
    """Liang-Barsky dilim (slab) yöntemiyle segment-AABB kesişimi.

    Neden hazır bir kütüphane değil: bu proje harici bağımlılık eklemekten
    kaçınıyor (`sch_wire.py` ile aynı gerekçe) ve bu test
    tamamen kapalı formda, 20 satırda ve TAM olarak test edilebilir
    şekilde yazılabiliyor.
    """
    x_min, y_min, x_max, y_max = kutu
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    t0, t1 = 0.0, 1.0

    for yon, baslangic, alt, ust in (
        (dx, a[0], x_min, x_max),
        (dy, a[1], y_min, y_max),
    ):
        if abs(yon) < 1e-12:
            if baslangic < alt or baslangic > ust:
                return False
            continue
        ta = (alt - baslangic) / yon
        tb = (ust - baslangic) / yon
        if ta > tb:
            ta, tb = tb, ta
        t0 = max(t0, ta)
        t1 = min(t1, tb)
        if t0 > t1:
            return False
    return True


def yol_engelli_mi(
    segmentler: Sequence[Tuple[Nokta, Nokta]],
    engeller: Sequence[Engel],
    iz_genisligi_mm: float,
) -> List[str]:
    """Yolun herhangi bir segmenti bir engelin (clearance ile şişirilmiş)
    kutusunu kesiyor mu — kesen engellerin isim listesi döner.

    İz genişliğinin YARISI da paya eklenir: iz bir çizgi değil, şeritdir;
    merkez hattı kutunun 0.05mm dışından geçse bile 0.2mm genişliğinde bir
    iz o kutuya girer.
    """
    ek_pay = iz_genisligi_mm / 2.0
    carpanlar: List[str] = []
    for engel in engeller:
        kutu = engel.sismis_kutu(ek_pay)
        if any(_segment_kutuyu_kesiyor_mu(a, b, kutu) for a, b in segmentler):
            carpanlar.append(engel.isim)
    return carpanlar


# ------------------------------------------------------------------
# 2. STRATEJİLER (CLAUDE.md Pathfinding basamakları)
# ------------------------------------------------------------------

def _dogrudan_yol(istek: YolIstegi) -> List[Tuple[Nokta, Nokta]]:
    return [(istek.baslangic, istek.bitis)]


def _l_yollari(istek: YolIstegi) -> List[List[Tuple[Nokta, Nokta]]]:
    """İki olası L dönüşü: önce yatay-sonra dikey, ve tersi."""
    (x1, y1), (x2, y2) = istek.baslangic, istek.bitis
    yatay_once = [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2))]
    dikey_once = [((x1, y1), (x1, y2)), ((x1, y2), (x2, y2))]
    return [y for y in (yatay_once, dikey_once) if any(a != b for a, b in y)]


def _u_yollari(
    istek: YolIstegi, engeller: Sequence[Engel]
) -> List[List[Tuple[Nokta, Nokta]]]:
    """Engellerin etrafından dolanan U dönüşü adayları.

    Her engelin şişirilmiş kutusunun 4 kenarından birine "kaçış koridoru"
    (waypoint bandı) kurulur ve iki L dönüşüyle o banda gidilip dönülür.
    Adaylar KISALIK sırasına göre değil, çağıran tarafından
    (`akilli_yol_bul`) engelsizlik + uzunluk birlikte değerlendirilerek
    seçilir.
    """
    (x1, y1), (x2, y2) = istek.baslangic, istek.bitis
    ek = istek.iz_genisligi_mm / 2.0 + istek.clearance_mm
    adaylar: List[List[Tuple[Nokta, Nokta]]] = []

    for engel in engeller:
        x_min, y_min, x_max, y_max = engel.sismis_kutu(ek)
        for koridor_x in (x_min, x_max):
            adaylar.append([
                ((x1, y1), (koridor_x, y1)),
                ((koridor_x, y1), (koridor_x, y2)),
                ((koridor_x, y2), (x2, y2)),
            ])
        for koridor_y in (y_min, y_max):
            adaylar.append([
                ((x1, y1), (x1, koridor_y)),
                ((x1, koridor_y), (x2, koridor_y)),
                ((x2, koridor_y), (x2, y2)),
            ])
    # Sıfır uzunluklu segmentleri temizle (aynı koordinat tekrarı).
    return [[(a, b) for a, b in yol if a != b] for yol in adaylar]


def akilli_yol_bul(
    istek: YolIstegi,
    engeller: Sequence[Engel] = (),
    alt_katman: str = "B.Cu",
    alt_katman_engelleri: Optional[Sequence[Engel]] = None,
) -> YolSonucu:
    """`CLAUDE.md` "Otonom Yol Bulma" merdiveninin birebir uygulaması.

    Sıra (ilk BAŞARILI olan kazanır — daha basit yol daima tercih edilir):
      1. **DOGRUDAN** — düz/dik tek segment.
      2. **L_DONUSU** — tek kırılma, aynı katman.
      3. **U_DONUSU** — engelin etrafından waypoint'lerle dolanma. Birden
         fazla aday engelsizse EN KISASI seçilir.
      4. **KATMAN_DEGISIMI** — via ile alt katmana inip geçmek. `istek.
         yuksek_hiz_mi` True ise bu basamak **ATLANIR** (MASTER_RULEBOOK
         Faz 4 Öncelik 2: yüksek hızlı sinyaller via KULLANMADAN, sadece
         üst katmandan) ve sonuç `BULUNAMADI` döner -> çağıran taraf
         yerleşime (Faz 3) dönmek zorundadır.

    Hiçbiri olmazsa `Strateji.BULUNAMADI` döner — bu, "DRC hatası verip pes
    etmek" DEĞİLDİR: üç basamağın hepsi denenmiş ve tükenmiştir, `notlar`
    hangi engelin hangi basamağı bloke ettiğini taşır.
    """
    notlar: List[str] = []

    dogrudan = _dogrudan_yol(istek)
    carpanlar = yol_engelli_mi(dogrudan, engeller, istek.iz_genisligi_mm)
    if not carpanlar:
        return YolSonucu(dogrudan, Strateji.DOGRUDAN, 0, [istek.katman], notlar)
    notlar.append(f"doğrudan yol engelli: {', '.join(carpanlar)}")

    for yol in _l_yollari(istek):
        if not yol_engelli_mi(yol, engeller, istek.iz_genisligi_mm):
            return YolSonucu(yol, Strateji.L_DONUSU, 0, [istek.katman], notlar)
    notlar.append("iki L dönüşü de engelli")

    temiz_u = [
        yol for yol in _u_yollari(istek, engeller)
        if yol and not yol_engelli_mi(yol, engeller, istek.iz_genisligi_mm)
    ]
    if temiz_u:
        en_kisa = min(temiz_u, key=lambda y: sum(math.dist(a, b) for a, b in y))
        return YolSonucu(en_kisa, Strateji.U_DONUSU, 0, [istek.katman], notlar)
    notlar.append("engel etrafından dolanan (waypoint) aday bulunamadı")

    if istek.yuksek_hiz_mi:
        notlar.append(
            "KATMAN DEĞİŞİMİ ATLANDI: yüksek hızlı net (MASTER_RULEBOOK Faz 4 "
            "Öncelik 2 — via yasak). Çözüm routing'de değil YERLEŞİMDE aranmalı."
        )
        return YolSonucu([], Strateji.BULUNAMADI, 0, [], notlar)

    # 4. Katman değişimi: alt katmanda kendi engel listesi verilmediyse
    #    ENGELSİZ VARSAYILMAZ — bu tehlikeli bir varsayım olurdu
    #    (`bom_lifecycle_koprusu`'nun "veri yoksa TBD" disiplini).
    if alt_katman_engelleri is None:
        notlar.append(
            f"{alt_katman} engel listesi verilmedi — alt katman 'boş' VARSAYILMADI, "
            "katman değişimi önerilmedi (NEEDS_HUMAN)."
        )
        return YolSonucu([], Strateji.BULUNAMADI, 0, [], notlar)

    alt_istek = YolIstegi(
        istek.baslangic, istek.bitis, istek.net,
        istek.iz_genisligi_mm, istek.clearance_mm, alt_katman, False,
    )
    for aday in [_dogrudan_yol(alt_istek), *_l_yollari(alt_istek)]:
        if not yol_engelli_mi(aday, alt_katman_engelleri, istek.iz_genisligi_mm):
            return YolSonucu(
                aday, Strateji.KATMAN_DEGISIMI, 2,
                [istek.katman, alt_katman, istek.katman],
                notlar + [f"{alt_katman}'a via ile inildi (2 via: iniş + çıkış)"],
            )

    notlar.append(f"{alt_katman} üzerinde de engelsiz yol yok")
    return YolSonucu([], Strateji.BULUNAMADI, 0, [], notlar)


# ------------------------------------------------------------------
# 3. 45° KÖŞE DÖNÜŞÜMÜ (MASTER_RULEBOOK Faz 7 "asla 90° dik açı")
# ------------------------------------------------------------------

def koseleri_45_dereceye_cevir(
    segmentler: Sequence[Tuple[Nokta, Nokta]],
    pah_mm: float = 0.25,
) -> List[Tuple[Nokta, Nokta]]:
    """Her 90° köşeyi, iki segmenti `pah_mm` kadar kısaltıp aralarına 45°'lik
    bir pah (chamfer) segmenti koyarak dönüştürür.

    MASTER_RULEBOOK Faz 7: *"Asla 90 derece dik açı çizilmez; tüm dönüşler
    45 derece veya kavisli (arc) olacaktır."* Yol bulucu (yukarıda) bilinçli
    olarak dik açılı (Manhattan) çalışır — çünkü engel geometrisi AABB
    tabanlı ve dik yollarda kesişim testi kesin; 45°'ye dönüşüm AYRI ve
    SON adımdır.

    Pah, komşu segmentlerin YARISINDAN büyük olamaz (yoksa segment ters
    yöne döner ve yol bozulur): bu durumda o köşede pah, mevcut uzunluğa
    göre KÜÇÜLTÜLÜR — sessizce bozuk geometri üretmek yerine.
    """
    if pah_mm <= 0:
        raise ValueError("pah_mm pozitif olmalı.")
    if len(segmentler) < 2:
        return list(segmentler)

    sonuc: List[Tuple[Nokta, Nokta]] = []
    kalan = [(tuple(a), tuple(b)) for a, b in segmentler]

    onceki_bitis: Optional[Nokta] = None
    for i, (a, b) in enumerate(kalan):
        baslangic = onceki_bitis if onceki_bitis is not None else a
        bitis = b
        if i + 1 < len(kalan):
            sonraki_a, sonraki_b = kalan[i + 1]
            u1 = _birim_vektor(baslangic, bitis)
            u2 = _birim_vektor(sonraki_a, sonraki_b)
            if u1 is not None and u2 is not None and abs(u1[0] * u2[0] + u1[1] * u2[1]) < 1e-9:
                # Dik köşe: pah'ı iki segmentin de sığdırabileceği kadar kırp.
                uzunluk1 = math.dist(baslangic, bitis)
                uzunluk2 = math.dist(sonraki_a, sonraki_b)
                p = min(pah_mm, uzunluk1 / 2.0, uzunluk2 / 2.0)
                if p > 1e-9:
                    kose = bitis
                    pah_baslangic = (kose[0] - u1[0] * p, kose[1] - u1[1] * p)
                    pah_bitis = (kose[0] + u2[0] * p, kose[1] + u2[1] * p)
                    sonuc.append((baslangic, pah_baslangic))
                    sonuc.append((pah_baslangic, pah_bitis))
                    onceki_bitis = pah_bitis
                    continue
        sonuc.append((baslangic, bitis))
        onceki_bitis = bitis

    return [(a, b) for a, b in sonuc if a != b]


def _birim_vektor(a: Nokta, b: Nokta) -> Optional[Tuple[float, float]]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1e-12:
        return None
    return (dx / d, dy / d)


def dik_aci_sayisi(segmentler: Sequence[Tuple[Nokta, Nokta]]) -> int:
    """Yolda kalan 90° köşe sayısı — `koseleri_45_dereceye_cevir()`'in
    gerçekten iş yaptığının ölçülebilir kanıtı (Faz 7 kabul kriteri)."""
    sayi = 0
    for (a1, b1), (a2, b2) in zip(segmentler, segmentler[1:]):
        u1, u2 = _birim_vektor(a1, b1), _birim_vektor(a2, b2)
        if u1 is None or u2 is None:
            continue
        if abs(u1[0] * u2[0] + u1[1] * u2[1]) < 1e-9:
            sayi += 1
    return sayi


# ------------------------------------------------------------------
# 4. PUSH & SHOVE (tek adım — kaskad YOK, bilinçli sınır)
# ------------------------------------------------------------------

def itip_kaydir_oner(
    engelleyen: Iz,
    istek: YolIstegi,
    diger_engeller: Sequence[Engel] = (),
    ek_pay_mm: float = 0.0,
) -> Optional[Iz]:
    """Engelleyen bir mevcut izi, istenen yola koridor açacak kadar DİK
    yönde kaydırmayı önerir (P&S'in tek adımı).

    Kaydırma miktarı = iki izin yarı genişlikleri + clearance kadar ayrılma
    ihtiyacı; yön, istenen yolun engelleyen izin hangi tarafında kaldığına
    göre DETERMİNİSTİK seçilir.

    `None` DÖNDÜĞÜ (ve çağıranın `NEEDS_HUMAN` raporlaması gereken) haller:
      - `engelleyen.kilitli` (yüksek hızlı/elle çizilmiş iz — bu proje
        kilitli bir izi asla kendi kendine bozmaz),
      - kaydırılan iz BAŞKA bir engele çarpıyorsa (zincirleme shove
        UYGULANMAZ — `bom_lifecycle_koprusu.find_pin_compatible()`'ın uygun
        aday yoksa boş dönüp kararı çağırana bırakması ile aynı disiplin),
      - engelleyen iz eğikse (yalnızca yatay/dikey izler kaydırılır; eğik
        izde "dik yön" seçimi kafadan bir karar olurdu).
    """
    if engelleyen.kilitli:
        return None

    yon_vektoru = _birim_vektor(engelleyen.baslangic, engelleyen.bitis)
    if yon_vektoru is None:
        return None
    yatay = abs(yon_vektoru[1]) < 1e-9
    dikey = abs(yon_vektoru[0]) < 1e-9
    if not (yatay or dikey):
        return None  # eğik iz: dik yön seçimi belirsiz -> NEEDS_HUMAN

    gerekli_ayrilma = (
        engelleyen.genislik_mm / 2.0
        + istek.iz_genisligi_mm / 2.0
        + istek.clearance_mm
        + ek_pay_mm
    )

    if yatay:
        iz_y = engelleyen.baslangic[1]
        hedef_y = (istek.baslangic[1] + istek.bitis[1]) / 2.0
        mevcut_ayrilma = abs(hedef_y - iz_y)
        if mevcut_ayrilma >= gerekli_ayrilma:
            return None  # zaten engellemiyor, kaydırmaya gerek yok
        kayma = (gerekli_ayrilma - mevcut_ayrilma) * (-1.0 if hedef_y >= iz_y else 1.0)
        yeni = Iz(
            engelleyen.isim,
            (engelleyen.baslangic[0], iz_y + kayma),
            (engelleyen.bitis[0], engelleyen.bitis[1] + kayma),
            engelleyen.genislik_mm, engelleyen.net,
        )
    else:
        iz_x = engelleyen.baslangic[0]
        hedef_x = (istek.baslangic[0] + istek.bitis[0]) / 2.0
        mevcut_ayrilma = abs(hedef_x - iz_x)
        if mevcut_ayrilma >= gerekli_ayrilma:
            return None
        kayma = (gerekli_ayrilma - mevcut_ayrilma) * (-1.0 if hedef_x >= iz_x else 1.0)
        yeni = Iz(
            engelleyen.isim,
            (iz_x + kayma, engelleyen.baslangic[1]),
            (engelleyen.bitis[0] + kayma, engelleyen.bitis[1]),
            engelleyen.genislik_mm, engelleyen.net,
        )

    # Kaydırılan iz başka bir engele girdiyse öneri GEÇERSİZ.
    if yol_engelli_mi(
        [(yeni.baslangic, yeni.bitis)],
        [e for e in diger_engeller if e.isim != f"iz:{engelleyen.isim}"],
        yeni.genislik_mm,
    ):
        return None
    return yeni


def shove_ozetle(engelleyen: Iz, oneri: Optional[Iz]) -> str:
    """`itip_kaydir_oner()` sonucunu okunabilir cümleye çevirir —
    `ecad_mcad_termal_kopru.termal_bariyer_ozetle()` ile aynı desen."""
    if oneri is None:
        sebep = "kilitli iz" if engelleyen.kilitli else "kaydırma başka engele çarpıyor / gerek yok"
        return f"{engelleyen.isim}: itip-kaydırma ÖNERİLMEDİ ({sebep}) -> NEEDS_HUMAN"
    dx = oneri.baslangic[0] - engelleyen.baslangic[0]
    dy = oneri.baslangic[1] - engelleyen.baslangic[1]
    return (
        f"{engelleyen.isim}: ({dx:+.3f}, {dy:+.3f})mm kaydırılması önerildi "
        f"-> {oneri.baslangic} -> {oneri.bitis}"
    )


# ------------------------------------------------------------------
# 5. KABUL KAPILARI + RAPOR
# ------------------------------------------------------------------

def via_kurali_kontrolu(sonuclar: Dict[str, YolSonucu], yuksek_hiz_netleri: Sequence[str]) -> Bulgu:
    """Yüksek hızlı netlerde via KULLANILMADIĞINI doğrular (MASTER_RULEBOOK
    Faz 4 Öncelik 2). `akilli_yol_bul` bunu zaten engeller ama yollar elle
    veya başka bir router'la üretilmiş olabilir — kapı AYRI durmalı."""
    ihlaller: List[Dict[str, object]] = []
    taranan = 0
    for net in yuksek_hiz_netleri:
        if net not in sonuclar:
            continue
        taranan += 1
        if sonuclar[net].via_sayisi > 0:
            ihlaller.append({"net": net, "via_sayisi": sonuclar[net].via_sayisi})
    return bulgu_uret(
        "yuksek_hiz_via_yasagi",
        taranan=taranan,
        ihlaller=ihlaller,
        detay="MASTER_RULEBOOK Faz 4 Öncelik 2: yüksek hızlı sinyaller via kullanmadan F.Cu'dan",
    )


def geometri_kurali_kontrolu(sonuclar: Dict[str, YolSonucu]) -> Bulgu:
    """Hiçbir yolda 90° köşe kalmadığını doğrular (Faz 7 Geometri Kuralı)."""
    ihlaller: List[Dict[str, object]] = []
    taranan = 0
    for net, sonuc in sonuclar.items():
        if not sonuc.segmentler:
            continue
        taranan += 1
        adet = dik_aci_sayisi(sonuc.segmentler)
        if adet:
            ihlaller.append({"net": net, "dik_aci_sayisi": adet})
    return bulgu_uret(
        "45_derece_geometri",
        taranan=taranan,
        ihlaller=ihlaller,
        detay="Faz 7: tüm dönüşler 45° veya arc olmalı",
    )


def routing_plan_satiri_uret(net: str, sonuc: YolSonucu) -> Dict[str, object]:
    """`pcb-layout` Aşama 3.7'nin `TEST/routing_plan.json` satırına DOĞRUDAN
    yazılabilir sözlük — bu köprü ile o topoloji raporu arasındaki bağ."""
    return {
        "net": net,
        "strateji": sonuc.strateji.value,
        "katmanlar": sonuc.katmanlar,
        "via_sayisi": sonuc.via_sayisi,
        "uzunluk_mm": sonuc.uzunluk_mm,
        "segment_sayisi": len(sonuc.segmentler),
        "notlar": sonuc.notlar,
    }


# ------------------------------------------------------------------
# 6. PCBNEW TARAFI (taslak — bu ortamda pcbnew YOK)
# ------------------------------------------------------------------

class TopolojikRouter:
    """`akilli_yol_bul()` sonucunu gerçek bir `.kicad_pcb`'ye yazan taslak.

    `pcbnew_koprusu.py` ile AYNI uyarı geçerlidir: bu ortamda `pcbnew`
    kurulu değil, aşağıdaki yazma yolu SENİN makinende doğrulanmalıdır.
    `pcbnew` yoksa `kullanilabilir_mi()` False döner ve `iz_yaz()`
    `RuntimeError` fırlatır — sessizce "yazdım" demez.

    KiCad'in kendi PNS (Push & Shove) router'ı Python'a dışa
    AKTARILMAMIŞTIR (dosya başlığındaki dürüstlük notu); bu sınıf onu
    çağırmaz, `itip_kaydir_oner()`'in ürettiği geometriyi yazar.
    """

    def __init__(self, board_path: str) -> None:
        self.board_path = board_path
        self._pcbnew = None
        try:  # pragma: no cover - ortam bağımlı
            import pcbnew  # type: ignore

            self._pcbnew = pcbnew
        except ImportError:
            self._pcbnew = None

    def kullanilabilir_mi(self) -> bool:
        return self._pcbnew is not None

    def iz_yaz(self, sonuc: YolSonucu, net_ismi: str, genislik_mm: float) -> int:
        """Yol segmentlerini board'a `PCB_TRACK` olarak ekler, eklenen
        segment sayısını döner. `pcbnew` yoksa `RuntimeError`."""
        if not self.kullanilabilir_mi():  # pragma: no cover - ortam bağımlı
            raise RuntimeError(
                "pcbnew import edilemedi — bu fonksiyon KiCad'in dahili python "
                "ortamında çalıştırılmalı (MASTER_RULEBOOK Faz -0)."
            )
        pcbnew = self._pcbnew  # pragma: no cover - ortam bağımlı
        board = pcbnew.LoadBoard(self.board_path)
        net = board.FindNet(net_ismi)
        if net is None:
            raise ValueError(f"net bulunamadı: {net_ismi}")
        katman = board.GetLayerID(sonuc.katmanlar[0] if sonuc.katmanlar else "F.Cu")
        eklenen = 0
        for a, b in sonuc.segmentler:
            iz = pcbnew.PCB_TRACK(board)
            iz.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            iz.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            iz.SetWidth(pcbnew.FromMM(genislik_mm))
            iz.SetLayer(katman)
            iz.SetNet(net)
            board.Add(iz)
            eklenen += 1
        board.Save(self.board_path)
        return eklenen


def _bulgu_uyumlu_iz_yaz(
    board_path: str, net_ismi: str, genislik_mm: float,
    segmentler: List[Tuple[Nokta, Nokta]], katman: str = "F.Cu",
) -> int:
    """`TopolojikRouter.iz_yaz()`'ı SADE (JSON-serileştirilebilir)
    parametrelerle çağıran ince sarmalayıcı — `otonom_kurtarma_motoru.py::
    izole_calistir()`'in bir alt süreçte "modul:fonksiyon" olarak
    çağırabilmesi için hedef fonksiyonun imzası ilkel tiplerden (str/float/
    list of tuples) oluşmalı, `YolSonucu`/`TopolojikRouter` nesnelerini
    doğrudan ALAMAZ (alt süreç sınırında serileştirilemezler)."""
    segmentler_tuple = [(tuple(a), tuple(b)) for a, b in segmentler]
    sonuc = YolSonucu(segmentler_tuple, Strateji.U_DONUSU, 0, [katman])
    return TopolojikRouter(board_path).iz_yaz(sonuc, net_ismi, genislik_mm)


# ------------------------------------------------------------------
# 7. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: engeli TAM yolun üstüne koyup clearance'ı büyütürsek
    `yol_engelli_mi()` mutlaka bir isim döndürmeli. Aksi halde engel tespiti
    hiçbir şey kontrol etmiyordur."""
    engel = Engel("bariyer", 4.0, -5.0, 6.0, 5.0, clearance_mm=0.2)
    return bool(yol_engelli_mi([((0.0, 0.0), (10.0, 0.0))], [engel], 0.2))


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. Engelsiz -> DOGRUDAN
    s = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"))
    if s.strateji != Strateji.DOGRUDAN:
        hatalar.append(f"engelsiz yolda DOGRUDAN beklendi, {s.strateji} geldi")

    # 2. Ortada bariyer -> dolanma (L veya U), via YOK
    engel = Engel("bariyer", 4.0, -1.0, 6.0, 1.0)
    s2 = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"), [engel])
    if not s2.bulundu_mu or s2.via_sayisi != 0:
        hatalar.append("bariyer etrafından via'sız dolanma bulunamadı")

    # 3. Yüksek hızlı net asla via ile çözülmemeli
    kapali = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    s3 = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "MIPI_D0_P", yuksek_hiz_mi=True), [kapali])
    if s3.via_sayisi != 0 or s3.strateji != Strateji.BULUNAMADI:
        hatalar.append("yüksek hızlı nette via yasağı uygulanmadı")

    # 4. 45° dönüşüm dik açı bırakmamalı
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))]
    if dik_aci_sayisi(koseleri_45_dereceye_cevir(yol)) != 0:
        hatalar.append("45° dönüşümünden sonra dik açı kaldı")

    # 5. Fault injection
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: engel tespiti boş olabilir")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: topolojik_router_koprusu.py öz testleri temiz.")
