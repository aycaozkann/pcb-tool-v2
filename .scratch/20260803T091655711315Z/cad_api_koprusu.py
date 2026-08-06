#!/usr/bin/env python3
"""
cad_api_koprusu.py
===================
Stokta olan ama KiCad kütüphanesinde BULUNMAYAN entegreler için dış CAD
varlık kaynaklarından (SnapEDA / Octopart-Nexar / Ultra Librarian mantığı)
`.kicad_sym`, `.kicad_mod` ve `.step` dosyalarını çekip projeye dahil eden
köprü.

NEDEN BU DOSYA VAR:
-------------------
`uretim_zinciri_koprusu.py::jlc_parcasi_indir()` sadece LCSC/JLCPCB
kataloğunu kapsıyor (JLC2KiCadLib). LCSC'de OLMAYAN ama DigiKey/Mouser'da
stokta bulunan bir parça (ör. bir Analog Devices/TI özel entegresi) için
projede hiçbir yol yoktu — o parçayı elle çizmek ya da parçayı hiç
kullanmamak gerekiyordu. Bu modül o boşluğu kapatır.

İKİ SERT KAPI (bu modülün asıl değeri indirme DEĞİL, DOĞRULAMADIR):
--------------------------------------------------------------------
İnternetten gelen bir sembol/footprint GÜVENİLİR DEĞİLDİR. Bu yüzden:

  1. **Lifecycle kapısı (indirmeden ÖNCE)** —
     `indirmeden_once_lifecycle_kapisi()`, MASTER_RULEBOOK Bölüm 0'ın
     *"BOM Kuralı (Kalıcı, İstisnasız): NRND/Obsolete/EOL hiçbir parça
     seçilmez, prototip/hobi amaçlı olsa bile"* kuralını UYGULAR. NRND bir
     parçanın footprint'ini indirip şematiğe koymak, o parçayı tasarıma
     kilitlemenin en sessiz yoludur — o yüzden kapı indirmenin ÖNÜNDE durur.
  2. **Pin sayısı kapısı (şematiğe işlemeden ÖNCE)** —
     `pin_sayisi_dogrula()`, MASTER_RULEBOOK Faz 1'in *"Şematik
     sembolündeki pin sayıları ile datasheet pin sayıları eşleştirilecektir
     (soğutucu pad dahil)"* kuralını UYGULAR. SnapEDA sembolleri gerçek
     hayatta yanlış/eksik pinli çıkabiliyor (özellikle exposed pad'i
     atlayanlar) — bu, indirilen varlığa körü körüne güvenmemenin ölçülebilir
     yolu.

AĞ UYARISI — HAYALİ DOSYA/URL ÜRETME YASAĞI:
---------------------------------------------
Bu ortamda ağ erişimi ve API anahtarı YOK. `api_token=None` ile çağrıldığında
`varlik_sorgula()` **hayali bir indirme URL'si veya dosya UYDURMAZ**;
`kaynak="TBD"` ile boş bir sonuç döner
(`bom_lifecycle_koprusu.nexar_sorgula(api_key=None)` ile birebir aynı
disiplin). Var olmayan bir `.kicad_sym`'i "indirdim" diye raporlamak,
şematiği sessizce yanlış pinlerle kurmanın en hızlı yoludur.
"""

from __future__ import annotations

import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from bom_lifecycle_koprusu import LifecycleDurumu, TedarikVerisi, nexar_sorgula


class Saglayici(str, Enum):
    SNAPEDA = "snapeda"
    NEXAR = "nexar"          # Octopart'ın güncel API'si
    ULTRA_LIBRARIAN = "ultra_librarian"


class VarlikTipi(str, Enum):
    SEMBOL = "kicad_sym"
    FOOTPRINT = "kicad_mod"
    MODEL_3D = "step"


# Güvenlik: indirme SADECE bu host'lardan yapılır. Rastgele bir URL'den
# dosya çekip projeye kütüphane olarak kaydetmek (ve sonra onu KiCad'in
# ayrıştırması) bir tedarik zinciri riskidir; beyaz liste bilinçli olarak
# dar tutuldu.
IZINLI_HOSTLAR: Tuple[str, ...] = (
    "snapeda.com",
    "www.snapeda.com",
    "api.snapeda.com",
    "api.nexar.com",
    "app.ultralibrarian.com",
)


