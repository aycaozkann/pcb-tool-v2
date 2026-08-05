#!/usr/bin/env python3
"""
pcb_carpisma_radari.py
========================
JSON ÇARPIŞMA RADARI — yapay zekanın (pcb-layout ajanının) yerleşim/routing
doğruluğunu PNG/SVG'ye BAKARAK değil, DETERMİNİSTİK bir JSON API'siyle
kontrol etmesi için.

NEDEN AYRI BİR MODÜL (`pcbnew_koprusu.py`'nin YERİNE değil, YANINA):
--------------------------------------------------------------------------
`pcb_gorsel_kesit.py` (bkz. `HAFIZA/Hafiza_Defteri.md`, "ajana gerçek görme
yeteneği" kaydı) U2 (LGA-14, 0.5mm pitch) gibi yoğun bölgelerde köre kör
koordinat tahminini çözdü — ama GÖRSEL bir araçtır: PNG'ye "bakıp" karar
vermek, bir sonraki adımda yine insan-benzeri sezgi gerektirir ve ölçülebilir
değildir (dosyanın kendi "DÜRÜSTLÜK SINIRI" notu: SVG↔board koordinat
eşlemesinde ~0.06mm yay-örnekleme farkı var — ÖLÇÜM/DRC kararı için
KULLANILMAMALI). Bu modül placement/routing DOĞRULUĞU için görsel araca
alternatif GETİRİR: her footprint'in gerçek sınır kutusunu (bounding box)
`pcbnew.FOOTPRINT.GetBoundingBox()` ile milimetre hassasiyetinde okuyup,
komponent-komponent ÇAKIŞMASINI ve komponent-Edge.Cuts TAŞMASINI sayısal
(X/Y mm örtüşme + tavsiye edilen kaçış mesafesi) bir JSON olarak döndürür.

KURAL (bkz. `.claude/skills/pcb-layout/SKILL.md` ve `CLAUDE.md`): yerleşim
DOĞRULUĞUNU test ederken `pcb_gorsel_kesit.py` ile resim üretip BAKMA —
bu modülün JSON çıktısını (`carpisma_json_uret`) kullan, dönen
`tavsiye_edilen_kacis_X_mm`/`_Y_mm` değerlerine göre koordinatları güncelle.
`pcb_gorsel_kesit.py` SADECE üretim öncesi DFM/görsel son-kontrol için kalır
(bkz. o dosyanın "DÜRÜSTLÜK SINIRI" notu — ölçüm/DRC kararı için hâlâ
KULLANILMAMALI, bu modülün ortaya çıkış nedeni tam olarak bu sınırdır).

MİMARİ TERCİH — pure-geometri fonksiyonları `pcbnew`'DEN BAĞIMSIZ:
--------------------------------------------------------------------------
`mcad_carpisma_koprusu.py`'nin kanıtlanmış desenini izler: gerçek çakışma
matematiği (`sinir_kutulari_carpisiyor_mu`, `carpisan_ciftleri_bul`,
`kart_disina_tasmayi_bul`) SAF Python'dur — `pcbnew`'e hiç dokunmaz, düz
`SinirKutusu` dataclass'ları üzerinde çalışır, bu yüzden mock GEREKMEDEN
gerçek testlerle doğrulanabilir. Sadece `komponent_sinir_kutularini_al()`
gerçek bir `board` nesnesinin `GetFootprints()`/`GetBoundingBox()`
metotlarını ÇAĞIRIR — ama `import pcbnew` bile YAPMAZ (sadece "ördek
tipleme" — duck typing), bu yüzden test dosyasında GERÇEK `pcbnew` modülü
kurulu olmasa bile basit mock/sahte nesnelerle test edilebilir (Görev 4).
Sadece `carpisma_json_uret()`/`carpisma_radari_tara()` (dosyadan gerçek
board YÜKLEYEN CLI-seviyesi sarmalayıcılar) `import pcbnew` yapar — bu
ortamda gerçek `pcbnew` YOKTUR, SENİN makinende doğrulanmalı (bkz.
`pcbnew_koprusu.py` başındaki AĞ/ARAÇ UYARISI ile AYNI disiplin).

ÖLÇÜM TUZAKLARI (`pcbnew_koprusu.py` ile AYNI, tekrar burada da geçerli):
  (b) `GetBoundingBox()` ipek ekran (silkscreen referans/değer) metnini de
      dahil eder — `GetBoundingBox(False, False)` kullanılır (aggregateFlag,
      includeTexts parametreleri kapatılır), yoksa "REF**" metni komponentin
      gerçek gövdesinden çok daha büyük görünüp sahte çakışmalar üretir.
  (d) float mm karşılaştırmaları — bu modülde tüm dış API mm cinsindendir
      (kullanıcıya sunulan JSON okunur olsun diye), ama iç örtüşme testi
      `> 1e-9` toleranslı yapılır (tam sıfır örtüşmeyi "çakışma" SAYMAMAK
      için — iki komponent tam kenar kenara duruyorsa bu bir hata DEĞİLDİR).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

NM_PER_MM = 1_000_000


def _mm(deger_nm: float) -> float:
    return deger_nm / NM_PER_MM


# ------------------------------------------------------------------
# 1. SINIR KUTUSU (SAF VERİ — pcbnew'e bağımlı DEĞİL)
# ------------------------------------------------------------------

@dataclass
class SinirKutusu:
    """Eksen-hizalı (axis-aligned) sınır kutusu, mm cinsinden."""

    ref: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def genislik(self) -> float:
        return self.x_max - self.x_min

    @property
    def yukseklik(self) -> float:
        return self.y_max - self.y_min

    @property
    def merkez(self) -> Tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)


def _kesisim_mm(a: SinirKutusu, b: SinirKutusu) -> Tuple[float, float]:
    """İki kutunun X/Y eksenindeki örtüşme miktarını döner (>0 ise o
    eksende örtüşüyor demektir; ikisi de >0 ise gerçek 2D çakışma var)."""
    ix = min(a.x_max, b.x_max) - max(a.x_min, b.x_min)
    iy = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
    return ix, iy


# ------------------------------------------------------------------
# 2. GERÇEK BOARD'DAN SINIR KUTUSU ÇIKARIMI
#    (duck-typing — `import pcbnew` YOK, bu yüzden mock nesnelerle testi mümkün)
# ------------------------------------------------------------------

def komponent_sinir_kutularini_al(board) -> Dict[str, SinirKutusu]:
    """Karttaki HER footprint'in gerçek sınır kutusunu (bounding box) mm
    cinsinden döner.

    `board`, `GetFootprints()` metodu olan HERHANGİ bir nesne olabilir
    (gerçek `pcbnew.BOARD` veya test için basit bir mock/sahte nesne) —
    bu fonksiyon `pcbnew` modülünü DOĞRUDAN import ETMEZ, sadece verilen
    nesnenin arayüzünü (duck typing) kullanır: `fp.GetReference()`,
    `fp.GetBoundingBox(False, False)`, `bbox.GetLeft()/GetTop()/GetRight()/
    GetBottom()` (nm cinsinden, `pcbnew`'in iç birimiyle TUTARLI).

    TUZAK (b): `GetBoundingBox(False, False)` — iki `False` bilinçlidir,
    silkscreen referans/değer metnini HARİÇ tutar (dosya başlığına bak).
    """
    kutular: Dict[str, SinirKutusu] = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        bbox = fp.GetBoundingBox(False, False)
        kutular[ref] = SinirKutusu(
            ref=ref,
            x_min=_mm(bbox.GetLeft()),
            y_min=_mm(bbox.GetTop()),
            x_max=_mm(bbox.GetRight()),
            y_max=_mm(bbox.GetBottom()),
        )
    return kutular


def kart_sinir_kutusunu_al(board) -> Optional[SinirKutusu]:
    """`Edge.Cuts` çizimlerinin toplam sınır kutusunu döner.

    SINIR (dürüstlük notu): bu bir BOUNDING BOX'tır, tam bir poligon
    içerme (point-in-polygon) testi DEĞİLDİR — dairesel/köşeleri
    kırpılmış (chamfered) bir kart ana hattında, bbox'ın İÇİNDE ama
    GERÇEK ana hattın DIŞINDA kalan bir köşe noktası bu testi YANLIŞ
    NEGATİF (taşma yok sanılır) verebilir. Kesin poligon testi için
    `pcbnew.SHAPE_POLY_SET.Contains()` gerekir (bkz. `pcbnew_koprusu.py::
    _kart_kenari_noktalari` — aynı sınırlama orada da açıkça not edilmiş).
    Dikdörtgen/yuvarlatılmamış kartlarda bu SINIR devreye girmez.
    """
    import pcbnew  # noqa: F401 — sadece Edge_Cuts sabiti için, gerçek ortamda

    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")
    bulundu = False
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        bbox = d.GetBoundingBox()
        bulundu = True
        x_min = min(x_min, _mm(bbox.GetLeft()))
        y_min = min(y_min, _mm(bbox.GetTop()))
        x_max = max(x_max, _mm(bbox.GetRight()))
        y_max = max(y_max, _mm(bbox.GetBottom()))

    if not bulundu:
        return None
    return SinirKutusu("EDGE_CUTS", x_min, y_min, x_max, y_max)


# ------------------------------------------------------------------
# 2b. İZ (TRACK) ENGELİ — İKİ AŞAMALI ÇARPIŞMA TESTİ İÇİN
#     (cm4-io-test'te otonom_python_router.py'nin A*'ı bunu kullanacak)
# ------------------------------------------------------------------
#
# NEDEN BU BÖLÜM VAR (cm4-io-test, 2026-08-05 bulgusu): `otonom_python_
# router.py::izgara_a_yildiz_ara()` engelleri SADECE AABB (x_min/y_min/
# x_max/y_max) olarak test ediyordu. 45°'lik köşegen bir iz için bu AABB,
# izin GERÇEK çizgisinden çok daha büyük bir dikdörtgendir (örn. (48,16.46)
# -> (31.86,27.275) köşegeninin AABB'si X:[31.86,48] Y:[16.46,27.275] -
# bu dikdörtgenin köşelerine yakın büyük üçgen alanlar TAMAMEN BOŞ olduğu
# halde "engelli" sayılıyordu). Gerçek cm4-io-test HDMI0_TX2_P J2->via
# hop'unda bu YÜZDEN A*'ın hedef/başlangıç noktası "engelli bölgede"
# yanlış-pozitif verdi, halbuki nokta o köşegen çizgisinden gerçekte
# >1mm uzaktaydı.
#
# İKİ AŞAMALI ÇÖZÜM (broad + narrow phase, klasik çarpışma-motoru deseni):
#   1. Broad phase: mevcut AABB testi AYNEN korunur (performans için ön
#      filtre — nokta AABB DIŞINDAYSA gerçek segment hiç hesaplanmaz).
#   2. Narrow phase: nokta AABB İÇİNDEYSE, engel bir `IzEngeli` (segment)
#      ise noktanın segmente GERÇEK dik mesafesi ölçülür
#      (`nokta_segmente_dik_mesafe`); bu mesafe (iz_genişliği/2 +
#      clearance)'tan BÜYÜKSE nokta güvenlidir (AABB içinde ama çizgiden
#      yeterince uzak) - yanlış-pozitif İPTAL edilir.
#   `SinirKutusu` (komponent) engelleri narrow-phase'e GİRMEZ - bir
#   komponentin gerçek gövdesi zaten o AABB'nin büyük kısmını dolduruyor
#   kabul edilir (segment değil, katı cisim), bu yüzden mevcut davranış
#   BOZULMADAN korunur.

def nokta_segmente_dik_mesafe(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """`(px,py)` noktasının `(x1,y1)-(x2,y2)` ÇİZGİ SEGMENTİNE (sonsuz
    doğruya değil) en kısa dik mesafesi, mm cinsinden. Standart vektör
    projeksiyon matematiği: en yakın nokta segment dışına düşerse en
    yakın UCA kenetlenir (clamped). Segment sıfır uzunluklu ise (x1,y1)
    == (x2,y2), bu bir NOKTA engeli demektir (örn. bir via) - düz nokta-
    nokta mesafesine düşer, özel durum kodu GEREKMEZ (aşağıdaki formül
    `uzunluk_kare == 0` durumunu zaten ayrı ele alır)."""
    dx, dy = x2 - x1, y2 - y1
    uzunluk_kare = dx * dx + dy * dy
    if uzunluk_kare < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / uzunluk_kare))
    yakin_x, yakin_y = x1 + t * dx, y1 + t * dy
    return math.hypot(px - yakin_x, py - yakin_y)


@dataclass
class IzEngeli:
    """Bir bakır iz (track) veya via'nın segment-doğru engel temsili.

    `x_min`/`y_min`/`x_max`/`y_max` (broad-phase AABB) `SinirKutusu` ile
    AYNI arayüzü sağlar - `otonom_python_router.py`'nin mevcut
    `KutuBenzeri` Protocol'üne (duck-typing) uyar, YENİ bir tip kontrolü
    GEREKMEZ. Narrow-phase testi bu sınıfın `x1/y1/x2/y2/genislik_mm`
    alanlarının VARLIĞIYLA (hasattr) tetiklenir - `SinirKutusu`'nun bu
    alanları YOKTUR, bu yüzden narrow-phase'e hiç girmez (katı cisim
    olarak kalır, davranış değişmez).

    Via'lar (nokta engeli) `x1==x2, y1==y2` ile temsil edilir -
    `nokta_segmente_dik_mesafe` bunu otomatik nokta-mesafesine indirger.
    """

    ref: str
    x1: float
    y1: float
    x2: float
    y2: float
    genislik_mm: float

    @property
    def x_min(self) -> float:
        return min(self.x1, self.x2) - self.genislik_mm / 2.0

    @property
    def x_max(self) -> float:
        return max(self.x1, self.x2) + self.genislik_mm / 2.0

    @property
    def y_min(self) -> float:
        return min(self.y1, self.y2) - self.genislik_mm / 2.0

    @property
    def y_max(self) -> float:
        return max(self.y1, self.y2) + self.genislik_mm / 2.0


def iz_engellerini_al(board, haric_net_adi: Optional[str] = None) -> List["IzEngeli"]:
    """Karttaki HER track/via'yı `IzEngeli` engeli olarak döner -
    `komponent_sinir_kutularini_al()` ile AYNI duck-typing deseni
    (`board.GetTracks()`, `pad.Type()`, vb. - `import pcbnew` YAPMAZ,
    çağıran taraf `pcbnew.PCB_VIA_T` sabitini KENDİSİ karşılaştırıp
    verir gerekmez; burada `Type()`'ın döndürdüğü değer `board`'un
    kendi modülünden geldiği için ekstra import gerekmiyor).

    `haric_net_adi` verilirse o net'in KENDİ track/via'ları engel
    listesine ALINMAZ (henüz routelanmamış/routelanmakta olan net'in
    kendi geçmiş denemelerini kendine engel saymaması için) - `None`
    ise (varsayılan) TÜM net'ler dahil edilir.
    """
    import pcbnew  # lazy - MASTER_RULEBOOK "pcbnew Bağımlılığı Her Zaman Lazy"

    NM = NM_PER_MM
    engeller: List[IzEngeli] = []
    for t in board.GetTracks():
        net_adi = t.GetNetname()
        if haric_net_adi is not None and net_adi == haric_net_adi:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            pos = t.GetPosition()
            x, y = pos.x / NM, pos.y / NM
            genislik = t.GetWidth(pcbnew.F_Cu) / NM  # bkz. PCB_VIA::GetWidth katman argümanı notu
            engeller.append(IzEngeli(f"via_{net_adi}", x, y, x, y, genislik))
        else:
            s, e = t.GetStart(), t.GetEnd()
            genislik = t.GetWidth() / NM
            engeller.append(IzEngeli(
                f"trk_{net_adi}", s.x / NM, s.y / NM, e.x / NM, e.y / NM, genislik,
            ))
    return engeller


# ------------------------------------------------------------------
# 3. SAF GEOMETRİ — ÇAKIŞMA + TAŞMA TESPİTİ (pcbnew'e bağımlı DEĞİL)
# ------------------------------------------------------------------

def kutular_carpisiyor_mu(a: SinirKutusu, b: SinirKutusu, tolerans_mm: float = 1e-9) -> Optional[Tuple[float, float]]:
    """İki kutu çakışıyorsa (X, Y örtüşme miktarı, mm) döner, aksi halde
    `None`. TUZAK (d): tam kenar-kenar temas (örtüşme == 0) çakışma
    SAYILMAZ — `tolerans_mm` bu sınırı float hassasiyetiyle korur."""
    ix, iy = _kesisim_mm(a, b)
    if ix > tolerans_mm and iy > tolerans_mm:
        return (round(ix, 4), round(iy, 4))
    return None


def _tavsiye_edilen_kacis(sabit: SinirKutusu, hareketli: SinirKutusu, ic_ice_x: float, ic_ice_y: float) -> Tuple[float, float]:
    """`hareketli` parçasının `sabit` parçadan kurtulması için önerilen
    X/Y kaçış mesafesi (mm) — örtüşme miktarına küçük bir emniyet payı
    (0.1mm) eklenir, yön (+/-) iki merkezin göreli konumundan çıkarılır.

    Bu SADECE bir başlangıç önerisidir — hangi eksende kaçmanın daha
    ANLAMLI olduğuna (ör. komşu bir üçüncü komponente çarpmamak) karar
    vermek çağıran tarafın (pcb-layout ajanı) sorumluluğundadır; bu
    fonksiyon sadece "bu iki parçayı ayırmak için gereken minimum mesafe
    ne kadar" sorusuna cevap verir, nihai yerleşim kararını VERMEZ.
    """
    pay = 0.1
    sm_x, sm_y = sabit.merkez
    hm_x, hm_y = hareketli.merkez
    yon_x = 1.0 if hm_x >= sm_x else -1.0
    yon_y = 1.0 if hm_y >= sm_y else -1.0
    return (round(yon_x * (ic_ice_x + pay), 4), round(yon_y * (ic_ice_y + pay), 4))


def carpisan_ciftleri_bul(kutular: Dict[str, SinirKutusu]) -> List[Dict[str, Any]]:
    """Her ikili footprint çiftini tarar, çakışanlar için Görev 2'nin TAM
    JSON şemasında bir kayıt üretir:
    `{"hata_tipi": "CARPISMA", "parca_1", "parca_2",
      "ic_ice_gecme_X_mm", "ic_ice_gecme_Y_mm", "tavsiye_edilen_kacis_X_mm",
      "tavsiye_edilen_kacis_Y_mm"}`.

    `parca_2`, `parca_1`'e göre HAREKETLİ kabul edilir (kaçış önerisi ona
    göre hesaplanır) — iki parçadan hangisinin gerçekte sabit/hareketli
    olduğuna (ör. konnektör vs. pasif) karar vermek çağıran tarafındır.
    """
    ihlaller: List[Dict[str, Any]] = []
    refs = sorted(kutular)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = kutular[refs[i]], kutular[refs[j]]
            ortusme = kutular_carpisiyor_mu(a, b)
            if ortusme is None:
                continue
            ix, iy = ortusme
            kacis_x, kacis_y = _tavsiye_edilen_kacis(a, b, ix, iy)
            ihlaller.append({
                "hata_tipi": "CARPISMA",
                "parca_1": a.ref,
                "parca_2": b.ref,
                "ic_ice_gecme_X_mm": ix,
                "ic_ice_gecme_Y_mm": iy,
                "tavsiye_edilen_kacis_X_mm": kacis_x,
                "tavsiye_edilen_kacis_Y_mm": kacis_y,
            })
    return ihlaller


def kart_disina_tasmayi_bul(kutular: Dict[str, SinirKutusu], kart: SinirKutusu) -> List[Dict[str, Any]]:
    """Her footprint'in kart (Edge.Cuts bbox) sınırları İÇİNDE kalıp
    kalmadığını kontrol eder — taşan her parça için
    `{"hata_tipi": "KART_DISI_TASMA", "parca_1", "parca_2": null,
      "ic_ice_gecme_X_mm", "ic_ice_gecme_Y_mm", "tavsiye_edilen_kacis_X_mm",
      "tavsiye_edilen_kacis_Y_mm"}` (Görev 1'in "Edge.Cuts dışına taşma"
    maddesi — `parca_2` burada anlamsız olduğu için `null`, şema Görev
    2'nin örneğiyle TUTARLI tutulur).

    SINIR: `kart` bir BOUNDING BOX'tır, `kart_sinir_kutusunu_al()`'ın
    kendi dürüstlük notuna bakınız (dairesel/kırpılmış kenarlarda kesin
    değildir).
    """
    ihlaller: List[Dict[str, Any]] = []
    for ref in sorted(kutular):
        fp = kutular[ref]
        tasma_sol = max(0.0, kart.x_min - fp.x_min)
        tasma_sag = max(0.0, fp.x_max - kart.x_max)
        tasma_ust = max(0.0, kart.y_min - fp.y_min)
        tasma_alt = max(0.0, fp.y_max - kart.y_max)
        tasma_x = max(tasma_sol, tasma_sag)
        tasma_y = max(tasma_ust, tasma_alt)
        if tasma_x <= 1e-9 and tasma_y <= 1e-9:
            continue
        pay = 0.1
        yon_x = -1.0 if tasma_sol >= tasma_sag else 1.0
        yon_y = -1.0 if tasma_ust >= tasma_alt else 1.0
        ihlaller.append({
            "hata_tipi": "KART_DISI_TASMA",
            "parca_1": ref,
            "parca_2": None,
            "ic_ice_gecme_X_mm": round(tasma_x, 4),
            "ic_ice_gecme_Y_mm": round(tasma_y, 4),
            "tavsiye_edilen_kacis_X_mm": round(yon_x * (tasma_x + pay), 4) if tasma_x > 1e-9 else 0.0,
            "tavsiye_edilen_kacis_Y_mm": round(yon_y * (tasma_y + pay), 4) if tasma_y > 1e-9 else 0.0,
        })
    return ihlaller


# ------------------------------------------------------------------
# 4. BULGU SÖZLEŞMESİYLE SARILMIŞ TARAMA + HAM JSON API
# ------------------------------------------------------------------

def carpisma_radari_tara(kutular: Dict[str, SinirKutusu], kart: Optional[SinirKutusu] = None) -> Bulgu:
    """`bulgu_sozlesmesi.Bulgu` sözleşmesiyle sarılmış sonuç — CLAUDE.md'nin
    doğrulama kapısı zincirine (`tum_gercek_board_kontrollerini_calistir()`
    ile aynı desende) eklenmek için. `kart=None` ise sadece komponent-
    komponent çakışması taranır, Edge.Cuts taşma kontrolü atlanır (KAPSAM_YOK
    değil — bu bilinçli bir opsiyonel parametre, `taranan` sayısı yine
    komponent çift sayısına göre doğru hesaplanır)."""
    ihlaller = carpisan_ciftleri_bul(kutular)
    n = len(kutular)
    taranan = n * (n - 1) // 2
    if kart is not None:
        tasma_ihlalleri = kart_disina_tasmayi_bul(kutular, kart)
        ihlaller.extend(tasma_ihlalleri)
        taranan += n

    return bulgu_uret(
        "carpisma_radari",
        taranan,
        ihlaller,
        f"{n} komponent, {n * (n - 1) // 2} ikili çakışma kombinasyonu"
        + (f" + {n} kart-sınırı kontrolü" if kart is not None else "") + " tarandı.",
    )


def carpisma_json_uret(board_path: str, kicad_cli: Optional[str] = None) -> List[Dict[str, Any]]:
    """CLI-seviyesi sarmalayıcı: gerçek `.kicad_pcb`'yi `pcbnew.LoadBoard()`
    ile açar, TÜM çarpışma/taşma ihlallerini Görev 2'nin TAM JSON şemasında
    düz bir liste olarak döner.

    AĞ/ARAÇ UYARISI (`pcbnew_koprusu.py` ile AYNI disiplin): bu fonksiyon
    `import pcbnew` yapar — bu geliştirme ortamında gerçek `pcbnew` YOKTUR,
    SENİN makinende gerçek bir `.kicad_pcb` ile çalıştırılıp doğrulanmalıdır.
    Alttaki `komponent_sinir_kutularini_al`/`carpisan_ciftleri_bul`/
    `kart_disina_tasmayi_bul` fonksiyonları PCBNEW'DEN BAĞIMSIZ olduğu için
    zaten bu ortamda mock'larla test edilmiştir (bkz. `test_pcb_carpisma_
    radari.py`) — sadece BU sarmalayıcı katmanı doğrulanmamıştır.
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    kutular = komponent_sinir_kutularini_al(board)
    kart = kart_sinir_kutusunu_al(board)
    return carpisan_ciftleri_bul(kutular) + (kart_disina_tasmayi_bul(kutular, kart) if kart else [])


# ------------------------------------------------------------------
# 5. ÖZ-TEST (fault-injection dahil — mock GEREKMEZ, saf geometri)
# ------------------------------------------------------------------

def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. Çakışmayan iki kutu -> None
    a = SinirKutusu("U1", 0, 0, 2, 2)
    b = SinirKutusu("C3", 5, 5, 6, 6)
    if kutular_carpisiyor_mu(a, b) is not None:
        hatalar.append("çakışmayan kutular yanlışlıkla çarpışma sayıldı")

    # 2. Tam kenar kenar temas -> çakışma SAYILMAMALI (tuzak d)
    c = SinirKutusu("U2", 0, 0, 2, 2)
    d = SinirKutusu("U3", 2, 0, 4, 2)
    if kutular_carpisiyor_mu(c, d) is not None:
        hatalar.append("kenar-kenar temas yanlışlıkla çarpışma sayıldı")

    # 3. Gerçek çakışma -> doğru X/Y örtüşme miktarı
    e = SinirKutusu("U1", 0, 0, 2, 2)
    f = SinirKutusu("C3", 1.2, 0.5, 3.2, 2.5)
    ortusme = kutular_carpisiyor_mu(e, f)
    if ortusme is None or abs(ortusme[0] - 0.8) > 1e-6 or abs(ortusme[1] - 1.5) > 1e-6:
        hatalar.append(f"örtüşme miktarı yanlış hesaplandı: {ortusme} (beklenen ~(0.8, 1.5))")

    # 4. FAULT INJECTION: bilerek üst üste konan iki parça KESİNLİKLE FAIL vermeli
    kutular = {"U1": e, "C3": f}
    ihlaller = carpisan_ciftleri_bul(kutular)
    if not ihlaller:
        hatalar.append("fault-injection kırılmadı: üst üste konan parçalar çakışma vermedi")
    elif ihlaller[0]["hata_tipi"] != "CARPISMA":
        hatalar.append(f"JSON şeması yanlış: {ihlaller[0]}")

    # 5. Kart dışına taşma tespiti
    kart = SinirKutusu("EDGE_CUTS", 0, 0, 10, 10)
    tasan = SinirKutusu("J1", -1.0, 2, 1.0, 4)
    tasmalar = kart_disina_tasmayi_bul({"J1": tasan}, kart)
    if not tasmalar or tasmalar[0]["hata_tipi"] != "KART_DISI_TASMA":
        hatalar.append("kart dışına taşma tespit edilemedi")
    elif abs(tasmalar[0]["ic_ice_gecme_X_mm"] - 1.0) > 1e-6:
        hatalar.append(f"taşma miktarı yanlış: {tasmalar[0]}")

    # 6. Kart içinde kalan parça taşma vermemeli
    icerde = SinirKutusu("R1", 1, 1, 2, 2)
    tasmalar2 = kart_disina_tasmayi_bul({"R1": icerde}, kart)
    if tasmalar2:
        hatalar.append("kart içindeki parça yanlışlıkla taşma sayıldı")

    # 7. Bulgu sözleşmesi: taranan=0 (0 veya 1 komponent) -> KAPSAM_YOK
    bos = carpisma_radari_tara({})
    if bos.durum.value != "KAPSAM_YOK":
        hatalar.append("boş komponent listesi KAPSAM_YOK dönmedi")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: pcb_carpisma_radari.py öz testleri temiz.")
