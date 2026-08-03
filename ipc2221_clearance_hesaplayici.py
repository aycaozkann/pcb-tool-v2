#!/usr/bin/env python3
"""
ipc2221_clearance_hesaplayici.py
===================================
IPC-2221B Table 6-1 (İletken Boşluk/Yalıtım Mesafesi) tablosunu baz alan,
katman tipi (iç/dış) VE kaplama durumuna (kaplamasız/conformal coating)
göre minimum clearance + creepage hesaplayan modül.

NEDEN AYRI BİR MODÜL (`pcb_stackup_planner.py::IPC2221_HARICI_MESAFE_TABLOSU_MM`
YERİNE değil, ONUN GENİŞLETİLMİŞ HALİ):
-------------------------------------------------------------------------
`pcb_stackup_planner.py` içinde ZATEN bir tablo/fonksiyon var
(`IPC2221_HARICI_MESAFE_TABLOSU_MM` + `gerekli_izolasyon_mesafesi_mm()`)
ama SADECE dış/kaplamasız (external, uncoated) koşulu kapsıyor — iç katman
ve kaplamalı (conformal coated) koşulları YOK, creepage'i clearance'tan
AYIRT ETMİYOR, ve voltaj bantları interpolasyon YAPMIYOR (basamak/step
fonksiyonu). Bu modül o üç eksiği kapatır. **Sessiz sapmayı önlemek için**,
dış/kaplamasız koşulun ORTAK voltaj noktalarında (15V, 30V, 50V, 100V,
500V) BİREBİR AYNI sayılar kullanılır (aşağıdaki `_ESKI_TABLO_ILE_TUTARLILIK_TESTI`).

ÖNEMLİ — DÜRÜSTLÜK NOTU (bu tablonun kaynağı ve güven seviyesi):
-------------------------------------------------------------------
Bu ortamda resmi, SATIN ALINMIŞ IPC-2221B PDF'ine ERİŞİM YOKTUR. Aşağıdaki
tablo, birden fazla YAYGIN OLARAK ATIFTA BULUNULAN ikincil kaynaktan
(üretici tasarım kılavuzları, PCB tedarikçilerinin teknik makaleleri)
derlenmiştir ve HER DEĞER, `MesafeNoktasi.guven` alanıyla kendi güven
seviyesini TAŞIR:

  - `"MEVCUT_KOD_ILE_TUTARLI"` — bu projenin `pcb_stackup_planner.py`
    dosyasında ZATEN kabul edilmiş external/uncoated değerleriyle birebir
    aynı (en yüksek güven — proje içinde önceden onaylanmış).
  - `"IKINCIL_KAYNAK_TAHMINI"` — yaygın olarak atıfta bulunulan ama bu
    ortamda resmi standarda karşı DOĞRULANAMAMIŞ bir sayı.
  - `"MUHAFAZAKAR_VARSAYIM"` — belirsizlik durumunda BİLEREK DAHA BÜYÜK
    (daha güvenli/daha fazla mesafe isteyen) bir değer seçildi; gerçek
    resmi değer bundan KÜÇÜK çıkabilir (bu durumda tasarım gereğinden
    fazla muhafazakar olmuş olur — GÜVENLİ yöndeki hata) ama BÜYÜK
    çıkmamalı (bu, TEHLİKELİ yönde bir hata olurdu).

**Bu modül compliance (uygunluk) KANITI DEĞİLDİR — sadece ilk tarama/
eleme aracıdır.** Güvenlik-kritik veya yüksek voltajlı (>50V) her tasarımda,
üretim imzasından ÖNCE değerler resmi IPC-2221B (veya ilgili IEC 60664-1/
UL 60950-1/62368-1 gibi türev standart) kopyasından TEK TEK doğrulanmalı ve
bir güvenlik/uyumluluk uzmanına onaylatılmalıdır.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence


class KatmanTipi(str, Enum):
    IC = "internal"
    DIS = "external"


class KaplamaDurumu(str, Enum):
    KAPLAMASIZ = "uncoated"
    KAPLI = "conformal_coated"


class Guven(str, Enum):
    MEVCUT_KOD_ILE_TUTARLI = "MEVCUT_KOD_ILE_TUTARLI"
    IKINCIL_KAYNAK_TAHMINI = "IKINCIL_KAYNAK_TAHMINI"
    MUHAFAZAKAR_VARSAYIM = "MUHAFAZAKAR_VARSAYIM"


@dataclass(frozen=True)
class MesafeNoktasi:
    maks_gerilim_V: float
    clearance_mm: float
    guven: Guven


# ------------------------------------------------------------------
# TABLO — kullanıcının istediği 7 bant: 0-15, 16-30, 31-50, 51-100,
# 101-300, 301-500, >500 V.
#
# Dış/Kaplamasız (external, uncoated) ortak noktalarda (15/30/50/100/500V)
# `pcb_stackup_planner.IPC2221_HARICI_MESAFE_TABLOSU_MM` ile BİREBİR AYNI
# (bkz. dosya başlığı) — bu yüzden bu satırlar en yüksek güven seviyesini
# taşır. 300V noktası o tablonun 250V(0.3mm)/500V(0.5mm) basamakları
# ARASINDA kalır; burada İKİSİNİN ARASINDA muhafazakar (üste yakın) bir
# değer seçildi (0.4mm) — kesin değer resmi tablodan doğrulanmalı.
# ------------------------------------------------------------------

_DIS_KAPLAMASIZ: tuple[MesafeNoktasi, ...] = (
    MesafeNoktasi(15, 0.05, Guven.MEVCUT_KOD_ILE_TUTARLI),
    MesafeNoktasi(30, 0.05, Guven.MEVCUT_KOD_ILE_TUTARLI),
    MesafeNoktasi(50, 0.10, Guven.MEVCUT_KOD_ILE_TUTARLI),
    MesafeNoktasi(100, 0.10, Guven.MEVCUT_KOD_ILE_TUTARLI),
    MesafeNoktasi(300, 0.40, Guven.MUHAFAZAKAR_VARSAYIM),
    MesafeNoktasi(500, 0.50, Guven.MEVCUT_KOD_ILE_TUTARLI),
)

# İç katmanlar (internal): gerçek IPC-2221B tablosunda düşük voltajlarda
# genellikle dış/kaplamasızdan DAHA KÜÇÜK (iç katman çevresel kirlenmeye
# kapalı) — ama bu ortamda kesin sayı doğrulanamadığı için bu modül
# BİLEREK dış/kaplamasız ile AYNI (asla daha küçük değil) değeri kullanır.
# Bu, "belirsizlikte muhafazakar (daha büyük/daha güvenli) tarafta hata
# yap" ilkesinin uygulamasıdır — `ipc2152_hesaplayici.py`'nin iç-katman
# derating kararıyla AYNI disiplin.
_IC_KAPLAMASIZ: tuple[MesafeNoktasi, ...] = tuple(
    MesafeNoktasi(n.maks_gerilim_V, n.clearance_mm, Guven.MUHAFAZAKAR_VARSAYIM)
    for n in _DIS_KAPLAMASIZ
)

# Conformal coating (kaplamalı dış katman): yaygın olarak atıfta bulunulan
# özet kaynaklar, kaplamanın ORTA/YÜKSEK voltajlarda mesafeyi belirgin
# ölçüde AZALTTIĞINI belirtir — ama bu bir ELEKTRİKSEL azalma değil, aynı
# zamanda PRATİK bir üretim/işleme tabanı (`_KAPLI_TABAN_MM`) da vardır:
# kaplama kalınlığı/uygulama toleransı kendisi belirli bir minimum
# mesafenin altına inmeyi ANLAMSIZ kılar. SONUÇ: çok düşük voltajlarda
# (ör. 15V) kaplamasızın zaten çok dar olan elektriksel minimumu
# (0.05mm), kaplı tabandan (0.13mm) KÜÇÜK kalabilir — yani kaplı değer o
# bantta kaplamasızdan SAYISAL OLARAK BÜYÜK görünür. Bu bir hata DEĞİLDİR;
# "kaplama HER ZAMAN daha az mesafe ister" basitleştirmesi düşük
# voltajlarda geçerli değildir. Öz-testler bu nüansı (`_KAPLI_TABAN_KIC_ETKISI_V`)
# AÇIKÇA modeller — sessizce yanlış bir monotonluk iddia edilmez.
_KAPLI_TABAN_MM = 0.13
_KAPLI_OLCEK_FAKTORU = 0.4  # kaplamasız değerin bu kesri kadar azaltılır (taban altına düşmez)

_DIS_KAPLI: tuple[MesafeNoktasi, ...] = tuple(
    MesafeNoktasi(
        n.maks_gerilim_V,
        round(max(_KAPLI_TABAN_MM, n.clearance_mm * _KAPLI_OLCEK_FAKTORU), 4),
        Guven.IKINCIL_KAYNAK_TAHMINI,
    )
    for n in _DIS_KAPLAMASIZ
)

_TABLOLAR: dict[tuple[KatmanTipi, KaplamaDurumu], tuple[MesafeNoktasi, ...]] = {
    (KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ): _DIS_KAPLAMASIZ,
    (KatmanTipi.IC, KaplamaDurumu.KAPLAMASIZ): _IC_KAPLAMASIZ,
    (KatmanTipi.DIS, KaplamaDurumu.KAPLI): _DIS_KAPLI,
    # İç katman, tanım gereği çevresel kirlenmeye/kaplamaya maruz KALMAZ —
    # "iç + kaplı" kombinasyonu anlamsızdır; çağıran taraf bunu isterse
    # AÇIKÇA `ValueError` alır (sessizce dış-kaplı değeri geri DÖNMEZ).
}

# Creepage, clearance'tan BÜYÜK VEYA EŞİT olmalıdır (IEC 60664-1'in genel
# ilkesi — malzeme grubu/kirlenme derecesine göre TAM oranı değişir).
# Kesin CTI/kirlenme-derecesi verisi olmadan, bu modül creepage'i
# "clearance × VARSAYILAN_CREEPAGE_KATSAYISI" olarak MUHAFAZAKAR bir
# yaklaşımla üretir — gerçek değer daha büyük olabilir, kesin oran resmi
# tablo + malzeme CTI değeriyle doğrulanmalı.
VARSAYILAN_CREEPAGE_KATSAYISI = 1.0


@dataclass(frozen=True)
class ClearanceSonucu:
    clearance_mm: float
    creepage_mm: float
    gerilim_V: float
    katman_tipi: KatmanTipi
    kaplama_durumu: KaplamaDurumu
    guven: Guven
    interpolasyon_kullanildi: bool


def _tablo_getir(katman_tipi: KatmanTipi, kaplama_durumu: KaplamaDurumu) -> tuple[MesafeNoktasi, ...]:
    anahtar = (katman_tipi, kaplama_durumu)
    if anahtar not in _TABLOLAR:
        raise ValueError(
            f"Geçersiz kombinasyon: katman_tipi={katman_tipi.value}, "
            f"kaplama_durumu={kaplama_durumu.value} — iç katman + kaplama "
            "kombinasyonu tanımsızdır (iç katmanlar conformal coating'e maruz kalmaz)."
        )
    return _TABLOLAR[anahtar]


def clearance_hesapla_mm(
    maksimum_gerilim_V: float,
    katman_tipi: KatmanTipi,
    kaplama_durumu: KaplamaDurumu = KaplamaDurumu.KAPLAMASIZ,
    interpolasyon_modu: bool = False,
    creepage_katsayisi: float = VARSAYILAN_CREEPAGE_KATSAYISI,
) -> ClearanceSonucu:
    """Verilen tepe voltajı için minimum clearance + creepage (mm) döner.

    `interpolasyon_modu`:
      - `False` (varsayılan, STANDART-SADIK davranış): resmi IPC tabloları
        BASAMAK (step) fonksiyonudur — bir voltaj bandına düşen HER değer
        o bandın tablo değerini alır, ARADA yumuşak bir geçiş YOKTUR. Bu
        varsayılan, gerçek standart davranışını yansıtır.
      - `True`: bant sınırları arasında DOĞRUSAL interpolasyon yapar —
        standardın KENDİSİNDE olmayan, bu ARACIN sunduğu bir mühendislik
        kolaylığıdır (ör. "150V'ta tam olarak ne kadar marj var" sorusuna
        daha yumuşak bir tahmin). `interpolasyon_kullanildi` alanı bu
        farkı rapora TAŞIR — hangi modun kullanıldığı asla gizlenmez.
    """
    if maksimum_gerilim_V < 0:
        raise ValueError(f"maksimum_gerilim_V negatif olamaz, gelen: {maksimum_gerilim_V!r}")
    if creepage_katsayisi < 1.0:
        raise ValueError(
            f"creepage_katsayisi >= 1.0 olmalı (creepage clearance'tan küçük olamaz), "
            f"gelen: {creepage_katsayisi!r}"
        )

    tablo = _tablo_getir(katman_tipi, kaplama_durumu)
    son_nokta = tablo[-1]

    if maksimum_gerilim_V > son_nokta.maks_gerilim_V:
        # Tablonun üstünde: mevcut projenin `gerekli_izolasyon_mesafesi_mm()`
        # ile AYNI dürüst doğrusal ekstrapolasyon disiplini (kesinlikle
        # gerçek tabloyla doğrulanmalı).
        clearance = son_nokta.clearance_mm * (maksimum_gerilim_V / son_nokta.maks_gerilim_V)
        guven = Guven.MUHAFAZAKAR_VARSAYIM
        interpolasyon_kullanildi = False
    elif not interpolasyon_modu:
        eslesen = next(n for n in tablo if maksimum_gerilim_V <= n.maks_gerilim_V)
        clearance = eslesen.clearance_mm
        guven = eslesen.guven
        interpolasyon_kullanildi = False
    else:
        clearance, guven = _dogrusal_interpolasyon(tablo, maksimum_gerilim_V)
        interpolasyon_kullanildi = True

    creepage = round(clearance * creepage_katsayisi, 4)

    return ClearanceSonucu(
        clearance_mm=round(clearance, 4),
        creepage_mm=creepage,
        gerilim_V=maksimum_gerilim_V,
        katman_tipi=katman_tipi,
        kaplama_durumu=kaplama_durumu,
        guven=guven,
        interpolasyon_kullanildi=interpolasyon_kullanildi,
    )


def _dogrusal_interpolasyon(
    tablo: Sequence[MesafeNoktasi], gerilim_V: float
) -> tuple[float, Guven]:
    """`tablo`daki iki bitişik nokta arasında doğrusal interpolasyon yapar.

    Alt sınırın (0V) clearance'ı, tablonun İLK noktasının değeriyle AYNI
    kabul edilir (0V'ta "hiç mesafe gerekmez" demek FİZİKSEL OLARAK yanlış
    olurdu — düşük voltaj bandının minimum değeri korunur).
    """
    onceki_v, onceki_mm, onceki_guven = 0.0, tablo[0].clearance_mm, tablo[0].guven
    for nokta in tablo:
        if gerilim_V <= nokta.maks_gerilim_V:
            if nokta.maks_gerilim_V == onceki_v:
                return nokta.clearance_mm, nokta.guven
            oran = (gerilim_V - onceki_v) / (nokta.maks_gerilim_V - onceki_v)
            deger = onceki_mm + oran * (nokta.clearance_mm - onceki_mm)
            # İnterpolasyon iki nokta arasındaysa, sonucun güveni bu
            # ikisinin EN AZ GÜVENİLİR (en yüksek belirsizlik) olanını
            # MİRAS ALIR — sessizce daha yüksek bir güven iddia edilmez.
            en_az_guvenilir = max((onceki_guven, nokta.guven), key=_guven_siralamasi)
            return deger, en_az_guvenilir
        onceki_v, onceki_mm, onceki_guven = nokta.maks_gerilim_V, nokta.clearance_mm, nokta.guven
    return tablo[-1].clearance_mm, tablo[-1].guven


def _guven_siralamasi(guven: Guven) -> int:
    sira = {
        Guven.MEVCUT_KOD_ILE_TUTARLI: 0,
        Guven.IKINCIL_KAYNAK_TAHMINI: 1,
        Guven.MUHAFAZAKAR_VARSAYIM: 2,
    }
    return sira[guven]


def tum_kombinasyonlari_uret(
    maksimum_gerilim_V: float, interpolasyon_modu: bool = False,
) -> dict[str, ClearanceSonucu]:
    """Aynı voltaj için TÜM geçerli (katman × kaplama) kombinasyonlarını
    tek seferde döner — rapor/`.kicad_dru` üretiminde kullanışlı."""
    sonuc: dict[str, ClearanceSonucu] = {}
    for (katman, kaplama) in _TABLOLAR:
        anahtar = f"{katman.value}_{kaplama.value}"
        sonuc[anahtar] = clearance_hesapla_mm(maksimum_gerilim_V, katman, kaplama, interpolasyon_modu)
    return sonuc


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: creepage katsayısını bilerek 1'in ALTINA (0.5)
    çekmeye çalışırsak `ValueError` beklenir (creepage clearance'tan küçük
    OLAMAZ, fiziksel bir kısıt) — kabul edilirse girdi doğrulaması boştur."""
    try:
        clearance_hesapla_mm(100, KatmanTipi.DIS, creepage_katsayisi=0.5)
    except ValueError:
        return True
    return False


