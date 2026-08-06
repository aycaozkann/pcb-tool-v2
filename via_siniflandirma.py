#!/usr/bin/env python3
"""
via_siniflandirma.py
======================
HDI (High Density Interconnect) via SINIFLANDIRMASI — `pcb_stackup_planner.py`
içindeki `ViaTipi` (SADECE_BOYDAN_BOYA / KOR_VE_GOMULU_IZINLI, İKİLİ BAYRAK)
enum'unun GENİŞLEMESİ, yerine geçmez.

NEDEN AYRI DOSYA VE NEDEN `ViaTipi`'Yİ SİLMİYORUZ:
----------------------------------------------------
`ViaTipi` stackup-SEVİYESİNDE bir POLİTİKA bayrağıdır ("bu board'da
kör/gömülü via'ya İZİN VAR MI") — `fiziksel_dogrulama_yap()` bunu board
genelinde tek bir aspect-ratio üst sınırı seçmek için kullanır.
`ViaTipiDetay` (bu dosyada) ise TEK BİR VIA'nın GERÇEK tipini (blind mi,
buried mi, microvia mı) ve o via'ya ÖZGÜ aspect-ratio sınırını taşır —
bir board'da `KOR_VE_GOMULU_IZINLI` politikası açıkken bile aynı anda
BOYDAN_BOYA, KOR ve MİKROVIA via'lar bir arada bulunabilir (ör. J1/J2
B2B konnektörlerinde microvia, güç düzlemi geçişinde boydan-boya). İkisi
farklı SORUYA cevap verir, biri diğerini gereksiz kılmaz.

`pcbnew_koprusu.py::via_in_pad_kontrolu()` REAKTİF bir kontroldür (ÇİZİLMİŞ
bir board'da via-in-pad'leri BULUR, fab notu uyarısı üretir). Bu dosyadaki
`select_via_type_for_bga()` ise PROAKTİF: yerleşim/routing BAŞLAMADAN ÖNCE,
BGA/fine-pitch bir pad pitch'i verildiğinde hangi via tipinin GEREKTİĞİNİ
önceden söyler — `dolgu_ve_kapak_var_mi=True` işaretini via ÇİZİLMEDEN
zorunlu kılar, sonradan `via_in_pad_kontrolu`'nun yakaladığı "via-in-pad
ama dolgu/kapak yok" durumunu baştan ÖNLER.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

# TEK yönlü bağımlılık (via_siniflandirma -> pcb_stackup_planner). Ters yönde
# (pcb_stackup_planner -> via_siniflandirma) import GEREKİYORSA (ör. yeni
# `via_tipi_aspect_ratio_kontrolu` fonksiyonu bu dosyanın `Via` tipini
# kullanmak için) o import fonksiyon GÖVDESİ İÇİNDE (deferred/local) yapılır
# — döngüsel import'u (circular import) kırmanın standart, kasıtlı yolu.
from pcb_stackup_planner import KATMAN_KALINLIK_VARSAYIMI_MM


class ViaTipiDetay(Enum):
    """Tek bir via'nın GERÇEK fiziksel tipi (IPC-2226 sınıflandırması)."""

    BOYDAN_BOYA = auto()   # through-hole: tüm katmanları delip geçer
    KOR = auto()            # blind: dış katmandan bir iç katmana
    GOMULU = auto()          # buried: iki iç katman arası, dış yüzeyde GÖRÜNMEZ
    MIKROVIA = auto()        # microvia: genelde L1-L2 (veya Ln-1 - Ln), lazer delik


# Via tipine göre MAKSİMUM izinli aspect ratio (delme derinliği / matkap
# çapı). BOYDAN_BOYA değeri `pcb_stackup_planner.py::fiziksel_dogrulama_yap`
# içindeki `maks_izinli_aspect_ratio = 8.0` ile KASITLI OLARAK aynı (tek
# kaynak-of-truth ihlali gibi görünmesin diye burada da AÇIKÇA not
# düşülüyor: iki dosya da IPC-2221/2226'nın aynı endüstri-standart 8:1
# boydan-boya sınırını referans alıyor). KOR/GOMULU/MIKROVIA için 1:1 —
# lazer/mekanik kör delik teknolojisi genelde bunu gerektirir (kaynak:
# IPC-2226 HDI tasarım kılavuzu, Tip I-III mikrovia yapıları).
MAKS_ASPECT_ORANI: dict[ViaTipiDetay, float] = {
    ViaTipiDetay.BOYDAN_BOYA: 8.0,
    ViaTipiDetay.KOR: 1.0,
    ViaTipiDetay.GOMULU: 1.0,
    ViaTipiDetay.MIKROVIA: 1.0,
}


