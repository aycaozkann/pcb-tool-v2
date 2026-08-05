#!/usr/bin/env python3
"""
otonom_python_router.py
=========================
SON ÇARE (last-resort) SAF PYTHON A* ROUTER — `pcbnew`'in KENDİ
`route_trace`/interaktif router çekirdeğini KULLANMAZ. `topolojik_router_
koprusu.py::akilli_yol_bul()`'un DOGRUDAN/L_DONUSU/U_DONUSU/KATMAN_DEGISIMI
merdiveni de tükenirse (karmaşık/çok engelli bir koridorda dört basamağın
hiçbiri temiz bir yol bulamazsa) devreye giren, IZGARA tabanlı bir A*
arama motorudur.

NEDEN AYRI BİR MODÜL (`akilli_yol_bul()`'un YERİNE değil, ARDINDA):
--------------------------------------------------------------------------
`akilli_yol_bul()` HEURİSTİK bir merdivendir — az sayıda "aday yol" dener
(düz, 2 L, birkaç U). Bu HIZLIDIR ve çoğu durumda yeterlidir, ama gerçekten
labirent gibi bir bölgede (çok sayıda örtüşen engel) hiçbir aday temiz
çıkmayabilir — bu, o merdivenin TASARIM SINIRIDIR, hata değildir. Bu modül
KAPSAMLI bir arama sunar: engelleri bir IZGARAYA (grid) işleyip, başlangıç-
bitiş arası TÜM olası 8-yönlü yolları A* ile tarar. Daha YAVAŞ ama daha
İNATÇIDIR — `MASTER_RULEBOOK`'un "Otonom Yol Bulma" merdiveninin DÖRDÜNCÜ
basamağından SONRAKİ, BEŞİNCİ ve SON otomatik basamak olarak konumlanır
(`otonom_kurtarma_motoru.py::otonom_routing_merdiveni()` bu sırayı uygular).

Bu, projenin "asla kullanıcıdan çizim bekleme, önce kendi kurtarma
motorlarına geç" ilkesinin (bkz. `CLAUDE.md` "Tam Otonom Kurtarma
Mekanizması") somut karşılığıdır — `NEEDS_HUMAN` artık SADECE bu modül de
dahil TÜM otomatik basamaklar gerçekten tükendiğinde raporlanır.

MİMARİ TERCİH — arama SAF Python, YAZMA katmanı `pcbnew` (izole):
--------------------------------------------------------------------------
`izgara_a_yildiz_ara()` hiçbir `pcbnew` importu YAPMAZ — düz `(x, y)`
tuple'ları ve `pcb_carpisma_radari.SinirKutusu` (veya uyumlu herhangi bir
nesne: `x_min/y_min/x_max/y_max` özellikleri) üzerinde çalışır, bu yüzden
bu ortamda (gerçek `pcbnew` OLMADAN) tam kapsamlı test edilebilir. SADECE
`duz_izleri_pcbnew_ile_yaz()` gerçek board'a dokunur — kullanıcının AÇIKÇA
istediği gibi, KiCad'in `route_trace`/PNS çekirdeğini DEĞİL, sadece düz
`pcbnew.PCB_TRACK` segmentleri ekler (`topolojik_router_koprusu.py::
TopolojikRouter.iz_yaz()` ile AYNI, kanıtlanmış yazma deseni — kasıtlı
olarak kopyalanmadı, o fonksiyon ÇAĞRILIR, bkz. altta).

SINIR (dürüstlük notu): 8-yönlü ızgara A*, gerçek sürekli geometriyi
`hucre_mm` çözünürlüğüne YUVARLAR — çok ince (<hucre_mm) bir koridor
ıskalanabilir. Bu yüzden `hucre_mm` iz genişliği + clearance'ın YARISINDAN
KÜÇÜK seçilmelidir (varsayılan 0.1mm, tipik 0.2-0.25mm iz için güvenli);
çağıran taraf daha yoğun bir bölgede bunu küçültebilir (arama süresi
karesel artar — `maks_dugum` bu yüzden ZORUNLU bir üst sınırdır, sessizce
sonsuz aramaya izin verilmez).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

# Sadece geometri fonksiyonu - pcb_carpisma_radari modülü de `import pcbnew`
# YAPMAZ (kendi lazy-import kuralına uyar), bu yüzden bu modülün başlıktaki
# "pcbnew GEREKMEZ" iddiası bozulmuyor. Narrow-phase çarpışma testi (bkz.
# `_hucre_engelli_mi`) için kullanılır.
from pcb_carpisma_radari import IzEngeli, nokta_segmente_dik_mesafe

Nokta = Tuple[float, float]
IzgaraHucresi = Tuple[int, int]
IzgaraDugum3D = Tuple[int, int, int]  # (hücre_x, hücre_y, katman_indeksi)


class KutuBenzeri(Protocol):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class AramaSonucu:
    yol: List[Nokta]
    dugum_sayisi: int
    bulundu_mu: bool
    neden: str = ""


# ------------------------------------------------------------------
# 1. IZGARA + ENGEL HARİTALAMA (pcbnew'e bağımlı DEĞİL)
# ------------------------------------------------------------------

def _hucreye_cevir(nokta: Nokta, hucre_mm: float) -> IzgaraHucresi:
    return (round(nokta[0] / hucre_mm), round(nokta[1] / hucre_mm))


def _noktaya_cevir(hucre: IzgaraHucresi, hucre_mm: float) -> Nokta:
    return (hucre[0] * hucre_mm, hucre[1] * hucre_mm)


def _hucre_engelli_mi(
    hucre: IzgaraHucresi, engeller: Sequence[KutuBenzeri], hucre_mm: float, clearance_mm: float,
) -> bool:
    """İKİ AŞAMALI çarpışma testi (2026-08-05, cm4-io-test bulgusu):

    1. Broad phase (mevcut davranış, AYNEN korunur): nokta engelin AABB'si
       dışındaysa hemen sıradaki engele geç - ucuz, hızlı ön filtre.
    2. Narrow phase: nokta AABB İÇİNDEYSE VE engel bir `IzEngeli` (segment)
       ise (`pcb_carpisma_radari.IzEngeli` - `x1/y1/x2/y2/genislik_mm`
       alanlarının VARLIĞIYLA `hasattr` ile tespit edilir, yeni bir tip
       importu/izinstance kontrolü GEREKMEZ), noktanın segmente GERÇEK
       dik mesafesi ölçülür. Bu mesafe (iz_genişliği/2 + clearance)'tan
       büyükse nokta GÜVENLİDİR - 45° köşegen izlerin AABB'sinin köşelere
       yakın boş üçgen alanlarını yanlışlıkla "dolu" saymanın önüne geçer
       (bkz. `pcb_carpisma_radari.py` İZ ENGELİ bölümünün başlık notu).
       `SinirKutusu` (komponent) engelleri bu alanlara SAHİP DEĞİLDİR,
       dolayısıyla narrow-phase'e hiç girmez - katı cisim olarak kalır,
       ESKİ davranış (saf AABB) bu tip engeller için BİREBİR korunur.
    """
    x, y = _noktaya_cevir(hucre, hucre_mm)
    for e in engeller:
        if not ((e.x_min - clearance_mm) <= x <= (e.x_max + clearance_mm) and
                (e.y_min - clearance_mm) <= y <= (e.y_max + clearance_mm)):
            continue  # broad phase: AABB dışında -> bu engel temiz
        if hasattr(e, "x1") and hasattr(e, "genislik_mm"):
            mesafe = nokta_segmente_dik_mesafe(x, y, e.x1, e.y1, e.x2, e.y2)
            sinir = e.genislik_mm / 2.0 + clearance_mm
            if mesafe > sinir:
                continue  # narrow phase: AABB içindeydi ama gerçek çizgiden yeterince uzak
        return True
    return False


# 8 yön: 4 eksen (maliyet 1) + 4 çapraz (maliyet √2) — Faz 7'nin 45°
# tercihiyle UYUMLU, ızgara ayrıklığında dik açı sayısını baştan azaltır.
_YONLER: Tuple[Tuple[int, int, float], ...] = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)),
    (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2)),
)


def _sezgisel(a: IzgaraHucresi, b: IzgaraHucresi) -> float:
    """Octile mesafe — 8 yönlü ızgarada A*'ın KABUL EDİLEBİLİR (asla
    gerçek maliyeti aşmayan) sezgi fonksiyonu; Manhattan burada YANLIŞ
    olurdu (çapraz hareketi hesaba katmaz, optimal olmayan yol seçtirebilir)."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)


