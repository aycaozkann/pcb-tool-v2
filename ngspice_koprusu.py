#!/usr/bin/env python3
"""
ngspice_koprusu.py
===================
Şematik fazından sonra devreyi GERÇEKTEN simüle eden köprü: KiCad'in
`kicad-cli`'siyle SPICE netlist'i çıkarır, `ngspice`'ı CLI (batch) modunda
çağırır, DC/AC sweep sonuçlarını ayrıştırır ve voltaj düşümü (IR drop)
kabul kriterlerini PASS/FAIL olarak döndürür.

NEDEN BU DOSYA VAR:
-------------------
`MASTER_RULEBOOK.md` Faz 3, `TEST/simulasyon_raporu.md`'yi ZORUNLU kılıyor
ve EK checklist'te şunu ayrıca soruyor: *"kullanılan modelin (gerçek üretici
modeli mi, davranışsal mı) türü ve davranışsal ise neyi yansıtmadığı
belirtildi mi?"* — ama bugüne kadar bu raporu üretecek hiçbir kod yoktu;
"davranışsal simülasyon" pratikte modelin kafasından yazdığı bir metindi.
Bu modül o raporun ARKASINA gerçek bir çözücü koyar.

EN ÖNEMLİ KURAL — SAYI UYDURMA YASAĞI:
---------------------------------------
`ngspice` kurulu değilse bu modül **hiçbir simülasyon sonucu ÜRETMEZ**.
`bulgu_sozlesmesi.py`'nin `KAPSAM_YOK` durumu döner ve rapora "simülasyon
KOŞULMADI" yazılır. `bom_lifecycle_koprusu.py::nexar_sorgula(api_key=None)`
nasıl hayali stok/fiyat üretmiyorsa (`kaynak="TBD"`), bu modül de hayali
voltaj/akım üretmez. Bir simülasyon raporundaki uydurma sayı, hiç rapor
olmamasından DAHA tehlikelidir — çünkü PASS gibi görünür.

DOĞRULAMA DURUMU (bu makinede GERÇEKTEN koşturuldu):
----------------------------------------------------
  - **ngspice: DOĞRULANDI.** `ngspice-46` bulundu; davranışsal bir LDO+yük
    devresiyle gerçek bir `.dc` sweep koşturuldu, `cikti_ayristir()` 5 veri
    satırını doğru okudu ve `voltaj_dususu_dogrula()` 358.8mV'lik düşümü
    FAIL olarak raporladı. Yani bu modülün çalıştırma+ayrıştırma+karar
    zinciri uydurma değil, ölçülmüş.
  - **Windows tuzağı (ölçüldü):** `ngspice.exe` interaktif yapıdır ve
    `--version` dahil her çağrıda donar (stdin=/dev/null verilse bile 30s
    timeout). Otomasyonda `ngspice_con.exe` KULLANILMALIDIR — bkz.
    `NGSPICE_ADAYLARI`.
  - **kicad-cli netlist ihracı: DOĞRULANDI.** KiCad 10.0'ın
    `sch export netlist --format spice` bayrakları birebir bu modüldeki
    komutla eşleşiyor ve gerçek `ESP32C3_SmartBand.kicad_sch` üzerinde
    çalıştı. Bu koşum, `sembol_modeli_eksik_olanlar()`'daki bir HATAYI da
    ortaya çıkardı (bkz. o fonksiyonun docstring'i) — modelsiz semboller
    `U4 __U4` biçiminde çıkıyor, `X...` olarak değil.
  - **HÂLÂ DOĞRULANMADI:** gerçek bir üretici `.lib`/`.subckt` modeliyle
    (ör. TI/ADI SPICE modeli) uçtan uca koşum ve `.ac` analizinin gerçek
    devrede yakınsaması. `ngspice_surumu()` gerçek sürümü rapora basar,
    böylece raporu okuyan hangi çözücünün koştuğunu (veya koşmadığını) görür.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from bulgu_sozlesmesi import Bulgu, BulguDurumu, bulgu_uret


class ModelTuru(str, Enum):
    """MASTER_RULEBOOK Faz 3'ün "hangi model kullanıldı" sorusunun cevabı.

    Rapora YAZILMASI ZORUNLU — bir davranışsal modelle alınan PASS ile
    üretici SPICE modeliyle alınan PASS aynı şey değildir.
    """

    URETICI_SPICE = "URETICI_SPICE"      # üreticinin resmi .lib/.sub modeli
    DAVRANISSAL = "DAVRANISSAL"          # ideal kaynak/direnç eşdeğeri
    BILINMIYOR = "BILINMIYOR"


@dataclass
class DcSweep:
    """`.dc <kaynak> <baslangic> <bitis> <adim>`"""

    kaynak: str
    baslangic_v: float
    bitis_v: float
    adim_v: float

    def spice_satiri(self) -> str:
        return f".dc {self.kaynak} {self.baslangic_v} {self.bitis_v} {self.adim_v}"


@dataclass
class AcSweep:
    """`.ac <tip> <nokta> <f_baslangic> <f_bitis>`"""

    f_baslangic_hz: float
    f_bitis_hz: float
    nokta_sayisi: int = 20
    tip: str = "dec"  # dec | oct | lin

    def spice_satiri(self) -> str:
        if self.tip not in ("dec", "oct", "lin"):
            raise ValueError(f"geçersiz AC sweep tipi: {self.tip!r}")
        return f".ac {self.tip} {self.nokta_sayisi} {self.f_baslangic_hz} {self.f_bitis_hz}"


@dataclass
class OpAnalizi:
    """`.op` — çalışma noktası (operating point). IR drop / rail doğrulaması
    için en doğrudan analiz."""

    def spice_satiri(self) -> str:
        return ".op"


@dataclass
class TranAnalizi:
    """`.tran <adim_s> <sure_s> [<baslangic_s>]` — zaman-domeni (transient)
    analiz. "Sanal osiloskop probu" modunun temeli: DC/AC sweep'in aksine
    sweep ekseni ZAMANDIR — `cikti_ayristir()` "time" başlığını ZATEN
    tanıyor (bkz. `sweep_var` tespiti), bu yüzden mevcut ayrıştırma/koşum
    zinciri (`netlist_analiz_ekle`, `ngspice_calistir`) DEĞİŞTİRİLMEDEN
    tekrar kullanılabildi."""

    adim_s: float
    sure_s: float
    baslangic_s: float = 0.0

    def spice_satiri(self) -> str:
        if self.baslangic_s > 0:
            return f".tran {self.adim_s} {self.sure_s} {self.baslangic_s}"
        return f".tran {self.adim_s} {self.sure_s}"


@dataclass
class SimulasyonSonucu:
    """Ayrıştırılmış ngspice çıktısı.

    `veri[dugum_ismi]` -> (sweep_degeri, olculen_deger) çiftleri listesi.
    `.op` analizinde sweep değeri 0.0'dır (tek nokta).
    """

    veri: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    satir_sayisi: int = 0
    ham_cikti: str = ""
    ngspice_surumu: str = "BILINMIYOR"

    def son_deger(self, dugum: str) -> Optional[float]:
        seri = self.veri.get(dugum)
        return seri[-1][1] if seri else None

    def min_deger(self, dugum: str) -> Optional[float]:
        seri = self.veri.get(dugum)
        return min(v for _, v in seri) if seri else None


# ------------------------------------------------------------------
# 1. ARAÇ VARLIK KONTROLÜ (yoksa sessiz sayı UYDURMA yerine KAPSAM_YOK)
# ------------------------------------------------------------------

# Windows'ta ngspice İKİ ayrı çalıştırılabilirle gelir ve YANLIŞ OLANI
# SEÇMEK OTOMASYONU KİLİTLER — bu, bu makinede bilfiil yaşandı:
#   - `ngspice.exe`     : interaktif/GUI (BLT) yapı. `--version` dahil HER
#     çağrıda kendi konsolunu açıp komut bekler; stdin `/dev/null` verilse
#     bile dönmez (30s timeout ile ölçüldü).
#   - `ngspice_con.exe` : konsol yapısı. Headless/batch otomasyonda
#     KULLANILMASI GEREKEN budur (ngspice-46 sürüm çıktısını anında bastı).
# Bu yüzden arama sırası bilinçli olarak `ngspice_con` ile BAŞLAR.
NGSPICE_ADAYLARI: Tuple[str, ...] = ("ngspice_con", "ngspice")


def ngspice_yolu_bul(ngspice: Optional[str] = None) -> Optional[str]:
    """ngspice çalıştırılabilirinin tam yolu, yoksa `None`.

    `ngspice=None` (varsayılan) iken `NGSPICE_ADAYLARI` sırayla denenir —
    Windows'ta konsol yapısı (`ngspice_con`) tercih edilir (yukarıdaki nota
    bak). Açıkça bir isim/yol verilirse SADECE o denenir.

    `KURULUM.md`'nin araç-varlık denetimi deseniyle aynı: eksikse akış
    DURUR/atlanır, "kurulu varsay" YASAK.
    """
    if ngspice is not None:
        return shutil.which(ngspice)
    for aday in NGSPICE_ADAYLARI:
        yol = shutil.which(aday)
        if yol:
            return yol
    return None


def ngspice_surumu(ngspice: Optional[str] = None, zaman_asimi_s: int = 20) -> str:
    """Gerçek sürüm string'i — rapora basılır ki hangi çözücünün koştuğu
    (veya koşmadığı) belgelenmiş olsun. Kurulu değilse "YOK".

    `stdin` bilinçli olarak `DEVNULL`'a bağlanır: interaktif yapı yanlışlıkla
    seçilirse süresiz beklemek yerine timeout'a düşüp AÇIKÇA
    "CALISTIRILAMADI" raporlaması gerekir — sessizce donmuş bir akış, hatalı
    bir rapordan daha kötüdür.
    """
    yol = ngspice_yolu_bul(ngspice)
    if yol is None:
        return "YOK"
    try:
        sonuc = subprocess.run(
            [yol, "--version"],
            capture_output=True,
            text=True,
            timeout=zaman_asimi_s,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as hata:  # pragma: no cover - ortam bağımlı
        return f"CALISTIRILAMADI ({hata})"
    metin = (sonuc.stdout or "") + (sonuc.stderr or "")
    for satir in metin.splitlines():
        s = satir.strip().lstrip("*").strip()
        if "ngspice" in s.lower():
            return s
    ilk_satir = next((s.strip() for s in metin.splitlines() if s.strip()), "")
    return ilk_satir or "BILINMIYOR"


# ------------------------------------------------------------------
# 2. SPICE NETLIST ÜRETİMİ (kicad-cli) + ön kontroller
# ------------------------------------------------------------------

def spice_netlist_uret(
    schematic_path: str,
    cikti_path: str = "devre.cir",
    kicad_cli: str = "kicad-cli",
) -> str:
    """`kicad-cli sch export netlist --format spice` sarmalayıcısı.

    `kicad_koprusu.py::erc_calistir()` ile aynı subprocess deseni. Bayrak
    adı/çıktı biçimi KiCad 10'da DOĞRULANMADI (dosya başlığındaki uyarı) —
    başarısız olursa `RuntimeError` fırlatır, sessizce boş netlist üretmez.
    """
    komut = [
        kicad_cli, "sch", "export", "netlist",
        "--format", "spice",
        "--output", cikti_path,
        schematic_path,
    ]
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise RuntimeError(f"kicad-cli spice netlist üretemedi: {sonuc.stderr}")
    if not Path(cikti_path).exists():
        raise RuntimeError(f"{cikti_path} oluşmadı — kicad-cli çıktısı: {sonuc.stdout}")
    return cikti_path


def sembol_modeli_eksik_olanlar(netlist_metni: str) -> List[str]:
    """SPICE modeli olmayan komponentleri (simüle EDİLEMEZ olanları) bulur.

    KiCad'de bir sembole `Spice_Model`/`Sim.Device` alanı girilmemişse o parça
    netlist'e ÇIKAR ama modelsiz çıkar — simülasyon sessizce anlamsız bir
    sonuç verir. Bunu ÖNCEDEN raporlamak gerekir (MASTER_RULEBOOK Faz 3'ün
    "davranışsal ise neyi yansıtmadığını belirt" kuralının somut girdisi).

    GERÇEK VERİYLE DOĞRULANDI (ve ilk taslaktaki hatayı düzeltti): bu makinede
    KiCad 10.0'ın `kicad-cli sch export netlist --format spice` çıktısı
    (ESP32C3_SmartBand.kicad_sch, 45 satır) modelsiz sembolleri şu biçimde
    yazıyor:

        U4 __U4
        Y1 __Y1
        J1 __J1

    yani **refdes'in kendisiyle, `__` ön ekli bir model adıyla** — `X` ön ekli
    klasik subckt örneği OLARAK DEĞİL. İlk taslak sadece `X...` satırlarına
    baktığı için bu 12 modelsiz parçanın HİÇBİRİNİ yakalamıyordu; ölçüm
    olmadan yazılmış bir sezgiselin nasıl sessizce boş kaldığının somut
    örneği. Artık iki desen birlikte kontrol edilir:
      1. son token'ı `__` ile başlayan her komponent satırı (KiCad'in
         "model atanmadı" işareti),
      2. `X` ön ekli, karşılığında `.subckt`/`.include`/`.lib` bulunmayan
         alt-devre örnekleri.
    """
    tanimlanan: set[str] = set()
    for satir in netlist_metni.splitlines():
        m = re.match(r"^\.subckt\s+(\S+)", satir.strip(), re.IGNORECASE)
        if m:
            tanimlanan.add(m.group(1).lower())
    dis_kaynak_var = any(
        s.strip().lower().startswith((".include", ".lib"))
        for s in netlist_metni.splitlines()
    )

    eksikler: List[str] = []
    for satir in netlist_metni.splitlines():
        s = satir.strip()
        if not s or s.startswith(("*", ".")):
            continue
        parcalar = s.split()
        if len(parcalar) < 2:
            continue
        model = parcalar[-1]

        # 1) KiCad'in "model atanmadı" işareti: `U4 __U4`
        if model.startswith("__"):
            eksikler.append(parcalar[0])
            continue

        # 2) Klasik subckt örneği, tanımı/`.include`'ı yok
        if s[0].upper() == "X" and len(parcalar) >= 3:
            if model.lower() not in tanimlanan and not dis_kaynak_var:
                eksikler.append(parcalar[0])
    return eksikler


def netlist_analiz_ekle(
    netlist_metni: str,
    analiz,
    izlenen_dugumler: Sequence[str],
) -> str:
    """Netlist'e analiz komutunu ve batch modda çıktı basacak `.control`
    bloğunu ekler.

    `print` (ASCII tablo) bilinçli olarak `wrdata` (ikili/ayrı dosya)
    yerine seçildi: tek bir stdout akışı ayrıştırmak, geçici dosya
    yönetiminden daha az kırılgan ve `cikti_ayristir()` ile birebir test
    edilebilir.
    """
    if not izlenen_dugumler:
        raise ValueError("en az bir izlenen düğüm verilmeli (neyi ölçtüğünü bilmeyen simülasyon rapor değildir).")

    izleme = " ".join(f"v({d})" if not d.lower().startswith("v(") else d for d in izlenen_dugumler)
    govde = netlist_metni.rstrip()
    # `.end` varsa analiz/kontrol bloğu ondan ÖNCE gelmeli.
    if govde.lower().endswith(".end"):
        govde = govde[: -len(".end")].rstrip()

    return (
        f"{govde}\n"
        f"{analiz.spice_satiri()}\n"
        f".control\n"
        f"run\n"
        f"print {izleme}\n"
        f".endc\n"
        f".end\n"
    )


# ------------------------------------------------------------------
# 3. ÇALIŞTIRMA VE ÇIKTI AYRIŞTIRMA
# ------------------------------------------------------------------

_VERI_SATIRI = re.compile(r"^\s*(\d+)\s+(.+)$")
_SAYI = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def cikti_ayristir(metin: str) -> SimulasyonSonucu:
    """ngspice batch (`-b`) `print` çıktısının ASCII tablosunu ayrıştırır.

    Beklenen biçim (gerçek ngspice çıktısı):
        Index   v-sweep         v(out)
        --------------------------------
        0	0.000000e+00	0.000000e+00
        1	1.000000e-01	9.900000e-02

    İlk sütun (Index) atılır, ikinci sütun sweep ekseni (`v-sweep`,
    `frequency`, `time`), kalan sütunlar izlenen düğümlerdir. `.op`
    analizinde sweep sütunu olmayabilir; o durumda sweep değeri 0.0 kabul
    edilir.

    Hiçbir veri satırı bulunamazsa BOŞ sonuç döner — `voltaj_dususu_dogrula`
    bunu `KAPSAM_YOK`'a çevirir, sessizce PASS'a ÇEVİRMEZ.
    """
    sonuc = SimulasyonSonucu(ham_cikti=metin)
    basliklar: List[str] = []
    sweep_var = False

    for satir in metin.splitlines():
        s = satir.rstrip()
        if not s:
            continue
        if s.strip().lower().startswith("index"):
            basliklar = s.split()[1:]  # "Index" atılır
            sweep_var = bool(basliklar) and basliklar[0].lower() in (
                "v-sweep", "frequency", "time", "sweep", "i-sweep", "temp-sweep",
            )
            veri_basliklari = basliklar[1:] if sweep_var else basliklar
            sonuc.veri = {b: [] for b in veri_basliklari}
            continue
        if not basliklar:
            continue
        m = _VERI_SATIRI.match(s)
        if not m:
            continue
        sayilar = [float(x) for x in _SAYI.findall(m.group(2))]
        if not sayilar:
            continue
        if sweep_var:
            sweep_degeri, degerler = sayilar[0], sayilar[1:]
        else:
            sweep_degeri, degerler = 0.0, sayilar
        veri_basliklari = basliklar[1:] if sweep_var else basliklar
        for baslik, deger in zip(veri_basliklari, degerler):
            sonuc.veri.setdefault(baslik, []).append((sweep_degeri, deger))
        sonuc.satir_sayisi += 1

    return sonuc


def ngspice_calistir(
    netlist_path: str,
    ngspice: Optional[str] = None,
    zaman_asimi_s: int = 120,
) -> Optional[SimulasyonSonucu]:
    """ngspice'ı batch (`-b`) modda koşturur ve ayrıştırılmış sonucu döner.

    `ngspice` KURULU DEĞİLSE `None` döner — hata FIRLATMAZ ama sahte sonuç
    da ÜRETMEZ (dosya başlığındaki "sayı uydurma yasağı"). Çağıran taraf
    `None` gördüğünde `KAPSAM_YOK` raporlamak zorundadır; bunun kolay yolu
    `voltaj_dususu_dogrula()`'yı kullanmaktır.

    ngspice, yakınsama uyarılarında sıfır olmayan çıkış kodu dönebilir ama
    yine de kullanılabilir çıktı basar; bu yüzden returncode tek başına
    başarısızlık ölçütü SAYILMAZ — ayrıştırılan satır sayısı esastır.
    """
    yol = ngspice_yolu_bul(ngspice)
    if yol is None:
        return None
    if not Path(netlist_path).exists():
        raise FileNotFoundError(f"{netlist_path} bulunamadı.")

    sonuc = subprocess.run(
        [yol, "-b", netlist_path],
        capture_output=True,
        text=True,
        timeout=zaman_asimi_s,
        stdin=subprocess.DEVNULL,  # interaktif yapı seçilirse donma yerine timeout
    )
    ayristirilmis = cikti_ayristir((sonuc.stdout or "") + "\n" + (sonuc.stderr or ""))
    ayristirilmis.ngspice_surumu = ngspice_surumu(ngspice)
    return ayristirilmis


# ------------------------------------------------------------------
# 4. KABUL KRİTERLERİ (voltaj düşümü / rail doğrulaması)
# ------------------------------------------------------------------

@dataclass
class RayHedefi:
    """Bir güç rayının simülasyondan beklenen davranışı.

    `tolerans_yuzde`, MASTER_RULEBOOK Faz 2'nin worst-case tolerans zinciri
    maddesiyle uyumlu olarak, ÜST kademenin ΔVOUT'u da düşülmüş bir hedef
    olmalıdır — bu dataclass o hesabı YAPMAZ, sadece sonucu taşır (hesap
    `pcb_faz1_2` tarzı CSV raporunda yapılır ve buraya girdi olur).
    """

    dugum: str
    nominal_v: float
    tolerans_yuzde: float = 5.0
    min_kabul_v: Optional[float] = None  # verilirse tolerans yerine BU kullanılır

    @property
    def alt_sinir_v(self) -> float:
        if self.min_kabul_v is not None:
            return self.min_kabul_v
        return self.nominal_v * (1.0 - self.tolerans_yuzde / 100.0)


def voltaj_dususu_dogrula(
    sonuc: Optional[SimulasyonSonucu],
    hedefler: Sequence[RayHedefi],
) -> Bulgu:
    """Her ray için simülasyonda ölçülen EN KÖTÜ (minimum) gerilimi kabul
    sınırıyla karşılaştırır — PASS/FAIL.

    En kötü değer (`min_deger`) kullanılır, ortalama veya son değer DEĞİL:
    bir rayın sweep'in ortasında sınırın altına düşüp sonra toparlanması
    da bir başarısızlıktır (o anda MCU reset atar).

    `sonuc is None` (ngspice yok) veya hiç veri satırı yoksa -> `KAPSAM_YOK`.
    Bu, "simülasyon geçti" DEĞİLDİR ve `Bulgu.gecti_mi` False döner.
    """
    if sonuc is None:
        return bulgu_uret(
            "simulasyon_voltaj_dususu",
            taranan=0,
            detay="ngspice kurulu değil — simülasyon KOŞULMADI (sonuç uydurulmadı).",
        )
    if sonuc.satir_sayisi == 0:
        return bulgu_uret(
            "simulasyon_voltaj_dususu",
            taranan=0,
            detay="ngspice çıktısında ayrıştırılabilir veri satırı yok — netlist/analiz hatalı olabilir.",
        )

    ihlaller: List[Dict[str, object]] = []
    taranan = 0
    for hedef in hedefler:
        # `taranan`, İNCELENEN HEDEF sayısıdır (çıktıda bulunan düğüm sayısı
        # değil): düğüm hiç izlenmemişse bu bir İHLALDİR, kapsam boşluğu
        # değil — aksi halde tek hedefi izlemeyi unutmak sessizce
        # KAPSAM_YOK'a düşer ve ihlal görünmez olur (testle yakalandı).
        taranan += 1
        anahtar = hedef.dugum if hedef.dugum in sonuc.veri else f"v({hedef.dugum})"
        if anahtar not in sonuc.veri:
            ihlaller.append({
                "dugum": hedef.dugum,
                "sebep": "simülasyon çıktısında bu düğüm YOK (izlenen düğümler arasına eklenmemiş)",
            })
            continue
        olculen = sonuc.min_deger(anahtar)
        if olculen is None:
            continue
        if olculen < hedef.alt_sinir_v:
            ihlaller.append({
                "dugum": hedef.dugum,
                "nominal_v": hedef.nominal_v,
                "alt_sinir_v": round(hedef.alt_sinir_v, 6),
                "olculen_min_v": round(olculen, 6),
                "dusum_mv": round((hedef.nominal_v - olculen) * 1000.0, 3),
            })

    return bulgu_uret(
        "simulasyon_voltaj_dususu",
        taranan=taranan,
        ihlaller=ihlaller,
        detay=f"ngspice={sonuc.ngspice_surumu}, veri_satiri={sonuc.satir_sayisi}",
    )


def ac_bant_dogrula(
    sonuc: Optional[SimulasyonSonucu],
    dugum: str,
    min_kazanc_db: float,
    f_alt_hz: float,
    f_ust_hz: float,
) -> Bulgu:
    """AC sweep'te belirtilen bantta kazancın `min_kazanc_db`'nin ALTINA
    düşmediğini doğrular (ör. besleme filtresinin geçirme bandı, PDN
    empedansı).

    dB dönüşümü BURADA yapılmaz: ngspice `print v(out)` ile lineer büyüklük
    basar; bant içi en küçük lineer değer dB'ye çevrilir. Girdi 0 veya
    negatifse (yakınsama artefaktı) o nokta ATLANIR ve `detay`e yazılır —
    sessizce -inf dB üretip FAIL basmak yanıltıcı olurdu.
    """
    if sonuc is None or sonuc.satir_sayisi == 0:
        return bulgu_uret(
            "simulasyon_ac_bant",
            taranan=0,
            detay="ngspice yok veya çıktı boş — AC analizi KOŞULMADI.",
        )
    import math

    anahtar = dugum if dugum in sonuc.veri else f"v({dugum})"
    seri = sonuc.veri.get(anahtar, [])
    bant = [(f, v) for f, v in seri if f_alt_hz <= f <= f_ust_hz]
    gecerli = [(f, v) for f, v in bant if v > 0]
    atlanan = len(bant) - len(gecerli)
    if not gecerli:
        return bulgu_uret(
            "simulasyon_ac_bant",
            taranan=0,
            detay=f"{f_alt_hz}-{f_ust_hz}Hz bandında geçerli (pozitif) veri noktası yok.",
        )

    ihlaller: List[Dict[str, object]] = []
    for f, v in gecerli:
        db = 20.0 * math.log10(v)
        if db < min_kazanc_db:
            ihlaller.append({
                "frekans_hz": f, "kazanc_db": round(db, 3), "min_kazanc_db": min_kazanc_db,
            })
    return bulgu_uret(
        "simulasyon_ac_bant",
        taranan=len(gecerli),
        ihlaller=ihlaller,
        detay=f"bant={f_alt_hz}-{f_ust_hz}Hz, atlanan_gecersiz_nokta={atlanan}",
    )


# ------------------------------------------------------------------
# 4b. TRANSIENT (.tran) — "sanal osiloskop probu"
# ------------------------------------------------------------------
#
# GÖREV (openEMS/SI köprüsü ile birlikte istendi): herhangi bir net'te
# zamana göre voltaj/akım eğrisi, CSV + PNG grafik olarak. Bu, DC/AC
# sweep'in YANINA eklendi — mevcut `spice_netlist_uret`/`netlist_analiz_ekle`/
# `ngspice_calistir`/`cikti_ayristir` zincirinin HİÇBİRİ değiştirilmedi,
# sadece `TranAnalizi` (yukarıda) bu zincire YENİ bir analiz tipi olarak
# eklendi ve bu fonksiyon CSV/PNG çıktısını üstüne koyuyor.


def _dosya_adi_guvenli(net_adi: str) -> str:
    """Bir net adını (ör. "v(vout)", "I2C_SDA") güvenli bir dosya adı
    parçasına çevirir — alfasayısal olmayan karakterler `_` ile değişir."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", net_adi).strip("_") or "net"


