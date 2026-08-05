"""
hdi_stackup_genisletme.py
===========================
FAZ 0.5 — HDI (High Density Interconnect: mikrovia + blind/buried via)
stackup alanları için GENİŞLETİLEBİLİRLİK İSKELETİ.

BU DOSYA SADECE VERİ MODELİDİR — GERÇEK HESAP MANTIĞI YOKTUR:
--------------------------------------------------------------------------
Aşağıdaki dataclass'lar, `pcb_stackup_planner.py`'nin ileride HDI
katmanlarını (mikrovia stacking kuralları, blind/buried via aspect ratio,
via-in-pad dolgu/kaplama) modellemesi GEREKTİĞİNDE nereye oturacağını
BELİRLER — ama şu an hiçbiri gerçek bir hesap/doğrulama YAPMAZ. Bilinçli
bir tercih: bu proje şu an TEK KATMAN ÇİFTİ (2-4 katman) hedefleyen
kart(lar) üzerinde çalışıyor (bkz. `pcb_stackup_planner.py`'nin mevcut
`KATMAN_KALINLIK_VARSAYIMI_MM` tek-tip katman modeli) — HDI için gerçek
mikrovia aspect-ratio/güvenilirlik kuralları (IPC-2226) YAZMADAN ÖNCE
gerçek bir HDI hedefi (ör. BGA fan-out yoğunluğu stackup'ı zorluyor)
ortaya çıkması beklenir. Şimdiden tam mantık yazmak SPEKÜLATİF genellik
olurdu (bu projenin "ihtiyaç sinyali olmadan hook yazma" disiplini,
bkz. aşağıdaki NEDEN BURADA DURUYORUZ notu).

Bu dosyadaki her dataclass alanı, ileride `pcb_stackup_planner.
stackup_planla()`'nın HDI-farkında bir sürümüne GİRDİ olacak şekilde
tasarlandı — ama o fonksiyon burada YAZILMADI.

NEDEN RİJİT-ESNEK (RIGID-FLEX) VE IC-PAKET ORTAK TASARIMI İÇİN HİÇ HOOK
YOK (bilinçli, kapsam dışı bırakma kararı):
--------------------------------------------------------------------------
İkisi de bu projenin mevcut/planlanan hiçbir tasarımında (tek kamera
kartı prototipi, 6-kamera kafa bandı, IoT görüntü sensörü, cm4-io-test,
SHT35, ESP32-C3) TALEP EDİLMEDİ — ne bir esnek/rijit-esnek board, ne de
paket-içi (IC package-level, ör. interposer/RDL) bir ortak tasarım
senaryosu var. Bu ikisi için şimdiden bir `RijitEsnekBolge`/`PaketRdlKatmani`
iskeleti yazmak, hiçbir gerçek kullanım noktası olmayan SPEKÜLATİF bir
genellik eklemek olurdu — ileride gerçek bir talep (ör. bir esnek
konnektör kablosu veya paket-içi entegrasyon) ortaya çıkarsa, o zaman bu
dosyanın YANINA, aynı "sadece veri modeli, gerçek mantık yok" disipliniyle
eklenmelidirler; burada ÖNDEN üretilmezler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MikroviaKatmani:
    """Bir mikrovia'nın hangi iki bitişik katman arasında delindiğini
    tanımlayan boş veri modeli — GERÇEK aspect-ratio/güvenilirlik
    hesabı YOK (IPC-2226 mikrovia kuralları burada UYGULANMAZ).

    Alanlar, `pcb_stackup_planner.stackup_planla()`'nın çıktısındaki
    `"Katman_N"` isimlendirmesiyle (bkz. o fonksiyonun `Dict[str, str]`
    dönüş sözleşmesi) TUTARLI tutulmak üzere tasarlandı — bu dosyanın
    ileride o sözleşmeyle nasıl birleşeceğini göstermek içindir, şu an
    hiçbir kod bu birleşimi YAPMAZ.
    """

    ust_katman_adi: str  # ör. "Katman_1"
    alt_katman_adi: str  # ör. "Katman_2"
    hedef_delik_capi_mm: Optional[float] = None
    aspect_orani_siniri: Optional[float] = None  # TBD — IPC-2226'dan gelecek, UYDURULMADI


@dataclass
class BlindBuriedViaBolgesi:
    """Blind (yüzeyden bir iç katmana) veya buried (iki iç katman arası,
    dış yüzeyde GÖRÜNMEYEN) bir via bölgesinin boş veri modeli.

    `kor_mu`/`buried_mi` ayrımı fabrikasyon süreç farkını (blind via tek
    bir dış lamine katmanda delinip kaplanır, buried via ayrı bir
    ön-lamine adımı gerektirir) YANSITMAK içindir — ama bu dosyada hiçbir
    fabrikasyon-uyumluluk kontrolü YAPILMAZ.
    """

    baslangic_katman_adi: str
    bitis_katman_adi: str
    buried_mi: bool = False  # False = blind (dış katmandan başlar), True = buried (iki iç katman arası)
    fabrika_destekliyor_mu: Optional[bool] = None  # TBD — fabrika DFM profiline bağlı, UYDURULMADI


@dataclass
class HdiStackupGenisletmesi:
    """Bir stackup'ın HDI alanlarının toplamı — `pcb_stackup_planner.
    stackup_planla()`'nın gelecekteki bir HDI-farkında sürümüne GİRDİ
    olması TASARLANMIŞ, ama HENÜZ HİÇBİR YERDEN TÜKETİLMEYEN boş konteyner.
    """

    mikrovialar: List[MikroviaKatmani] = field(default_factory=list)
    blind_buried_bolgeler: List[BlindBuriedViaBolgesi] = field(default_factory=list)
