"""
ecad_mcad_termal_kopru.py
==========================
ECAD (şematik/PCB) ile MCAD (kasa/enclosure) arasındaki TERMAL entegrasyonu
köprüler — `MASTER_RULEBOOK.md` **Faz 4b: Mekanik-Termal Entegrasyon**'un
kod karşılığı.

`mekanik_dxf_koprusu.py`, kasayı şimdiye kadar SADECE bir 3D keepout
TEHDİDİ olarak ele aldı (`z_kontrolu_yap` — "buraya parça yükselemez").
Bu modül kasayı ayrıca bir ısıl TEMAS HEDEFİ olarak da ele alır — mekanikçinin
bıraktığı bir "heatsink boss" (termal çıkıntı) yüzeyi, ısı kaynağı bir
komponentin ısısını kasaya aktarabileceği bir fırsattır, sadece bir engel
değil.

Bu dosya üç mevcut köprüyü birleştirir:
  - `mekanik_dxf_koprusu.py`  → kasa/STEP verisi (temas yüzeyi koordinatları)
  - `pcb_stackup_planner.py`  → mevcut `TermalYonetim`/`termal_yonetim_kontrolu`
    (via-sayısı kontrolü) — bu modül onu ÇAĞIRIR/genişletir, YENİDEN YAZMAZ,
    böylece mevcut testler (`test_pcb_stackup_planner.py`) bozulmaz.
  - `kicad_koprusu.py`        → gerçek `.kicad_pcb` dosyasına yazma deseni
    (`custom_dru_yaz` ile aynı "önce `.bak` yedek al, sonra yaz" disiplini)

KASA VERİSİ YOKSA (mekanik STEP paylaşılmadıysa): bu modülün fonksiyonları
boş/`None` girdilerle çağrılabilir ve SESSİZCE (hata fırlatmadan) devre dışı
kalır — her fonksiyonun "kasa verisi yok" dalına bakınız. Bu, projenin genel
"veri yoksa dur, hata fırlatma, CONFIRM/atla" disiplinine uyar.

AĞ/ARAÇ UYARISI: `mekanik_dxf_koprusu.py`'deki gibi, gerçek STEP parse
`cadquery`/`python-occ` gerektirir ve bu ortamda kurulu değildir — bu modül
ÖNCEDEN PARSE EDİLMİŞ `TermalTemasBolgesi` listesi üzerinde çalışır.

DOĞRULAMA NOTU: `b_mask_poligonu_pcb_ye_yaz()` ve `edge_cuts_yarigi_pcb_ye_yaz()`
ürettiği `.kicad_pcb` S-expression'ları, bu proje için kurulu gerçek
`kicad-cli` (KiCad 10.0.4) ile test edildi: gerçek `ESP32C3_SmartBand.kicad_pcb`
dosyasının bir kopyasına her iki fonksiyon da uygulandı, ardından
`kicad-cli pcb drc` sonucu her iki elemanı da (gr_poly/B.Mask, gr_line×2/
Edge.Cuts) hatasız ayrıştırdı — DRC'nin tek bulguğu ("Board has malformed
outline") test PCB'sinin hiç Edge.Cuts sınırı tanımlanmamış olmasından
kaynaklandı, üretilen S-expression sözdiziminden DEĞİL. Yine de: pad-mask
clearance/fabrikaya özgü frezeleme kısıtları gibi ÜRETİM detayları
doğrulanmadı — hedef fabrikayla (JLCPCB/PCBWay) teyit edilmeli.
"""

from __future__ import annotations

import shutil
import uuid as uuid_lib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from pcb_stackup_planner import TermalYonetim, termal_yonetim_kontrolu


# ------------------------------------------------------------------
# 1. TERMAL TEMAS YÜZEYİ (STEP'ten türetilmiş heatsink boss)
# ------------------------------------------------------------------

