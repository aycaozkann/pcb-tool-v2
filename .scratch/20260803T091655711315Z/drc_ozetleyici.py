"""
drc_ozetleyici.py
==================
GÖREV 11 (`DOCS/11_Full_Otonom_Donusum_Talimati.md`): `kicad_koprusu.py::
drc_raporunu_ozetle()` DRC/ERC JSON raporundaki HER ihlali (violations +
unconnected_items) tekilleştirmeden, ham `[severity] description` satırı
olarak döndürüyordu — yoğun bir bölgede (ör. bir IC'nin altındaki 12 kısa
devre) bu 12 ayrı satır olarak dökülüp context'i şişiriyor ve konum
bağlamını (bir bölgede mi yoksa kartın her yerine mi dağılmış) gizliyor.

Bu modül, gerçek KiCad DRC JSON şemasının HER ihlal için `items[].pos`
altında taşıdığı koordinatları OKUYUP basit bir grid/merkez-noktası
yaklaşımıyla ihlalleri coğrafi olarak kümeler ve `bulgu_sozlesmesi.Bulgu`
sözleşmesiyle raporlar.

BİLİNÇLİ TASARIM KARARI: `kicad_koprusu.py::drc_raporunu_ozetle()`
DEĞİŞTİRİLMEDİ (geriye dönük uyumluluk — `test_kicad_koprusu.py:75` bu
fonksiyonun ham liste davranışına bağlı). Bu modül ONUN YANINDA, ayrı bir
"kümelenmiş özet" katmanı olarak durur; `kicad_koprusu.py`'yi import ETMEZ,
sadece onun ÜRETTİĞİ DRC rapor sözlüğünü (`Dict`) girdi olarak alır.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

# `kicad_koprusu.py::_drc_tum_ihlaller`'daki ŞEMA VARSAYIMIYLA AYNI: DRC
# raporunda ihlaller iki ayrı anahtar altında gelir (violations +
# unconnected_items). Bu modül kendi kopyasını tutar — `kicad_koprusu`'yu
# import ETMEMEK (döngüsel bağımlılık riski YOK, ama modülü kasıtlı olarak
# "sadece bir Dict alır" ilkesine sadık tutmak için, bkz. dosya başlığı).
_ANAHTARLAR = ("violations", "unconnected_items")


def _tum_ihlaller(rapor: Dict) -> List[Dict]:
    ihlaller: List[Dict] = []
    for anahtar in _ANAHTARLAR:
        ihlaller.extend(rapor.get(anahtar, []))
    return ihlaller


def ihlalden_temsili_konum(ihlal: Dict) -> Optional[Tuple[float, float]]:
    """Bir ihlalin `items[]` listesindeki `pos` alanlarının merkez
    noktasını (centroid) hesaplar. `items`/`pos` yoksa (beklenmeyen/eksik
    bir girdi şeması) `None` döner — UYDURMA KOORDİNAT üretilmez, çağıran
    taraf bu ihlali "konumsuz" grubuna koymalıdır."""
    konumlar = [
        (float(item["pos"]["x"]), float(item["pos"]["y"]))
        for item in ihlal.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("pos"), dict)
        and "x" in item["pos"] and "y" in item["pos"]
    ]
    if not konumlar:
        return None
    return (
        sum(x for x, _ in konumlar) / len(konumlar),
        sum(y for _, y in konumlar) / len(konumlar),
    )


@dataclass
class Kume:
    """Coğrafi olarak yakın ihlallerin gruplandığı tek bir küme."""

    merkez: Optional[Tuple[float, float]]
    sayi: int
    severity_dagilimi: Dict[str, int] = field(default_factory=dict)
    ornek_aciklamalar: List[str] = field(default_factory=list)
    refdes: Optional[str] = None

    @property
    def konumsuz_mu(self) -> bool:
        return self.merkez is None


_KONUMSUZ_ANAHTAR = "__KONUMSUZ__"


def ihlalleri_kumele(ihlaller: List[Dict], hucre_boyutu_mm: float = 2.0) -> List[Kume]:
    """Basit bir grid yaklaşımıyla ihlalleri kümeler: her ihlalin temsili
    konumu (`ihlalden_temsili_konum`) `hucre_boyutu_mm` büyüklüğünde bir
    ızgara hücresine yuvarlanır; aynı hücreye düşen ihlaller TEK bir
    `Kume`'de toplanır. Küme merkezi, hücrenin köşesi DEĞİL, o hücredeki
    ihlallerin GERÇEK konumlarının ortalamasıdır (daha doğru bir "burada"
    işareti için).

    Konumsuz ihlaller (`ihlalden_temsili_konum` `None` dönenler) SESSİZCE
    ATILMAZ — ayrı, `konumsuz_mu=True` olan bir kümede toplanır."""
    if hucre_boyutu_mm <= 0:
        raise ValueError(f"hucre_boyutu_mm > 0 olmalı, alındı: {hucre_boyutu_mm}")

    hucreler: Dict[object, List[Tuple[Dict, Tuple[float, float]]]] = {}
    konumsuzlar: List[Dict] = []

    for ihlal in ihlaller:
        konum = ihlalden_temsili_konum(ihlal)
        if konum is None:
            konumsuzlar.append(ihlal)
            continue
        hucre_anahtari = (round(konum[0] / hucre_boyutu_mm), round(konum[1] / hucre_boyutu_mm))
        hucreler.setdefault(hucre_anahtari, []).append((ihlal, konum))

    kumeler: List[Kume] = []
    for grup in hucreler.values():
        konumlar = [k for _, k in grup]
        merkez = (
            sum(x for x, _ in konumlar) / len(konumlar),
            sum(y for _, y in konumlar) / len(konumlar),
        )
        severity_dagilimi: Dict[str, int] = {}
        aciklamalar: List[str] = []
        for ihlal, _ in grup:
            sev = ihlal.get("severity", "?")
            severity_dagilimi[sev] = severity_dagilimi.get(sev, 0) + 1
            aciklamalar.append(ihlal.get("description", ""))
        kumeler.append(Kume(merkez, len(grup), severity_dagilimi, aciklamalar[:5]))

    if konumsuzlar:
        severity_dagilimi = {}
        aciklamalar = []
        for ihlal in konumsuzlar:
            sev = ihlal.get("severity", "?")
            severity_dagilimi[sev] = severity_dagilimi.get(sev, 0) + 1
            aciklamalar.append(ihlal.get("description", ""))
        kumeler.append(Kume(None, len(konumsuzlar), severity_dagilimi, aciklamalar[:5]))

    # Büyükten küçüğe sırala — en yoğun bölge ilk okunan satır olsun.
    kumeler.sort(key=lambda k: k.sayi, reverse=True)
    return kumeler


_FOOTPRINT_ENGEL_SCRIPT = """
import json, sys
sys.path.insert(0, r"%s")
import pcbnew
from pcb_carpisma_radari import komponent_sinir_kutularini_al