def transient_calistir(
    netlist_path: str,
    sure_s: float,
    adim_s: float,
    prob_netleri: Sequence[str],
    calisma_dizini: str,
    ngspice: Optional[str] = None,
    zaman_asimi_s: int = 120,
) -> Bulgu:
    """`.tran` koşumu — her `prob_netleri` girdisi için (zaman, voltaj)
    çift serisi `calisma_dizini/tran_<net>.csv`'ye yazılır, hepsi TEK bir
    `calisma_dizini/tran_osiloskop.png` grafiğinde üst üste çizilir
    ("sanal osiloskop probu").

    SAYI UYDURMA YASAĞI (dosyanın geri kalanıyla AYNI disiplin): `ngspice`
    kurulu değilse (`ngspice_calistir()` `None` dönerse) HİÇBİR CSV/PNG
    YAZILMAZ, `KAPSAM_YOK` döner. `matplotlib` kurulu değilse CSV'ler yine
    yazılır (ham veri, çizim ayrı bir katman) ama PNG atlanır — bu durum
    `detay` alanına açıkça yazılır, sessizce yok sayılmaz.

    Her `prob_netleri` girdisi simülasyon çıktısında BULUNAMAZSA (net
    netlist'te yok / izlenen düğümler arasına eklenmemiş) bu bir İHLALDİR
    (`voltaj_dususu_dogrula`'nın "düğüm çıktıda yok" deseniyle AYNI) —
    sessizce atlanmaz, `taranan` her zaman `len(prob_netleri)`'tir.

    DOĞRULAMA DURUMU: bu makinede `ngspice_con.exe` KURULU — RC şarj/deşarj
    devresi gibi basit bir devrede uçtan uca (netlist -> .tran -> CSV/PNG)
    GERÇEKTEN koşturulup test edildi, bkz. `test_ngspice_koprusu.py`.
    """
    if not prob_netleri:
        raise ValueError(
            "en az bir prob net verilmeli — neyi ölçtüğünü bilmeyen bir "
            "'osiloskop' rapor değildir."
        )

    kontrol = "ngspice_transient"
    netlist_metni = Path(netlist_path).read_text(encoding="utf-8")
    analiz = TranAnalizi(adim_s=adim_s, sure_s=sure_s)
    tran_netlist_metni = netlist_analiz_ekle(netlist_metni, analiz, prob_netleri)

    tran_netlist_path = str(Path(netlist_path).with_name(Path(netlist_path).stem + "_tran.cir"))
    Path(tran_netlist_path).write_text(tran_netlist_metni, encoding="utf-8")

    sonuc = ngspice_calistir(tran_netlist_path, ngspice=ngspice, zaman_asimi_s=zaman_asimi_s)
    if sonuc is None:
        return bulgu_uret(
            kontrol, taranan=0,
            detay="ngspice kurulu değil — transient (.tran) simülasyonu KOŞULMADI.",
        )
    if sonuc.satir_sayisi == 0:
        return bulgu_uret(
            kontrol, taranan=0,
            detay="ngspice çıktısında ayrıştırılabilir veri satırı yok — netlist/analiz hatalı olabilir.",
        )

    calisma_dir = Path(calisma_dizini)
    calisma_dir.mkdir(parents=True, exist_ok=True)

    taranan = 0
    ihlaller: List[Dict[str, object]] = []
    seriler: Dict[str, List[Tuple[float, float]]] = {}
    for net in prob_netleri:
        taranan += 1
        anahtar = net if net in sonuc.veri else f"v({net})"
        seri = sonuc.veri.get(anahtar)
        if not seri:
            ihlaller.append({
                "net": net,
                "sebep": "simülasyon çıktısında bu düğüm YOK (izlenen düğümler arasına eklenmemiş veya netlist'te yok)",
            })
            continue
        seriler[net] = seri
        csv_yolu = calisma_dir / f"tran_{_dosya_adi_guvenli(net)}.csv"
        with open(csv_yolu, "w", newline="", encoding="utf-8") as fh:
            yazici = csv.writer(fh)
            yazici.writerow(["zaman_s", "voltaj_v"])
            yazici.writerows(seri)

    png_yolu: Optional[Path] = None
    matplotlib_yok_notu = ""
    if seriler:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            matplotlib_yok_notu = " matplotlib kurulu değil — PNG üretilmedi, sadece CSV yazıldı."
        else:
            fig, ax = plt.subplots()
            for net, seri in seriler.items():
                ax.plot([t for t, _ in seri], [v for _, v in seri], label=net)
            ax.set_xlabel("zaman (s)")
            ax.set_ylabel("voltaj (V)")
            ax.set_title("Sanal Osiloskop (ngspice .tran)")
            ax.legend()
            ax.grid(True)
            png_yolu = calisma_dir / "tran_osiloskop.png"
            fig.savefig(png_yolu)
            plt.close(fig)

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"ngspice={sonuc.ngspice_surumu}, sure_s={sure_s}, adim_s={adim_s}, "
        f"csv_yazilan_netler={sorted(seriler.keys())}, "
        f"png={str(png_yolu) if png_yolu else '(yazilmadi)'}."
        + matplotlib_yok_notu,
    )


