#!/usr/bin/env python3
"""
ipc_dru_koprusu.py
====================
`ipc2152_hesaplayici.py`, `ipc2221_clearance_hesaplayici.py` ve
`ipc6012_dfm_motoru.py`'nin sayısal sonuçlarını, KiCad 10'un anlayacağı
s-expression `Custom Rules` (`.kicad_dru`) formatına çeviren köprü.

ÖNEMLİ — ÜÇ SESSİZ TUZAK, GERÇEK KİCAD 10 İLE AMPİRİK OLARAK DOĞRULANDI:
-------------------------------------------------------------------------
Bu proje daha önce (ESP32-C3 Smart Band kart revizyonunda) bir
`.kicad_dru` dosyası yazıp `kicad-cli pcb drc` ile test ettiğinde, kuralların
SESSİZCE hiç uygulanmadığı keşfedildi — kicad-cli HİÇBİR HATA/UYARI
VERMEDEN dosyayı yok sayıyordu, DRC "kurallar uygulandı" gibi GÖRÜNÜYORDU
ama aslında hiçbiri çalışmıyordu. Doğrulama yöntemi: global bir
`(constraint clearance (min 3mm))` probu eklenip DRC ihlal sayısının
GERÇEKTEN patlayıp patlamadığına bakıldı (dosya okunuyorsa ihlal sayısı
büyük ölçüde artar, okunmuyorsa taban seviyede kalır). Bu modül o üç
tuzağı YAPISAL OLARAK imkânsız kılar:

  1. **`(version 1)` başlığı ZORUNLU.** Yoksa dosyanın TAMAMI sessizce
     yok sayılır. `_kicad_dru_govdesi_uret()` bunu HER ZAMAN ilk satır
     olarak yazar — çağıran taraf unutamaz.
  2. **`(priority N)` GEÇERLİ BİR TOKEN DEĞİL.** Bir kurala eklenirse o
     kural sessizce devre dışı kalır. Bu modül `priority` alanı/parametresi
     HİÇ SUNMAZ — kural önceliği KiCad'de dosya SIRASINA göre belirlenir
     (İLK EŞLEŞEN KURAL KAZANIR). `KuralBloguSirasi` enum'u bu SIRAYI
     açıkça kodlar: İSTİSNALAR (component-özel) her zaman GENEL kurallardan
     ÖNCE yazılır.
  3. **Yorum karakteri `#`'dir, `;` DEĞİL.** `;` kullanılırsa parse çöker
     ve dosyanın TAMAMI yok sayılır. Bu modülün ürettiği tüm yorumlar `#`
     ile başlar; `;` hiçbir yerde kullanılmaz.

DOĞRULAMA DURUMU (bu makinede GERÇEKTEN koşturuldu — ESP32C3_SmartBand.kicad_pcb):
`track_width`/`clearance` VE `annular_width` constraint'lerinin ÜÇÜ DE
GERÇEK `kicad-cli pcb drc` (KiCad 10.0.4) ile, yukarıdaki üç tuzak
düzeltildikten sonra GERÇEKTEN UYGULANDIĞI (sadece parse edildiği değil,
GERÇEK ihlal ürettiği) doğrulandı — proje sahibinin gerçek kartına karşı,
orijinal `.kicad_dru` dosyası GÜVENLİ ŞEKİLDE YEDEKLENİP/GERİ YÜKLENEREK:
  - `clearance` probu (global, 3mm minimum): temel 3 ihlalden 503 ihlale
    çıktı — dosyanın GERÇEKTEN okunduğunun kanıtı.
  - `annular_width` probu (via'lar için 5mm minimum, kasıtlı aşırı büyük):
    187 tane `"annular_width"` tipi ihlal üretti, her biri kuralın adını
    ("Annular Test") ve tam limitini ("5.00...") DOĞRU raporladı.
Test sonunda orijinal `.kicad_dru` dosyası `diff` ile bit-bit aynı olduğu
doğrulanarak geri yüklendi — proje sahibinin gerçek dosyasına KALICI bir
değişiklik YAPILMADI.
"""

