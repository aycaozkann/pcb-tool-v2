"""
ipc7351_footprint.py
======================
IPC-7351 (SMD Land Pattern / footprint pad boyutlandırma) hesaplayıcısı.

NEDEN BU DOSYA VAR:
Proje şimdiye kadar footprint/pad boyutlandırmasını "datasheet'teki
land-pattern'i kopyala" diyerek insana bırakıyordu (bkz. `SKILL-konnektor`
karşılaştırması, FPC/ZIF landing notları) — bu doğru bir varsayılan ama iki
uçlu çip pasifler (0402/0603/0805 R/C/L) gibi standart paketler için
IPC-7351B formülüyle **hesaplanabilir/doğrulanabilir** bir land pattern
üretilebilir. Bu modül o hesabı yapar.

FORMÜLLER (IPC-7351B, iki-terminalli çip komponent — chip R/C/L):
    Zmax (pad-dışı span)   = Lmin + 2*Jt + sqrt(Cl^2 + F^2 + P^2)
    Gmin (pad-içi boşluk)  = Smax - 2*Jh - sqrt(Cs^2 + F^2 + P^2)
    Xmax (pad genişliği)   = Wmin + 2*Js + sqrt(Cs^2 + F^2 + P^2)

    burada S = L - 2*T (terminasyonlar arası iç mesafe, "heel-to-heel")
    Jt/Jh/Js = toe/heel/side fillet hedefleri (yoğunluk seviyesine göre)
    Cl/Cs = komponent toleransı, F = fabrikasyon toleransı, P = yerleşim toleransı

Pad boyutları: pad_uzunlugu = (Zmax - Gmin) / 2, pad_genisligi = Xmax.

DÜRÜSTLÜK NOTU (proje disipliniyle uyumlu):
Buradaki varsayılan Jt/Jh/Js/F/P/Cl/Cs değerleri IPC-7351B'nin yaygın
YAYIMLANMIŞ varsayılanlarıdır (Density Level B/Nominal referans alınarak).
Bu SIGN-OFF için yeterli DEĞİLDİR — kritik/yoğun bir tasarımda gerçek
IPC-7351B tablosu (veya bir IPC-7351 hesaplayıcısı, ör. PCB Libraries'in
kendi aracı) ile ÇAPRAZ DOĞRULANMALI, özellikle özel/nadir paketlerde.
Bu modülün amacı "makul bir başlangıç + hesabın izlenebilirliği"dir,
kütüphane üretiminin otomatik/sorgusuz kaynağı değildir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class YogunlukSeviyesi(str, Enum):
    """IPC-7351B üç yoğunluk seviyesi — aynı paket için üç farklı pad boyutu
    üretir. Seçim üretim/güvenilirlik hedefine göre yapılır, keyfi değil."""

    A_MAKSIMUM = "A"   # En geniş pad (en kolay lehim, en fazla alan)
    B_NOMINAL = "B"    # Çoğu tasarımın varsayılanı
    C_MINIMUM = "C"    # En yoğun paketleme (fine-pitch, alan kısıtlı)


# Yoğunluk seviyesine göre fillet hedefleri (mm) — IPC-7351B chip/SMD
# komponent tablosunun yaygın yayımlanmış varsayılanları.
_FILLET_MM = {
    YogunlukSeviyesi.A_MAKSIMUM: {"Jt": 0.55, "Jh": 0.00, "Js": 0.05},
    YogunlukSeviyesi.B_NOMINAL: {"Jt": 0.35, "Jh": 0.00, "Js": 0.03},
    YogunlukSeviyesi.C_MINIMUM: {"Jt": 0.15, "Jh": 0.00, "Js": 0.01},
}

# Varsayılan tolerans bütçesi (mm) — F: fabrikasyon, P: yerleşim,
# Cl/Cs: komponent toleransı. Kritik tasarımda datasheet/fab profilinden
# GÜNCELLENMELİ; burada tipik SMT üretim varsayılanları kullanıldı.
VARSAYILAN_F_MM = 0.05
VARSAYILAN_P_MM = 0.05
VARSAYILAN_CL_MM = 0.10
VARSAYILAN_CS_MM = 0.10


@dataclass
class CipKomponentBoyutlari:
    """Datasheet'ten alınan HAM boyutlar (mm). Min/maks toleransları
    verilmezse `tolerans_mm` ile simetrik bir bant varsayılır."""

    uzunluk_nom_mm: float   # L: gövde uzunluğu (terminasyon dahil, uç-uca)
    genislik_nom_mm: float  # W: gövde genişliği
    terminasyon_nom_mm: float  # T: terminasyon (uç metal kısmı) uzunluğu
    tolerans_mm: float = 0.05  # L/W/T için simetrik ± tolerans (datasheet yoksa)


@dataclass
class LandPatternSonucu:
    pad_uzunlugu_mm: float
    pad_genisligi_mm: float
    pad_araligi_mm: float  # merkez-merkez (pitch) — iki pad'in merkez mesafesi
    zmax_mm: float
    gmin_mm: float
    xmax_mm: float
    yogunluk: YogunlukSeviyesi


def _zmax_gmin_xmax_hesapla(
    l_nom_mm: float, w_nom_mm: float, t_nom_mm: float, tolerans_mm: float,
    fillet: dict, f_mm: float, p_mm: float, cl_mm: float, cs_mm: float,
    yogunluk: YogunlukSeviyesi,
) -> LandPatternSonucu:
    """Zmax/Gmin/Xmax'ın ORTAK çekirdeği — `land_pattern_hesapla()` (2-terminal
    çip), `gullwing_land_pattern_hesapla()` (SOIC/QFP) VE
    `qfn_land_pattern_hesapla()` (no-lead) hep AYNI IPC-7351B toe/heel/side
    formül ailesini kullanır; tek fark hangi (L, W, T, fillet tablosu)
    girdisinin verildiğidir. Tek yerde tutulur ki üç fonksiyon birbirinden
    SAPMASIN (kopyala-yapıştır driftini önler)."""
    l_min = l_nom_mm - tolerans_mm
    l_maks = l_nom_mm + tolerans_mm
    w_min = w_nom_mm - tolerans_mm

    kok_terim_uzun = math.sqrt(cl_mm ** 2 + f_mm ** 2 + p_mm ** 2)
    kok_terim_yan = math.sqrt(cs_mm ** 2 + f_mm ** 2 + p_mm ** 2)

    s_maks = l_maks - 2 * t_nom_mm  # terminasyonlar arası iç (heel-to-heel) mesafe

    zmax = l_min + 2 * fillet["Jt"] + kok_terim_uzun
    gmin = s_maks - 2 * fillet["Jh"] - kok_terim_uzun
    xmax = w_min + 2 * fillet["Js"] + kok_terim_yan

    if gmin <= 0:
        raise ValueError(
            f"Gmin={gmin:.3f}mm <= 0 — bu geometri/tolerans kombinasyonuyla "
            "pad'ler çakışıyor demektir; girdi boyutlarını/toleransları kontrol et."
        )

    pad_uzunlugu = (zmax - gmin) / 2
    pad_araligi = (zmax + gmin) / 2  # iki pad merkezi arası mesafe

    return LandPatternSonucu(
        pad_uzunlugu_mm=round(pad_uzunlugu, 4),
        pad_genisligi_mm=round(xmax, 4),
        pad_araligi_mm=round(pad_araligi, 4),
        zmax_mm=round(zmax, 4),
        gmin_mm=round(gmin, 4),
        xmax_mm=round(xmax, 4),
        yogunluk=yogunluk,
    )


def land_pattern_hesapla(
    komponent: CipKomponentBoyutlari,
    yogunluk: YogunlukSeviyesi = YogunlukSeviyesi.B_NOMINAL,
    f_mm: float = VARSAYILAN_F_MM,
    p_mm: float = VARSAYILAN_P_MM,
    cl_mm: float = VARSAYILAN_CL_MM,
    cs_mm: float = VARSAYILAN_CS_MM,
) -> LandPatternSonucu:
    """İki-terminalli çip komponent (0402/0603/0805/1206 R/C/L vb.) için
    IPC-7351B pad boyutlarını hesaplar.

    Çok-pinli paketler için: `gullwing_land_pattern_hesapla()` (SOIC/TSOP/QFP)
    ve `qfn_land_pattern_hesapla()` (no-lead QFN), BGA için ayrı formül
    ailesi olan `bga_land_pattern_hesapla()` kullanılmalı.
    """
    return _zmax_gmin_xmax_hesapla(
        komponent.uzunluk_nom_mm, komponent.genislik_nom_mm,
        komponent.terminasyon_nom_mm, komponent.tolerans_mm,
        _FILLET_MM[yogunluk], f_mm, p_mm, cl_mm, cs_mm, yogunluk,
    )


# ------------------------------------------------------------------
# Gullwing / QFP (SOIC, TSOP, TQFP vb.) — çok-pinli, İKİ KARŞIT SIRA
# ------------------------------------------------------------------
#
# Matematiksel olarak 2-terminalli çip ile AYNI Zmax/Gmin/Xmax ailesi
# kullanılır — tek fark L/W/T'nin komponent GÖVDESİ değil, karşı iki lead
# sırasının DIŞ AÇIKLIĞI (lead-tip-to-lead-tip span), tek bir lead'in
# genişliği ve lead ayak (foot) uzunluğu olmasıdır. Aynı sıra içindeki
# komşu pad'ler arası mesafe (pitch) bu hesaba GİRMEZ — IPC-7351 pitch'i
# hesaplamaz, doğrudan datasheet'ten alır (`komponent.pitch_mm` sadece
# taşınır, footprint üretiminde kullanılmak üzere).

@dataclass
class GullwingKomponentBoyutlari:
    """Datasheet'ten alınan gullwing/QFP lead boyutları (mm)."""

    pin_sayisi: int
    pitch_mm: float             # aynı sıradaki komşu lead merkezleri arası mesafe
    lead_span_nom_mm: float     # L: karşı iki sıra lead-ucu arası TOPLAM açıklık
    lead_genislik_nom_mm: float # W: tek bir lead'in genişliği
    lead_uzunluk_nom_mm: float  # T: lead ayak (foot) uzunluğu
    tolerans_mm: float = 0.05


