#!/usr/bin/env python3
"""
otonom_kurtarma_motoru.py
============================
"TAM OTONOM KURTARMA MEKANİZMASI" — `CLAUDE.md`'nin (Anayasa) yeni kuralının
kod karşılığı: routing sırasında canlı araç (MCP/`pcbnew`) çökerse
(segfault, timeout, "Python process for KiCAD scripting is not running" —
bu proje bunu GERÇEKTEN yaşadı, bkz. `HAFIZA/Hafiza_Defteri.md` 2026-07-31
kaydı) kullanıcıdan "sen çiz" diye BEKLEMEK YASAKTIR. Bu modül, bir araç
çöktüğünde otomatik olarak sırayla denenen ÜÇ savunma katmanını birleştirir.

NEDEN AYRI BİR ORKESTRATÖR MODÜL:
--------------------------------------------------------------------------
Üç katman zaten var/yeni yazıldı ama BİRBİRİNDEN BAĞIMSIZ yaşıyordu:
  1. `topolojik_router_koprusu.py::akilli_yol_bul()` — DOGRUDAN/L/U/
     KATMAN_DEGISIMI merdiveni (HIZLI, sezgisel).
  2. Bu dosyadaki `bolumlu_yol_dene()` — UZUN bir rotayı küçük parçalara
     (`segment_uzunlugu_mm`) bölüp HER PARÇAYI ayrı ayrı `akilli_yol_bul()`
     ile çözmeyi dener (bir bütün olarak karmaşık bir yol, küçük
     parçalara bölününce çözülebilir hale gelebilir).
  3. `otonom_python_router.py::izgara_a_yildiz_ara()` — SON ÇARE, kapsamlı
     ızgara A* araması (YAVAŞ ama İNATÇI).
`otonom_routing_merdiveni()` bu üçünü TEK bir çağrıda sırayla dener, HER
başarılı adayı `izole_calistir()` (Görev 1 — subprocess sandboxing) ile
board'a YAZMAYA çalışır; yazma da çökerse (pcbnew segfault/timeout) o
katman BAŞARISIZ sayılır ve BİR SONRAKİ katmana geçilir — asla üst
seviyeye (çağıran ajana/kullanıcıya) HAM bir crash/exception SIZDIRILMAZ.

GÖREV 1 — NEDEN SUBPROCESS SANDBOXING (`izole_calistir`):
--------------------------------------------------------------------------
`pcbnew`'in C++ çekirdeği (SWIG üzerinden) segfault edebilir veya
donabilir (bu proje MCP'de GERÇEKTEN yaşadı: `route_trace` 30s timeout
sonrası backend'in TAMAMEN öldüğü, `open_project` ile bile kurtarılamadığı
gözlemlendi). Bu, ana süreçte (MCP sunucusu/bu ajanın kendi Python süreci)
çalıştırılırsa TÜM oturumu düşürür. `izole_calistir()`, hedef fonksiyonu
`subprocess.run([sys.executable, "-c", ...], timeout=...)` ile KISA ÖMÜRLÜ,
İZOLE bir alt süreçte çalıştırır — o süreç çökerse/donarsa SADECE o alt
süreç kaybolur, ana süreç `{"basarili": False, "hata": "..."}" ile
DEVAM EDER. Bu, MCP sunucusunun kendi kaynak kodunu (bu proje onun
SAHİBİ değil, `mixelpixx/KiCAD-MCP-Server` harici bir bağımlılıktır)
değiştirmeden, BU PROJENİN KENDİ yazma çağrılarına (`topolojik_router_
koprusu.TopolojikRouter.iz_yaz`, `otonom_python_router.duz_izleri_
pcbnew_ile_yaz`) uygulanabilen bir sandboxing katmanıdır.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from topolojik_router_koprusu import (
    Engel,
    Strateji,
    YolIstegi,
    YolSonucu,
    akilli_yol_bul,
)
from otonom_python_router import izgara_a_yildiz_ara


# ------------------------------------------------------------------
# GÖREV 1 — SUBPROCESS SANDBOXING (izole çalıştırma)
# ------------------------------------------------------------------

@dataclass
class IzoleSonuc:
    basarili: bool
    sonuc: Any = None
    hata: str = ""
    stderr: str = ""


_ALT_SUREC_SABLONU = """
import importlib
import json
import sys

