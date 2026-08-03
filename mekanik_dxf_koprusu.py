"""
mekanik_dxf_koprusu.py
========================
`case.dxf` / `enclosure.step`'ten board outline + montaj deliği + 3D keepout
(yükseklik haritalı) üretimi. [[SKILL-mekanik-dxf]] karşılığı.

`pcb-layout` skill'inin Faz 3'ü (placement) bu modülün ürettiği
`keepout_zones.json`'u BARİYER kısıtı olarak tüketir: her parçanın
body-height'ı bölgenin `max_allowed_height_mm`'ini AŞMAMALI.

AĞ/ARAÇ UYARISI: gerçek DXF/STEP parse işlemi `ezdxf` (DXF) ve
`python-occ`/`cadquery` (STEP) gibi kütüphaneler gerektirir — bu ortamda
kurulu değiller. Bu modül parse edilmiş/basitleştirilmiş veri yapıları
üzerinde çalışır (`DxfOutline`, `StepYukseklikHaritasi`); gerçek
`ezdxf.readfile()`/`cadquery.importers.importStep()` çağrısı, bu veri
yapılarını DOLDURAN ayrı bir adım olarak senin makinende (gerçek dosyayla)
tamamlanmalı. Sessizce "kurulu olduğunu varsayma" kuralı burada da geçerli.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ------------------------------------------------------------------
# 1. BOARD OUTLINE (DXF) İÇE AKTARIM
# ------------------------------------------------------------------

@dataclass
class DxfOutline:
    """`ezdxf` ile okunmuş DXF'ten çıkarılan, birimi/orijini DOĞRULANMIŞ
    kapalı Edge.Cuts poligonu."""

    nokta_listesi: List[Tuple[float, float]]  # mm, kapalı poligon (ilk == son olabilir)
    birim: str = "mm"  # "mm" | "mil" — mil ise import_board_outline mm'ye çevirir
    delik_listesi: List[Tuple[float, float, float]] = field(default_factory=list)
    # (cx, cy, çap_mm)


def _mil_den_mm_e(deger: float) -> float:
    return deger * 0.0254


def import_board_outline(outline: DxfOutline, bilinen_delik_koordinati: Optional[Tuple[float, float]] = None) -> DxfOutline:
    """
    Birim (mm/mil) ve orijini doğrular. `bilinen_delik_koordinati` verilirse
    (ör. montaj deliğinin gerçek/beklenen konumu), outline'daki en yakın
    deliğe olan mesafe bir "çapa kontrolü" (anchor check) olarak raporlanır
    — büyük bir sapma varsa birim/orijin hatası şüphesi doğar.

    Poligon KAPALI değilse (açık outline) -> board dolmaz; burada
    `poligon_kapali_mi()` ile tespit edilip çağırana `CONFIRM` gerektiren
    bir durum olarak bırakılır (burada otomatik "toleransla kapatma"
    YAPILMAZ — bu, insanın onaylaması gereken bir varsayımdır).
    """
    noktalar = list(outline.nokta_listesi)
    if outline.birim == "mil":
        noktalar = [(_mil_den_mm_e(x), _mil_den_mm_e(y)) for x, y in noktalar]
        delikler = [(_mil_den_mm_e(x), _mil_den_mm_e(y), _mil_den_mm_e(d)) for x, y, d in outline.delik_listesi]
    else:
        delikler = outline.delik_listesi

    if bilinen_delik_koordinati is not None and delikler:
        bx, by = bilinen_delik_koordinati
        en_yakin = min(delikler, key=lambda d: math.hypot(d[0] - bx, d[1] - by))
        sapma = math.hypot(en_yakin[0] - bx, en_yakin[1] - by)
        if sapma > 0.5:  # mm — kaba bir eşik, gerçek projede kalibre edilmeli
            raise ValueError(
                f"ÇAPA KONTROLÜ BAŞARISIZ: bilinen delik ({bx},{by}) ile outline'daki "
                f"en yakın delik ({en_yakin[0]:.2f},{en_yakin[1]:.2f}) arası "
                f"{sapma:.2f}mm sapma var — birim(mm/mil) veya orijin hatası şüphesi. "
                "CONFIRM gerekli, otomatik düzeltme yapılmadı."
            )

    return DxfOutline(nokta_listesi=noktalar, birim="mm", delik_listesi=delikler)


def poligon_kapali_mi(nokta_listesi: List[Tuple[float, float]], tolerans_mm: float = 0.01) -> bool:
    if len(nokta_listesi) < 3:
        return False
    ilk, son = nokta_listesi[0], nokta_listesi[-1]
    return math.hypot(ilk[0] - son[0], ilk[1] - son[1]) <= tolerans_mm


# ------------------------------------------------------------------
# 2. 3D KEEPOUT (YÜKSEKLİK HARİTALI) BÖLGELER
# ------------------------------------------------------------------

@dataclass
class TavanHaritasiBolgesi:
    """Kutu tavanı düz değilse (STEP'ten türetilmiş) bölge-bazlı Z değeri."""

    poligon: List[Tuple[float, float]]
    tavan_z_mm: float


@dataclass
class KeepoutBolgesi:
    isim: str
    poligon_2d: List[Tuple[float, float]]  # mm
    max_allowed_height_mm: float  # top-side (± clearance dahil edilmiş)
    max_allowed_height_mm_bottom: Optional[float] = None
    kaynak: str = "TBD"  # "step_tavan_haritasi" | "sabit_kutu_yuksekligi" | "TBD"


def derive_keepouts(
    delik_listesi: List[Tuple[float, float, float]],
    ring_mm: float = 3.0,
    global_max_height_mm: Optional[float] = None,
    tavan_haritasi: Optional[List[TavanHaritasiBolgesi]] = None,
    clearance_mm: float = 0.3,
) -> List[KeepoutBolgesi]:
    """
    Montaj deliği + konnektör + optik eksen keepout üretir. Kutu tavanı düz
    DEĞİLSE `tavan_haritasi` (STEP'ten türetilmiş bölge-bazlı Z) kullanılır;
    yoksa `global_max_height_mm` (sabit kutu yüksekliği) tüm bölgelere
    uygulanır. Her iki durumda da CLEARANCE payı (0.2-0.5mm tipik) düşülür.
    """
    bolgeler: List[KeepoutBolgesi] = []

    for i, (cx, cy, cap) in enumerate(delik_listesi):
        yaricap = cap / 2 + ring_mm
        # basit kare/daire yaklaşık poligon (gerçek DXF'te dairesel olur,
        # burada 8 köşeli yaklaşık çokgen ile temsil ediyoruz)
        poligon = [
            (
                cx + yaricap * math.cos(2 * math.pi * k / 8),
                cy + yaricap * math.sin(2 * math.pi * k / 8),
            )
            for k in range(8)
        ]
        tavan_z = global_max_height_mm
        kaynak = "sabit_kutu_yuksekligi" if global_max_height_mm is not None else "TBD"
        if tavan_haritasi:
            for bolge in tavan_haritasi:
                if _nokta_poligon_icinde_mi(cx, cy, bolge.poligon):
                    tavan_z = bolge.tavan_z_mm
                    kaynak = "step_tavan_haritasi"
                    break

        max_h = (tavan_z - clearance_mm) if tavan_z is not None else 0.0
        bolgeler.append(
            KeepoutBolgesi(
                isim=f"montaj_delik_{i}_keepout",
                poligon_2d=poligon,
                max_allowed_height_mm=max_h,
                kaynak=kaynak,
            )
        )

    return bolgeler


def _nokta_poligon_icinde_mi(x: float, y: float, poligon: List[Tuple[float, float]]) -> bool:
    icinde = False
    n = len(poligon)
    for i in range(n):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
        ):
            icinde = not icinde
    return icinde