def gullwing_land_pattern_hesapla(
    komponent: GullwingKomponentBoyutlari,
    yogunluk: YogunlukSeviyesi = YogunlukSeviyesi.B_NOMINAL,
    f_mm: float = VARSAYILAN_F_MM,
    p_mm: float = VARSAYILAN_P_MM,
    cl_mm: float = VARSAYILAN_CL_MM,
    cs_mm: float = VARSAYILAN_CS_MM,
) -> LandPatternSonucu:
    """SOIC/TSOP/QFP (gullwing lead) paketleri için IPC-7351B land pattern.

    Dönen `LandPatternSonucu.pad_araligi_mm`, KARŞIT İKİ SIRA arasındaki
    (lead span'e bağlı) mesafedir — aynı sıra içindeki pad'ler arası mesafe
    `komponent.pitch_mm`'dir, bu fonksiyon onu HESAPLAMAZ.
    """
    return _zmax_gmin_xmax_hesapla(
        komponent.lead_span_nom_mm, komponent.lead_genislik_nom_mm,
        komponent.lead_uzunluk_nom_mm, komponent.tolerans_mm,
        _FILLET_MM[yogunluk], f_mm, p_mm, cl_mm, cs_mm, yogunluk,
    )


# ------------------------------------------------------------------
# QFN (no-lead, pull-back terminal) — gullwing ile AYNI matematik, FARKLI
# fillet tablosu
# ------------------------------------------------------------------
#
# QFN'de görünür bir "gullwing" bacak YOK — terminal gövdeyle hizalı (flush)
# veya hafifçe içeri çekik (pull-back). Bu yüzden toe fillet (Jt) gullwing'e
# göre BELİRGİN KÜÇÜKTÜR (pad, lead'i çok az aşar). Aşağıdaki değerler
# YAYGIN YAYIMLANMIŞ tipik QFN varsayılanlarıdır — dosyanın en başındaki
# DÜRÜSTLÜK NOTU'yla AYNI disiplin: sign-off için yeterli değildir, kritik/
# yoğun bir QFN'de gerçek IPC-7351B QFN tablosu veya üretici land pattern
# önerisiyle ÇAPRAZ DOĞRULANMALI.
_FILLET_MM_QFN = {
    YogunlukSeviyesi.A_MAKSIMUM: {"Jt": 0.30, "Jh": 0.00, "Js": 0.05},
    YogunlukSeviyesi.B_NOMINAL: {"Jt": 0.20, "Jh": 0.00, "Js": 0.03},
    YogunlukSeviyesi.C_MINIMUM: {"Jt": 0.10, "Jh": 0.00, "Js": 0.01},
}


