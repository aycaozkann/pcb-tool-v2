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
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple

# Sadece geometri fonksiyonu - pcb_carpisma_radari modülü de `import pcbnew`
# YAPMAZ (kendi lazy-import kuralına uyar), bu yüzden bu modülün başlıktaki
# "pcbnew GEREKMEZ" iddiası bozulmuyor. Narrow-phase çarpışma testi (bkz.
# `_hucre_engelli_mi`) için kullanılır.
from pcb_carpisma_radari import nokta_segmente_dik_mesafe

Nokta = Tuple[float, float]
IzgaraHucresi = Tuple[int, int]


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
) -> AramaSonucu:
    """Başlangıç-bitiş arası 8-yönlü A* ile IZGARA üzerinde en kısa yolu
    arar. Engeller `SinirKutusu`-uyumlu (x_min/y_min/x_max/y_max) herhangi
    bir nesne olabilir — `pcb_carpisma_radari.SinirKutusu` bu arayüzü
    zaten karşılar, ayrı bir dönüşüm GEREKMEZ.

    `maks_dugum` aşılırsa arama DURDURULUR ve `bulundu_mu=False` +
    açıklayıcı `neden` döner — sessizce sonsuza kadar aramaya devam
    edilmez (bkz. dosya başlığı SINIR notu).
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
            aday_g = mevcut_g + maliyet
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