girdi = json.loads(sys.argv[1])
modul_adi, fonksiyon_adi = girdi["fonksiyon_yolu"].split(":")
modul = importlib.import_module(modul_adi)
fonksiyon = getattr(modul, fonksiyon_adi)
sonuc = fonksiyon(**girdi["kwargs"])
print(json.dumps({"sonuc": sonuc}))
"""


def izole_calistir(
    fonksiyon_yolu: str,
    kwargs: Optional[Dict[str, Any]] = None,
    zaman_asimi_s: int = 30,
    python_yolu: Optional[str] = None,
) -> IzoleSonuc:
    """`fonksiyon_yolu` ("modul:fonksiyon" biçiminde) ile belirtilen
    fonksiyonu, `kwargs` ile, KISA ÖMÜRLÜ bir alt süreçte çalıştırır.

    Fonksiyonun DÖNÜŞ DEĞERİ `json.dumps` ile serileştirilebilir OLMALIDIR
    (örn. `int`/`str`/`dict`/`list`) — `pcbnew` nesneleri DEĞİL; bu yüzden
    hedef fonksiyonlar (`TopolojikRouter.iz_yaz`, `duz_izleri_pcbnew_ile_
    yaz`) zaten sade bir `int` (eklenen segment sayısı) döner.

    Üç ayrı başarısızlık modu, ÜÇÜ de exception FIRLATMADAN, yapılandırılmış
    `IzoleSonuc` olarak döner (çağıranın üst katmana geçebilmesi için):
      - **timeout:** `subprocess.TimeoutExpired` — alt süreç donmuş olabilir
        (gerçek pcbnew segfault/hang senaryosu).
      - **çökme:** alt süreç sıfır olmayan çıkış koduyla bitti (exception,
        segfault sinyali) — `stderr` tanı için saklanır.
      - **json_hatasi:** alt süreç sıfır ile bitti ama stdout geçerli JSON
        DEĞİLDİ (beklenmeyen çıktı) — sessizce "başarılı" SAYILMAZ.
    """
    kwargs = kwargs or {}
    girdi = json.dumps({"fonksiyon_yolu": fonksiyon_yolu, "kwargs": kwargs})
    komut = [python_yolu or sys.executable, "-c", _ALT_SUREC_SABLONU, girdi]

    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi_s)
    except subprocess.TimeoutExpired:
        return IzoleSonuc(False, hata=f"timeout ({zaman_asimi_s}s) — alt süreç donmuş olabilir (pcbnew hang)")

    if sonuc.returncode != 0:
        return IzoleSonuc(False, hata="cokme", stderr=sonuc.stderr[-2000:])

    try:
        veri = json.loads(sonuc.stdout)
    except (json.JSONDecodeError, ValueError):
        return IzoleSonuc(False, hata="json_hatasi", stderr=sonuc.stdout[-2000:])

    return IzoleSonuc(True, sonuc=veri.get("sonuc"))


# ------------------------------------------------------------------
# GÖREV 2 — WAYPOINT/SEGMENT FALLBACK (uzun yolu parçalara böl)
# ------------------------------------------------------------------

def bolumlu_yol_dene(
    istek: YolIstegi,
    engeller: Sequence[Engel] = (),
    segment_uzunlugu_mm: float = 5.0,
) -> YolSonucu:
    """`istek.baslangic` → `istek.bitis` doğrusunu ~`segment_uzunlugu_mm`'lik
    ara noktalara böler, HER ardışık çifti AYRI bir `akilli_yol_bul()`
    çağrısıyla çözmeyi dener.

    Neden işe yarayabilir: `akilli_yol_bul()`'un L/U merdiveni TEK bir
    uzun (12-14mm) rota için engelleri aşamayabilir (çok fazla farklı
    engel aynı anda devrede) ama her biri ~5mm'lik KISA bir parça için
    aynı merdiven genelde yeterlidir — problem alanı KÜÇÜLTÜLEREK
    çözülebilir hale getirilir.

    HERHANGİ bir parça çözülemezse TÜM sonuç `BULUNAMADI` döner (kısmi bir
    yol yazılmaz) — `notlar` HANGİ parçanın hangi basamakta tıkandığını
    taşır ki bir sonraki katman (A*) veya insan bunu okuyabilsin.
    """
    import math

    (x1, y1), (x2, y2) = istek.baslangic, istek.bitis
    toplam_uzunluk = math.dist((x1, y1), (x2, y2))
    if toplam_uzunluk <= segment_uzunlugu_mm:
        return akilli_yol_bul(istek, engeller)

    parca_sayisi = max(1, round(toplam_uzunluk / segment_uzunlugu_mm))
    ara_noktalar = [
        (x1 + (x2 - x1) * i / parca_sayisi, y1 + (y2 - y1) * i / parca_sayisi)
        for i in range(parca_sayisi + 1)
    ]

    tum_segmentler: List[Any] = []
    katmanlar: List[str] = []
    toplam_via = 0
    notlar: List[str] = [f"{parca_sayisi} parçaya bölündü (~{segment_uzunlugu_mm}mm/parça)"]

    for i in range(parca_sayisi):
        alt_istek = YolIstegi(
            ara_noktalar[i], ara_noktalar[i + 1], istek.net,
            istek.iz_genisligi_mm, istek.clearance_mm, istek.katman, istek.yuksek_hiz_mi,
        )
        alt_sonuc = akilli_yol_bul(alt_istek, engeller)
        if not alt_sonuc.bulundu_mu:
            notlar.append(f"parça {i + 1}/{parca_sayisi} çözülemedi: {'; '.join(alt_sonuc.notlar)}")
            return YolSonucu([], Strateji.BULUNAMADI, 0, [], notlar)
        tum_segmentler.extend(alt_sonuc.segmentler)
        for k in alt_sonuc.katmanlar:
            if k not in katmanlar:
                katmanlar.append(k)
        toplam_via += alt_sonuc.via_sayisi

    notlar.append("tüm parçalar bağımsız çözüldü, tek yol olarak birleştirildi")
    return YolSonucu(tum_segmentler, Strateji.U_DONUSU, toplam_via, katmanlar, notlar)


# ------------------------------------------------------------------
# ORKESTRATÖR — üç katmanı sırayla dener, HER yazmayı izole çalıştırır
# ------------------------------------------------------------------

@dataclass
class MerdivenSonucu:
    basarili: bool
    basamak: str  # "AKILLI_YOL" | "BOLUMLU_YOL" | "IZGARA_A_YILDIZ" | "TUKENDI"
    yazilan_segment_sayisi: int = 0
    tum_notlar: List[str] = field(default_factory=list)
    needs_human: bool = False


def otonom_routing_merdiveni(
    istek: YolIstegi,
    engeller: Sequence[Engel],
    board_path: str,
    genislik_mm: float,
    segment_uzunlugu_mm: float = 5.0,
    a_yildiz_hucre_mm: float = 0.1,
    a_yildiz_clearance_mm: float = 0.2,
    izole_zaman_asimi_s: int = 30,
    yazma_fonksiyonu_yolu: str = "topolojik_router_koprusu:_bulgu_uyumlu_iz_yaz",
) -> MerdivenSonucu:
    """ÜÇ katmanı sırayla dener; HER başarılı geometriyi board'a yazarken
    `izole_calistir()` kullanır — yazma da çökerse bir SONRAKİ katmana
    geçilir (asla üst katmana ham exception sızdırılmaz).

    `NEEDS_HUMAN=True` SADECE üçü de (geometri arama VEYA izole yazma
    anlamında) gerçekten tükendiğinde döner — bu, CLAUDE.md'nin "araç
    çöktü" (otomatik kurtarma zorunlu) ile "aynı ihlal 3 kez tekrarlıyor"
    (gerçek mühendislik kararı gerektirir) ayrımının BİRİNCİSİNİ tüketmiş
    olduğunun kanıtıdır — ikincisi bu modülün kapsamı DIŞINDADIR.
    """
    tum_notlar: List[str] = []

    # Basamak 1: akilli_yol_bul (hızlı, sezgisel)
    s1 = akilli_yol_bul(istek, engeller)
    if s1.bulundu_mu:
        yazma = izole_calistir(
            yazma_fonksiyonu_yolu,
            {"board_path": board_path, "net_ismi": istek.net, "genislik_mm": genislik_mm,
             "segmentler": s1.segmentler, "katman": s1.katmanlar[0] if s1.katmanlar else istek.katman},
            izole_zaman_asimi_s,
        )
        if yazma.basarili:
            return MerdivenSonucu(True, "AKILLI_YOL", yazma.sonuc or 0, tum_notlar + s1.notlar)
        tum_notlar.append(f"AKILLI_YOL bulundu ama izole yazma başarısız: {yazma.hata}")
    else:
        tum_notlar.append(f"AKILLI_YOL bulunamadı: {'; '.join(s1.notlar)}")

    # Basamak 2: bölümlü (waypoint segmentasyonu)
    s2 = bolumlu_yol_dene(istek, engeller, segment_uzunlugu_mm)
    if s2.bulundu_mu:
        yazma2 = izole_calistir(
            yazma_fonksiyonu_yolu,
            {"board_path": board_path, "net_ismi": istek.net, "genislik_mm": genislik_mm,
             "segmentler": s2.segmentler, "katman": s2.katmanlar[0] if s2.katmanlar else istek.katman},
            izole_zaman_asimi_s,
        )
        if yazma2.basarili:
            return MerdivenSonucu(True, "BOLUMLU_YOL", yazma2.sonuc or 0, tum_notlar + s2.notlar)
        tum_notlar.append(f"BOLUMLU_YOL bulundu ama izole yazma başarısız: {yazma2.hata}")
    else:
        tum_notlar.append(f"BOLUMLU_YOL bulunamadı: {'; '.join(s2.notlar)}")

    # Basamak 3: saf Python ızgara A* (son çare)
    a_yildiz_engeller = [
        type("K", (), {"x_min": e.x_min, "y_min": e.y_min, "x_max": e.x_max, "y_max": e.y_max})()
        for e in engeller
    ]
    s3 = izgara_a_yildiz_ara(
        istek.baslangic, istek.bitis, a_yildiz_engeller, a_yildiz_hucre_mm, a_yildiz_clearance_mm,
    )
    if s3.bulundu_mu:
        yazma3 = izole_calistir(
            "otonom_python_router:duz_izleri_pcbnew_ile_yaz",
            {"board_path": board_path, "net_ismi": istek.net, "yol_noktalari": s3.yol,
             "genislik_mm": genislik_mm, "katman": istek.katman},
            izole_zaman_asimi_s,
        )
        if yazma3.basarili:
            return MerdivenSonucu(True, "IZGARA_A_YILDIZ", yazma3.sonuc or 0, tum_notlar)
        tum_notlar.append(f"IZGARA_A_YILDIZ bulundu ama izole yazma başarısız: {yazma3.hata}")
    else:
        tum_notlar.append(f"IZGARA_A_YILDIZ bulunamadı: {s3.neden}")

    tum_notlar.append(
        "TÜM otomatik katmanlar (akıllı yol / bölümlü yol / ızgara A*) tükendi — "
        "bu artık bir araç çökmesi DEĞİL, muhtemelen gerçek bir yerleşim sorunu "
        "(NEEDS_HUMAN, bkz. CLAUDE.md 'Sonsuz Döngü Kaçış Kuralı')."
    )
    return MerdivenSonucu(False, "TUKENDI", 0, tum_notlar, needs_human=True)


# ------------------------------------------------------------------
# ÖZ-TEST YARDIMCI FONKSİYONLARI (izole alt süreçte çağrılabilmesi için
# modül seviyesinde, kwargs kabul eden — math.sqrt/time.sleep GİBİ C
# fonksiyonları **kwargs kabul ETMEZ, bu yüzden testte kullanılamaz)
# ------------------------------------------------------------------

def _test_topla(a: float, b: float) -> float:
    return a + b


def _test_uyu(saniye: float) -> str:
    import time

    time.sleep(saniye)
    return "uyandi"


def _test_patla() -> None:
    raise RuntimeError("kasıtlı fault-injection çökmesi")


# ------------------------------------------------------------------
# ÖZ-TEST (fault-injection dahil — pcbnew GEREKMEZ)
# ------------------------------------------------------------------

def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. izole_calistir: normal (pcbnew gerektirmeyen) bir fonksiyon başarıyla çalışmalı
    sonuc = izole_calistir("otonom_kurtarma_motoru:_test_topla", {"a": 3.0, "b": 4.0}, zaman_asimi_s=10)
    if not sonuc.basarili or sonuc.sonuc != 7.0:
        hatalar.append(f"izole_calistir normal fonksiyonda başarısız: {sonuc}")

    # 2. FAULT INJECTION: alt süreçte kasıtlı exception -> çökme YAKALANMALI, exception SIZMAMALI
    sonuc2 = izole_calistir("otonom_kurtarma_motoru:_test_patla", {}, zaman_asimi_s=10)
    if sonuc2.basarili or sonuc2.hata != "cokme":
        hatalar.append(f"izole_calistir kasıtlı hatayı yakalayamadı: {sonuc2}")

    # 3. FAULT INJECTION: timeout -> yakalanmalı, ana süreç düşmemeli
    sonuc3 = izole_calistir("otonom_kurtarma_motoru:_test_uyu", {"saniye": 5}, zaman_asimi_s=1)
    if sonuc3.basarili or "timeout" not in sonuc3.hata:
        hatalar.append(f"izole_calistir timeout'u doğru yakalamadı: {sonuc3}")

    # 4. bolumlu_yol_dene: kısa mesafede doğrudan akilli_yol_bul'a düşmeli
    kisa = YolIstegi((0.0, 0.0), (2.0, 0.0), "SIG")
    s = bolumlu_yol_dene(kisa, [], segment_uzunlugu_mm=5.0)
    if not s.bulundu_mu:
        hatalar.append("kısa mesafede bolumlu_yol_dene başarısız oldu")

    # 5. bolumlu_yol_dene: uzun mesafe parçalara bölünmeli VE engelsizse bulunmalı
    uzun = YolIstegi((0.0, 0.0), (20.0, 0.0), "SIG")
    s2 = bolumlu_yol_dene(uzun, [], segment_uzunlugu_mm=5.0)
    if not s2.bulundu_mu or "parça" not in s2.notlar[0]:
        hatalar.append(f"uzun mesafe segmentasyonu beklendiği gibi çalışmadı: {s2}")

    # 6. bolumlu_yol_dene: HERHANGİ bir parça engelliyse TÜM sonuç BULUNAMADI olmalı
    #    (kısmi yol YAZILMAZ)
    tam_engel = Engel("tam_kapatan_duvar", -100.0, -1.0, 100.0, 1.0, clearance_mm=0.2)
    s3 = bolumlu_yol_dene(uzun, [tam_engel], segment_uzunlugu_mm=5.0)
    if s3.bulundu_mu:
        hatalar.append("her yönde kapatan engelde bolumlu_yol_dene yanlışlıkla başarılı oldu")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: otonom_kurtarma_motoru.py öz testleri temiz.")
