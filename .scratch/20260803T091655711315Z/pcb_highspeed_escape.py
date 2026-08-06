"""
pcb_highspeed_escape.py
========================
Yüksek hızlı diferansiyel çiftin paket/konnektör PAD'İNDEN ÇIKIŞ (escape)
geometrisini yönetir — [[SKILL-highspeed-length-match]]/[[SKILL-pcb-highspeed-escape]]
dokümanlarındaki kuralların gerçek Python koduna dönüştürülmüş hali.

`pcb_stackup_planner.py` hattın GÖVDESİNİ (empedans, length-match, coupling)
yönetiyordu; bu dosya hattın **pad'den çıktığı ilk 1-3 mm'sini** yönetir —
gerçek kartlarda hataların çoğu burada doğar ve standart clearance DRC'si
bunu YAKALAMAZ (soldermask ayrı bir üretim katmanıdır, DRC'nin bildiği bakır
clearance'tan bağımsız).

Neden ayrı dosya: `pcb_stackup_planner.py` zaten 1000+ satır; bu modül
tek bir dar konuya (escape geometrisi) odaklı, bağımsız test edilebilir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional


# ------------------------------------------------------------------
# 1. MASKE BARAJI (SOLDER MASK DAM) HESABI
# ------------------------------------------------------------------
#
# Pin-arası kanaldan geçen iz (ör. SOT-23-6 ESD dizisinde GND/VBUS pini iki
# veri pininin TAM ORTASINDA): bakır clearance yeterli görünse bile maske
# expansion payı düşüldüğünde maske basılamayacak kadar dar bir "baraj"
# kalabilir → iki pin arasında lehim köprüsü. Standart DRC "clearance"
# kontrolü bunu YAKALAMAZ çünkü o bakır-bakır mesafesine bakar, maskeye değil.

# Fab'in tipik minimum maske barajı (mm). Gerçek fab profiline göre override et
# (ör. JLCPCB tipik 0.20-0.25mm, üretici sayfasından TARİHLİ doğrulanmalı).
FAB_MIN_MASKE_BARAJI_MM = 0.20


@dataclass
class PinArasiKanal:
    """SOT-23-6 gibi paketlerde iki veri pini arasında kalan GND/VBUS pinine
    ulaşmak için izin geçmek zorunda olduğu dar kanal."""

    pad_sutun_araligi_mm: float
    """Komşu pad sütunlarının merkez-merkez mesafesi (datasheet footprint)."""
    pad_uzunlugu_mm: float
    """Pad'in kanal yönündeki uzunluğu (footprint)."""
    mask_expansion_mm: float = 0.05
    """Fab'in soldermask expansion değeri (tipik ~0.05mm, fab profilinden al)."""


def kanal_genisligi_hesapla_mm(kanal: PinArasiKanal) -> float:
    """Pad sütunları arasında izin geçebileceği boş kanal genişliği."""
    return kanal.pad_sutun_araligi_mm - kanal.pad_uzunlugu_mm


def maske_baraji_hesapla_mm(kanal: PinArasiKanal, iz_genisligi_mm: float) -> float:
    """
    İz, kanalın TAM ORTASINDAN simetrik geçtiği varsayılır.

    baraj = boşluk - 2 * mask_expansion
    boşluk = (kanal_genisligi - iz_genisligi) / 2
    """
    kanal_genisligi = kanal_genisligi_hesapla_mm(kanal)
    bosluk = (kanal_genisligi - iz_genisligi_mm) / 2
    baraj = bosluk - 2 * kanal.mask_expansion_mm
    return baraj


def maske_baraji_kontrolu(
    kanal: PinArasiKanal,
    iz_genisligi_mm: float,
    fab_min_baraj_mm: float = FAB_MIN_MASKE_BARAJI_MM,
) -> List[str]:
    """
    Verilen iz genişliği için maske barajını hesaplar ve fab minimumuyla
    karşılaştırır. İhlal varsa AÇIKLAYICI (ne olacağını söyleyen) bir uyarı
    döndürür — sessizce "false" dönmez, çünkü sonuç lehim köprüsü/kısa devre
    riskidir ve genelde 2 farklı net'i (ör. 5V ve veri hattı) birleştirir.
    """
    bulgular: List[str] = []
    baraj = maske_baraji_hesapla_mm(kanal, iz_genisligi_mm)
    kanal_genisligi = kanal_genisligi_hesapla_mm(kanal)

    if kanal_genisligi <= 0:
        bulgular.append(
            f"KRİTİK: pad sütun aralığı ({kanal.pad_sutun_araligi_mm}mm) <= pad "
            f"uzunluğu ({kanal.pad_uzunlugu_mm}mm) — kanal yok, iz pad'e değer (short)."
        )
        return bulgular

    if baraj < fab_min_baraj_mm:
        bulgular.append(
            f"KRİTİK: maske barajı {baraj:.3f}mm < fab minimumu {fab_min_baraj_mm}mm "
            f"(iz={iz_genisligi_mm}mm, kanal={kanal_genisligi:.3f}mm). "
            "Maske basılmaz -> pin-arası LEHİM KÖPRÜSÜ riski. "
            "İz genişliğini azalt, farklı (kısa pad'li) footprint kullan, "
            "veya izi via ile iç katmana taşı."
        )
    return bulgular