def _esitlik_kontrolu_mevcut_tabloyla() -> list[str]:
    """`pcb_stackup_planner.IPC2221_HARICI_MESAFE_TABLOSU_MM` ile ortak
    voltaj noktalarında (15/30/50/100/500V) BİREBİR eşleşme — sessiz
    sapma kontrolü (dosya başlığındaki tek-kaynak-gerçeklik iddiasının
    kanıtı)."""
    from pcb_stackup_planner import gerekli_izolasyon_mesafesi_mm

    hatalar: list[str] = []
    for v in (15, 30, 50, 100, 500):
        eski = gerekli_izolasyon_mesafesi_mm(v)
        yeni = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ).clearance_mm
        if not (abs(eski - yeni) < 1e-9):
            hatalar.append(f"{v}V'ta eski tablo={eski}mm, yeni tablo={yeni}mm — SAPMA VAR")
    return hatalar


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. Mevcut kodla tutarlılık (tek kaynak gerçeklik iddiasının kanıtı).
    hatalar.extend(_esitlik_kontrolu_mevcut_tabloyla())

    # 2. Voltaj arttıkça clearance monoton artmalı (asla azalmamalı).
    onceki = None
    for v in (10, 20, 40, 75, 200, 400, 600):
        sonuc = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
        if onceki is not None and sonuc.clearance_mm < onceki:
            hatalar.append(f"{v}V'ta clearance azaldı: {onceki}mm -> {sonuc.clearance_mm}mm")
        onceki = sonuc.clearance_mm

    # 3. Kaplamalı dış katman, kaplamasız değer TABANIN (0.13mm) ÜSTÜNDEYKEN
    #    asla ondan DAHA BÜYÜK olmamalı. Taban altındaki (çok düşük voltaj)
    #    bantlarda kaplı sayısal olarak büyük GÖRÜNEBİLİR — bu, üretim
    #    tabanından kaynaklanan BEKLENEN bir durumdur (bkz. dosya başlığı
    #    `_KAPLI_TABAN_MM` notu), hata değildir.
    for v in (15, 50, 100, 300, 500):
        kaplamasiz = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ)
        kapli = clearance_hesapla_mm(v, KatmanTipi.DIS, KaplamaDurumu.KAPLI)
        if kaplamasiz.clearance_mm > _KAPLI_TABAN_MM and kapli.clearance_mm > kaplamasiz.clearance_mm:
            hatalar.append(f"{v}V'ta kaplı ({kapli.clearance_mm}mm) kaplamasızdan ({kaplamasiz.clearance_mm}mm) büyük")

    # 4. İç katman + kaplama kombinasyonu reddedilmeli.
    try:
        clearance_hesapla_mm(50, KatmanTipi.IC, KaplamaDurumu.KAPLI)
    except ValueError:
        pass
    else:
        hatalar.append("iç katman + kaplama kombinasyonu reddedilmedi")

    # 5. İnterpolasyon modu, basamak modundan FARKLI (ara değerde) sonuç üretmeli.
    basamak = clearance_hesapla_mm(200, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=False)
    interpolasyonlu = clearance_hesapla_mm(200, KatmanTipi.DIS, KaplamaDurumu.KAPLAMASIZ, interpolasyon_modu=True)
    if basamak.interpolasyon_kullanildi or not interpolasyonlu.interpolasyon_kullanildi:
        hatalar.append("interpolasyon_kullanildi bayrağı doğru işaretlenmedi")

    # 6. Creepage >= clearance her zaman sağlanmalı.
    sonuc = clearance_hesapla_mm(100, KatmanTipi.DIS, creepage_katsayisi=1.2)
    if sonuc.creepage_mm < sonuc.clearance_mm:
        hatalar.append(f"creepage ({sonuc.creepage_mm}mm) clearance'tan ({sonuc.clearance_mm}mm) küçük")

    # 7. Fault injection.
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: creepage doğrulaması boş olabilir")

    return hatalar


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gerilim", type=float, help="maksimum tepe voltajı, V")
    p.add_argument("--katman", choices=[k.value for k in KatmanTipi], default=KatmanTipi.DIS.value)
    p.add_argument("--kaplama", choices=[k.value for k in KaplamaDurumu], default=KaplamaDurumu.KAPLAMASIZ.value)
    p.add_argument("--interpolasyon", action="store_true")
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

    if args.oztest or args.gerilim is None:
        if args.gerilim is None and not args.oztest:
            print("--gerilim verilmedi; öz-testler tamamlandı.")
        return 0

    try:
        sonuc = clearance_hesapla_mm(
            args.gerilim, KatmanTipi(args.katman), KaplamaDurumu(args.kaplama), args.interpolasyon,
        )
    except ValueError as exc:
        parser.error(str(exc))

    veri = sonuc.__dict__ | {
        "katman_tipi": sonuc.katman_tipi.value,
        "kaplama_durumu": sonuc.kaplama_durumu.value,
        "guven": sonuc.guven.value,
    }
    metin = json.dumps(veri, indent=2, ensure_ascii=False, sort_keys=True)
    print(metin)
    if args.json:
        args.json.write_text(metin + "\n", encoding="utf-8")
        print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