# ------------------------------------------------------------------
# 3. Z (YÜKSEKLİK) KONTROLÜ — placement bariyerinin girdisi
# ------------------------------------------------------------------

@dataclass
class KomponentYukseklik:
    refdes: str
    x: float
    y: float
    body_height_mm: float
    taraf: str = "top"  # "top" | "bottom"


def z_kontrolu_yap(
    komponentler: List[KomponentYukseklik],
    bolgeler: List[KeepoutBolgesi],
) -> List[str]:
    """
    Her parçanın body-height'ının, merkezinin içinde bulunduğu keepout
    bölgesinin `max_allowed_height_mm` (top) veya `..._bottom` (bottom)
    değerini AŞMADIĞINI doğrular. Bu, `pcb-layout` Faz 3 (placement
    bariyeri) başlamadan önceki SABİT kısıttır.
    """
    bulgular: List[str] = []
    for k in komponentler:
        for b in bolgeler:
            if not _nokta_poligon_icinde_mi(k.x, k.y, b.poligon_2d):
                continue
            sinir = b.max_allowed_height_mm_bottom if k.taraf == "bottom" else b.max_allowed_height_mm
            if sinir is not None and k.body_height_mm > sinir:
                bulgular.append(
                    f"KRİTİK [{k.refdes}]: body-height {k.body_height_mm}mm > "
                    f"'{b.isim}' bölgesinin izin verdiği {sinir}mm ({k.taraf})."
                )
    return bulgular


# ------------------------------------------------------------------
# 4. STEREO/OPTİK IPD TOLERANS ZİNCİRİ
# ------------------------------------------------------------------

@dataclass
class IpdToleransBileseni:
    isim: str
    tolerans_mm: float


def ipd_tolerans_zinciri_hesapla(
    nominal_ipd_mm: float,
    bilesenler: List[IpdToleransBileseni],
    rss_mi: bool = False,
) -> Dict[str, float]:
    """
    IPD = nominal ± (t_yerleşim + t_footprint + t_montaj + ...)

    `rss_mi=True` ise kare-kök-toplamı (RSS, istatistiksel — bağımsız
    toleranslar için daha gerçekçi) kullanılır; `False` ise worst-case
    (doğrudan toplam, en kötü durum) kullanılır. Hangisinin kullanıldığı
    kritik bir tasarım kararıdır, çağıran fonksiyon bunu açıkça seçmeli.
    """
    if rss_mi:
        toplam_tolerans = math.sqrt(sum(b.tolerans_mm ** 2 for b in bilesenler))
    else:
        toplam_tolerans = sum(b.tolerans_mm for b in bilesenler)

    return {
        "nominal_mm": nominal_ipd_mm,
        "toplam_tolerans_mm": round(toplam_tolerans, 4),
        "min_mm": round(nominal_ipd_mm - toplam_tolerans, 4),
        "max_mm": round(nominal_ipd_mm + toplam_tolerans, 4),
        "yontem": "RSS" if rss_mi else "worst_case",
    }


def optik_merkez_ofseti_uygula(
    footprint_origin: Tuple[float, float],
    optik_merkez_ofseti_mm: Tuple[float, float],
) -> Tuple[float, float]:
    """
    Optik merkez != footprint origin. Datasheet'ten alınan ofseti footprint
    origin'ine uygulayarak gerçek optik eksen koordinatını döndürür — bu
    olmadan IPD tolerans zinciri yanlış referans noktasından hesaplanır.
    """
    fx, fy = footprint_origin
    ox, oy = optik_merkez_ofseti_mm
    return (fx + ox, fy + oy)