# ------------------------------------------------------------------
# 2. A* ARAMA (saf Python, pcbnew GEREKMEZ)
# ------------------------------------------------------------------

def izgara_a_yildiz_ara(
    baslangic: Nokta,
    bitis: Nokta,
    engeller: Sequence[KutuBenzeri] = (),
    hucre_mm: float = 0.1,
    clearance_mm: float = 0.2,
    maks_dugum: int = 200_000,
    ek_maliyet_fonksiyonu: Optional[Callable[[Nokta, Nokta], float]] = None,
) -> AramaSonucu:
    """Başlangıç-bitiş arası 8-yönlü A* ile IZGARA üzerinde en kısa yolu
    arar. Engeller `SinirKutusu`-uyumlu (x_min/y_min/x_max/y_max) herhangi
    bir nesne olabilir — `pcb_carpisma_radari.SinirKutusu` bu arayüzü
    zaten karşılar, ayrı bir dönüşüm GEREKMEZ.

    `maks_dugum` aşılırsa arama DURDURULUR ve `bulundu_mu=False` +
    açıklayıcı `neden` döner — sessizce sonsuza kadar aramaya devam
    edilmez (bkz. dosya başlığı SINIR notu).

    `ek_maliyet_fonksiyonu` (FAZ 0.5-2 — canlı SI/PI maliyeti): verilirse
    HER aday adımın (a_mm, b_mm) segmenti için çağrılır, dönen değer o
    adımın maliyetine EKLENİR (temel 1.0/√2 hareket maliyetinin üstüne).
    Bu, "routing-SONRASI kontrol" yerine "routing-SIRASI karar" sağlar —
    A* artık sadece geometrik en-kısa yolu değil, `si_pi_maliyet_
    fonksiyonu_uret()` gibi bir fonksiyonla cezalandırılan bir yolu arar
    (bkz. o fonksiyonun docstring'i). A*'ın OPTİMALLİĞİ bozulmaz: sezgi
    (`_sezgisel`) bu ek maliyeti hesaba KATMAZ (her zaman `<=` gerçek
    maliyet kalır, kabul edilebilirlik korunur) — sadece potansiyel
    olarak daha fazla düğüm gezilir, YANLIŞ bir yol asla BULUNMAZ.
    """
    bas_h = _hucreye_cevir(baslangic, hucre_mm)
    bit_h = _hucreye_cevir(bitis, hucre_mm)

    if _hucre_engelli_mi(bas_h, engeller, hucre_mm, clearance_mm):
        return AramaSonucu([], 0, False, "başlangıç noktası engelli bölgede")
    if _hucre_engelli_mi(bit_h, engeller, hucre_mm, clearance_mm):
        return AramaSonucu([], 0, False, "bitiş noktası engelli bölgede")
    if bas_h == bit_h:
        return AramaSonucu([baslangic, bitis], 0, True)

    acik: List[Tuple[float, float, IzgaraHucresi]] = [(_sezgisel(bas_h, bit_h), 0.0, bas_h)]
    geldigi: dict = {bas_h: None}
    g_skoru: dict = {bas_h: 0.0}
    ziyaret_edildi: set = set()

    while acik:
        if len(ziyaret_edildi) > maks_dugum:
            return AramaSonucu([], len(ziyaret_edildi), False, f"düğüm bütçesi ({maks_dugum}) aşıldı")

        _, mevcut_g, mevcut = heapq.heappop(acik)
        if mevcut in ziyaret_edildi:
            continue
        ziyaret_edildi.add(mevcut)

        if mevcut == bit_h:
            yol_h: List[IzgaraHucresi] = []
            n: Optional[IzgaraHucresi] = mevcut
            while n is not None:
                yol_h.append(n)
                n = geldigi[n]
            yol_h.reverse()
            yol_mm = [_noktaya_cevir(h, hucre_mm) for h in yol_h]
            yol_mm[0] = baslangic
            yol_mm[-1] = bitis
            return AramaSonucu(_yolu_sadelestir(yol_mm), len(ziyaret_edildi), True)

        for dx, dy, maliyet in _YONLER:
            komsu = (mevcut[0] + dx, mevcut[1] + dy)
            if komsu in ziyaret_edildi:
                continue
            if _hucre_engelli_mi(komsu, engeller, hucre_mm, clearance_mm):
                continue
            adim_maliyeti = maliyet
            if ek_maliyet_fonksiyonu is not None:
                adim_maliyeti += ek_maliyet_fonksiyonu(
                    _noktaya_cevir(mevcut, hucre_mm), _noktaya_cevir(komsu, hucre_mm),
                )
            aday_g = mevcut_g + adim_maliyeti
            if aday_g < g_skoru.get(komsu, float("inf")):
                g_skoru[komsu] = aday_g
                geldigi[komsu] = mevcut
                f = aday_g + _sezgisel(komsu, bit_h)
                heapq.heappush(acik, (f, aday_g, komsu))

    return AramaSonucu([], len(ziyaret_edildi), False, "engelsiz yol bulunamadı (arama tükendi)")


