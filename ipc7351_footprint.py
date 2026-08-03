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

    NOT: Bu formül gullwing/QFN/BGA gibi çok-pinli paketlere UYGULANMAZ —
    onlar için ayrı (pin-pitch bazlı) IPC-7351 hesap yolu gerekir; bu modül
    şimdilik yalnızca 2-terminalli çip paketleri kapsıyor (`TBD: QFN/BGA`).
    """
    l_min = komponent.uzunluk_nom_mm - komponent.tolerans_mm
    l_maks = komponent.uzunluk_nom_mm + komponent.tolerans_mm
    w_min = komponent.genislik_nom_mm - komponent.tolerans_mm
    t_nom = komponent.terminasyon_nom_mm

    fillet = _FILLET_MM[yogunluk]
    kok_terim_uzun = math.sqrt(cl_mm ** 2 + f_mm ** 2 + p_mm ** 2)
    kok_terim_yan = math.sqrt(cs_mm ** 2 + f_mm ** 2 + p_mm ** 2)

    s_maks = l_maks - 2 * t_nom  # terminasyonlar arası iç (heel-to-heel) mesafe

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
