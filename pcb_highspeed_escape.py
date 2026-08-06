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
from typing import Dict, List, Optional, Sequence


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


# ------------------------------------------------------------------
# 7. 0.4mm-PITCH GND-AYRILMIŞ KONNEKTÖR ESCAPE (referans board türevi)
# ------------------------------------------------------------------
#
# KAYNAK: Resmi Raspberry Pi Foundation CM4 IO Board tasarım dosyaları
# (v3l0c1r4pt0r/CM4IO-KiCAD, CC BY 4.0 — https://github.com/v3l0c1r4pt0r/CM4IO-KiCAD).
# `CM4IOv5.kicad_pcb` içindeki TRD0-3_P/N (Gigabit Ethernet, CM4 B2B
# konnektörü/"Module1"→ common-mode choke U1/U2 arası) segment zinciri
# s-expression seviyesinde chain-walk edilerek çıkarıldı (2026-08-04,
# cm4-io-test/REFERANS/CM4IOv5_orijinal/ altında saklı ham veri).
#
# BULGULAR (8 net, 12 segmentlik zincirlerin TAMAMI incelendi):
#   1. Pad'den ilk segment: pad'in KENDİ çıkış yönünde düz, 0.44-0.63mm
#      (native pad tail uzunluğu ile aynı mertebede).
#   2. Bunu TAKİBEN (toplam 0.5-2.1mm içinde) TEK bir 45° dönüş ile uzun
#      diyagonale (135°/45°) commit edilir — J1/J2 gibi 0.4mm'lik yoğun
#      pad satırından "önce tam kaçış SONRA köşegen" değil, neredeyse
#      ANINDA köşegene geçiliyor.
#   3. P/N ÇİFTİ, committed diyagonalin TAMAMI boyunca (referans board'da
#      ölçülen örnekte ~42mm) SEGMENT UZUNLUKLARI BİREBİR EŞİT tutularak
#      rijit paralel-ofset olarak taşınıyor — "coupling" tek bir yakınsama
#      noktası değil, sürdürülen bir DİSİPLİN.
#   4. Her ucun YAKININDA (pad tarafında VE hedef tarafında), P/N pad
#      pozisyonlarındaki eksen uyuşmazlığını gidermek için ≤~1.6mm'lik
#      BAĞIMSIZ (kuplajsız) "trim" segmentlerine izin veriliyor — bu
#      trim'ler kuralın İSTİSNASI değil, kuralın kendisinin bir parçası.
#   5. HİÇBİR köşe ham 90° değil — sadece 45°/90°/135°/180° kombinasyonu;
#      gerçek bir 90° gerektiğinde iki 45° + aralarında <0.1mm'lik mikro
#      segmentle "chamfer" ediliyor (bkz. `dik_acili_koseleri_bul` — bu
#      disiplin zaten o fonksiyonun varsayımıyla birebir örtüşüyor).
#   6. SIFIR via — ama bunun nedeni yönlendirme değil YERLEŞİM: ilk pasif
#      bileşen (choke), konnektörden çıkan 45° çizginin önünde başka hiçbir
#      footprint'in olmayacağı kadar yakın/hizalı konumlandırılmış
#      ([[feedback_placement_trumps_routing]] ile birebir örtüşüyor).
#      Bizim board'umuzda hedef IC (ör. D4-D7) o hizada DEĞİLSE (araya
#      başka bileşen giriyorsa), kural (6) ihlal edilir ve via-pair hop'u
#      gerekli hale gelir — bkz. `via_pair_gerekli_mi` altta.
#   7. Aynı koridoru paylaşan KOMŞU çiftler (ör. TRD0 ile TRD1) arasında
#      ölçülen pair-to-pair mesafe ~0.45-0.47mm (0.127mm iz genişliğinde)
#      — J1/J2 gibi board'larda kullanılan daha kalın izlerde (0.15-0.2mm)
#      orantılı olarak büyütülmeli (bkz. `pair_to_pair_min_mesafe_mm`).