def maksimum_iz_genisligi_icin_baraj_mm(
    kanal: PinArasiKanal,
    fab_min_baraj_mm: float = FAB_MIN_MASKE_BARAJI_MM,
) -> float:
    """
    Verilen kanal için, fab minimum maske barajını SAĞLAYAN maksimum iz
    genişliğini geri çözer (iz genişliğini AKIM değil BARAJ belirler kuralı).

    baraj_min = (kanal - iz)/2 - 2*expansion
    => iz = kanal - 2*(baraj_min + 2*expansion)
    """
    kanal_genisligi = kanal_genisligi_hesapla_mm(kanal)
    iz_max = kanal_genisligi - 2 * (fab_min_baraj_mm + 2 * kanal.mask_expansion_mm)
    return max(iz_max, 0.0)


# ------------------------------------------------------------------
# 2. ÇİFTİN PAD SÜTUNUNA GİRMEDEN AÇILMASI
# ------------------------------------------------------------------

@dataclass
class DiferansiyelPadAcilimi:
    pad_boyu_mm: float
    """Ara pinin (GND/VBUS) kanal yönündeki pad uzunluğu."""
    cift_adimi_mm: float
    """Diferansiyel çiftin P/N arası pitch'i (pad merkez-merkez)."""


def acilma_gerekli_mi(acilim: DiferansiyelPadAcilimi) -> bool:
    """Ara pinin pad boyu >= çift adımından büyükse çift olduğu gibi
    giremez; pad'e değer (short) -> önceden açılmalı."""
    return acilim.pad_boyu_mm >= acilim.cift_adimi_mm


def acilma_mesafesi_hesapla_mm(acilim: DiferansiyelPadAcilimi) -> Optional[float]:
    """
    Çiftin pad sütununa girmeden kaç mm önce ±(pin_aralığı/2)'ye 45° ile
    açılması gerektiğini tahmini olarak döndürür (pad boyu ile aynı mertebe
    + pay). `None` dönerse açılmaya gerek yok.
    """
    if not acilma_gerekli_mi(acilim):
        return None
    # 45° açı ile pad boyu kadar yanal kaçış mesafesi kat edileceğinden,
    # boyuna mesafe de aynı mertebede + küçük bir pay gerekir.
    return round(acilim.pad_boyu_mm + 0.8, 3)


# ------------------------------------------------------------------
# 3. 90° KÖŞE KONTROLÜ
# ------------------------------------------------------------------

@dataclass
class RotaSegmenti:
    x1: float
    y1: float
    x2: float
    y2: float


def _yon_derece(seg: RotaSegmenti) -> float:
    return math.degrees(math.atan2(seg.y2 - seg.y1, seg.x2 - seg.x1))


def donus_acisi_hesapla(seg_a: RotaSegmenti, seg_b: RotaSegmenti) -> float:
    """İki ardışık segment arasındaki dönüş açısını (0-180°, mutlak) döndürür."""
    fark = abs(_yon_derece(seg_a) - _yon_derece(seg_b)) % 360
    if fark > 180:
        fark = 360 - fark
    return fark


def dik_acili_koseleri_bul(
    segmentler: List[RotaSegmenti],
    alt_esik: float = 85.0,
    ust_esik: float = 95.0,
) -> List[int]:
    """
    Ardışık segment çiftlerinin dönüş açısını ölçer; 85-95° aralığındaki
    (yaklaşık 90°, "asit tuzağı" + empedans çukuru riski) köşelerin index'ini
    döndürür. Kabul kriteri: bu liste BOŞ olmalı.
    """
    kotu_koseler: List[int] = []
    for i in range(len(segmentler) - 1):
        aci = donus_acisi_hesapla(segmentler[i], segmentler[i + 1])
        if alt_esik <= aci <= ust_esik:
            kotu_koseler.append(i)
    return kotu_koseler


# ------------------------------------------------------------------
# 4. SKEW'İ ps CİNSİNDEN DEĞERLENDİRME (gereksiz meander eklememe)
# ------------------------------------------------------------------

# FR4 mikroşerit tipik efektif dielektrik sabiti (~3.2) için hız (mm/ns).
FR4_MIKROSERIT_HIZ_MM_NS = 167.6


