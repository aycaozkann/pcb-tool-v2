#!/usr/bin/env python3
"""
openems_koprusu.py
===================
KiCad board'undan MIPI CSI-2 diferansiyel çift geometrisini çıkarıp openEMS
(FDTD) ile S-parametre simülasyonu koşturan köprü.

NEDEN BU DOSYA VAR:
`ngspice_koprusu.py` devre-seviyesi (DC/AC/transient) simülasyon yapıyor ama
transmission-line/EM davranışını (empedans süreksizliği, return loss, göz
diyagramı) göremiyor. Bu modül o boşluğu kapatır — `pcb_stackup_planner.py`/
`empedans_cozucu.py`'nin analitik (kapalı-form) formüllerinden DAHA GÜÇLÜ
bir doğrulama katmanı: analitik formüller ilk tahmin, openEMS gerçek 3D
alan çözümü. İkisi ÇELİŞTİĞİNDE openEMS kazanır.

TEKNİK KARAR — subprocess+XML DEĞİL, resmi Python API:
--------------------------------------------------------
openEMS'in port/mesh/excitation tanımı elle XML yazarak GÜVENİLİR şekilde
üretilemez — resmi örnekler (ör. differential microstrip line tutorial)
hep `CSXCAD.ContinuousStructure()` + `openEMS.openEMS()` Python
nesneleriyle kuruluyor; bu yaklaşım geometriyi (pcbnew'den gelen track/via
koordinatları) doğrudan `AddBox`/`AddCylinder` çağrılarına besleyebilmeyi
sağlıyor, ara XML formatı gerekmiyor. Bu yüzden bu modül `CSXCAD`/`openEMS`
Python paketlerinin KURULU olmasını varsayar (bkz. `openems_kurulu_mu()`).

SAYI UYDURMA YASAĞI (ngspice_koprusu.py ile AYNI disiplin):
--------------------------------------------------------------
openEMS/CSXCAD Python paketleri import edilemiyorsa bu modül HİÇBİR
S-parametre üretmez, `Bulgu(durum=KAPSAM_YOK, taranan=0)` döner. Simülasyon
koşup da sonuç dosyası (`.s4p`) oluşmazsa bu FAIL'dir, KAPSAM_YOK DEĞİL —
ikisi ayrı: KAPSAM_YOK = "hiç koşmadı", FAIL = "koştu ama başarısız/sonuç
üretemedi".

GEOMETRİ ÇIKARIMI — YENİDEN YAZMA, TEKRAR KULLAN:
--------------------------------------------------
`geometri_cikar()` YENİ bir `board.GetTracks()` döngüsü YAZMAZ —
`pcbnew_koprusu.py::net_iz_ve_via_listesi_topla()` (bu görev kapsamında o
dosyaya EKLENDİ, tam da bu köprünün ihtiyacı için) çağrılır. Gerber'den
çıkarım yalnızca pcbnew erişilemiyorsa yedek yol olarak DÜŞÜNÜLEBİLİR —
bu sürümde YAZILMADI (`pcbnew` yoksa zaten `KAPSAM_YOK`, Gerber yedeği
ayrı, opsiyonel bir görev).

DOĞRULAMA DURUMU (bu makinede GERÇEKTEN doğrulanan/doğrulanmayan kısımlar
— TAHMİNLE DEĞİL, GERÇEK KOŞUMLA güncellenmiştir):
--------------------------------------------------------------------------
  - **openems_kurulu_mu(): DOĞRULANDI.** Bu makinede `CSXCAD`/`openEMS`
    Python paketleri KURULU DEĞİL — `import` denemesi gerçekten
    `ModuleNotFoundError` fırlattı, fonksiyon `False` döndü (ölçüldü).
  - **geometri_cikar(): pcbnew erişim/KAPSAM_YOK yolu sahte-pcbnew mock'uyla
    DOĞRULANDI** (`test_openems_koprusu.py`) — gerçek bir `.kicad_pcb` ile
    HENÜZ doğrulanmadı (bu ortamda gerçek KiCad/pcbnew kurulu değil, aynı
    `pcbnew_koprusu.py` AĞ/ARAÇ UYARISI geçerli).
  - **fdtd_kur_ve_calistir(): TAMAMEN YAZILDI (port/excitation dahil),
    ARAYÜZ SÖZLEŞMESİ SEVİYESİNDE test edildi, GERÇEK openEMS'te HİÇ
    ÇALIŞTIRILAMADI.** KAPSAM_YOK dalı (openEMS yokken) bu makinede
    GERÇEKTEN tetiklendi. Sinyal izi kutuları `openems_3d_extractor.py::
    csxcad_kutu_olustur()`'u ÇAĞIRIYOR (eskiden eksen-hizalı `AddBox`
    kullanılıyordu — 45° izlerde genişliği ~1.4x FAZLA gösteren bir
    hataydı, şimdi izin yönüne DİK ofsetle GERÇEK dikdörtgen kesit
    üretiliyor). Diferansiyel 4-port lumped port kurulumu (yakın uçta P/N
    zıt işaretle excite=±1, uzak uçta P/N pasif yük) + `CalcPort()` ile
    Sdd11/Sdd21 hesabı + `skrf` ile `.s2p` yazımı TAMAMEN YAZILDI ve
    `sys.modules["CSXCAD"]`/`["openEMS"]`'e yerleştirilen SAHTE modüllerle
    (`test_openems_koprusu.py::TestFdtdKurVeCalistirSahteOpenems`, 4 test)
    akış/imza/excite-işareti seviyesinde DOĞRULANDI — ama bu sahte testler
    GERÇEK openEMS FİZİĞİNİ doğrulamaz, sadece "bu fonksiyon çağırdığı
    API'yi doğru sırada/doğru imzayla çağırıyor mu" sorusuna cevap verir.
    SENİN openEMS kurulu makinende, bilinen empedanslı bir referans
    yapıyla (ör. 100Ω MIPI D-PHY diferansiyel çift) sayısal doğruluk
    AYRICA doğrulanmadan PRODUCTION kararı için KULLANILMAMALI.
  - **s_parametre_degerlendir(): YAZILDI, gerçek `.s4p` ile TEST
    EDİLMEDİ** (`skrf` de bu makinede kurulu değil). Tek-uçlu (single-ended)
    Sii dönüş kaybı hesabı YAZILDI ve KAPSAM_YOK/FAIL dallarıyla test
    edildi; diferansiyel (Sdd) mixed-mode dönüşümü (`skrf.Network.se2gmm`'in
    port-eşleştirme kuralı bu fonksiyonda TEYİT EDİLMEDİĞİ için) BİLEREK
    eklenmedi — ama `fdtd_kur_ve_calistir()` artık Sdd11/Sdd21'i KENDİ
    içinde (mixed-mode dönüşümüne İHTİYAÇ DUYMADAN, diferansiyel excite
    ile TEK koşumda) hesaplayıp doğrudan `.s2p` yazdığı için bu fonksiyonun
    diferansiyel sınırı `fdtd_kur_ve_calistir()`'in ÇIKTISI için ARTIK
    SORUN DEĞİL — sadece HARİCİ/bağımsız üretilmiş 4-portlu bir `.s4p`
    dosyasını değerlendirmek isteyen çağıranlar için hâlâ geçerli bir sınır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret


# --------------------------------------------------------------------------
# Kurulum kontrolü — sayı uydurma yasağının ilk savunma hattı
# --------------------------------------------------------------------------

def openems_kurulu_mu() -> bool:
    """openEMS/CSXCAD Python paketleri import edilebiliyor mu?

    NOT: `shutil.which("openEMS")` (CLI ikili dosyası) DEĞİL — bu modül
    Python API kullanıyor, o yüzden import denemesi doğru kontrol.
    """
    try:
        import CSXCAD  # noqa: F401
        import openEMS  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------
# Geometri çıkarımı — pcbnew_koprusu.py'deki MEVCUT yardımcıyı kullanır
# --------------------------------------------------------------------------

@dataclass
class DiferansiyelCiftGeometrisi:
    net_adi_pozitif: str
    net_adi_negatif: str
    iz_segmentleri_pozitif: List[dict] = field(default_factory=list)
    iz_segmentleri_negatif: List[dict] = field(default_factory=list)
    via_listesi_pozitif: List[dict] = field(default_factory=list)
    via_listesi_negatif: List[dict] = field(default_factory=list)
    referans_duzlem_z_mm: float = 0.0


def geometri_cikar(
    pcb_yolu: str,
    net_adi_pozitif: str,
    net_adi_negatif: str,
    referans_duzlem_z_mm: float = 0.0,
) -> Tuple[Optional[DiferansiyelCiftGeometrisi], Optional[Bulgu]]:
    """MIPI D+ / D- çiftinin iz/via geometrisini pcbnew'den çıkarır.

    `pcbnew_koprusu.py::net_iz_ve_via_listesi_topla()`'yı TEKRAR KULLANIR
    (yeni bir `board.GetTracks()` döngüsü YAZILMADI). `referans_duzlem_z_mm`
    şimdilik çağıran tarafça verilir — `pcb_stackup_planner.py`'nin stackup
    çıktısından TEK KAYNAK olarak türetilmesi ayrı bir entegrasyon adımıdır
    (bu sürümde YAPILMADI, sabit/varsayılan 0.0 kullanılıyor — sessizce
    "doğru" varsayılmasın diye burada AÇIKÇA belirtiliyor).

    Döner: `(geometri, None)` başarılıysa; `pcbnew` kurulu değilse veya
    her iki net'te de hiç iz yoksa `(None, Bulgu(KAPSAM_YOK))` — çağıran
    `if kapsam_yok is not None: return kapsam_yok` ile erken çıkabilir
    (`pcbnew_koprusu.py::_pcbnew_veya_kapsam_yok` ile AYNI desen).
    """
    kontrol = "openems_geometri_cikarimi"
    from pcbnew_koprusu import _pcbnew_veya_kapsam_yok, net_iz_ve_via_listesi_topla

    _pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(pcb_yolu, kontrol)
    if kapsam_yok is not None:
        return None, kapsam_yok

    pozitif = net_iz_ve_via_listesi_topla(board, net_adi_pozitif)
    negatif = net_iz_ve_via_listesi_topla(board, net_adi_negatif)

    if not pozitif["izler"] and not negatif["izler"]:
        return None, bulgu_uret(
            kontrol, taranan=0, detay=(
                f"'{net_adi_pozitif}'/'{net_adi_negatif}' net çiftinde hiç iz "
                "bulunamadı — geometri çıkarılamadı (KAPSAM_YOK, PASS DEĞİL)."
            ),
        )

    geometri = DiferansiyelCiftGeometrisi(
        net_adi_pozitif=net_adi_pozitif,
        net_adi_negatif=net_adi_negatif,
        iz_segmentleri_pozitif=pozitif["izler"],
        iz_segmentleri_negatif=negatif["izler"],
        via_listesi_pozitif=pozitif["vialar"],
        via_listesi_negatif=negatif["vialar"],
        referans_duzlem_z_mm=referans_duzlem_z_mm,
    )
    return geometri, None


# --------------------------------------------------------------------------
# FDTD kurulum + koşum
# --------------------------------------------------------------------------

_MESH_ADIM_MM = {"kaba": 0.2, "orta": 0.1, "ince": 0.05}


def fdtd_kur_ve_calistir(
    geometri: DiferansiyelCiftGeometrisi,
    calisma_dizini: str,
    mesh_cozunurlugu: Literal["kaba", "orta", "ince"] = "kaba",
    frekans_araligi_ghz: Tuple[float, float] = (0.1, 6.0),
    hedef_empedans_ohm: float = 100.0,
    substrat_kalinligi_mm: float = 0.2,
    bakir_kalinligi_mm: float = 0.035,
) -> Bulgu:
    """openEMS Python API ile diferansiyel port + mesh kurup FDTD koşturur.

    openEMS/CSXCAD kurulu değilse KAPSAM_YOK döner (taranan=0) — hiçbir
    S-parametre üretmez, hiçbir dosya yazmaz (bu dal bu makinede GERÇEKTEN
    tetiklendi/test edildi, bkz. dosya başlığı).

    UYARI: Bu fonksiyonun geri kalanı (mesh/geometri/port kurulumu) openEMS
    kurulu OLMAYAN bu makinede TEK BİR KEZ BİLE ÇALIŞTIRILAMADI — bilinen
    empedanslı bir referans yapıyla doğrulanmadan production kararı için
    KULLANILMAMALI (bkz. dosya başlığı DOĞRULAMA DURUMU notu).
    """
    kontrol = "openems_fdtd_simulasyonu"
    if not openems_kurulu_mu():
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                "openEMS/CSXCAD Python paketleri kurulu değil — simülasyon "
                "KOŞULMADI. Tahmini/varsayılan S-parametre ÜRETİLMEDİ."
            ),
        )

    from CSXCAD import ContinuousStructure
    from openEMS import openEMS as OpenEMSCozucu

    tum_izler = geometri.iz_segmentleri_pozitif + geometri.iz_segmentleri_negatif
    if not tum_izler:
        return bulgu_uret(
            kontrol, taranan=0, detay="geometri.iz_segmentleri boş — mesh kurulacak bir şey yok (KAPSAM_YOK).",
        )

    xs = [c for iz in tum_izler for c in (iz["baslangic_mm"][0], iz["bitis_mm"][0])]
    ys = [c for iz in tum_izler for c in (iz["baslangic_mm"][1], iz["bitis_mm"][1])]
    x_min, x_max = min(xs) - 2.0, max(xs) + 2.0  # 2mm hava boşluğu payı
    y_min, y_max = min(ys) - 2.0, max(ys) + 2.0

    f_baslangic_hz = frekans_araligi_ghz[0] * 1e9
    f_bitis_hz = frekans_araligi_ghz[1] * 1e9
    f0_hz = (f_baslangic_hz + f_bitis_hz) / 2.0
    fc_hz = (f_bitis_hz - f_baslangic_hz) / 2.0
    adim_mm = _MESH_ADIM_MM[mesh_cozunurlugu]

    FDTD = OpenEMSCozucu(NrTS=30000, EndCriteria=1e-4)
    FDTD.SetGaussExcite(f0_hz, fc_hz)
    FDTD.SetBoundaryCond(["PML_8"] * 6)

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(1e-3)  # birim: mm

    import numpy as np
    mesh.AddLine("x", list(np.arange(x_min, x_max + adim_mm, adim_mm)))
    mesh.AddLine("y", list(np.arange(y_min, y_max + adim_mm, adim_mm)))
    z0 = geometri.referans_duzlem_z_mm
    mesh.AddLine("z", [z0 - 1.0, z0, z0 + substrat_kalinligi_mm, z0 + substrat_kalinligi_mm + 1.0])

    # GND referans düzlemi
    gnd = CSX.AddMetal("GND")
    gnd.AddBox([x_min, y_min, z0], [x_max, y_max, z0])

    # sinyal izleri (P+/P-) — substrat üstünde, iz genişliği/başlangıç-bitiş
    # koordinatları GERÇEK board'dan geldi (`geometri_cikar` üzerinden).
    # DÜZELTME: eskiden burada `AddBox(min/max)` ile eksen-hizalı bir
    # bounding-box kullanılıyordu — bu, DİYAGONAL (45°) izlerde gerçek
    # genişlikten ÇOK DAHA GENİŞ bir iletken üretir (bir 45° izin bbox'ı,
    # iz genişliğinin ~1.4 katı yan uzunluğa sahiptir). Artık `openems_3d_
    # extractor.py::csxcad_kutu_olustur()` ÇAĞRILIYOR — izin YÖNÜNE DİK
    # ofsetle GERÇEK dikdörtgen kesiti üretir, açıdan BAĞIMSIZ doğru sonuç
    # verir (bkz. o fonksiyonun kendi DOĞRULAMA DURUMU notu).
    from openems_3d_extractor import csxcad_kutu_olustur

    sinyal = CSX.AddMetal("SINYAL")
    z_ust = z0 + substrat_kalinligi_mm
    for iz in tum_izler:
        csxcad_kutu_olustur(sinyal, {"baslangic": iz["baslangic_mm"], "bitis": iz["bitis_mm"],
                                       "genislik_mm": iz["genislik_mm"]}, z_ust)

    # --- Diferansiyel LUMPED PORT + excitation ---
    # openEMS'in resmi tek-uçlu S-parametre tutoriallerinde (ör.
    # MSL_NotchFilter.py) kullanılan `s11 = port[0].uf_ref/port[0].uf_inc`,
    # `s21 = port[1].uf_ref/port[0].uf_inc` deseninin DİFERANSİYEL 4-portlu
    # hale genişletilmiş biçimi: yakın uçta P (port 1, excite=+1) ve N
    # (port 2, excite=-1) EŞZAMANLI ZIT işaretle sürülür (bu, ortak-modu
    # BASTIRIR — ayrı bir ortak-mod koşumuna gerek KALMAZ, doğrudan
    # diferansiyel Sdd11/Sdd21 elde edilir). Uzak uçta P (port 3) ve N
    # (port 4) PASİF/eşleşmiş yük portlarıdır. TÜM portlar sinyal izinden
    # (z_ust) GND düzlemine (z0) DİKEY ('z') yönde tanımlanır, empedansı
    # `hedef_empedans_ohm/2` (diferansiyel hattı iki tek-uçlu lumped
    # port'un TOPLAMI olarak sürmenin standart yaklaşımı).
    #
    # DOĞRULANMADI (bkz. dosya başlığı): `AddLumpedPort` imzası
    # (`port_nr, R, start, stop, direction, excite`), dönen port
    # nesnesinin `.CalcPort()`/`.uf_inc`/`.uf_ref` arayüzü openEMS'in
    # resmi Python örneklerine dayanır — bu makinede openEMS kurulu
    # OLMADIĞI için TEK BİR KEZ BİLE çalıştırılamadı. Kurulu bir sürümde
    # API farklıysa (sürüm farkları `CalcPort` imzasını değiştirebilir)
    # burası güncellenmeli.
    #
    # SINIR: yakın/uzak uç, her iletkenin kendi x_min/x_max'ına göre
    # belirlenir — çiftin ANA güzergah yönünün x ekseni olduğu varsayılır
    # (tipik escape/breakout rotası için makul; keskin 90° dönüşlü bir
    # güzergahta YANLIŞ port yerleşimi üretebilir, elle gözden geçir).
    poz = geometri.iz_segmentleri_pozitif
    neg = geometri.iz_segmentleri_negatif
    if not poz or not neg:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                "geometri.iz_segmentleri_pozitif veya _negatif boş — "
                "diferansiyel port için HER İKİ iletken de gerekli (KAPSAM_YOK)."
            ),
        )

    def _y_ortalama(izler):
        ys = [c for iz in izler for c in (iz["baslangic_mm"][1], iz["bitis_mm"][1])]
        return sum(ys) / len(ys)

    def _x_araligi(izler):
        xs = [c for iz in izler for c in (iz["baslangic_mm"][0], iz["bitis_mm"][0])]
        return min(xs), max(xs)

    poz_y, neg_y = _y_ortalama(poz), _y_ortalama(neg)
    poz_x_min, poz_x_max = _x_araligi(poz)
    neg_x_min, neg_x_max = _x_araligi(neg)
    port_genislik_mm = max((iz["genislik_mm"] for iz in tum_izler), default=0.2)
    yw = port_genislik_mm / 2.0
    z_alt, z_ust_port = z0, z_ust + bakir_kalinligi_mm
    tek_uclu_port_ohm = hedef_empedans_ohm / 2.0

    portlar = [
        FDTD.AddLumpedPort(1, tek_uclu_port_ohm,
                            [poz_x_min, poz_y - yw, z_alt], [poz_x_min, poz_y + yw, z_ust_port],
                            "z", excite=1),
        FDTD.AddLumpedPort(2, tek_uclu_port_ohm,
                            [neg_x_min, neg_y - yw, z_alt], [neg_x_min, neg_y + yw, z_ust_port],
                            "z", excite=-1),
        FDTD.AddLumpedPort(3, tek_uclu_port_ohm,
                            [poz_x_max, poz_y - yw, z_alt], [poz_x_max, poz_y + yw, z_ust_port],
                            "z"),
        FDTD.AddLumpedPort(4, tek_uclu_port_ohm,
                            [neg_x_max, neg_y - yw, z_alt], [neg_x_max, neg_y + yw, z_ust_port],
                            "z"),
    ]

    calisma_dir = Path(calisma_dizini)
    calisma_dir.mkdir(parents=True, exist_ok=True)
    FDTD.Run(str(calisma_dir), cleanup=True)

    f = np.linspace(f_baslangic_hz, f_bitis_hz, 401)
    for port in portlar:
        port.CalcPort(str(calisma_dir), f)

    # Sdd11: yakın uç diferansiyel yansıması; Sdd21: uzak uca diferansiyel
    # iletim — port[0] (P, excite=+1) TEK kaynak sayılır (port[1] zıt
    # işaretle AYNI dalgayı taşır, ayrı bir referans GEREKMEZ).
    sdd11 = portlar[0].uf_ref / portlar[0].uf_inc
    sdd21 = portlar[2].uf_ref / portlar[0].uf_inc

    s2p_yolu = calisma_dir / "sonuc_diferansiyel.s2p"
    yazildi_mi = False
    try:
        import skrf as rf

        s = np.zeros((len(f), 2, 2), dtype=complex)
        s[:, 0, 0] = sdd11
        s[:, 1, 0] = sdd21
        s[:, 0, 1] = sdd21  # karşılıklı (reciprocal) hat varsayımı
        s[:, 1, 1] = sdd11  # simetrik diferansiyel hat varsayımı
        agi = rf.Network(f=f, s=s, z0=hedef_empedans_ohm, f_unit="Hz")
        agi.write_touchstone(str(s2p_yolu))
        yazildi_mi = True
    except ImportError:
        pass

    return bulgu_uret(
        kontrol, taranan=1, detay=(
            f"FDTD koşumu TAMAMLANDI (mesh={mesh_cozunurlugu}, port_ohm={tek_uclu_port_ohm}). "
            f"Sdd11(f0)={abs(sdd11[len(f)//2]):.4f}, Sdd21(f0)={abs(sdd21[len(f)//2]):.4f}. "
            + (f"Sonuç: {s2p_yolu}." if yazildi_mi else "skrf kurulu değil — .s2p YAZILMADI, sadece ham dizi hesaplandı.")
            + " UYARI: bu koşum zinciri bu makinede DOĞRULANAMADI (bkz. dosya başlığı)."
        ),
    )


# --------------------------------------------------------------------------
# Sonuç değerlendirme
# --------------------------------------------------------------------------

def s_parametre_degerlendir(
    s4p_yolu: str,
    hedef_empedans_ohm: float,
    min_return_loss_db: float = -10.0,
) -> Bulgu:
    """Touchstone (`.s4p`) dosyasını `skrf` ile okuyup TEK UÇLU (single-
    ended) dönüş kaybını (`Sii`, her port kendi başına) değerlendirir.

    Dosya YOKSA bu FAIL'dir (simülasyon koştu ama sonuç üretemedi),
    KAPSAM_YOK DEĞİL — KAPSAM_YOK sadece `skrf`/openEMS hiç kurulu
    olmadığında kullanılır.

    SINIR (bilerek): bu fonksiyon DİFERANSİYEL (`Sdd11`/`Sdd21`, mixed-mode)
    sonucu HESAPLAMAZ — `skrf.Network.se2gmm()`'in port-eşleştirme kuralı
    (hangi fiziksel port çiftinin hangi mod indeksine karşılık geldiği)
    bu ortamda `skrf` kurulu olmadığı için TEYİT EDİLEMEDİ; yanlış tahmin
    edilip "Sdd11" diye YANLIŞ bir sayı raporlamak, hiç rapor etmemekten
    DAHA KÖTÜ olurdu (dosya başlığındaki sayı uydurma yasağı). Bu yüzden
    sadece tek-uçlu `Sii` (her fiziksel port kendi dönüş kaybı) raporlanır
    — diferansiyel analiz için `skrf` kurulu bir makinede
    `agi.se2gmm(p=...)`'in port sırası resmi örnekle DOĞRULANARAK bu
    fonksiyona eklenmelidir.
    """
    kontrol = "s_parametre_degerlendirme"
    yol = Path(s4p_yolu)
    if not yol.exists():
        return bulgu_uret(
            kontrol, taranan=1,
            ihlaller=[{"sebep": "sonuç dosyası bulunamadı", "beklenen_yol": str(yol)}],
            detay="Simülasyon koştu ama .s4p üretilmedi — bu FAIL, KAPSAM_YOK değil.",
        )

    try:
        import skrf as rf
    except ImportError:
        return bulgu_uret(
            kontrol, taranan=0, detay="skrf kütüphanesi kurulu değil — değerlendirme KOŞULMADI.",
        )

    agi = rf.Network(str(yol))
    taranan = 0
    ihlaller: List[dict] = []
    for port_no in range(agi.nports):
        taranan += 1
        sii_db = agi.s_db[:, port_no, port_no]
        maks_sii_db = float(sii_db.max())
        if maks_sii_db > min_return_loss_db:
            ihlaller.append({
                "port": port_no + 1,
                "maks_return_loss_db": round(maks_sii_db, 3),
                "sinir_db": min_return_loss_db,
                "sorun": "tek_uclu_donus_kaybi_asimi",
            })

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"{agi.nports}-portlu ağ, TEK UÇLU Sii değerlendirildi (Sdd DEĞİL — "
        f"bkz. fonksiyon notu). hedef_empedans_ohm={hedef_empedans_ohm} "
        f"(port referans empedansı touchstone dosyasında {agi.z0[0].real if hasattr(agi, 'z0') else '?'} "
        "olarak tanımlı olmalı, burada AYRICA doğrulanmadı).",
    )


# --------------------------------------------------------------------------
# Akım yoğunluğu haritası — akim_yogunlugu_haritasi.py'ye YÖNLENDİRİR
# --------------------------------------------------------------------------

def akim_yogunlugu_haritasi_uret(
    pcb_yolu: str, net_adi: str, akim_a: float, calisma_dizini: str,
) -> Bulgu:
    """EM DEĞİL — resistive mesh (DC IR-drop'un geometriye yayılmış hali).
    openEMS'e bağımlı DEĞİLDİR, her zaman çalışabilir. Gerçek hesap/çözücü
    `akim_yogunlugu_haritasi.py`'de YAŞAR (ayrı dosya — bu köprünün
    `fdtd_kur_ve_calistir`/`s_parametre_degerlendir`'i openEMS'e bağımlıyken
    bu fonksiyon BAĞIMLI DEĞİL; iki farklı bağımlılık profilini AYNI
    dosyada karıştırmamak için ayrı tutuldu). Bu fonksiyon sadece ince bir
    yönlendirme sarmalayıcısıdır — `openems_koprusu` API'siyle çağıranlar
    için (ör. `main.py`) tek noktadan erişim sağlar."""
    from akim_yogunlugu_haritasi import akim_yogunlugu_haritasi_uret as _gercek_uygulama

    return _gercek_uygulama(pcb_yolu, net_adi, akim_a, calisma_dizini)