@dataclass
class TermalTemasBolgesi:
    """Kasanın STEP modelinden türetilmiş bir metal temas yüzeyi (heatsink boss).

    `mekanik_dxf_koprusu.TavanHaritasiBolgesi`'nin ısıl kardeşi: o "buraya
    parça YÜKSELEMEZ" der (tehdit), bu "buraya parça ISISINI AKTARABİLİR"
    der (fırsat) — ikisi de aynı STEP modelinden, farklı amaçlarla türetilir.
    """

    isim: str
    poligon: List[Tuple[float, float]]  # mm, kasadaki temas yüzeyinin 2D izdüşümü
    z_boslugu_mm: float  # PCB üst yüzeyi ile kasa temas yüzeyi arası boşluk


def _nokta_poligon_icinde_mi(x: float, y: float, poligon: List[Tuple[float, float]]) -> bool:
    """`mekanik_dxf_koprusu.py`'deki private helper'ın birebir kopyası.

    Modüller arası private (`_` ile başlayan) import Python konvansiyonuna
    aykırı olduğu için, bu küçük geometri yardımcısı burada tekrar edildi
    (tek kaynak DEĞİL ama iki köprü dosyası birbirine sıkı bağımlı olmasın
    diye bilinçli bir tercih — `pcb-layout`/`schematic-design` skill'lerinin
    kendi köprü dosyalarını birbirinden bağımsız tutma alışkanlığıyla
    tutarlı).
    """
    icinde = False
    n = len(poligon)
    for i in range(n):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
        ):
            icinde = not icinde
    return icinde


def soguturucu_yuzey_bul(
    x: float, y: float, yuzeyler: List[TermalTemasBolgesi]
) -> Optional[TermalTemasBolgesi]:
    """Verilen (x,y) komponent koordinatı kasadaki bir `TermalTemasBolgesi`
    poligonunun içine düşüyorsa o bölgeyi, düşmüyorsa `None` döndürür.

    NOT: İmza, mekanik_dxf_koprusu.py'deki `derive_keepouts(..., tavan_haritasi=...)`
    deseniyle tutarlı olsun diye `yuzeyler` parametresi ALIR — projede hiçbir
    fonksiyon gizli/global state okumaz, kasa verisi HER ZAMAN açıkça
    parametre olarak geçirilir.

    `yuzeyler` boşsa (kasa STEP verisi paylaşılmadıysa) sessizce `None`
    döner — hata FIRLATMAZ; bu, modülün "kasa verisi yoksa atlanır"
    kuralının temel taşıdır.
    """
    if not yuzeyler:
        return None
    for yuzey in yuzeyler:
        if _nokta_poligon_icinde_mi(x, y, yuzey.poligon):
            return yuzey
    return None


# ------------------------------------------------------------------
# 2. TERMAL YÖNETİM + B.MASK AÇIKLIĞI + YÜZEY KAPLAMASI ENTEGRASYONU
# ------------------------------------------------------------------

@dataclass
class KomponentTermalDurumu:
    """`pcb_stackup_planner.TermalYonetim` + kasa/B.Mask/yüzey-kaplama bağlamı."""

    yonetim: TermalYonetim
    x: float
    y: float
    b_mask_acikligi_tanimli_mi: bool = False
    yuzey_kaplamasi: str = "TBD"  # "ENIG" | "HASL" | "TBD"


