#!/usr/bin/env python3
"""
emi_emc_kural_motoru.py
==========================
Yüksek frekanslı (High-Speed) sinyallerin elektromanyetik gürültü
yaymasını (EMI) ve almasını (EMC) engellemek için üç TEMEL, sektörde
yaygın atıfta bulunulan kuralı hesaplayan + `bulgu_sozlesmesi.Bulgu`
sözleşmesiyle GERÇEK ölçümü denetleyen motor (FCC Part 15 / CISPR 32
pre-compliance hazırlığı — bu modülün kendisi bir uyumluluk testi/lab
ölçümü DEĞİLDİR, bkz. aşağıdaki dürüstlük notu).

ÜÇ KURAL (kullanıcının Görev 2 isteğiyle birebir):
-------------------------------------------------------------------------
  1. **3W Kuralı (crosstalk önleme)**: iki yüksek hızlı sinyal yolu
     arasındaki MERKEZ-MERKEZ mesafe, iz genişliğinin en az 3 katı
     olmalıdır (`w_3w()`). Bu, komşu izdeki manyetik akı kuplajının
     ~%70 azaltıldığı, Henry Ott'un "Noise Reduction Techniques in
     Electronic Systems" kitabından ve pek çok fab/EMC uygulama notundan
     yaygın olarak atıfta bulunulan bir kısayoldur — 3W merkez-merkez
     mesafesi kenar-kenar boşluğun 2W olduğu anlamına gelir (mesafe - iz
     genişliği = 2W); bu modül HER İKİ tanımı da (merkez-merkez VE
     kenar-kenar) döndürür ki çağıran taraf hangisini kullandığını
     KARIŞTIRMASIN (bu, sektörde en sık yapılan "3W mü 2W mü" hatasıdır).
  2. **20H Kuralı (kenar ışıması/fringing önleme)**: VCC/güç düzlemi,
     GND düzlemine göre kart kenarından İÇERDE olmalıdır — çekilme
     (setback) mesafesi, iki düzlem arasındaki dielektrik kalınlığının
     EN AZ 20 katı olmalıdır (`h_20h_setback_mm()`). %70 alan azaltımı
     için 20H, %98 için ~100H gerektiği literatürde (Mark Montrose)
     ayrıca not edilir — bu modül VARSAYILAN olarak muhafazakâr 20H'yi
     kullanır, `carpan` parametresiyle 100H'ye çıkarılabilir.
  3. **Via-Stitching (kenar dikişi) aralığı**: kenar GND via'larının
     maksimum aralığı `dalga_boyu / 20` formülüyle hesaplanır
     (`stitching_max_araligi_mm()`). BU FORMÜL `pcbnew_koprusu.py::
     _lambda_20_hedef_mm()` İLE FİZİKSEL OLARAK AYNIDIR — kod
     TEKRARLANMADI, ışık hızı sabiti (`C_MPS`) oradan İTHAL EDİLDİ (tek
     kaynak gerçeklik). Fark: `pcbnew_koprusu.py`'deki fonksiyon GERÇEK
     bir `.kicad_pcb`'yi `pcbnew` ile açıp via konumlarını ÖLÇER (bu
     modülde YOK, `pcbnew` bağımlılığı yok); bu modüldeki
     `via_araligi_kontrolu()` ise ÖNCEDEN ölçülmüş/dışarıdan verilen
     aralık listesini (örn. `pcbnew_koprusu.py`'nin ürettiği ham veri)
     hedefe karşı denetler — ikisi BİRLİKTE kullanılmalı, biri diğerinin
     yerine geçmez (`ipc_a_610_dfa_motoru.py`'nin `ipc7351_footprint.py`
     ile ilişkisiyle AYNI desen).

ÖNEMLİ — DÜRÜSTLÜK NOTU:
-------------------------------------------------------------------------
3W/20H/λ-20 kuralları FCC/CISPR'ın KENDİSİNİN yayınladığı sabit sayılar
DEĞİLDİR — bunlar EMC mühendisliği pratiğinde YAYGIN kabul görmüş,
alan/kuplaj azaltımını hedefleyen TASARIM SEZGİSELLERİDİR (heuristik).
Gerçek FCC Part 15 / CISPR 32 uyumluluğu yalnızca akredite bir EMC lab
ölçümüyle (`SKILL-dogrulama-matrisi.md`'nin **D seviyesi**, bu projedeki
`emi-emc` skill'inin de kabul ettiği ayrım) kanıtlanabilir — bu modül bir
**A seviyesi** (dosyadan/girdiden ölçülebilir) ön-hazırlık katmanıdır,
lab testinin YERİNE GEÇMEZ.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret
from pcbnew_koprusu import C_MPS

# ------------------------------------------------------------------
# 1) 3W KURALI — crosstalk önleme
# ------------------------------------------------------------------

VARSAYILAN_3W_CARPANI = 3.0


@dataclass(frozen=True)
class UcWSonucu:
    iz_genisligi_mm: float
    carpan: float
    minimum_merkez_merkez_mm: float
    minimum_kenar_kenar_mm: float
    kaynak_notu: str = (
        "3W kuralı (Henry Ott / yaygın EMC uygulama notu, TEMSİLİ sezgisel) — "
        "FCC/CISPR'ın kendisinin yayınladığı bir tablo değeri DEĞİLDİR."
    )


def w_3w(iz_genisligi_mm: float, carpan: float = VARSAYILAN_3W_CARPANI) -> UcWSonucu:
    """3W kuralına göre minimum merkez-merkez VE kenar-kenar mesafeyi hesaplar.

    `minimum_kenar_kenar_mm = minimum_merkez_merkez_mm - iz_genisligi_mm`
    (eşit genişlikli iki iz varsayımıyla) — FARKLI genişlikli iki iz için
    `w_3w_karma_genislik()` kullanılmalı.
    """
    if iz_genisligi_mm <= 0:
        raise ValueError(f"w_3w: iz_genisligi_mm pozitif olmalı, gelen: {iz_genisligi_mm!r}")
    if carpan < 1.0:
        raise ValueError(f"w_3w: carpan >= 1.0 olmalı (1.0 altı crosstalk'ı KÖTÜLEŞTİRİR), gelen: {carpan!r}")
    merkez_merkez = round(iz_genisligi_mm * carpan, 4)
    kenar_kenar = round(merkez_merkez - iz_genisligi_mm, 4)
    return UcWSonucu(
        iz_genisligi_mm=iz_genisligi_mm,
        carpan=carpan,
        minimum_merkez_merkez_mm=merkez_merkez,
        minimum_kenar_kenar_mm=kenar_kenar,
    )


def w_3w_karma_genislik(
    iz_a_genislik_mm: float, iz_b_genislik_mm: float, carpan: float = VARSAYILAN_3W_CARPANI
) -> UcWSonucu:
    """Farklı genişlikte iki iz için 3W hedefini ORTALAMA genişlik üzerinden
    hesaplar (yaygın pratik yaklaşım — her iki izin de kendi genişliğinin
    3 katını istemesi ARASINDAKİ en muhafazakâr/güvenli nokta)."""
    ortalama = (iz_a_genislik_mm + iz_b_genislik_mm) / 2.0
    sonuc = w_3w(ortalama, carpan)
    kenar_kenar = round(sonuc.minimum_merkez_merkez_mm - (iz_a_genislik_mm + iz_b_genislik_mm) / 2.0, 4)
    return UcWSonucu(
        iz_genisligi_mm=ortalama,
        carpan=carpan,
        minimum_merkez_merkez_mm=sonuc.minimum_merkez_merkez_mm,
        minimum_kenar_kenar_mm=kenar_kenar,
        kaynak_notu=sonuc.kaynak_notu + f" (karma genişlik: A={iz_a_genislik_mm}mm, B={iz_b_genislik_mm}mm, ortalama kullanıldı)",
    )


@dataclass(frozen=True)
class UcWOlcumu:
    iz_a_adi: str
    iz_b_adi: str
    iz_a_genislik_mm: float
    iz_b_genislik_mm: float
    merkez_merkez_mesafe_mm: float


def uc_w_kontrolu(
    olcumler: Sequence[UcWOlcumu], carpan: float = VARSAYILAN_3W_CARPANI
) -> Bulgu:
    """Gerçek (veya elle girilen) iz çiftlerini 3W hedefine karşı denetler."""
    ihlaller = []
    for o in olcumler:
        hedef = w_3w_karma_genislik(o.iz_a_genislik_mm, o.iz_b_genislik_mm, carpan)
        if o.merkez_merkez_mesafe_mm < hedef.minimum_merkez_merkez_mm:
            ihlaller.append({
                "a": o.iz_a_adi, "b": o.iz_b_adi,
                "olculen_merkez_merkez_mm": round(o.merkez_merkez_mesafe_mm, 4),
                "minimum_merkez_merkez_mm": hedef.minimum_merkez_merkez_mm,
                "eksik_mm": round(hedef.minimum_merkez_merkez_mm - o.merkez_merkez_mesafe_mm, 4),
            })
    return bulgu_uret(
        "emi_3w_crosstalk",
        taranan=len(olcumler),
        ihlaller=ihlaller,
        detay=f"3W kuralı (çarpan={carpan}), merkez-merkez mesafe denetlendi.",
    )


# ------------------------------------------------------------------
# 2) 20H KURALI — kenar ışıması/fringing önleme
# ------------------------------------------------------------------

VARSAYILAN_20H_CARPANI = 20.0


@dataclass(frozen=True)
class YirmiHSonucu:
    dielektrik_kalinligi_mm: float
    carpan: float
    minimum_setback_mm: float
    kaynak_notu: str = (
        "20H kuralı (Mark Montrose, 'EMC and the Printed Circuit Board') — "
        "%70 alan azaltımı hedefler; %98 için ~100H önerilir (carpan=100 ile)."
    )


def h_20h_setback_mm(
    dielektrik_kalinligi_mm: float, carpan: float = VARSAYILAN_20H_CARPANI
) -> YirmiHSonucu:
    """Güç düzleminin GND düzlemine göre kart kenarından ne kadar İÇERİDE
    olması gerektiğini (setback) hesaplar."""
    if dielektrik_kalinligi_mm <= 0:
        raise ValueError(
            f"h_20h_setback_mm: dielektrik_kalinligi_mm pozitif olmalı, gelen: {dielektrik_kalinligi_mm!r}"
        )
    if carpan < 1.0:
        raise ValueError(f"h_20h_setback_mm: carpan >= 1.0 olmalı, gelen: {carpan!r}")
    return YirmiHSonucu(
        dielektrik_kalinligi_mm=dielektrik_kalinligi_mm,
        carpan=carpan,
        minimum_setback_mm=round(dielektrik_kalinligi_mm * carpan, 4),
    )


@dataclass(frozen=True)
class YirmiHOlcumu:
    """`guc_kenar_setback_mm`: güç düzleminin kart kenarından mesafesi.
    `gnd_kenar_setback_mm`: GND düzleminin kart kenarından mesafesi —
    20H kuralı GÜÇ'ün GND'DEN daha içeride olmasını da ZORUNLU kılar,
    yalnızca mutlak mesafeyi değil (bkz. `yirmi_h_kontrolu` iki kontrolü
    BİRDEN yapar)."""

    katman_cifti_adi: str
    dielektrik_kalinligi_mm: float
    guc_kenar_setback_mm: float
    gnd_kenar_setback_mm: float


def yirmi_h_kontrolu(
    olcumler: Sequence[YirmiHOlcumu], carpan: float = VARSAYILAN_20H_CARPANI
) -> Bulgu:
    """İki ayrı ihlal türünü aynı kontrolde raporlar:
      (a) güç setback'i mutlak 20H hedefinin altında,
      (b) güç GND'den daha içeride DEĞİL (setback farkı ters/yetersiz).
    İkisi FARKLI kök nedenlerdir — biri "20H hesabı hiç yapılmamış",
    diğeri "hesap yapılmış ama güç/GND sırası karışmış" (yaygın hata)."""
    ihlaller = []
    for o in olcumler:
        hedef = h_20h_setback_mm(o.dielektrik_kalinligi_mm, carpan)
        sorunlar = []
        if o.guc_kenar_setback_mm < hedef.minimum_setback_mm:
            sorunlar.append(
                f"güç setback {o.guc_kenar_setback_mm}mm < hedef {hedef.minimum_setback_mm}mm"
            )
        fark = o.guc_kenar_setback_mm - o.gnd_kenar_setback_mm
        if fark < hedef.minimum_setback_mm:
            sorunlar.append(
                f"güç-GND setback farkı {round(fark, 4)}mm < hedef {hedef.minimum_setback_mm}mm "
                "(güç düzlemi GND'den yeterince içeride değil)"
            )
        if sorunlar:
            ihlaller.append({
                "katman_cifti": o.katman_cifti_adi,
                "guc_setback_mm": o.guc_kenar_setback_mm,
                "gnd_setback_mm": o.gnd_kenar_setback_mm,
                "minimum_setback_mm": hedef.minimum_setback_mm,
                "sorunlar": sorunlar,
            })
    return bulgu_uret(
        "emi_20h_kenar_isimasi",
        taranan=len(olcumler),
        ihlaller=ihlaller,
        detay=f"20H kuralı (çarpan={carpan}), güç/GND düzlem kenar setback'i denetlendi.",
    )


# ------------------------------------------------------------------
# 3) VIA-STITCHING (kenar dikişi) aralığı — dalga_boyu / 20
# ------------------------------------------------------------------

VARSAYILAN_STITCHING_CARPANI = 20.0


@dataclass(frozen=True)
class StitchingSonucu:
    f_diz_ghz: float
    er_eff: float
    dalga_boyu_mm: float
    carpan: float
    maksimum_aralik_mm: float
    kaynak_notu: str = (
        "λ/20 hedefi — kenar GND via aralığı, kaçak alanların (fringing) "
        "kart kenarından yayılmasını dizden (f_knee) türetilen dalga boyunun "
        "1/20'sinin altında tutarak sınırlar. Formül `pcbnew_koprusu."
        "_lambda_20_hedef_mm()` ile FİZİKSEL OLARAK AYNIDIR (C_MPS oradan "
        "ithal edilir, tek kaynak gerçeklik)."
    )


def stitching_max_araligi_mm(
    f_diz_ghz: float, er_eff: float = 4.5, carpan: float = VARSAYILAN_STITCHING_CARPANI
) -> StitchingSonucu:
    """Maksimum kenar/geçiş via aralığını `dalga_boyu / carpan` (varsayılan
    λ/20) formülüyle hesaplar. `f_diz_ghz` = f_knee (kenar hızından türetilen
    diz frekansı, saat frekansı DEĞİL — bkz. `pcb_stackup_planner.py`'deki
    f_knee tartışması, aynı disiplin burada da geçerli)."""
    if f_diz_ghz <= 0:
        raise ValueError(f"stitching_max_araligi_mm: f_diz_ghz pozitif olmalı, gelen: {f_diz_ghz!r}")
    if er_eff <= 0:
        raise ValueError(f"stitching_max_araligi_mm: er_eff pozitif olmalı, gelen: {er_eff!r}")
    v = C_MPS / math.sqrt(er_eff)
    f_hz = f_diz_ghz * 1e9
    dalga_boyu_mm = (v / f_hz) * 1000.0
    return StitchingSonucu(
        f_diz_ghz=f_diz_ghz,
        er_eff=er_eff,
        dalga_boyu_mm=round(dalga_boyu_mm, 4),
        carpan=carpan,
        maksimum_aralik_mm=round(dalga_boyu_mm / carpan, 4),
    )


def via_araligi_kontrolu(
    olculen_araliklar_mm: Sequence[float],
    f_diz_ghz: float,
    er_eff: float = 4.5,
    carpan: float = VARSAYILAN_STITCHING_CARPANI,
) -> Bulgu:
    """Önceden ölçülmüş (ör. `pcbnew_koprusu.py`'nin gerçek board'dan
    ürettiği) ardışık via aralığı listesini λ/carpan hedefine karşı denetler."""
    hedef = stitching_max_araligi_mm(f_diz_ghz, er_eff, carpan)
    ihlaller = [
        {"olculen_mm": round(a, 4), "maksimum_mm": hedef.maksimum_aralik_mm,
         "asim_mm": round(a - hedef.maksimum_aralik_mm, 4)}
        for a in olculen_araliklar_mm
        if a > hedef.maksimum_aralik_mm
    ]
    return bulgu_uret(
        "emi_via_stitching_araligi",
        taranan=len(olculen_araliklar_mm),
        ihlaller=ihlaller,
        detay=f"f_diz={f_diz_ghz}GHz, er_eff={er_eff} -> λ={hedef.dalga_boyu_mm}mm, "
              f"hedef maksimum aralık={hedef.maksimum_aralik_mm}mm (λ/{carpan}).",
    )


def genel_sonuc(bulgular: Sequence[Bulgu]) -> str:
    """`ipc6012_dfm_motoru`/`ipc_a_610_dfa_motoru` ile AYNI birleştirme
    disiplini: FAIL > NEEDS_HUMAN(KAPSAM_YOK) > PASS."""
    if any(b.durum == BulguDurumu.FAIL for b in bulgular):
        return "FAIL"
    if any(b.durum == BulguDurumu.KAPSAM_YOK for b in bulgular):
        return "NEEDS_HUMAN"
    return "PASS"


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION (üç kural için de): hedefin BİRAZ altına/üstüne
    koyup kontrolün GERÇEKTEN FAIL verdiğini, tam sınırında PASS verdiğini
    kanıtla."""
    sonuclar = []

    # 3W
    hedef = w_3w(0.2)
    tam = uc_w_kontrolu([UcWOlcumu("A", "B", 0.2, 0.2, hedef.minimum_merkez_merkez_mm)])
    az = uc_w_kontrolu([UcWOlcumu("A", "B", 0.2, 0.2, hedef.minimum_merkez_merkez_mm - 0.01)])
    sonuclar.append(tam.durum == BulguDurumu.PASS and az.durum == BulguDurumu.FAIL)

    # 20H
    hedef_h = h_20h_setback_mm(0.1)
    tam_h = yirmi_h_kontrolu([
        YirmiHOlcumu("F.Cu-In1.Cu", 0.1, hedef_h.minimum_setback_mm + 5.0, 5.0)
    ])
    az_h = yirmi_h_kontrolu([
        YirmiHOlcumu("F.Cu-In1.Cu", 0.1, hedef_h.minimum_setback_mm - 0.01, 0.0)
    ])
    sonuclar.append(tam_h.durum == BulguDurumu.PASS and az_h.durum == BulguDurumu.FAIL)

    # Via stitching
    hedef_s = stitching_max_araligi_mm(5.0)
    tam_s = via_araligi_kontrolu([hedef_s.maksimum_aralik_mm], 5.0)
    asili_s = via_araligi_kontrolu([hedef_s.maksimum_aralik_mm + 0.5], 5.0)
    sonuclar.append(tam_s.durum == BulguDurumu.PASS and asili_s.durum == BulguDurumu.FAIL)

    return all(sonuclar)


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. 3W: merkez-merkez - iz_genisligi == kenar-kenar (tanım tutarlılığı).
    s = w_3w(0.25)
    if abs(s.minimum_kenar_kenar_mm - (s.minimum_merkez_merkez_mm - 0.25)) > 1e-9:
        hatalar.append("w_3w: kenar-kenar/merkez-merkez tanım tutarsızlığı")

    # 2. 3W: carpan < 1.0 reddedilmeli.
    try:
        w_3w(0.2, carpan=0.5)
    except ValueError:
        pass
    else:
        hatalar.append("w_3w: carpan<1.0 reddedilmedi")

    # 3. 20H: dielektrik arttıkça setback ORANTILI artmalı.
    ince = h_20h_setback_mm(0.1)
    kalin = h_20h_setback_mm(0.2)
    if not (kalin.minimum_setback_mm == 2 * ince.minimum_setback_mm):
        hatalar.append("h_20h_setback_mm: dielektrik ile orantılı artmıyor")

    # 4. Via stitching: daha yüksek frekans -> DAHA SIK via (daha küçük maksimum aralık).
    dusuk_f = stitching_max_araligi_mm(1.0)
    yuksek_f = stitching_max_araligi_mm(10.0)
    if not (yuksek_f.maksimum_aralik_mm < dusuk_f.maksimum_aralik_mm):
        hatalar.append("stitching_max_araligi_mm: yüksek frekansta aralık küçülmüyor")

    # 5. Boş ölçüm kümeleri KAPSAM_YOK olmalı, sessizce PASS OLMAMALI.
    for bulgu in (uc_w_kontrolu([]), yirmi_h_kontrolu([]), via_araligi_kontrolu([], 5.0)):
        if bulgu.durum != BulguDurumu.KAPSAM_YOK or bulgu.gecti_mi:
            hatalar.append(f"{bulgu.kontrol}: boş girdi PASS sayıldı (KAPSAM_YOK olmalıydı)")

    # 6. genel_sonuc önceliği: FAIL > NEEDS_HUMAN > PASS.
    fail_b = Bulgu("x", BulguDurumu.FAIL, 1, [{"m": 1}])
    kapsam_b = Bulgu("y", BulguDurumu.KAPSAM_YOK, 0, [])
    pass_b = Bulgu("z", BulguDurumu.PASS, 1, [])
    if genel_sonuc([fail_b, kapsam_b]) != "FAIL":
        hatalar.append("genel_sonuc: FAIL önceliği bozuk")
    if genel_sonuc([kapsam_b, pass_b]) != "NEEDS_HUMAN":
        hatalar.append("genel_sonuc: NEEDS_HUMAN önceliği bozuk")
    if genel_sonuc([pass_b]) != "PASS":
        hatalar.append("genel_sonuc: PASS durumu bozuk")

    # 7. Fault injection (üç kural).
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: 3W/20H/stitching sınır testlerinden biri boş olabilir")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--iz-genisligi-mm", type=float, default=0.2)
    p.add_argument("--dielektrik-kalinligi-mm", type=float, default=0.1)
    p.add_argument("--f-diz-ghz", type=float, default=5.0)
    p.add_argument("--er-eff", type=float, default=4.5)
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
        uc_w = w_3w(args.iz_genisligi_mm)
        yirmi_h = h_20h_setback_mm(args.dielektrik_kalinligi_mm)
        stitch = stitching_max_araligi_mm(args.f_diz_ghz, args.er_eff)
        veri = {
            "3w": {
                "iz_genisligi_mm": uc_w.iz_genisligi_mm,
                "minimum_merkez_merkez_mm": uc_w.minimum_merkez_merkez_mm,
                "minimum_kenar_kenar_mm": uc_w.minimum_kenar_kenar_mm,
            },
            "20h": {
                "dielektrik_kalinligi_mm": yirmi_h.dielektrik_kalinligi_mm,
                "minimum_setback_mm": yirmi_h.minimum_setback_mm,
            },
            "via_stitching": {
                "f_diz_ghz": stitch.f_diz_ghz,
                "er_eff": stitch.er_eff,
                "dalga_boyu_mm": stitch.dalga_boyu_mm,
                "maksimum_aralik_mm": stitch.maksimum_aralik_mm,
            },
        }
        metin = json.dumps(veri, indent=2, ensure_ascii=False, sort_keys=True)
        print(metin)
        if args.json:
            args.json.write_text(metin + "\n", encoding="utf-8")
            print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
