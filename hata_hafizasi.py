#!/usr/bin/env python3
"""
hata_hafizasi.py
=================
ERC/DRC/DFM hataları için KALICI ÖĞRENME HAFIZASI — Obsidian uyumlu bir
Markdown veritabanı (`Hata_Hafizasi.md`) üzerinde çalışan, geçmiş hataları
ve ÇÖZÜMLERİNİ kaydedip bir sonraki tasarımda geri getiren (retrieval)
köprü.

NEDEN BU DOSYA VAR:
-------------------
Proje bugüne kadar bir DRC/ERC hatası aldığında `pcb-layout` skill'inin
"Sonsuz Döngü Kaçış Kuralı"na göre deneme-yanılma yapıyordu — ama bu
öğrenme OTURUMLA BİRLİKTE ÖLÜYORDU. Bir önceki projede "bu clearance
ihlalini iz genişliğini düşürerek DEĞİL, yerleşimi değiştirerek çözmüştük"
bilgisi hiçbir yerde durmuyordu. Bu modül o kurumsal hafızayı dosyaya alır.

RETRIEVAL YÖNTEMİ — DÜRÜSTLÜK NOTU ("RAG" kelimesi hakkında):
--------------------------------------------------------------
Bu modül **vektör gömme (embedding) tabanlı bir RAG DEĞİLDİR** ve öyleymiş
gibi de sunulmaz. Gömme üretmek harici bir model/ağ erişimi gerektirir; bu
proje hiçbir yerde doğrulanmamış bir ağ bağımlılığı eklemiyor. Bunun yerine
iki katmanlı, tamamen yerel ve test edilebilir bir arama yapılır:
  1. **İmza eşleşmesi (kesin):** DRC mesajındaki koordinat/refdes/sayı gibi
     her seferinde DEĞİŞEN kısımlar normalize edilip bir imza hash'i
     üretilir. Aynı SINIF hata, koordinatları farklı olsa bile aynı imzayı
     alır — bu, saf metin karşılaştırmasının yapamadığı şey.
  2. **Sözcüksel örtüşme (Jaccard):** imza tutmazsa normalize token
     kümelerinin kesişim/birleşim oranı. Eşiğin (`benzerlik_esigi`) altında
     kalan hiçbir şey ÖNERİLMEZ — "belki alakalıdır" diye zayıf bir eşleşme
     sunmak, yanlış çözümü tekrar denemeye yol açar.
Gerçek bir gömme tabanlı arama ileride eklenirse `benzer_kayitlari_bul()`
imzası korunarak DEĞİŞTİRİLEBİLİR; çağıranlar etkilenmez.

EN ÖNEMLİ TASARIM KARARI — BAŞARISIZ DENEMELER DE KAYDEDİLİR:
--------------------------------------------------------------
Hafıza sadece "işe yarayan çözümü" değil, **denenip İŞE YARAMAYAN çözümü de**
kaydeder (`Sonuc.BASARISIZ`). `cozum_oner()` başarısız kayıtları asla öneri
olarak sunmaz ama "bunu daha önce denedik, olmadı" listesi olarak DÖNDÜRÜR.
Bir ajanın aynı yanlış düzeltmeyi üçüncü kez denemesi, hiç hafızası
olmamasından daha maliyetlidir.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Obsidian kasası kullanılacaksa bu yol `HataHafizasi(dosya_yolu=...)` ile
# verilir (ör. r"C:\Users\Dell\Documents\Hata_Hafizasi.md"). VARSAYILAN
# bilinçli olarak PROJE İÇİdir — bir aracın, kullanıcının kişisel notlarının
# durduğu kasaya sorulmadan yazması doğru olmaz; kasa yolu bir KARARDIR.
VARSAYILAN_HAFIZA_YOLU = "HAFIZA/Hata_Hafizasi.md"

BASLIK = """---
tags: [pcb, hata-hafizasi, drc, erc, dfm]
olusturan: hata_hafizasi.py
---

# Hata Hafızası