def termal_yonetim_ve_mask_kontrolu(
    durum: KomponentTermalDurumu,
    yuzeyler: List[TermalTemasBolgesi],
    kritik_guc_esigi_W: float = 0.5,
) -> List[str]:
    """`pcb_stackup_planner.termal_yonetim_kontrolu()`'nu ÇAĞIRARAK (mevcut
    via-sayısı kontrolünü BOZMADAN/tekrar yazmadan — mevcut 142 testin
    deseniyle uyumlu kalınır) genişletir:

    Komponentin `guc_yayilimi_W`'si `kritik_guc_esigi_W`'yi AŞIYORSA VE
    `soguturucu_yuzey_bul()` onun altında bir kasa temas yüzeyi BULUYORSA:
      1. B.Mask açıklığı tanımlı değilse -> HATA (komponent altı çıplak
         bakıra çıkamıyor, kasaya ısıl temas kuramaz).
      2. B.Mask açıklığı VAR ama yüzey kaplaması ENIG değilse (HASL/TBD)
         -> UYARI (çıplak bakır zamanla oksitlenir, termal performans
         zamanla düşer — sadece mask açıklığı YETMEZ, kaplama da şart).
    """
    hatalar = list(termal_yonetim_kontrolu(durum.yonetim))

    if durum.yonetim.guc_yayilimi_W <= kritik_guc_esigi_W:
        return hatalar

    yuzey = soguturucu_yuzey_bul(durum.x, durum.y, yuzeyler)
    if yuzey is None:
        return hatalar

    if not durum.b_mask_acikligi_tanimli_mi:
        hatalar.append(
            f"TERMAL YÖNETİM HATASI ({durum.yonetim.isim}): kasa temas bölgesinde "
            f"('{yuzey.isim}', z_boşluğu={yuzey.z_boslugu_mm}mm) ama B.Mask açıklığı "
            f"tanımlı değil — komponent altı çıplak bakıra çıkamıyor, kasaya ısıl "
            f"temas kuramaz. `b_mask_poligonu_pcb_ye_yaz()` ile açıklık ekle."
        )
    elif durum.yuzey_kaplamasi.upper() != "ENIG":
        hatalar.append(
            f"TERMAL YÜZEY KAPLAMASI UYARISI ({durum.yonetim.isim}): B.Mask açıklığı "
            f"var ama yüzey kaplaması '{durum.yuzey_kaplamasi}' (ENIG değil) — çıplak "
            f"bakır zamanla oksitlenip termal ped/kasa temasının performansını "
            f"düşürür. Fabrikasyon/BOM notuna ENIG ZORUNLU kılınmalı (HASL kabul "
            f"edilmez — düzlemsizliği termal ped sıkışmasını da bozar)."
        )

    return hatalar


def b_mask_poligonu_pcb_ye_yaz(
    board_path: str,
    komponent_isim: str,
    poligon_mm: List[Tuple[float, float]],
) -> None:
    """Gerçek B.Mask açıklık poligonunu `.kicad_pcb` dosyasına yazar.

    `kicad_koprusu.py::custom_dru_yaz()` ile AYNI desen: orijinal dosya
    `.bak` uzantısıyla yedeklenir, sonra üzerine yazılır (append değil —
    dosyanın kapanış parantezinden HEMEN önce bir `gr_poly` bloğu eklenir).

    KiCad'de bir mask katmanına (B.Mask/F.Mask) doğrudan çizilen dolu bir
    `gr_poly`, o bölgede maskeyi AÇAR (mask açıklığı) — ayrı bir "zone"
    nesnesi gerekmez.

    Sözdizimi `kicad-cli pcb drc` ile gerçek proje PCB'sine karşı test
    edildi (bkz. dosyanın başındaki DOĞRULAMA NOTU) — üretim/fabrika
    kısıtları (pad-mask clearance vb.) ayrıca teyit edilmeli.
    """
    board = Path(board_path)
    if not board.exists():
        raise FileNotFoundError(f"{board_path} bulunamadı.")
    if len(poligon_mm) < 3:
        raise ValueError("poligon_mm en az 3 nokta içermeli.")

    yedek_yolu = board.with_suffix(board.suffix + ".bak")
    shutil.copy(board, yedek_yolu)

    icerik = board.read_text(encoding="utf-8")

    pts_satirlari = "\n\t\t\t".join(f"(xy {x} {y})" for x, y in poligon_mm)
    blok = (
        f'\t(gr_poly\n'
        f'\t\t(pts\n'
        f'\t\t\t{pts_satirlari}\n'
        f'\t\t)\n'
        f'\t\t(layer "B.Mask")\n'
        f'\t\t(width 0)\n'
        f'\t\t(fill yes)\n'
        f'\t\t(locked no)\n'
        f'\t\t(uuid "{uuid_lib.uuid4()}")\n'
        f'\t)\n'
    )

    # Dosyanın kapanış parantezinden hemen önce ekle (kicad_pcb kök düğümü).
    son_kapanis = icerik.rfind(")")
    if son_kapanis == -1:
        raise ValueError(f"{board_path} geçerli bir .kicad_pcb dosyası gibi görünmüyor.")
    yeni_icerik = icerik[:son_kapanis] + blok + icerik[son_kapanis:]
    board.write_text(yeni_icerik, encoding="utf-8")