# ------------------------------------------------------------------
# 4c. PDN OTOMATİK DEKUPLAJ ÖNERİSİ (FAZ 0.5-3)
# ------------------------------------------------------------------
#
# NEDEN BU BÖLÜM VAR: `voltaj_dususu_dogrula()` bir rayın tolerans dışına
# ÇIKTIĞINI SÖYLER ama "peki ne ekleyeyim" sorusuna cevap VERMEZ — bu
# bölüm o boşluğu, `voltaj_dususu_dogrula()`'nın ÜRETTİĞİ Bulgu'yu GİRDİ
# olarak alıp kapatır (simülasyonu TEKRARLAMAZ, sadece SONUCUNU YORUMLAR).

@dataclass
class DekuplajOnerisi:
    """Bir ray için üretilen kapasitör değeri + yerleşim mesafesi önerisi."""

    dugum: str
    onerilen_kapasitans_f: List[float]  # ör. [100e-9] ya da [100e-9, 10e-6]
    maks_mesafe_mm: float
    gerekce: str


# Eşik-bazlı, KURAL-OF-THUMB kademeler — gerçek geçici akım (dI/dt) ve ESR
# verisi olmadan KESİN bir C = I*dt/dV hesabı YAPILAMAZ (`voltaj_dususu_
# dogrula()`'nın Bulgu'sunda sadece nominal/ölçülen gerilim vardır, akım
# YOKTUR). Bu tablo "düşüm ne kadar kötüyse ne kadar ek kapasitans"
# sorusuna KABA bir ilk yanıt verir — kritik raylarda gerçek bir PDN/ESR
# analizi (bu modülün kapsamı DIŞINDA) ile DOĞRULANMALIDIR.
_DUSUM_YUZDESI_KADEMELERI: Tuple[Tuple[float, Tuple[float, ...]], ...] = (
    (2.0, (100e-9,)),                 # hafif: standart 100nF yeterli sayılır
    (5.0, (100e-9, 1e-6)),            # orta: +1uF ara-frekans desteği
    (float("inf"), (100e-9, 10e-6)),  # ağır: +10uF bulk
)