def _yolu_sadelestir(yol: List[Nokta]) -> List[Nokta]:
    """Ardışık KOLİNEER noktaları birleştirir — ızgara A*'ının ürettiği
    çok-segmentli "merdiven" yolunu, gerçek iz sayısını azaltacak şekilde
    düz çizgilere indirger (fazladan via/köşe YOK, sadece nokta sadeleşmesi)."""
    if len(yol) < 3:
        return yol
    sonuc = [yol[0]]
    for i in range(1, len(yol) - 1):
        a, b, c = sonuc[-1], yol[i], yol[i + 1]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        capraz = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(capraz) < 1e-9:
            continue  # kolineer — b'yi atla
        sonuc.append(b)
    sonuc.append(yol[-1])
    return sonuc


# ------------------------------------------------------------------
# 2b. DİFERANSİYEL ÇİFT (COUPLED) ROUTING
#     (FAZ 0, cm4-io-test'in J1 diferansiyel çift ihtiyacından doğdu)
# ------------------------------------------------------------------
#
# NEDEN AYRI İKİ A* DEĞİL: P ve N net'lerini BAĞIMSIZ iki
# `izgara_a_yildiz_ara()` çağrısıyla rotalamak aralarındaki gap'i SABİT
# TUTAMAZ — iki arama farklı yollar seçebilir (farklı engel etrafından
# dolanabilir), bu da noktasal olarak gap'in daralıp genişlemesine (empedans
# süreksizliği, EMI) yol açar. Bu fonksiyon TEK bir A* aramasını P/N
# ÇİFTİNİN MERKEZ HATTI üzerinde yapar, sonra HER segment boyunca dik
# ofsetle iki paralel yol türetir — gap MATEMATİKSEL OLARAK sabit kalır.
#
# STUB STRATEJİSİ: dar pitch'li bir konnektörde (ör. 0.4mm) P/N pad'leri
# arasındaki mesafe, coupled koridorun ihtiyaç duyduğu (genislik_mm*2 +
# gap_mm) mesafeden küçük olabilir. Çözüm: önce her net KISA BAĞIMSIZ bir
# stub ile (pad'den diğer nete UZAKLAŞAN yönde, `stub_uzunluk_mm`) açılır,
# stub'ların bittiği noktaların ORTA NOKTASI merkez-hat aramasının
# başlangıcı/bitişi olur.