Bu dosya OTOMATİK yönetilir (`hata_hafizasi.py`). Elle düzenlenebilir ama
her kaydın `imza` satırı KORUNMALIDIR — arama onun üzerinden çalışır.

İlgili: [[MASTER_RULEBOOK]] · [[TASARIM_AKISI]] · [[Hafiza_Defteri]] (bu
dosyanın serbest-metin, proje-ötesi kardeşi — fark için oradaki bilgi
kutusuna bakın)

"""


class KontrolTipi(str, Enum):
    DRC = "DRC"
    ERC = "ERC"
    DFM = "DFM"
    SIMULASYON = "SIMULASYON"
    DIGER = "DIGER"


class Sonuc(str, Enum):
    COZULDU = "COZULDU"
    BASARISIZ = "BASARISIZ"      # denendi, işe yaramadı -> bir daha önerilmez
    NEEDS_HUMAN = "NEEDS_HUMAN"  # otomatik çözülemedi, insan kararı gerekti


@dataclass
class HataKaydi:
    tip: KontrolTipi
    mesaj: str
    kok_neden: str
    cozum: str
    sonuc: Sonuc
    proje: str = ""
    tarih: str = field(default_factory=lambda: date.today().isoformat())
    etiketler: List[str] = field(default_factory=list)
    imza: str = ""

    def __post_init__(self) -> None:
        if not self.imza:
            self.imza = imza_uret(self.mesaj)


# ------------------------------------------------------------------
# 1. NORMALİZASYON VE İMZA
# ------------------------------------------------------------------

_KOORDINAT = re.compile(r"\(?\s*-?\d+[.,]\d+\s*(mm|mils?)?\s*[,;]\s*-?\d+[.,]\d+\s*(mm|mils?)?\s*\)?")
_REFDES = re.compile(r"\b([A-Z]{1,3})(\d+)\b")
_SAYI = re.compile(r"-?\d+(?:[.,]\d+)?")
_TIRNAKLI = re.compile(r"[\"']([^\"']+)[\"']")
_BOSLUK = re.compile(r"\s+")


def mesaji_normalize_et(mesaj: str) -> str:
    """DRC/ERC mesajını, her koşuda DEĞİŞEN kısımlarını yer tutucuya
    çevirerek KARŞILAŞTIRILABİLİR hale getirir.

    Sıra önemlidir: koordinatlar sayılardan ÖNCE temizlenmeli, yoksa
    "(12.34, 56.78)" önce iki ayrı sayıya dönüşür ve koordinat olduğu
    bilgisi kaybolur.

    Örnek:
      "Clearance violation (net "GND" and net "+3V3") at (12.34, 56.78)"
      -> "clearance violation (net <net> and net <net>) at <koord>"
    """
    metin = mesaj.strip()
    metin = _KOORDINAT.sub(" <koord> ", metin)
    metin = _TIRNAKLI.sub(" <net> ", metin)
    metin = _REFDES.sub(lambda m: f"<{m.group(1).lower()}ref>", metin)
    metin = _SAYI.sub(" <sayi> ", metin)
    metin = _BOSLUK.sub(" ", metin)
    return metin.strip().lower()


def imza_uret(mesaj: str) -> str:
    """Normalize edilmiş mesajdan 8 karakterlik kararlı bir imza üretir.

    Aynı SINIF hata (farklı koordinat/refdes/değer) aynı imzayı alır — bu,
    hafızanın çalışmasının ön koşuludur. `uretim_zinciri_koprusu.py::
    rotation_map_versiyonla()`'nın içerik-hash'i ile aynı disiplin.
    """
    return hashlib.sha256(mesaji_normalize_et(mesaj).encode("utf-8")).hexdigest()[:8]


def _tokenler(mesaj: str) -> set:
    return {t for t in re.split(r"[^a-z0-9<>_]+", mesaji_normalize_et(mesaj)) if len(t) > 2}


def benzerlik(mesaj_a: str, mesaj_b: str) -> float:
    """Normalize token kümeleri arasında Jaccard benzerliği (0-1)."""
    a, b = _tokenler(mesaj_a), _tokenler(mesaj_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ------------------------------------------------------------------
# 2. MARKDOWN OKUMA/YAZMA (Obsidian uyumlu)
# ------------------------------------------------------------------

_ALAN = re.compile(r"^-\s*\*\*(?P<ad>[^:*]+):\*\*\s*(?P<deger>.*)$")


def kaydi_markdown_a_cevir(kayit: HataKaydi) -> str:
    """Tek kaydı Obsidian uyumlu bir `##` bölümüne çevirir."""
    etiket_metni = " ".join(f"#{e.lstrip('#')}" for e in kayit.etiketler)
    return (
        f"## {kayit.tip.value} — {kayit.imza}\n"
        f"- **tip:** {kayit.tip.value}\n"
        f"- **imza:** {kayit.imza}\n"
        f"- **mesaj:** {kayit.mesaj}\n"
        f"- **kok_neden:** {kayit.kok_neden}\n"
        f"- **cozum:** {kayit.cozum}\n"
        f"- **sonuc:** {kayit.sonuc.value}\n"
        f"- **proje:** {kayit.proje}\n"
        f"- **tarih:** {kayit.tarih}\n"
        f"- **etiketler:** {etiket_metni}\n"
        "\n"
    )


def markdown_i_kayitlara_cevir(icerik: str) -> List[HataKaydi]:
    """Markdown dosyasını `HataKaydi` listesine geri ayrıştırır.

    Bilinmeyen/eksik alanlar sessizce varsayılana düşer AMA `imza` veya
    `mesaj` eksikse o bölüm ATLANIR — yarım bir kayıt, yanlış bir öneriye
    dönüşebilir.
    """
    kayitlar: List[HataKaydi] = []
    for bolum in icerik.split("\n## ")[1:]:
        alanlar: Dict[str, str] = {}
        for satir in bolum.splitlines():
            m = _ALAN.match(satir.strip())
            if m:
                alanlar[m.group("ad").strip().lower()] = m.group("deger").strip()
        if not alanlar.get("mesaj") or not alanlar.get("imza"):
            continue
        try:
            tip = KontrolTipi(alanlar.get("tip", "DIGER"))
        except ValueError:
            tip = KontrolTipi.DIGER
        try:
            sonuc = Sonuc(alanlar.get("sonuc", "NEEDS_HUMAN"))
        except ValueError:
            sonuc = Sonuc.NEEDS_HUMAN
        kayitlar.append(HataKaydi(
            tip=tip,
            mesaj=alanlar["mesaj"],
            kok_neden=alanlar.get("kok_neden", ""),
            cozum=alanlar.get("cozum", ""),
            sonuc=sonuc,
            proje=alanlar.get("proje", ""),
            tarih=alanlar.get("tarih", ""),
            etiketler=[e.lstrip("#") for e in alanlar.get("etiketler", "").split() if e.strip()],
            imza=alanlar["imza"],
        ))
    return kayitlar


class HataHafizasi:
    """Markdown dosyası üzerinde çalışan hata hafızası.

    Dosya YOKSA ilk yazmada oluşturulur; okuma boş liste döner (hata
    FIRLATMAZ — "henüz hafıza yok" normal bir başlangıç durumudur).
    """

    def __init__(self, dosya_yolu: str = VARSAYILAN_HAFIZA_YOLU, benzerlik_esigi: float = 0.55) -> None:
        self.dosya_yolu = Path(dosya_yolu)
        self.benzerlik_esigi = benzerlik_esigi

    # -------- okuma --------

    def kayitlari_oku(self) -> List[HataKaydi]:
        if not self.dosya_yolu.exists():
            return []
        return markdown_i_kayitlara_cevir(self.dosya_yolu.read_text(encoding="utf-8"))

    # -------- yazma --------

    def kaydet(self, kayit: HataKaydi) -> bool:
        """Kaydı ekler. `True` = eklendi, `False` = AYNI (imza + çözüm +
        sonuç) kayıt zaten vardı.

        İdempotanlık şart: aynı DRC hatası bir koşuda 40 kez çıkabilir;
        hafızayı 40 özdeş kayıtla şişirmek aramayı bozar.
        """
        mevcutlar = self.kayitlari_oku()
        for m in mevcutlar:
            if (m.imza, m.cozum.strip(), m.sonuc) == (kayit.imza, kayit.cozum.strip(), kayit.sonuc):
                return False

        self.dosya_yolu.parent.mkdir(parents=True, exist_ok=True)
        if not self.dosya_yolu.exists():
            self.dosya_yolu.write_text(BASLIK, encoding="utf-8")
        with open(self.dosya_yolu, "a", encoding="utf-8") as f:
            f.write(kaydi_markdown_a_cevir(kayit))
        return True

    # -------- arama (retrieval) --------

    def benzer_kayitlari_bul(
        self, mesaj: str, tip: Optional[KontrolTipi] = None
    ) -> List[Tuple[float, HataKaydi]]:
        """`(benzerlik_skoru, kayit)` listesi — skora göre azalan.

        İmzası TAM eşleşen kayıtlar skor 1.0 alır; diğerleri Jaccard skoruyla
        ve yalnızca `benzerlik_esigi`nin ÜSTÜNDE kalırlarsa döner.
        """
        hedef_imza = imza_uret(mesaj)
        sonuclar: List[Tuple[float, HataKaydi]] = []
        for kayit in self.kayitlari_oku():
            if tip is not None and kayit.tip != tip:
                continue
            if kayit.imza == hedef_imza:
                sonuclar.append((1.0, kayit))
                continue
            skor = benzerlik(mesaj, kayit.mesaj)
            if skor >= self.benzerlik_esigi:
                sonuclar.append((round(skor, 4), kayit))
        return sorted(sonuclar, key=lambda p: -p[0])

    def cozum_oner(
        self, mesaj: str, tip: Optional[KontrolTipi] = None
    ) -> Dict[str, List[Dict[str, object]]]:
        """Geçmişten çözüm önerir.

        Döner:
          - `oneriler`: `sonuc == COZULDU` kayıtlar (skora göre sıralı) —
            "geçen sefer bunu böyle çözmüştük".
          - `denenmis_basarisizlar`: `sonuc == BASARISIZ` kayıtlar — bunlar
            ASLA öneri olarak sunulmaz, "bunu denedik olmadı" uyarısıdır.
          - `insan_gerekenler`: `NEEDS_HUMAN` — geçmişte otomatik
            çözülemeyen sınıf; aynı hata yine çıkıyorsa döngüye girmeden
            doğrudan kullanıcıya gitmenin sinyali.
        """
        gruplar: Dict[str, List[Dict[str, object]]] = {
            "oneriler": [], "denenmis_basarisizlar": [], "insan_gerekenler": [],
        }
        for skor, kayit in self.benzer_kayitlari_bul(mesaj, tip):
            oge = {
                "skor": skor, "imza": kayit.imza, "kok_neden": kayit.kok_neden,
                "cozum": kayit.cozum, "proje": kayit.proje, "tarih": kayit.tarih,
            }
            if kayit.sonuc == Sonuc.COZULDU:
                gruplar["oneriler"].append(oge)
            elif kayit.sonuc == Sonuc.BASARISIZ:
                gruplar["denenmis_basarisizlar"].append(oge)
            else:
                gruplar["insan_gerekenler"].append(oge)
        return gruplar


# ------------------------------------------------------------------
# 3. DRC/ERC RAPORLARINDAN OTOMATİK ÖĞRENME
# ------------------------------------------------------------------

def drc_raporundan_kayit_uret(
    rapor: Dict,
    kok_neden: str,
    cozum: str,
    sonuc: Sonuc,
    proje: str = "",
    tip: KontrolTipi = KontrolTipi.DRC,
    sadece_hatalar: bool = True,
) -> List[HataKaydi]:
    """`kicad_koprusu.py::drc_calistir()`/`erc_calistir()` JSON raporundan
    hata kaydı listesi üretir.

    Aynı imzaya sahip ihlaller TEKİLLEŞTİRİLİR: 40 ayrı koordinatta çıkan
    aynı sınıf clearance ihlali TEK kayıt olur (hafızayı şişirmemek için —
    `HataHafizasi.kaydet()`'in idempotanlığıyla aynı gerekçe).

    `sadece_hatalar=True` iken `severity != "error"` olanlar atlanır;
    uyarıları da öğrenmek istiyorsan açıkça False geç.
    """
    gorulen: set = set()
    kayitlar: List[HataKaydi] = []
    for ihlal in rapor.get("violations", []):
        if sadece_hatalar and ihlal.get("severity") != "error":
            continue
        mesaj = ihlal.get("description", "").strip()
        if not mesaj:
            continue
        imza = imza_uret(mesaj)
        if imza in gorulen:
            continue
        gorulen.add(imza)
        kayitlar.append(HataKaydi(
            tip=tip, mesaj=mesaj, kok_neden=kok_neden, cozum=cozum,
            sonuc=sonuc, proje=proje,
            etiketler=[tip.value.lower(), _etiket_tahmin_et(mesaj)],
        ))
    return kayitlar


_ETIKET_ANAHTARLARI: Tuple[Tuple[str, str], ...] = (
    ("clearance", "clearance"),
    ("track width", "iz-genisligi"),
    ("annular", "annular-ring"),
    ("silk", "serigrafi"),
    ("courtyard", "courtyard"),
    ("unconnected", "baglanti-eksik"),
    ("hole", "delik"),
    ("via", "via"),
    ("power", "guc"),
    ("pin not", "pin"),
)


def _etiket_tahmin_et(mesaj: str) -> str:
    """Mesajdan kaba bir konu etiketi çıkarır (Obsidian'da gruplamak için).
    Eşleşme yoksa `genel` — uydurma bir etiket üretilmez."""
    kucuk = mesaj.lower()
    for anahtar, etiket in _ETIKET_ANAHTARLARI:
        if anahtar in kucuk:
            return etiket
    return "genel"


def hafizaya_ogret(
    hafiza: HataHafizasi,
    rapor: Dict,
    kok_neden: str,
    cozum: str,
    sonuc: Sonuc,
    proje: str = "",
    tip: KontrolTipi = KontrolTipi.DRC,
) -> int:
    """DRC/ERC raporunu hafızaya işler; EKLENEN kayıt sayısını döner."""
    return sum(
        1 for kayit in drc_raporundan_kayit_uret(rapor, kok_neden, cozum, sonuc, proje, tip)
        if hafiza.kaydet(kayit)
    )


def onceki_cozumleri_rapora_dok(hafiza: HataHafizasi, rapor: Dict) -> str:
    """Yeni bir DRC raporundaki her ihlal için hafızadan önerileri toplayıp
    Markdown özet üretir — `pcb-layout` Faz 5 döngüsüne girmeden ÖNCE
    okunacak "geçen sefer ne yapmıştık" notu.

    Hafıza boşsa bunu AÇIKÇA yazar; sessiz boş bir bölüm, "hafızada bir şey
    yok" ile "hafızaya bakılmadı"yı karıştırır.
    """
    satirlar = ["# Hata Hafızası — Önceki Çözümler", ""]
    ihlaller = [
        v.get("description", "") for v in rapor.get("violations", [])
        if v.get("description")
    ]
    if not ihlaller:
        return "\n".join(satirlar + ["- (raporda ihlal yok)"]) + "\n"

    gorulen: set = set()
    bulundu = False
    for mesaj in ihlaller:
        imza = imza_uret(mesaj)
        if imza in gorulen:
            continue
        gorulen.add(imza)
        gruplar = hafiza.cozum_oner(mesaj)
        satirlar.append(f"## `{imza}` — {mesaj}")
        if gruplar["oneriler"]:
            bulundu = True
            satirlar.append("**Geçmişte İŞE YARAYAN:**")
            for o in gruplar["oneriler"]:
                satirlar.append(
                    f"- (skor {o['skor']}) {o['cozum']} — kök neden: {o['kok_neden']} "
                    f"[{o['proje']} / {o['tarih']}]"
                )
        if gruplar["denenmis_basarisizlar"]:
            bulundu = True
            satirlar.append("**DENEMEYİN (geçmişte başarısız):**")
            for o in gruplar["denenmis_basarisizlar"]:
                satirlar.append(f"- (skor {o['skor']}) {o['cozum']}")
        if gruplar["insan_gerekenler"]:
            bulundu = True
            satirlar.append(
                "**NEEDS_HUMAN geçmişi:** bu sınıf hata daha önce otomatik "
                "çözülemedi — döngüye girmeden kullanıcıya sor."
            )
        if not any(gruplar.values()):
            satirlar.append("- hafızada eşleşme YOK (yeni sınıf hata)")
        satirlar.append("")

    if not bulundu:
        satirlar.append("> Hafıza tarandı, hiçbir ihlal için geçmiş kayıt bulunamadı.")
    return "\n".join(satirlar) + "\n"


# ------------------------------------------------------------------
# 4. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: tamamen ALAKASIZ bir mesaj, mevcut bir kayıtla
    EŞLEŞMEMELİ. Eşleşiyorsa arama her şeye "benziyor" diyordur ve öneri
    mekanizması değersizdir."""
    a = "Clearance violation (net GND and net +3V3)"
    b = "Symbol pin not connected to any net"
    return benzerlik(a, b) < 0.55


def oz_testleri_calistir() -> List[str]:
    import tempfile

    hatalar: List[str] = []

    # 1. Aynı sınıf hata, farklı koordinat -> AYNI imza
    m1 = 'Clearance violation (net "GND" and net "+3V3") at (12.34, 56.78)'
    m2 = 'Clearance violation (net "GND" and net "+3V3") at (98.76, 54.32)'
    if imza_uret(m1) != imza_uret(m2):
        hatalar.append("koordinat farkı imzayı değiştirdi (normalizasyon çalışmıyor)")

    # 2. Farklı sınıf hata -> FARKLI imza
    if imza_uret(m1) == imza_uret("Track width too small"):
        hatalar.append("farklı hata sınıfları aynı imzayı aldı")

    # 3. Yaz-oku-ara turu
    with tempfile.TemporaryDirectory() as d:
        hafiza = HataHafizasi(str(Path(d) / "Hata_Hafizasi.md"))
        kayit = HataKaydi(
            KontrolTipi.DRC, m1, "yerleşim çok sıkışık",
            "C7 2mm kaydırıldı, iz genişliği DEĞİŞTİRİLMEDİ", Sonuc.COZULDU, "TestProje",
        )
        if not hafiza.kaydet(kayit):
            hatalar.append("ilk kayıt eklenemedi")
        if hafiza.kaydet(kayit):
            hatalar.append("aynı kayıt ikinci kez eklendi (idempotan değil)")
        if len(hafiza.kayitlari_oku()) != 1:
            hatalar.append("okuma tek kaydı geri getirmedi")

        oneri = hafiza.cozum_oner(m2)  # farklı koordinat, aynı sınıf
        if not oneri["oneriler"] or oneri["oneriler"][0]["skor"] != 1.0:
            hatalar.append("imza eşleşmesiyle geçmiş çözüm bulunamadı")

        # 4. BAŞARISIZ kayıt asla öneri olmamalı
        hafiza.kaydet(HataKaydi(
            KontrolTipi.DRC, m1, "aynı kök neden",
            "iz genişliği 0.15mm'ye düşürüldü", Sonuc.BASARISIZ, "TestProje",
        ))
        oneri2 = hafiza.cozum_oner(m1)
        if any("0.15mm" in str(o["cozum"]) for o in oneri2["oneriler"]):
            hatalar.append("BAŞARISIZ çözüm öneri olarak sunuldu")
        if not oneri2["denenmis_basarisizlar"]:
            hatalar.append("BAŞARISIZ kayıt 'denemeyin' listesine düşmedi")

    # 5. Fault injection
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: benzerlik her şeye benziyor olabilir")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: hata_hafizasi.py öz testleri temiz.")
