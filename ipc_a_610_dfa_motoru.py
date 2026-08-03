#!/usr/bin/env python3
"""
ipc_a_610_dfa_motoru.py
==========================
IPC-A-610 (Elektronik Montajlar için Kabul Kriterleri) ruhuna uygun,
Pick-and-Place (dizgi) ve Reflow (fırınlama) süreçleri için komponentler
arası MİNİMUM BOŞLUK (clearance) hesaplayan DFA (Design For Assembly)
motoru.

ÖNEMLİ — DÜRÜSTLÜK NOTU (bu modülün sayılarının kaynağı, `ipc6012_dfm_motoru.py`
başlığındaki notla AYNI disiplin):
-------------------------------------------------------------------------
Bu ortamda resmi, satın alınmış IPC-A-610 PDF'ine ERİŞİM YOKTUR. Ayrıca
IPC-A-610'un KENDİSİ çoğunlukla GÖRSEL/NİTEL kabul kriterleri tanımlar
(lehim köşesi şekli, ıslanma açısı, komponent hizalanması vb.) — sabit bir
"komponentler arası şu kadar mm" mesafe TABLOSU İÇERMEZ. Aşağıdaki
mesafeler, IPC-A-610'un kabul kriterlerinin (çarpışma, lehim gölgelenmesi/
shadowing, dizgi nozulu erişimi, dalga/el lehimi erişimi) PRATİKTE hangi
fiziksel boşlukla sağlandığına dair, sektörde YAYGIN ATIFTA BULUNULAN
TEMSİLİ değerlerdir (fab yetenek sayfaları + DFM kılavuzları, tıpkı
`ipc6012_dfm_motoru.py`'nin annular ring/aspect ratio değerleri gibi).
Üretime geçmeden önce seçilen dizgi hattının (pick-and-place nozul
toleransı, reflow profili) GÜNCEL yetenek verisiyle çapraz doğrulanmalı.

ÜÇ MESAFE SINIFI (kullanıcının Görev 1 isteğiyle birebir):
-------------------------------------------------------------------------
  1. **SMD-SMD**: dizgi nozulunun çarpışmadan iki komponenti ayrı ayrı
     bırakabilmesi + reflow'da komşu komponentin ısıl gölgelemesi
     (yüksek gövdeli bir komponent, kısa bir komşusuna sıcak hava/IR
     erişimini engelleyip soğuk lehim eklemi riski yaratabilir — IPC-A-610
     Madde 4'ün "yetersiz ıslanma" kabul-red kriterinin kök nedenlerinden
     biridir). Gövde yükseklik farkı eşiği aşarsa EK boşluk istenir.
  2. **SMD-THT**: THT parçalar genelde dalga lehimi/el lehimi/selektif
     lehim ile monte edilir — bu süreçlerin PALET/DEMİR erişimi SMD'den
     daha büyük bir boşluk gerektirir (sıçrama/köprüleme riski).
  3. **Komponent-Kart Kenarı**: dizgi hattının taşıma rayı (rail) +
     nozul/vakum erişimi + (varsa) V-score/depanel stresi keepout'u.

NEDEN AYRI BİR MODÜL (`ipc7351_footprint.py`'nin YERİNE GEÇMEZ):
-------------------------------------------------------------------------
`ipc7351_footprint.py` bir komponentin KENDİ footprint'inin (pad boyutu +
courtyard fazlası) land pattern'ini hesaplar — TEK komponentin kendi
geometrisiyle ilgilidir. Bu modül ise İKİ AYRI komponent arasındaki (veya
bir komponentle kart kenarı arasındaki) montaj-süreci boşluğunu hesaplar —
`mcp__kicad__check_courtyard_overlaps` iki courtyard'ın ÇAKIŞIP
çakışmadığına bakar (ikili/nitel), bu modül ise "en az kaç mm boşluk
OLMALI" sorusuna sayısal cevap verir ve `bulgu_sozlesmesi.Bulgu`
sözleşmesiyle GERÇEK bir yerleşimi bu hedefe karşı denetleyebilir.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret


class KomponentTipi(str, Enum):
    SMD_PASIF = "smd_pasif"        # 2-terminal R/C/L (0201..1210 vb.)
    SMD_IC = "smd_ic"              # gövdeli SMD IC (SOIC/QFN/BGA/SOT vb.)
    THT = "tht"                    # delikli montaj (DIP, elektrolitik, vb.)
    KONNEKTOR = "konnektor"        # büyük mekanik konnektör (USB, header, vb.)


class MontajSinifi(str, Enum):
    """IPC-A-610'un genel Class 1/2/3 sınıflandırması (IPC-6012 ile aynı
    taksonomi) — Class 3 (yüksek güvenilirlik) daha sıkı boşluk ister,
    çünkü kabul edilebilir kusur/yeniden-iş toleransı daha düşüktür."""

    CLASS_1 = "Class 1"  # genel tüketici elektroniği
    CLASS_2 = "Class 2"  # dedike servis elektroniği
    CLASS_3 = "Class 3"  # yüksek güvenilirlik (havacılık/tıbbi/askeri)


@dataclass(frozen=True)
class PaketBoyutlari:
    """Bir komponentin dizgi/reflow açısından ilgili gövde ölçüleri."""

    uzunluk_mm: float
    genislik_mm: float
    yukseklik_mm: float

    def __post_init__(self) -> None:
        if min(self.uzunluk_mm, self.genislik_mm, self.yukseklik_mm) <= 0:
            raise ValueError(f"PaketBoyutlari: tüm boyutlar pozitif olmalı, gelen: {self}")


@dataclass(frozen=True)
class ClearanceSonucu:
    komponent_tipi_a: KomponentTipi
    komponent_tipi_b: KomponentTipi
    minimum_clearance_mm: float
    montaj_sinifi: MontajSinifi
    yukseklik_farki_mm: float
    golgeleme_riski_mi: bool
    kaynak_notu: str


# ------------------------------------------------------------------
# TEMSİLİ TABAN MESAFELER (bkz. dosya başlığı — dürüstlük notu)
# ------------------------------------------------------------------
# Anahtar: frozenset({tip_a, tip_b}) — sırasız çift (A-B ile B-A aynı kural).
_SMD_SMD_TABAN_MM: dict[frozenset, float] = {
    frozenset({KomponentTipi.SMD_PASIF}): 0.20,                              # pasif-pasif
    frozenset({KomponentTipi.SMD_PASIF, KomponentTipi.SMD_IC}): 0.25,
    frozenset({KomponentTipi.SMD_IC}): 0.30,                                 # IC-IC
}

_SMD_THT_TABAN_MM: dict[frozenset, float] = {
    frozenset({KomponentTipi.SMD_PASIF, KomponentTipi.THT}): 1.00,
    frozenset({KomponentTipi.SMD_IC, KomponentTipi.THT}): 1.50,
    frozenset({KomponentTipi.THT}): 2.00,                                    # THT-THT
}

# Class 2 taban değerine göre çarpan — Class 1 daha gevşek, Class 3 daha sıkı.
_SINIF_CARPANI: dict[MontajSinifi, float] = {
    MontajSinifi.CLASS_1: 0.85,
    MontajSinifi.CLASS_2: 1.00,
    MontajSinifi.CLASS_3: 1.30,
}

# Konnektör: mekanik kısıt (mating/aktüatör keepout) ağır bastığı için
# ayrı, daha büyük bir taban kullanılır — küçük bir pasifle bile en az
# bu kadar boşluk istenir (konnektör gövdesi + tolerans + el/alet erişimi).
_KONNEKTOR_TABAN_MM = 1.50

# Reflow ısıl gölgeleme (shadowing): iki SMD komponent arasındaki gövde
# yükseklik farkı bu eşiği AŞARSA, kısa komponent sıcak hava/IR'a
# yetersiz erişebilir (soğuk lehim eklemi riski) — ek boşluk istenir.
GOLGELEME_YUKSEKLIK_ESIGI_MM = 2.0
GOLGELEME_EK_BOSLUK_MM = 0.30

# Komponent-kart kenarı keepout — dizgi rayı + nozul/vakum erişimi +
# (varsa) depanel stresi. `dfm_emc_check.py::check_edge_keepout_ceramics`
# ile AYNI riski (kırılgan 2-terminal seramikler) kapsar ama BURADA genel
# olarak TÜM komponent tiplerine, sadece seramiklere değil, uygulanır.
KENAR_KEEPOUT_MM: dict[KomponentTipi, float] = {
    KomponentTipi.SMD_PASIF: 2.0,
    KomponentTipi.SMD_IC: 3.0,
    KomponentTipi.THT: 3.0,
    KomponentTipi.KONNEKTOR: 5.0,
}


def _sinirlar_arasi_bosluk_mm(
    x_a: float, y_a: float, boyut_a: PaketBoyutlari, aci_a: float,
    x_b: float, y_b: float, boyut_b: PaketBoyutlari, aci_b: float,
) -> float:
    """İki komponentin eksene-hizalı (axis-aligned) bounding box'ları
    arasındaki en kısa mesafe (kenar-kenar, merkez-merkez DEĞİL).

    SINIR (bilerek basitleştirildi, yazılı — sessiz sınır sahte güven
    yaratır): rotasyon açısı bounding box'ı GERÇEKTEN döndürmez, sadece
    45°'nin katı olmayan açılarda `uzunluk`/`genislik`'in kabaca YER
    DEĞİŞTİRİP değiştirmediğine (90°/270°) bakar. Rastgele açılı (ör. 37°)
    yerleşimlerde bu YAKLAŞIKTIR ve gerçek mesafeyi OLDUĞUNDAN BÜYÜK
    gösterebilir — kesin doğrulama için gerçek `.kicad_pcb` courtyard
    poligonlarına karşı (`mcp__kicad__check_courtyard_overlaps` /
    `check_clearance`) çapraz kontrol edilmelidir.
    """
    def kutu(x, y, boyut, aci):
        # 90°/270°'de uzunluk-genişlik yer değiştirir; diğer açılarda
        # (yukarıdaki sınır notu) döndürülmemiş kutu kullanılır.
        u, g = boyut.uzunluk_mm, boyut.genislik_mm
        if round(aci) % 180 == 90:
            u, g = g, u
        return (x - u / 2, y - g / 2, x + u / 2, y + g / 2)

    ax0, ay0, ax1, ay1 = kutu(x_a, y_a, boyut_a, aci_a)
    bx0, by0, bx1, by1 = kutu(x_b, y_b, boyut_b, aci_b)

    dx = max(ax0 - bx1, bx0 - ax1, 0.0)
    dy = max(ay0 - by1, by0 - ay1, 0.0)
    # YUVARLAMA KASITLI (proje disiplini — bkz. `ipc_dru_koprusu.py` ve
    # `dfm_emc_check.annular_ring` başlıklarındaki AYNI ders): float
    # çıkarma artığı (`0.19999999999999996` gibi) tam sınırdaki bir çifti
    # yanlışlıkla ihlal gösterebilir. 4 ondalık, bu modülün diğer tüm
    # mm değerleriyle (`round(..., 4)`) TUTARLI bir hassasiyettir.
    return round(math.hypot(dx, dy), 4)


def minimum_clearance_hesapla(
    komponent_tipi_a: KomponentTipi,
    komponent_tipi_b: KomponentTipi,
    paket_boyutlari_a: PaketBoyutlari,
    paket_boyutlari_b: PaketBoyutlari,
    montaj_sinifi: MontajSinifi = MontajSinifi.CLASS_2,
) -> ClearanceSonucu:
    """Görev 1'in çekirdek isteği: (tip_a, tip_b, paket_boyutları) ->
    minimum_clearance_mesafesi (mm). SMD-SMD / SMD-THT / THT-THT
    tablolarını + reflow gölgeleme eklentisini + montaj sınıfı çarpanını
    uygular."""
    ikili = frozenset({komponent_tipi_a, komponent_tipi_b})
    ikisi_de_smd = KomponentTipi.THT not in ikili and KomponentTipi.KONNEKTOR not in ikili
    ikisi_de_tht_veya_karma = KomponentTipi.THT in ikili

    if KomponentTipi.KONNEKTOR in ikili:
        taban = _KONNEKTOR_TABAN_MM
        kaynak = "Konnektör mekanik keepout tabanı (TEMSİLİ, dosya başlığına bkz.)"
    elif ikisi_de_tht_veya_karma:
        taban = _SMD_THT_TABAN_MM.get(ikili) or _SMD_THT_TABAN_MM[frozenset({KomponentTipi.THT})]
        kaynak = "SMD-THT/THT-THT dalga/el-lehimi erişim tabanı (TEMSİLİ)"
    else:
        taban = _SMD_SMD_TABAN_MM.get(ikili) or _SMD_SMD_TABAN_MM[frozenset({KomponentTipi.SMD_IC})]
        kaynak = "SMD-SMD dizgi nozulu erişim tabanı (TEMSİLİ)"

    yukseklik_farki = abs(paket_boyutlari_a.yukseklik_mm - paket_boyutlari_b.yukseklik_mm)
    golgeleme = ikisi_de_smd and yukseklik_farki > GOLGELEME_YUKSEKLIK_ESIGI_MM
    ek = GOLGELEME_EK_BOSLUK_MM if golgeleme else 0.0

    minimum_mm = round((taban + ek) * _SINIF_CARPANI[montaj_sinifi], 4)

    return ClearanceSonucu(
        komponent_tipi_a=komponent_tipi_a,
        komponent_tipi_b=komponent_tipi_b,
        minimum_clearance_mm=minimum_mm,
        montaj_sinifi=montaj_sinifi,
        yukseklik_farki_mm=round(yukseklik_farki, 4),
        golgeleme_riski_mi=golgeleme,
        kaynak_notu=f"{kaynak}; sınıf çarpanı x{_SINIF_CARPANI[montaj_sinifi]} "
                    f"({montaj_sinifi.value})" + (
                        f"; +{GOLGELEME_EK_BOSLUK_MM}mm reflow gölgeleme "
                        f"eki (yükseklik farkı {yukseklik_farki:.2f}mm > "
                        f"{GOLGELEME_YUKSEKLIK_ESIGI_MM}mm)" if golgeleme else ""
                    ),
    )


def minimum_kenar_clearance_mm(komponent_tipi: KomponentTipi) -> float:
    """Komponent-kart kenarı minimum boşluğu (mm) — bkz. `KENAR_KEEPOUT_MM`."""
    return KENAR_KEEPOUT_MM[komponent_tipi]


# ------------------------------------------------------------------
# Gerçek yerleşim denetimi (bulgu_sozlesmesi.Bulgu sözleşmesiyle)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class YerlesikKomponent:
    """`.kicad_pcb`'den (veya `pcbnew_koprusu.py::kicad_pcb_yerlesimlerini_cikar()`
    gibi bir ayrıştırıcıdan) okunan TEK bir komponentin dizgi/reflow
    açısından ilgili verisi."""

    referans: str
    tip: KomponentTipi
    boyutlar: PaketBoyutlari
    x_mm: float
    y_mm: float
    aci_derece: float = 0.0


class IpcA610DfaMotoru:
    """Verilen yerleşimi `minimum_clearance_hesapla()`/`minimum_kenar_clearance_mm()`
    hedeflerine karşı denetler, `Bulgu` sözleşmesiyle PASS/FAIL/KAPSAM_YOK
    raporlar (`ipc6012_dfm_motoru.Ipc6012DfmMotoru` ile AYNI desen)."""

    def __init__(self, montaj_sinifi: MontajSinifi = MontajSinifi.CLASS_2) -> None:
        self.montaj_sinifi = montaj_sinifi

    def komponent_clearance_kontrolu(
        self, yerlesimler: Sequence[YerlesikKomponent]
    ) -> Bulgu:
        """Her komponent ÇİFTİ için (n*(n-1)/2 çift) ölçülen boşluğu
        hesaplanan minimumla karşılaştırır."""
        cift_sayisi = 0
        ihlaller = []
        for i in range(len(yerlesimler)):
            for j in range(i + 1, len(yerlesimler)):
                a, b = yerlesimler[i], yerlesimler[j]
                cift_sayisi += 1
                hedef = minimum_clearance_hesapla(
                    a.tip, b.tip, a.boyutlar, b.boyutlar, self.montaj_sinifi
                )
                olculen = _sinirlar_arasi_bosluk_mm(
                    a.x_mm, a.y_mm, a.boyutlar, a.aci_derece,
                    b.x_mm, b.y_mm, b.boyutlar, b.aci_derece,
                )
                if olculen < hedef.minimum_clearance_mm:
                    ihlaller.append({
                        "a": a.referans, "b": b.referans,
                        "olculen_mm": round(olculen, 4),
                        "minimum_mm": hedef.minimum_clearance_mm,
                        "eksik_mm": round(hedef.minimum_clearance_mm - olculen, 4),
                        "golgeleme_riski_mi": hedef.golgeleme_riski_mi,
                    })
        return bulgu_uret(
            "ipc_a_610_komponent_clearance",
            taranan=cift_sayisi,
            ihlaller=ihlaller,
            detay=f"{len(yerlesimler)} komponent, {cift_sayisi} çift denetlendi "
                  f"({self.montaj_sinifi.value}). SINIR: bounding-box yaklaşıklığı "
                  "kullanır, rastgele açılarda GERÇEK courtyard'dan farklı olabilir "
                  "(bkz. `_sinirlar_arasi_bosluk_mm` docstring'i).",
        )

    def kenar_clearance_kontrolu(
        self,
        yerlesimler: Sequence[YerlesikKomponent],
        kenar_noktalari_mm: Sequence[tuple[float, float]],
    ) -> Bulgu:
        """`dfm_emc_check.py::board_outline_segments()`'ten örneklenmiş
        Edge.Cuts nokta listesine (veya elle verilen) en yakın mesafeyi
        her komponent için ölçer."""
        if not kenar_noktalari_mm:
            return bulgu_uret(
                "ipc_a_610_kenar_clearance", taranan=0,
                detay="Edge.Cuts nokta listesi boş — board outline bulunamadı.",
            )
        ihlaller = []
        for k in yerlesimler:
            en_yakin = min(
                math.hypot(k.x_mm - ex, k.y_mm - ey) for ex, ey in kenar_noktalari_mm
            )
            minimum = minimum_kenar_clearance_mm(k.tip)
            if en_yakin < minimum:
                ihlaller.append({
                    "ref": k.referans, "tip": k.tip.value,
                    "olculen_mm": round(en_yakin, 4), "minimum_mm": minimum,
                })
        return bulgu_uret(
            "ipc_a_610_kenar_clearance",
            taranan=len(yerlesimler),
            ihlaller=ihlaller,
            detay="Komponent-merkezinden en yakın Edge.Cuts örnek noktasına mesafe "
                  "(gövde kenarı DEĞİL — TEMSİLİ/yaklaşık, tıpkı `dfm_emc_check."
                  "check_edge_keepout_ceramics` gibi).",
        )

    def tum_kontrolleri_calistir(
        self,
        yerlesimler: Sequence[YerlesikKomponent] = (),
        kenar_noktalari_mm: Sequence[tuple[float, float]] = (),
    ) -> list[Bulgu]:
        return [
            self.komponent_clearance_kontrolu(yerlesimler),
            self.kenar_clearance_kontrolu(yerlesimler, kenar_noktalari_mm),
        ]

    def genel_sonuc(self, bulgular: Sequence[Bulgu]) -> str:
        if any(b.durum == BulguDurumu.FAIL for b in bulgular):
            return "FAIL"
        if any(b.durum == BulguDurumu.KAPSAM_YOK for b in bulgular):
            return "NEEDS_HUMAN"
        return "PASS"


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: iki SMD pasifi hesaplanan minimumun BİRAZ altına
    yerleştirip kontrolün GERÇEKTEN FAIL verdiğini kanıtla."""
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    hedef = minimum_clearance_hesapla(
        KomponentTipi.SMD_PASIF, KomponentTipi.SMD_PASIF, kucuk, kucuk
    )
    motor = IpcA610DfaMotoru()

    # Tam sınırında: boşluk == minimum -> PASS.
    bosluk = hedef.minimum_clearance_mm
    x_tam = kucuk.uzunluk_mm + bosluk  # iki kutu arası boşluk tam `bosluk` olacak şekilde
    tam = [
        YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0, 0),
        YerlesikKomponent("R2", KomponentTipi.SMD_PASIF, kucuk, x_tam, 0),
    ]
    tam_bulgu = motor.komponent_clearance_kontrolu(tam)

    # Biraz altında (0.01mm eksik) -> FAIL.
    az = [
        YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0, 0),
        YerlesikKomponent("R2", KomponentTipi.SMD_PASIF, kucuk, x_tam - 0.01, 0),
    ]
    az_bulgu = motor.komponent_clearance_kontrolu(az)

    return tam_bulgu.durum == BulguDurumu.PASS and az_bulgu.durum == BulguDurumu.FAIL


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. Class 3, Class 1'den DAHA SIKI (büyük) minimum clearance istemeli.
    kucuk = PaketBoyutlari(1.0, 0.5, 0.5)
    c1 = minimum_clearance_hesapla(KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kucuk, kucuk, MontajSinifi.CLASS_1)
    c3 = minimum_clearance_hesapla(KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kucuk, kucuk, MontajSinifi.CLASS_3)
    if not (c3.minimum_clearance_mm > c1.minimum_clearance_mm):
        hatalar.append("Class 3 clearance Class 1'den büyük değil (sınıf tanımına aykırı)")

    # 2. SMD-THT, SMD-SMD'den her zaman BÜYÜK olmalı (aynı sınıf, aynı boyut).
    smd_smd = minimum_clearance_hesapla(KomponentTipi.SMD_PASIF, KomponentTipi.SMD_PASIF, kucuk, kucuk)
    smd_tht = minimum_clearance_hesapla(KomponentTipi.SMD_PASIF, KomponentTipi.THT, kucuk, kucuk)
    if not (smd_tht.minimum_clearance_mm > smd_smd.minimum_clearance_mm):
        hatalar.append("SMD-THT clearance SMD-SMD'den büyük değil")

    # 3. Yükseklik farkı eşiği aşan iki SMD -> gölgeleme bayrağı VE ek boşluk.
    kisa = PaketBoyutlari(2.0, 1.0, 0.5)
    yuksek = PaketBoyutlari(2.0, 1.0, 5.0)  # fark 4.5mm > 2.0mm eşik
    golgeli = minimum_clearance_hesapla(KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kisa, yuksek)
    golgesiz = minimum_clearance_hesapla(KomponentTipi.SMD_IC, KomponentTipi.SMD_IC, kisa, kisa)
    if not golgeli.golgeleme_riski_mi:
        hatalar.append("yükseklik farkı eşiği aşıldığında gölgeleme_riski_mi=False (beklenen True)")
    if not (golgeli.minimum_clearance_mm > golgesiz.minimum_clearance_mm):
        hatalar.append("gölgeleme riski varken minimum clearance artmadı")

    # 4. Boş yerleşim listesi -> KAPSAM_YOK, sessizce PASS DEĞİL.
    motor = IpcA610DfaMotoru()
    bos_bulgu = motor.komponent_clearance_kontrolu([])
    if bos_bulgu.durum != BulguDurumu.KAPSAM_YOK or bos_bulgu.gecti_mi:
        hatalar.append("boş yerleşim PASS sayıldı (KAPSAM_YOK olmalıydı)")

    # 5. Tek komponent (çift üretilemez) -> yine KAPSAM_YOK (0 çift taranmış).
    tek = [YerlesikKomponent("R1", KomponentTipi.SMD_PASIF, kucuk, 0, 0)]
    tek_bulgu = motor.komponent_clearance_kontrolu(tek)
    if tek_bulgu.durum != BulguDurumu.KAPSAM_YOK:
        hatalar.append("tek komponentle (0 çift) KAPSAM_YOK dönmedi")

    # 6. Fault injection.
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: komponent clearance sınır testi boş olabilir")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sinif", choices=[s.value for s in MontajSinifi], default=MontajSinifi.CLASS_2.value)
    p.add_argument("--oztest", action="store_true")
    p.add_argument("--json", type=Path)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = _olustur_parser()
    args = parser.parse_args(argv)

    hatalar = oz_testleri_calistir()
    for h in hatalar:
        print(f"ÖZ-TEST FAIL: {h}", file=sys.stderr)
    if hatalar:
        return 1
    print("ÖZ-TEST PASS: tüm kontroller temiz.")

    if not args.oztest:
        sinif = MontajSinifi(args.sinif)
        ornek = PaketBoyutlari(2.0, 1.25, 0.6)
        satirlar = []
        tipler = list(KomponentTipi)
        for i, ta in enumerate(tipler):
            for tb in tipler[i:]:
                sonuc = minimum_clearance_hesapla(ta, tb, ornek, ornek, sinif)
                satirlar.append({
                    "a": ta.value, "b": tb.value,
                    "minimum_clearance_mm": sonuc.minimum_clearance_mm,
                })
        metin = json.dumps({"montaj_sinifi": sinif.value, "clearance_tablosu": satirlar},
                            indent=2, ensure_ascii=False, sort_keys=True)
        print(metin)
        if args.json:
            args.json.write_text(metin + "\n", encoding="utf-8")
            print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