@dataclass
class VarlikSorguSonucu:
    """Bir MPN için dış kaynaktan dönen (veya dönmeyen) varlık bilgisi."""

    mpn: str
    saglayici: Saglayici
    kaynak: str = "TBD"  # "api" | "TBD" | "CONFIRM"
    sembol_url: Optional[str] = None
    footprint_url: Optional[str] = None
    step_url: Optional[str] = None
    notlar: List[str] = field(default_factory=list)

    @property
    def kullanilabilir_mi(self) -> bool:
        return self.kaynak == "api" and bool(self.sembol_url or self.footprint_url)


@dataclass
class IndirilenVarlik:
    mpn: str
    sembol_yolu: Optional[str] = None
    footprint_yolu: Optional[str] = None
    step_yolu: Optional[str] = None
    kaynak: str = "TBD"
    pin_dogrulandi_mi: bool = False

    @property
    def eksikler(self) -> List[str]:
        eksik = []
        if not self.sembol_yolu:
            eksik.append(VarlikTipi.SEMBOL.value)
        if not self.footprint_yolu:
            eksik.append(VarlikTipi.FOOTPRINT.value)
        if not self.step_yolu:
            eksik.append(VarlikTipi.MODEL_3D.value)
        return eksik


# ------------------------------------------------------------------
# 1. KAPI 1 — LIFECYCLE (indirmeden ÖNCE)
# ------------------------------------------------------------------

def indirmeden_once_lifecycle_kapisi(
    mpn: str,
    api_key: Optional[str] = None,
    tedarik: Optional[TedarikVerisi] = None,
) -> Tuple[bool, str]:
    """MASTER_RULEBOOK Bölüm 0 "BOM Kuralı (Kalıcı, İstisnasız)" kapısı.

    `(izin_var, gerekce)` döner. NRND / EOL / OBSOLETE çıkan bir parça için
    izin **ASLA** verilmez — "prototip için yeterli" istisnası YOKTUR
    (kuralın gerekçesi: ESP32-C3FN4 EOL ve MPU-6050 Obsolete vakaları).

    Lifecycle BİLİNMİYORSA (`TBD`, ağ/API yok) izin verilir ama gerekçe
    açıkça `CONFIRM` olarak işaretlenir — kullanıcıya raporlanması ZORUNLU;
    "bilinmiyor"u sessizce "Active" saymak bu projede yasaktır.

    `tedarik` doğrudan verilebilir (test veya önceden yapılmış sorgu için);
    verilmezse `nexar_sorgula()` çağrılır.
    """
    veri = tedarik if tedarik is not None else nexar_sorgula(mpn, api_key=api_key)
    if veri.lifecycle in (
        LifecycleDurumu.NRND,
        LifecycleDurumu.EOL,
        LifecycleDurumu.OBSOLETE,
    ):
        return False, (
            f"{mpn}: lifecycle={veri.lifecycle.value} — MASTER_RULEBOOK Bölüm 0 "
            "'BOM Kuralı (Kalıcı, İstisnasız)' gereği CAD varlığı indirilmedi; "
            "prototip amaçlı olsa bile Active bir alternatife geçilmeli."
        )
    if veri.kaynak == "TBD":
        return True, (
            f"{mpn}: lifecycle BİLİNMİYOR (kaynak=TBD, ağ/API yok) -> CONFIRM. "
            "İndirmeye izin verildi ama üretim durumu kullanıcıya doğrulatılmalı."
        )
    return True, f"{mpn}: lifecycle={veri.lifecycle.value} (kaynak={veri.kaynak}) — indirmeye izin verildi."


# ------------------------------------------------------------------
# 2. SORGU (ağ yoksa TBD — URL UYDURMA YASAK)
# ------------------------------------------------------------------

