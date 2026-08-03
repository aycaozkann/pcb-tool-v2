#!/usr/bin/env python3
"""
ipc2152_hesaplayici.py
========================
IPC-2152 (İletken Akım Taşıma Kapasitesi) standardına yönelik minimum iz
genişliği hesaplayıcısı — `empedans_cozucu.py`'nin (IPC-2141 empedans
çözücüsü) yapısal ikizi: aynı türde bir kapalı-form yaklaşık model, aynı
`_pozitif_olmali` girdi denetimi, aynı öz-test + fault-injection disiplini.

NEDEN AYRI BİR MODÜL (pcb_stackup_planner.py'deki mevcut fonksiyonun
YERİNE değil, ONUN ÜZERİNE):
-------------------------------------------------------------------------
`pcb_stackup_planner.py::iz_genisligi_hesapla_mm()` ZATEN var ve KENDİ
docstring'inde şunu açıkça söylüyor: *"Bu, tam IPC-2152 grafik/tablo
setinin YERİNE DEĞİL, onun yaygın kullanılan basitleştirilmiş öncülü olan
IPC-2221 ampirik formülünün uygulamasıdır."* Yani bu modülün ne YAPMASI
GEREKTİĞİ zaten kodda yazılıydı, sadece kod YOKTU. Bu dosya o boşluğu
dolduruyor — ama TEK KAYNAK GERÇEKLİK ilkesine uyarak (`ecad_mcad_termal_kopru.py`
ile aynı desen: "ÇAĞIRIR/genişletir, YENİDEN YAZMAZ"), temel kapalı-form
formülü YENİDEN TÜRETMEK yerine `pcb_stackup_planner.iz_genisligi_hesapla_mm()`'i
İTHAL EDİP ÇAĞIRIR — aynı sabitlerin (k=0.048/0.024, b=0.44, c=0.725) iki
ayrı dosyada BİRBİRİNDEN SESSİZCE SAPMASI riskini yapısal olarak ortadan
kaldırır.

ÖNEMLİ — DÜRÜSTLÜK NOTU (bu modülün NE OLMADIĞI):
----------------------------------------------------
Gerçek IPC-2152 (2009), IPC-2221'in tek kapalı-form denklemi YERİNE, 2D ısıl
modelleme ile üretilmiş bir EĞRİ AİLESİ (board kalınlığı, komşu bakır
dökümü, hava akışı, iç/dış katman farkları dahil) kullanır — bu eğriler
resmi standardın kendisinde grafik/tablo olarak yayınlanır ve bu ortamda
(satın alınmış IPC-2152 PDF'i olmadan) SAYISALLAŞTIRILAMAZ. Bu modül o
eğri ailesinin YERİNE GEÇMEZ; bunun yerine:
  1. Doğrulanmış IPC-2221 kapalı-form formülünü ÇEKİRDEK model olarak
     kullanır (yukarıdaki tek-kaynak gerekçesi),
  2. Üzerine, birden çok bağımsız ikincil kaynakta (üretici app-notları,
     PCB hesaplayıcı araçlarının belgeleri) YAYGIN OLARAK atıfta bulunulan
     bir gözlemi uygular: IPC-2152 eğrileri, İÇ katmanlarda IPC-2221'in
     basit k-yarılama varsayımından (k_ic = k_dis/2) DAHA FAZLA pay
     (daha geniş iz) gerektirir — bu modül bunu `ic_katman_derating_katsayisi`
     ile açık, AYARLANABİLİR bir parametre olarak uygular (varsayılan 1.25 —
     muhafazakar bir başlangıç noktası, KESİN bir IPC-2152 sabiti DEĞİL).

SONUÇ: Bu modülün çıktısı bir İLK TAHMİN/tarama aracıdır. Akım-kritik veya
güvenlik-kritik (ör. UL/IEC uyumluluğu gereken) tasarımlarda, üretim
imzasından ÖNCE sonuç mutlaka ŞUNLARDAN biriyle çapraz doğrulanmalı:
  - Saturn PCB Toolkit (yaygın kullanılan, IPC-2152 uyumlu ücretsiz
    hesaplayıcı — bu ortamda kurulu/erişilebilir DEĞİL, SENİN makinende
    çalıştırılmalı),
  - satın alınmış IPC-2152 standardının ilgili eğrisi,
  - gerçek bir termal ölçüm/prototip testi.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from pcb_stackup_planner import iz_genisligi_hesapla_mm

# Yaygın ikincil kaynaklarda (üretici app-notları, PCB hesaplayıcı
# belgeleri) atıfta bulunulan, IPC-2152'nin iç katmanlarda IPC-2221'in
# basit k-yarılama varsayımından DAHA FAZLA pay istediği gözlemini
# yansıtan MUHAFAZAKAR bir başlangıç katsayısı. KESİN bir IPC-2152 sabiti
# OLARAK SUNULMAZ — bkz. dosya başlığındaki dürüstlük notu.
VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI = 1.25


class KatmanTipi(str, Enum):
    IC = "internal"
    DIS = "external"


@dataclass(frozen=True)
class Ipc2152Sonucu:
    """Bir `ipc2152_min_iz_genisligi_mm()` çağrısının tam sonucu.

    `ic_katman_derating_katsayisi` alanı SONUCUN İÇİNE gömülüdür ki
    (sadece parametre olarak verilip unutulmasın) raporlarda/`.kicad_dru`
    yorumlarında hangi katsayının kullanıldığı HER ZAMAN görünür kalsın.
    """

    genislik_mm: float
    kesit_alani_mil2: float
    katman_tipi: KatmanTipi
    akim_A: float
    delta_t_C: float
    bakir_kalinligi_oz: float
    ic_katman_derating_katsayisi: float
    model: str = "IPC-2221 kapalı-form çekirdek + IPC-2152-bilgilendirilmiş iç-katman derating"


def ipc2152_min_iz_genisligi_mm(
    akim_A: float,
    delta_t_C: float,
    katman_tipi: KatmanTipi,
    bakir_kalinligi_oz: float = 1.0,
    ic_katman_derating_katsayisi: float = VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI,
) -> Ipc2152Sonucu:
    """Verilen akım/sıcaklık artışı/katman tipi/bakır kalınlığı için
    minimum iz genişliğini (mm) hesaplar.

    Girdi doğrulaması: `akim_A` ve `bakir_kalinligi_oz` pozitif olmalı,
    `delta_t_C` pozitif olmalı — aksi halde `ValueError` (sessizce 0 veya
    negatif bir genişlik ÜRETİLMEZ, `iz_genisligi_hesapla_mm()`'in
    `akim_A <= 0 -> 0.0` kısayolunun aksine burada BİLİNÇLİ OLARAK daha
    sıkı davranılır çünkü bu fonksiyonun çıktısı doğrudan bir DRC kuralına
    beslenecek — sıfır genişlikli bir kural sessizce "her şeyi kabul et"
    anlamına gelir).
    """
    if akim_A <= 0:
        raise ValueError(f"akim_A pozitif olmalı, gelen: {akim_A!r}")
    if delta_t_C <= 0:
        raise ValueError(f"delta_t_C pozitif olmalı, gelen: {delta_t_C!r}")
    if bakir_kalinligi_oz <= 0:
        raise ValueError(f"bakir_kalinligi_oz pozitif olmalı, gelen: {bakir_kalinligi_oz!r}")
    if ic_katman_derating_katsayisi < 1.0:
        raise ValueError(
            f"ic_katman_derating_katsayisi >= 1.0 olmalı (iç katman ASLA dış "
            f"katmandan daha az pay istemez), gelen: {ic_katman_derating_katsayisi!r}"
        )

    dis_katman_mi = katman_tipi == KatmanTipi.DIS
    temel_genislik_mm = iz_genisligi_hesapla_mm(
        akim_A, delta_t_C, bakir_kalinligi_oz, dis_katman_mi=dis_katman_mi
    )

    uygulanan_katsayi = 1.0 if dis_katman_mi else ic_katman_derating_katsayisi
    genislik_mm = temel_genislik_mm * uygulanan_katsayi

    # Kesit alanını da rapor için geri hesapla (mil^2, IPC formülünün doğal birimi).
    kalinlik_mil = bakir_kalinligi_oz * 1.378
    kesit_alani_mil2 = (genislik_mm / 0.0254) * kalinlik_mil

    return Ipc2152Sonucu(
        genislik_mm=round(genislik_mm, 4),
        kesit_alani_mil2=round(kesit_alani_mil2, 2),
        katman_tipi=katman_tipi,
        akim_A=akim_A,
        delta_t_C=delta_t_C,
        bakir_kalinligi_oz=bakir_kalinligi_oz,
        ic_katman_derating_katsayisi=uygulanan_katsayi,
    )


def ic_dis_karsilastirmasi_uret(
    akim_A: float,
    delta_t_C: float,
    bakir_kalinligi_oz: float = 1.0,
    ic_katman_derating_katsayisi: float = VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI,
) -> dict[str, Ipc2152Sonucu]:
    """Aynı akım/sıcaklık için hem iç hem dış katman sonucunu tek seferde
    döner — `DOCS/03_Design_Rules.md` tablosunu doldururken veya
    `.kicad_dru` için iki net class kuralı üretirken kullanışlı."""
    return {
        "external": ipc2152_min_iz_genisligi_mm(
            akim_A, delta_t_C, KatmanTipi.DIS, bakir_kalinligi_oz, ic_katman_derating_katsayisi
        ),
        "internal": ipc2152_min_iz_genisligi_mm(
            akim_A, delta_t_C, KatmanTipi.IC, bakir_kalinligi_oz, ic_katman_derating_katsayisi
        ),
    }


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION (empedans_cozucu.py ile aynı disiplin)
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: derating katsayısını bilerek 1'in ALTINA
    (0.5) çekersek, iç katman sonucu DIŞ katmandan DAHA DAR çıkmalı —
    bu FİZİKSEL OLARAK YANLIŞTIR (iç katman ısıyı daha zor atar, her
    zaman DAHA GENİŞ veya eşit iz ister). `ValueError` beklenir; eğer
    fonksiyon bunu SESSİZCE kabul edip yanlış bir sonuç üretirse, girdi
    doğrulaması boştur."""
    try:
        ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.IC, ic_katman_derating_katsayisi=0.5)
    except ValueError:
        return True
    return False


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. Aynı akım/sıcaklıkta iç katman DIŞ katmandan asla daha dar olamaz.
    sonuclar = ic_dis_karsilastirmasi_uret(10.0, 10.0)
    if sonuclar["internal"].genislik_mm < sonuclar["external"].genislik_mm:
        hatalar.append(
            f"iç katman ({sonuclar['internal'].genislik_mm}mm) dış katmandan "
            f"({sonuclar['external'].genislik_mm}mm) daha dar çıktı — fiziksel olarak yanlış"
        )

    # 2. Akım arttıkça genişlik monoton artmalı.
    dusuk = ipc2152_min_iz_genisligi_mm(1.0, 10.0, KatmanTipi.DIS)
    yuksek = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS)
    if not (yuksek.genislik_mm > dusuk.genislik_mm):
        hatalar.append(f"akım arttıkça genişlik artmadı: {dusuk.genislik_mm} -> {yuksek.genislik_mm}")

    # 3. Daha kalın bakır (oz) aynı akım için DAHA DAR iz gerektirmeli
    #    (kesit alanı sabit -> kalınlık artınca genişlik azalır).
    ince = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS, bakir_kalinligi_oz=1.0)
    kalin = ipc2152_min_iz_genisligi_mm(5.0, 10.0, KatmanTipi.DIS, bakir_kalinligi_oz=2.0)
    if not (kalin.genislik_mm < ince.genislik_mm):
        hatalar.append(f"bakır kalınlığı arttıkça genişlik azalmadı: {ince.genislik_mm} -> {kalin.genislik_mm}")

    # 4. Geçersiz girdiler açıkça reddedilmeli (sessiz 0 üretilmemeli).
    for kwargs in ({"akim_A": 0}, {"akim_A": -1}, {"delta_t_C": 0}, {"bakir_kalinligi_oz": -1}):
        varsayilan = {"akim_A": 1.0, "delta_t_C": 10.0, "katman_tipi": KatmanTipi.DIS, "bakir_kalinligi_oz": 1.0}
        varsayilan.update(kwargs)
        try:
            ipc2152_min_iz_genisligi_mm(**varsayilan)
        except ValueError:
            pass
        else:
            hatalar.append(f"geçersiz girdi ({kwargs}) reddedilmedi")

    # 5. Fault injection.
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: iç/dış katman karşılaştırması boş olabilir")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--akim", type=float, help="akım, A")
    p.add_argument("--delta-t", type=float, default=10.0, help="izin verilen sıcaklık artışı, °C")
    p.add_argument("--bakir-oz", type=float, default=1.0, help="bakır ağırlığı, oz")
    p.add_argument(
        "--derating", type=float, default=VARSAYILAN_IC_KATMAN_DERATING_KATSAYISI,
        help="iç katman derating katsayısı (>= 1.0)",
    )
    p.add_argument("--json", type=Path)
    p.add_argument("--oztest", action="store_true")
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

    if args.oztest or args.akim is None:
        if args.akim is None and not args.oztest:
            print("--akim verilmedi; öz-testler tamamlandı.")
        return 0

    try:
        sonuclar = ic_dis_karsilastirmasi_uret(
            args.akim, args.delta_t, args.bakir_oz, args.derating
        )
    except ValueError as exc:
        parser.error(str(exc))

    rapor = {k: v.__dict__ | {"katman_tipi": v.katman_tipi.value} for k, v in sonuclar.items()}
    metin = json.dumps(rapor, indent=2, ensure_ascii=False, sort_keys=True)
    print(metin)
    if args.json:
        args.json.write_text(metin + "\n", encoding="utf-8")
        print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