def _perpendikuler_birim_vektor(a: Nokta, b: Nokta) -> Tuple[float, float]:
    """`a->b` segmentine DİK birim vektör (90° saat yönünün tersi)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    uzunluk = math.hypot(dx, dy)
    if uzunluk < 1e-9:
        return (0.0, 0.0)
    return (-dy / uzunluk, dx / uzunluk)


def _merkez_hattan_cift_uret(merkez_yol: List[Nokta], yaricap_mm: float) -> Tuple[List[Nokta], List[Nokta]]:
    """Bir merkez-hat polyline'ından, HER segmentin kendi yönüne dik
    ofsetle iki paralel yol (P: +yaricap, N: -yaricap) üretir.

    SINIR (dürüstlük notu): köşelerde (segment yönü değiştiğinde) komşu
    iki segmentin ofset yönleri ORTALAMASI alınır (basit bir miter/bevel
    karışımı) — gerçek bir miter-join hesabı DEĞİLDİR, keskin köşelerde
    P/N yolları arasında `yaricap_mm` mertebesinde küçük bir geometrik
    hata OLUŞABİLİR. Bu, coupled routing'in kabul edilen bir sınırıdır;
    kritik keskin-köşe senaryolarında elle gözden geçirilmeli."""
    if len(merkez_yol) < 2:
        return list(merkez_yol), list(merkez_yol)

    p_yol: List[Nokta] = []
    n_yol: List[Nokta] = []
    for i, nokta in enumerate(merkez_yol):
        if i == 0:
            nx, ny = _perpendikuler_birim_vektor(merkez_yol[0], merkez_yol[1])
        elif i == len(merkez_yol) - 1:
            nx, ny = _perpendikuler_birim_vektor(merkez_yol[-2], merkez_yol[-1])
        else:
            n1x, n1y = _perpendikuler_birim_vektor(merkez_yol[i - 1], nokta)
            n2x, n2y = _perpendikuler_birim_vektor(nokta, merkez_yol[i + 1])
            nx, ny = (n1x + n2x) / 2.0, (n1y + n2y) / 2.0
            norm = math.hypot(nx, ny)
            if norm > 1e-9:
                nx, ny = nx / norm, ny / norm
        p_yol.append((nokta[0] + nx * yaricap_mm, nokta[1] + ny * yaricap_mm))
        n_yol.append((nokta[0] - nx * yaricap_mm, nokta[1] - ny * yaricap_mm))
    return p_yol, n_yol


@dataclass
class CoupledAramaSonucu:
    p_yolu: List[Nokta]
    n_yolu: List[Nokta]
    merkez_hat_sonucu: AramaSonucu
    bulundu_mu: bool
    neden: str = ""


def izgara_a_yildiz_ara_coupled(
    p_baslangic: Nokta,
    n_baslangic: Nokta,
    p_bitis: Nokta,
    n_bitis: Nokta,
    genislik_mm: float,
    gap_mm: float,
    engeller: Sequence[KutuBenzeri] = (),
    hucre_mm: float = 0.1,
    clearance_mm: float = 0.2,
    maks_dugum: int = 200_000,
    stub_uzunluk_mm: float = 0.5,
    ek_maliyet_fonksiyonu: Optional[Callable[[Nokta, Nokta], float]] = None,
) -> CoupledAramaSonucu:
    """P/N net çiftini SABİT `gap_mm` ile TEK bir arama olarak rotalar
    (bkz. dosya başlığı "DİFERANSİYEL ÇİFT" notu).

    1) Her net kendi pad'inden (`p_baslangic`/`n_baslangic` ve
       `p_bitis`/`n_bitis`) `stub_uzunluk_mm` kadar DİĞER netten
       UZAKLAŞAN yönde düz bir stub ile açılır (dar pad pitch'i coupled
       koridora "yayar"). `stub_uzunluk_mm=0` verilirse stub atlanır —
       çağıran taraf zaten birleşme noktalarını hesaplamışsa bunu
       kullanabilir.
    2) Stub'ların orta noktaları arasında (`merkez_bas`/`merkez_bit`)
       TEK bir `izgara_a_yildiz_ara()` çağrısı yapılır; `engeller` için
       kullanılan `clearance_mm`, TÜM coupled koridoru (P+gap+N) kapsayacak
       şekilde `clearance_mm + gap_mm/2 + genislik_mm` olarak genişletilir
       (muhafazakâr bir yaklaşım — köşelerde koridor genişliği TAM
       korunmayabilir, bkz. `_merkez_hattan_cift_uret` notu).
    3) Bulunan merkez hattan `_merkez_hattan_cift_uret()` ile P/N yolları
       türetilir, orijinal pad noktalarıyla (stub) birleştirilip
       sadeleştirilir.
    """
    if stub_uzunluk_mm < 0:
        raise ValueError("stub_uzunluk_mm negatif olamaz")
    if genislik_mm <= 0 or gap_mm <= 0:
        raise ValueError("genislik_mm ve gap_mm pozitif olmalı")

    def _stub_uygula(baslangic: Nokta, diger_net_noktasi: Nokta, uzunluk: float) -> Nokta:
        if uzunluk <= 1e-9:
            return baslangic
        dx = baslangic[0] - diger_net_noktasi[0]
        dy = baslangic[1] - diger_net_noktasi[1]
        d = math.hypot(dx, dy)
        if d < 1e-9:
            return baslangic
        return (baslangic[0] + dx / d * uzunluk, baslangic[1] + dy / d * uzunluk)

    p_birlesme_bas = _stub_uygula(p_baslangic, n_baslangic, stub_uzunluk_mm)
    n_birlesme_bas = _stub_uygula(n_baslangic, p_baslangic, stub_uzunluk_mm)
    p_birlesme_bit = _stub_uygula(p_bitis, n_bitis, stub_uzunluk_mm)
    n_birlesme_bit = _stub_uygula(n_bitis, p_bitis, stub_uzunluk_mm)

    merkez_bas = ((p_birlesme_bas[0] + n_birlesme_bas[0]) / 2.0, (p_birlesme_bas[1] + n_birlesme_bas[1]) / 2.0)
    merkez_bit = ((p_birlesme_bit[0] + n_birlesme_bit[0]) / 2.0, (p_birlesme_bit[1] + n_birlesme_bit[1]) / 2.0)

    yaricap_mm = gap_mm / 2.0 + genislik_mm / 2.0
    koridor_clearance_mm = clearance_mm + yaricap_mm

    merkez_sonuc = izgara_a_yildiz_ara(
        merkez_bas, merkez_bit, engeller, hucre_mm=hucre_mm,
        clearance_mm=koridor_clearance_mm, maks_dugum=maks_dugum,
        ek_maliyet_fonksiyonu=ek_maliyet_fonksiyonu,
    )
    if not merkez_sonuc.bulundu_mu:
        return CoupledAramaSonucu([], [], merkez_sonuc, False, merkez_sonuc.neden)

    p_yol_ic, n_yol_ic = _merkez_hattan_cift_uret(list(merkez_sonuc.yol), yaricap_mm)
    p_yol = _yolu_sadelestir([p_baslangic] + p_yol_ic + [p_bitis])
    n_yol = _yolu_sadelestir([n_baslangic] + n_yol_ic + [n_bitis])

    return CoupledAramaSonucu(p_yol, n_yol, merkez_sonuc, True)


# ------------------------------------------------------------------
# 2c. VIA YERLEŞİM GEÇERLİLİĞİ (annular-ring + hole-to-hole)
#     (0.5mm via'nın 0.4mm pin pitch'inde 221 DRC ihlaline yol açtığı
#     bir olaydan sonra eklendi — bu kontrol PROJEDE DAHA ÖNCE YOKTU)
# ------------------------------------------------------------------

@dataclass
class ViaYerlesimKontrolu:
    via_capi_mm: float
    delik_capi_mm: float
    min_annular_ring_mm: float = 0.15
    min_hole_to_hole_mm: float = 0.2

    def annular_ring_mm(self) -> float:
        return (self.via_capi_mm - self.delik_capi_mm) / 2.0

    def annular_ring_yeterli_mi(self) -> bool:
        return self.annular_ring_mm() >= self.min_annular_ring_mm


def via_yerlesimi_gecerli_mi(
    aday_nokta: Nokta,
    via_capi_mm: float,
    delik_capi_mm: float,
    komsu_delikler: Sequence[Tuple[float, float, float]] = (),
    min_annular_ring_mm: float = 0.15,
    min_hole_to_hole_mm: float = 0.2,
) -> Tuple[bool, str]:
    """Bir via yerleştirme adayının annular-ring VE hole-to-hole clearance
    açısından geçerli olup olmadığını kontrol eder — döner: `(gecerli_mi,
    sebep)`. `sebep` sadece `gecerli_mi=False` iken doludur.

    `komsu_delikler`, board üzerindeki DİĞER delik/via merkezlerinin
    `(x_mm, y_mm, delik_capi_mm)` listesidir — pad delikleri DAHİL
    edilmelidir (0.5mm via'nın 0.4mm pin pitch'inde 221 ihlale yol açtığı
    olayda tam olarak BU kontrol eksikti: via'nın komşu pad deliklerine
    olan mesafesi hiç ölçülmüyordu). Merkezler-arası mesafe
    `via_yaricap + komsu_yaricap + min_hole_to_hole_mm`'den KÜÇÜKSE ihlal.
    """
    kontrol = ViaYerlesimKontrolu(via_capi_mm, delik_capi_mm, min_annular_ring_mm, min_hole_to_hole_mm)
    if not kontrol.annular_ring_yeterli_mi():
        return False, (
            f"annular ring yetersiz: {kontrol.annular_ring_mm():.4f}mm < "
            f"{min_annular_ring_mm}mm (via_capi={via_capi_mm}mm, delik={delik_capi_mm}mm)"
        )
    for kx, ky, komsu_cap in komsu_delikler:
        mesafe = math.hypot(aday_nokta[0] - kx, aday_nokta[1] - ky)
        gerekli = (via_capi_mm / 2.0) + (komsu_cap / 2.0) + min_hole_to_hole_mm
        if mesafe < gerekli:
            return False, (
                f"hole-to-hole clearance ihlali: ({kx:.3f},{ky:.3f}) konumundaki komşu "
                f"delikten {mesafe:.4f}mm mesafede, gerekli >= {gerekli:.4f}mm "
                f"(via_yaricap={via_capi_mm / 2.0}mm + komsu_yaricap={komsu_cap / 2.0}mm + "
                f"min_hole_to_hole={min_hole_to_hole_mm}mm)"
            )
    return True, ""


# ------------------------------------------------------------------
# 2c-2. CANLI SI/PI MALİYET FONKSİYONLARI (FAZ 0.5-2)
#     routing-SIRASI karar verici — routing-SONRASI kontrol DEĞİL.
#     `empedans_cozucu.py`/`pcb_stackup_planner.py`'nin GERÇEK stackup
#     çözümünü YENİDEN HESAPLAMAZ, sadece GİRDİ olarak alır (tek kaynak
#     stackup çözücüde kalır — bkz. her iki fonksiyonun kendi notu).
# ------------------------------------------------------------------

def si_pi_maliyet_fonksiyonu_uret(
    diger_hs_izler: Sequence[IzEngeli],
    net_genislik_mm: float,
    w_kurali_carpani: float = 3.0,
    ihlal_agirligi: float = 5.0,
) -> Callable[[Nokta, Nokta], float]:
    """A* arama adımına EKLENECEK (bkz. `izgara_a_yildiz_ara(..., ek_
    maliyet_fonksiyonu=...)`) bir SI-farkındalı maliyet fonksiyonu üretir.

    3W KURALI: paralel yüksek-hızlı izler arası mesafe >= `w_kurali_
    carpani * net_genislik_mm` (varsayılan 3x — crosstalk/EMI için
    endüstri standardı) olmalı. Üretilen kapanış (closure), her aday A*
    adımının (a->b segmentinin ORTA NOKTASI) `diger_hs_izler`'deki
    (BAŞKA bir net'e ait, `pcb_carpisma_radari.IzEngeli`) en yakın ize
    olan mesafesini ölçer; mesafe eşiğin ALTINDAYSA eksik mesafeyle
    orantılı bir CEZA döner — eşiğin üstündeyse ceza TAM SIFIRDIR
    (temel A* maliyetine hiçbir şey eklenmez).

    `empedans_cozucu.py` BAĞLANTISI: `net_genislik_mm`, çağıran tarafın
    `pcb_stackup_planner.empedans_geometrisi_coz()`'den (hedef empedansı
    KARŞILAYAN gerçek W) aldığı değer OLMALIDIR — bu fonksiyon o
    geometriyi YENİDEN HESAPLAMAZ. Bu, "routing-sonrası empedans/3W
    kontrolü" (`emi_emc_kural_motoru.py::uc_w_kuraline_cevir` gibi)
    modellerinden FARKLI olarak, ihlali routing BAŞLAMADAN ÖNCE değil
    routing SIRASINDA (her adayı puanlayarak) önler.

    `diger_hs_izler` BOŞSA fonksiyon her zaman 0.0 döner (performans
    kısayolu — boş bir listede en_yakin hesaplamak ValueError fırlatırdı,
    burada bilerek erken çıkılır)."""
    esik_mm = w_kurali_carpani * net_genislik_mm

    def _maliyet(a: Nokta, b: Nokta) -> float:
        if not diger_hs_izler:
            return 0.0
        orta_x, orta_y = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        en_yakin = min(
            nokta_segmente_dik_mesafe(orta_x, orta_y, iz.x1, iz.y1, iz.x2, iz.y2)
            for iz in diger_hs_izler
        )
        if en_yakin >= esik_mm:
            return 0.0
        eksik = esik_mm - en_yakin
        return ihlal_agirligi * eksik

    return _maliyet


def via_impedans_sureksizligi_maliyeti(via_maliyeti_temel: float, empedans_sapma_yuzde: float = 0.0) -> float:
    """Bir via'nın "empedans süreksizliği" cezasını, stackup çözücüden
    gelen empedans sapma yüzdesiyle (`pcb_stackup_planner.empedans_
    geometrisi_coz()`'ün `en_iyi.hata_yuzde` alanı) ÖLÇEKLER.

    Gerekçe: her via KENDİ BAŞINA küçük bir empedans süreksizliğidir
    (referans düzlem geçişi, ek kapasitans). Geometri ZATEN hedef
    empedanstan sapmışsa (`empedans_sapma_yuzde > 0`), üstüne bir via
    daha eklemek DAHA RİSKLİDİR — bu fonksiyon o riski `via_maliyeti`'ni
    DOĞRUSAL olarak büyüterek A*'a yansıtır. `empedans_sapma_yuzde=0.0`
    (varsayılan) -> `via_maliyeti_temel` DEĞİŞMEDEN döner (geriye dönük
    uyumlu, mevcut çağıranları BOZMAZ)."""
    return via_maliyeti_temel * (1.0 + empedans_sapma_yuzde / 100.0)


# ------------------------------------------------------------------
# 2d. KATMAN/VIA-FARKINDALI A*
#     (arama durumu artık (hücre, katman) — via kullanmanın maliyeti var
#     VE via_yerlesimi_gecerli_mi() geçmeyen bir nokta via YERİ olarak
#     hiç ÜRETİLMEZ, sonradan filtrelenmez)
# ------------------------------------------------------------------

def _sezgisel3d(a: IzgaraDugum3D, b: IzgaraDugum3D) -> float:
    """2D octile sezgi + katman farkı sezgiye KATKI YAPMAZ (0 varsayılır)
    — A*'ın kabul edilebilirliği (sezgi asla gerçek maliyeti AŞMAMALI)
    için gerekli; katman farkını sezgiye eklemek `via_maliyeti`'ni tahmin
    etmeyi gerektirir ve YANLIŞLIKLA gerçek maliyeti AŞARSA A* optimal
    olmayan bir yol bulabilir. Bu basitleştirme A*'ı Dijkstra'ya biraz
    YAKLAŞTIRIR (potansiyel olarak daha fazla düğüm gezilir) ama asla
    YANLIŞ/optimal-olmayan bir yol BULMAZ."""
    return _sezgisel((a[0], a[1]), (b[0], b[1]))


@dataclass
class KatmanliAramaSonucu:
    yol: List[Tuple[float, float, int]]  # (x_mm, y_mm, katman_indeksi)
    via_konumlari: List[Nokta]
    dugum_sayisi: int
    bulundu_mu: bool
    neden: str = ""


def izgara_a_yildiz_ara_katmanli(
    baslangic: Nokta,
    bitis: Nokta,
    katman_sayisi: int = 2,
    baslangic_katman: int = 0,
    bitis_katman: int = 0,
    katman_engelleri: Optional[Dict[int, Sequence[KutuBenzeri]]] = None,
    hucre_mm: float = 0.1,
    clearance_mm: float = 0.2,
    maks_dugum: int = 200_000,
    via_maliyeti: float = 5.0,
    via_capi_mm: float = 0.5,
    via_delik_capi_mm: float = 0.3,
    komsu_delikler: Sequence[Tuple[float, float, float]] = (),
    min_annular_ring_mm: float = 0.15,
    min_hole_to_hole_mm: float = 0.2,
    ek_maliyet_fonksiyonu: Optional[Callable[[Nokta, Nokta], float]] = None,
    empedans_sapma_yuzde: float = 0.0,
) -> KatmanliAramaSonucu:
    """`izgara_a_yildiz_ara()`'nın KATMAN-farkında genişlemesi.

    Arama durumu `(hücre_x, hücre_y, katman)` üçlüsüdür. Aynı katmanda
    hareket normal 8-yönlü maliyetle (1.0/√2) devam eder; KATMAN
    DEĞİŞTİRMEK (via açmak) `via_maliyeti` EK maliyet öder VE o (x,y)
    noktası `via_yerlesimi_gecerli_mi()`'den GEÇMEDİĞİ SÜRECE bir komşu
    olarak ÜRETİLMEZ bile — annular-ring/hole-to-hole ihlali üretecek bir
    yol hiç ARANMAZ, sonradan filtrelenmez (bkz. dosya başlığı: bu kontrol
    projede DAHA ÖNCE HİÇ YOKTU, 221-ihlallik gerçek bir olayın nedeniydi).

    `katman_engelleri`, `{katman_indeksi: [engel, ...]}` biçiminde HER
    katmanın KENDİ engel listesini taşır — sözlükte olmayan bir katman
    engelsiz kabul edilir.

    `ek_maliyet_fonksiyonu` (FAZ 0.5-2): `izgara_a_yildiz_ara()` ile AYNI
    sözleşme — SADECE aynı-katman hareketlerine uygulanır (via geçişlerine
    DEĞİL, o zaten `via_maliyeti` ile ayrı fiyatlandırılıyor).

    `empedans_sapma_yuzde` (FAZ 0.5-2): `pcb_stackup_planner.
    empedans_geometrisi_coz()`'ün `hata_yuzde` alanından beslenir —
    `via_impedans_sureksizligi_maliyeti()` ile `via_maliyeti`'ni ÖLÇEKLER
    (hedeften ne kadar sapılmışsa via açmak o kadar PAHALI hale gelir).
    Varsayılan 0.0 -> `via_maliyeti` DEĞİŞMEDEN kullanılır (geriye dönük
    uyumlu).
    """
    if katman_sayisi < 1:
        raise ValueError("katman_sayisi >= 1 olmalı")
    if not (0 <= baslangic_katman < katman_sayisi and 0 <= bitis_katman < katman_sayisi):
        raise ValueError("baslangic_katman/bitis_katman [0, katman_sayisi) aralığında olmalı")

    katman_engelleri = katman_engelleri or {}

    bas_h = _hucreye_cevir(baslangic, hucre_mm)
    bit_h = _hucreye_cevir(bitis, hucre_mm)
    bas_dugum: IzgaraDugum3D = (bas_h[0], bas_h[1], baslangic_katman)
    bit_dugum: IzgaraDugum3D = (bit_h[0], bit_h[1], bitis_katman)

    def _katman_engelli_mi(hucre: IzgaraHucresi, katman: int) -> bool:
        return _hucre_engelli_mi(hucre, katman_engelleri.get(katman, ()), hucre_mm, clearance_mm)

    if _katman_engelli_mi(bas_h, baslangic_katman):
        return KatmanliAramaSonucu([], [], 0, False, "başlangıç noktası engelli bölgede")
    if _katman_engelli_mi(bit_h, bitis_katman):
        return KatmanliAramaSonucu([], [], 0, False, "bitiş noktası engelli bölgede")
    if bas_dugum == bit_dugum:
        return KatmanliAramaSonucu(
            [(baslangic[0], baslangic[1], baslangic_katman), (bitis[0], bitis[1], bitis_katman)],
            [], 0, True,
        )

    via_gecerlilik_onbellegi: Dict[IzgaraHucresi, Tuple[bool, str]] = {}

    def _via_gecerli_mi(hucre: IzgaraHucresi) -> Tuple[bool, str]:
        if hucre not in via_gecerlilik_onbellegi:
            nokta = _noktaya_cevir(hucre, hucre_mm)
            via_gecerlilik_onbellegi[hucre] = via_yerlesimi_gecerli_mi(
                nokta, via_capi_mm, via_delik_capi_mm, komsu_delikler,
                min_annular_ring_mm, min_hole_to_hole_mm,
            )
        return via_gecerlilik_onbellegi[hucre]

    acik: List[Tuple[float, float, IzgaraDugum3D]] = [(_sezgisel3d(bas_dugum, bit_dugum), 0.0, bas_dugum)]
    geldigi: dict = {bas_dugum: None}
    g_skoru: dict = {bas_dugum: 0.0}
    ziyaret_edildi: set = set()

    while acik:
        if len(ziyaret_edildi) > maks_dugum:
            return KatmanliAramaSonucu([], [], len(ziyaret_edildi), False, f"düğüm bütçesi ({maks_dugum}) aşıldı")

        _, mevcut_g, mevcut = heapq.heappop(acik)
        if mevcut in ziyaret_edildi:
            continue
        ziyaret_edildi.add(mevcut)

        if mevcut == bit_dugum:
            dugum_yol: List[IzgaraDugum3D] = []
            n: Optional[IzgaraDugum3D] = mevcut
            while n is not None:
                dugum_yol.append(n)
                n = geldigi[n]
            dugum_yol.reverse()

            yol_mm: List[Tuple[float, float, int]] = [
                (*_noktaya_cevir((d[0], d[1]), hucre_mm), d[2]) for d in dugum_yol
            ]
            yol_mm[0] = (baslangic[0], baslangic[1], baslangic_katman)
            yol_mm[-1] = (bitis[0], bitis[1], bitis_katman)
            via_konumlari = [
                _noktaya_cevir((dugum_yol[i][0], dugum_yol[i][1]), hucre_mm)
                for i in range(1, len(dugum_yol))
                if dugum_yol[i][2] != dugum_yol[i - 1][2]
            ]
            return KatmanliAramaSonucu(yol_mm, via_konumlari, len(ziyaret_edildi), True)

        mx, my, mk = mevcut

        for dx, dy, maliyet in _YONLER:
            komsu_h = (mx + dx, my + dy)
            komsu: IzgaraDugum3D = (komsu_h[0], komsu_h[1], mk)
            if komsu in ziyaret_edildi:
                continue
            if _katman_engelli_mi(komsu_h, mk):
                continue
            adim_maliyeti = maliyet
            if ek_maliyet_fonksiyonu is not None:
                adim_maliyeti += ek_maliyet_fonksiyonu(
                    _noktaya_cevir((mx, my), hucre_mm), _noktaya_cevir(komsu_h, hucre_mm),
                )
            aday_g = mevcut_g + adim_maliyeti
            if aday_g < g_skoru.get(komsu, float("inf")):
                g_skoru[komsu] = aday_g
                geldigi[komsu] = mevcut
                f = aday_g + _sezgisel3d(komsu, bit_dugum)
                heapq.heappush(acik, (f, aday_g, komsu))

        gecerli, _sebep = _via_gecerli_mi((mx, my))
        if gecerli:
            efektif_via_maliyeti = via_impedans_sureksizligi_maliyeti(via_maliyeti, empedans_sapma_yuzde)
            for hedef_katman in range(katman_sayisi):
                if hedef_katman == mk:
                    continue
                komsu = (mx, my, hedef_katman)
                if komsu in ziyaret_edildi:
                    continue
                if _katman_engelli_mi((mx, my), hedef_katman):
                    continue
                aday_g = mevcut_g + efektif_via_maliyeti
                if aday_g < g_skoru.get(komsu, float("inf")):
                    g_skoru[komsu] = aday_g
                    geldigi[komsu] = mevcut
                    f = aday_g + _sezgisel3d(komsu, bit_dugum)
                    heapq.heappush(acik, (f, aday_g, komsu))

    return KatmanliAramaSonucu([], [], len(ziyaret_edildi), False, "engelsiz yol bulunamadı (arama tükendi)")


# ------------------------------------------------------------------
# 3. PCBNEW YAZMA KATMANI (izole/ince — sadece düz Track ekler)
# ------------------------------------------------------------------

def duz_izleri_pcbnew_ile_yaz(
    board_path: str, net_ismi: str, yol_noktalari: Sequence[Nokta], genislik_mm: float, katman: str = "F.Cu",
) -> int:
    """`izgara_a_yildiz_ara()`'nın ürettiği polyline'ı gerçek board'a DÜZ
    `pcbnew.PCB_TRACK` segmentleri olarak yazar — KiCad'in `route_trace`/
    PNS ROUTER ÇEKİRDEĞİNİ KULLANMAZ (kullanıcının açık isteği), sadece
    `pcbnew.PCB_TRACK`'i doğrudan `board.Add()` ile ekler.

    `topolojik_router_koprusu.py::TopolojikRouter.iz_yaz()` ile AYNI
    yazma deseni (bilinçli tekrar değil — o fonksiyon ÇAĞRILIR, kod
    kopyalanmaz) — bu ortamda `pcbnew` YOK, SENİN makinende doğrulanmalı.
    """
    from topolojik_router_koprusu import Strateji, YolSonucu, TopolojikRouter

    segmentler = [(yol_noktalari[i], yol_noktalari[i + 1]) for i in range(len(yol_noktalari) - 1)]
    sonuc = YolSonucu(segmentler, Strateji.U_DONUSU, 0, [katman])
    yazici = TopolojikRouter(board_path)
    return yazici.iz_yaz(sonuc, net_ismi, genislik_mm)


# ------------------------------------------------------------------
# 4. ÖZ-TEST (fault-injection dahil — pcbnew GEREKMEZ)
# ------------------------------------------------------------------

@dataclass
class _TestKutusu:
    x_min: float
    y_min: float
    x_max: float
    y_max: float


def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: başlangıç NOKTASININ TAM ÜSTÜNE engel koyarsak
    arama KESİNLİKLE başarısız (bulundu_mu=False) dönmeli."""
    engel = _TestKutusu(-0.5, -0.5, 0.5, 0.5)
    sonuc = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), [engel], hucre_mm=0.5, clearance_mm=0.1)
    return sonuc.bulundu_mu is False


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. Engelsiz düz yol -> bulunmalı, yol boyu ~mesafeye yakın
    s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), hucre_mm=0.5)
    if not s.bulundu_mu:
        hatalar.append("engelsiz düz yol bulunamadı")
    elif abs(sum(math.dist(s.yol[i], s.yol[i + 1]) for i in range(len(s.yol) - 1)) - 5.0) > 0.6:
        hatalar.append(f"engelsiz yol boyu beklenenden çok farklı: {s.yol}")

    # 2. Duvar ortada -> A* etrafından dolanmalı (akilli_yol_bul'un L/U'sunun
    #    çözemediği, TAM ortayı kapatan bir duvar senaryosu)
    duvar = _TestKutusu(2.0, -0.3, 3.0, 5.0)
    s2 = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), [duvar], hucre_mm=0.25, clearance_mm=0.2)
    if not s2.bulundu_mu:
        hatalar.append("duvar etrafından dolanan yol bulunamadı")

    # 3. Tamamen kapalı kutu (başlangıç noktası engel İÇİNDE) -> temiz FAIL
    kapali = _TestKutusu(-1.0, -1.0, 1.0, 1.0)
    s3 = izgara_a_yildiz_ara((0.0, 0.0), (10.0, 0.0), [kapali], hucre_mm=0.5, clearance_mm=0.1)
    if s3.bulundu_mu or "engelli bölgede" not in s3.neden:
        hatalar.append(f"başlangıcı kapalı senaryo yanlış sonuç verdi: {s3}")

    # 4. Düğüm bütçesi aşılırsa temiz FAIL (sonsuz arama YOK)
    s4 = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), hucre_mm=0.01, maks_dugum=50)
    if s4.bulundu_mu or "bütçe" not in s4.neden:
        hatalar.append(f"düğüm bütçesi aşımı doğru raporlanmadı: {s4}")

    # 5. Aynı hücrede başlangıç/bitiş -> tek segment, arama gerekmez
    s5 = izgara_a_yildiz_ara((0.0, 0.0), (0.02, 0.02), hucre_mm=0.5)
    if not s5.bulundu_mu or s5.dugum_sayisi != 0:
        hatalar.append("aynı hücre kısayolu çalışmadı")

    # 6. Fault injection
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: A* her zaman yol buluyor olabilir")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: otonom_python_router.py öz testleri temiz.")