def varlik_sorgula(
    mpn: str,
    saglayici: Saglayici = Saglayici.SNAPEDA,
    api_token: Optional[str] = None,
) -> VarlikSorguSonucu:
    """MPN için CAD varlık (sembol/footprint/3D) indirme bağlantılarını sorar.

    `api_token is None` ise **hiçbir URL uydurulmaz**: `kaynak="TBD"` döner
    ve `notlar`a ne yapılması gerektiği yazılır. Gerçek uygulama (senin
    makinende, token ile):
      1. SnapEDA: `POST https://api.snapeda.com/v1/search` (Bearer token),
         yanıttaki `models[].kicad_symbol_url` / `kicad_footprint_url` /
         `step_url` alanları alınır.
      2. Nexar (Octopart): GraphQL `supSearchMpn(q:)` -> `part.cad`
         alanındaki varlık bağlantıları.
      3. Yanıt 404/boş ise `kaynak="CONFIRM"` ile boş sonuç dönülür ve
         kullanıcıdan datasheet land-pattern'iyle ELLE oluşturma istenir —
         asla yaklaşık/benzer bir footprint ikame EDİLMEZ.
    """
    if api_token is None:
        return VarlikSorguSonucu(
            mpn=mpn,
            saglayici=saglayici,
            kaynak="TBD",
            notlar=[
                f"{saglayici.value} API token'ı verilmedi — sorgu yapılmadı, "
                "URL/dosya uydurulmadı. KURULUM.md'ye token adımı ekleyip "
                "yeniden çalıştır.",
            ],
        )
    raise NotImplementedError(
        f"{saglayici.value} sorgusu senin makinende gerçek api_token ile tamamlanmalı "
        "(bu ortamda ağ erişimi yok). Yanıt şeması doğrulanmadan bu fonksiyon "
        "sahte bir sonuç DÖNDÜRMEZ."
    )


def host_izinli_mi(url: str) -> bool:
    """URL, `IZINLI_HOSTLAR` beyaz listesinde ve HTTPS mi."""
    parcalar = urlparse(url)
    return parcalar.scheme == "https" and parcalar.netloc.lower() in IZINLI_HOSTLAR


def varlik_indir(
    url: str,
    hedef_yol: str,
    api_token: Optional[str] = None,
    zaman_asimi_s: int = 60,
) -> str:
    """Tek bir CAD varlık dosyasını indirir ve `hedef_yol`'a yazar.

    Sert kurallar:
      - `api_token is None` -> `RuntimeError` (token'sız indirme denemesi
        sessizce boş dosya bırakabilir),
      - HTTPS olmayan veya beyaz liste dışı host -> `ValueError`,
      - HTTP hatası -> hata yukarı FIRLATILIR, yarım/boş dosya BIRAKILMAZ
        (önce geçici dosyaya indirilir, başarılıysa taşınır).
    """
    if api_token is None:
        raise RuntimeError(
            "api_token olmadan indirme yapılmaz — sessizce boş/yarım kütüphane "
            "dosyası bırakmak, yanlış footprint'le kart bastırmanın yoludur."
        )
    if not host_izinli_mi(url):
        raise ValueError(f"izin verilmeyen indirme kaynağı: {url!r} (beyaz liste: {IZINLI_HOSTLAR})")

    hedef = Path(hedef_yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_suffix(hedef.suffix + ".indiriliyor")

    istek = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_token}"})
    try:  # pragma: no cover - ağ gerektirir
        with urllib.request.urlopen(istek, timeout=zaman_asimi_s) as yanit, open(gecici, "wb") as f:
            shutil.copyfileobj(yanit, f)
    except urllib.error.URLError as hata:  # pragma: no cover - ağ gerektirir
        if gecici.exists():
            gecici.unlink()
        raise RuntimeError(f"{url} indirilemedi: {hata}") from hata
    gecici.replace(hedef)  # pragma: no cover - ağ gerektirir
    return str(hedef)  # pragma: no cover - ağ gerektirir


# ------------------------------------------------------------------
# 3. KAPI 2 — PİN SAYISI (şematiğe işlemeden ÖNCE)
# ------------------------------------------------------------------

_PIN_NUMARASI = re.compile(r"\(number\s+\"([^\"]+)\"")
_PAD_NUMARASI = re.compile(r"\(pad\s+\"([^\"]+)\"")


def sembol_pin_numaralari(sembol_metni: str) -> List[str]:
    """`.kicad_sym` metninden BENZERSİZ pin numaralarını çıkarır.

    Neden benzersiz: KiCad sembollerinde aynı pin, çok-üniteli (multi-unit)
    veya de Morgan alternatif gövde stilinde TEKRAR tanımlanır. Ham `(pin`
    saymak bu yüzden pin sayısını 2-3 katına çıkarabilir ve datasheet
    karşılaştırması sahte FAIL verir. Numara kümesi bu tuzağı kapatır.
    """
    return sorted(set(_PIN_NUMARASI.findall(sembol_metni)))