def qfn_land_pattern_hesapla(
    komponent: GullwingKomponentBoyutlari,
    yogunluk: YogunlukSeviyesi = YogunlukSeviyesi.B_NOMINAL,
    f_mm: float = VARSAYILAN_F_MM,
    p_mm: float = VARSAYILAN_P_MM,
    cl_mm: float = VARSAYILAN_CL_MM,
    cs_mm: float = VARSAYILAN_CS_MM,
) -> LandPatternSonucu:
    """QFN (no-lead) paketleri için IPC-7351B land pattern — `komponent.
    lead_span_nom_mm` burada gövde/terminal DIŞ açıklığıdır (QFN'de lead
    span ≈ gövde boyutu, gullwing'deki gibi gövdeden taşan bacak yoktur).
    `GullwingKomponentBoyutlari` PAYLAŞILIR (aynı alan seti yeterli) — ayrı
    bir dataclass açmak sahte bir fark yaratırdı; TEK fark fillet tablosudur.
    """
    return _zmax_gmin_xmax_hesapla(
        komponent.lead_span_nom_mm, komponent.lead_genislik_nom_mm,
        komponent.lead_uzunluk_nom_mm, komponent.tolerans_mm,
        _FILLET_MM_QFN[yogunluk], f_mm, p_mm, cl_mm, cs_mm, yogunluk,
    )