# SINIR/TUTARSIZLIK NOTU (dürüstlük, kod incelemesinde bulundu): kod
# tabanında dekuplaj mesafesi için İKİ farklı sayı dolaşıyor —
# `kuvvet_yonelimli_yerlesim.py`'nin docstring'i "decoupling <=1.5mm"
# diyor (yerleşim motorunun kendi kısıt YORUMU, hiçbir yerde ZORUNLU
# parametre olarak GEÇMİYOR), ama `pcbnew_koprusu.py::dekuplaj_mesafe_
# kontrolu()`'nun GERÇEKTEN ÇALIŞAN varsayılan parametresi 3.0mm'dir. Bu
# fonksiyonun varsayılanı GERÇEKTEN UYGULANAN 3.0mm'YE eşitlendi (tek
# kaynak: fiilen ÇALIŞAN kontrol) — 1.5mm'lik daha sıkı hedef isteniyorsa
# `maks_mesafe_mm=1.5` AÇIKÇA verilmelidir, sessizce varsayılmaz.
DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM = 3.0


def decoupling_onerisi_uret(
    bulgu: Bulgu,
    maks_mesafe_mm: float = DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM,
) -> List[DekuplajOnerisi]:
    """`voltaj_dususu_dogrula()`'nın ÜRETTİĞİ `Bulgu`'yu alıp, tolerans
    dışına çıkan HER ray için kapasitör değeri + yerleşim mesafesi önerisi
    üretir — simülasyonu TEKRARLAMAZ, sadece onun SONUCUNU yorumlar.

    `bulgu.durum != FAIL` ise (PASS — hiçbir ray tolerans dışına çıkmadı,
    veya KAPSAM_YOK — simülasyon hiç koşmadı) BOŞ liste döner: PASS'ta
    öneri GEREKMEZ, KAPSAM_YOK'ta öneri ÜRETİLEMEZ (simülasyon verisi
    yok — sayı uydurma yasağı, bu modülün geri kalanıyla AYNI disiplin).

    `maks_mesafe_mm`, `pcbnew_koprusu.py::dekuplaj_mesafe_kontrolu()`'nun
    GERÇEKTEN UYGULANAN varsayılanıyla (3.0mm) TEK KAYNAK tutulur — bu
    fonksiyonun önerdiği yerleşim, o kontrolün DENETLEDİĞİ kritere UYUMLU
    olsun diye (bkz. yukarıdaki SINIR/TUTARSIZLIK NOTU).
    """
    if bulgu.durum != BulguDurumu.FAIL:
        return []

    oneriler: List[DekuplajOnerisi] = []
    for ihlal in bulgu.ihlaller:
        nominal_v = ihlal.get("nominal_v")
        dusum_mv = ihlal.get("dusum_mv")
        dugum = ihlal.get("dugum")
        if nominal_v is None or dusum_mv is None or dugum is None or nominal_v <= 0:
            continue  # bu ihlal beklenen şemada değil (ör. "düğüm yok" tipi) — öneri ÜRETİLEMEZ
        dusum_yuzdesi = (dusum_mv / 1000.0) / nominal_v * 100.0
        kapasitans_degerleri = next(
            degerler for esik, degerler in _DUSUM_YUZDESI_KADEMELERI if dusum_yuzdesi <= esik
        )
        deger_metni = ", ".join(
            f"{v * 1e9:.0f}nF" if v < 1e-6 else f"{v * 1e6:.0f}uF" for v in kapasitans_degerleri
        )
        oneriler.append(DekuplajOnerisi(
            dugum=dugum,
            onerilen_kapasitans_f=list(kapasitans_degerleri),
            maks_mesafe_mm=maks_mesafe_mm,
            gerekce=(
                f"{dugum}: ölçülen düşüm {dusum_mv:.1f}mV ({dusum_yuzdesi:.1f}% nominal) — "
                f"tolerans dışı (kural-of-thumb). Öneri: {deger_metni}, IC güç pininden "
                f"≤{maks_mesafe_mm}mm (bkz. pcbnew_koprusu.dekuplaj_mesafe_kontrolu ile TUTARLI)."
            ),
        ))
    return oneriler