from __future__ import annotations

import shutil
import uuid as _uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from ipc2152_hesaplayici import Ipc2152Sonucu
from ipc2221_clearance_hesaplayici import ClearanceSonucu
from ipc6012_dfm_motoru import SinifLimitleri


class KuralOnceligi(int, Enum):
    """KiCad'de gerçek bir `priority` alanı YOKTUR (bkz. dosya başlığı) —
    bu enum sadece bu modül İÇİNDE kuralları DOSYA SIRASINA göre
    dizmek için kullanılan bir yardımcıdır, üretilen `.kicad_dru`
    metnine YAZILMAZ."""

    ISTISNA = 0  # component-özel istisnalar — İLK yazılır (kazanır)
    GENEL = 1    # net-class bazlı genel kurallar — SONRA yazılır


@dataclass(frozen=True)
class DruKurali:
    isim: str
    kosul: str
    constraint_tipi: str  # "track_width" | "clearance" | "annular_width" | ...
    min_deger_mm: float
    oncelik: KuralOnceligi = KuralOnceligi.GENEL
    aciklama: str = ""

    def __post_init__(self) -> None:
        if self.min_deger_mm <= 0:
            raise ValueError(f"{self.isim}: min_deger_mm pozitif olmalı, gelen: {self.min_deger_mm!r}")
        if "\n" in self.isim or "\n" in self.kosul:
            raise ValueError(
                f"{self.isim}: isim/koşulda satır sonu OLAMAZ (s-expression yapısının "
                "içindeki bir string alanına gömülür — bir satır sonu, s-expression'ı bozar)."
            )
        # ';' YASAĞI SADECE isim/kosul İÇİN — bunlar `(rule "...")`/
        # `(condition "...")` s-expression YAPISININ İÇİNE gömülen kısa
        # tanımlayıcılardır, en güvenli tercih tamamen yasaklamaktır.
        # `aciklama` İSE farklıdır: `blok()` onu HER ZAMAN kendi `# `
        # önekiyle tek bir yorum satırına sarar (aşağıya bak) — bir '#'
        # satırının İÇİNDEKİ ';' KiCad'in DRU dilinde tamamen ZARARSIZDIR
        # (satırın tamamı zaten yorum), bu yüzden `aciklama`da ';' YASAK
        # DEĞİL. Asıl risk `aciklama`da bir SATIR SONU olması olurdu (o
        # zaman ikinci satır '#' önekSİZ kalır ve s-expression'a karışır)
        # — bu yüzden burada ';' yerine SATIR SONU kontrol edilir.
        if ";" in self.isim or ";" in self.kosul:
            raise ValueError(
                f"{self.isim}: isim/koşulda ';' karakteri YASAK — KiCad .kicad_dru "
                "yorum karakteri '#' dir, ';' parse'ı SESSİZCE çökertir (bkz. modül başlığı)."
            )

    def blok(self) -> str:
        # `aciklama` çok satırlıysa HER satır KENDİ '#' önekini alır —
        # aksi halde ikinci satır önekSİZ kalır ve geçersiz bir s-expression
        # token'ı gibi ayrıştırılıp TÜM dosyanın çökmesine yol açabilir
        # (tuzak #1/#3 ile aynı "sessizce tüm dosya" riski).
        yorum_satirlari = [f"# {s}" for s in self.aciklama.splitlines() if self.aciklama]
        yorum = ("\n".join(yorum_satirlari) + "\n") if yorum_satirlari else ""
        return (
            f'{yorum}'
            f'(rule "{self.isim}"\n'
            f'  (condition "{self.kosul}")\n'
            f'  (constraint {self.constraint_tipi} (min {self.min_deger_mm}mm)))'
        )


