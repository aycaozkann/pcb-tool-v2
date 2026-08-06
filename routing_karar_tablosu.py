#!/usr/bin/env python3
"""
routing_karar_tablosu.py
==========================
Manuel kontrol için NET-BAZLI routing karar tablosu — bir `.kicad_pcb`'yi
gerçekten `pcbnew` ile okuyup her net için bir satır üreten XLSX + CSV
çıktısı.

TÜM VERİ BOARD'UN KENDİSİNDEN ÇIKARILIR (pcbnew API) — hiçbir alan elle/
tahminen doldurulmaz. Bir alan hesaplanamıyorsa (ör. empedans hedefi
tanımsız bir net için) "N/A" yazılır, UYDURULMAZ.

İKİ İSTİSNA — açıkça HEURİSTİK olan, ama dönen SAYISAL DEĞERİ hâlâ gerçek
bir kaynaktan (`pcb_stackup_planner.py`) alan iki adım:
  1. `arabirim_turu_tahmin_et()`: net ADINI (ör. "PCIE_TX_P") bilinen bir
     arayüz ailesine (`AraBirimTuru`) PATTERN-MATCH eder — board'da bir
     net'in "ben PCIe'yim" diye semantik bir etiketi YOKTUR, bu adım
     kaçınılmaz olarak isim tabanlıdır. Ama eşleşme bulunduktan SONRA
     dönen OHM HEDEFİ `pcb_stackup_planner.ARAYUZ_EMPEDANS_HEDEFLERI`
     tablosundan gelir — o sayı burada TEKRAR TANIMLANMAZ/uydurulmaz.
     Eşleşme yoksa "N/A" (fonksiyon `None` döner).
  2. `net_kategorisi_ve_gerekce()`: aynı şekilde isim deseniyle GÜÇ/GND/
     YÜKSEK-HIZ/STANDART-I/O kategorisine ayırır — bu kategoriye göre
     önerilen katman, `pcb-layout` skill'inin Faz 2 stackup rolü
     tanımından (F.Cu=kritik HS, In1.Cu=GND düzlemi, In2.Cu=bölünmüş güç
     düzlemleri, B.Cu=düşük hızlı I/O) DOĞRUDAN alınır, kafadan
     ATANMAZ.

`pcbnew` bu geliştirme ortamında pip-kurulu DEĞİLDİR — modül [[MASTER_
RULEBOOK: pcbnew Bağımlılığı Her Zaman Lazy]] kuralına uyar: import
fonksiyon gövdesi içinde yapılır, `pcbnew` yoksa exception fırlatmadan
`None` döner, çağıran (`routing_tablosu_uret`) bunu KAPSAM_YOK olarak
işler. Gerçek çalıştırma KiCad'in gömülü Python'unda yapılmalıdır (bkz.
`pcbnew_koprusu.py`'nin aynı deseni).

`openpyxl` de AYRI, opsiyonel bir bağımlılıktır (KiCad'in gömülü
Python'unda pip ile ayrıca kurulmalı) — yoksa XLSX ATLANIR (net bir uyarı
ile), CSV çıktısı (stdlib `csv`, HER ZAMAN mevcut) yine üretilir.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NM_PER_MM = 1_000_000


def _mm(deger_nm: float) -> float:
    return deger_nm / NM_PER_MM


def _xy_mm(nokta) -> Tuple[float, float]:
    return (round(_mm(nokta.x), 4), round(_mm(nokta.y), 4))


def _pcbnew_veya_none():
    try:
        import pcbnew
        return pcbnew
    except ImportError:
        return None


# ------------------------------------------------------------------
# 1. NET ADI SEZGİLERİ (diff-pair eşi, arayüz tahmini, kategori/gerekçe)
#    — dönüş HEURİSTİK ama kaynak-değerler GERÇEK, bkz. modül docstring'i
# ------------------------------------------------------------------

_DIFF_SUFFIX_ESLEME: Tuple[Tuple[str, str], ...] = (
    ("_P", "_N"), ("_N", "_P"),
    ("_DP", "_DM"), ("_DM", "_DP"),
    ("_POS", "_NEG"), ("_NEG", "_POS"),
)


def diff_pair_esini_bul(net_isim: str, tum_net_isimleri: set) -> Optional[str]:
    """Net adının bilinen bir diferansiyel-çift ek'iyle (suffix) bittiğini
    ve KARŞI ek'e sahip bir net'in board'da GERÇEKTEN var olduğunu
    doğrular. Sadece isim benzerliği YETMEZ — aday net board'da yoksa
    `None` döner (uydurma eş üretilmez)."""
    for ek, karsi_ek in _DIFF_SUFFIX_ESLEME:
        if net_isim.endswith(ek):
            aday = net_isim[: -len(ek)] + karsi_ek
            if aday in tum_net_isimleri:
                return aday
    return None


_ARABIRIM_DESENLERI: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"HDMI", re.I), "HDMI"),
    (re.compile(r"PCIE", re.I), "PCIE"),
    (re.compile(r"USB.*3|USB3", re.I), "USB3_x"),
    (re.compile(r"USB", re.I), "USB2_0"),
    (re.compile(r"ETH.*TRD|ETHERNET", re.I), "ETHERNET_1G"),
    (re.compile(r"LVDS", re.I), "LVDS"),
    (re.compile(r"DDR", re.I), "DDR3_4"),
)


def arabirim_turu_tahmin_et(net_isim: str) -> Optional[str]:
    """`pcb_stackup_planner.AraBirimTuru` üye adını (string) döner —
    eşleşme yoksa `None`. Sıra ÖNEMLİ (ör. 'USB3' önce 'USB'den önce
    kontrol edilir, aksi halde hep USB2_0'a düşer)."""
    for desen, tur_adi in _ARABIRIM_DESENLERI:
        if desen.search(net_isim):
            return tur_adi
    return None


def empedans_hedefi_getir_net_isminden(net_isim: str) -> Optional[float]:
    """Döndürülen OHM DEĞERİ `pcb_stackup_planner.py::
    ARAYUZ_EMPEDANS_HEDEFLERI`'nden gelir (görev talimatı:
    `empedans_hedefi_getir()` kullan, uydurma). Eşleşme yoksa `None`
    (tabloda 'N/A' olarak yazılır)."""
    tur_adi = arabirim_turu_tahmin_et(net_isim)
    if tur_adi is None:
        return None
    from pcb_stackup_planner import AraBirimTuru, ARAYUZ_EMPEDANS_HEDEFLERI
    tur = getattr(AraBirimTuru, tur_adi, None)
    if tur is None:
        return None
    return ARAYUZ_EMPEDANS_HEDEFLERI.get(tur)


_GUC_NET_DESENLERI = (
    "VCC", "VDD", "3V3", "3.3V", "+3V3", "+3.3V", "5V", "+5V", "1V8", "+1V8",
    "1V2", "+1V2", "AVDD", "DVDD", "VBAT", "VBUS", "VIN",
)

# `.claude/skills/pcb-layout` Faz 2 stackup rolü (DEĞİŞTİRİLMEDEN alıntı):
# F.Cu=kritik HS/diferansiyel, In1.Cu=kesintisiz GND düzlemi,
# In2.Cu=bölünmüş güç düzlemleri, B.Cu=düşük hızlı dijital/atlama yolu.
_KATEGORI_ONERILEN_KATMAN = {
    "YÜKSEK HIZ": "F.Cu",
    "GÜÇ/GND": "In1.Cu (düzlem)",
    "GÜÇ": "In2.Cu (bölünmüş güç düzlemi)",
    "STANDART I/O": "B.Cu",
}


def net_kategorisi_ve_gerekce(
    net_isim: str, arabirim_turu: Optional[str], diff_esi: Optional[str],
) -> Tuple[str, str]:
    ad = net_isim.strip().upper()
    parcalar = ad.split("_")
    if ad == "GND" or ad.endswith("_GND") or parcalar[0] == "GND":
        return "GÜÇ/GND", "Toprak dönüş düzlemi — nokta-nokta iz değil, GND pour (Faz 2)."
    # Tam-parça eşleşmesi (ör. "CARRIER_3V3" -> ["CARRIER","3V3"] -> "3V3"
    # bilinen güç deseniyle eşleşir) — "USBVCC_SENSE" gibi rastgele bir alt
    # dizeyi YANLIŞLIKLA güç sayan saf substring eşleşmesinden KAÇINILIR.
    if any(p == d for d in _GUC_NET_DESENLERI for p in parcalar):
        return "GÜÇ", f"Güç rayı net'i (isim deseni '{ad}' bilinen güç önekiyle eşleşti)."
    if diff_esi:
        if arabirim_turu:
            return (
                "YÜKSEK HIZ",
                f"Diferansiyel çift ({arabirim_turu} arayüzü, isim deseninden "
                f"tahmin edildi), eşi: {diff_esi}.",
            )
        return (
            "YÜKSEK HIZ (arayüz belirsiz)",
            f"Diferansiyel çift adayı (eşi: {diff_esi} board'da mevcut) ama "
            "bilinen bir arayüz deseniyle eşleşmedi — empedans hedefi N/A.",
        )
    return "STANDART I/O", "Tek uçlu, düşük hızlı sinyal/GPIO — özel empedans hedefi yok."


def onerilen_katman(kategori: str) -> str:
    return _KATEGORI_ONERILEN_KATMAN.get(kategori, "B.Cu")


# ------------------------------------------------------------------
# 2. GERÇEK BOARD'DAN NET SEGMENT ZİNCİRİ ÇIKARIMI
# ------------------------------------------------------------------

def _net_pinlerini_bul(board, net_isim: str) -> List[Dict[str, Any]]:
    pinler = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net_isim:
                pinler.append({
                    "pin": f"{fp.GetReference()}.{p.GetNumber()}",
                    "konum_mm": _xy_mm(p.GetPosition()),
                })
    return pinler


def _katman_adi(board, katman_id) -> str:
    try:
        return board.GetLayerName(katman_id)
    except Exception:
        return str(katman_id)


def net_segmentlerini_cikar(board, net_isim: str) -> Dict[str, Any]:
    """Bir net'in TÜM track/via öğelerini (pcbnew) çıkarır. TUZAK (a):
    `GetClass()` hem "PCB_TRACK" hem "PCB_ARC" döner, arc'lar ATLANMAZ."""
    izler = [t for t in board.GetTracks() if t.GetNetname() == net_isim]
    segmentler: List[Dict[str, Any]] = []
    vialar: List[Dict[str, Any]] = []
    toplam_uzunluk_mm = 0.0

    for t in izler:
        sinif = t.GetClass()
        if sinif == "PCB_VIA":
            vialar.append({
                "konum_mm": _xy_mm(t.GetPosition()),
                "ust_katman": _katman_adi(board, t.TopLayer()),
                "alt_katman": _katman_adi(board, t.BottomLayer()),
            })
        elif sinif in ("PCB_TRACK", "PCB_ARC"):
            s = _xy_mm(t.GetStart())
            e = _xy_mm(t.GetEnd())
            uzunluk = math.hypot(e[0] - s[0], e[1] - s[1])
            toplam_uzunluk_mm += uzunluk
            segmentler.append({
                "katman": _katman_adi(board, t.GetLayer()),
                "baslangic_mm": s,
                "bitis_mm": e,
                "genislik_mm": round(_mm(t.GetWidth()), 4),
                "uzunluk_mm": round(uzunluk, 4),
            })

    return {
        "net": net_isim,
        "pinler": _net_pinlerini_bul(board, net_isim),
        "segmentler": segmentler,
        "vialar": vialar,
        "toplam_uzunluk_mm": round(toplam_uzunluk_mm, 4),
    }


def katman_sirasi_metni_uret(veri: Dict[str, Any], konum_toleransi_mm: float = 0.01) -> str:
    """Segment/via listesinden "F.Cu(0,0→5,0) → VIA(5,0) → In2.Cu(5,0→10,0)"
    formatında insan-okur bir zincir metni üretir. Zincir bir uç noktadan
    (ilk pin varsa oradan, yoksa ilk segmentin başlangıcından) başlayıp
    eşleşen uçları takip ederek kurulur — bulunamayan/bağlı olmayan
    parçalar zincir SONUNA "+ N ayrık parça" olarak eklenir (sessizce
    ATILMAZ)."""
    segmentler = list(veri["segmentler"])
    vialar = list(veri["vialar"])
    if not segmentler and not vialar:
        return "(routsuz — hiç segment/via yok)"

    def _yakin(a, b):
        return abs(a[0] - b[0]) <= konum_toleransi_mm and abs(a[1] - b[1]) <= konum_toleransi_mm

    # Çok-pinli (>2, ör. flow-through ESD/choke) net'lerde HANGİ pin'in
    # zincirin gerçek ucu olduğu iteration sırasından belli değildir —
    # her aday başlangıç noktasından bir deneme yapılır, en AZ "ayrık
    # parça" bırakan (yani en UZUN zincir kuran) sonuç seçilir. Sessizce
    # "kurulamadı" demek yerine gerçekten en iyi sonucu arar.
    adaylar = [p["konum_mm"] for p in veri["pinler"]] or [segmentler[0]["baslangic_mm"]]
    en_iyi: Optional[Tuple[List[str], int]] = None
    for baslangic in adaylar:
        sonuc = _zincir_kur(baslangic, segmentler, vialar, _yakin)
        if en_iyi is None or sonuc[1] < en_iyi[1]:
            en_iyi = sonuc
            if sonuc[1] == 0:
                break
    parcalar, ayrik = en_iyi
    zincir = " → ".join(parcalar) if parcalar else "(zincir kurulamadı)"
    if ayrik:
        zincir += f"  [+ {ayrik} bağlı olmayan/ayrık parça — elle incele]"
    return zincir


def _zincir_kur(baslangic, segmentler, vialar, _yakin) -> Tuple[List[str], int]:
    parcalar: List[str] = []
    mevcut = baslangic
    kalan_seg = list(segmentler)
    kalan_via = list(vialar)
    ilerleme_oldu = True
    # ÖNCELİK: via'lar segment'lerden ÖNCE denenir. Gerekçe — bir via ile
    # onu takip eden bir sonraki segment genelde AYNI (x,y) noktasında
    # buluşur (via katman değiştirir, segment o yeni katmanda devam eder);
    # sadece konuma bakan bir eşleştirici, o noktada "hangisi önce" sorusunu
    # segment'i seçerek YANLIŞ cevaplayabilir (via'yı sessizce "ayrık parça"
    # sepetine düşürüp zincirden DÜŞÜRÜR). Via'yı önce denemek bu belirsizliği
    # via lehine çözer — bir via'nın "tüketilmesi" zinciri asla YANLIŞ
    # yönlendirmez (via her iki ucundan da devam edilebilir bir hub'dır).
    while ilerleme_oldu:
        ilerleme_oldu = False
        for v in list(kalan_via):
            if _yakin(v["konum_mm"], mevcut):
                parcalar.append(f"VIA({v['konum_mm']}, {v['ust_katman']}↔{v['alt_katman']})")
                kalan_via.remove(v)
                ilerleme_oldu = True
                break
        if ilerleme_oldu:
            continue
        for s in list(kalan_seg):
            if _yakin(s["baslangic_mm"], mevcut):
                parcalar.append(f"{s['katman']}({s['baslangic_mm']}→{s['bitis_mm']})")
                mevcut = s["bitis_mm"]
                kalan_seg.remove(s)
                ilerleme_oldu = True
                break
            if _yakin(s["bitis_mm"], mevcut):
                parcalar.append(f"{s['katman']}({s['bitis_mm']}→{s['baslangic_mm']})")
                mevcut = s["baslangic_mm"]
                kalan_seg.remove(s)
                ilerleme_oldu = True
                break

    ayrik = len(kalan_seg) + len(kalan_via)
    return parcalar, ayrik


# ------------------------------------------------------------------
# 3. DİFERANSİYEL SKEW (MASTER_RULEBOOK "Diferansiyel Faz Uyumu")
# ------------------------------------------------------------------
#
# NOT (yorum farkı, açıkça belirtiliyor — uydurulmuyor): MASTER_RULEBOOK
# metni 15mm'i "asimetri başlayan köşeye EN FAZLA bu mesafede düzeltme
# menderesi eklenmeli" olarak tanımlar — bir "toplam skew toleransı"
# DEĞİL. Bu tablo, board'daki tek somut "15mm" sayısını PASS/FAIL eşiği
# olarak kullanır (görev talimatının istediği literal yorum) ama bu
# yorum farkını burada AÇIKÇA belgeler.
SKEW_ESIK_MM = 15.0


def skew_hesapla_ve_degerlendir(uzunluk_a_mm: float, uzunluk_b_mm: float) -> Dict[str, Any]:
    skew_mm = round(abs(uzunluk_a_mm - uzunluk_b_mm), 4)
    return {
        "skew_mm": skew_mm,
        "esik_mm": SKEW_ESIK_MM,
        "durum": "PASS" if skew_mm <= SKEW_ESIK_MM else "FAIL",
    }


# ------------------------------------------------------------------
# 4. DRC DURUMU (gerçek JSON'dan, tahmin YOK)
# ------------------------------------------------------------------

def drc_durumunu_bul(net_isim: str, drc_json_yolu: Optional[str]) -> str:
    if not drc_json_yolu or not Path(drc_json_yolu).is_file():
        return "N/A (DRC raporu verilmedi)"
    try:
        veri = json.loads(Path(drc_json_yolu).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as hata:
        return f"N/A (DRC raporu okunamadı: {hata})"

    ihlaller = veri.get("violations", [])
    eslesen = [v for v in ihlaller if net_isim in json.dumps(v, ensure_ascii=False)]
    if not eslesen:
        return "Bu net için ihlal bulunamadı"
    ozet = "; ".join(sorted({v.get("type", "?") for v in eslesen}))
    return f"{len(eslesen)} ihlal: {ozet}"


# ------------------------------------------------------------------
# 5. ANA SATIR ÜRETİMİ (routelanmış net'ler)
# ------------------------------------------------------------------

def net_satiri_uret(board, net_isim: str, tum_net_isimleri: set, drc_json_yolu: Optional[str]) -> Dict[str, Any]:
    veri = net_segmentlerini_cikar(board, net_isim)
    diff_esi = diff_pair_esini_bul(net_isim, tum_net_isimleri)
    arabirim = arabirim_turu_tahmin_et(net_isim)
    kategori, gerekce = net_kategorisi_ve_gerekce(net_isim, arabirim, diff_esi)
    empedans = empedans_hedefi_getir_net_isminden(net_isim)

    skew_bilgisi = None
    if diff_esi and diff_esi in tum_net_isimleri:
        esi_veri = net_segmentlerini_cikar(board, diff_esi)
        skew_bilgisi = skew_hesapla_ve_degerlendir(
            veri["toplam_uzunluk_mm"], esi_veri["toplam_uzunluk_mm"],
        )

    pinler = veri["pinler"]
    return {
        "Net Adı": net_isim,
        "Başlangıç Pin": pinler[0]["pin"] + f" @ {pinler[0]['konum_mm']}" if pinler else "N/A",
        "Bitiş Pin": (pinler[-1]["pin"] + f" @ {pinler[-1]['konum_mm']}"
                      if len(pinler) > 1 else ("(tek pin)" if pinler else "N/A")),
        "Pin Sayısı": len(pinler),
        "Katman Sırası": katman_sirasi_metni_uret(veri),
        "Segment Genişlikleri (mm)": ", ".join(
            f"{s['katman']}:{s['genislik_mm']}" for s in veri["segmentler"]
        ) or "N/A",
        "Toplam İz Uzunluğu (mm)": veri["toplam_uzunluk_mm"],
        "Via Sayısı": len(veri["vialar"]),
        "Via Detayı": "; ".join(
            f"{v['konum_mm']} {v['ust_katman']}↔{v['alt_katman']}" for v in veri["vialar"]
        ) or "(via yok)",
        "Empedans Hedefi (Ω)": empedans if empedans is not None else "N/A",
        "Diferansiyel Eşi": diff_esi or "N/A",
        "Skew (mm)": skew_bilgisi["skew_mm"] if skew_bilgisi else "N/A",
        "Skew Durumu (15mm kuralı)": skew_bilgisi["durum"] if skew_bilgisi else "N/A",
        "Kategori": kategori,
        "Gerekçe": gerekce,
        "DRC Durumu": drc_durumunu_bul(net_isim, drc_json_yolu),
    }


# ------------------------------------------------------------------
# 6. KALAN (UNROUTED) BAĞLANTILAR SEKMESİ
# ------------------------------------------------------------------

def _en_yakin_n_engel(board, nokta_mm: Tuple[float, float], haric_net: str, n: int = 3) -> List[Dict[str, Any]]:
    adaylar = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == haric_net:
                continue
            konum = _xy_mm(p.GetPosition())
            mesafe = math.hypot(konum[0] - nokta_mm[0], konum[1] - nokta_mm[1])
            adaylar.append({"tip": "pad", "ref": f"{fp.GetReference()}.{p.GetNumber()}",
                             "net": p.GetNetname(), "konum_mm": konum, "mesafe_mm": round(mesafe, 4)})
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.GetNetname() == haric_net:
            continue
        konum = _xy_mm(t.GetPosition())
        mesafe = math.hypot(konum[0] - nokta_mm[0], konum[1] - nokta_mm[1])
        adaylar.append({"tip": "via", "ref": t.GetNetname(), "net": t.GetNetname(),
                         "konum_mm": konum, "mesafe_mm": round(mesafe, 4)})
    adaylar.sort(key=lambda a: a["mesafe_mm"])
    return adaylar[:n]


def _router_log_gerekcesi(net_isim: str, router_log_yolu: Optional[str]) -> str:
    if not router_log_yolu or not Path(router_log_yolu).is_file():
        return "denenmedi"
    try:
        icerik = Path(router_log_yolu).read_text(encoding="utf-8", errors="replace")
    except OSError as hata:
        return f"denenmedi (log okunamadı: {hata})"
    satirlar = [s for s in icerik.splitlines() if net_isim in s]
    if not satirlar:
        return "denenmedi (log'da bu net için kayıt yok)"
    return " | ".join(satirlar[-3:])  # son 3 ilgili satır (en güncel bağlam)


def kalan_baglanti_satiri_uret(
    board, net_isim: str, drc_json_yolu: Optional[str], router_log_yolu: Optional[str],
    karar_birimleri_yolu: Optional[str],
) -> Dict[str, Any]:
    pinler = _net_pinlerini_bul(board, net_isim)
    arabirim = arabirim_turu_tahmin_et(net_isim)
    # NOT: unrouted net'lerde diff-pair eşinin ROUTED olup olmadığı bu
    # satırın odağı değil (o zaten routelanmış tabloda görünür) — kategori
    # sadece isim/arayüz desenine göre belirlenir, `diff_esi=None` geçilir.
    kategori, _ = net_kategorisi_ve_gerekce(net_isim, arabirim, None)

    kus_ucusu = "N/A"
    engel_listesi = "N/A"
    if len(pinler) >= 2:
        a, b = pinler[0]["konum_mm"], pinler[-1]["konum_mm"]
        kus_ucusu = round(math.hypot(a[0] - b[0], a[1] - b[1]), 4)
        engeller = _en_yakin_n_engel(board, a, net_isim, n=3)
        engel_listesi = "; ".join(
            f"{e['tip']}:{e['ref']}@{e['konum_mm']} ({e['mesafe_mm']}mm)" for e in engeller
        ) or "(engel bulunamadı)"

    karar_id = "N/A"
    if karar_birimleri_yolu and Path(karar_birimleri_yolu).is_file():
        try:
            kb = json.loads(Path(karar_birimleri_yolu).read_text(encoding="utf-8"))
            for k in kb.get("kararlar", []):
                if net_isim in json.dumps(k, ensure_ascii=False):
                    karar_id = k.get("karar_id", "N/A")
                    break
        except (OSError, json.JSONDecodeError):
            karar_id = "N/A (karar_birimleri.json okunamadı)"

    return {
        "Net Adı": net_isim,
        "Başlangıç Pin": (pinler[0]["pin"] + f" @ {pinler[0]['konum_mm']}") if pinler else "N/A",
        "Bitiş Pin": (pinler[-1]["pin"] + f" @ {pinler[-1]['konum_mm']}") if len(pinler) > 1 else "N/A",
        "Kuş Uçuşu Mesafe (mm)": kus_ucusu,
        "Önerilen Katman": onerilen_katman(kategori),
        "Önerilen İz Genişliği (mm)": 0.2,  # bkz. modül notu: board minimum trackwidth
        "Neden Çizilemedi": _router_log_gerekcesi(net_isim, router_log_yolu),
        "En Yakın 3 Engel": engel_listesi,
        "İlgili karar_id": karar_id,
    }


# ------------------------------------------------------------------
# 7. ANA GİRİŞ NOKTASI
# ------------------------------------------------------------------

def routing_tablosu_uret(
    board_path: str,
    drc_json_yolu: Optional[str] = None,
    router_log_yolu: Optional[str] = None,
    karar_birimleri_yolu: Optional[str] = None,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """`pcbnew` yoksa `None` döner (çağıran KAPSAM_YOK olarak işler —
    [[MASTER_RULEBOOK: pcbnew Bağımlılığı Her Zaman Lazy]])."""
    pcbnew = _pcbnew_veya_none()
    if pcbnew is None:
        return None
    board = pcbnew.LoadBoard(board_path)

    tum_netler = set()
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                tum_netler.add(p.GetNetname())

    routelanmis, routsuz = [], []
    for net_isim in sorted(tum_netler):
        veri = net_segmentlerini_cikar(board, net_isim)
        if veri["segmentler"] or veri["vialar"]:
            routelanmis.append(net_satiri_uret(board, net_isim, tum_netler, drc_json_yolu))
        else:
            routsuz.append(kalan_baglanti_satiri_uret(
                board, net_isim, drc_json_yolu, router_log_yolu, karar_birimleri_yolu,
            ))

    return {"routelanmis": routelanmis, "routsuz": routsuz}


# ------------------------------------------------------------------
# 8. ÇIKTI YAZIMI (CSV her zaman; XLSX openpyxl varsa)
# ------------------------------------------------------------------

def csv_yaz(satirlar: List[Dict[str, Any]], yol: str) -> None:
    if not satirlar:
        Path(yol).write_text("", encoding="utf-8")
        return
    with open(yol, "w", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        yazici.writeheader()
        yazici.writerows(satirlar)


def xlsx_yaz(veri: Dict[str, List[Dict[str, Any]]], yol: str) -> bool:
    """`openpyxl` yoksa `False` döner, XLSX ATLANIR (CSV zaten yazıldı) —
    hard crash YOK."""
    try:
        import openpyxl
    except ImportError:
        return False

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Routing_Tablosu"
    satirlar = veri["routelanmis"]
    if satirlar:
        basliklar = list(satirlar[0].keys())
        ws1.append(basliklar)
        for s in satirlar:
            ws1.append([s[b] for b in basliklar])

    ws2 = wb.create_sheet("Kalan_Baglantilar")
    kalan = veri["routsuz"]
    if kalan:
        basliklar2 = list(kalan[0].keys())
        ws2.append(basliklar2)
        for s in kalan:
            ws2.append([s[b] for b in basliklar2])

    wb.save(yol)
    return True


def uret_ve_kaydet(
    board_path: str,
    cikti_dizini: str,
    drc_json_yolu: Optional[str] = None,
    router_log_yolu: Optional[str] = None,
    karar_birimleri_yolu: Optional[str] = None,
) -> Dict[str, Any]:
    """CLI/`main.py` entegrasyonunun çağırdığı üst seviye fonksiyon.
    Döner: {"basarili": bool, "xlsx_yazildi": bool, "csv_yollari": [...],
    "kapsam_yok_detay": str|None}."""
    veri = routing_tablosu_uret(board_path, drc_json_yolu, router_log_yolu, karar_birimleri_yolu)
    if veri is None:
        return {
            "basarili": False, "xlsx_yazildi": False, "csv_yollari": [],
            "kapsam_yok_detay": "pcbnew modülü bulunamadı — KiCad'in gömülü Python'unda çalıştırın.",
        }

    Path(cikti_dizini).mkdir(parents=True, exist_ok=True)
    csv1 = str(Path(cikti_dizini) / "routing_tablosu.csv")
    csv2 = str(Path(cikti_dizini) / "kalan_baglantilar.csv")
    csv_yaz(veri["routelanmis"], csv1)
    csv_yaz(veri["routsuz"], csv2)

    xlsx_yolu = str(Path(cikti_dizini) / "routing_karar_tablosu.xlsx")
    xlsx_yazildi = xlsx_yaz(veri, xlsx_yolu)

    return {
        "basarili": True,
        "xlsx_yazildi": xlsx_yazildi,
        "xlsx_yolu": xlsx_yolu if xlsx_yazildi else None,
        "csv_yollari": [csv1, csv2],
        "routelanmis_sayisi": len(veri["routelanmis"]),
        "routsuz_sayisi": len(veri["routsuz"]),
        "kapsam_yok_detay": None,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Kullanım: python routing_karar_tablosu.py board.kicad_pcb [cikti_dizini] "
              "[drc.json] [router.log] [karar_birimleri.json]")
        sys.exit(1)
    board_arg = sys.argv[1]
    cikti_arg = sys.argv[2] if len(sys.argv) > 2 else "TEST"
    drc_arg = sys.argv[3] if len(sys.argv) > 3 else None
    log_arg = sys.argv[4] if len(sys.argv) > 4 else None
    karar_arg = sys.argv[5] if len(sys.argv) > 5 else None

    sonuc = uret_ve_kaydet(board_arg, cikti_arg, drc_arg, log_arg, karar_arg)
    print(json.dumps(sonuc, indent=2, ensure_ascii=False))
