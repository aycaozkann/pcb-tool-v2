"""
kicad_koprusu.py
================
`pcb_stackup_planner.py`'nin ürettiği karar/kural çıktılarını (net class,
DRC kuralları) gerçek bir KiCad 10 projesine aktaran köprü modülü.

MİMARİ KARARI — kicad-cli KANONİK ENTEGRASYON YÖNTEMİDİR:
------------------------------------------------------------
Bu projede KiCad'e üç farklı yoldan bağlanma denendi/tanımlandı:

1) **kicad-cli (subprocess) — KANONİK/ÖNCELİKLİ YÖNTEM.**
   Resmi, dokümante edilmiş, stabil CLI. Bu dosyadaki `drc_calistir()` ve
   dosya-tabanlı net class yazımı bu yöntemi kullanır.

2) **mixelpixx/KiCAD-MCP-Server (`mcp__kicad__*` araçları)** — `SKILL.md` ve
   `SKILL (1).md` (schematic-design / pcb-layout) bu yöntemi kullanıyor.
   **Bu yöntem BİLEREK ikincil/yedek plana düşürüldü**, çünkü aynı `SKILL.md`
   dosyasının kendi Ek-A'sı bu MCP sunucusunun bilinen hatalarını listeliyor:
   `sync_schematic_to_board` bazı sembol tiplerinde pinleri yanlış nete
   yazabiliyor, `get_net_connections` iki neti birleştirip gösterebiliyor,
   `get_schematic_pin_locations` sahte koordinat döndürebiliyor. `SKILL.md`
   bile her kritik netin `kicad-cli sch export netlist` ile BAĞIMSIZ olarak
   çapraz doğrulanmasını şart koşuyor — yani MCP katmanının kendisi güvenilir
   tek kaynak değil, kicad-cli zaten "gerçek kanıt" rolünde. Bu yüzden: MCP
   araçları GUI-benzeri kolaylık (component ekleme, board açma) için
   kullanılabilir, ama her doğrulama/karar noktasında kicad-cli esastır.

3) **kipy / IPC API** — KiCad ekibinin kendi ifadesiyle "unstable", üçüncü
   öncelikte, ayrı bir bölümde tutuluyor (aşağıda bölüm 3).

Pratik sonuç: Bu köprüdeki `net_classleri_projeye_yaz()` dosya-tabanlı JSON
yazımı ve `drc_calistir()` kicad-cli çağrısı, MCP tabanlı `SKILL.md`/
`SKILL (1).md` akışlarının YERİNE de geçebilir — MCP araçları çalışmadığında
veya sonucundan şüphe duyulduğunda bu modüldeki fonksiyonlar tek doğrulama
kaynağı olarak kullanılmalıdır.

ÖNEMLİ — DÜRÜSTLÜK NOTU:
------------------------
Bu dosya bir İSKELETTİR ve gerçek bir KiCad kurulumu OLMADAN (bu ortamda
KiCad yok) yazıldı. Şunlar doğrulanmadan production'da güvenilmemeli:
  - `.kicad_pro` içindeki net_classes JSON anahtar yolu (şema sürümden
    sürüme değişebilir) — gerçek bir `.kicad_pro` dosyasına bakarak
    doğrulanmalı.
  - kipy Board API çağrıları (bölüm 3) hiç çalıştırılmadı.
Bu doğrulamayı Claude Code, SENİN makinende gerçek KiCad 10 ve gerçek proje
dosyalarıyla yapmalı — orada `kicad-cli` ve gerçek `.kicad_pro` dosyası var.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from arac_yollari import kicad_cli_yolunu_bul
from pcb_stackup_planner import DiferansiyelCift


# ------------------------------------------------------------------
# 1. NET CLASS ÜRETİMİ VE DOSYAYA YAZMA (dosya tabanlı — güvenilir yol)
# ------------------------------------------------------------------

@dataclass
class NetClassTanimi:
    isim: str
    track_width_mm: float
    dp_gap_mm: float
    net_isimleri: List[str]


def net_class_json_uret(
    cift: DiferansiyelCift, track_width_mm: float, dp_gap_mm: float, net_isimleri: List[str]
) -> Dict:
    """Bir differential pair için KiCad net class JSON parçası üretir.

    NOT: Anahtar isimleri (name, track_width, diff_pair_gap, nets) KiCad 10'un
    `.kicad_pro` şemasına göre DOĞRULANMALIDIR — burada genel/beklenen yapıya
    göre yazıldı, gerçek dosyada farklı olabilir.
    """
    return {
        "name": cift.isim.replace(" ", "_").replace("/", "_").replace("+", "P").replace("-", "N"),
        "track_width": track_width_mm,
        "diff_pair_gap": dp_gap_mm,
        "nets": net_isimleri,
    }


def net_classleri_projeye_yaz(kicad_pro_path: str, yeni_siniflar: List[Dict]) -> None:
    """`.kicad_pro` dosyasını (JSON) okuyup net class listesine ekler/günceller.

    Orijinal dosyayı düzenlemeden önce `.bak` uzantılı bir yedek alır —
    yanlış giden bir şema varsayımı geri alınabilsin diye.
    """
    proje_yolu = Path(kicad_pro_path)
    if not proje_yolu.exists():
        raise FileNotFoundError(f"{kicad_pro_path} bulunamadı.")

    yedek_yolu = proje_yolu.with_suffix(proje_yolu.suffix + ".bak")
    shutil.copy(proje_yolu, yedek_yolu)

    with open(proje_yolu, "r", encoding="utf-8") as f:
        veri = json.load(f)

    # NOT: Gerçek anahtar yolu (örn. veri["board"]["design_settings"]["net_classes"])
    # gerçek bir KiCad 10 .kicad_pro dosyasına bakılarak DOĞRULANMALI.
    net_classes = (
        veri.setdefault("board", {})
        .setdefault("design_settings", {})
        .setdefault("net_classes", [])
    )

    mevcut_isimler = {nc.get("name") for nc in net_classes}
    for yeni in yeni_siniflar:
        if yeni["name"] in mevcut_isimler:
            net_classes[:] = [
                yeni if nc.get("name") == yeni["name"] else nc for nc in net_classes
            ]
        else:
            net_classes.append(yeni)

    with open(proje_yolu, "w", encoding="utf-8") as f:
        json.dump(veri, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# 2. DRC ÇALIŞTIRMA (kicad-cli — stabil, dokümante edilmiş resmi araç)
# ------------------------------------------------------------------

def drc_calistir(
    board_path: str, rapor_path: str = "drc_raporu.json", kicad_cli: Optional[str] = None
) -> Dict:
    """kicad-cli ile headless DRC çalıştırır ve JSON raporu döndürür.

    kicad-cli DRC ihlali bulduğunda returncode=1 döndürebilir — bu bir
    çalıştırma hatası değil, "hata bulundu" anlamına gelir; bu yüzden
    0 ve 1 ikisi de normal kabul edilir.
    """
    komut = [kicad_cli_yolunu_bul(kicad_cli), "pcb", "drc", "--output", rapor_path, "--format", "json", board_path]
    sonuc = subprocess.run(komut, capture_output=True, text=True)

    if sonuc.returncode not in (0, 1):
        raise RuntimeError(f"kicad-cli çalıştırılamadı: {sonuc.stderr}")

    with open(rapor_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _drc_tum_ihlaller(rapor: Dict) -> List[Dict]:
    """DRC raporundaki HER iki listeyi de (`violations` + `unconnected_items`)
    tek bir akışta döner.

    DOĞRULANMIŞ BULGU (bu makinede gerçek `kicad-cli pcb drc --format json`
    ile kontrol edildi, ESP32C3_SmartBand.kicad_pcb): rapor şemasında
    ihlaller İKİ AYRI anahtar altında gelir — `violations` (clearance,
    dangling via, footprint mismatch vb.) VE ayrıca `unconnected_items`
    (eksik bağlantılar — GERÇEK board'da 6 tanesi `"severity": "error"`
    olarak çıktı). Önceki sürüm SADECE `violations`'a bakıyordu; bu, 6
    gerçek "error" seviyeli eksik bağlantıyı SESSİZCE PASS sayıyordu —
    bir board'un router'ın tamamlamadığı netlerle üretime geçebileceği
    anlamına geliyordu. Artık ikisi de taranır.
    """
    return list(rapor.get("violations", [])) + list(rapor.get("unconnected_items", []))


def drc_raporunu_ozetle(rapor: Dict) -> List[str]:
    """DRC JSON raporundan okunabilir bir hata/uyarı listesi çıkarır —
    `violations` VE `unconnected_items` ikisini de kapsar (bkz.
    `_drc_tum_ihlaller` docstring'i)."""
    return [
        f"[{ihlal.get('severity', '?')}] {ihlal.get('description', '')}"
        for ihlal in _drc_tum_ihlaller(rapor)
    ]


def drc_temiz_mi(rapor: Dict) -> bool:
    """Raporda (violations + unconnected_items) 'error' seviyesinde hiç
    ihlal yoksa True döner (uyarılar hariç)."""
    return not any(v.get("severity") == "error" for v in _drc_tum_ihlaller(rapor))


def erc_calistir(
    schematic_path: str, rapor_path: str = "erc_raporu.json", kicad_cli: Optional[str] = None
) -> Dict:
    """kicad-cli ile headless ERC çalıştırır ve JSON raporu döndürür.

    `drc_calistir` ile birebir aynı desen: returncode 0 (temiz) veya 1
    (ihlal bulundu) normal kabul edilir, başka bir kod gerçek bir çalıştırma
    hatasıdır. SKILL.md Faz 3.2'nin ("ERC çalıştır, PWR_FLAG'a sarılmadan
    önce kök nedeni bul") kod karşılığı budur — MCP üzerinden ERC çağrılıp
    çağrılmadığından bağımsız olarak, kabul kriteri burada.

    ŞEMA DOĞRULANDI (bu makinede gerçek `kicad-cli sch erc --format json`
    ile ESP32C3_SmartBand.kicad_sch üzerinde koşturuldu — önceki sürümdeki
    "doğrulanmadı" notu artık geçersiz): ERC raporunun şeması DRC'den
    FARKLIDIR — ihlaller üst seviyede `violations` DEĞİL,
    `sheets[].violations` altında, HER SAYFA için ayrı bir listede gelir:

        {"sheets": [{"path": "/", "violations": [...]}], ...}

    Bu proje HİYERARŞİK şematik desteklediği (`add_hierarchical_sheet`
    vb.) için birden fazla `sheets[]` girdisi olabilir — hepsi
    TOPLANMALIDIR, sadece ilk sayfaya bakmak diğer sayfalardaki hataları
    kaçırır. `erc_raporunu_ozetle()`/`erc_temiz_mi()` artık bu gerçek
    şemayı okur; eski `drc_raporunu_ozetle()`'ı çağıran sürüm (üst seviye
    `violations` arardı) GERÇEK bir ERC raporunda HER ZAMAN boş liste
    bulup sessizce PASS derdi — 7 gerçek uyarı içeren bu projenin kendi
    şematiğiyle test edilince bu hemen ortaya çıktı.
    """
    komut = [kicad_cli_yolunu_bul(kicad_cli), "sch", "erc", "--output", rapor_path, "--format", "json", schematic_path]
    sonuc = subprocess.run(komut, capture_output=True, text=True)

    if sonuc.returncode not in (0, 1):
        raise RuntimeError(f"kicad-cli sch erc çalıştırılamadı: {sonuc.stderr}")

    with open(rapor_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _erc_tum_ihlaller(rapor: Dict) -> List[Dict]:
    """ERC raporundaki TÜM sayfalardaki ihlalleri tek bir akışta toplar
    (bkz. `erc_calistir` docstring'indeki gerçek şema notu).

    `"sheets"` anahtarı hiç YOKSA (beklenmeyen/eski bir şema) SESSİZCE boş
    dönmez — bu durumda şema varsayımı GEÇERSİZ olabilir; çağıran taraf
    `erc_temiz_mi()`'nin `True` dönmesine güvenmeden önce
    `sema_taninmadi_mi()` ile bunu ayrıca kontrol etmelidir (fail-closed
    disiplini: bilinmeyen şema asla sessizce PASS sayılmaz).
    """
    ihlaller: List[Dict] = []
    for sayfa in rapor.get("sheets", []):
        ihlaller.extend(sayfa.get("violations", []))
    return ihlaller


def sema_taninmadi_mi(rapor: Dict) -> bool:
    """`rapor` ne DRC'nin (`violations` üst seviyede) ne de ERC'nin
    (`sheets[].violations`) bilinen şemasına uyuyorsa `True` döner.

    Fail-closed kapısı: `erc_temiz_mi()`/`drc_temiz_mi()` `True` dönse
    bile, eğer şema hiç tanınmadıysa bu GERÇEK bir "temiz" değil, "hiçbir
    şey okunamadı" anlamına gelebilir. `kicad_koprusu.py`'yi çağıran her
    release-gate akışı bu fonksiyonu da kontrol etmeli.
    """
    return "violations" not in rapor and "sheets" not in rapor


def erc_raporunu_ozetle(rapor: Dict) -> List[str]:
    """ERC JSON raporundan (gerçek `sheets[].violations` şemasından)
    okunabilir bir hata/uyarı listesi çıkarır — bkz. `erc_calistir`
    docstring'indeki doğrulanmış şema notu."""
    return [
        f"[{ihlal.get('severity', '?')}] {ihlal.get('description', '')}"
        for ihlal in _erc_tum_ihlaller(rapor)
    ]


def erc_temiz_mi(rapor: Dict) -> bool:
    """Raporda (TÜM sayfalarda, `sheets[].violations`) 'error'/'fatal'
    seviyesinde ihlal yoksa True döner — bkz. `erc_calistir` docstring'i
    (üst seviye `violations` DEĞİL, gerçek ERC şeması `sheets[]` altında)."""
    return not any(
        v.get("severity") in ("error", "fatal") for v in _erc_tum_ihlaller(rapor)
    )


def gercek_board_dogrulama_kapisi(
    board_path: str,
    kapsam_yok_izinli_kontroller: Sequence[str] = (),
) -> Tuple[bool, Dict]:
    """`drc_calistir()`/`erc_calistir()`'in YANINA — Faz 4/adım 5 (Doğrulama
    kapısı) için `pcbnew_koprusu.py`'deki gerçek-board kontrollerini
    (maske barajı, via-in-pad, annular ring, kenar keepout) çalıştırır ve
    tek bir PASS/FAIL kararına indirger.

    Önceki durum: standart DRC/ERC "temiz" dese bile bu kontroller (özellikle
    maske barajı) YAKALANMIYORDU — DRC bakır-bakır clearance'a bakar, maske
    açıklığına bakmaz ([[SKILL-dfm]] ile aynı ayrım, `pcb_highspeed_escape.py`
    docstring'inde de tekrarlanıyor). Bu fonksiyon o boşluğu adım 5'e bağlar.

    KAPSAM_YOK DAVRANIŞI (düzeltildi — önceki sürüm FAIL SAYMIYORDU):
    ---------------------------------------------------------------------
    Önceki sürümde bir kontrolün `KAPSAM_YOK` dönmesi (ör. `via-in-pad`
    kontrolü board'da HİÇ via bulamadı) `temiz_mi`'yi etkilemiyordu — bu,
    "kontrol edildi, temiz çıktı" ile "kontrol hiç GERÇEK anlamda
    çalışmadı" arasındaki farkı tam da `bulgu_sozlesmesi.py`'nin önlemek
    istediği şekilde bulanıklaştırıyordu: bir board'da hiç GND via'sı
    yoksa (yanlış yerleşim/DRC ayarı belirtisi olabilir) kontrol sessizce
    `KAPSAM_YOK` döner ve bu ÜRETİME GEÇİŞ KARARINDA fark edilmeden
    geçerdi. **Bu artık fail-closed'dır:** `KAPSAM_YOK` dönen HERHANGİ bir
    kontrol, `kapsam_yok_izinli_kontroller` listesinde AÇIKÇA
    belirtilmediği sürece `temiz_mi=False` yapar. Bir board tipi için
    (ör. via'sız, tamamen yüzey montaj bir kart) belirli bir kontrolün
    kapsam dışı kalması NORMALSE, bu listeye o kontrolün `kontrol` adı
    açıkça eklenmelidir — sessiz varsayılan YOKTUR, her istisna
    belgelenmiş bir karardır.

    Dönen: (`temiz_mi`, `bulgu_sozlesmesi.ozet_rapor()` çıktısı — özet
    sözlüğüne ayrıca `"kapsam_yok_engelledi"` anahtarıyla, hangi
    kontrollerin KAPSAM_YOK yüzünden kapıyı kapattığı eklenir).

    AĞ/ARAÇ UYARISI: `pcbnew_koprusu.py` gibi bu fonksiyon da gerçek
    `pcbnew` gerektirir — bu ortamda çalıştırılıp doğrulanmadı, senin
    makinende gerçek bir `.kicad_pcb` ile test edilmeli.
    """
    from bulgu_sozlesmesi import BulguDurumu, ozet_rapor
    from pcbnew_koprusu import tum_gercek_board_kontrollerini_calistir

    bulgular = tum_gercek_board_kontrollerini_calistir(board_path)
    izinli = set(kapsam_yok_izinli_kontroller)
    kapsam_yok_engelledi = [
        b.kontrol for b in bulgular
        if b.durum == BulguDurumu.KAPSAM_YOK and b.kontrol not in izinli
    ]
    temiz_mi = (
        not any(b.durum == BulguDurumu.FAIL for b in bulgular)
        and not kapsam_yok_engelledi
    )
    ozet = ozet_rapor(bulgular)
    ozet["kapsam_yok_engelledi"] = kapsam_yok_engelledi
    return temiz_mi, ozet


def tekrarlanan_ihlal_tespit_et(
    rapor_gecmisi: List[Dict], esik: int = 3
) -> List[str]:
    """Art arda gelen DRC raporlarında AYNI ihlalin `esik` kez tekrarlanıp
    tekrarlanmadığını tespit eder.

    `rapor_gecmisi`: en eski rapordan en yeniye sıralı `drc_calistir()`
    çıktıları listesi (son `esik` eleman kontrol edilir).

    Döndürür: eşik sayısı kadar art arda tekrar eden ihlal açıklamalarının
    listesi (boşsa tekrar yok demektir).

    `pcb-layout` skill'inin "Sonsuz Döngü Kaçış Kuralı"nın kod karşılığıdır:
    bu fonksiyon True/dolu bir liste döndürürse, o net/yol üzerinde küçük
    düzeltmelerle devam ETMEK YERİNE, yolu tamamen silip farklı bir
    geometriden yeniden çizme stratejisine geçilmelidir — aynı küçük
    varyasyonla tekrar denemek yasaktır.
    """
    if len(rapor_gecmisi) < esik:
        return []

    son_n = rapor_gecmisi[-esik:]
    ilk_ozet = set(drc_raporunu_ozetle(son_n[0]))
    tekrar_eden: List[str] = []
    for ihlal in ilk_ozet:
        if all(ihlal in drc_raporunu_ozetle(r) for r in son_n[1:]):
            tekrar_eden.append(ihlal)
    return tekrar_eden


# ------------------------------------------------------------------
# 2b. CUSTOM DRC KURALLARI (.kicad_dru) VE GÖRSEL DENETİM (kicad-cli)
# ------------------------------------------------------------------
#
# `pcb-layout` skill'inin Aşama 3.6'sının kod karşılığı: routing (Faz 4)
# başlamadan ÖNCE, net class bazlı fiziksel bir "koridor" KiCad'in kendi
# DRC motoruna gömülür — AI (veya FreeRouting) yanlış bir yol çizse bile
# standart DRC bunu anında yakalar. Değerler kafadan uydurulmaz;
# `pcb_stackup_planner.py::iz_genisligi_hesapla_mm()` gibi hesaplanmış
# değerler `min_genislik_mm` olarak buraya verilmelidir.
#
# DOĞRULANMADI: `.kicad_dru` dosyasının KiCad 10'daki tam yolu/adı
# (`<proje>.kicad_dru`, proje köküyle aynı isimde) ve `kicad-cli pcb drc`'nin
# bu dosyayı otomatik okuyup okumadığı SENİN kurulumunda teyit edilmeli —
# KiCad sürümleri arasında Custom Rules dilinin sözdizimi küçük farklılıklar
# gösterebilir.

@dataclass
class OzelDrcKurali:
    isim: str
    net_class_kosulu: str  # örn. "HIGH_CURRENT"
    min_iz_genisligi_mm: float


def custom_dru_yaz(proje_kicad_dru_path: str, kurallar: List[OzelDrcKurali]) -> None:
    """Net class bazlı minimum iz genişliği kurallarını `.kicad_dru` dosyasına yazar.

    Örnek üretilen kural (tek bir `OzelDrcKurali` için):

        (rule "Yüksek Akım Yolları"
          (condition "A.NetClass == 'HIGH_CURRENT'")
          (constraint track_width (min 1.5mm)))

    Mevcut dosyanın üzerine YAZAR (append değil) — proje başına tek bir
    `.kicad_dru` dosyası olduğu varsayılır. Farklı çalıştırmalar arasında
    kuralları korumak istersen, önce mevcut dosyayı okuyup birleştir.
    """
    blok_listesi = []
    for k in kurallar:
        blok_listesi.append(
            f'(rule "{k.isim}"\n'
            f'  (condition "A.NetClass == \'{k.net_class_kosulu}\'")\n'
            f'  (constraint track_width (min {k.min_iz_genisligi_mm}mm)))'
        )
    icerik = "\n\n".join(blok_listesi) + "\n"
    Path(proje_kicad_dru_path).write_text(icerik, encoding="utf-8")


def pcb_gorseli_disa_aktar(
    board_path: str,
    svg_cikti_path: str = "pcb_gorunumu.svg",
    katmanlar: str = "F.Cu,B.Cu,F.SilkS,Edge.Cuts",
    kicad_cli: Optional[str] = None,
) -> str:
    """`kicad-cli pcb export svg` ile kartın görüntüsünü dışa aktarır.

    Bu, `pcb-layout` skill'indeki "Görsel Denetim (Vision Review)" adımının
    girdisidir — üretilen SVG, Claude'un vision yeteneğiyle incelenmek üzere
    kullanılır (bu fonksiyon SADECE görseli üretir, incelemeyi YAPMAZ — o,
    görseli okuyabilen modelin/aracın işidir).

    DOĞRULANMADI: `--layers` bayrağının tam formatı ve varsayılan
    çözünürlük/görünüm açısı KiCad 10'da teyit edilmeli.
    """
    komut = [
        kicad_cli_yolunu_bul(kicad_cli), "pcb", "export", "svg",
        "--output", svg_cikti_path,
        "--layers", katmanlar,
        board_path,
    ]
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise RuntimeError(f"PCB SVG export başarısız: {sonuc.stderr}")
    return svg_cikti_path


# ------------------------------------------------------------------
# 2b. REFERANS DÜZLEMİ SÜREKLİLİĞİ (return-path) KONTROLÜ
# ------------------------------------------------------------------
#
# Yüksek hızlı bir hat, referans (GND/PWR) düzleminde bir split/void üzerinden
# geçerse dönüş akımı zorunlu bir dolambaç yapar -> empedans sıçraması + EMI.
# Standart clearance/width DRC'si bunu YAKALAMAZ (o bakır-bakır mesafesine
# bakar, düzlem sürekliliğine değil) — bu yüzden ayrı bir kontrol gerekir.
#
# DOĞRULANMADI: `.kicad_pcb` zone/track S-Expr şeması KiCad sürümleri arasında
# küçük farklar gösterebilir (özellikle `(zone ... (filled_polygon ...))` vs
# ham `(polygon ...)` anahat). Bu fonksiyon ham anahat (outline) poligonunu
# kullanır — dolgu sırasında oluşan thermal-relief/pad çıkıntılarını DEĞİL,
# kaba düzlem şeklini kontrol eder. Kritik bir tasarımda gerçek dosya üzerinde
# senin makinende teyit edilmeli.

@dataclass
class DuzlemPoligonu:
    layer: str
    net_adi: str
    nokta_listesi: List[Tuple[float, float]]  # (x, y) mm, kapalı poligon


@dataclass
class IzSegmenti:
    net_adi: str
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float


def _nokta_poligon_icinde_mi(x: float, y: float, poligon: List[Tuple[float, float]]) -> bool:
    """Ray-casting (even-odd) point-in-polygon testi. Harici bağımlılık yok."""
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


def check_reference_plane_continuity(
    yuksek_hiz_izleri: List[IzSegmenti],
    duzlemler: List[DuzlemPoligonu],
    referans_net: str = "GND",
) -> List[str]:
    """
    Her yüksek hızlı iz segmentinin İKİ UCUNUN da (ve orta noktasının),
    aynı katmandaki `referans_net` düzlem poligonunun İÇİNDE kalıp
    kalmadığını kontrol eder. Dışında kalan bir nokta = o segmentin altında
    referans düzlemi YOK (split/void üzerinden geçiyor demektir).

    Kabul kriteri: dönen liste BOŞ olmalı (`length_matching` temiz olsa bile
    bu ihlal SI'yı bozar — [[SKILL-highspeed-length-match]] adım 7).
    """
    bulgular: List[str] = []
    for iz in yuksek_hiz_izleri:
        ilgili_duzlem = next(
            (d for d in duzlemler if d.layer == iz.layer and d.net_adi == referans_net),
            None,
        )
        if ilgili_duzlem is None:
            bulgular.append(
                f"KRİTİK [{iz.net_adi}]: {iz.layer} katmanında '{referans_net}' "
                "referans düzlemi tanımı hiç bulunamadı."
            )
            continue

        orta_x, orta_y = (iz.x1 + iz.x2) / 2, (iz.y1 + iz.y2) / 2
        noktalar = [(iz.x1, iz.y1), (orta_x, orta_y), (iz.x2, iz.y2)]
        for nx, ny in noktalar:
            if not _nokta_poligon_icinde_mi(nx, ny, ilgili_duzlem.nokta_listesi):
                bulgular.append(
                    f"KRİTİK [{iz.net_adi}] @ {iz.layer}: ({nx:.2f}, {ny:.2f}) "
                    f"noktası '{referans_net}' düzleminin DIŞINDA — split/void "
                    "üzerinden geçiyor. Katman geçişinde GND->GND stitching via "
                    "veya GND->PWR bitişik 100nF kapasitör ekle."
                )
                break  # bu iz için bir kez raporla, aynı ize tekrar ekleme
    return bulgular


# ------------------------------------------------------------------
# 2c. DFT / TEST NOKTALARI + BRING-UP CHECKLIST
# ------------------------------------------------------------------
#
# [[SKILL-dft-testpoints]] karşılığı: güç rayı + debug (SWD/UART) + kritik
# sinyallere test noktası ekleme kararını üretir + bring-up checklist yazar.
# NOT: bu fonksiyonlar test noktasının ŞEMATİĞE fiziksel S-Expr enjeksiyonunu
# YAPMAZ (o iş MCP `mcp__kicad__*` araçlarının veya harici bir wire-injection
# script'inin işi) — burada üretilen `testpoint_map.json` o adımın GİRDİSİDİR.

class TpSinifi(Enum):
    GUC = "POWER"
    DEBUG = "DEBUG"
    SAAT = "CLOCK"


@dataclass
class TpTanimi:
    net_adi: str
    sinif: TpSinifi
    beklenen_voltaj_v: Optional[float] = None
    zorunlu: bool = True


def insert_test_points(
    rail_tree: Dict[str, Dict],
    debug_netleri: Optional[List[str]] = None,
) -> List[TpTanimi]:
    """
    `rail_tree.json` (bkz. `pcb_stackup_planner.py` çıktısı) + debug net
    listesinden zorunlu TP kapsamını türetir.

    Zorunlu kapsam (kapsam hedefi güç+debug %100):
      - Her güç rayı (regülatör ÇIKIŞI, girişi değil).
      - SWD (SWDIO/SWCLK/nRST), UART (TX/RX), boot-strap, PMIC enable/PG.

    `rail_tree` formatı: {"3V3": {"vout": 3.3, ...}, "1V2_CORE": {"vout": 1.2, ...}}
    """
    tps: List[TpTanimi] = []
    for rail_adi, rail_bilgi in rail_tree.items():
        tps.append(
            TpTanimi(
                net_adi=rail_adi,
                sinif=TpSinifi.GUC,
                beklenen_voltaj_v=rail_bilgi.get("vout"),
                zorunlu=True,
            )
        )

    zorunlu_debug = debug_netleri or [
        "SWDIO", "SWCLK", "nRST", "UART_TX", "UART_RX",
    ]
    for net in zorunlu_debug:
        tps.append(TpTanimi(net_adi=net, sinif=TpSinifi.DEBUG))

    return tps


def tp_kapsam_kontrolu(
    tps: List[TpTanimi],
    beklenen_guc_rayi_sayisi: int,
    beklenen_debug_net_listesi: List[str],
) -> List[str]:
    """Kapsam hedefi güç+debug %100 — eksik kalanı raporla."""
    bulgular: List[str] = []
    guc_tp_sayisi = sum(1 for t in tps if t.sinif == TpSinifi.GUC)
    if guc_tp_sayisi < beklenen_guc_rayi_sayisi:
        bulgular.append(
            f"EKSİK: {beklenen_guc_rayi_sayisi} güç rayı bekleniyordu, "
            f"{guc_tp_sayisi} TP bulundu."
        )
    mevcut_debug_netleri = {t.net_adi for t in tps if t.sinif == TpSinifi.DEBUG}
    eksik = set(beklenen_debug_net_listesi) - mevcut_debug_netleri
    if eksik:
        bulgular.append(f"EKSİK debug TP: {sorted(eksik)}")
    return bulgular


def generate_bringup_checklist(
    tps: List[TpTanimi],
    rail_enable_sirasi: List[str],
    cikti_path: str = "bringup_checklist.md",
    tolerans_yuzde: float = 5.0,
) -> str:
    """
    Sıralı beklenen voltaj + rail enable sırasını `bringup_checklist.md`
    olarak yazar. Rail sıralama hatası core'a hasar verebileceği için sıra
    burada ZORLANIR (adımlar numaralı ve rail_enable_sirasi'na göre dizilir).

    DİJİTAL BRING-UP (Obsidian'da laboratuvarda dolduruluyor):
    -------------------------------------------------------------
    Her güç rayı satırı artık bir CHECKBOX ve bir Markdown TABLO satırı
    içerir — osiloskop/multimetre ile ölçülen gerçek değer, dosya doğrudan
    Obsidian'da (tablette/laptop'ta laboratuvarda) AÇILIP tablonun
    "Ölçülen" hücresine ELLE yazılır, sonuç PASS/FAIL/NEEDS_HUMAN olarak
    işaretlenir ve checkbox tıklanır. Bu dosya böylece kartın canlı test
    kaydına dönüşür ve `TEST/` altında revizyonla birlikte ARŞİVLENİR —
    kağıt üstünde tutulan bir test raporunun dijital karşılığıdır.

    `tolerans_yuzde`, tablodaki "Kabul Aralığı" sütununu hesaplamak için
    kullanılır (`bulgu_sozlesmesi.py` ile aynı ruh: hedef sayı kafadan
    değil, açık bir formülden gelir) — gerçek kabul kriteri Faz 2'nin
    worst-case tolerans hesabıysa, buraya O DEĞER geçirilmelidir; bu
    parametrenin varsayılanı (5%) sadece TEK kademeli basit raylar için
    bir başlangıç noktasıdır.
    """
    satirlar = ["# Bring-up Checklist\n"]
    satirlar.append(
        "## 1. Güç Sırası (rail_enable_sirasi'na göre — SIRAYI DEĞİŞTİRME)\n"
    )
    satirlar.append(
        "| # | Ray | Beklenen | Kabul Aralığı | Ölçülen | Sonuç | Tamam |\n"
        "|---|---|---|---|---|---|---|"
    )
    guc_map = {t.net_adi: t for t in tps if t.sinif == TpSinifi.GUC}
    for i, rail in enumerate(rail_enable_sirasi, start=1):
        tp = guc_map.get(rail)
        if tp and tp.beklenen_voltaj_v:
            beklenen = f"{tp.beklenen_voltaj_v} V"
            alt = round(tp.beklenen_voltaj_v * (1 - tolerans_yuzde / 100), 3)
            ust = round(tp.beklenen_voltaj_v * (1 + tolerans_yuzde / 100), 3)
            aralik = f"{alt}–{ust} V (±{tolerans_yuzde}%)"
        else:
            beklenen, aralik = "TBD", "TBD"
        satirlar.append(
            f"| {i} | `{rail}` | {beklenen} | {aralik} | _(lab'de doldur)_ "
            f"| _(PASS/FAIL/NEEDS_HUMAN)_ | [ ] |"
        )

    satirlar.append("\n## 2. Debug Erişilebilirliği\n")
    for t in tps:
        if t.sinif == TpSinifi.DEBUG:
            satirlar.append(f"- [ ] `{t.net_adi}` TP'si probe açısıyla erişilebilir mi?")

    satirlar.append(
        "\n## 3. Not\n- Yüksek hızlı hatta (MIPI/USB) TP stub'ı KULLANILMADI "
        "(empedans süreksizliği riski) — mikro-TP/prob-pad kontrolü ayrıca yapılmalı.\n"
    )

    satirlar.append(
        "\n## 4. Sonuç Arşivi\n"
        "- Bu dosya, tüm satırlar doldurulup imzalandıktan sonra "
        "`[[../DOCS/Templates/Dogrulama_Kaydi]]` şablonuyla bir doğrulama "
        "kaydına dönüştürülüp `DOCS/07_Dogrulama/`'ya bağlanmalıdır — "
        "PASS, gerçek ölçüm olmadan burada da yazılmaz.\n"
        "- Ölçüm tarihi: _(YYYY-MM-DD)_ · Ölçen: _(isim)_ · Cihaz: _(ör. Rigol DS1054Z)_\n"
    )

    icerik = "\n".join(satirlar) + "\n"
    Path(cikti_path).write_text(icerik, encoding="utf-8")
    return cikti_path


# ------------------------------------------------------------------
# 3. (OPSİYONEL / DOĞRULANMAMIŞ) CANLI KiCad OTURUMU — kipy IPC API
# ------------------------------------------------------------------
#
# UYARI: KiCad ekibinin kendi dokümantasyonu bu API için şunu söylüyor:
# "This is an unstable API and is not intended for use other than by API
#  developers." Bu fonksiyonlar bu ortamda HİÇ ÇALIŞTIRILMADI — gerçek bir
# KiCad 10 oturumu açıkken (Preferences > Plugins > Enable API işaretli)
# senin makinende test edilmesi gerekir.

def canli_baglanti_kur(headless: bool = False):
    """Çalışan bir KiCad oturumuna (veya headless kicad-cli sunucusuna) bağlanır."""
    try:
        from kipy import KiCad
    except ImportError as e:
        raise ImportError(
            "kicad-python paketi kurulu değil. Kurmak için: pip install kicad-python"
        ) from e

    kicad = KiCad(headless=headless)
    kicad.ping()
    return kicad


def aktif_board_ozeti_al(kicad) -> Dict:
    """Bağlı KiCad oturumundaki açık board hakkında temel bilgi döndürür."""
    board = kicad.get_board()
    return {"board": board}


if __name__ == "__main__":
    # --- Sadece dosya tabanlı (güvenilir) kısımların örnek gösterimi ---
    from pcb_stackup_planner import DiferansiyelCift, AraBirimTuru

    usb_cift = DiferansiyelCift(
        isim="USB_D+/D-", arayuz=AraBirimTuru.USB3_x,
        uzunluk_pozitif_mm=42.0, uzunluk_negatif_mm=41.9, veri_hizi_Gbps=5.0,
    )
    net_class = net_class_json_uret(
        usb_cift, track_width_mm=0.2, dp_gap_mm=0.127,
        net_isimleri=["USB_D+", "USB_D-"],
    )
    print("Üretilen net class JSON parçası:")
    print(json.dumps(net_class, indent=2, ensure_ascii=False))
    print(
        "\nBu parçayı gerçek bir .kicad_pro dosyasına yazmak için "
        "net_classleri_projeye_yaz(kicad_pro_path, [net_class]) çağrılır."
    )
