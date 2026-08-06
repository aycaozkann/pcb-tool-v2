#!/usr/bin/env python3
"""
openems_3d_extractor.py
========================
KiCad board'undan MIPI diferansiyel çift geometrisini (iz + via + genişlik +
katman Z konumu) çıkarıp openEMS/CSXCAD'e aktarır. `openems_koprusu.py`'nin
`geometri_cikar()`'ından FARKLI/tamamlayıcı bir yol: `esleş_diferansiyel_ciftler()`
ile net isimlerini OTOMATİK sonek-eşleştirir (`openems_koprusu.geometri_cikar()`
çift adlarını ÇAĞIRANDAN alır — ikisi aynı işi FARKLI girdilerle yapar,
bilerek TEK bir fonksiyona zorlanmadı; `fdtd_kur_ve_calistir()` artık bu
dosyadaki `csxcad_kutu_olustur()`'u ÇAĞIRIYOR — bkz. `openems_koprusu.py`).

DÜZELTİLEN 4 SORUN (orijinal taslağa göre):
--------------------------------------------------------------------------
1. **Bilinen tuzak tekrarı**: orijinal taslak `track.Type() ==
   pcbnew.PCB_TRACE_T` kullanıyordu. `pcbnew_koprusu.py`'de bu proje
   DAHA ÖNCE tam olarak bu tuzağa düşüp (`PCB_TRACE_T` arc segmentlerini
   kaçırıyor) `t.GetClass() == "PCB_TRACK"` string karşılaştırmasına
   geçmişti — bu modül AYNI, zaten doğrulanmış deseni kullanır (PCB_ARC
   ayrıca ele alınmadı — bkz. SINIR notu altta).
2. **Genişlik yok sayılıyordu**: `AddBox(start, end)` sonsuz-ince çizgi
   üretiyordu. `csxcad_kutu_olustur()` genişliği, izin yönüne DİK ofset ile
   gerçek bir dikdörtgen kesit (4 köşeli polygon) olarak hesaplar.
3. **Z konumu sabitti**: `katman_z_konumu_getir()` artık `pcb_stackup_
   planner.py::stackup_planla()`'nın GERÇEK dönüş tipine (`Dict[str, str]`,
   `"Katman_N"` anahtarları FİZİKSEL SIRAYLA) bağlanır — TEK KAYNAK,
   ikinci bir yerde tekrar tanımlanmaz.
4. **Alt-string net eşleştirme fragildi**: `"D0" in ad` yerine, sonek
   tabanlı (`_P`/`_N`) eşleştirme + D+/D- çiftleştirme kullanılır
   (`esleş_diferansiyel_ciftler`).

BULGU SÖZLEŞMESİ DÜZELTMESİ (bu görevde ayrıca istendi): `izleri_ve_
vialari_cikar()` eskiden `Bulgu`'nun İÇİNE veri (geometri listesi)
sızdırıyordu (dönüş tipi `Bulgu` diye ANNOTE edilmişken fiilen bir tuple
döndürüyordu — annotation YALAN söylüyordu). Şimdi:
  - `_geometri_topla()` SADECE veri döner (Bulgu YOK, PASS/FAIL kavramı YOK).
  - `izleri_ve_vialari_cikar()` `Tuple[Bulgu, List[Dict]]` döner — Bulgu
    SADECE tarama durumunu (PASS/KAPSAM_YOK) taşır, geometri AYRI kanaldan
    (ikinci eleman) gider. `bulgu_sozlesmesi.py`'nin "Bulgu veri taşıyıcısı
    DEĞİLDİR" disiplini böylece korunur.

DOĞRULAMA DURUMU (GERÇEK koşumla güncellenmiştir — tahminle DEĞİL):
--------------------------------------------------------------------------
  - **esleş_diferansiyel_ciftler() / katman_z_konumu_getir() / _geometri_
    topla() / izleri_ve_vialari_cikar(): pcbnew mock'uyla GERÇEKTEN test
    edildi** (`test_openems_3d_extractor.py`) — sahte `board.GetNetsByName()`/
    `GetTracks()` ile PASS/KAPSAM_YOK/eşleştirme mantığı DOĞRULANDI.
    `katman_z_konumu_getir()` ayrıca `pcb_stackup_planner.stackup_planla()`
    ile üretilmiş GERÇEK bir stackup sözlüğüne karşı test edildi.
    **REGRESYON (bu testler sırasında GERÇEKTEN bulundu/düzeltildi):**
    `izleri_ve_vialari_cikar()` ilk yazımda modül-SEVİYESİ `try/except
    ImportError: pcbnew=None` sentinel'i kullanıyordu — bu, testin
    `sys.modules["pcbnew"]`'e SONRADAN yerleştirdiği taklit modülü hiç
    GÖRMÜYORDU (modül zaten `pcbnew=None` ile yüklenmişti), bütün
    pcbnew-bağımlı testler yanlışlıkla KAPSAM_YOK dönüyordu. Fonksiyon
    içi (yerel) `import pcbnew`'e geçilerek düzeltildi — `pcbnew_
    koprusu.py::_pcbnew_veya_kapsam_yok()` ile AYNI ders/desen.
  - **csxcad_kutu_olustur(): GEOMETRİ MATEMATİĞİ (dik vektör/ofset/köşe
    hesabı) saf Python testiyle GERÇEKTEN doğrulandı** (CSXCAD GEREKMEDEN —
    `points` çıktısı elle hesaplanmış beklenen köşelerle karşılaştırıldı).
    `AddPolygon` ÇAĞRISININ KENDİSİ (CSXCAD nesnesi üzerinde) bu makinede
    ÇALIŞTIRILAMADI — CSXCAD kurulu değil. `openems_koprusu.py::
    fdtd_kur_ve_calistir()` artık bu fonksiyonu ÇAĞIRIYOR ama o zincirin
    tamamı openEMS kurulu bir makinede DOĞRULANMALI (bkz. o dosyanın
    DOĞRULAMA DURUMU notu).

SINIR (bilerek, madde 1'in devamı): `PCB_ARC` (yaylı iz segmentleri) bu
modülde `PCB_TRACK` ile AYNI şekilde ele ALINMAZ — `_geometri_topla()`
`t.GetClass() == "PCB_TRACK"` filtresini kullanır, `pcbnew_koprusu.py::
net_iz_ve_via_listesi_topla()`'nın AKSİNE (o fonksiyon PCB_ARC'ı da dahil
eder). Diferansiyel çiftlerin ESCAPE/kritik bölgelerinde genelde düz
segmentler kullanılır (yay nadir), bu yüzden bilinçli olarak basit
tutuldu; yay içeren bir geometri için `pcbnew_koprusu.net_iz_ve_via_
listesi_topla()` tercih edilmeli (`openems_koprusu.geometri_cikar()`'ın
kullandığı fonksiyon budur).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret


def _mm(deger_nm: float) -> float:
    """pcbnew_koprusu.py::_mm ile AYNI dönüşüm — nm -> mm."""
    return deger_nm / 1_000_000.0


@dataclass
class DiferansiyelCiftNeti:
    pozitif_net_adi: str
    negatif_net_adi: str
    katman_adi: str
    z_ust_mm: float
    z_alt_mm: float


def esleş_diferansiyel_ciftler(
    board, sonek_pozitif: str = "_P", sonek_negatif: str = "_N"
) -> List[Tuple[str, str]]:
    """Net isimlerini SONEKE göre eşleştirir (alt-string arama DEĞİL).

    Örn. "MIPI_D0_P" / "MIPI_D0_N" çifti eşleşir; "LED0", "GPIO_D0_EN"
    gibi alakasız netler sonek uymadığı için ELENIR. Deterministik sırayla
    (sıralanmış net adı listesi) gezinir — test edilebilirlik için."""
    tum_net_adlari = sorted(n for n in board.GetNetsByName().keys() if n)
    net_seti = set(tum_net_adlari)
    ciftler: List[Tuple[str, str]] = []
    for ad in tum_net_adlari:
        if not ad.endswith(sonek_pozitif):
            continue
        govde = ad[: -len(sonek_pozitif)]
        es = govde + sonek_negatif
        if es in net_seti:
            ciftler.append((ad, es))
    return ciftler


def katman_z_konumu_getir(
    stackup_sonucu: Dict[str, str],
    katman_adi: str,
    katman_kalinlik_mm: Optional[float] = None,
) -> Optional[Tuple[float, float]]:
    """`(z_ust_mm, z_alt_mm)` döner — `pcb_stackup_planner.py::
    stackup_planla()`'nın GERÇEK dönüş tipine (`Dict[str, str]`) bağlıdır.

    `stackup_planla()`/`dizilimi_olustur()` "StackupSonucu" gibi ayrı bir
    dataclass DÖNDÜRMEZ — düz `{"Katman_1": "SİNYAL (...)", "Katman_2":
    "GND", ...}` sözlüğü döner, anahtarlar `dizilimi_olustur()` içinde
    ZATEN fiziksel sırayla (Katman_1 = en üst dış katman) eklenir; Python
    dict'i insertion-order koruduğu için bu sıralama GÜVENİLİR bir Z
    kaynağıdır — burada UYDURMA bir tip icat EDİLMEDİ.

    Her katmanın kalınlığı, `pcb_stackup_planner.KATMAN_KALINLIK_
    VARSAYIMI_MM` (0.15mm) — TEK KAYNAK; bu sabit `via_stub.py`'nin stub
    uzunluğu hesabında da AYNI şekilde kullanılıyor, burada AYRI bir sabit
    TANIMLANMADI. `katman_kalinlik_mm` verilirse (ör. gerçek ölçülmüş
    stackup) varsayılanı EZER.

    `katman_adi` stackup'ta yoksa `None` döner — uydurma bir Z değeri
    ÜRETİLMEZ.
    """
    from pcb_stackup_planner import KATMAN_KALINLIK_VARSAYIMI_MM

    kalinlik = katman_kalinlik_mm if katman_kalinlik_mm is not None else KATMAN_KALINLIK_VARSAYIMI_MM
    katman_adlari = list(stackup_sonucu.keys())
    if katman_adi not in katman_adlari:
        return None
    idx = katman_adlari.index(katman_adi)
    return idx * kalinlik, (idx + 1) * kalinlik


def _geometri_topla(board, net_kodlari: set) -> List[Dict]:
    """SADECE veri toplar — `Bulgu`/PASS-FAIL mantığı İÇERMEZ (bkz. dosya
    başlığı "BULGU SÖZLEŞMESİ DÜZELTMESİ"). `izleri_ve_vialari_cikar()`
    tarafından çağrılır; bağımsız test edilebilir olması için ayrıldı."""
    geometri: List[Dict] = []
    for iz in (t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"):
        if iz.GetNetCode() not in net_kodlari:
            continue
        geometri.append({
            "tip": "iz",
            "net_adi": iz.GetNetname(),
            "baslangic": (_mm(iz.GetStart().x), _mm(iz.GetStart().y)),
            "bitis": (_mm(iz.GetEnd().x), _mm(iz.GetEnd().y)),
            "genislik_mm": _mm(iz.GetWidth()),
            "katman": board.GetLayerName(iz.GetLayer()),
        })
    for via in (t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"):
        if via.GetNetCode() not in net_kodlari:
            continue
        geometri.append({
            "tip": "via",
            "net_adi": via.GetNetname(),
            "konum": (_mm(via.GetPosition().x), _mm(via.GetPosition().y)),
            "delik_mm": _mm(via.GetDrillValue()),
        })
    return geometri


def izleri_ve_vialari_cikar(
    board_path: Path, hedef_net_adlari: List[str]
) -> Tuple[Bulgu, List[Dict]]:
    """Verilen net adlarına ait iz/via geometrisini çıkarır.

    Dönüş `Tuple[Bulgu, List[Dict]]`'tir — `Bulgu` SADECE tarama
    durumunu (PASS/KAPSAM_YOK) taşır, geometri verisi AYRI (ikinci)
    kanaldan gider. Hedef net(ler) board'da hiç bulunamazsa
    `(Bulgu(KAPSAM_YOK), [])` döner — sessizce boş liste + PASS gibi
    görünen bir sonuç ÜRETİLMEZ.

    NOT: `pcbnew` burada modül-SEVİYESİ `try/except` sentinel'i (dosya
    başındaki) DEĞİL, fonksiyon-YEREL bir `import pcbnew` ile kontrol
    edilir — `pcbnew_koprusu.py::_pcbnew_veya_kapsam_yok()` ile AYNI
    desen. Modül seviyesinde import edip bir kere `None`'a sabitlemek,
    testlerin `sys.modules["pcbnew"]`'e SONRADAN yerleştirdiği taklit
    modülü GÖRMEMESİNE yol açar (modül zaten yüklenmiş, global değişken
    donmuş olur) — bu proje `pcbnew_koprusu.py` GÖREV 2'de tam olarak bu
    tuzağı yaşayıp yerel import'a geçmişti, burada AYNI ders uygulandı.
    """
    kontrol = "izleri_ve_vialari_cikar"
    try:
        import pcbnew
    except ImportError as hata:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"pcbnew modülü import edilemedi ({hata}) — KiCad Python ortamında değiliz.",
        ), []

    board = pcbnew.LoadBoard(str(board_path))
    net_kodlari = {
        info.GetNetCode()
        for ad, info in board.GetNetsByName().items()
        if ad in hedef_net_adlari
    }
    if not net_kodlari:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"Hedef net adları board'da bulunamadı: {hedef_net_adlari}",
        ), []

    geometri = _geometri_topla(board, net_kodlari)
    taranan = sum(1 for t in board.GetTracks() if t.GetClass() in ("PCB_TRACK", "PCB_VIA"))
    bulgu = bulgu_uret(
        kontrol, taranan,
        detay=f"{len(geometri)} obje hedef netlere ({hedef_net_adlari}) ait olarak bulundu.",
    )
    return bulgu, geometri


def csxcad_kutu_olustur(csx_metal, iz: Dict, z_ust_mm: float, priority: int = 10):
    """Bir iz kaydını genişlik-farkında bir CSXCAD polygon'a çevirir ve
    `csx_metal.AddPolygon(...)` ile ekler.

    CSXCAD Python API'sinin belgelenen `Properties.AddPolygon(points,
    norm_dir, elevation, priority=...)` imzasını kullanır: `points`
    `[[x0,x1,...,xn], [y0,y1,...,yn]]` biçiminde 2xN dizi (tek eksenli
    liste ÇİFTİ, nokta çiftleri listesi DEĞİL), `norm_dir='z'` poligon
    düzleminin normali (board yüzeyine PARALEL bir dikdörtgen için doğru
    eksen), `elevation=z_ust_mm` o düzlemin Z konumu (mm — `CSX.GetGrid().
    SetDeltaUnit(1e-3)` ile birim mm'ye ayarlandığı varsayılır, bkz.
    `openems_koprusu.py::fdtd_kur_ve_calistir`). `priority`, çakışan
    geometrilerde hangisinin KAZANACAĞINI belirler — openEMS örneklerinde
    metal öncelik SIFIR DEĞİL varsayılan (10) kullanılır.

    Matematik: izin yönüne DİK birim vektör bulunup `genislik_mm/2` kadar
    HER İKİ yöne ofsetlenerek 4 köşeli bir dikdörtgen elde edilir — SADECE
    start/end noktası (sonsuz-ince çizgi) DEĞİL (bkz. dosya başlığı
    madde 2).

    DOĞRULANMADI (bu makinede CSXCAD kurulu değil — bkz. dosya başlığı):
    `AddPolygon` çağrısının KENDİSİ değil, SADECE köşe hesabı matematiği
    bu ortamda test edildi (`test_openems_3d_extractor.py`).
    """
    (x1, y1), (x2, y2) = iz["baslangic"], iz["bitis"]
    dx, dy = x2 - x1, y2 - y1
    uzunluk = math.hypot(dx, dy)
    if uzunluk <= 1e-9:
        raise ValueError(f"iz uzunluğu sıfır (dejenere segment): {iz}")

    nx, ny = -dy / uzunluk, dx / uzunluk  # yöne DİK birim vektör
    yw = iz["genislik_mm"] / 2.0
    koseler = [
        (x1 + nx * yw, y1 + ny * yw),
        (x2 + nx * yw, y2 + ny * yw),
        (x2 - nx * yw, y2 - ny * yw),
        (x1 - nx * yw, y1 - ny * yw),
    ]
    points = [[k[0] for k in koseler], [k[1] for k in koseler]]
    return csx_metal.AddPolygon(points, "z", z_ust_mm, priority=priority)