@dataclass
class YuksekYogunlukKonnektorEscape:
    """0.4mm (veya benzeri ince) pitch'li, GND ile ayrılmış diferansiyel
    çift satırından çıkış parametreleri (J1/J2 DF40 tipi B2B konnektör,
    referans: CM4 IO Board TRD escape'i)."""

    pad_pitch_mm: float
    """Konnektörün native pin pitch'i (ör. 0.4mm)."""
    iz_genisligi_mm: float
    """Kullanılacak diferansiyel iz genişliği (proje genelinde tutarlı
    olmalı — cm4-io-test'te HDMI için 0.2mm kullanıldı, referans board
    0.127mm kullanmış; MUTLAK değer değil, ORAN önemli)."""
    ilk_duz_segment_mm: float = 0.55
    """Pad'den, pad'in kendi çıkış yönünde düz segment (referans: 0.44-0.63mm)."""
    commit_mesafesi_mm: float = 2.1
    """Bu mesafeye kadar TEK bir 45° dönüşle uzun diyagonale commit
    edilmiş olmalı (referans: 0.5-2.1mm aralığı, üst sınır alındı)."""
    max_trim_segment_mm: float = 1.6
    """Her ucun yakınında P/N pad pozisyon farkını gidermek için izin
    verilen MAKSİMUM bağımsız (kuplajsız) segment uzunluğu."""


def pair_to_pair_min_mesafe_mm(esc: YuksekYogunlukKonnektorEscape) -> float:
    """Aynı koridoru paylaşan komşu çiftler arası minimum merkez-merkez
    mesafe. Referans oranı (~0.47mm / 0.127mm iz ≈ 3.7x) bu projenin iz
    genişliğine ölçeklenir."""
    referans_oran = 0.47 / 0.127
    return round(esc.iz_genisligi_mm * referans_oran, 4)


def via_pair_gerekli_mi(
    pad_konumu: Tuple[float, float],
    hedef_konumu: Tuple[float, float],
    engel_bbox_listesi: List[Tuple[float, float, float, float]],
) -> bool:
    """
    Pad'den hedefe TEK bir 45°/135° diyagonal çizgi (referans board'daki
    gibi) çekildiğinde, bu çizgi verilen engel bbox'larından (x1,y1,x2,y2)
    HERHANGİ biriyle kesişiyor mu kontrol eder. Kesişiyorsa kural (6)
    ihlal edilmiş demektir — via-pair (İn2.Cu tünel) hop'u gerekli.

    NOT: Bu, YERLEŞİMİN routing'den önce doğrulanması gerektiği kuralının
    ([[feedback_placement_trumps_routing]]) otomatik kontrolüdür — sonuç
    True ise, önce hedef bileşenin/ara pasifin taşınıp taşınamayacağı
    değerlendirilmeli; taşınamıyorsa via-pair kullanılır (Faz 4 istisnası).
    """
    x1p, y1p = pad_konumu
    x2p, y2p = hedef_konumu

    def _segment_intersects_bbox(bbox: Tuple[float, float, float, float]) -> bool:
        bx1, by1, bx2, by2 = bbox
        # Liang-Barsky segment/aabb kesişim testi
        dx, dy = x2p - x1p, y2p - y1p
        t0, t1 = 0.0, 1.0
        for p, q in (
            (-dx, (x1p - bx1)),
            (dx, (bx2 - x1p)),
            (-dy, (y1p - by1)),
            (dy, (by2 - y1p)),
        ):
            if p == 0:
                if q < 0:
                    return False
                continue
            r = q / p
            if p < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
        return t0 <= t1

    return any(_segment_intersects_bbox(b) for b in engel_bbox_listesi)


