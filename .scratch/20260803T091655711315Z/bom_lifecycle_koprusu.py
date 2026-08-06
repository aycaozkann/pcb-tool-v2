"""
bom_lifecycle_koprusu.py
=========================
`bom.json` (refdes, MPN) girdisinden Nexar/Octopart tipi bir tedarik-zinciri
API'sine sorgu atıp lifecycle/stok/fiyat bilgisiyle risk skoru üretir, ve
NRND/EOL veya yüksek riskli parçalar için pin-uyumlu alternatif arama akışını
tanımlar. [[SKILL-bom-lifecycle]] karşılığı.

AĞ UYARISI (dürüstlük notu — CLAUDE.md/MASTER_RULEBOOK disipliniyle uyumlu):
------------------------------------------------------------------------
Bu dosyanın GraphQL istemci fonksiyonları (`nexar_sorgula`) gerçek bir API
anahtarı ve ağ erişimi GEREKTİRİR. Bu ortamda (sandbox) böyle bir erişim
YOKTUR — `nexar_sorgula` bilerek bir `NotImplementedError`/placeholder'dır,
UYDURMA VERİ DÖNDÜRMEZ. Gerçek entegrasyon SENİN makinende, gerçek bir
Nexar API key'iyle tamamlanmalı. Ağ yoksa/API dönmezse her alan `TBD` veya
`CONFIRM` olarak işaretlenmeli — hayali MPN/fiyat/stok asla üretilmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ------------------------------------------------------------------
# 1. VERİ YAPILARI
# ------------------------------------------------------------------

class LifecycleDurumu(Enum):
    ACTIVE = "Active"
    NRND = "NRND"  # Not Recommended for New Designs
    EOL = "EOL"
    OBSOLETE = "Obsolete"
    BILINMIYOR = "TBD"


@dataclass
class BomSatiri:
    refdes: str
    mpn: str
    paket: Optional[str] = None
    pinout_imza: Optional[str] = None  # datasheet'ten çıkarılan pin fonksiyon dizisi
    kritik: bool = False  # tek kaynak riski taşımaması gereken parça mı


@dataclass
class TedarikVerisi:
    """Nexar/Octopart sorgusundan (veya CONFIRM/TBD placeholder'dan) dönen veri."""

    mpn: str
    lifecycle: LifecycleDurumu = LifecycleDurumu.BILINMIYOR
    toplam_stok: Optional[int] = None
    tedarikci_sayisi: Optional[int] = None
    lead_time_gun: Optional[int] = None
    kaynak: str = "TBD"  # "nexar" | "TBD" | "CONFIRM"


@dataclass
class RiskSkoru:
    mpn: str
    skor: float  # 0.0 (düşük risk) - 1.0+ (yüksek risk)
    nedenler: List[str] = field(default_factory=list)

    @property
    def alternatif_aranmali_mi(self) -> bool:
        return self.skor > 0.5


# ------------------------------------------------------------------
# 2. AĞ SORGUSU (PLACEHOLDER — GERÇEK ENTEGRASYON GEREKİR)
# ------------------------------------------------------------------

def nexar_sorgula(mpn: str, api_key: Optional[str] = None) -> TedarikVerisi:
    """
    Nexar (Octopart) GraphQL API'sine `mpn` için lifecycle/stok/fiyat/offers
    sorgusu atması gereken fonksiyon.

    Bu ortamda ağ erişimi/API key doğrulanmadığı için UYDURMA VERİ
    DÖNDÜRMEZ — `kaynak="TBD"` ile boş bir `TedarikVerisi` döner. Gerçek
    entegrasyon (senin makinende):
      1. `api_key` ile Nexar GraphQL endpoint'ine `supSearchMpn(q: mpn)` sorgusu at.
      2. Dönen `lifecycle_status`, `total_avail`, `sellers`, `median_price_1000`
         alanlarını `TedarikVerisi`'ye map'le, `kaynak="nexar"` işaretle.
      3. API hata/timeout verirse `kaynak="TBD"` ile devam et — hayali MPN
         veya sayı ÜRETME.
    """
    if api_key is None:
        return TedarikVerisi(mpn=mpn, kaynak="TBD")
    raise NotImplementedError(
        "Gerçek Nexar GraphQL entegrasyonu bu ortamda yapılmadı — "
        "senin makinende gerçek api_key ile tamamlanmalı."
    )


def validate_bom_lifecycle(
    bom: List[BomSatiri],
    api_key: Optional[str] = None,
) -> Dict[str, TedarikVerisi]:
    """Her BOM satırı için `nexar_sorgula` çağırır, MPN -> TedarikVerisi map'i döner."""
    return {satir.mpn: nexar_sorgula(satir.mpn, api_key=api_key) for satir in bom}


# ------------------------------------------------------------------
# 3. RİSK SKORU
# ------------------------------------------------------------------

_LIFECYCLE_AGIRLIK = {
    LifecycleDurumu.ACTIVE: 0.0,
    LifecycleDurumu.NRND: 0.6,
    LifecycleDurumu.EOL: 1.0,
    LifecycleDurumu.OBSOLETE: 1.0,
    LifecycleDurumu.BILINMIYOR: 0.4,  # bilinmeyen durum da bir risktir, 0 sayma
}


def risk_skoru_hesapla(
    satir: BomSatiri,
    tedarik: TedarikVerisi,
    dusuk_stok_esigi: int = 1000,
    uzun_lead_time_gun: int = 26 * 7,  # ~6 ay
) -> RiskSkoru:
    """
    Risk skoru = lifecycle_agirlik + stok_riski + single_source_riski + lead_time_riski

    Ağırlıklar keyfi değil ama kesin bilim de değil — MASTER_RULEBOOK'ta
    "kritik parçada ≥2 kaynak tut" kuralına dayanır. Bileşenlerin toplamı
    1.0'ı aşabilir (bilerek — birden fazla risk faktörü üst üste binebilir).
    """
    nedenler: List[str] = []
    skor = _LIFECYCLE_AGIRLIK[tedarik.lifecycle]
    if tedarik.lifecycle != LifecycleDurumu.ACTIVE:
        nedenler.append(f"lifecycle={tedarik.lifecycle.value}")

    if tedarik.toplam_stok is not None and tedarik.toplam_stok < dusuk_stok_esigi:
        skor += 0.3
        nedenler.append(f"düşük stok ({tedarik.toplam_stok} < {dusuk_stok_esigi})")

    if tedarik.tedarikci_sayisi is not None:
        if tedarik.tedarikci_sayisi <= 1:
            skor += 0.3
            nedenler.append("single-source (tek tedarikçi)")
        elif satir.kritik and tedarik.tedarikci_sayisi < 2:
            skor += 0.2
            nedenler.append("kritik parça, <2 kaynak")

    if tedarik.lead_time_gun is not None and tedarik.lead_time_gun > uzun_lead_time_gun:
        skor += 0.2
        nedenler.append(f"uzun lead-time ({tedarik.lead_time_gun} gün)")

    if tedarik.kaynak == "TBD":
        nedenler.append("tedarik verisi doğrulanamadı (ağ/API yok) — CONFIRM gerekli")

    return RiskSkoru(mpn=satir.mpn, skor=round(skor, 3), nedenler=nedenler)


def lifecycle_raporu_olustur(
    bom: List[BomSatiri],
    tedarik_map: Dict[str, TedarikVerisi],
) -> List[RiskSkoru]:
    """Tüm BOM için risk skorlarını hesaplar, en riskliden en az riskliye sıralar."""
    skorlar = [
        risk_skoru_hesapla(satir, tedarik_map[satir.mpn])
        for satir in bom
        if satir.mpn in tedarik_map
    ]
    return sorted(skorlar, key=lambda r: r.skor, reverse=True)


# ------------------------------------------------------------------
# 4. PİN-UYUMLU ALTERNATİF ARAMA
# ------------------------------------------------------------------

@dataclass
class AlternatifAday:
    mpn: str
    ayni_paket: bool
    ayni_pinout: bool
    elektriksel_param_eslesiyor: bool
    footprint_degisiyor: bool  # True ise adım 1/2'ye (stackup/routing) feedback açılmalı

    @property
    def gecerli_mi(self) -> bool:
        """
        Kabul kriteri: aynı paket YETMEZ — pinout + elektriksel parametreler
        de eşleşmeli. "Equivalent" marketing lafına güvenme; pinout mutlaka
        datasheet'ten doğrulanmalı (bu bayrak elle/insan onayıyla set edilir,
        otomatik "aynı paket -> uyumlu" varsayımı YAPILMAZ).
        """
        return self.ayni_pinout and self.elektriksel_param_eslesiyor


def find_pin_compatible(
    orijinal: BomSatiri,
    adaylar: List[AlternatifAday],
) -> List[AlternatifAday]:
    """
    Aday listesinden gerçekten pin-uyumlu olanları filtreler. Boş liste
    dönerse `NEEDS_HUMAN` — otomatik bir "en yakın" tahmini YAPILMAZ, çünkü
    yanlış pinout varsayımı kartı doğrudan yakar.
    """
    return [a for a in adaylar if a.gecerli_mi]


def alternatif_karari_ozetle(
    orijinal: BomSatiri,
    risk: RiskSkoru,
    uygun_adaylar: List[AlternatifAday],
) -> str:
    if not risk.alternatif_aranmali_mi:
        return f"{orijinal.mpn}: risk düşük ({risk.skor}), alternatif aranmadı."
    if not uygun_adaylar:
        return (
            f"{orijinal.mpn}: risk yüksek ({risk.skor}, nedenler: {risk.nedenler}) "
            "AMA pin-uyumlu alternatif bulunamadı -> NEEDS_HUMAN."
        )
    footprint_degisen = [a.mpn for a in uygun_adaylar if a.footprint_degisiyor]
    ek_not = (
        f" UYARI: {footprint_degisen} footprint değiştiriyor -> stackup/routing'e "
        "(adım 1/2) feedback aç." if footprint_degisen else ""
    )
    return (
        f"{orijinal.mpn}: risk yüksek ({risk.skor}), önerilen alternatif(ler): "
        f"{[a.mpn for a in uygun_adaylar]}.{ek_not}"
    )