@dataclass
class Via:
    """Tek bir via'nın tam tanımı — `via_stub.py::check_via_stubs()` ve
    `pcb_stackup_planner.py::via_stub_analizi()` ile UYUMLU alan isimleri
    kullanır (net_isim/baslangic_katman/bitis_katman `ViaKullanimi` ile
    birebir eşleşir — o dataclass'ı burada TEKRAR TANIMLAMIYORUZ, çünkü
    `ViaKullanimi` sinyal bütünlüğü/stub odaklı, bu `Via` ise fiziksel
    sınıflandırma/DRC odaklı; ikisinin alan isimlerini tutarlı tutmak
    ileride birleştirmeyi kolaylaştırır, alan setleri farklı kalabilir)."""

    net_isim: str
    baslangic_katman: int  # örn. 1 (L1)
    bitis_katman: int      # örn. 8 (L8)
    tipi: ViaTipiDetay
    matkap_capi_mm: float
    pad_capi_mm: float
    pad_icinde_mi: bool = False       # via-in-pad
    dolgu_ve_kapak_var_mi: bool = False  # IPC-4761 Type VII (dolgu+kapak)

    @property
    def katman_araligi(self) -> int:
        """Via'nın geçtiği katman sayısı (kapsayıcı fark)."""
        return abs(self.bitis_katman - self.baslangic_katman)

    @property
    def aspect_oran(self) -> float:
        """Delme oranı = delinen derinlik / matkap çapı.

        Derinlik, katman aralığı kalınlığını `pcb_stackup_planner.py::
        KATMAN_KALINLIK_VARSAYIMI_MM` (0.15mm/katman varsayımı) ile
        hesaplar — bu sabit BURADA TEKRAR TANIMLANMAZ, doğrudan import
        edilir (görev talimatı: "tekrar tanımlama").
        """
        if self.matkap_capi_mm <= 0:
            return float("inf")
        derinlik_mm = self.katman_araligi * KATMAN_KALINLIK_VARSAYIMI_MM
        return derinlik_mm / self.matkap_capi_mm

    @property
    def maks_izinli_aspect_oran(self) -> float:
        return MAKS_ASPECT_ORANI[self.tipi]


# ------------------------------------------------------------------
# PROAKTİF KARAR: BGA/fine-pitch pad yoğunluğuna göre via tipi seçimi
# ------------------------------------------------------------------

def select_via_type_for_bga(
    pad_pitch_mm: float,
    routing_layer_gap: int,
    mikrovia_matkap_capi_mm: float = 0.1,
    kor_matkap_capi_mm: float = 0.15,
    boydan_boya_matkap_capi_mm: float = 0.3,
    min_yillik_halka_mm: float = 0.1,
    baslangic_katman: int = 1,
) -> Via:
    """BGA/fine-pitch komponent pad yoğunluğuna göre via tipi seçer.

    Karar tablosu (görev talimatındaki eşiklerle BİREBİR):
      - pitch >= 0.8mm  -> BOYDAN_BOYA (standart via yeterli, maliyet düşük)
      - 0.5mm <= pitch < 0.8mm VE routing_layer_gap yüzeysel (1-2 katman)
        -> KOR
      - pitch < 0.5mm VEYA komşu pad'e sığacak alan yoksa -> MIKROVIA
        (+ pad_icinde_mi=True)

    NOT (fiziksel sınır, dürüstçe belgelenmesi gereken bir sadeleştirme):
    0.5-0.8mm pitch bandında `routing_layer_gap > 2` (yüzeysel DEĞİL)
    durumu üçüncü dala (MIKROVIA) düşer — ama gerçek bir mikrovia TEK
    BAŞINA 1-2 katmandan daha derini pratik olarak GEÇEMEZ (lazer delik
    derinlik sınırı). Bu durumda üretimde gerçek çözüm STAĞLANMIŞ/
    KADEMELİ (stacked/staggered) mikrovia dizisidir, tek bir mikrovia
    DEĞİL — bu fonksiyon sınıflandırma amacıyla yine de en yakın/en
    ince kategori olan MIKROVIA'yı döndürür ve `pad_icinde_mi=True`
    ile IPC-4761 Type VII zorunluluğunu işaretler; ÇAĞIRAN taraf
    `routing_layer_gap > 2` VE `tipi == MIKROVIA` birlikte görürse
    bunun bir via-stack tasarımı gerektirdiğini AYRICA değerlendirmelidir
    (bu fonksiyon stack'i kendisi modellemez).

    Via-in-pad seçilirse (`pad_icinde_mi=True`) `dolgu_ve_kapak_var_mi=True`
    olarak İŞARETLENİR — IPC-4761 Type VII (dolgu+kapak) ZORUNLU tutulur,
    fab notuna bu bilgi otomatik taşınabilir hale gelir (görev talimatı).
    """
    if pad_pitch_mm <= 0:
        raise ValueError(f"pad_pitch_mm pozitif olmalı, alınan: {pad_pitch_mm}")
    if routing_layer_gap < 1:
        raise ValueError(f"routing_layer_gap >= 1 olmalı, alınan: {routing_layer_gap}")

    yuzeysel = routing_layer_gap <= 2

    if pad_pitch_mm >= 0.8:
        tipi = ViaTipiDetay.BOYDAN_BOYA
        matkap = boydan_boya_matkap_capi_mm
        pad_icinde = False
    elif pad_pitch_mm >= 0.5 and yuzeysel:
        tipi = ViaTipiDetay.KOR
        matkap = kor_matkap_capi_mm
        pad_icinde = False
    else:
        # pitch < 0.5mm VEYA (0.5<=pitch<0.8 ama yüzeysel değil, yukarıdaki
        # NOT'ta belgelenen via-stack durumu)
        tipi = ViaTipiDetay.MIKROVIA
        matkap = mikrovia_matkap_capi_mm
        pad_icinde = True

    pad_capi = matkap + 2 * min_yillik_halka_mm
    return Via(
        net_isim="",
        baslangic_katman=baslangic_katman,
        bitis_katman=baslangic_katman + routing_layer_gap,
        tipi=tipi,
        matkap_capi_mm=round(matkap, 4),
        pad_capi_mm=round(pad_capi, 4),
        pad_icinde_mi=pad_icinde,
        dolgu_ve_kapak_var_mi=pad_icinde,
    )