def skew_mm_den_ps_e_cevir(skew_mm: float, hiz_mm_ns: float = FR4_MIKROSERIT_HIZ_MM_NS) -> float:
    """skew_ps = skew_mm / v * 1000  (v: mm/ns)."""
    return skew_mm / hiz_mm_ns * 1000


def meander_gerekli_mi(skew_mm: float, butce_ps: float, hiz_mm_ns: float = FR4_MIKROSERIT_HIZ_MM_NS) -> bool:
    """
    ÖNCE ps'e çevir, SONRA karar ver. Fark bütçenin altındaysa meander EKLEME
    — meander çifti ayırır, kuplajı/empedansı bozar, ekstra köşe getirir.
    """
    return skew_mm_den_ps_e_cevir(skew_mm, hiz_mm_ns) >= butce_ps


def meander_ekleme_mesafesi_hesapla_mm(
    skew_mm: float,
    butce_ps: float,
    hiz_mm_ns: float = FR4_MIKROSERIT_HIZ_MM_NS,
) -> float:
    """
    Meander gerekiyorsa, budget'ı tam karşılayacak EK gecikmeyi mm cinsinden
    döndürür (fazla telafi etme — sadece bütçeyi karşılayacak kadar).
    """
    if not meander_gerekli_mi(skew_mm, butce_ps, hiz_mm_ns):
        return 0.0
    mevcut_ps = skew_mm_den_ps_e_cevir(skew_mm, hiz_mm_ns)
    eksik_ps = mevcut_ps - butce_ps
    return round(eksik_ps / 1000 * hiz_mm_ns, 4)


# ------------------------------------------------------------------
# 5. KOPLANAR GND DOLGUSU CLEARANCE
# ------------------------------------------------------------------

def gnd_dolgu_min_clearance_mm(iz_genisligi_mm: float, katsayi: float = 1.25) -> float:
    """
    Koplanar GND dolgusu çifte çok yaklaşırsa her iz düzleme kuple olur
    (diferansiyel empedans/gürültü bağışıklığı düşer). Kural: dolgu
    clearance'ı >= ~1.25 * iz genişliği (dikişli via'lara bağlantı verecek
    kadar yakın ama çifti bozmayacak kadar uzak).
    """
    return round(iz_genisligi_mm * katsayi, 4)


# ------------------------------------------------------------------
# 6. TOPLU KABUL KRİTERİ RAPORU
# ------------------------------------------------------------------

@dataclass
class EscapeDegerlendirmesi:
    net_adi: str
    kanal: Optional[PinArasiKanal] = None
    iz_genisligi_mm: Optional[float] = None
    acilim: Optional[DiferansiyelPadAcilimi] = None
    rota_segmentleri: Optional[List[RotaSegmenti]] = None
    skew_mm: Optional[float] = None
    butce_ps: Optional[float] = None


def escape_raporu_olustur(deger: EscapeDegerlendirmesi) -> List[str]:
    """Bir net için tüm escape kabul kriterlerini tek seferde değerlendirir."""
    bulgular: List[str] = []

    if deger.kanal is not None and deger.iz_genisligi_mm is not None:
        bulgular.extend(maske_baraji_kontrolu(deger.kanal, deger.iz_genisligi_mm))

    if deger.acilim is not None:
        mesafe = acilma_mesafesi_hesapla_mm(deger.acilim)
        if mesafe is not None:
            bulgular.append(
                f"BİLGİ [{deger.net_adi}]: çift, pad sütununa girmeden ~{mesafe}mm "
                "önce 45° ile açılmalı (ara pin pad boyu >= çift adımı)."
            )

    if deger.rota_segmentleri:
        kotu = dik_acili_koseleri_bul(deger.rota_segmentleri)
        if kotu:
            bulgular.append(
                f"KRİTİK [{deger.net_adi}]: {len(kotu)} adet 85-95° köşe bulundu "
                f"(segment index: {kotu}) — 45°/yay ile değiştir."
            )

    if deger.skew_mm is not None and deger.butce_ps is not None:
        ps = skew_mm_den_ps_e_cevir(deger.skew_mm)
        if meander_gerekli_mi(deger.skew_mm, deger.butce_ps):
            ek = meander_ekleme_mesafesi_hesapla_mm(deger.skew_mm, deger.butce_ps)
            bulgular.append(
                f"UYARI [{deger.net_adi}]: skew {ps:.1f}ps, bütçe {deger.butce_ps}ps "
                f"üzerinde — ~{ek}mm meander ekle (kritik olmayan bölümde, 45°)."
            )
        else:
            bulgular.append(
                f"OK [{deger.net_adi}]: skew {ps:.1f}ps, bütçe {deger.butce_ps}ps "
                "altında — meander EKLEME (gereksiz kuplaj/empedans bozulması)."
            )

    return bulgular