def footprint_pad_numaralari(footprint_metni: str) -> List[str]:
    """`.kicad_mod` metninden benzersiz pad numaralarını çıkarır.

    NOT: Isı/soğutucu (exposed) pad genelde `"EP"`, `"41"` gibi ayrı bir
    numarayla gelir; MASTER_RULEBOOK Faz 1 onun da SAYILMASINI ve GND'ye
    bağlanmasını şart koşuyor, bu yüzden filtrelenmez.
    """
    return sorted(set(_PAD_NUMARASI.findall(footprint_metni)))


def pin_sayisi_dogrula(
    sembol_metni: str,
    datasheet_pin_sayisi: int,
    footprint_metni: Optional[str] = None,
) -> Bulgu:
    """MASTER_RULEBOOK Faz 1 pin sayısı kapısı.

    İki karşılaştırma yapar:
      1. sembol pin sayısı == datasheet pin sayısı,
      2. (footprint verildiyse) footprint pad sayısı == sembol pin sayısı.

    İkincisi kritiktir: SnapEDA'dan sembol bir varyanttan, footprint başka
    bir varyanttan gelebiliyor (ör. exposed pad'li QFN sembolü + pad'siz
    QFN footprint'i) — ERC/DRC bu uyuşmazlığı yakalamaz, ilk kart
    lehimlendiğinde anlaşılır.

    Sembolde hiç pin bulunamazsa `KAPSAM_YOK` — "0 pin, 0 ihlal, PASS"
    tuzağı `bulgu_sozlesmesi.py` sayesinde imkânsız.
    """
    pinler = sembol_pin_numaralari(sembol_metni)
    ihlaller: List[Dict[str, object]] = []

    if len(pinler) != datasheet_pin_sayisi:
        ihlaller.append({
            "kontrol": "sembol_vs_datasheet",
            "sembol_pin_sayisi": len(pinler),
            "datasheet_pin_sayisi": datasheet_pin_sayisi,
            "eksik_veya_fazla": len(pinler) - datasheet_pin_sayisi,
        })

    if footprint_metni is not None:
        padler = footprint_pad_numaralari(footprint_metni)
        if len(padler) != len(pinler):
            ihlaller.append({
                "kontrol": "footprint_vs_sembol",
                "footprint_pad_sayisi": len(padler),
                "sembol_pin_sayisi": len(pinler),
                "sembolde_olmayan_padler": sorted(set(padler) - set(pinler)),
                "footprintte_olmayan_pinler": sorted(set(pinler) - set(padler)),
            })

    return bulgu_uret(
        "cad_varlik_pin_sayisi",
        taranan=len(pinler),
        ihlaller=ihlaller,
        detay=f"datasheet={datasheet_pin_sayisi} pin, sembol={len(pinler)} pin",
    )


# ------------------------------------------------------------------
# 4. PROJEYE KAYIT (lib-table'lara idempotent ekleme)
# ------------------------------------------------------------------

_LIB_SATIRI = '  (lib (name "{nick}")(type "KiCad")(uri "{uri}")(options "")(descr "{descr}"))\n'


def lib_table_kaydi_ekle(
    tablo_yolu: str,
    nick: str,
    uri: str,
    descr: str = "cad_api_koprusu ile eklendi",
) -> bool:
    """`sym-lib-table` / `fp-lib-table` dosyasına kütüphane kaydı ekler.

    `True` = eklendi, `False` = zaten vardı (İDEMPOTENT). Aynı nick'i iki
    kez eklemek KiCad'de "duplicate library nickname" hatası verir ve proje
    AÇILMAZ — bu yüzden varlık kontrolü sessiz bir kolaylık değil, zorunlu
    bir güvenliktir.

    Dosya yoksa geçerli bir iskeletle OLUŞTURULUR (`sym_lib_table` /
    `fp_lib_table` kök düğümü dosya adından türetilir).
    """
    yol = Path(tablo_yolu)
    kok = "fp_lib_table" if "fp-lib-table" in yol.name else "sym_lib_table"

    if not yol.exists():
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(f"({kok}\n  (version 7)\n)\n", encoding="utf-8")

    icerik = yol.read_text(encoding="utf-8")
    if f'(name "{nick}")' in icerik:
        return False

    son_kapanis = icerik.rfind(")")
    if son_kapanis == -1:
        raise ValueError(f"{tablo_yolu} geçerli bir lib-table dosyası değil.")
    yeni_satir = _LIB_SATIRI.format(nick=nick, uri=uri, descr=descr)
    yol.write_text(icerik[:son_kapanis] + yeni_satir + icerik[son_kapanis:], encoding="utf-8")
    return True


