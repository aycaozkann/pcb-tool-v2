#!/usr/bin/env python3
"""
via_capi_hesaplayici.py
========================
Via delik çapı / pad çapı hesaplayıcı (IPC-2221 tabanlı).

NEDEN AYRI BİR MODÜL (`pcb_stackup_planner.py::iz_genisligi_hesapla_mm()`
YERİNE değil, ONUN ÜZERİNE EK BİR KATMAN):
-------------------------------------------------------------------------
`pcb_stackup_planner.py` içindeki `iz_genisligi_hesapla_mm()` fonksiyonu
IPC-2221'in akım→kesit-alanı (mil²) formülünü DÜZ bir bakır İZİNE (dikdörtgen
kesit: genişlik × kalınlık) uygular. Bir via'nın akım taşıyan kesiti ise
FARKLI bir geometri: içi genelde boş/harici lehim ile dolu bir delik,
akımı asıl taşıyan SİLİNDİRİK kaplama duvarıdır (Alan ≈ π × Delik_Çapı ×
Kaplama_Kalınlığı, ince-duvar yaklaşımı). Bu modül `iz_genisligi_hesapla_mm()`'i
KOPYALAMAZ/YENİDEN YAZMAZ — ondan (aynı k/b/c IPC-2221 sabitleriyle) gerekli
kesit alanını (mil²) alır, sonra o alanı via'nın silindirik geometrisine göre
Delik_Çapı için cebirsel olarak çözer. Böylece iki modül arasında sabit
(k=0.048 dış / 0.024 iç, b=0.44, c=0.725) TEK KAYNAKTAN gelir — burada
yeniden yazılıp sessizce sapma riski taşımaz.

Benzer şekilde `FABRIKA_PROFILLERI`/`FabrikaProfili` (min_delik_capi_mm,
min_yillik_halka_mm) `pcb_stackup_planner.py`'de ZATEN tanımlı — burada
hardcode EDİLMEZ, oradan import edilip okunur.

ÖNEMLİ — DÜRÜSTLÜK NOTU:
-------------------------------------------------------------------
Bu, IPC-2221'in basitleştirilmiş akım/kesit-alanı formülünün via geometrisine
UYARLANMASIDIR — via'ya özel resmi bir IPC-2221/IPC-2152 eğri seti (delik
doldurma malzemesi, kaplama kalınlık toleransı, termal via vs. sinyal via
ayrımı gibi ayrıntıları modelleyen) burada UYGULANMAMIŞTIR. Kritik/yüksek
akımlı via dizilimlerinde (güç via'ları, termal via'lar) bu sonucu sadece
bir İLK TAHMİN olarak kullan; üretim öncesi üreticinin resmi DFM aracıyla
veya bir alan çözücüyle doğrula.

MATEMATİKSEL NOT — bu modelde "gerekli_via_sayisi" HER ZAMAN 1'dir:
-------------------------------------------------------------------
`via_capi_oner()`'ın "hesaplanan çap < fabrika minimumu" dalındaki
`gerekli_via_sayisi = ceil(gerekli_alan / tek_via_alani)` hesabı BİLİNÇLİ
olarak GÖREV'in tanımladığı formülle BİREBİR uygulanmıştır — ama sabit
kaplama kalınlığında Alan = π × Çap × Kaplama_Kalınlığı ÇAPLA DOĞRUSAL bir
ilişkidir (D² değil). Bu yüzden hesaplanan çap zaten minimumdan küçükse,
gerekli alan da (aynı doğrusal ilişki nedeniyle) minimum-çaplı TEK bir
via'nın sağladığı alandan HER ZAMAN küçüktür — minimuma yükseltilmiş tek
via matematiksel olarak HER ZAMAN yeterlidir, `gerekli_via_sayisi` bu
dalda asla 1'i aşamaz (kanıt: `test_via_capi_hesaplayici.py::
test_senaryo_b_...`). Gerçek çok-via (N>1) stitching senaryosu bu
formülle ÜRETİLEMEZ; onun için ya via alanının çapla KARESEL büyüdüğü
farklı bir model ya da "çap minimumdan büyük ama tek via aspect-ratio/
termal sınırını AŞIYOR" gibi FARKLI bir tetik koşulu gerekir — ikisi de
GÖREV metninde İSTENMEYEN kapsam dışı bir genişletme olur. Bu modül
GÖREV'in tanımladığı formülü sessizce "düzeltmek" yerine bu matematiksel
sınırı burada ve testte AÇIKÇA belgeler.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pcb_stackup_planner import (
    FabrikaProfili,
    FABRIKA_PROFILLERI,
    iz_genisligi_hesapla_mm,
)

MM_PER_MIL = 0.0254
# 1 oz bakır ≈ 1.378 mil kalınlık (35 mikron) — pcb_stackup_planner ile aynı sabit.
MIL_PER_OZ = 1.378


def _mm_to_mil(mm: float) -> float:
    return mm / MM_PER_MIL


def _mil_to_mm(mil: float) -> float:
    return mil * MM_PER_MIL


def _gerekli_kesit_alani_mil2(
    akim_A: float,
    sicaklik_artisi_C: float,
    bakir_agirligi_oz: float,
) -> float:
    """`iz_genisligi_hesapla_mm()`'i ÇAĞIRARAK aynı IPC-2221 sabitleriyle
    gerekli kesit alanını (mil²) geri türetir — formülü KOPYALAMAZ.
    Via dış yüzeyde de akım taşıdığı için her zaman dış katman k-sabiti
    (`dis_katman_mi=True`) kullanılır.
    """
    if akim_A <= 0:
        raise ValueError(f"akim_A pozitif olmalı, alınan: {akim_A}")
    if sicaklik_artisi_C <= 0:
        raise ValueError(f"sicaklik_artisi_C pozitif olmalı, alınan: {sicaklik_artisi_C}")
    if bakir_agirligi_oz <= 0:
        raise ValueError(f"kaplama_kalinligi_oz pozitif olmalı, alınan: {bakir_agirligi_oz}")

    genislik_mm = iz_genisligi_hesapla_mm(
        akim_A, sicaklik_artisi_C, bakir_agirligi_oz, dis_katman_mi=True
    )
    # iz_genisligi_hesapla_mm: genislik_mil = alan_mil2 / kalinlik_mil
    # -> alan_mil2 = genislik_mil * kalinlik_mil (tersine çevirme)
    genislik_mil = _mm_to_mil(genislik_mm)
    kalinlik_mil = bakir_agirligi_oz * MIL_PER_OZ
    return genislik_mil * kalinlik_mil


def via_delik_capi_hesapla_mm(
    akim_A: float,
    sicaklik_artisi_C: float = 10.0,
    kaplama_kalinligi_oz: float = 1.0,
) -> float:
    """IPC-2221'den (pcb_stackup_planner.iz_genisligi_hesapla_mm ile AYNI
    k/b/c sabitlerini kullanarak) gerekli kesit alanını (mil²) hesaplar,
    sonra via'nın silindirik kaplama geometrisinden (Alan = pi * Delik_Capi
    * Kaplama_Kalinligi) Delik_Capi'yi cebirsel olarak çözer:

        Delik_Capi_mil = Alan_mil2 / (pi * Kaplama_Kalinligi_mil)

    Dış katman k-sabiti kullanılır (via, dış yüzeyde de akım taşır).
    """
    alan_mil2 = _gerekli_kesit_alani_mil2(akim_A, sicaklik_artisi_C, kaplama_kalinligi_oz)
    kaplama_kalinligi_mil = kaplama_kalinligi_oz * MIL_PER_OZ
    delik_capi_mil = alan_mil2 / (math.pi * kaplama_kalinligi_mil)
    return _mil_to_mm(delik_capi_mil)


def pad_capi_hesapla_mm(delik_capi_mm: float, min_yillik_halka_mm: float) -> float:
    """Pad_Capi = Delik_Capi + 2 * min_yillik_halka_mm (her iki tarafta
    minimum yıllık halka payı)."""
    if delik_capi_mm <= 0:
        raise ValueError(f"delik_capi_mm pozitif olmalı, alınan: {delik_capi_mm}")
    if min_yillik_halka_mm < 0:
        raise ValueError(f"min_yillik_halka_mm negatif olamaz, alınan: {min_yillik_halka_mm}")
    return delik_capi_mm + 2 * min_yillik_halka_mm


@dataclass(frozen=True)
class ViaCapiSonucu:
    akim_A: float
    sicaklik_artisi_C: float
    kaplama_kalinligi_oz: float
    fabrika_isim: str

    hesaplanan_delik_capi_mm: float
    hesaplanan_delik_capi_mil: float

    onerilen_delik_capi_mm: float  # üretilebilirlik tabanına yükseltilmiş
    onerilen_delik_capi_mil: float

    pad_capi_mm: float
    pad_capi_mil: float

    uretilebilirlik_sinirinin_altinda: bool
    stitching_gerekli: bool
    gerekli_via_sayisi: int = 1

    detay: str = ""


def via_capi_oner(
    akim_A: float,
    fabrika_profili: FabrikaProfili,
    sicaklik_artisi_C: float = 10.0,
    kaplama_kalinligi_oz: float = 1.0,
) -> ViaCapiSonucu:
    """Hesaplanan delik çapı `fabrika_profili.min_delik_capi_mm`'nin
    ALTINDAYSA: sonucu min_delik_capi_mm'e yükseltir VE kaç via'ya
    (via stitching) bölünmesi gerektiğini hesaplar (gerekli_via_sayisi =
    ceil(gerekli_alan / tek_via_alani)). Sonuç hem tekil hem stitching
    önerisini taşır, hangisi gerekliyse `stitching_gerekli` ile işaretler.
    """
    hesaplanan_mm = via_delik_capi_hesapla_mm(akim_A, sicaklik_artisi_C, kaplama_kalinligi_oz)
    altinda_mi = hesaplanan_mm < fabrika_profili.min_delik_capi_mm

    if not altinda_mi:
        onerilen_mm = hesaplanan_mm
        gerekli_via_sayisi = 1
        stitching_gerekli = False
        detay = (
            f"Hesaplanan delik çapı ({hesaplanan_mm:.4f}mm) {fabrika_profili.isim} "
            f"üretilebilirlik sınırının ({fabrika_profili.min_delik_capi_mm}mm) üstünde — "
            f"tekil via yeterli."
        )
    else:
        onerilen_mm = fabrika_profili.min_delik_capi_mm
        stitching_gerekli = True

        # Gerekli toplam kesit alanı (mil²) — akım için ihtiyaç duyulan alan,
        # değişmez (fiziksel gereksinim). Tek bir min-çaplı via'nın taşıyabildiği
        # alanla karşılaştırılıp kaç via gerektiği hesaplanır.
        gerekli_alan_mil2 = _gerekli_kesit_alani_mil2(akim_A, sicaklik_artisi_C, kaplama_kalinligi_oz)
        kaplama_kalinligi_mil = kaplama_kalinligi_oz * MIL_PER_OZ
        min_delik_capi_mil = _mm_to_mil(fabrika_profili.min_delik_capi_mm)
        tek_via_alani_mil2 = math.pi * min_delik_capi_mil * kaplama_kalinligi_mil

        gerekli_via_sayisi = max(1, math.ceil(gerekli_alan_mil2 / tek_via_alani_mil2))
        detay = (
            f"Hesaplanan delik çapı ({hesaplanan_mm:.4f}mm) {fabrika_profili.isim} "
            f"üretilebilirlik sınırının ({fabrika_profili.min_delik_capi_mm}mm) ALTINDA — "
            f"delik çapı üretilebilirlik tabanına yükseltildi VE gerekli akım "
            f"kapasitesini karşılamak için {gerekli_via_sayisi} adet via'ya "
            f"(stitching) bölünmesi önerilir."
        )

    pad_capi_mm = pad_capi_hesapla_mm(onerilen_mm, fabrika_profili.min_yillik_halka_mm)

    return ViaCapiSonucu(
        akim_A=akim_A,
        sicaklik_artisi_C=sicaklik_artisi_C,
        kaplama_kalinligi_oz=kaplama_kalinligi_oz,
        fabrika_isim=fabrika_profili.isim,
        hesaplanan_delik_capi_mm=hesaplanan_mm,
        hesaplanan_delik_capi_mil=_mm_to_mil(hesaplanan_mm),
        onerilen_delik_capi_mm=onerilen_mm,
        onerilen_delik_capi_mil=_mm_to_mil(onerilen_mm),
        pad_capi_mm=pad_capi_mm,
        pad_capi_mil=_mm_to_mil(pad_capi_mm),
        uretilebilirlik_sinirinin_altinda=altinda_mi,
        stitching_gerekli=stitching_gerekli,
        gerekli_via_sayisi=gerekli_via_sayisi,
        detay=detay,
    )


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="via-capi",
        description="IPC-2221 tabanlı via delik çapı / pad çapı hesaplayıcı.",
    )
    p.add_argument("--akim", type=float, required=True, help="via'dan geçmesi gereken akım, A")
    p.add_argument(
        "--fabrika",
        required=True,
        choices=sorted(FABRIKA_PROFILLERI.keys()),
        help="fabrika DFM profili (pcb_stackup_planner.FABRIKA_PROFILLERI)",
    )
    p.add_argument("--sicaklik-artisi", type=float, default=10.0, dest="sicaklik_artisi", help="izin verilen sıcaklık artışı, °C (varsayılan 10)")
    p.add_argument("--kaplama-oz", type=float, default=1.0, dest="kaplama_oz", help="via kaplama kalınlığı, oz (varsayılan 1.0 ≈ 1.378 mil)")
    p.add_argument("--json", type=Path, help="sonucu ayrıca bu dosyaya JSON olarak yaz")
    return p


def _sonucu_yazdir(sonuc: ViaCapiSonucu) -> str:
    veri = {
        "girdi": {
            "akim_A": sonuc.akim_A,
            "sicaklik_artisi_C": sonuc.sicaklik_artisi_C,
            "kaplama_kalinligi_oz": sonuc.kaplama_kalinligi_oz,
            "fabrika": sonuc.fabrika_isim,
        },
        "hesaplanan_delik_capi": {"mm": round(sonuc.hesaplanan_delik_capi_mm, 4), "mil": round(sonuc.hesaplanan_delik_capi_mil, 2)},
        "onerilen_delik_capi": {"mm": round(sonuc.onerilen_delik_capi_mm, 4), "mil": round(sonuc.onerilen_delik_capi_mil, 2)},
        "pad_capi": {"mm": round(sonuc.pad_capi_mm, 4), "mil": round(sonuc.pad_capi_mil, 2)},
        "uretilebilirlik_sinirinin_altinda": sonuc.uretilebilirlik_sinirinin_altinda,
        "stitching_gerekli": sonuc.stitching_gerekli,
        "gerekli_via_sayisi": sonuc.gerekli_via_sayisi,
        "detay": sonuc.detay,
    }
    return json.dumps(veri, indent=2, ensure_ascii=False, sort_keys=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = _olustur_parser()
    args = parser.parse_args(argv)

    fabrika_profili = FABRIKA_PROFILLERI.get(args.fabrika)
    if fabrika_profili is None:
        parser.error(
            f"tanımsız fabrika profili: {args.fabrika!r} "
            f"(geçerli seçenekler: {sorted(FABRIKA_PROFILLERI.keys())})"
        )
        return 2  # argparse.error zaten SystemExit atar, bu satır sadece netlik için

    try:
        sonuc = via_capi_oner(
            akim_A=args.akim,
            fabrika_profili=fabrika_profili,
            sicaklik_artisi_C=args.sicaklik_artisi,
            kaplama_kalinligi_oz=args.kaplama_oz,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    metin = _sonucu_yazdir(sonuc)
    print(metin)
    if args.json:
        args.json.write_text(metin + "\n", encoding="utf-8")
        print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