board = pcbnew.LoadBoard(sys.argv[1])
kutular = komponent_sinir_kutularini_al(board)
print(json.dumps({
    ref: {"x_min": k.x_min, "y_min": k.y_min, "x_max": k.x_max, "y_max": k.y_max}
    for ref, k in kutular.items()
}))
"""


def en_yakin_footprint_bul(
    merkez: Tuple[float, float], board_path: Optional[str], kicad_python: Optional[str] = None,
) -> Optional[str]:
    """`merkez` (mm, DRC rapor koordinat sistemiyle AYNI) noktasına en
    yakın footprint'in referans designatörünü döner — OPSİYONEL bir
    zenginleştirme. `board_path` verilmezse veya `pcbnew`/KiCad bu
    makinede bulunamazsa (herhangi bir hata) fonksiyon ÇÖKMEZ, sadece
    `None` döner (rapor footprint ismi OLMADAN, sadece konumla üretilir).

    AĞ/ARAÇ UYARISI (`pcbnew_koprusu.py` ile AYNI disiplin): gerçek
    footprint listesi `pcbnew` gerektirir; bu ortamda mock'lu board ile
    test edilmiştir (bkz. `test_drc_ozetleyici.py`), gerçek bir
    `.kicad_pcb` ile SENİN makinende ayrıca doğrulanmalı."""
    if not board_path:
        return None
    try:
        from arac_yollari import kicad_python_yolunu_bul, pcbnew_scripti_calistir

        kicad_python_yolunu_bul(kicad_python)
    except FileNotFoundError:
        return None

    import tempfile

    script = _FOOTPRINT_ENGEL_SCRIPT % str(Path(__file__).resolve().parent)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            script_path = str(Path(tmp) / "_footprint_bul.py")
            Path(script_path).write_text(script, encoding="utf-8")
            sonuc = pcbnew_scripti_calistir(script_path, [board_path], kicad_python=kicad_python, timeout_s=60)
    except Exception:
        return None

    try:
        kutular = json.loads((sonuc.stdout or "").strip().splitlines()[-1]) if sonuc.stdout else {}
    except (json.JSONDecodeError, IndexError):
        return None
    if not kutular:
        return None

    en_yakin_ref, en_kisa_mesafe = None, math.inf
    for ref, k in kutular.items():
        cx = (k["x_min"] + k["x_max"]) / 2
        cy = (k["y_min"] + k["y_max"]) / 2
        mesafe = math.dist(merkez, (cx, cy))
        if mesafe < en_kisa_mesafe:
            en_yakin_ref, en_kisa_mesafe = ref, mesafe
    return en_yakin_ref


def kume_ozeti_uret(kume: Kume, board_path: Optional[str] = None, kicad_python: Optional[str] = None) -> str:
    """Kabul kriterindeki formatı üretir:
    'Özet: {refdes veya "X,Y civarı"} etrafında {sayi} adet {severity}
    ihlali kümelendi. Öneri: {refdes} bölgesindeki yerleşimi genişletin.'

    Konumsuz kümeler için farklı, ama yine eyleme geçirilebilir bir cümle
    üretir (konum/öneri kısmı atlanır, sessizce yok SAYILMAZ)."""
    baskin_severity = max(kume.severity_dagilimi, key=kume.severity_dagilimi.get) if kume.severity_dagilimi else "?"

    if kume.konumsuz_mu:
        return (
            f"Özet: konum bilgisi taşımayan {kume.sayi} adet {baskin_severity} ihlali var "
            "(DRC raporu şeması bu ihlaller için 'items[].pos' içermiyor). "
            "Öneri: bu ihlalleri ayrı ayrı incelemek gerekir, bölgesel kümeleme uygulanamadı."
        )

    yer_adi = kume.refdes
    if yer_adi is None and board_path:
        yer_adi = en_yakin_footprint_bul(kume.merkez, board_path, kicad_python)
        kume.refdes = yer_adi

    x, y = kume.merkez
    yer_ifadesi = yer_adi if yer_adi else f"({x:.2f}, {y:.2f}) civarı"
    return (
        f"Özet: {yer_ifadesi} etrafında {kume.sayi} adet {baskin_severity} ihlali kümelendi. "
        f"Öneri: {yer_adi + ' bölgesindeki' if yer_adi else 'bu bölgedeki'} yerleşimi genişletin."
    )


def _drc_semasi_taninmadi_mi(rapor: Dict) -> bool:
    """`kicad_koprusu.py::sema_taninmadi_mi()` ile AYNI tanıma mantığı
    (o fonksiyonu import etmemek için kasıtlı olarak kopyalanmıştır, bkz.
    dosya başlığı "sadece bir Dict alır" ilkesi) — rapor ne `violations`
    ne `unconnected_items` içeriyorsa şema TANINMADI demektir."""
    return "violations" not in rapor and "unconnected_items" not in rapor


def drc_kumeleri_bulgu_uret(
    rapor: Dict, board_path: Optional[str] = None, kicad_python: Optional[str] = None,
    hucre_boyutu_mm: float = 2.0,
) -> Bulgu:
    """`bulgu_sozlesmesi.bulgu_uret()`'i çağırıp DRC raporunun kümelenmiş
    özetini bir `Bulgu` olarak döner.

    `taranan`'ın anlamı BURADA "kaç ihlal bulundu" DEĞİLDİR (0 ihlal
    GERÇEKTEN temiz bir board anlamına gelebilir, bu KAPSAM_YOK
    SAYILMAMALI) — `taranan`, "DRC motoru tanınabilir bir rapor ÜRETTİ mi"
    sorusunun cevabıdır (`violations`/`unconnected_items` anahtarlarından
    en az biri var mı). Şema tanınmıyorsa (`rapor` bozuk/beklenmeyen bir
    yapıdaysa) `taranan=0` → otomatik KAPSAM_YOK (DRC'nin GERÇEKTEN
    çalışıp çalışmadığı BİLİNMİYOR, sessizce PASS/FAIL denemez). Şema
    tanınıyorsa `taranan=1`; ihlal listesi boşsa `ihlaller=[]` →
    `bulgu_uret` bunu PASS sayar (temiz board), doluysa FAIL."""
    if _drc_semasi_taninmadi_mi(rapor):
        return bulgu_uret(
            "drc_kumeleme", taranan=0,
            detay="DRC raporu şeması tanınmadı (violations/unconnected_items yok) — "
                  "DRC'nin gerçekten çalıştığı doğrulanamıyor.",
        )

    ihlaller = _tum_ihlaller(rapor)
    kumeler = ihlalleri_kumele(ihlaller, hucre_boyutu_mm) if ihlaller else []
    ihlal_sozlukleri = [
        {
            "merkez": k.merkez,
            "sayi": k.sayi,
            "severity_dagilimi": k.severity_dagilimi,
            "ozet": kume_ozeti_uret(k, board_path, kicad_python),
        }
        for k in kumeler
    ]
    return bulgu_uret(
        "drc_kumeleme", taranan=1, ihlaller=ihlal_sozlukleri,
        detay=f"{len(kumeler)} küme, {len(ihlaller)} ham ihlal (hücre boyutu {hucre_boyutu_mm}mm)"
        if ihlaller else "0 ihlal (temiz board)",
    )