# ------------------------------------------------------------------
# BGA — TAMAMEN FARKLI formül ailesi (toe/heel/side fillet YOK)
# ------------------------------------------------------------------

@dataclass
class BgaKomponentBoyutlari:
    """Datasheet'ten alınan BGA top/ball boyutları (mm)."""

    pin_sayisi: int
    pitch_mm: float
    top_capi_nom_mm: float  # ball/top çapı (nominal)


@dataclass
class BgaLandPatternSonucu:
    pad_capi_mm: float
    pitch_mm: float
    maske_tipi: str  # "NSMD" | "SMD"


def bga_land_pattern_hesapla(
    komponent: BgaKomponentBoyutlari, maske_tipi: str = "NSMD",
) -> BgaLandPatternSonucu:
    """BGA pad çapı, toe/heel/side fillet formülüyle DEĞİL, top/ball
    çapının bir ORANI olarak belirlenir (IPC-7351B'nin BGA'ya özgü,
    2-terminal/gullwing'den TAMAMEN AYRI yaklaşımı):
      - NSMD (non-solder-mask-defined, yaygın — bakır kendisi pad sınırını
        belirler, iyi kendinden-hizalama): pad_capi = 0.80 * top_capi_nom
      - SMD (solder-mask-defined, daha az yaygın — mask açıklığı bakırdan
        küçük tutulup pad sınırını belirler): pad_capi = 1.00 * top_capi_nom

    DÜRÜSTLÜK NOTU (dosyanın geri kalanıyla AYNI disiplin): 0.80/1.00
    çarpanları IPC-7351B'nin YAYGIN YAYIMLANMIŞ pratik kurallarıdır, kesin
    bir fiziksel sabit DEĞİL — kritik/yoğun bir BGA'da gerçek IPC-7351B BGA
    tablosu veya JEDEC/üretici land pattern önerisiyle ÇAPRAZ DOĞRULANMALI.
    """
    if maske_tipi not in ("NSMD", "SMD"):
        raise ValueError(f"maske_tipi 'NSMD' veya 'SMD' olmalı, verildi: {maske_tipi!r}")

    carpan = 0.80 if maske_tipi == "NSMD" else 1.00
    pad_capi = round(komponent.top_capi_nom_mm * carpan, 4)
    if pad_capi <= 0:
        raise ValueError(f"top_capi_nom_mm pozitif olmalı, verildi: {komponent.top_capi_nom_mm}")

    return BgaLandPatternSonucu(pad_capi_mm=pad_capi, pitch_mm=komponent.pitch_mm, maske_tipi=maske_tipi)


# ------------------------------------------------------------------
# Yaygın paket boyutları (mm) — EIA/IEC isimlendirmesiyle, datasheet
# yoksa hızlı başlangıç için. GERÇEK PROJEDE datasheet boyutu esastır,
# bu tablo yalnızca "hiçbir veri yoksa" kaba bir başlangıçtır.
# ------------------------------------------------------------------
YAYGIN_CIP_PAKETLERI_MM = {
    "0201": CipKomponentBoyutlari(0.60, 0.30, 0.10, tolerans_mm=0.03),
    "0402": CipKomponentBoyutlari(1.00, 0.50, 0.25, tolerans_mm=0.05),
    "0603": CipKomponentBoyutlari(1.60, 0.80, 0.35, tolerans_mm=0.05),
    "0805": CipKomponentBoyutlari(2.00, 1.25, 0.40, tolerans_mm=0.10),
    "1206": CipKomponentBoyutlari(3.20, 1.60, 0.50, tolerans_mm=0.10),
}


def paket_isminden_hesapla(
    paket: str, yogunluk: YogunlukSeviyesi = YogunlukSeviyesi.B_NOMINAL
) -> LandPatternSonucu:
    """`YAYGIN_CIP_PAKETLERI_MM` tablosundan bilinen bir paket ismiyle
    (ör. "0402") doğrudan land pattern hesaplar. Bilinmeyen paket ->
    `KeyError` (uydurma boyut YOK, gerçek datasheet gerekir)."""
    if paket not in YAYGIN_CIP_PAKETLERI_MM:
        raise KeyError(
            f"'{paket}' tanınan paketler arasında değil "
            f"({sorted(YAYGIN_CIP_PAKETLERI_MM)}). Datasheet'ten "
            "CipKomponentBoyutlari elle oluşturup land_pattern_hesapla() çağır."
        )
    return land_pattern_hesapla(YAYGIN_CIP_PAKETLERI_MM[paket], yogunluk)
