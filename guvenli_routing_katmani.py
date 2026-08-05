#!/usr/bin/env python3
"""
guvenli_routing_katmani.py
============================
FAZ 0 — pcb-tool-v2 router'ını güçlendirme görevinin madde 3-4'ü:
routing BAŞLAMADAN ÖNCE netclass/board genişlik çelişkisini yakalayan bir
doğrulayıcı + HER routing script'inin ortak temeli olması gereken TEK bir
"güvenli yaz" wrapper'ı.

NEDEN AYRI BİR DOSYA (`otonom_python_router.py`/`pcb_carpisma_radari.py`
YERİNE): bu ikisi SAF geometri/arama katmanıdır (bilinçli olarak
`pcbnew`'e bağımlı DEĞİL, bkz. kendi dosya başlıkları). Bu modülün her iki
fonksiyonu da GERÇEK board + GERÇEK `kicad-cli` gerektirir (netclass'ları
okumak ve DRC çalıştırmak için) — ayrı tutmak, saf-mantık dosyalarının
"pcbnew gerekmez" iddiasını bozmadan bu iki katmanı net ayırır.

GÜVENLİ YAZ DİSİPLİNİ (madde 4, görev tanımından BİREBİR):
--------------------------------------------------------------------------
`guvenli_yaz_ve_dogrula()`: board'u yedekle -> değişikliği yaz -> zone'ları
refill et -> `kicad-cli pcb drc --format json --severity-all` çalıştır ->
**HEM `violations` HEM `unconnected_items` sayısını** öncekiyle karşılaştır
-> ikisinden HERHANGİ biri arttıysa yedekten GERİ AL. Sadece "0 violation"
görmek board'un tamamlandığı anlamına GELMEZ (bkz. görev tanımındaki
uyarı) — bu fonksiyon bu iki sayıyı AYRI AYRI izler, biri gizlice kötüleşip
diğeri sabit kalsa bile regresyon YAKALANIR.

DOĞRULAMA DURUMU: `netclass_genislik_dogrula()` (saf mantık, `pcbnew`
gerekmez) bu ortamda GERÇEKTEN test edildi. `netclass_genislik_dogrula_
board()` ve `guvenli_yaz_ve_dogrula()` gerçek `pcbnew`/`kicad-cli`
gerektirir — bu ortamda modül import edilebilirliği ve KAPSAM_YOK/hata
yolları test edildi, ama gerçek bir board üzerinde HENÜZ ÇALIŞTIRILMADI
(bu proje bunu SENİN makinende, cm4-io-test gibi gerçek bir board ile
doğrulaman gerektiğini defalarca vurgulamış — aynı disiplin burada da
geçerli, bkz. `pcbnew_koprusu.py` AĞ/ARAÇ UYARISI).

FAZ 0 MADDE 5 — `hata_hafizasi.py` ZORUNLU ENTEGRASYONU:
--------------------------------------------------------------------------
`guvenli_yaz_ve_dogrula()` artık isteğe bağlı bir `hata_hafizasi` +
`degisiklik_aciklamasi` parametre çifti kabul eder. Verilirse: değişiklik
uygulanmadan ÖNCE `benzer_kayitlari_bul()` ile "bu strateji daha önce
denendi mi, işe yaramadı mı" sorgulanır ve sonuç `Bulgu.detay`'a bir HAFIZA
UYARISI olarak eklenir (çağıran ajan/router bunu görüp stratejisini
değiştirebilir — fonksiyon bunu KENDİLİĞİNDEN engel olarak kullanmaz, karar
insanın/ajanın elinde kalır). Sonuç belli olunca (regresyon oldu/olmadı)
otomatik olarak `BASARISIZ`/`COZULDU` kaydı hafızaya YAZILIR — böylece bir
board'da öğrenilen "bu yaklaşım işe yaramadı" dersi, hiçbir çağıranın elle
kaydetmesine gerek kalmadan projeler arası taşınır. `hata_hafizasi=None`
(varsayılan) iken davranış TAMAMEN eskisiyle aynıdır (geriye dönük uyumlu).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from hata_hafizasi import HataHafizasi, HataKaydi, KontrolTipi, Sonuc

NM_PER_MM = 1_000_000


# ------------------------------------------------------------------
# 1. NETCLASS GENİŞLİK DOĞRULAYICI (saf mantık, pcbnew GEREKMEZ)
# ------------------------------------------------------------------

@dataclass
class NetclassGenislikIhlali:
    netclass_adi: str
    tanimli_track_width_mm: float
    board_min_track_width_mm: float


def netclass_genislik_dogrula(
    netclass_genislikleri: Dict[str, float], board_min_track_width_mm: float,
) -> List[NetclassGenislikIhlali]:
    """Routing BAŞLAMADAN ÖNCE her netclass'ın `track_width`'ini board'un
    `min_track_width` ayarına karşı kontrol eder.

    Bir netclass, board'un minimum iz genişliğinden DAHA DAR bir
    `track_width` belirtiyorsa, bu netclass'a atanmış HER iz DRC'de
    "track width below minimum" ihlali verir — bu genellikle bir
    KONFİGÜRASYON hatasıdır (netclass yanlış girilmiş/board ayarı
    sonradan sıkılaştırılmış) ve routing SESSİZCE ihlal üreten izler
    yazmadan ÖNCE, burada AÇIKÇA yakalanmalıdır."""
    ihlaller: List[NetclassGenislikIhlali] = []
    for netclass_adi, genislik_mm in netclass_genislikleri.items():
        if genislik_mm < board_min_track_width_mm:
            ihlaller.append(NetclassGenislikIhlali(netclass_adi, genislik_mm, board_min_track_width_mm))
    return ihlaller


def netclass_genislik_dogrula_bulgu(
    netclass_genislikleri: Dict[str, float], board_min_track_width_mm: float,
) -> Bulgu:
    """`netclass_genislik_dogrula()`'yı `bulgu_sozlesmesi.Bulgu` ile sarar
    — `taranan=0` (hiç netclass yoksa) KAPSAM_YOK döner, sessizce PASS
    SAYILMAZ."""
    kontrol = "netclass_genislik_dogrulama"
    ihlaller_raw = netclass_genislik_dogrula(netclass_genislikleri, board_min_track_width_mm)
    ihlaller = [
        {
            "netclass": i.netclass_adi,
            "tanimli_track_width_mm": i.tanimli_track_width_mm,
            "board_min_track_width_mm": i.board_min_track_width_mm,
        }
        for i in ihlaller_raw
    ]
    return bulgu_uret(
        kontrol, len(netclass_genislikleri), ihlaller,
        f"board_min_track_width_mm={board_min_track_width_mm}, {len(netclass_genislikleri)} netclass kontrol edildi.",
    )


def netclass_genislik_dogrula_board(board_path: str) -> Bulgu:
    """`netclass_genislik_dogrula_bulgu()`'nün GERÇEK `.kicad_pcb`'den
    okuyan sarmalayıcısı — `pcbnew.BOARD.GetDesignSettings()` üzerinden
    netclass genişliklerini ve board'un minimum iz genişliğini okur.

    DOĞRULANMADI (bu ortamda pcbnew yok) — SENİN makinende gerçek bir
    board ile çalıştırılıp doğrulanmalı; `GetNetClasses()`/`m_TrackMinWidth`
    alan adları KiCad 10 API'sine göre yazıldı ama TEK BİR KEZ BİLE
    çalıştırılamadı.
    """
    kontrol = "netclass_genislik_dogrulama"
    try:
        import pcbnew
    except ImportError as hata:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"pcbnew modülü import edilemedi ({hata}) — KiCad Python ortamında değiliz.",
        )

    board = pcbnew.LoadBoard(board_path)
    settings = board.GetDesignSettings()
    board_min_mm = settings.m_TrackMinWidth / NM_PER_MM

    # NOT: netclass'lar BOARD üzerinde değil, `BOARD_DESIGN_SETTINGS`
    # (`settings`) üzerinde yaşar — `board.GetNetClasses()` DEĞİL,
    # `settings.GetNetClasses()` (KiCad 10 API varsayımı, DOĞRULANMADI).
    netclass_genislikleri: Dict[str, float] = {}
    netclasses = settings.GetNetClasses() if hasattr(settings, "GetNetClasses") else {}
    for isim, nc in netclasses.items():
        netclass_genislikleri[str(isim)] = nc.GetTrackWidth() / NM_PER_MM
    # Default netclass bazı KiCad sürümlerinde GetNetClasses()'a DAHİL
    # DEĞİLDİR, ayrı bir GetDefault() erişimcisi ister — varsa AYRICA
    # eklenir, yoksa sessizce atlanır (uydurma bir "Default" girdisi
    # ÜRETİLMEZ).
    if hasattr(settings, "GetDefault"):
        varsayilan = settings.GetDefault()
        netclass_genislikleri.setdefault(varsayilan.GetName(), varsayilan.GetTrackWidth() / NM_PER_MM)

    return netclass_genislik_dogrula_bulgu(netclass_genislikleri, board_min_mm)


# ------------------------------------------------------------------
# 2. GÜVENLİ YAZ + DOĞRULA (yedekle -> yaz -> refill -> DRC -> gerekirse geri al)
# ------------------------------------------------------------------

def _drc_calistir_severity_all(board_path: str, kicad_cli: Optional[str] = None, zaman_asimi_s: int = 180) -> Dict[str, Any]:
    """`kicad_koprusu.py::drc_calistir()` ile AYNI subprocess deseni,
    TEK farkla: `--severity-all` bayrağı EKLENİR — görev tanımının
    kendi uyarısı ("sadece '0 violation' görmek board'un tamamlandığı
    anlamına gelmez") tam olarak bu bayrağın EKSİKLİĞİNDEN kaynaklanan
    bir riske işaret ediyor; varsayılan severity filtresi bazı ihlal
    sınıflarını (ör. sadece 'warning' önem derecesindekiler) rapor dışı
    bırakabilir."""
    import tempfile

    from arac_yollari import kicad_cli_yolunu_bul

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        rapor_path = tmp.name

    komut = [
        kicad_cli_yolunu_bul(kicad_cli), "pcb", "drc",
        "--output", rapor_path, "--format", "json", "--severity-all", board_path,
    ]
    sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi_s)
    if sonuc.returncode not in (0, 1):  # 1 = ihlal bulundu, hata DEĞİL (kicad_koprusu.py ile AYNI kural)
        raise RuntimeError(f"kicad-cli DRC başarısız (returncode={sonuc.returncode}): {sonuc.stderr}")
    with open(rapor_path, encoding="utf-8") as fh:
        return json.load(fh)


def guvenli_yaz_ve_dogrula(
    board_path: str,
    degisiklik_fonksiyonu: Callable[[Any], Any],
    kicad_cli: Optional[str] = None,
    zone_refill_yap: bool = True,
    hata_hafizasi: Optional[HataHafizasi] = None,
    degisiklik_aciklamasi: str = "",
    proje: str = "",
) -> Bulgu:
    """TEK reusable "yaz-doğrula-gerekirse geri al" wrapper'ı — HER routing
    script'inin ortak temeli olması gereken fonksiyon (görev tanımı madde 4).

    Akış: board'u `<board_path>.guvenli_yaz_yedek` olarak yedekle ->
    `degisiklik_fonksiyonu(board)` çağırıp değişikliği YÜKLENMİŞ bir
    `pcbnew.BOARD` nesnesi üzerinde uygula -> `board.Save()` -> (istenirse)
    `pcbnew.ZONE_FILLER` ile zone'ları refill et -> `kicad-cli pcb drc
    --severity-all` çalıştır -> YENİ `violations` VEYA `unconnected_items`
    sayısı ESKİSİNDEN fazlaysa (HERHANGİ biri) yedekten GERİ AL.

    `degisiklik_fonksiyonu` KENDİ `board.Save()`'ini ÇAĞIRMAMALIDIR — bu
    fonksiyon TEK bir kayıt noktası sağlar (çift kayıt/tutarsız durum
    riskini önlemek için).

    Önceki DRC durumu ÖLÇÜLEMEZSE (ör. board zaten bozuksa, kicad-cli
    hata verirse) değişiklik YİNE DE uygulanır ama karşılaştırma
    YAPILAMADIĞI için `regresyon_olcumu = "yapilamadi"` olarak
    raporlanır — sessizce "regresyon yok" VARSAYILMAZ.

    `hata_hafizasi`/`degisiklik_aciklamasi` (FAZ 0 madde 5, ikisi de
    OPSİYONEL — `None`/boş string iken davranış eskisiyle birebir aynıdır):
    verilirse, değişiklik uygulanmadan ÖNCE `degisiklik_aciklamasi`
    (ör. "MIPI_CAM0 P/N coupled route, In2.Cu via geçişi") hafızada
    aranır; daha önce AYNI/BENZER bir strateji `BASARISIZ` olarak
    kaydedilmişse bu, dönen `Bulgu.detay`'a bir HAFIZA UYARISI olarak
    eklenir (fonksiyon bunu kendiliğinden bir "dur" sebebi SAYMAZ — karar
    çağıran ajanda kalır, çünkü aynı görünen strateji farklı bağlamda işe
    yarayabilir). Sonuç belli olduktan sonra (regresyon oldu/olmadı)
    otomatik olarak `BASARISIZ`/`COZULDU` kaydı hafızaya yazılır.

    DOĞRULANMADI (bu ortamda pcbnew/kicad-cli gerçek bir board ile HENÜZ
    çalıştırılmadı — bkz. dosya başlığı).
    """
    kontrol = "guvenli_yaz_ve_dogrula"
    try:
        import pcbnew
    except ImportError as hata:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"pcbnew modülü import edilemedi ({hata}) — KiCad Python ortamında değiliz.",
        )

    board_path_p = Path(board_path)
    if not board_path_p.is_file():
        return bulgu_uret(kontrol, taranan=0, detay=f"{board_path} bulunamadı.")

    hafiza_uyarisi = ""
    if hata_hafizasi is not None and degisiklik_aciklamasi:
        eslesmeler = hata_hafizasi.benzer_kayitlari_bul(degisiklik_aciklamasi, tip=KontrolTipi.DRC)
        basarisizlar = [k for _skor, k in eslesmeler if k.sonuc == Sonuc.BASARISIZ]
        if basarisizlar:
            ornekler = "; ".join(f"'{k.cozum}' ({k.tarih}, proje={k.proje or 'bilinmiyor'})" for k in basarisizlar[:3])
            hafiza_uyarisi = (
                f" [HAFIZA UYARISI: bu/benzer strateji hafızada {len(basarisizlar)} kez "
                f"BAŞARISIZ olarak kayıtlı — {ornekler}]"
            )

    yedek_yolu = str(board_path_p) + ".guvenli_yaz_yedek"
    shutil.copy2(board_path, yedek_yolu)

    onceki_violation: Optional[int] = None
    onceki_unconnected: Optional[int] = None
    try:
        onceki_rapor = _drc_calistir_severity_all(board_path, kicad_cli=kicad_cli)
        onceki_violation = len(onceki_rapor.get("violations", []))
        onceki_unconnected = len(onceki_rapor.get("unconnected_items", []))
    except Exception:
        pass  # önceki durum ölçülemedi — regresyon karşılaştırması altta "yapilamadi" olarak işaretlenir

    board = pcbnew.LoadBoard(board_path)
    degisiklik_fonksiyonu(board)
    board.Save(board_path)

    refill_hatasi: Optional[str] = None
    if zone_refill_yap:
        try:
            board_yeniden = pcbnew.LoadBoard(board_path)
            filler = pcbnew.ZONE_FILLER(board_yeniden)
            filler.Fill(board_yeniden.Zones())
            board_yeniden.Save(board_path)
        except Exception as hata:
            refill_hatasi = str(hata)  # refill başarısızlığı DRC'yi durdurmaz, sadece raporlanır

    try:
        yeni_rapor = _drc_calistir_severity_all(board_path, kicad_cli=kicad_cli)
    except Exception as hata:
        shutil.copy2(yedek_yolu, board_path)
        return bulgu_uret(
            kontrol, taranan=1,
            ihlaller=[{"sebep": f"DRC koşumu başarısız oldu, değişiklik GERİ ALINDI: {hata}"}],
            detay=f"Board {yedek_yolu}'den geri yüklendi.",
        )

    yeni_violation = len(yeni_rapor.get("violations", []))
    yeni_unconnected = len(yeni_rapor.get("unconnected_items", []))

    if onceki_violation is None:
        regresyon_var = False
        regresyon_olcumu = "yapilamadi"
    else:
        regresyon_var = (yeni_violation > onceki_violation) or (yeni_unconnected > onceki_unconnected)
        regresyon_olcumu = "yapildi"

    if regresyon_var:
        shutil.copy2(yedek_yolu, board_path)
        if hata_hafizasi is not None and degisiklik_aciklamasi:
            hata_hafizasi.kaydet(HataKaydi(
                tip=KontrolTipi.DRC,
                mesaj=degisiklik_aciklamasi,
                kok_neden=(
                    f"violations {onceki_violation}->{yeni_violation}, "
                    f"unconnected_items {onceki_unconnected}->{yeni_unconnected}"
                ),
                cozum="Bu strateji DRC regresyonuna yol açtı, geri alındı — bir daha ÖNERİLMEMELİDİR.",
                sonuc=Sonuc.BASARISIZ,
                proje=proje,
            ))
        return bulgu_uret(
            kontrol, taranan=1,
            ihlaller=[{
                "sebep": "DRC regresyonu (violations VE/VEYA unconnected_items arttı) — değişiklik GERİ ALINDI",
                "onceki_violation": onceki_violation, "yeni_violation": yeni_violation,
                "onceki_unconnected": onceki_unconnected, "yeni_unconnected": yeni_unconnected,
            }],
            detay=f"Board {yedek_yolu}'den geri yüklendi.{hafiza_uyarisi}",
        )

    if hata_hafizasi is not None and degisiklik_aciklamasi:
        hata_hafizasi.kaydet(HataKaydi(
            tip=KontrolTipi.DRC,
            mesaj=degisiklik_aciklamasi,
            kok_neden="",
            cozum=(
                f"Bu strateji uygulandı, DRC regresyonu YOK (violations {onceki_violation}->{yeni_violation}, "
                f"unconnected_items {onceki_unconnected}->{yeni_unconnected})."
            ),
            sonuc=Sonuc.COZULDU,
            proje=proje,
        ))

    detay = (
        f"Değişiklik uygulandı ve KORUNDU. regresyon_olcumu={regresyon_olcumu}, "
        f"violations: {onceki_violation}->{yeni_violation}, "
        f"unconnected_items: {onceki_unconnected}->{yeni_unconnected}.{hafiza_uyarisi}"
    )
    if refill_hatasi:
        detay += f" UYARI: zone refill başarısız oldu ({refill_hatasi}) — DRC yine de çalıştırıldı."

    return bulgu_uret(kontrol, taranan=1, ihlaller=[], detay=detay)
