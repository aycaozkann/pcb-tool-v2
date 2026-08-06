"""
PCB Katman Sayısı ve Stackup (Dizilim) Belirleme Aracı
========================================================
Şematikten gelen sinyal ve komponent bilgilerine bakarak:
  1) Kaç katmanlı bir PCB gerektiğini hesaplar
  2) Katman dizilimini (stackup) oluşturur
  3) Elektriksel kuralları (dönüş yolu, güç bütünlüğü, crosstalk) doğrular
  4) Üretim/mekanik kısıtları (kalınlık, termal, bakır dengesi) doğrular
  5) Hata varsa katman sayısını artırıp tekrar dener, sonuca ulaşınca raporlar

Bu dosya baştan sona çalıştırılabilir gerçek Python kodudur (örnek veriyle).
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Tuple

from empedans_cozucu import stackup_tara
from bulgu_sozlesmesi import Bulgu, bulgu_uret


# ------------------------------------------------------------------
# 1. VERİ YAPILARI
# ------------------------------------------------------------------

class SinyalTuru(Enum):
    GUC = auto()
    GND = auto()
    HIZLI_DIJITAL = auto()
    YAVAS_DIJITAL = auto()
    ANALOG = auto()
    RF = auto()


class KilifTuru(Enum):
    STANDART = auto()
    DIP = auto()
    QFN = auto()
    BGA = auto()
    FINE_PITCH_BGA = auto()


class ViaTipi(Enum):
    SADECE_BOYDAN_BOYA = auto()
    KOR_VE_GOMULU_IZINLI = auto()


class AraBirimTuru(Enum):
    """Yüksek hızlı arayüz tipi — differential pair empedans hedefini belirler."""
    USB2_0 = auto()
    USB3_x = auto()
    HDMI = auto()
    ETHERNET_1G = auto()
    LVDS = auto()
    PCIE = auto()
    DDR3_4 = auto()  # tipik olarak single-ended ama uzunluk eşleştirme kritik
    MIPI_CSI2_DPHY = auto()  # kamera sensörü <-> SoC (OG05B10 vb.)


class FrekansBandi(Enum):
    """RF/kablosuz anten ve hat kuralları için frekans bandı."""
    WIFI_BLE_2_4GHZ = auto()
    WIFI_5GHZ = auto()
    SUBGHZ_433 = auto()
    SUBGHZ_868_915 = auto()
    GPS_L1 = auto()


@dataclass
class Net:
    isim: str
    tur: SinyalTuru
    empedans_kontrolu_gerekli_mi: bool = False
    maks_akim: float = 0.0


@dataclass
class Komponent:
    isim: str
    kilif_turu: KilifTuru
    pin_sayisi: int = 0
    guc_pini_sayisi: int = 0          # IC üzerindeki ayrı güç (VDD/VCC) pin sayısı
    dekuplaj_kapasitor_sayisi: int = 0  # bu komponent için tanımlanmış decoupling kapasitör adedi


@dataclass
class MekanikVeTermalKisitlar:
    hedef_kalinlik_mm: float = 1.6
    maks_isi_yayilimi_W: float = 1.0
    kabul_edilen_via_tipi: ViaTipi = ViaTipi.KOR_VE_GOMULU_IZINLI
    bakir_denge_toleransi: float = 15.0  # yüzde


@dataclass
class DiferansiyelCift:
    """Bir differential pair (örn. USB_DP/USB_DM) için tasarım verisi."""
    isim: str
    arayuz: AraBirimTuru
    uzunluk_pozitif_mm: float
    uzunluk_negatif_mm: float
    veri_hizi_Gbps: float = 0.0
    hedef_empedans_ohm_override: float = 0.0  # 0 ise arayüze göre otomatik atanır


@dataclass
class ViaKullanimi:
    """Bir sinyalin gerçekten kullandığı katman aralığı — via stub hesabı için."""
    net_isim: str
    baslangic_katman: int
    bitis_katman: int
    veri_hizi_Gbps: float


@dataclass
class AntenYerlesimi:
    """Bir anten (chip anten veya PCB trace anten) için yerleşim verisi."""
    isim: str
    frekans_bandi: FrekansBandi
    kenara_mesafe_mm: float          # anten ile kart kenarı arası mesafe
    en_yakin_bakir_mesafe_mm: float  # anten ile en yakın bakır dökümü/GND arası mesafe


@dataclass
class KristalYerlesimi:
    """Bir kristal/osilatör için yerleşim verisi."""
    isim: str
    ic_pinine_mesafe_mm: float           # ilgili IC'nin XTAL pinlerine mesafe
    gurultu_kaynagina_mesafe_mm: float   # en yakın hızlı/RF/switching sinyale mesafe
    guard_ring_var_mi: bool = False      # kristal etrafında GND guard ring var mı


@dataclass
class RFHattiStitching:
    """Bir RF iz hattı boyunca GND stitching via yerleşimi."""
    isim: str
    frekans_GHz: float
    stitching_via_araligi_mm: float


@dataclass
class YalitimGereksinimi:
    """İki net arasındaki yüksek voltaj yalıtımı (creepage/clearance) gereksinimi."""
    isim: str
    gerilim_farki_V: float
    tasarim_mesafesi_mm: float  # tasarımdaki gerçek fiziksel mesafe


@dataclass
class YuksekAkimIzi:
    """Güç elektroniği hattı için akım/genişlik/bakır kalınlığı verisi."""
    isim: str
    akim_A: float
    mevcut_genislik_mm: float
    dis_katman_mi: bool = True


@dataclass
class TermalYonetim:
    """Bir komponentin ısı yayılımı ve mevcut termal via sayısı."""
    isim: str
    guc_yayilimi_W: float
    mevcut_termal_via_sayisi: int


# ------------------------------------------------------------------
# 2. SİNYALLERİ GRUPLAMA
# ------------------------------------------------------------------

def sinyalleri_grupla(tum_sinyaller: List[Net]) -> Dict[str, List[Net]]:
    hafiza = {
        "Guc_Alanlari": [],
        "GND_Alanlari": [],
        "Kritik_Sinyaller": [],
        "RF_Sinyaller": [],
        "Analog_Sinyaller": [],
        "Standart_IO": [],
    }

    for sinyal in tum_sinyaller:
        if sinyal.tur == SinyalTuru.GUC:
            hafiza["Guc_Alanlari"].append(sinyal)
        elif sinyal.tur == SinyalTuru.GND:
            hafiza["GND_Alanlari"].append(sinyal)
        elif sinyal.tur == SinyalTuru.RF:
            # RF, kritik sinyallerin bir alt kümesi olarak da sayılır (dönüş yolu
            # kuralları RF için de geçerlidir) ama ayrıca kendi grubunda izlenir.
            hafiza["RF_Sinyaller"].append(sinyal)
            hafiza["Kritik_Sinyaller"].append(sinyal)
        elif sinyal.tur == SinyalTuru.HIZLI_DIJITAL:
            hafiza["Kritik_Sinyaller"].append(sinyal)
        elif sinyal.tur == SinyalTuru.ANALOG:
            hafiza["Analog_Sinyaller"].append(sinyal)
        else:  # YAVAS_DIJITAL ve diğerleri
            hafiza["Standart_IO"].append(sinyal)

    return hafiza


# ------------------------------------------------------------------
# 3. KATMAN SAYISINI BELİRLEME ALGORİTMASI
# ------------------------------------------------------------------

def bga_var_mi(komponentler: List[Komponent], hedef: KilifTuru) -> bool:
    return any(k.kilif_turu == hedef for k in komponentler)


def katman_sayisini_hesapla(hafiza: Dict[str, List[Net]], komponentler: List[Komponent]) -> int:
    hedef_katman = 2  # en ucuz başlangıç noktası

    # Kural 1: Fiziksel imkansızlık (Fine-Pitch BGA kaçış yolları)
    fine_pitch_sayisi = sum(1 for k in komponentler if k.kilif_turu == KilifTuru.FINE_PITCH_BGA)
    if fine_pitch_sayisi >= 1:
        hedef_katman = max(hedef_katman, 8)

    # Kural 1b: Birden fazla Fine-Pitch BGA veya çok yüksek pin sayısı
    # (kaçış yolları üst üste biner, tek yönlü routing yetmez)
    toplam_bga_pin = sum(
        k.pin_sayisi for k in komponentler if k.kilif_turu == KilifTuru.FINE_PITCH_BGA
    )
    if fine_pitch_sayisi >= 2 or toplam_bga_pin > 600:
        hedef_katman = max(hedef_katman, 10)

    # Kural 2: Empedans ve dönüş yolu
    if len(hafiza["Kritik_Sinyaller"]) > 0:
        hedef_katman = max(hedef_katman, 4)

    # Kural 2b: RF sinyalleri özel izolasyon ister (RF katmanının her iki
    # tarafında da GND olması gerekir → en az 6 katman gerekir ki RF
    # gömülebilsin ve iki ayrı GND referansı olsun)
    if len(hafiza["RF_Sinyaller"]) > 0:
        hedef_katman = max(hedef_katman, 6)

    # Kural 3: Güç bütünlüğü (çoklu voltaj + çok sayıda kritik sinyal)
    if len(hafiza["Guc_Alanlari"]) >= 3 and len(hafiza["Kritik_Sinyaller"]) > 10:
        hedef_katman = max(hedef_katman, 6)

    # Kural 3b: Yüksek akımlı güç hatları (>3A) ayrı/kalın bakır düzlem ister
    yuksek_akimli_hat_var_mi = any(n.maks_akim > 3.0 for n in hafiza["Guc_Alanlari"])
    if yuksek_akimli_hat_var_mi and len(hafiza["Guc_Alanlari"]) >= 2:
        hedef_katman = max(hedef_katman, 6)

    return hedef_katman


# ------------------------------------------------------------------
# 4. STACKUP (KATMAN DİZİLİMİ) ATAMASI
# ------------------------------------------------------------------

def dizilimi_olustur(katman_sayisi: int, hafiza: Dict[str, List[Net]]) -> Dict[str, str]:
    stackup: Dict[str, str] = {}

    cok_kritik_sinyal_esigi = 15  # "Cok_Fazla" yerine somut bir sayı kullanıyoruz

    if katman_sayisi == 2:
        stackup["Katman_1"] = "SİNYAL + GÜÇ (karışık, referans zayıf)"
        stackup["Katman_2"] = "GND (tüm dönüş yolu tek katmanda)"

    elif katman_sayisi == 4:
        stackup["Katman_1"] = "SİNYAL (Öncelik: Kritik_Sinyaller ve Analog)"
        stackup["Katman_2"] = "GND (Katman 1'in referansı)"
        stackup["Katman_3"] = "GÜÇ (Katman 4'ün referansı, Katman 2 ile kapasitans)"
        stackup["Katman_4"] = "SİNYAL (Öncelik: Standart_IO)"

    elif katman_sayisi == 6:
        if len(hafiza["Kritik_Sinyaller"]) > cok_kritik_sinyal_esigi:
            # Kalkanlama (shielding) kuralı
            stackup["Katman_1"] = "SİNYAL (Standart)"
            stackup["Katman_2"] = "GND"
            stackup["Katman_3"] = "SİNYAL (En kritikler buraya gömülür)"
            stackup["Katman_4"] = "GND veya GÜÇ (Katman 3'ü alttan kalkanlar)"
            stackup["Katman_5"] = "GÜÇ (Geri kalan voltajlar)"
            stackup["Katman_6"] = "SİNYAL (Standart)"
        else:
            stackup["Katman_1"] = "SİNYAL (Kritik/Analog)"
            stackup["Katman_2"] = "GND"
            stackup["Katman_3"] = "SİNYAL (Standart_IO)"
            stackup["Katman_4"] = "GÜÇ"
            stackup["Katman_5"] = "GND"
            stackup["Katman_6"] = "SİNYAL (Standart_IO)"

    else:
        # 8 ve üzeri katmanlar için genel bir şablon: dış katmanlar sinyal,
        # kritik sinyaller iki GND arasına gömülür, güç katmanları ortalarda.
        stackup["Katman_1"] = "SİNYAL (Kritik/Analog - dış)"
        stackup["Katman_2"] = "GND"
        kalan = katman_sayisi - 4
        orta_sinyal_sayisi = max(1, kalan // 2)
        idx = 3
        for i in range(orta_sinyal_sayisi):
            stackup[f"Katman_{idx}"] = "SİNYAL (Gömülü, GND ile korumalı)"
            idx += 1
            stackup[f"Katman_{idx}"] = "GÜÇ" if i % 2 == 0 else "GND"
            idx += 1
        # Kalan katmanları GND/GÜÇ ile doldur, son iki katman dış sinyal
        while idx <= katman_sayisi - 2:
            stackup[f"Katman_{idx}"] = "GÜÇ"
            idx += 1
        stackup[f"Katman_{katman_sayisi - 1}"] = "GND"
        stackup[f"Katman_{katman_sayisi}"] = "SİNYAL (Standart_IO - dış)"

    return stackup


# ------------------------------------------------------------------
# 5. ÇAPRAZ DOĞRULAMA (ELEKTRİKSEL DRC)
# ------------------------------------------------------------------

def capraz_dogrulama_yap(
    stackup: Dict[str, str], hafiza: Dict[str, List[Net]], katman_sayisi: int
) -> Tuple[List[str], List[str]]:
    hatalar: List[str] = []
    uyarilar: List[str] = []

    # KONTROL 1: Dönüş yolu (return path) doğrulaması
    if len(hafiza["Kritik_Sinyaller"]) > 0:
        if "GND" not in stackup.get("Katman_2", ""):
            hatalar.append(
                "KRİTİK HATA: Katman 1'deki hızlı sinyaller için L2'de temiz bir GND dönüş yolu yok!"
            )

    # KONTROL 2: Güç düzlemi parçalanma doğrulaması
    guc_katmani_sayisi = sum(1 for v in stackup.values() if "GÜÇ" in v)
    if len(hafiza["Guc_Alanlari"]) >= 4 and guc_katmani_sayisi < 2:
        hatalar.append(
            "KRİTİK HATA: Tek bir GÜÇ katmanında 4 farklı voltaj bölünemez. EMI yayılımı felaket olur!"
        )

    # KONTROL 3: Crosstalk (çapraz karışma) doğrulaması
    for i in range(1, katman_sayisi):
        mevcut = stackup.get(f"Katman_{i}", "")
        sonraki = stackup.get(f"Katman_{i + 1}", "")
        if "SİNYAL" in mevcut and "SİNYAL" in sonraki:
            uyarilar.append(
                f"UYARI: Katman {i} ve {i + 1} yan yana sinyal. Çizerken bu yolları birbirine "
                f"DİK (X ve Y ekseninde) çiz!"
            )

    # KONTROL 4: RF izolasyon doğrulaması
    # RF sinyali varsa en az 6 katman olmalı ki RF, iki GND arasına gömülebilsin.
    if len(hafiza["RF_Sinyaller"]) > 0:
        if katman_sayisi < 6:
            hatalar.append(
                "KRİTİK HATA: RF sinyalleri var ama katman sayısı RF'i iki GND arasına "
                "gömmeye yetmiyor (min. 6 katman gerekir)."
            )

    return hatalar, uyarilar


# ------------------------------------------------------------------
# 6. FİZİKSEL / ÜRETİM DOĞRULAMASI (DFM)
# ------------------------------------------------------------------

def termal_katman_ihtiyaci(kisitlar: MekanikVeTermalKisitlar, mevcut_katman: int) -> int:
    if kisitlar.maks_isi_yayilimi_W > 5.0 and mevcut_katman < 6:
        return mevcut_katman + 2
    return mevcut_katman


def uretim_limiti_kontrolu(
    komponentler: List[Komponent], kisitlar: MekanikVeTermalKisitlar, mevcut_katman: int
) -> int:
    if bga_var_mi(komponentler, KilifTuru.FINE_PITCH_BGA):
        if kisitlar.kabul_edilen_via_tipi == ViaTipi.SADECE_BOYDAN_BOYA:
            return max(mevcut_katman, 10)
    return mevcut_katman


def bakir_dengesi_kontrolu(stackup: Dict[str, str], katman_sayisi: int) -> float:
    """
    Basitleştirilmiş bakır yoğunluk dengesi kontrolü.
    Üst yarı ve alt yarıdaki 'dolu' (SİNYAL/GÜÇ) katman oranını kıyaslar.
    Gerçek üretimde bu, kopper-pour alan yüzdeleriyle hesaplanır; burada
    stackup türlerine dayalı basit bir yoğunluk skoru kullanıyoruz.
    """
    yogunluk_skoru = {"SİNYAL": 1.0, "GÜÇ": 0.9, "GND": 0.6}

    def skor(tur_metni: str) -> float:
        for anahtar, deger in yogunluk_skoru.items():
            if anahtar in tur_metni:
                return deger
        return 0.5

    orta = katman_sayisi / 2
    ust_toplam = 0.0
    alt_toplam = 0.0
    for i in range(1, katman_sayisi + 1):
        deger = skor(stackup.get(f"Katman_{i}", ""))
        if i <= orta:
            ust_toplam += deger
        else:
            alt_toplam += deger

    ust_yogunluk = (ust_toplam / (katman_sayisi / 2)) * 100
    alt_yogunluk = (alt_toplam / (katman_sayisi / 2)) * 100
    return abs(ust_yogunluk - alt_yogunluk)


def fiziksel_dogrulama_yap(
    stackup: Dict[str, str],
    kisitlar: MekanikVeTermalKisitlar,
    komponentler: List[Komponent],
    katman_sayisi: int,
) -> List[str]:
    hatalar: List[str] = []

    # KONTROL 1: Mekanik kalınlık çakışması
    min_olasi_kalinlik = katman_sayisi * 0.15  # her katman ort. 0.15mm
    if min_olasi_kalinlik > kisitlar.hedef_kalinlik_mm:
        hatalar.append(
            f"MEKANİK HATA: {katman_sayisi} katmanlı yapı, "
            f"{kisitlar.hedef_kalinlik_mm}mm kalınlığa sığmaz "
            f"(min. gerekli ~{min_olasi_kalinlik:.2f}mm)!"
        )

    # KONTROL 2: Bükülme (warping) riski
    bakir_farki = bakir_dengesi_kontrolu(stackup, katman_sayisi)
    if bakir_farki > kisitlar.bakir_denge_toleransi:
        hatalar.append(
            f"ÜRETİM HATASI: Bakır dağılımı asimetrik (fark: %{bakir_farki:.1f}, "
            f"tolerans: %{kisitlar.bakir_denge_toleransi}). Kart lehim fırınında bükülecektir. "
            f"Boş katmanlara (thieving) bakır dökümü ekle."
        )

    # KONTROL 3: Via aspect ratio (delme oranı) doğrulaması
    # Standart minimum via çapı ~0.2mm kabul edilir. Endüstri genel kuralı,
    # boydan-boya via için delme oranının (kalınlık / çap) 8:1'i geçmemesidir;
    # bu aşılırsa fabrika via'yı güvenilir şekilde metalize edemez.
    varsayilan_min_via_capi_mm = 0.2
    maks_izinli_aspect_ratio = 8.0
    if kisitlar.kabul_edilen_via_tipi == ViaTipi.SADECE_BOYDAN_BOYA:
        gerekli_oran = kisitlar.hedef_kalinlik_mm / varsayilan_min_via_capi_mm
        if gerekli_oran > maks_izinli_aspect_ratio:
            hatalar.append(
                f"ÜRETİM HATASI: Boydan-boya via delme oranı {gerekli_oran:.1f}:1, "
                f"izinli {maks_izinli_aspect_ratio:.0f}:1 sınırını aşıyor. Kör/gömülü "
                f"via'ya izin verilmeli ya da kart kalınlığı azaltılmalı."
            )

    return hatalar


# ------------------------------------------------------------------
# 6b. HDI VIA TİPİ ASPECT-RATIO DOĞRULAMASI (via_siniflandirma.py GENİŞLETMESİ)
# ------------------------------------------------------------------
#
# NOT (döngüsel import): `via_siniflandirma.py` bu dosyadaki
# `KATMAN_KALINLIK_VARSAYIMI_MM`'i import ediyor (tek yönlü bağımlılık).
# Bu fonksiyonun `Via`/`ViaTipiDetay` tipine ihtiyacı olduğu için import
# BURADA, FONKSİYON GÖVDESİ İÇİNDE (deferred/local) yapılır — döngüsel
# import'u kırmanın standart yolu, modül seviyesinde YAPILMAZ.

def via_tipi_aspect_ratio_kontrolu(via: "Via") -> Bulgu:  # noqa: F821 (deferred import)
    """Tek bir via'nın GERÇEK tipine (`ViaTipiDetay`) göre aspect-ratio
    sınırını doğrular — `fiziksel_dogrulama_yap`'taki KONTROL 3'ün
    board-genel/politika seviyesindeki 8:1 sınırından FARKLI: burada her
    via KENDİ tipine göre (KOR/GOMULU/MIKROVIA için 1:1, BOYDAN_BOYA için
    `maks_izinli_aspect_ratio` ile AYNI 8:1 sabiti — DEĞİŞTİRİLMEDİ)
    değerlendirilir.
    """
    from via_siniflandirma import ViaTipiDetay  # noqa: F401 (tip kontrolü/okunabilirlik)

    sinir = via.maks_izinli_aspect_oran
    oran = via.aspect_oran
    ihlaller = []
    if oran > sinir:
        ihlaller.append({
            "via_net": via.net_isim,
            "via_tipi": via.tipi.name,
            "olculen_aspect_oran": round(oran, 3),
            "izinli_sinir": sinir,
            "baslangic_katman": via.baslangic_katman,
            "bitis_katman": via.bitis_katman,
            "matkap_capi_mm": via.matkap_capi_mm,
        })
    return bulgu_uret(
        "via_tipi_aspect_ratio",
        taranan=1,
        ihlaller=ihlaller,
        detay=(
            f"{via.tipi.name} via için izinli aspect ratio {sinir:.0f}:1 "
            f"(KOR/GOMULU/MIKROVIA lazer/kör delik teknolojisi ~1:1 gerektirir, "
            f"BOYDAN_BOYA mekanik delik 8:1'e kadar güvenilir metalize olur)."
        ),
    )


# ------------------------------------------------------------------
# 7. FAZ 1: İZ GENİŞLİĞİ / AKIM HESABI (IPC-2221 YAKLAŞIK FORMÜLÜ)
# ------------------------------------------------------------------
#
# NOT: Bu, tam IPC-2152 grafik/tablo setinin YERİNE DEĞİL, onun yaygın
# kullanılan basitleştirilmiş öncülü olan IPC-2221 ampirik formülünün
# uygulamasıdır. IPC-2152, hava akışı, komşu iz sıcaklığı ve karmaşık
# katman etkileşimlerini de hesaba katan çok daha ayrıntılı eğrilerden
# oluşur ve burada tam olarak modellenmemiştir. Kritik/yüksek akımlı
# tasarımlarda bu sonucu sadece bir İLK TAHMİN olarak kullan; gerçek
# üretim öncesi bir alan çözücü (field solver) veya üreticinin resmi
# hesap aracıyla doğrula.

def iz_genisligi_hesapla_mm(
    akim_A: float,
    sicaklik_artisi_C: float = 10.0,
    bakir_agirligi_oz: float = 1.0,
    dis_katman_mi: bool = True,
) -> float:
    """
    IPC-2221 formülü: A = (I / (k * dT^0.44)) ^ (1/0.725)
    A: kesit alanı (mil^2), I: akım (A), dT: izin verilen sıcaklık artışı (°C)
    k: dış katman için 0.048, iç katman için 0.024 (iç katmanlar ısıyı daha
    zor atar, bu yüzden aynı akım için daha geniş iz ister)
    """
    if akim_A <= 0:
        return 0.0

    k = 0.048 if dis_katman_mi else 0.024
    b = 0.44
    c = 0.725

    alan_mil2 = (akim_A / (k * (sicaklik_artisi_C ** b))) ** (1 / c)

    # 1 oz bakır ≈ 1.378 mil kalınlık (35 mikron)
    kalinlik_mil = bakir_agirligi_oz * 1.378
    genislik_mil = alan_mil2 / kalinlik_mil
    genislik_mm = genislik_mil * 0.0254
    return genislik_mm


def guc_hatlari_icin_iz_genisligi_kontrolu(
    hafiza: Dict[str, List[Net]],
    bakir_agirligi_oz: float = 1.0,
    sicaklik_artisi_C: float = 10.0,
) -> Dict[str, float]:
    """Her güç/yüksek akımlı net için önerilen minimum dış katman iz genişliğini (mm) döndürür."""
    oneriler: Dict[str, float] = {}
    for net in hafiza["Guc_Alanlari"]:
        if net.maks_akim > 0:
            oneriler[net.isim] = iz_genisligi_hesapla_mm(
                net.maks_akim, sicaklik_artisi_C, bakir_agirligi_oz, dis_katman_mi=True
            )
    return oneriler


# ------------------------------------------------------------------
# 8. FAZ 1: FABRİKA (ÜRETİCİ) DFM PROFİLLERİ
# ------------------------------------------------------------------
#
# NOT: Aşağıdaki sayılar TEMSİLİDİR — gerçek üretime geçmeden önce
# seçtiğin üreticinin GÜNCEL yetenek sayfasından (capabilities page)
# doğrula; bu değerler zamanla değişir ve üretici/opsiyona göre farklılık
# gösterir.

@dataclass
class FabrikaProfili:
    isim: str
    min_iz_genisligi_mm: float
    min_iz_araligi_mm: float
    min_delik_capi_mm: float
    min_yillik_halka_mm: float  # minimum annular ring
    maks_aspect_ratio: float = 8.0


FABRIKA_PROFILLERI: Dict[str, FabrikaProfili] = {
    "JLCPCB_STANDART": FabrikaProfili(
        isim="JLCPCB Standart",
        min_iz_genisligi_mm=0.127,
        min_iz_araligi_mm=0.127,
        min_delik_capi_mm=0.3,
        min_yillik_halka_mm=0.13,
        maks_aspect_ratio=8.0,
    ),
    "JLCPCB_GELISMIS": FabrikaProfili(
        isim="JLCPCB Gelişmiş (Advanced)",
        min_iz_genisligi_mm=0.09,
        min_iz_araligi_mm=0.09,
        min_delik_capi_mm=0.2,
        min_yillik_halka_mm=0.1,
        maks_aspect_ratio=10.0,
    ),
    "PCBWAY_STANDART": FabrikaProfili(
        isim="PCBWay Standart",
        min_iz_genisligi_mm=0.09,
        min_iz_araligi_mm=0.09,
        min_delik_capi_mm=0.25,
        min_yillik_halka_mm=0.125,
        maks_aspect_ratio=8.0,
    ),
}


def fabrika_dfm_kontrolu(
    tasarim_iz_genisligi_mm: float,
    tasarim_iz_araligi_mm: float,
    tasarim_delik_capi_mm: float,
    profil: FabrikaProfili,
) -> List[str]:
    hatalar: List[str] = []

    if tasarim_iz_genisligi_mm < profil.min_iz_genisligi_mm:
        hatalar.append(
            f"DFM HATASI ({profil.isim}): İz genişliği {tasarim_iz_genisligi_mm}mm, "
            f"minimum {profil.min_iz_genisligi_mm}mm'nin altında."
        )

    if tasarim_iz_araligi_mm < profil.min_iz_araligi_mm:
        hatalar.append(
            f"DFM HATASI ({profil.isim}): İz aralığı {tasarim_iz_araligi_mm}mm, "
            f"minimum {profil.min_iz_araligi_mm}mm'nin altında."
        )

    if tasarim_delik_capi_mm < profil.min_delik_capi_mm:
        hatalar.append(
            f"DFM HATASI ({profil.isim}): Delik çapı {tasarim_delik_capi_mm}mm, "
            f"minimum {profil.min_delik_capi_mm}mm'nin altında."
        )

    return hatalar


# ------------------------------------------------------------------
# 9. FAZ 1: DECOUPLING (BAYPAS) KAPASİTÖR KURALI
# ------------------------------------------------------------------

def dekuplaj_kontrolu(komponentler: List[Komponent]) -> List[str]:
    """
    Basit kural: her güç pini için en az 1 adet yakın decoupling kapasitörü
    (tipik 100nF) olmalı. Bu, gerçek yerleşim mesafesini değil sadece SAYIYI
    kontrol eder — kapasitörün pine gerçekten yakın (birkaç mm) yerleştirilmesi
    ayrı bir yerleşim/routing kontrolüdür ve burada modellenmemiştir.
    """
    hatalar: List[str] = []
    for k in komponentler:
        if k.guc_pini_sayisi > 0 and k.dekuplaj_kapasitor_sayisi < k.guc_pini_sayisi:
            hatalar.append(
                f"DEKUPLAJ HATASI: {k.isim} için {k.guc_pini_sayisi} güç pini var ama "
                f"sadece {k.dekuplaj_kapasitor_sayisi} decoupling kapasitör tanımlı. "
                f"Her güç pinine en az 1 adet (tipik 100nF) yakın kapasitör ekle."
            )
        # Yüksek pin sayılı (BGA/QFN gibi) komponentler için ek bulk kapasitör önerisi
        if k.pin_sayisi >= 100 and k.dekuplaj_kapasitor_sayisi < (k.guc_pini_sayisi + 1):
            hatalar.append(
                f"BULK KAPASİTÖR UYARISI: {k.isim} yüksek pinli bir komponent; ani akım "
                f"talepleri için decoupling kapasitörlerine ek olarak en az 1 adet bulk "
                f"kapasitör (10-100uF) eklenmesi önerilir."
            )
    return hatalar


# ------------------------------------------------------------------
# 10. FAZ 2: DIFFERENTIAL PAIR EMPEDANS HEDEFİ
# ------------------------------------------------------------------
#
# NOT: Aşağıdaki değerler yaygın endüstri hedefleridir (arayüz özel şart-
# namelerinden). Gerçek tasarımda kart kalınlığı, dielektrik sabiti ve iz
# geometrisine göre bir alan çözücü (field solver / stackup calculator) ile
# DOĞRULANMALIDIR — bu sadece hedefi hatırlatan bir referans tablosudur.

ARAYUZ_EMPEDANS_HEDEFLERI: Dict[AraBirimTuru, float] = {
    AraBirimTuru.USB2_0: 90.0,
    AraBirimTuru.USB3_x: 90.0,
    AraBirimTuru.HDMI: 100.0,
    AraBirimTuru.ETHERNET_1G: 100.0,
    AraBirimTuru.LVDS: 100.0,
    AraBirimTuru.PCIE: 85.0,
    AraBirimTuru.DDR3_4: 40.0,  # single-ended karakteristik empedans (yaklaşık)
    # 100Ω ±10%: birden fazla bağımsız kaynakta (Cadence MIPI PCB tasarım
    # rehberi, MIPI DSI/D-PHY layout notları) tutarlı — önceden bu satır
    # yoktu, fonksiyon 100.0 varsayılanına DÜŞÜYORDU (rastlantısal doğru,
    # ama isimsiz/kasıtsız). OG05B10 datasheet'i farklı bir tolerans
    # verirse (NDA'lı, henüz alınmadı) bu SAYI değil TOLERANS ayrı
    # aşağıda güncellenmeli, ikisi karıştırılmamalı.
    AraBirimTuru.MIPI_CSI2_DPHY: 100.0,
}


def empedans_hedefi_getir(cift: DiferansiyelCift) -> float:
    if cift.hedef_empedans_ohm_override > 0:
        return cift.hedef_empedans_ohm_override
    return ARAYUZ_EMPEDANS_HEDEFLERI.get(cift.arayuz, 100.0)


def empedans_geometrisi_coz(
    cift: DiferansiyelCift,
    h_mm: float,
    er: float,
    t_mm: float = 0.035,
    fab_min_w_mm: float = 0.127,
    fab_min_s_mm: float = 0.127,
) -> Dict[str, object]:
    """`empedans_hedefi_getir()`'in döndürdüğü HEDEF sayıyı (ör. USB3 için 90Ω)
    GERÇEKTEN karşılayacak (W, S) iz genişliği/aralığını çözer.

    Önceki durum: `empedans_hedefi_getir()` sadece bir hedef ohm değeri
    döndürüyordu; o hedefi karşılayan fiziksel geometriyi hesaplayan hiçbir
    kod yoktu (SKILL-empedans-stackup karşılaştırmasında tespit edilen
    boşluk). Bu fonksiyon `empedans_cozucu.py::hedefe_gore_coz()`'u çağırarak
    o boşluğu kapatır — akışta `empedans_hedefi_getir()`'den HEMEN SONRA
    çağrılmalı (Faz 2 — Katman Yapısı & Empedans).

    Dönen sözlük: {"hedef_ohm", "en_iyi": {w_mm, s_mm, zdiff_ohm, hata_yuzde}
    veya None, "ulasilabilir_mi": bool}. `en_iyi is None` ise verilen H/fab
    sınırlarıyla hedefe ULAŞILAMIYOR demektir — stackup'ı revize et
    (`pcb_stackup_planner.py` §3 kuralı: "Hesaplanan W < fab min iz?
    -> stackup'ı revize et, routing'i değil" ile aynı disiplin).

    NOT: Bu kapalı-form sonuç ERKEN TASARIM içindir; üretim sign-off'u için
    gerçek laminate verisi + fab impedance coupon/TDR raporu şarttır
    (bkz. `empedans_cozucu.py` başındaki dürüstlük notu).
    """
    hedef_ohm = empedans_hedefi_getir(cift)
    rapor = stackup_tara(
        hedef_ohm=hedef_ohm, er=er, t=t_mm,
        w_araligi=(0.05, 2.0, 0.005), s_araligi=(0.05, 2.0, 0.005),
        fab_min_w=fab_min_w_mm, fab_min_s=fab_min_s_mm,
        h_adaylari=(h_mm,),
    )
    satir = rapor["stackuplar"][0]
    return {
        "hedef_ohm": hedef_ohm,
        "en_iyi": satir["en_iyi"] if satir["ulasilabilir"] else None,
        "tum_adaylar": satir["ilk_5"],
        "ulasilabilir_mi": satir["ulasilabilir"],
    }


# ------------------------------------------------------------------
# 11. FAZ 2: LENGTH MATCHING (UZUNLUK EŞLEŞTİRME) DOĞRULAMASI
# ------------------------------------------------------------------
#
# NOT: Tolerans değerleri arayüze göre değişir — burada tipik/muhafazakâr
# değerler kullanılmıştır. Kritik tasarımlarda arayüzün resmi elektriksel
# şartnamesinden (örn. USB-IF, HDMI Forum, JEDEC) kesin toleransı al.

ARAYUZ_UZUNLUK_TOLERANSI_MM: Dict[AraBirimTuru, float] = {
    AraBirimTuru.USB2_0: 1.5,
    AraBirimTuru.USB3_x: 0.5,
    AraBirimTuru.HDMI: 0.5,
    AraBirimTuru.ETHERNET_1G: 1.0,
    AraBirimTuru.LVDS: 0.5,
    AraBirimTuru.PCIE: 0.13,
    AraBirimTuru.DDR3_4: 0.13,
    # 0.127mm (5 mil): MIPI D-PHY intra-pair skew için endüstride yaygın
    # kabul gören üst sınır — birden fazla bağımsız kaynakta (Cadence,
    # gdugpcba MIPI tasarım rehberi, pcbartists MIPI DSI notları)
    # ≤5 mil olarak tutarlı. NOT: OG05B10'un kendi datasheet'i (NDA'lı,
    # henüz alınmadı) daha sıkı bir değer verirse BU SAYI güncellenmeli —
    # bu, genel D-PHY pratiği, sensöre özel garanti DEĞİL.
    AraBirimTuru.MIPI_CSI2_DPHY: 0.127,
}


def length_matching_kontrolu(cift: DiferansiyelCift) -> List[str]:
    """Bir differential pair'in P/N hatları arasındaki uzunluk farkını kontrol eder."""
    hatalar: List[str] = []
    fark_mm = abs(cift.uzunluk_pozitif_mm - cift.uzunluk_negatif_mm)
    tolerans = ARAYUZ_UZUNLUK_TOLERANSI_MM.get(cift.arayuz, 0.5)

    if fark_mm > tolerans:
        hatalar.append(
            f"LENGTH MATCHING HATASI ({cift.isim}): P/N hatları arasında {fark_mm:.3f}mm "
            f"fark var, {cift.arayuz.name} için izin verilen tolerans {tolerans}mm. "
            f"Kısa olan hatta 'serpentine' (kıvrımlı) routing ile uzunluk ekle."
        )
    return hatalar


# ------------------------------------------------------------------
# 12. FAZ 2: VIA STUB (BACK-DRILLING İHTİYACI) ANALİZİ
# ------------------------------------------------------------------
#
# NOT: Bu basitleştirilmiş bir kural-of-thumb'dır. Gerçek stub etkisi
# frekansa, dielektriğe ve via geometrisine bağlıdır; kesin karar için
# bir SI (signal integrity) simülasyonu/uzmanı gerekir. Burada endüstride
# yaygın kullanılan "~10 Gbps üzeri ve stub > ~0.5mm ise back-drill düşün"
# kuralı uygulanmıştır.

KATMAN_KALINLIK_VARSAYIMI_MM = 0.15
STUB_UZUNLUK_ESIGI_MM = 0.5
VERI_HIZI_ESIGI_GBPS = 10.0


def via_stub_analizi(via: ViaKullanimi, toplam_katman: int, via_tipi: ViaTipi) -> List[str]:
    uyarilar: List[str] = []

    if via_tipi != ViaTipi.SADECE_BOYDAN_BOYA:
        # Kör/gömülü via zaten stub bırakmaz (sinyalin kullandığı katmanlarla sınırlı)
        return uyarilar

    stub_katman_sayisi = toplam_katman - via.bitis_katman
    stub_uzunluk_mm = stub_katman_sayisi * KATMAN_KALINLIK_VARSAYIMI_MM

    if via.veri_hizi_Gbps >= VERI_HIZI_ESIGI_GBPS and stub_uzunluk_mm > STUB_UZUNLUK_ESIGI_MM:
        uyarilar.append(
            f"VIA STUB UYARISI ({via.net_isim}): {via.veri_hizi_Gbps} Gbps hızında sinyal, "
            f"boydan-boya via ile Katman {via.bitis_katman}'de bitiyor ama karta Katman "
            f"{toplam_katman}'e kadar delik açılıyor. Tahmini stub uzunluğu "
            f"~{stub_uzunluk_mm:.2f}mm — bu hızda sinyal yansımasına (reflection) yol açabilir. "
            f"Back-drilling (stub'ı sonradan delerek kısaltma) veya kör/gömülü via kullanımı önerilir."
        )
    return uyarilar


# ------------------------------------------------------------------
# 13. FAZ 3: ANTEN KEEP-OUT ALANI DOĞRULAMASI
# ------------------------------------------------------------------
#
# NOT: Aşağıdaki değerler yaygın chip-anten üretici uygulama notlarından
# (application note) alınan TİPİK/muhafazakâr rakamlardır. Her anten
# modülünün KENDİ datasheet'indeki keep-out çizimi asıl referanstır —
# antenler arasında (özellikle sub-GHz ve GPS gibi patch/harici antenlerde)
# büyük farklar olabilir. Bu fonksiyon sadece "hiç kontrol etmemekten daha
# iyi" bir ilk elemedir.

ANTEN_MIN_BAKIR_MESAFESI_MM: Dict[FrekansBandi, float] = {
    FrekansBandi.WIFI_BLE_2_4GHZ: 5.0,
    FrekansBandi.WIFI_5GHZ: 5.0,
    FrekansBandi.SUBGHZ_433: 15.0,
    FrekansBandi.SUBGHZ_868_915: 12.0,
    FrekansBandi.GPS_L1: 5.0,
}

ANTEN_MIN_KENAR_MESAFESI_MM: Dict[FrekansBandi, float] = {
    FrekansBandi.WIFI_BLE_2_4GHZ: 3.0,
    FrekansBandi.WIFI_5GHZ: 3.0,
    FrekansBandi.SUBGHZ_433: 5.0,
    FrekansBandi.SUBGHZ_868_915: 5.0,
    FrekansBandi.GPS_L1: 3.0,
}


def anten_keepout_kontrolu(yerlesim: AntenYerlesimi) -> List[str]:
    hatalar: List[str] = []

    min_bakir = ANTEN_MIN_BAKIR_MESAFESI_MM.get(yerlesim.frekans_bandi, 5.0)
    min_kenar = ANTEN_MIN_KENAR_MESAFESI_MM.get(yerlesim.frekans_bandi, 3.0)

    if yerlesim.en_yakin_bakir_mesafe_mm < min_bakir:
        hatalar.append(
            f"ANTEN KEEP-OUT HATASI ({yerlesim.isim}): En yakın bakır/GND dökümüne "
            f"{yerlesim.en_yakin_bakir_mesafe_mm}mm mesafede, {yerlesim.frekans_bandi.name} "
            f"için minimum {min_bakir}mm keep-out gerekir. Anten performansı ve rezonans "
            f"frekansı bakırdan etkilenir; alandaki bakır dökümünü çıkar."
        )

    if yerlesim.kenara_mesafe_mm < min_kenar:
        hatalar.append(
            f"ANTEN KEEP-OUT HATASI ({yerlesim.isim}): Kart kenarına "
            f"{yerlesim.kenara_mesafe_mm}mm mesafede, minimum {min_kenar}mm gerekir. "
            f"Anten kenara çok yakınsa ışıma paterni bozulur ve verim düşer."
        )

    return hatalar


# ------------------------------------------------------------------
# 14. FAZ 3: KRİSTAL / OSİLATÖR YERLEŞİM KURALI
# ------------------------------------------------------------------
#
# NOT: Bu kurallar genel iyi-uygulama (best practice) kılavuzlarına dayanır.
# Kesin mesafe, kristalin çalışma frekansına ve IC üreticisinin yerleşim
# kılavuzuna göre değişebilir — kritik tasarımlarda IC'nin datasheet'indeki
# "layout guidelines" bölümünü esas al.

KRISTAL_MAKS_IC_MESAFESI_MM = 8.0
KRISTAL_MIN_GURULTU_MESAFESI_MM = 5.0


def kristal_yerlesim_kontrolu(yerlesim: KristalYerlesimi) -> List[str]:
    hatalar: List[str] = []

    if yerlesim.ic_pinine_mesafe_mm > KRISTAL_MAKS_IC_MESAFESI_MM:
        hatalar.append(
            f"KRİSTAL YERLEŞİM HATASI ({yerlesim.isim}): IC'nin XTAL pinlerine "
            f"{yerlesim.ic_pinine_mesafe_mm}mm mesafede, maksimum önerilen "
            f"{KRISTAL_MAKS_IC_MESAFESI_MM}mm. Uzun XTAL izleri parazitik kapasitans "
            f"ve EMI'ya yol açar; kristali IC'ye mümkün olduğunca yaklaştır."
        )

    if yerlesim.gurultu_kaynagina_mesafe_mm < KRISTAL_MIN_GURULTU_MESAFESI_MM:
        if not yerlesim.guard_ring_var_mi:
            hatalar.append(
                f"KRİSTAL YERLEŞİM HATASI ({yerlesim.isim}): En yakın gürültülü/hızlı "
                f"sinyale {yerlesim.gurultu_kaynagina_mesafe_mm}mm mesafede ve etrafında "
                f"GND guard ring yok. Kristal hassas bir analog osilatördür; ya "
                f"{KRISTAL_MIN_GURULTU_MESAFESI_MM}mm'den uzağa taşı ya da etrafına "
                f"guard ring (GND ile çevrili koruma halkası) ekle."
            )

    return hatalar


# ------------------------------------------------------------------
# 15. FAZ 3: RF HATTI GND STITCHING VIA ARALIĞI
# ------------------------------------------------------------------
#
# NOT: Stitching via aralığı için yaygın kullanılan kural-of-thumb λ/20
# (bazı kaynaklarda λ/10) sınırıdır — bunun altında GND dönüş yolu sürekli
# kabul edilir. Dalga boyu burada basitleştirilmiş efektif dielektrik
# sabiti (er_eff) varsayımıyla hesaplanır; kesin değer iz genişliği ve
# stackup'a bağlıdır ve bir alan çözücüyle doğrulanmalıdır.

def rf_stitching_araligi_hesapla_mm(frekans_GHz: float, er_eff: float = 3.0) -> float:
    """Serbest uzay ışık hızını (300 mm/ns ≈ 3x10^8 m/s) kullanarak, verilen
    efektif dielektrik sabitinde dalga boyunun 1/20'sini (mm) döndürür."""
    if frekans_GHz <= 0:
        return float("inf")
    dalga_boyu_mm = 300.0 / (frekans_GHz * math.sqrt(er_eff))
    return dalga_boyu_mm / 20.0


def rf_stitching_kontrolu(hat: RFHattiStitching, er_eff: float = 3.0) -> List[str]:
    hatalar: List[str] = []
    izin_verilen_aralik = rf_stitching_araligi_hesapla_mm(hat.frekans_GHz, er_eff)

    if hat.stitching_via_araligi_mm > izin_verilen_aralik:
        hatalar.append(
            f"RF STITCHING HATASI ({hat.isim}): GND stitching via aralığı "
            f"{hat.stitching_via_araligi_mm}mm, {hat.frekans_GHz}GHz için izin verilen "
            f"maksimum ~{izin_verilen_aralik:.2f}mm (λ/20). Aralık çok genişse dönüş yolu "
            f"sürekliliği bozulur ve istenmeyen ışıma/kayıp oluşur. Via sayısını artır."
        )
    return hatalar


# ------------------------------------------------------------------
# 16. FAZ 4: CREEPAGE / CLEARANCE (YALITIM MESAFESİ) DOĞRULAMASI
# ------------------------------------------------------------------
#
# NOT: Aşağıdaki tablo IPC-2221B'nin harici iletken (external conductor),
# kaplamasız (uncoated), deniz seviyesi/düşük kirlenme derecesi için
# TİPİK/basitleştirilmiş değerlerine dayanır. Gerçek creepage/clearance
# gereksinimi; kaplama (conformal coating) var mı, rakım, kirlenme derecesi
# (pollution degree) ve ilgili güvenlik standardına (IEC 60950, 62368,
# 60601 tıbbi cihazlar vb.) göre ÖNEMLİ ÖLÇÜDE değişir. Yüksek voltaj
# içeren tasarımlarda mutlaka ilgili standardın GÜNCEL tablosunu kullan ve
# bir güvenlik/uyumluluk uzmanına doğrulat — bu sadece bir ilk elemedir.

IPC2221_HARICI_MESAFE_TABLOSU_MM: List[Tuple[float, float]] = [
    (15, 0.05),
    (30, 0.05),
    (50, 0.1),
    (100, 0.1),
    (150, 0.2),
    (170, 0.2),
    (250, 0.3),
    (500, 0.5),
    (1000, 1.5),
]


def gerekli_izolasyon_mesafesi_mm(gerilim_farki_V: float) -> float:
    for maks_gerilim, mesafe_mm in IPC2221_HARICI_MESAFE_TABLOSU_MM:
        if gerilim_farki_V <= maks_gerilim:
            return mesafe_mm
    # Tablodaki en yüksek voltaj sınırının üzerindeyse, kaba bir doğrusal
    # ölçekleme kullan (kesinlikle gerçek tabloyla doğrulanmalı).
    son_gerilim, son_mesafe = IPC2221_HARICI_MESAFE_TABLOSU_MM[-1]
    return son_mesafe * (gerilim_farki_V / son_gerilim)


def izolasyon_kontrolu(gereksinim: YalitimGereksinimi) -> List[str]:
    hatalar: List[str] = []
    gerekli_mesafe = gerekli_izolasyon_mesafesi_mm(gereksinim.gerilim_farki_V)

    if gereksinim.tasarim_mesafesi_mm < gerekli_mesafe:
        hatalar.append(
            f"YALITIM HATASI ({gereksinim.isim}): {gereksinim.gerilim_farki_V}V fark için "
            f"tasarımdaki mesafe {gereksinim.tasarim_mesafesi_mm}mm, IPC-2221 tablosuna göre "
            f"minimum {gerekli_mesafe}mm gerekir. Bu, güvenlik açısından KRİTİK bir hatadır — "
            f"ark oluşumu/kısa devre riski taşır. Hatları uzaklaştır veya slot/kesim ekle."
        )
    return hatalar


# ------------------------------------------------------------------
# 17. FAZ 4: YÜKSEK AKIM BAKIR KALINLIĞI GEREKSİNİMİ
# ------------------------------------------------------------------
#
# Faz 1'deki iz_genisligi_hesapla_mm fonksiyonunun tersini çözer: sabit bir
# iz genişliği kısıtı varsa (örn. konektör pini/pad genişliği sabit), akımı
# taşımak için gereken minimum bakır ağırlığını (oz) hesaplar.

def gerekli_bakir_agirligi_oz(
    akim_A: float,
    mevcut_genislik_mm: float,
    sicaklik_artisi_C: float = 10.0,
    dis_katman_mi: bool = True,
) -> float:
    if akim_A <= 0 or mevcut_genislik_mm <= 0:
        return 0.0

    k = 0.048 if dis_katman_mi else 0.024
    b = 0.44
    c = 0.725

    alan_mil2 = (akim_A / (k * (sicaklik_artisi_C ** b))) ** (1 / c)
    genislik_mil = mevcut_genislik_mm / 0.0254
    kalinlik_mil = alan_mil2 / genislik_mil
    return kalinlik_mil / 1.378  # 1 oz ≈ 1.378 mil


# Çoğu standart fabrika işlemi için pratik/ekonomik üst sınır. Daha kalın
# bakır (örn. 4-6oz) mümkündür ama maliyeti ciddi artırır ve tüm fabrikalar
# desteklemez — bu değeri seçtiğin fabrikanın yetenek sayfasına göre ayarla.
MAKS_EKONOMIK_BAKIR_AGIRLIGI_OZ = 3.0


def guc_elektronigi_bakir_kontrolu(
    iz: YuksekAkimIzi,
    sicaklik_artisi_C: float = 10.0,
    maks_ekonomik_oz: float = MAKS_EKONOMIK_BAKIR_AGIRLIGI_OZ,
) -> List[str]:
    hatalar: List[str] = []
    gerekli_oz = gerekli_bakir_agirligi_oz(
        iz.akim_A, iz.mevcut_genislik_mm, sicaklik_artisi_C, iz.dis_katman_mi
    )

    if gerekli_oz > maks_ekonomik_oz:
        hatalar.append(
            f"GÜÇ ELEKTRONİĞİ HATASI ({iz.isim}): {iz.akim_A}A akımı {iz.mevcut_genislik_mm}mm "
            f"genişlikte taşımak için ~{gerekli_oz:.1f}oz bakır gerekir, bu ekonomik/standart "
            f"sınır olan {maks_ekonomik_oz}oz'un üzerinde. İz genişliğini artır, akımı "
            f"paralel izlere/katmanlara böl veya daha kalın bakır seçeneğini fabrikayla teyit et."
        )
    return hatalar


# ------------------------------------------------------------------
# 18. FAZ 4: TERMAL VIA / ISI YÖNETİMİ KONTROLÜ
# ------------------------------------------------------------------
#
# NOT: Gerçek termal via performansı; via çapı, plating kalınlığı, dolgu
# (filled/tented) durumu ve bakır alanına bağlıdır ve JEDEC termal test
# kartlarıyla ölçülür. Burada "her via yaklaşık X watt taşır" şeklinde
# BASİTLEŞTİRİLMİŞ bir kural-of-thumb kullanılmıştır — kritik termal
# tasarımlarda bir termal simülasyon (FEA) veya üreticinin app notu ile
# doğrulanmalıdır.

VIA_BASINA_TERMAL_KAPASITE_W = 0.3  # tipik 0.3mm plated via için kaba varsayım


def termal_via_sayisi_hesapla(
    guc_W: float, via_basina_kapasite_W: float = VIA_BASINA_TERMAL_KAPASITE_W
) -> int:
    if guc_W <= 0:
        return 0
    return math.ceil(guc_W / via_basina_kapasite_W)


def termal_yonetim_kontrolu(yonetim: TermalYonetim) -> List[str]:
    hatalar: List[str] = []
    gerekli_via_sayisi = termal_via_sayisi_hesapla(yonetim.guc_yayilimi_W)

    if yonetim.mevcut_termal_via_sayisi < gerekli_via_sayisi:
        hatalar.append(
            f"TERMAL YÖNETİM HATASI ({yonetim.isim}): {yonetim.guc_yayilimi_W}W ısı yayılımı "
            f"için tahmini {gerekli_via_sayisi} termal via gerekir, tasarımda sadece "
            f"{yonetim.mevcut_termal_via_sayisi} adet var. Yetersiz termal via, komponentin "
            f"aşırı ısınmasına ve ömrünün kısalmasına yol açar. Via sayısını artır veya "
            f"komponent altındaki bakır alanı büyüt."
        )
    return hatalar


# ------------------------------------------------------------------
# 19. ANA PROGRAM (İTERATİF DOĞRULAMA DÖNGÜSÜ)
# ------------------------------------------------------------------

def stackup_planla(
    tum_sinyaller: List[Net],
    komponentler: List[Komponent],
    kisitlar: MekanikVeTermalKisitlar,
    maks_deneme: int = 10,
) -> Dict[str, str]:
    hafiza = sinyalleri_grupla(tum_sinyaller)

    # 1) Elektriksel minimumu bul
    baz_katman = katman_sayisini_hesapla(hafiza, komponentler)

    # 2) Termal ve üretim ihtiyaçlarına göre sayıyı güncelle (fiziksel override)
    baz_katman = max(baz_katman, termal_katman_ihtiyaci(kisitlar, baz_katman))
    baz_katman = max(baz_katman, uretim_limiti_kontrolu(komponentler, kisitlar, baz_katman))

    deneme = 0
    while deneme < maks_deneme:
        deneme += 1
        print(f"\n--- {baz_katman} Katmanlı Dizilim Test Ediliyor (Deneme {deneme}) ---")
        hedef_dizilim = dizilimi_olustur(baz_katman, hafiza)

        elk_hatalar, uyarilar = capraz_dogrulama_yap(hedef_dizilim, hafiza, baz_katman)
        fiz_hatalar = fiziksel_dogrulama_yap(hedef_dizilim, kisitlar, komponentler, baz_katman)

        tum_hatalar = elk_hatalar + fiz_hatalar

        if not tum_hatalar:
            print("SONUÇ: BAŞARILI! Elektriksel ve üretim kuralları sağlandı.\n")
            print(f"Toplam Katman Sayısı: {baz_katman}")
            print("Üretilecek Dizilim:")
            for k, v in hedef_dizilim.items():
                print(f"  {k}: {v}")
            if uyarilar:
                print("\nTasarımcıya Notlar:")
                for uyari in uyarilar:
                    print(f"  - {uyari}")
            return hedef_dizilim
        else:
            print("SONUÇ: BAŞARISIZ! Doğrulama hataları bulundu:")
            for hata in tum_hatalar:
                print(f"  -> {hata}")
            print("ÇÖZÜM: Katman sayısı yeterli değil. 2 katman eklenip baştan hesaplanıyor...")
            baz_katman += 2  # PCB katmanları her zaman çift sayı artar (core dengesi için)

    raise RuntimeError(
        f"{maks_deneme} denemede geçerli bir stackup bulunamadı. Kısıtları gözden geçirin."
    )


# ------------------------------------------------------------------
# ÖRNEK KULLANIM (bu dosya doğrudan çalıştırıldığında devreye girer)
# ------------------------------------------------------------------

if __name__ == "__main__":
    # --- Örnek şematik verisi ---
    sinyaller = [
        Net("3V3", SinyalTuru.GUC, maks_akim=1.5),
        Net("5V0", SinyalTuru.GUC, maks_akim=2.0),
        Net("1V8", SinyalTuru.GUC, maks_akim=0.8),
        Net("GND", SinyalTuru.GND),
        Net("AGND", SinyalTuru.GND),
        Net("MIPI_CLK", SinyalTuru.HIZLI_DIJITAL, empedans_kontrolu_gerekli_mi=True),
        Net("MIPI_D0", SinyalTuru.HIZLI_DIJITAL, empedans_kontrolu_gerekli_mi=True),
        Net("USB_DP", SinyalTuru.HIZLI_DIJITAL, empedans_kontrolu_gerekli_mi=True),
        Net("USB_DM", SinyalTuru.HIZLI_DIJITAL, empedans_kontrolu_gerekli_mi=True),
        Net("SENSOR_ADC", SinyalTuru.ANALOG),
        Net("LED1", SinyalTuru.YAVAS_DIJITAL),
        Net("BUTTON1", SinyalTuru.YAVAS_DIJITAL),
    ]

    komponentler = [
        Komponent("U1_SoC", KilifTuru.FINE_PITCH_BGA, pin_sayisi=400,
                  guc_pini_sayisi=8, dekuplaj_kapasitor_sayisi=8),
        Komponent("U2_PMIC", KilifTuru.QFN, pin_sayisi=32,
                  guc_pini_sayisi=2, dekuplaj_kapasitor_sayisi=1),  # eksik decoupling örneği
        Komponent("R1", KilifTuru.STANDART, pin_sayisi=2),
    ]

    kisitlar = MekanikVeTermalKisitlar(
        hedef_kalinlik_mm=1.6,
        maks_isi_yayilimi_W=3.0,
        kabul_edilen_via_tipi=ViaTipi.KOR_VE_GOMULU_IZINLI,
        bakir_denge_toleransi=15.0,
    )

    stackup_planla(sinyaller, komponentler, kisitlar)

    # --- FAZ 1 gösterimi: iz genişliği, fabrika DFM ve decoupling kontrolü ---
    print("\n=== FAZ 1: İz Genişliği Önerileri (1oz bakır, dış katman, 10°C artış) ===")
    hafiza = sinyalleri_grupla(sinyaller)
    for isim, genislik_mm in guc_hatlari_icin_iz_genisligi_kontrolu(hafiza).items():
        print(f"  {isim}: min. {genislik_mm:.3f} mm iz genişliği önerilir")

    print("\n=== FAZ 1: Fabrika DFM Kontrolü (JLCPCB Standart profiline göre) ===")
    dfm_hatalari = fabrika_dfm_kontrolu(
        tasarim_iz_genisligi_mm=0.1,
        tasarim_iz_araligi_mm=0.1,
        tasarim_delik_capi_mm=0.25,
        profil=FABRIKA_PROFILLERI["JLCPCB_STANDART"],
    )
    if dfm_hatalari:
        for hata in dfm_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Tasarım değerleri seçilen fabrika profiline uygun.")

    print("\n=== FAZ 1: Decoupling Kapasitör Kontrolü ===")
    dekuplaj_hatalari = dekuplaj_kontrolu(komponentler)
    if dekuplaj_hatalari:
        for hata in dekuplaj_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Tüm komponentler için decoupling yeterli.")

    # --- FAZ 2 gösterimi: differential pair, length matching, via stub ---
    print("\n=== FAZ 2: Differential Pair Empedans Hedefi ve Length Matching ===")
    usb_cift = DiferansiyelCift(
        isim="USB_D+/D-",
        arayuz=AraBirimTuru.USB3_x,
        uzunluk_pozitif_mm=42.0,
        uzunluk_negatif_mm=41.2,  # 0.8mm fark, USB3 toleransı 0.5mm -> hata beklenir
        veri_hizi_Gbps=5.0,
    )
    print(f"  Hedef empedans ({usb_cift.isim}): {empedans_hedefi_getir(usb_cift)} ohm")
    lm_hatalari = length_matching_kontrolu(usb_cift)
    if lm_hatalari:
        for hata in lm_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Length matching toleransı içinde.")

    print("\n=== FAZ 2: Via Stub (Back-Drilling İhtiyacı) Analizi ===")
    yuksek_hizli_via = ViaKullanimi(
        net_isim="PCIE_TX0",
        baslangic_katman=1,
        bitis_katman=3,  # sinyal katman 3'te bitiyor
        veri_hizi_Gbps=16.0,  # PCIe Gen4 hızında
    )
    stub_uyarilari = via_stub_analizi(
        yuksek_hizli_via, toplam_katman=8, via_tipi=ViaTipi.SADECE_BOYDAN_BOYA
    )
    if stub_uyarilari:
        for uyari in stub_uyarilari:
            print(f"  -> {uyari}")
    else:
        print("  Via stub etkisi bu hız/derinlik için önemsiz.")

    # --- FAZ 3 gösterimi: anten keep-out, kristal yerleşimi, RF stitching ---
    print("\n=== FAZ 3: Anten Keep-Out Alanı Kontrolü ===")
    anten = AntenYerlesimi(
        isim="WIFI_ANT1",
        frekans_bandi=FrekansBandi.WIFI_BLE_2_4GHZ,
        kenara_mesafe_mm=2.0,          # 3mm gerekirken 2mm -> hata beklenir
        en_yakin_bakir_mesafe_mm=3.0,  # 5mm gerekirken 3mm -> hata beklenir
    )
    anten_hatalari = anten_keepout_kontrolu(anten)
    if anten_hatalari:
        for hata in anten_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Anten keep-out alanı yeterli.")

    print("\n=== FAZ 3: Kristal/Osilatör Yerleşim Kontrolü ===")
    kristal = KristalYerlesimi(
        isim="XTAL1_16MHz",
        ic_pinine_mesafe_mm=12.0,           # 8mm sınırını aşıyor -> hata beklenir
        gurultu_kaynagina_mesafe_mm=2.0,    # 5mm altında ve guard ring yok -> hata beklenir
        guard_ring_var_mi=False,
    )
    kristal_hatalari = kristal_yerlesim_kontrolu(kristal)
    if kristal_hatalari:
        for hata in kristal_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Kristal yerleşimi uygun.")

    print("\n=== FAZ 3: RF Hattı GND Stitching Via Aralığı Kontrolü ===")
    rf_hat = RFHattiStitching(isim="WIFI_RF_TRACE", frekans_GHz=2.4, stitching_via_araligi_mm=5.0)
    izin_verilen = rf_stitching_araligi_hesapla_mm(rf_hat.frekans_GHz)
    print(f"  2.4GHz için izin verilen maks. stitching aralığı: ~{izin_verilen:.2f}mm")
    stitching_hatalari = rf_stitching_kontrolu(rf_hat)
    if stitching_hatalari:
        for hata in stitching_hatalari:
            print(f"  -> {hata}")
    else:
        print("  RF stitching via aralığı yeterli.")

    # --- FAZ 4 gösterimi: yalıtım, yüksek akım bakır, termal via ---
    print("\n=== FAZ 4: Creepage/Clearance (Yalıtım Mesafesi) Kontrolü ===")
    yalitim = YalitimGereksinimi(
        isim="AC_HAT - LOJIK_GND", gerilim_farki_V=230.0, tasarim_mesafesi_mm=0.2
    )
    print(f"  Gerekli minimum mesafe (230V için): {gerekli_izolasyon_mesafesi_mm(230.0)} mm")
    yalitim_hatalari = izolasyon_kontrolu(yalitim)
    if yalitim_hatalari:
        for hata in yalitim_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Yalıtım mesafesi yeterli.")

    print("\n=== FAZ 4: Yüksek Akım Bakır Kalınlığı Kontrolü ===")
    guc_izi = YuksekAkimIzi(isim="MOTOR_12V", akim_A=15.0, mevcut_genislik_mm=2.0)
    print(
        f"  Gerekli bakır kalınlığı: ~{gerekli_bakir_agirligi_oz(15.0, 2.0):.1f} oz "
        f"(2.0mm genişlik, 15A için)"
    )
    bakir_hatalari = guc_elektronigi_bakir_kontrolu(guc_izi)
    if bakir_hatalari:
        for hata in bakir_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Bakır kalınlığı ekonomik sınırlar içinde.")

    print("\n=== FAZ 4: Termal Via / Isı Yönetimi Kontrolü ===")
    termal = TermalYonetim(isim="U3_MOSFET", guc_yayilimi_W=4.0, mevcut_termal_via_sayisi=5)
    print(f"  {termal.guc_yayilimi_W}W için tahmini gerekli via sayısı: "
          f"{termal_via_sayisi_hesapla(termal.guc_yayilimi_W)}")
    termal_hatalari = termal_yonetim_kontrolu(termal)
    if termal_hatalari:
        for hata in termal_hatalari:
            print(f"  -> {hata}")
    else:
        print("  Termal via sayısı yeterli.")
