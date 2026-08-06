#!/usr/bin/env python3
"""
ipc6012_dfm_motoru.py
========================
IPC-6012 (Rijit PCB Kalifikasyon ve Performans Şartnamesi) Class 2 / Class
3 üretilebilirlik sınıflarına göre bir tasarımın (KiCad'den okunan gerçek
ölçümlerin) limitleri karşılayıp karşılamadığını denetleyen motor.

NEDEN `bulgu_sozlesmesi.Bulgu` KULLANILIYOR (empedans_cozucu.py/
ipc2152_hesaplayici.py'den FARKLI olarak):
-------------------------------------------------------------------------
`empedans_cozucu.py` ve `ipc2152_hesaplayici.py` birer ÇÖZÜCÜdür — "hedefe
göre ne olmalı" sorusuna cevap verirler, kendi başlarına bir PASS/FAIL
üretmezler. Bu modül ise KULLANICININ KENDİ İSTEĞİYLE ("...PASS/FAIL olarak
döndürmeli") bir KONTROLCÜdür — bu proje genelinde her kontrolcü
(`gerber_dfm_gorsel_koprusu.py`, `mcad_carpisma_koprusu.py`,
`ecad_mcad_termal_kopru.py` ...) `bulgu_sozlesmesi.Bulgu` sözleşmesini
kullanır: `taranan == 0` iken durum ASLA PASS olamaz (`KAPSAM_YOK` zorunlu)
— "hiç ölçüm verilmedi" ile "ölçüm verildi, hepsi temiz" birbirine
KARIŞMAZ. Bu modül o disiplini takip eder.

NEDEN `FabrikaProfili`'NİN (pcb_stackup_planner.py) YERİNE GEÇMEZ:
-------------------------------------------------------------------------
`pcb_stackup_planner.py::FABRIKA_PROFILLERI`, BELİRLİ bir üreticinin
(JLCPCB, PCBWay...) GERÇEK süreç yeteneklerini tutar — "bu fabrika bunu
üretebilir mi" sorusuna cevap verir ve `TASLAK` değil, o dosyanın kendi
notuna göre "gerçek üretime geçmeden önce üreticinin GÜNCEL yetenek
sayfasından doğrulanmalı" bir veridir. Bu modül ise IPC-6012'nin SINIF
TANIMI limitlerini tutar — "bu tasarım Class 2 mi yoksa Class 3 mü
gerektiriyor" sorusuna cevap verir. İKİSİ FARKLI SORULARDIR: bir fabrika
Class 3 limitlerini üretebilecek YETENEKTE olabilir ama SİPARİŞ Class 2
olarak verilmiş olabilir (daha ucuz/hızlı) — bu modül tasarımı SINIF
tanımına göre değerlendirir, `FabrikaProfili` ise SEÇİLEN FABRİKANIN o
sınıfı gerçekten üretip üretemeyeceğini. İkisi BİRLİKTE kullanılmalı,
biri diğerinin yerine geçmez.

ÖNEMLİ — DÜRÜSTLÜK NOTU (limit sayılarının kaynağı):
-------------------------------------------------------------------------
Bu ortamda resmi, satın alınmış IPC-6012 PDF'ine ERİŞİM YOKTUR. Aşağıdaki
limitler, sektörde YAYGIN OLARAK ATIFTA BULUNULAN, birden fazla ikincil
kaynakta (fab yetenek sayfaları, PCB tasarım kılavuzları) tekrarlanan
TEMSİLİ değerlerdir — `pcb_stackup_planner.py::FABRIKA_PROFILLERI`'nin
kendi başlığındaki "Aşağıdaki sayılar TEMSİLİDİR" notuyla AYNI disiplin.
Solder mask barajı özel bir durum: bu, IPC-6012'nin KENDİSİNİN hard bir
sayı verdiği bir alan DEĞİLDİR (bu daha çok bir FABRİKA süreç yeteneğidir)
— bu yüzden burada varsayılan olarak projede ZATEN kabul edilmiş
`pcb_highspeed_escape.FAB_MIN_MASKE_BARAJI_MM` (0.20mm) kullanılır, kullanıcının
"genelde 0.1mm" varsayımı bilinçli olarak KULLANILMADI (0.1mm daha
agresif/gelişmiş bir fab yeteneğidir — `FABRIKA_PROFILLERI["JLCPCB_GELISMIS"]`
seviyesine yakın, standart bir fab için VARSAYILAN olarak GÜVENİLEMEZ).

Üretime geçmeden önce TÜM limitler, seçilen fabrikanın GÜNCEL IPC-6012
uygunluk beyanından (çoğu fab bunu "IPC Class 2/3 certified" diye
belgeler) çapraz doğrulanmalıdır.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret
from pcb_highspeed_escape import FAB_MIN_MASKE_BARAJI_MM


class Ipc6012Sinifi(str, Enum):
    CLASS_2 = "Class 2"
    CLASS_3 = "Class 3"


@dataclass(frozen=True)
class SinifLimitleri:
    """Bir IPC-6012 sınıfının bu modülün denetlediği üç limiti.

    `kaynak_notu` HER limit setinde ZORUNLU tutulur — hangi ikincil
    kaynaktan/varsayımdan geldiği rapor edilebilsin diye (dosya başlığındaki
    dürüstlük notunun kod karşılığı).
    """

    sinif: Ipc6012Sinifi
    min_annular_ring_mm: float
    min_solder_mask_baraji_mm: float
    maks_aspect_ratio: float
    kaynak_notu: str


# TEMSİLİ limitler — dosya başlığındaki dürüstlük notuna bakınız.
# Annular ring ve aspect ratio: yaygın olarak atıfta bulunulan Class 2/3
# karşılaştırma tabloları. Solder mask barajı: IPC-6012'nin kendisi hard
# bir sayı vermediği için projenin KENDİ kabul ettiği fab minimumu
# (`FAB_MIN_MASKE_BARAJI_MM`) her iki sınıfta da TABAN olarak kullanılır;
# Class 3 için daha sıkı bir üretim disiplini beklendiğinden aynı taban
# korunur (daha GEVŞEK bir Class-3 barajı YANLIŞ yönde bir hata olurdu).
SINIF_LIMITLERI: dict[Ipc6012Sinifi, SinifLimitleri] = {
    Ipc6012Sinifi.CLASS_2: SinifLimitleri(
        sinif=Ipc6012Sinifi.CLASS_2,
        min_annular_ring_mm=0.05,
        min_solder_mask_baraji_mm=FAB_MIN_MASKE_BARAJI_MM,
        maks_aspect_ratio=10.0,
        kaynak_notu=(
            "TEMSİLİ (ikincil kaynak) — annular ring/aspect ratio resmi IPC-6012 "
            "tablosundan TEK TEK doğrulanmalı; solder mask barajı "
            "pcb_highspeed_escape.FAB_MIN_MASKE_BARAJI_MM'den miras alındı."
        ),
    ),
    Ipc6012Sinifi.CLASS_3: SinifLimitleri(
        sinif=Ipc6012Sinifi.CLASS_3,
        min_annular_ring_mm=0.075,
        min_solder_mask_baraji_mm=FAB_MIN_MASKE_BARAJI_MM,
        maks_aspect_ratio=8.0,
        kaynak_notu=(
            "TEMSİLİ (ikincil kaynak) — Class 3 (yüksek güvenilirlik: havacılık/"
            "tıbbi/askeri) Class 2'den DAHA SIKI limitler ister (daha büyük "
            "annular ring, daha düşük aspect ratio); resmi IPC-6012 tablosundan "
            "TEK TEK doğrulanmalı."
        ),
    ),
}


@dataclass(frozen=True)
class ViaOlcumu:
    """KiCad'den okunan (veya elle girilen) TEK bir via'nın gerçek ölçümü.

    `delik_capi_mm`: sondaj (drill) çapı — plating ÖNCESİ nominal çap.
    `pad_capi_mm`: dış bakır pad çapı — annular ring bundan hesaplanır.
    """

    referans: str
    delik_capi_mm: float
    pad_capi_mm: float

    @property
    def annular_ring_mm(self) -> float:
        """Annular ring = (pad_çapı - delik_çapı) / 2 — tek taraflı halka
        genişliği (üretimde yaygın kullanılan tanım)."""
        return (self.pad_capi_mm - self.delik_capi_mm) / 2.0


@dataclass(frozen=True)
class MaskeKanaliOlcumu:
    """Bir solder mask barajının (iki açıklık arasındaki köprü) ölçümü —
    `gerber_dfm_gorsel_koprusu.py::en_yakin_flash_ciftleri()`'nden GERÇEK
    export edilmiş Gerber koordinatlarıyla üretilebilir, ya da elle girilir."""

    tanim: str
    baraj_genisligi_mm: float


@dataclass(frozen=True)
class DelikOlcumu:
    """Aspect ratio (kart kalınlığı / delik çapı) için tek bir delik ölçümü."""

    referans: str
    kart_kalinligi_mm: float
    delik_capi_mm: float

    @property
    def aspect_ratio(self) -> float:
        return self.kart_kalinligi_mm / self.delik_capi_mm


class Ipc6012DfmMotoru:
    """Verilen ölçüm kümelerini seçilen IPC-6012 sınıfının limitlerine göre
    denetler ve `Bulgu` sözleşmesiyle PASS/FAIL/KAPSAM_YOK raporlar.

    Kullanım:
        motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
        bulgular = motor.tum_kontrolleri_calistir(via_olcumleri, maske_olcumleri, delik_olcumleri)
        if any(b.durum == BulguDurumu.FAIL for b in bulgular):
            ...
    """

    def __init__(self, sinif: Ipc6012Sinifi, limitler: SinifLimitleri | None = None) -> None:
        self.sinif = sinif
        # `limitler` parametresi, kullanıcının KENDİ doğruladığı resmi
        # tablo değerleriyle bu modülün TEMSİLİ varsayılanlarını EZMESİNE
        # izin verir — bu, bir "gerçek veri gelince güncelle" kaçış yoludur
        # (`bom_lifecycle_koprusu.py`'nin `TedarikVerisi(kaynak="TBD")`'sini
        # gerçek API sonucuyla ezme deseniyle aynı ruh).
        self.limitler = limitler if limitler is not None else SINIF_LIMITLERI[sinif]

    def annular_ring_kontrolu(self, olcumler: Sequence[ViaOlcumu]) -> Bulgu:
        ihlaller = [
            {
                "referans": v.referans,
                "olculen_mm": round(v.annular_ring_mm, 4),
                "minimum_mm": self.limitler.min_annular_ring_mm,
                "eksik_mm": round(self.limitler.min_annular_ring_mm - v.annular_ring_mm, 4),
            }
            for v in olcumler
            if v.annular_ring_mm < self.limitler.min_annular_ring_mm
        ]
        return bulgu_uret(
            "ipc6012_annular_ring",
            taranan=len(olcumler),
            ihlaller=ihlaller,
            detay=f"{self.sinif.value}, min={self.limitler.min_annular_ring_mm}mm ({self.limitler.kaynak_notu})",
        )

    def solder_mask_baraji_kontrolu(self, olcumler: Sequence[MaskeKanaliOlcumu]) -> Bulgu:
        ihlaller = [
            {
                "tanim": m.tanim,
                "olculen_mm": m.baraj_genisligi_mm,
                "minimum_mm": self.limitler.min_solder_mask_baraji_mm,
            }
            for m in olcumler
            if m.baraj_genisligi_mm < self.limitler.min_solder_mask_baraji_mm
        ]
        return bulgu_uret(
            "ipc6012_solder_mask_baraji",
            taranan=len(olcumler),
            ihlaller=ihlaller,
            detay=f"{self.sinif.value}, min={self.limitler.min_solder_mask_baraji_mm}mm "
                  "(kaynak: pcb_highspeed_escape.FAB_MIN_MASKE_BARAJI_MM, IPC-6012'nin kendisi değil)",
        )

    def aspect_ratio_kontrolu(self, olcumler: Sequence[DelikOlcumu]) -> Bulgu:
        ihlaller = [
            {
                "referans": d.referans,
                "olculen_oran": round(d.aspect_ratio, 3),
                "maksimum_oran": self.limitler.maks_aspect_ratio,
                "kart_kalinligi_mm": d.kart_kalinligi_mm,
                "delik_capi_mm": d.delik_capi_mm,
            }
            for d in olcumler
            if d.aspect_ratio > self.limitler.maks_aspect_ratio
        ]
        return bulgu_uret(
            "ipc6012_aspect_ratio",
            taranan=len(olcumler),
            ihlaller=ihlaller,
            detay=f"{self.sinif.value}, maks={self.limitler.maks_aspect_ratio}:1 ({self.limitler.kaynak_notu})",
        )

    def tum_kontrolleri_calistir(
        self,
        via_olcumleri: Sequence[ViaOlcumu] = (),
        maske_olcumleri: Sequence[MaskeKanaliOlcumu] = (),
        delik_olcumleri: Sequence[DelikOlcumu] = (),
    ) -> list[Bulgu]:
        """Üç kontrolü de çalıştırır. Boş verilen bir ölçüm kümesi o
        kontrolün `KAPSAM_YOK` dönmesine yol açar — sessizce PASS
        SAYILMAZ (`bulgu_sozlesmesi.py`'nin temel garantisi)."""
        return [
            self.annular_ring_kontrolu(via_olcumleri),
            self.solder_mask_baraji_kontrolu(maske_olcumleri),
            self.aspect_ratio_kontrolu(delik_olcumleri),
        ]

    def genel_sonuc(self, bulgular: Sequence[Bulgu]) -> str:
        """Üç kontrolün BİRLEŞİK PASS/FAIL/NEEDS_HUMAN kararı.

        Kullanıcının Görev 3'teki isteği ("PASS/FAIL olarak döndürmeli")
        burada tek bir string'e indirgenir; ama `KAPSAM_YOK` görmezden
        gelinip sessizce PASS SAYILMAZ — en az bir kontrol hiç veri
        almadıysa sonuç `NEEDS_HUMAN`dır (bu proje genelinde `KAPSAM_YOK`
        release kapısını kapatır — bkz. `uretim_ciktilari_cli.py`'deki
        aynı disiplin)."""
        if any(b.durum == BulguDurumu.FAIL for b in bulgular):
            return "FAIL"
        if any(b.durum == BulguDurumu.KAPSAM_YOK for b in bulgular):
            return "NEEDS_HUMAN"
        return "PASS"


def kicad_via_verisinden_olcum_uret(
    via_kayitlari: Sequence[dict[str, float]],
) -> list[ViaOlcumu]:
    """`pcbnew_koprusu.py`/`.kicad_pcb`'den okunan ham via verisini (
    `{"ref": str, "delik_mm": float, "pad_mm": float}` sözlük listesi)
    `ViaOlcumu` listesine çevirir.

    KiCad'in kendi veri modelinden BAĞIMSIZ tutuldu (bu ortamda `pcbnew`
    kurulu değil, bkz. `pcbnew_koprusu.py` başlığı) — çağıran taraf
    `pcbnew` API'sinden (`pad.GetDrillSize()`/`pad.GetSize()`) bu basit
    sözlük formatına kendi dönüştürmesini yapar; bu fonksiyon SADECE o
    ara formatı tip-güvenli dataclass'a çevirir.
    """
    return [
        ViaOlcumu(
            referans=str(kayit.get("ref", "?")),
            delik_capi_mm=float(kayit["delik_mm"]),
            pad_capi_mm=float(kayit["pad_mm"]),
        )
        for kayit in via_kayitlari
    ]


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: annular ring'i limitin BİRAZ altına koyup kontrolün
    GERÇEKTEN FAIL verdiğini kanıtla — sınır (boundary) değerinde test,
    ">=' yerine yanlışlıkla '>' yazılmış olsaydı bunu YAKALARDI."""
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    limit = motor.limitler.min_annular_ring_mm
    tam_sinirinda = ViaOlcumu("V1", delik_capi_mm=0.3, pad_capi_mm=0.3 + 2 * limit)
    biraz_altinda = ViaOlcumu(
        "V2", delik_capi_mm=0.3, pad_capi_mm=0.3 + 2 * (limit - 0.001)
    )
    tam_sonuc = motor.annular_ring_kontrolu([tam_sinirinda])
    az_sonuc = motor.annular_ring_kontrolu([biraz_altinda])
    return tam_sonuc.durum == BulguDurumu.PASS and az_sonuc.durum == BulguDurumu.FAIL


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. Class 3, Class 2'den DAHA SIKI olmalı (daha büyük annular ring,
    #    daha düşük aspect ratio) — sınıf tanımının temel özelliği.
    c2 = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_2]
    c3 = SINIF_LIMITLERI[Ipc6012Sinifi.CLASS_3]
    if not (c3.min_annular_ring_mm >= c2.min_annular_ring_mm):
        hatalar.append("Class 3 annular ring Class 2'den küçük (sınıf tanımına aykırı)")
    if not (c3.maks_aspect_ratio <= c2.maks_aspect_ratio):
        hatalar.append("Class 3 aspect ratio Class 2'den büyük (sınıf tanımına aykırı)")

    # 2. Boş ölçüm kümesi KAPSAM_YOK olmalı, sessizce PASS OLMAMALI.
    motor = Ipc6012DfmMotoru(Ipc6012Sinifi.CLASS_2)
    bos_bulgu = motor.annular_ring_kontrolu([])
    if bos_bulgu.durum != BulguDurumu.KAPSAM_YOK or bos_bulgu.gecti_mi:
        hatalar.append("boş ölçüm kümesi PASS sayıldı (KAPSAM_YOK olmalıydı)")

    # 3. genel_sonuc() KAPSAM_YOK'u NEEDS_HUMAN'a çevirmeli, PASS'e DEĞİL.
    bulgular = motor.tum_kontrolleri_calistir()  # üçü de boş -> hepsi KAPSAM_YOK
    if motor.genel_sonuc(bulgular) != "NEEDS_HUMAN":
        hatalar.append("tüm ölçümler boşken genel_sonuc PASS/FAIL döndü (NEEDS_HUMAN olmalıydı)")

    # 4. Gerçek bir ihlal FAIL üretmeli ve genel_sonuc bunu yansıtmalı.
    kotu_via = ViaOlcumu("V_KOTU", delik_capi_mm=0.3, pad_capi_mm=0.32)  # annular=0.01mm < 0.05mm
    bulgular_fail = motor.tum_kontrolleri_calistir(via_olcumleri=[kotu_via])
    if motor.genel_sonuc(bulgular_fail) != "FAIL":
        hatalar.append("bilinen bir ihlal FAIL olarak raporlanmadı")

    # 5. Fault injection.
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: annular ring sınır testi boş olabilir")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sinif", choices=[s.value for s in Ipc6012Sinifi], default=Ipc6012Sinifi.CLASS_2.value)
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
        sinif = Ipc6012Sinifi(args.sinif)
        limitler = SINIF_LIMITLERI[sinif]
        veri = limitler.__dict__ | {"sinif": limitler.sinif.value}
        metin = json.dumps(veri, indent=2, ensure_ascii=False, sort_keys=True)
        print(metin)
        if args.json:
            args.json.write_text(metin + "\n", encoding="utf-8")
            print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