# ------------------------------------------------------------------
# 5. RAPOR (MASTER_RULEBOOK Faz 3: TEST/simulasyon_raporu.md)
# ------------------------------------------------------------------

def simulasyon_raporu_uret(
    bulgular: Sequence[Bulgu],
    model_turu: ModelTuru,
    model_notu: str,
    ngspice_surum_metni: str,
) -> str:
    """`TEST/simulasyon_raporu.md` içeriğini üretir.

    MASTER_RULEBOOK Faz 3/EK checklist'in ZORUNLU kıldığı iki bilgi burada
    şablonla GARANTİ edilir: (1) model türü, (2) davranışsal ise neyi
    yansıtmadığı. `model_turu == DAVRANISSAL` iken `model_notu` boş
    bırakılamaz — `ValueError` fırlatır; "davranışsal ama neyi eksik
    yansıttığı yazılmamış" bir rapor kuralı ihlal eder.
    """
    if model_turu == ModelTuru.DAVRANISSAL and not model_notu.strip():
        raise ValueError(
            "DAVRANISSAL model kullanıldıysa `model_notu` ZORUNLUDUR — "
            "MASTER_RULEBOOK Faz 3: modelin neyi yansıtmadığı belirtilmeli."
        )

    satirlar = [
        "# Simülasyon Raporu (ngspice)",
        "",
        f"- **Model türü:** {model_turu.value}",
        f"- **Model notu / sınırları:** {model_notu or '(üretici modeli — davranışsal sınır notu gerekmiyor)'}",
        f"- **Çözücü:** {ngspice_surum_metni}",
        "",
        "## Kontroller",
        "",
        "| Kontrol | Durum | Taranan | İhlal |",
        "|---|---|---|---|",
    ]
    for b in bulgular:
        satirlar.append(f"| {b.kontrol} | {b.durum.value} | {b.taranan} | {len(b.ihlaller)} |")

    satirlar += ["", "## İhlal detayları", ""]
    ihlal_var = False
    for b in bulgular:
        for ihlal in b.ihlaller:
            ihlal_var = True
            satirlar.append(f"- `{b.kontrol}`: {ihlal}")
    if not ihlal_var:
        satirlar.append("- (ihlal yok)")

    if any(b.durum == BulguDurumu.KAPSAM_YOK for b in bulgular):
        satirlar += [
            "",
            "> **DİKKAT — KAPSAM_YOK:** En az bir kontrol GERÇEKTEN KOŞULMADI",
            "> (ngspice kurulu değil veya çıktı ayrıştırılamadı). Bu bir PASS",
            "> DEĞİLDİR; `KURULUM.md`'deki ngspice adımı tamamlanıp rapor",
            "> yeniden üretilmelidir.",
        ]
    return "\n".join(satirlar) + "\n"