def kutuphaneye_kaydet(
    varlik: IndirilenVarlik,
    proje_dizini: str,
    kutuphane_adi: str = "project_cad_api",
) -> Dict[str, object]:
    """İndirilen dosyaları proje kütüphane dizinine taşır ve lib-table'lara
    kaydeder.

    **Pin doğrulaması yapılmamış bir varlık KAYDEDİLMEZ** —
    `varlik.pin_dogrulandi_mi` False ise `PermissionError` fırlatır. Kural
    zincirinin buradan atlanabilmesi, kapının hiç olmaması demek olurdu.
    """
    if not varlik.pin_dogrulandi_mi:
        raise PermissionError(
            f"{varlik.mpn}: pin sayısı kapısı (pin_sayisi_dogrula) GEÇİLMEDEN "
            "kütüphaneye kayıt yapılamaz — MASTER_RULEBOOK Faz 1."
        )

    kok = Path(proje_dizini)
    sembol_dizini = kok / f"{kutuphane_adi}.kicad_sym"
    footprint_dizini = kok / f"{kutuphane_adi}.pretty"
    model_dizini = kok / "3d_models"
    sonuc: Dict[str, object] = {"mpn": varlik.mpn, "kayitlar": [], "tasinan": []}

    if varlik.sembol_yolu:
        kaynak = Path(varlik.sembol_yolu)
        sembol_dizini.parent.mkdir(parents=True, exist_ok=True)
        if kaynak.resolve() != sembol_dizini.resolve():
            shutil.copy(kaynak, sembol_dizini)
        sonuc["tasinan"].append(str(sembol_dizini))  # type: ignore[union-attr]
        if lib_table_kaydi_ekle(
            str(kok / "sym-lib-table"), kutuphane_adi, f"${{KIPRJMOD}}/{sembol_dizini.name}"
        ):
            sonuc["kayitlar"].append("sym-lib-table")  # type: ignore[union-attr]

    if varlik.footprint_yolu:
        footprint_dizini.mkdir(parents=True, exist_ok=True)
        hedef = footprint_dizini / Path(varlik.footprint_yolu).name
        if Path(varlik.footprint_yolu).resolve() != hedef.resolve():
            shutil.copy(varlik.footprint_yolu, hedef)
        sonuc["tasinan"].append(str(hedef))  # type: ignore[union-attr]
        if lib_table_kaydi_ekle(
            str(kok / "fp-lib-table"), kutuphane_adi, f"${{KIPRJMOD}}/{footprint_dizini.name}"
        ):
            sonuc["kayitlar"].append("fp-lib-table")  # type: ignore[union-attr]

    if varlik.step_yolu:
        model_dizini.mkdir(parents=True, exist_ok=True)
        hedef = model_dizini / Path(varlik.step_yolu).name
        if Path(varlik.step_yolu).resolve() != hedef.resolve():
            shutil.copy(varlik.step_yolu, hedef)
        sonuc["tasinan"].append(str(hedef))  # type: ignore[union-attr]

    sonuc["eksikler"] = varlik.eksikler
    return sonuc


# ------------------------------------------------------------------
# 5. RAPOR
# ------------------------------------------------------------------