# ------------------------------------------------------------------
# 3. TERMAL PED KALINLIĞI
# ------------------------------------------------------------------

def termal_ped_kalinligi_hesapla(kasa_z_boslugu_mm: float, sikisma_orani: float = 0.25) -> float:
    """Termal ped kalınlığı = `kasa_z_boslugu_mm / (1 - sikisma_orani)`.

    Ped, vidalandığında `sikisma_orani` (varsayılan %25, tipik aralık
    %20-30) kadar ezilip TAM OLARAK `kasa_z_boslugu_mm`'yi doldurmalı:
      - Daha İNCE bir ped -> boşluk kalır, ısıl direnç artar (kontaksız
        hava boşluğu, ısı aktarımını neredeyse durdurur).
      - Daha KALIN bir ped -> aşırı sıkışma, PCB'ye mekanik gerilim
        biner (`MASTER_RULEBOOK`'un titreşim/lehim-çatlağı kuralı —
        bkz. `termal_bariyer_gerekli_mi` docstring'i, aynı endişenin
        farklı bir kaynağı).
    """
    if kasa_z_boslugu_mm <= 0:
        raise ValueError("kasa_z_boslugu_mm pozitif olmalı.")
    if not (0 < sikisma_orani < 1):
        raise ValueError("sikisma_orani (0, 1) aralığında olmalı.")
    return round(kasa_z_boslugu_mm / (1 - sikisma_orani), 4)


def termal_ped_bom_notu_uret(isim: str, kalinlik_mm: float) -> str:
    """`termal_ped_kalinligi_hesapla()` sonucunu BOM'a yazılacak tek satırlık
    bir nota çevirir.

    Entegrasyon noktası: bu string, `bom_lifecycle_koprusu.py`'nin BOM
    satır üretim akışına (örn. `BomSatiri.aciklama` veya benzeri bir alana)
    doğrudan eklenebilir — bu modül `bom_lifecycle_koprusu.py`'ye bağımlılık
    EKLEMEZ (döngüsel import riski), sadece formatı üretir.
    """
    return f"Thermal Pad — {kalinlik_mm}mm ({isim})"


# ------------------------------------------------------------------
# 4. TERMAL BARİYER (Edge.Cuts FREZELEME YARIĞI) — mekanik/ısıl çelişki çözümü
# ------------------------------------------------------------------
#
# MASTER_RULEBOOK'un iki kuralı burada ÇATIŞABİLİR:
#   - Termal izolasyon: ısı kaynağı ile hassas parça arasına bir yarık
#     (slot) açmak, bakır üzerinden ısıl iletimi keser.
#   - Titreşim/lehim-çatlağı: yarık kart kenarına fazla yakınsa, kalan
#     malzeme (web) mekanik dayanımı zayıflatır, mikroskobik lehim
#     çatlaklarına yol açabilir.
# Bu iki kural birlikte çözülemiyorsa (yeterli web bırakılamıyorsa),
# `edge_cuts_yarigi_oner()` KASITLI olarak `None` döner — çağıran taraf
# bunu `termal_bariyer_ozetle()` ile "-> NEEDS_HUMAN" olarak raporlamalı.
# (Bu, `bom_lifecycle_koprusu.find_pin_compatible()`'ın boş liste dönüp
# "NEEDS_HUMAN"ı ÇAĞIRANA bıraktığı desenle birebir aynı disiplin.)

MIN_WEB_GENISLIGI_MM = 1.5  # MASTER_RULEBOOK titreşim/lehim-çatlağı kuralına göre minimum kalan malzeme


@dataclass
class TermalKaynakVeHassasParca:
    """Bir ısı kaynağı (LDO vb.) ile ısıya hassas bir parça (sensör,
    osilatör) çifti — termal bariyer ihtiyacı analizinin girdisi."""

    kaynak_isim: str
    kaynak_x: float
    kaynak_y: float
    hassas_isim: str
    hassas_x: float
    hassas_y: float
    ortak_bakir_katmani: bool  # ikisi de aynı (kalın, örn. 2oz) GND/güç katmanına mı bağlı
    kart_kenarina_mesafe_mm: float  # önerilecek yarığın kart kenarına en yakın mesafesi