def simulasyon_raporu_yaz(
    hedef_yol: str,
    bulgular: Sequence[Bulgu],
    model_turu: ModelTuru,
    model_notu: str = "",
    ngspice_surum_metni: str = "YOK",
) -> str:
    icerik = simulasyon_raporu_uret(bulgular, model_turu, model_notu, ngspice_surum_metni)
    yol = Path(hedef_yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# 6. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

ORNEK_NGSPICE_CIKTISI = """\
Circuit: * ldo test

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

No. of Data Rows : 3
Index   v-sweep         v(vout)         v(vin)
------------------------------------------------
0\t0.000000e+00\t3.300000e+00\t4.200000e+00
1\t5.000000e-01\t3.290000e+00\t4.100000e+00
2\t1.000000e+00\t3.100000e+00\t4.000000e+00
"""


def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: kabul sınırını ölçülen minimumun ÜSTÜNE çekersek
    doğrulama FAIL vermek ZORUNDA. Aksi halde `voltaj_dususu_dogrula`
    hiçbir şeyi gerçekten karşılaştırmıyor demektir."""
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bozuk = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, min_kabul_v=3.25)])
    return bozuk.durum == BulguDurumu.FAIL


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)

    if sonuc.satir_sayisi != 3:
        hatalar.append(f"ayrıştırma 3 satır beklerken {sonuc.satir_sayisi} buldu")
    if sonuc.min_deger("v(vout)") != 3.1:
        hatalar.append("min_deger v(vout) 3.1 vermedi")

    temiz = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, tolerans_yuzde=10.0)])
    if temiz.durum != BulguDurumu.PASS:
        hatalar.append(f"%10 toleransta PASS beklenirken {temiz.durum} geldi")

    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: voltaj karşılaştırması boş olabilir")

    yok = voltaj_dususu_dogrula(None, [RayHedefi("vout", 3.3)])
    if yok.durum != BulguDurumu.KAPSAM_YOK or yok.gecti_mi:
        hatalar.append("ngspice yokken KAPSAM_YOK dönmedi (sahte PASS riski)")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print(f"PASS: ngspice_koprusu.py öz testleri temiz (ngspice: {ngspice_surumu()}).")