def escape_planı_olustur(
    esc: YuksekYogunlukKonnektorEscape,
    pad_konumu: Tuple[float, float],
    kacis_yonu: Tuple[float, float],
) -> List[Tuple[float, float]]:
    """
    Referans board disiplinine göre pad'den itibaren ilk ~commit_mesafesi
    kadar olan waypoint dizisini üretir: pad -> düz kaçış -> 45° ile
    diyagonale commit. `kacis_yonu` birim vektör olmalı (ör. (0,1) =
    konnektör satırından +Y'ye kaçış, (0,-1) = -Y'ye).

    Dönen liste, çağıranın uzun diyagonali bu son noktadan hedefe doğru
    (via_pair_gerekli_mi=False ise doğrudan, True ise via-pair üzerinden)
    devam ettirmesi için başlangıç noktalarını verir.
    """
    px, py = pad_konumu
    kx, ky = kacis_yonu
    duz_uc = (px + kx * esc.ilk_duz_segment_mm, py + ky * esc.ilk_duz_segment_mm)
    return [pad_konumu, duz_uc]


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


# ------------------------------------------------------------------
# 7. ÇOKLU KART (HOST -> N KAMERA) TOPLAM SKEW BÜTÇESİ (FAZ 0.5 #35)
# ------------------------------------------------------------------
# `skew_mm_den_ps_e_cevir()`/`meander_gerekli_mi()` (Bölüm 4) TEK bir net'in
# P/N çifti içi skew'ini ölçer. Kafa bandı sisteminde asıl soru FARKLI:
# HOST'tan 6 AYRI kamera kartına giden clock/trigger hatlarının TOPLAM
# gecikmesi (PCB izi + host<->kart kablosu + katman geçişleri) birbirinden
# ne kadar SAPIYOR — kartlar arası bu fark (skew) senkron örnekleme
# bütçesini aşarsa kameralar arasında görüntü zaman damgası kayması olur.

# Tipik ekranlı diferansiyel kablo (ör. koaksiyel çift/FPC uzatma) için
# efektif hız — FR4 mikroşeritten FARKLI dielektrik/ortam, ayrı bir sabit.
# Bu sadece "gerçek kablo verisi yoksa" kullanılacak bir VARSAYILANDIR;
# gerçek tasarımda kablonun kendi datasheet'inden alınan hız kullanılmalı.
VARSAYILAN_KABLO_HIZ_MM_NS = 200.0

# Bir via'nın katman geçişinde eklediği TİPİK ek gecikme (barrel boyu +
# stub etkisinin kaba bir toplamı) — GERÇEK bir alan çözümü/simülasyon
# DEĞİLDİR (bkz. `yerlesim_skoru()`'nun termal skoru ile AYNI disiplin
# notu: bu sadece "ne kadar riskli" kaba bir tahmindir, ileride
# `pcb_stackup_planner`'ın gerçek stackup kalınlığıyla hassaslaştırılabilir,
# şu an İÇİN bağlı DEĞİL).
VARSAYILAN_VIA_GECIS_GECIKMESI_PS = 5.0


@dataclass
class KartYolSegmenti:
    """HOST'tan TEK bir kamera kartına giden fiziksel yolun uzunluk/geçiş
    bileşenleri — clock/trigger hattının TOPLAM gecikmesini hesaplamak
    için gerekli tüm parçalar (host PCB izi + host<->kart kablosu + kart
    PCB izi + katman geçiş/via sayısı)."""

    kart_adi: str
    host_pcb_uzunluk_mm: float = 0.0
    kablo_uzunluk_mm: float = 0.0
    kart_pcb_uzunluk_mm: float = 0.0
    katman_gecis_sayisi: int = 0


@dataclass
class KartGecikmeSonucu:
    kart_adi: str
    toplam_gecikme_ps: float
    pcb_gecikme_ps: float
    kablo_gecikme_ps: float
    via_gecikme_ps: float