@dataclass
class FrezelemeYarigi:
    isim: str
    baslangic: Tuple[float, float]
    bitis: Tuple[float, float]
    genislik_mm: float
    web_genisligi_mm: float


def termal_bariyer_gerekli_mi(cift: TermalKaynakVeHassasParca) -> bool:
    """MASTER_RULEBOOK'un "zıt köşe" yerleşim kuralına RAĞMEN, ısı kaynağı
    ile hassas parça AYNI kalın bakır katmanına (örn. 2oz GND) bağlıysa
    ısıl olarak yeterince ayrışmadığı kabul edilir — **mesafeden bağımsız**.

    MESAFE-BAZLI BİR EŞİK KASITLI OLARAK YOK: önceki bir taslakta burada
    "mesafe X eşiğini aşarsa bakırın kendi direnci baskın hale gelir,
    bariyer gerekmez" mantığıyla kafadan uydurulmuş bir çarpan (ör. "zıt
    köşe mesafesinin 3 katı") kullanılmıştı — bu, projenin başka hiçbir
    yerinde kabul etmediği bir şeydi: kaynaksız/doğrulanmamış bir sayısal
    fizik eşiği (bkz. `VIA_BASINA_TERMAL_KAPASITE_W`'nin "kaba varsayım,
    FEA/üretici app notuyla doğrulanmalı" notu; anten eşleştirme ağının
    "VNA ile fiziksel ayar gerekir" notu — aynı disiplin). Küçük bir PCB'de
    (bu projede ~50mm sınıfı giyilebilir kart) sürekli kalın bakır düzlemi
    ısıyı pratikte tüm kart yüzeyine hızla yayar; "şu mesafeden sonra
    güvenlidir" diyecek doğrulanmış bir termal direnç/FEA verisi YOK.
    Bilinmeyen durumda bu proje AŞIRI-MUHAFAZAKÂR davranır (fazladan
    NEEDS_HUMAN/bariyer önerisi, eksik uyarı değil) — gerçek bir termal
    simülasyon/ölçüm ileride mesafe-bazlı bir istisnayı haklı çıkarırsa,
    bu fonksiyon o VERİYLE (uydurma bir çarpanla değil) güncellenmelidir.
    """
    return cift.ortak_bakir_katmani


def edge_cuts_yarigi_oner(
    cift: TermalKaynakVeHassasParca,
    yarik_genisligi_mm: float = 1.0,
    min_web_genisligi_mm: float = MIN_WEB_GENISLIGI_MM,
) -> Optional[FrezelemeYarigi]:
    """Isı kaynağı ile hassas parça arasına bir Edge.Cuts frezeleme yarığı
    (milling slot) önerir — SADECE kart kenarı ile yarık arasında
    `min_web_genisligi_mm` kadar kalan malzeme (web) bırakılabiliyorsa.

    Bariyer gerekmiyorsa (`termal_bariyer_gerekli_mi() == False`) veya web
    genişliği yetersizse (yarık kart kenarına fazla yakın düşerse) `None`
    döner — çağıran taraf bunu `termal_bariyer_ozetle()` ile
    "-> NEEDS_HUMAN" olarak raporlamalı. Termal izolasyon KAZANIP mekanik
    dayanım (titreşim/lehim-çatlağı) KAYBETMEK YASAK; bu fonksiyon o
    ödünü sessizce vermez.
    """
    if not termal_bariyer_gerekli_mi(cift):
        return None

    kalan_web = cift.kart_kenarina_mesafe_mm - yarik_genisligi_mm
    if kalan_web < min_web_genisligi_mm:
        return None

    orta_x = (cift.kaynak_x + cift.hassas_x) / 2.0
    y_min = min(cift.kaynak_y, cift.hassas_y) - 2.0
    y_max = max(cift.kaynak_y, cift.hassas_y) + 2.0
    return FrezelemeYarigi(
        isim=f"termal_bariyer_{cift.kaynak_isim}_{cift.hassas_isim}",
        baslangic=(orta_x, y_min),
        bitis=(orta_x, y_max),
        genislik_mm=yarik_genisligi_mm,
        web_genisligi_mm=round(kalan_web, 4),
    )