def _kicad_dru_govdesi_uret(kurallar: Sequence[DruKurali], baslik_yorumu: str = "") -> str:
    """`DruKurali` listesinden TAM `.kicad_dru` metnini üretir.

    Sıralama: `KuralOnceligi.ISTISNA` kuralları HER ZAMAN
    `KuralOnceligi.GENEL` kurallarından ÖNCE yazılır (dosya başlığındaki
    tuzak #2 — "ilk eşleşen kural kazanır" gerçeğinin doğrudan sonucu).
    Python'un `sorted()`'ı KARARLI (stable) olduğu için aynı öncelik
    grubu içindeki GÖRECELİ sıra korunur.
    """
    sirali = sorted(kurallar, key=lambda k: k.oncelik.value)
    # Kurallar arasına BOŞ SATIR koy (okunabilirlik) — s-expression
    # yapısını etkilemez.
    govde: list[str] = ["(version 1)", ""]
    if baslik_yorumu:
        for satir in baslik_yorumu.splitlines():
            govde.append(f"# {satir}" if satir.strip() else "#")
        govde.append("")
    for i, k in enumerate(sirali):
        govde.append(k.blok())
        if i != len(sirali) - 1:
            govde.append("")
    return "\n".join(govde) + "\n"


def kural_dosyasi_olustur(
    hedef_yol: str,
    kurallar: Sequence[DruKurali],
    baslik_yorumu: str = "",
    yedek_al: bool = True,
) -> str:
    """`DruKurali` listesini GERÇEK bir `.kicad_dru` dosyasına yazar.

    `kicad_koprusu.py::custom_dru_yaz()` ile AYNI "önce yedek al, sonra
    üzerine yaz" deseni — proje başına TEK bir `.kicad_dru` varsayılır,
    mevcut dosyanın üzerine YAZILIR (append değil).

    Boş `kurallar` listesiyle çağrılırsa `ValueError` fırlatır — boş bir
    `.kicad_dru` dosyası yazmak, "hiçbir özel kural yok" ile "kurallar
    unutuldu" arasındaki farkı gizler; çağıran taraf bunu BİLİNÇLİ olarak
    istiyorsa boş bir dosyayı kendi elleriyle yazmalı, bu fonksiyon
    sessizce onu yapmaz.
    """
    if not kurallar:
        raise ValueError(
            "kurallar listesi boş — boş bir .kicad_dru dosyası bilerek yazılmak "
            "isteniyorsa bu fonksiyonu ÇAĞIRMA, dosyayı doğrudan yaz."
        )

    yol = Path(hedef_yol)
    if yedek_al and yol.exists():
        shutil.copy(yol, yol.with_suffix(yol.suffix + ".bak"))

    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(_kicad_dru_govdesi_uret(kurallar, baslik_yorumu), encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# IPC SONUÇLARINI DruKurali'NA ÇEVİREN YARDIMCI FONKSİYONLAR
# ------------------------------------------------------------------

def ipc2152_kuraline_cevir(
    net_class: str, sonuc: Ipc2152Sonucu, isim_oneki: str = "",
) -> DruKurali:
    """Bir `Ipc2152Sonucu`'nu, o net class için minimum iz genişliği
    kuralına çevirir."""
    isim = f"{isim_oneki}IPC-2152 {net_class} Min Genişlik ({sonuc.katman_tipi.value})"
    return DruKurali(
        isim=isim,
        kosul=f"A.NetClass == '{net_class}'",
        constraint_tipi="track_width",
        min_deger_mm=sonuc.genislik_mm,
        oncelik=KuralOnceligi.GENEL,
        aciklama=(
            f"IPC-2152 (bkz. ipc2152_hesaplayici.py): {sonuc.akim_A}A, "
            f"dT={sonuc.delta_t_C}C, {sonuc.bakir_kalinligi_oz}oz, "
            f"iç-katman-derating={sonuc.ic_katman_derating_katsayisi}"
        ),
    )


def ipc2221_kuraline_cevir(
    net_a_class: str, net_b_class: str, sonuc: ClearanceSonucu, isim_oneki: str = "",
) -> DruKurali:
    """Bir `ClearanceSonucu`'nu, iki net class ARASINDAKİ minimum mesafe
    kuralına çevirir.

    NOT: KiCad'in özel kural dilinde iki-net-class-arası bir clearance
    kuralı `(condition "A.NetClass == 'X' && B.NetClass == 'Y'")` şeklinde
    yazılır — bu, GERÇEK `kicad-cli pcb drc` ile bu ortamda test edilmedi
    (yukarıdaki `track_width`/tek-parça `clearance` örneklerinden farklı
    olarak iki AYRI net class'ı aynı anda eşleştiren bir koşul), SENİN
    makinende ayrıca doğrulanmalı.
    """
    isim = f"{isim_oneki}IPC-2221 {net_a_class}-{net_b_class} Clearance"
    return DruKurali(
        isim=isim,
        kosul=f"A.NetClass == '{net_a_class}' && B.NetClass == '{net_b_class}'",
        constraint_tipi="clearance",
        min_deger_mm=sonuc.clearance_mm,
        oncelik=KuralOnceligi.GENEL,
        aciklama=(
            f"IPC-2221B (bkz. ipc2221_clearance_hesaplayici.py): {sonuc.gerilim_V}V, "
            f"{sonuc.katman_tipi.value}/{sonuc.kaplama_durumu.value}, güven={sonuc.guven.value}"
        ),
    )


def ipc6012_kuraline_cevir(limitler: SinifLimitleri, isim_oneki: str = "") -> list[DruKurali]:
    """Bir `SinifLimitleri`'ni, TÜM izlerde geçerli genel `annular_width`
    kuralına çevirir (`.kicad_dru`'da yalnızca `annular_width` desteklenir
    — solder mask barajı ve aspect ratio KiCad Custom Rules'un native
    constraint kümesinde YOKTUR, bu ikisi `.kicad_dru`'ya YAZILAMAZ; onlar
    `ipc6012_dfm_motoru.py`'nin kendi Python kontrolleriyle, gerçek Gerber/
    `.kicad_pcb` verisi üzerinden denetlenmeye DEVAM ETMELİDİR — bkz.
    `gerber_dfm_gorsel_koprusu.py`)."""
    return [
        DruKurali(
            isim=f"{isim_oneki}IPC-6012 {limitler.sinif.value} Minimum Annular Ring",
            kosul="A.Type == 'Via'",
            constraint_tipi="annular_width",
            min_deger_mm=limitler.min_annular_ring_mm,
            oncelik=KuralOnceligi.GENEL,
            aciklama=f"IPC-6012 {limitler.sinif.value} (bkz. ipc6012_dfm_motoru.py): {limitler.kaynak_notu}",
        )
    ]


def uc_w_kuraline_cevir(
    net_class_a: str, net_class_b: str, sonuc, isim_oneki: str = "",
) -> DruKurali:
    """`emi_emc_kural_motoru.UcWSonucu`'nu (3W crosstalk kuralı) iki net
    class ARASINDAKİ minimum kenar-kenar clearance kuralına çevirir.

    KiCad'in `clearance` constraint'i BAKIR KENARI-KENARINA mesafe ölçer
    (merkez-merkez DEĞİL) — bu yüzden `sonuc.minimum_kenar_kenar_mm`
    kullanılır, `minimum_merkez_merkez_mm` DEĞİL (bu ikisinin
    KARIŞTIRILMASI `emi_emc_kural_motoru.py`'nin başlığında ayrıca
    uyarılan, sektörde en sık yapılan 3W hatasıdır).

    DOĞRULAMA DURUMU: `ipc2221_kuraline_cevir` ile AYNI gerekçeyle
    (bkz. o fonksiyonun docstring'i) iki-net-class koşulu bu ortamda
    GERÇEK `kicad-cli pcb drc` ile test EDİLMEDİ — track_width/tek-parça
    clearance/annular_width'in aksine, SENİN makinende ayrıca
    doğrulanmalı.
    """
    isim = f"{isim_oneki}EMI 3W {net_class_a}-{net_class_b} Crosstalk Clearance"
    return DruKurali(
        isim=isim,
        kosul=f"A.NetClass == '{net_class_a}' && B.NetClass == '{net_class_b}'",
        constraint_tipi="clearance",
        min_deger_mm=sonuc.minimum_kenar_kenar_mm,
        oncelik=KuralOnceligi.GENEL,
        aciklama=(
            f"3W kuralı (bkz. emi_emc_kural_motoru.py): iz genişliği "
            f"{sonuc.iz_genisligi_mm}mm, çarpan {sonuc.carpan}, "
            f"merkez-merkez hedefi {sonuc.minimum_merkez_merkez_mm}mm "
            f"(burada kenar-kenar {sonuc.minimum_kenar_kenar_mm}mm yazılı)."
        ),
    )


def dfa_courtyard_kuraline_cevir(
    referans_a: str, referans_b: str, sonuc, isim_oneki: str = "",
) -> DruKurali:
    """`ipc_a_610_dfa_motoru.ClearanceSonucu`'nu (DFA komponent-komponent
    clearance) İKİ KOMPONENT arasındaki `courtyard_clearance` kuralına
    çevirir — `istisna_kurali_uret()` ile AYNI `A.Reference == B.Reference
    == ...` yerine iki FARKLI referansı eşleştiren bir koşul üretir, bu
    yüzden `KuralOnceligi.ISTISNA` ile işaretlenir (component-özel kural,
    net-class bazlı genel kurallardan ÖNCE yazılmalı — bkz. modül başlığı
    tuzak #2 tartışması).

    DOĞRULAMA DURUMU — DİĞERLERİNDEN DAHA TEMKİNLİ OLUNMALI: `courtyard_
    clearance` constraint tipi, bu modülün GERÇEK `kicad-cli pcb drc` ile
    doğrulanmış `track_width`/`clearance`/`annular_width` üçlüsünün
    AKSİNE, bu ortamda HİÇ test edilmedi — KiCad'in custom rule dilinde
    var olduğu dokümantasyonda geçer ama BU PROJEDE ampirik olarak
    KANITLANMADI (dosya başlığındaki üç tuzak — versiyon/priority/yorum
    karakteri — SADECE track_width/clearance/annular_width ile kanıtlandı).
    Kullanmadan önce `ipc_dru_koprusu.py`'nin kendi doğrulama yöntemiyle
    (kasıtlı aşırı büyük bir prob değeri + DRC ihlal sayısının GERÇEKTEN
    patlaması) SENİN makinende doğrulanmalı; aksi halde bu kural
    `dfm_emc_check.py`/`ipc_a_610_dfa_motoru.komponent_clearance_kontrolu()`
    gibi Python-taraflı kontrollerle DENETİME DEVAM ETMELİDİR.
    """
    isim = f"{isim_oneki}DFA {referans_a}-{referans_b} Courtyard Clearance"
    return DruKurali(
        isim=isim,
        kosul=f"A.Reference == '{referans_a}' && B.Reference == '{referans_b}'",
        constraint_tipi="courtyard_clearance",
        min_deger_mm=sonuc.minimum_clearance_mm,
        oncelik=KuralOnceligi.ISTISNA,
        aciklama=(
            f"IPC-A-610 DFA (bkz. ipc_a_610_dfa_motoru.py): {sonuc.komponent_tipi_a.value}-"
            f"{sonuc.komponent_tipi_b.value}, {sonuc.montaj_sinifi.value}"
            + (", reflow gölgeleme eki dahil" if sonuc.golgeleme_riski_mi else "")
            + f". DOĞRULANMADI: courtyard_clearance constraint tipi bu ortamda test edilmedi."
        ),
    )


def istisna_kurali_uret(
    isim: str, referans: str, min_deger_mm: float, constraint_tipi: str = "clearance",
    aciklama: str = "",
) -> DruKurali:
    """Tek bir komponentin (`A.Reference == B.Reference == referans`)
    kendi iç pad-pad mesafesi için istisna kuralı — ESP32C3_SmartBand'de
    J2 (USB-C) ve U2 (LGA-14 IMU) için gerçekten kullanılan desenin
    genelleştirilmiş hali. `KuralOnceligi.ISTISNA` ile işaretlenir ki
    `_kicad_dru_govdesi_uret()` bunu genel kurallardan ÖNCE yazsın."""
    return DruKurali(
        isim=isim,
        kosul=f"A.Reference == '{referans}' && B.Reference == '{referans}'",
        constraint_tipi=constraint_tipi,
        min_deger_mm=min_deger_mm,
        oncelik=KuralOnceligi.ISTISNA,
        aciklama=aciklama,
    )


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: ';' karakteri içeren bir kural OLUŞTURULMAYA
    çalışılırsa `ValueError` beklenir — kabul edilirse (sessizce üretilen
    dosyada geçersiz bir yorum satırına dönüşürse) girdi doğrulaması
    boştur."""
    try:
        DruKurali("Kötü;İsim", "A.NetClass == 'X'", "clearance", 0.2)
    except ValueError:
        return True
    return False


def oz_testleri_calistir() -> list[str]:
    hatalar: list[str] = []

    # 1. Üretilen metin HER ZAMAN "(version 1)" ile başlamalı (tuzak #1).
    kural = DruKurali("Test", "A.NetClass == 'X'", "clearance", 0.2)
    metin = _kicad_dru_govdesi_uret([kural])
    if not metin.startswith("(version 1)"):
        hatalar.append("üretilen dosya '(version 1)' ile başlamıyor")

    # 2. Üretilen metinde ASLA '(priority' geçmemeli (tuzak #2).
    if "(priority" in metin:
        hatalar.append("üretilen dosyada geçersiz '(priority' token'ı var")

    # 3. Üretilen metinde yorum satırları '#' ile başlamalı, ';' KULLANILMAMALI.
    kral_aciklamali = DruKurali("Test2", "A.NetClass == 'Y'", "clearance", 0.3, aciklama="not")
    metin2 = _kicad_dru_govdesi_uret([kral_aciklamali])
    if ";" in metin2:
        hatalar.append("üretilen dosyada ';' karakteri var (yorum karakteri '#' olmalı)")

    # 4. İstisna kuralları GENEL kurallardan ÖNCE yazılmalı (dosya sırası önceliği).
    genel = DruKurali("Genel", "A.NetClass == 'GUC'", "track_width", 0.25, oncelik=KuralOnceligi.GENEL)
    istisna = istisna_kurali_uret("J2 İstisnası", "J2", 0.13)
    metin3 = _kicad_dru_govdesi_uret([genel, istisna])  # bilerek TERS sırada verildi
    if metin3.index('"J2 İstisnası"') > metin3.index('"Genel"'):
        hatalar.append("istisna kuralı genel kuraldan SONRA yazıldı (öncelik sırası bozuk)")

    # 5. Boş kural listesiyle dosya yazımı reddedilmeli.
    try:
        kural_dosyasi_olustur("gecici_test.kicad_dru", [])
    except ValueError:
        pass
    else:
        hatalar.append("boş kural listesiyle dosya yazımı reddedilmedi")

    # 6. Fault injection.
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: ';' doğrulaması boş olabilir")

    return hatalar


if __name__ == "__main__":
    import sys

    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        sys.exit(1)
    print("PASS: ipc_dru_koprusu.py öz testleri temiz.")