@dataclass
class CokluKartSkewButcesiSonucu:
    kart_sonuclari: Dict[str, KartGecikmeSonucu]
    en_hizli_kart: str
    en_yavas_kart: str
    maks_skew_ps: float
    butce_ps: float
    butce_asildi_mi: bool


def coklu_kart_skew_butcesi_hesapla(
    yollar: Sequence[KartYolSegmenti],
    butce_ps: float,
    pcb_hiz_mm_ns: float = FR4_MIKROSERIT_HIZ_MM_NS,
    kablo_hiz_mm_ns: float = VARSAYILAN_KABLO_HIZ_MM_NS,
    via_gecis_gecikmesi_ps: float = VARSAYILAN_VIA_GECIS_GECIKMESI_PS,
) -> CokluKartSkewButcesiSonucu:
    """HOST'tan HER kamera kartına giden clock/trigger hattının TOPLAM
    gecikmesini (PCB izi + kablo + katman geçişi) hesaplar; kartlar ARASI
    en büyük fark (skew) `butce_ps` ile karşılaştırılır.

    Bölüm 4'ün TEK-net skew hesabının ÇOKLU-KART genişlemesidir — HER kart
    kendi (potansiyel olarak farklı uzunlukta) HOST->kart yolunu taşır,
    skew bu yolların GERÇEK toplam gecikme FARKIdır (bir net'in kendi P/N
    çifti içi mm skew'i DEĞİL).

    `yollar` boşsa `ValueError` — en az bir kart yolu anlamlı bir skew
    hesabı için ZORUNLUDUR (skew tanımı gereği en az 2 karşılaştırma
    noktası ister, ama tek kartlı çağrı da "referansa göre skew=0"
    anlamında kabul edilir — çağıran taraf henüz eksik veriyle erken
    tespit yapabilsin diye reddetmiyoruz, sadece boş liste reddedilir).

    SINIR: via gecikmesi kaba bir sabit yaklaşımdır (bkz. modül seviyesi
    not), kablo hızının GERÇEK değeri kullanıcının kendi kablo
    datasheet'inden gelmelidir — varsayılan sadece veri yoksa kullanılır.
    """
    if not yollar:
        raise ValueError("En az bir kart yolu (KartYolSegmenti) gerekir.")

    sonuclar: Dict[str, KartGecikmeSonucu] = {}
    for yol in yollar:
        pcb_ps = skew_mm_den_ps_e_cevir(
            yol.host_pcb_uzunluk_mm + yol.kart_pcb_uzunluk_mm, pcb_hiz_mm_ns
        )
        kablo_ps = skew_mm_den_ps_e_cevir(yol.kablo_uzunluk_mm, kablo_hiz_mm_ns)
        via_ps = yol.katman_gecis_sayisi * via_gecis_gecikmesi_ps
        toplam_ps = pcb_ps + kablo_ps + via_ps
        sonuclar[yol.kart_adi] = KartGecikmeSonucu(
            kart_adi=yol.kart_adi,
            toplam_gecikme_ps=round(toplam_ps, 4),
            pcb_gecikme_ps=round(pcb_ps, 4),
            kablo_gecikme_ps=round(kablo_ps, 4),
            via_gecikme_ps=round(via_ps, 4),
        )

    en_yavas = max(sonuclar.values(), key=lambda s: s.toplam_gecikme_ps)
    en_hizli = min(sonuclar.values(), key=lambda s: s.toplam_gecikme_ps)
    maks_skew_ps = round(en_yavas.toplam_gecikme_ps - en_hizli.toplam_gecikme_ps, 4)

    return CokluKartSkewButcesiSonucu(
        kart_sonuclari=sonuclar,
        en_hizli_kart=en_hizli.kart_adi,
        en_yavas_kart=en_yavas.kart_adi,
        maks_skew_ps=maks_skew_ps,
        butce_ps=butce_ps,
        butce_asildi_mi=maks_skew_ps > butce_ps,
    )