def varlik_raporu_uret(
    sorgular: Sequence[VarlikSorguSonucu],
    bulgular: Sequence[Bulgu] = (),
) -> str:
    """CAD varlık edinme durumunun Markdown özeti (TEST/ dizinine yazılır).

    `kaynak == "TBD"` olan her satır açıkça "SORGULANMADI" olarak
    işaretlenir — raporu okuyan "bulunamadı" ile "hiç sorulmadı"yı ayırt
    edebilmelidir.
    """
    satirlar = [
        "# CAD Varlık Edinme Raporu (SnapEDA / Nexar)",
        "",
        "| MPN | Sağlayıcı | Durum | Sembol | Footprint | 3D |",
        "|---|---|---|---|---|---|",
    ]
    for s in sorgular:
        durum = {
            "api": "BULUNDU",
            "TBD": "SORGULANMADI (token/ağ yok)",
            "CONFIRM": "BULUNAMADI -> elle oluştur",
        }.get(s.kaynak, s.kaynak)
        satirlar.append(
            f"| {s.mpn} | {s.saglayici.value} | {durum} | "
            f"{'✔' if s.sembol_url else '—'} | {'✔' if s.footprint_url else '—'} | "
            f"{'✔' if s.step_url else '—'} |"
        )

    if bulgular:
        satirlar += ["", "## Pin sayısı kapısı (MASTER_RULEBOOK Faz 1)", ""]
        for b in bulgular:
            satirlar.append(f"- **{b.kontrol}**: {b.durum.value} — {b.detay}")
            for ihlal in b.ihlaller:
                satirlar.append(f"  - {ihlal}")

    notlar = [n for s in sorgular for n in s.notlar]
    if notlar:
        satirlar += ["", "## Notlar", ""] + [f"- {n}" for n in notlar]
    return "\n".join(satirlar) + "\n"


def varlik_raporu_yaz(hedef_yol: str, sorgular: Sequence[VarlikSorguSonucu],
                      bulgular: Sequence[Bulgu] = ()) -> str:
    yol = Path(hedef_yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(varlik_raporu_uret(sorgular, bulgular), encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# 6. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

ORNEK_SEMBOL = """\
(kicad_symbol_lib (version 20231120) (generator "cad_api_koprusu")
  (symbol "TEST_IC"
    (symbol "TEST_IC_1_1"
      (pin power_in line (at 0 0 0) (length 2.54)
        (name "VDD") (number "1"))
      (pin passive line (at 0 -2.54 0) (length 2.54)
        (name "GND") (number "2"))
      (pin bidirectional line (at 0 -5.08 0) (length 2.54)
        (name "SDA") (number "3"))
    )
    (symbol "TEST_IC_1_2"
      (pin power_in line (at 0 0 0) (length 2.54)
        (name "VDD") (number "1"))
    )
  )
)
"""

ORNEK_FOOTPRINT = """\
(footprint "TEST_IC" (layer "F.Cu")
  (pad "1" smd rect (at -1 0) (size 0.6 0.3) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "2" smd rect (at 0 0) (size 0.6 0.3) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "3" smd rect (at 1 0) (size 0.6 0.3) (layers "F.Cu" "F.Paste" "F.Mask"))
)
"""


def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: datasheet pin sayısını bilerek yanlış verirsek kapı
    FAIL vermek ZORUNDA. Aksi halde pin karşılaştırması hiçbir şey
    doğrulamıyordur."""
    bozuk = pin_sayisi_dogrula(ORNEK_SEMBOL, datasheet_pin_sayisi=8)
    return not bozuk.gecti_mi


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. Çok-üniteli sembolde pin numarası TEKRARI sayılmamalı (3, 4 değil)
    if sembol_pin_numaralari(ORNEK_SEMBOL) != ["1", "2", "3"]:
        hatalar.append("çok-üniteli sembolde benzersiz pin numaraları çıkarılamadı")

    # 2. Doğru pin sayısıyla PASS
    if not pin_sayisi_dogrula(ORNEK_SEMBOL, 3, ORNEK_FOOTPRINT).gecti_mi:
        hatalar.append("doğru pin sayısında PASS alınamadı")

    # 3. Fault injection
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: pin karşılaştırması boş olabilir")

    # 4. Token yoksa URL UYDURULMAMALI
    sorgu = varlik_sorgula("AD7124-8BCPZ", api_token=None)
    if sorgu.kaynak != "TBD" or sorgu.sembol_url is not None:
        hatalar.append("token yokken sahte URL/kaynak üretildi")

    # 5. NRND parça için lifecycle kapısı KAPALI olmalı
    nrnd = TedarikVerisi(mpn="MPU-6050", lifecycle=LifecycleDurumu.OBSOLETE, kaynak="nexar")
    izin, _ = indirmeden_once_lifecycle_kapisi("MPU-6050", tedarik=nrnd)
    if izin:
        hatalar.append("Obsolete parça için indirme izni verildi (Bölüm 0 ihlali)")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: cad_api_koprusu.py öz testleri temiz.")