def termal_bariyer_ozetle(
    cift: TermalKaynakVeHassasParca, yarik: Optional[FrezelemeYarigi]
) -> str:
    """`edge_cuts_yarigi_oner()` sonucunu okunabilir bir cümleye çevirir —
    `bom_lifecycle_koprusu.alternatif_karari_ozetle()` ile aynı "sonuç
    string'i üret" deseni."""
    if not termal_bariyer_gerekli_mi(cift):
        return (
            f"{cift.kaynak_isim}/{cift.hassas_isim}: ortak kalın bakır katmanı yok, "
            "termal bariyer gerekmiyor."
        )
    if yarik is None:
        return (
            f"{cift.kaynak_isim}/{cift.hassas_isim}: termal bariyer gerekli AMA kart "
            f"kenarına {cift.kart_kenarina_mesafe_mm}mm mesafede yeterli web genişliği "
            f"bırakılamıyor (min {MIN_WEB_GENISLIGI_MM}mm) -> NEEDS_HUMAN. Slot "
            "önerilmedi; mekanik dayanımı bozmadan ısıl izolasyon sağlanamıyor."
        )
    return (
        f"{cift.kaynak_isim}/{cift.hassas_isim}: Edge.Cuts yarığı önerildi "
        f"({yarik.baslangic} -> {yarik.bitis}, genişlik={yarik.genislik_mm}mm, "
        f"kalan web={yarik.web_genisligi_mm}mm)."
    )


def edge_cuts_yarigi_pcb_ye_yaz(board_path: str, yarik: FrezelemeYarigi) -> None:
    """Frezeleme yarığını `.kicad_pcb`'nin Edge.Cuts katmanına iki paralel
    `gr_line` (yarığın uzun kenarları) olarak yazar.

    `b_mask_poligonu_pcb_ye_yaz()` ile AYNI desen: `.bak` yedek alınır,
    dosyanın kapanış parantezinden hemen önce eklenir.

    Sözdizimi `kicad-cli pcb drc` ile test edildi (bkz. dosyanın başındaki
    DOĞRULAMA NOTU) — bu basit iki-`gr_line` temsili köşe yuvarlaması
    İÇERMEZ (frezeleme ucu keskin köşeli); hedef fabrikanın (JLCPCB/
    PCBWay) minimum frezeleme genişliği/köşe yarıçapı kısıtlarıyla ayrıca
    teyit edilmeli.
    """
    board = Path(board_path)
    if not board.exists():
        raise FileNotFoundError(f"{board_path} bulunamadı.")

    yedek_yolu = board.with_suffix(board.suffix + ".bak")
    shutil.copy(board, yedek_yolu)

    icerik = board.read_text(encoding="utf-8")

    x1, y1 = yarik.baslangic
    x2, y2 = yarik.bitis
    yari_genislik = yarik.genislik_mm / 2.0
    kenar1 = ((x1 - yari_genislik, y1), (x2 - yari_genislik, y2))
    kenar2 = ((x1 + yari_genislik, y1), (x2 + yari_genislik, y2))

    def gr_line(baslangic: Tuple[float, float], bitis: Tuple[float, float]) -> str:
        return (
            f'\t(gr_line\n'
            f'\t\t(start {baslangic[0]} {baslangic[1]})\n'
            f'\t\t(end {bitis[0]} {bitis[1]})\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(width 0.1)\n'
            f'\t\t(uuid "{uuid_lib.uuid4()}")\n'
            f'\t)\n'
        )

    blok = gr_line(*kenar1) + gr_line(*kenar2)

    son_kapanis = icerik.rfind(")")
    if son_kapanis == -1:
        raise ValueError(f"{board_path} geçerli bir .kicad_pcb dosyası gibi görünmüyor.")
    yeni_icerik = icerik[:son_kapanis] + blok + icerik[son_kapanis:]
    board.write_text(yeni_icerik, encoding="utf-8")
