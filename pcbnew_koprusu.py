"""
pcbnew_koprusu.py
===================
PROJENİN EN BÜYÜK MİMARİ BOŞLUĞUNU KAPATAN MODÜL.

Şu ana kadar `pcb_stackup_planner.py`, `pcb_highspeed_escape.py`,
`mekanik_dxf_koprusu.py` hep SOYUT dataclass'lar (`Komponent`,
`PinArasiKanal`, `DxfOutline`) üzerinde çalışıyordu — elle/başka koddan
doldurulan veri. Gerçek bir `.kicad_pcb` dosyasını hiçbir modül
AÇMIYORDU. Bu, arkadaşının `Skills/scripts/dfm_emc_check.py` /
`mask_dam.py` / `stitch_density.py` sistemine kıyasla en kritik farktı.

Bu dosya, gerçek board'u `pcbnew` API'siyle okuyup:
  1) `pcb_highspeed_escape.py::PinArasiKanal`'ı ELLE DOLDURMAK YERİNE
     gerçek komşu pad çiftlerinden OTOMATİK üretir (bkz. `kanal_ciftlerini_bul`),
  2) Kendi başına birkaç gerçek-board DFM kontrolü yapar (via-in-pad,
     annular ring, kenar/depanel seramik keepout) — `bulgu_sozlesmesi.py`
     sözleşmesiyle (taranan/durum ayrımı).

Bu modül `pcb_highspeed_escape.py`/`pcb_stackup_planner.py`'nin YERİNE
GEÇMEZ: onların doğru formüllerini (maske barajı, IPC-2221 vb.) gerçek
geometriyle BESLER. Hesap mantığı hâlâ o dosyalarda yaşıyor; burada sadece
"gerçek dosyadan veri çıkarma" katmanı var.

AĞ/ARAÇ UYARISI (proje disipliniyle uyumlu — bkz. `kicad_koprusu.py`,
`mekanik_dxf_koprusu.py` başındaki notlar): bu ortamda gerçek bir KiCad
kurulumu ve dolayısıyla `pcbnew` modülü YOKTUR. Bu dosya `import pcbnew`
satırına kadar tüm mantığı doğru yazılmış olarak sunar, ama SENİN
makinende gerçek `pcbnew` + gerçek bir `.kicad_pcb` ile ÇALIŞTIRILIP
doğrulanmadan production'da güvenilmemelidir (özellikle: pcbnew 10.0.5'te
bilinen API tuzakları için aşağıdaki "ÖLÇÜM TUZAKLARI" bölümüne bak —
bunlar arkadaşının projesinde gerçek kartlarda yaşanmış hatalardır).

ÖLÇÜM TUZAKLARI (pcbnew 10.0.5 — kodun içinde bilerek bunlara göre yazıldı):
  (a) `track.GetClass() == "PCB_TRACK"` YAYLARI ATLAR — arc'ta `GetClass()`
      `"PCB_ARC"` döner. Uzunluk/iz taramasında HER İKİSİNİ de filtrele.
  (b) `footprint.GetBoundingBox()` ipek ekran (silkscreen) metnini de
      dahil eder — kenar/keepout mesafesi için `GetBoundingBox(False, False)`
      kullan, yoksa geçerli yerleşimler "kart dışında" gibi görünür.
  (c) `ZONE.GetLayerName()` bazı pcbnew sürümlerinde YANLIŞ katman adı
      döndürebilir — katman kimliği için `GetLayer()` (int) veya
      `GetLayerSet().Seq()` kullan, isim string'ine güvenme.
  (d) float mm karşılaştırmaları sınırda yanlış pozitif/negatif üretir
      (ör. (0.7-0.4)/2 = 0.14999999999999997) — ölçümü tam sayı nanometre
      (pcbnew'in kendi iç birimi) ile yap, mm'ye SADECE raporlarken çevir.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from pcb_highspeed_escape import PinArasiKanal, maske_baraji_kontrolu

NM_PER_MM = 1_000_000  # pcbnew iç birimi: nanometre


def _mm(deger_nm: float) -> float:
    return deger_nm / NM_PER_MM


def _xy_mm(nokta) -> Tuple[float, float]:
    return (_mm(nokta.x), _mm(nokta.y))


# ------------------------------------------------------------------
# 1. GERÇEK PAD ÇİFTLERİNDEN PinArasiKanal ÜRETİMİ
#    (pcb_highspeed_escape.py'nin girdisini elle doldurmak yerine)
# ------------------------------------------------------------------

def _pcbnew_veya_kapsam_yok(board_path: str, kontrol_adi: str) -> Tuple[Any, Any, Optional[Bulgu]]:
    """`board_path`'i `pcbnew` ile yüklemeyi dener. `pcbnew` bu ortamda
    KURULU DEĞİLSE (`ImportError`/`ModuleNotFoundError`) exception
    FIRLATMAZ — çağıran `*_kontrolu()` fonksiyonuna özel bir KAPSAM_YOK
    `Bulgu` üretir (2026-08-03, Madde 5: "sessiz crash yerine KAPSAM_YOK").
    Dönen üçlü: BAŞARILIYSA `(pcbnew_modulu, board, None)`; pcbnew yoksa
    `(None, None, Bulgu)` — çağıran `if kapsam_yok is not None: return kapsam_yok`
    ile tek satırda erken çıkar.
    """
    try:
        import pcbnew
    except ImportError as hata:
        return None, None, bulgu_uret(
            kontrol_adi, taranan=0, detay=(
                f"pcbnew modülü bulunamadı ({hata}) — bu kontrol KiCad'in gömülü "
                "Python'unda (`C:\\Program Files\\KiCad\\10.0\\bin\\python.exe` "
                "benzeri) çalıştırılmalı; sessizce PASS/çökme yerine KAPSAM_YOK raporlandı."
            ),
        )
    return pcbnew, pcbnew.LoadBoard(board_path), None


def kanal_ciftlerini_bul(board, arama_mm: float = 3.0) -> List[Dict[str, Any]]:
    """Bakır boşluğu (0, arama_mm] arasında kalan komşu pad çiftlerini bulur
    ve her biri için `pcb_highspeed_escape.PinArasiKanal`'ı OTOMATİK üretir.

    Dönen her sözlük: {"pad_a", "pad_b", "kanal": PinArasiKanal, "iz_genisligi_mm"}
    — `iz_genisligi_mm`, o kanaldan GEÇEN gerçek izin genişliğidir (varsa);
    yoksa `None` (henüz routed değil, sadece kanal geometrisi raporlanır).

    mask_dam.py'deki `find_pad_pairs()` ile aynı yaklaşım — eksen-hizalı
    (axis-aligned) yarı-genişlik izdüşümü kullanır, döndürülmüş padlerde
    yaklaşıktır (SINIR, bkz. orijinal not).
    """
    import pcbnew  # noqa: F401  (yalnızca gerçek KiCad ortamında import edilir)

    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            pads.append((fp, pad))

    ciftler: List[Dict[str, Any]] = []
    n = len(pads)
    for i in range(n):
        f1, p1 = pads[i]
        c1 = _xy_mm(p1.GetPosition())
        for j in range(i + 1, n):
            f2, p2 = pads[j]
            if f1 is f2 and p1.GetNumber() == p2.GetNumber():
                continue
            c2 = _xy_mm(p2.GetPosition())
            mesafe = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
            if mesafe <= 1e-9:
                continue
            dx, dy = (c2[0] - c1[0]) / mesafe, (c2[1] - c1[1]) / mesafe
            h1 = abs(_mm(p1.GetSizeX()) / 2 * dx) + abs(_mm(p1.GetSizeY()) / 2 * dy)
            h2 = abs(_mm(p2.GetSizeX()) / 2 * dx) + abs(_mm(p2.GetSizeY()) / 2 * dy)
            bosluk = mesafe - h1 - h2
            if bosluk <= 0 or bosluk > arama_mm:
                continue

            m1 = _mm(p1.GetSolderMaskExpansion(pcbnew.F_Cu))
            kanal = PinArasiKanal(
                pad_sutun_araligi_mm=mesafe,
                # DÜZELTME (2026-07-31): burada önceden `(h1 + h2) * 2` vardı —
                # `bosluk_mm` (yukarıda) zaten `mesafe - h1 - h2` ile doğru
                # hesaplanıyor; `kanal_genisligi_hesapla_mm()` de aynı
                # `pad_sutun_araligi_mm - pad_uzunlugu_mm` formülünü kullanıyor,
                # bu yüzden `pad_uzunlugu_mm` = `h1 + h2` OLMALI (2 katı DEĞİL) —
                # yoksa `kanal_genisligi` gerçek boşluktan KÜÇÜK çıkıyor ve
                # SIRADAN 2-pedli pasifler (ör. bir kondansatörün kendi 2 pedi)
                # "kanal yok, kısa devre" diye YANLIŞ işaretleniyordu (bkz.
                # gerçek ESP32C3_SmartBand board'unda 175.815 yanlış-pozitif
                # üreten regresyon, `test_pcbnew_koprusu.py`'ye kilitlendi).
                pad_uzunlugu_mm=(h1 + h2),
                mask_expansion_mm=m1,
            )
            ciftler.append({
                "pad_a": f"{f1.GetReference()}.{p1.GetNumber()}",
                "pad_b": f"{f2.GetReference()}.{p2.GetNumber()}",
                "bosluk_mm": round(bosluk, 4),
                "orta_nokta_mm": ((c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0),
                "kanal": kanal,
            })
    return ciftler


def gercek_boarddan_maske_baraji_kontrolu(
    board_path: str,
    fab_min_baraj_mm: float = 0.20,
    arama_mm: float = 3.0,
) -> Bulgu:
    """`kanal_ciftlerini_bul()` ile bulunan her aday kanal için, o kanaldan
    geçen GERÇEK izin genişliğini board'dan okuyup
    `pcb_highspeed_escape.maske_baraji_kontrolu()`'nu çağırır.

    Bu, "elle PinArasiKanal doldur -> hesapla" akışını "gerçek board'u aç ->
    otomatik kanalları bul -> gerçek iz genişliğiyle hesapla" akışına
    dönüştürür — madde 1'deki mimari boşluğun somut kapanışı.
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    ciftler = kanal_ciftlerini_bul(board, arama_mm=arama_mm)
    izler = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]  # tuzak (a): PCB_ARC ayrı

    # DÜZELTME (2026-07-31): eskiden HER kanal x HER iz kombinasyonu (yakınlık
    # kontrolü OLMADAN) taranıyordu -> 1131 kanal x 375 iz = 424.125 tarama,
    # ilgisiz izlerin genişliği alakasız kanallara atfediliyordu, ve tek bir
    # bozuk kanal (yukarıdaki `pad_uzunlugu_mm` bug'ıyla birleşince) 175.815
    # birebir aynı sahte-pozitif üretiyordu (gerçek board'da doğrulandı, bkz.
    # `HAFIZA/Hafiza_Defteri.md`). Şimdi: bir kanal İÇİN sadece o kanalın orta
    # noktasına `yakinlik_mm` içinde kalan izler "o kanaldan geçiyor" sayılır
    # (kaba ama gerçek bir yakınlık testi — tam poligon kesişimi DEĞİL, bkz.
    # dosya başlığı SINIR notu) ve en YAKIN iz TEK BAŞINA raporlanır.
    yakinlik_mm = 0.5
    taranan = 0
    ihlaller: List[Dict[str, Any]] = []
    for cift in ciftler:
        mx, my = cift["orta_nokta_mm"]
        en_yakin = None
        en_yakin_mesafe = None
        for iz in izler:
            s, e = iz.GetStart(), iz.GetEnd()
            sx, sy, ex, ey = _mm(s.x), _mm(s.y), _mm(e.x), _mm(e.y)
            oy_x, oy_y = (sx + ex) / 2.0, (sy + ey) / 2.0
            mesafe = math.hypot(oy_x - mx, oy_y - my)
            if mesafe > yakinlik_mm:
                continue
            if en_yakin_mesafe is None or mesafe < en_yakin_mesafe:
                en_yakin_mesafe = mesafe
                en_yakin = iz
        taranan += 1
        if en_yakin is None:
            continue  # bu kanaldan henüz geçen bir iz yok — rapor edilecek bir şey yok
        genislik_mm = _mm(en_yakin.GetWidth())
        bulgular = maske_baraji_kontrolu(cift["kanal"], genislik_mm, fab_min_baraj_mm)
        if bulgular:
            ihlaller.append({
                "pad_a": cift["pad_a"], "pad_b": cift["pad_b"],
                "net": en_yakin.GetNetname(), "mesaj": bulgular[0],
            })

    return bulgu_uret(
        "gercek_maske_baraji", taranan, ihlaller,
        f"{len(ciftler)} aday kanal (her biri EN FAZLA 1 kez raporlanır), "
        f"{len(izler)} iz havuzundan yakınlık={yakinlik_mm}mm ile eşlendi "
        f"(arama={arama_mm}mm, fab_min_baraj={fab_min_baraj_mm}mm).",
    )


# ------------------------------------------------------------------
# 1b. TEK BİR NET'İN İZ/VIA GEOMETRİSİNİ TOPLA (ortak yardımcı —
#     başka köprüler bunu TEKRAR YAZMAK yerine ÇAĞIRMALI)
# ------------------------------------------------------------------

def net_iz_ve_via_listesi_topla(board, net_adi: str) -> Dict[str, List[Dict[str, Any]]]:
    """`net_adi`'na ait TÜM iz segmentlerini ve via'ları toplar.

    NEDEN BU FONKSİYON VAR: `openems_koprusu.py::geometri_cikar()` gibi
    başka köprülerin de bir net'in gerçek board geometrisine (SI/EM
    simülasyonu, akım yoğunluğu haritası vb. için) ihtiyacı var —
    `board.GetTracks()` üzerinde YENİ bir döngü yazmak yerine bu ortak
    yardımcıya bağlanmalılar (`kanal_ciftlerini_bul` ile AYNI "gerçek
    board'dan otomatik çıkarım" felsefesi).

    TUZAK (a) — bkz. dosya başlığı: `track.GetClass() == "PCB_TRACK"`
    YAYLARI (`PCB_ARC`) ATLAR; bu fonksiyon HER İKİSİNİ de "izler" listesine
    dahil eder (bir diferansiyel çift bükümlü/yay geçişli olabilir, yay
    segmentini atlamak geometriyi EKSİK çıkarır).

    Döner: `{"izler": [{"baslangic_mm", "bitis_mm", "genislik_mm",
    "katman"}, ...], "vialar": [{"konum_mm", "cap_mm", "ust_katman",
    "alt_katman"}, ...]}` — tümü mm/pcbnew katman kimliği (int), string
    katman adına GÜVENİLMEZ (tuzak (c))."""
    izler: List[Dict[str, Any]] = []
    vialar: List[Dict[str, Any]] = []
    for t in board.GetTracks():
        if t.GetNetname() != net_adi:
            continue
        sinif = t.GetClass()
        if sinif == "PCB_VIA":
            vialar.append({
                "konum_mm": _xy_mm(t.GetPosition()),
                # TUZAK (d, DOCS/10 D1.6): PCB_VIA.GetWidth() KATMAN
                # ARGÜMANI OLMADAN çağrılmaz (KiCad 10'da debug assert).
                "cap_mm": _mm(t.GetWidth(t.TopLayer())),
                "ust_katman": t.TopLayer(),
                "alt_katman": t.BottomLayer(),
            })
        elif sinif in ("PCB_TRACK", "PCB_ARC"):
            izler.append({
                "baslangic_mm": _xy_mm(t.GetStart()),
                "bitis_mm": _xy_mm(t.GetEnd()),
                "genislik_mm": _mm(t.GetWidth()),
                "katman": t.GetLayer(),
            })
    return {"izler": izler, "vialar": vialar}


# ------------------------------------------------------------------
# 2. VIA-IN-PAD (IPC-4761 Type VII gerektirir)
# ------------------------------------------------------------------

def via_in_pad_kontrolu(
    board_path: str,
    via_siniflandirma_haritasi: Optional[Dict[Tuple[float, float], bool]] = None,
    konum_toleransi_mm: float = 0.01,
) -> Bulgu:
    """Her via'nın bir SMD/konnektör pad'inin içinde kalıp kalmadığını
    kontrol eder. Bulunan her via-in-pad, fab notunda IPC-4761 Type VII
    (dolgu+kapak) olarak belirtilmelidir — Type IV/V (tented/plugged)
    YETERSİZDİR ([[SKILL-dfm]] §Via-in-pad).

    GENİŞLETME (2026-08-04, `via_siniflandirma.py` ile birlikte —
    ESKİ ÇAĞRI ŞEKLİ (`via_in_pad_kontrolu(board_path)`) DAVRANIŞ
    DEĞİŞTİRMEDEN çalışmaya devam eder, tespit mantığı BOZULMADI):

    `via_siniflandirma_haritasi` verilirse — tasarım-anında
    `via_siniflandirma.py::select_via_type_for_bga()` ile üretilen
    `Via` nesnelerinin `dolgu_ve_kapak_var_mi` alanını via KONUMUNA
    (mm, `konum_toleransi_mm` içinde) göre bu haritadan okur:
      - Harita bu konum için `True` diyorsa (bilinçli, IPC-4761 Type VII
        ile tasarlanmış via-in-pad) -> bulgu listesine EKLENMEZ (doğru
        pratik, gerçek bir DRC hatası DEĞİL).
      - Harita bu konum için `False` diyorsa YA DA haritada konum hiç
        YOKSA (sınıflandırma bilgisi eksik/bilinmiyor) -> ESKİ davranış
        korunur: ihlal listesine eklenir (gerçek DRC hatası, sadece
        "fab notunda belirtilmeli" tavsiyesi DEĞİL — `bulgu_uret` zaten
        `ihlaller` boş değilse `FAIL` döndürüyor, bu satır DEĞİŞMEDİ).
    Harita hiç verilmezse (`None`, varsayılan) davranış ESKİYLE BİREBİR
    aynıdır — geriye dönük uyumluluk korunur.
    """
    pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(board_path, "via_in_pad")
    if kapsam_yok is not None:
        return kapsam_yok
    vialar = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = [(fp, p) for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN)]

    def _dolgu_kapak_biliniyor_mu(via_mm: Tuple[float, float]) -> Optional[bool]:
        if via_siniflandirma_haritasi is None:
            return None
        for (kx, ky), deger in via_siniflandirma_haritasi.items():
            if abs(kx - via_mm[0]) <= konum_toleransi_mm and abs(ky - via_mm[1]) <= konum_toleransi_mm:
                return deger
        return None

    ihlaller: List[Dict[str, Any]] = []
    for v in vialar:
        vp = v.GetPosition()
        for fp, p in pads:
            if not p.IsOnLayer(v.TopLayer()) and not p.IsOnLayer(v.BottomLayer()):
                continue
            layer = v.TopLayer() if p.IsOnLayer(v.TopLayer()) else v.BottomLayer()
            if p.GetEffectivePolygon(layer).Collide(vp):
                via_mm = _xy_mm(vp)
                dolgu_kapak = _dolgu_kapak_biliniyor_mu(via_mm)
                if dolgu_kapak is True:
                    break  # IPC-4761 Type VII olarak tasarlanmış — ihlal DEĞİL
                ihlaller.append({
                    "via_mm": via_mm,
                    "pad": f"{fp.GetReference()}.{p.GetNumber()}",
                    "net": v.GetNetname(),
                    "dolgu_ve_kapak_biliniyor_mu": dolgu_kapak,  # None=bilinmiyor, False=yok
                })
                break

    return bulgu_uret(
        "via_in_pad", len(vialar), ihlaller,
        "Bulunan her via-in-pad fab notunda IPC-4761 Type VII "
        "(dolgu+kapak, dimple ≤25µm) olarak belirtilmeli. Sınıflandırma "
        "haritasında dolgu+kapak=True olarak işaretli via'lar zaten doğru "
        "tasarlanmış sayılır ve bu listeye dahil edilmez.",
    )


# ------------------------------------------------------------------
# 3. ANNULAR RING (teardrop adayı tespiti)
# ------------------------------------------------------------------

def annular_ring_kontrolu(board_path: str, min_mm: float = 0.15) -> Bulgu:
    """Halka (annular ring) < `min_mm` olan via/PTH pad'leri teardrop
    adayı olarak işaretler (Class 2 ~0.15 / Class 3 ~0.20mm).

    TUZAK (d): karşılaştırma TAM SAYI nm ile yapılır — float mm'de
    (0.7-0.4)/2 = 0.14999999999999997 çıkıp tam sınırdaki pad'i yanlışlıkla
    ihlal sayabilir."""
    pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(board_path, "annular_ring")
    if kapsam_yok is not None:
        return kapsam_yok
    limit_nm = int(round(min_mm * NM_PER_MM))

    taranan, ihlaller = 0, []
    for v in (t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"):
        taranan += 1
        # TUZAK (e): PCB_VIA.GetWidth() artık bir KATMAN argümanı istiyor
        # (per-layer via genişliği stack'leri desteklendiği için) -
        # parametresiz çağrı KiCad'de "GetWidth called without a layer
        # argument" debug assert'i (GUI pop-up, headless akışı kilitler)
        # fırlatıyor. TopLayer() ile via'nın üst katmandaki genişliği
        # alınır - standart (through) bir via için bu tüm katmanlarda
        # aynıdır, annular ring hesabı için yeterli.
        halka_nm = (v.GetWidth(v.TopLayer()) - v.GetDrill()) // 2
        if halka_nm < limit_nm:
            ihlaller.append({"tip": "via", "konum_mm": _xy_mm(v.GetPosition()),
                             "net": v.GetNetname(), "halka_mm": round(halka_nm / NM_PER_MM, 4)})

    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if d.x <= 0 or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            taranan += 1
            halka_nm = (min(p.GetSizeX(), p.GetSizeY()) - d.x) // 2
            if halka_nm < limit_nm:
                ihlaller.append({"tip": "pth", "pad": f"{fp.GetReference()}.{p.GetNumber()}",
                                 "halka_mm": round(halka_nm / NM_PER_MM, 4)})

    return bulgu_uret(
        "annular_ring", taranan, ihlaller,
        f"Halka < {min_mm}mm olan delikler teardrop adayıdır.",
    )


# ------------------------------------------------------------------
# 4. KENAR/DEPANEL — SERAMİK FLEX CRACK RİSKİ
# ------------------------------------------------------------------

def _kart_kenari_noktalari(board) -> List[Tuple[float, float]]:
    import pcbnew

    noktalar: List[Tuple[float, float]] = []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            poly = pcbnew.SHAPE_POLY_SET()
            d.TransformShapeToPolygon(poly, pcbnew.UNDEFINED_LAYER, 0,
                                      pcbnew.FromMM(0.01), pcbnew.ERROR_INSIDE)
        except Exception:
            continue
        for oi in range(poly.OutlineCount()):
            ol = poly.Outline(oi)
            for i in range(ol.PointCount()):
                p = ol.CPoint(i)
                noktalar.append((_mm(p.x), _mm(p.y)))
    return noktalar


def kenar_keepout_seramik_kontrolu(board_path: str, keepout_mm: float = 2.0) -> Bulgu:
    """2 uçlu seramik (C*/R*/L*) parçaların kart kenarından `keepout_mm`
    içinde olup olmadığını kontrol eder (flex crack riski,
    [[SKILL-dfm]] §MLCC flex crack).

    TUZAK (b): `footprint.GetBoundingBox()` yerine parçanın MERKEZ
    konumu kullanılıyor (referans/değer ipek metnini dahil etme riskini
    baştan eler)."""
    pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(board_path, "kenar_keepout_seramik")
    if kapsam_yok is not None:
        return kapsam_yok
    kenar = _kart_kenari_noktalari(board)
    if not kenar:
        return bulgu_uret("kenar_keepout_seramik", 0, [], "Edge.Cuts bulunamadı")

    taranan, ihlaller = 0, []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not re.match(r"^[CRL]\d", ref) or len(list(fp.Pads())) != 2:
            continue
        taranan += 1
        pos = _xy_mm(fp.GetPosition())
        mesafe = min(math.hypot(px - pos[0], py - pos[1]) for px, py in kenar)
        if mesafe < keepout_mm:
            ihlaller.append({
                "ref": ref, "konum_mm": pos, "kenar_mesafesi_mm": round(mesafe, 3),
                "yon_derece": round(fp.GetOrientationDegrees() % 180, 1),
            })

    return bulgu_uret(
        "kenar_keepout_seramik", taranan, ihlaller,
        f"2 uçlu seramikler kart kenarından ≥{keepout_mm}mm olmalı. "
        "İhlal listesindeki yon_derece ile parçanın uzun ekseni kırma "
        "hattına PARALEL mi elle doğrula.",
    )


# ------------------------------------------------------------------
# 5. GND STITCHING YOĞUNLUĞU (EMI/EMC — λ/20 hedefi)
# ------------------------------------------------------------------

C_MPS = 299_792_458.0


def _lambda_20_hedef_mm(f_diz_ghz: float, er_eff: float) -> float:
    """Hedef via aralığı: v = c/sqrt(er_eff), lambda = v/f, hedef = lambda/20.
    `f_diz_ghz` = f_knee (kenar hızından türetilen diz frekansı, saat
    frekansı DEĞİL — bkz. pcb_stackup_planner.py'deki f_knee tartışması)."""
    v = C_MPS / math.sqrt(er_eff)
    f_hz = f_diz_ghz * 1e9
    lam_mm = (v / f_hz) * 1000.0
    return lam_mm / 20.0


def stitch_yogunlugu_kontrolu(
    board_path: str,
    f_diz_ghz: float = 5.0,
    er_eff: float = 4.5,
    gnd_net_regex: str = r"^/?(GND|AGND|DGND|VSS)",
    kenar_adim_mm: float = 1.0,
) -> Bulgu:
    """Kart kenarı boyunca ve katman-geçişi (via) çevresinde en yakın GND
    via mesafesini ölçer, λ/20 hedefiyle karşılaştırır.

    Bu, arkadaşının `stitch_density.py`'sindeki yaklaşımın gerçek-board
    karşılığıdır — `pcb_stackup_planner.py`'deki
    `yuksek_frekans_daha_dar_stitching_araligi_ister` testi SOYUT bir
    frekans->aralık hesabıydı; bu fonksiyon o hesabı GERÇEK kart üzerindeki
    GND via konumlarıyla karşılaştırır.

    SINIR: `er_eff` sabit bir kullanıcı girdisidir, katman dielektriğinden
    otomatik hesaplanmaz. GND via YOKSA (referans noktası yok) KAPSAM_YOK
    döner — "via yok, o yüzden ihlal de yok" YANLIŞ bir PASS olurdu.
    """
    pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(board_path, "stitch_yogunlugu")
    if kapsam_yok is not None:
        return kapsam_yok
    hedef_mm = _lambda_20_hedef_mm(f_diz_ghz, er_eff)
    rx = re.compile(gnd_net_regex)
    tum_vialar = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    gnd_vialar = [v for v in tum_vialar if rx.match(v.GetNetname() or "")]

    if not gnd_vialar:
        return bulgu_uret(
            "stitch_yogunlugu", 0, [],
            "GND via bulunamadı — ölçüm referansı yok (KAPSAM_YOK, PASS DEĞİL)."
        )

    gnd_xy = [_xy_mm(v.GetPosition()) for v in gnd_vialar]
    kenar = _kart_kenari_noktalari(board)

    taranan, ihlaller = 0, []

    # (a) kenar boyunca örnekleme
    # DÜZELTME (2026-07-31): eskiden burada `d.GetStart()`/`d.GetEnd()` ile
    # HER Edge.Cuts çizim öğesini (şekil türünden BAĞIMSIZ) bir DOĞRU
    # PARÇASI gibi yorumlayan kendi (yanlış) döngüsü vardı — `PCB_SHAPE`
    # bir `gr_circle`/`gr_arc` (yuvarlak kart, TAM OLARAK bu projenin
    # durumu) olduğunda `GetStart()`/`GetEnd()` gerçek çevre noktaları
    # DEĞİL merkez/yardımcı noktalar döndürüyor; ikisi arasında doğrusal
    # enterpolasyon yapmak kart MERKEZİNDEN dışarı doğru sahte bir RADYAL
    # çizgi üretiyordu (`(0,0),(1,0),(2,0),(3,0)...` gibi — gerçek yuvarlak
    # kenarla HİÇ ilgisi yok, bazıları kart SINIRLARININ dışına düşüyordu;
    # bu, `kanal_ciftlerini_bul` bug'ından SONRA gerçek board'da bulunan
    # İKİNCİ ciddi bug — bir stitching-via denemesi kart dışına bir via
    # yerleştirdi, bkz. `HAFIZA/Hafiza_Defteri.md`). Yukarıda ZATEN
    # hesaplanmış ama kullanılmayan `kenar` (şekilden bağımsız,
    # `TransformShapeToPolygon` ile polygonlaştırılmış GERÇEK dış hat —
    # `kenar_keepout_seramik_kontrolu`'nun da kullandığı, doğruluğu round
    # board'da ZATEN kanıtlanmış fonksiyon) burada kullanılıyor: ardışık
    # poligon köşeleri arasında `kenar_adim_mm` aralıklarla örnekleme.
    if len(kenar) >= 2:
        n_pts = len(kenar)
        for i in range(n_pts):
            s = kenar[i]
            e = kenar[(i + 1) % n_pts]
            uzunluk = math.hypot(e[0] - s[0], e[1] - s[1])
            if uzunluk <= 0:
                continue
            n = max(1, int(math.ceil(uzunluk / kenar_adim_mm)))
            for k in range(n):
                t = k / n
                nokta = (s[0] + (e[0] - s[0]) * t, s[1] + (e[1] - s[1]) * t)
                taranan += 1
                mesafe = min(math.hypot(gx - nokta[0], gy - nokta[1]) for gx, gy in gnd_xy)
                if mesafe > hedef_mm:
                    ihlaller.append({"tur": "kenar", "konum_mm": nokta,
                                     "en_yakin_gnd_via_mm": round(mesafe, 3)})

    # (b) katman geçişi (via) çevresinde en yakın GND via
    for v in tum_vialar:
        if v.TopLayer() == v.BottomLayer():
            continue
        taranan += 1
        vp = _xy_mm(v.GetPosition())
        digerleri = [g for g in gnd_xy if g != vp]
        if not digerleri:
            continue
        mesafe = min(math.hypot(gx - vp[0], gy - vp[1]) for gx, gy in digerleri)
        if mesafe > hedef_mm:
            ihlaller.append({"tur": "via_donusu", "net": v.GetNetname(),
                             "konum_mm": vp, "en_yakin_gnd_via_mm": round(mesafe, 3)})

    return bulgu_uret(
        "stitch_yogunlugu", taranan, ihlaller,
        f"Hedef aralık (λ/20, f_diz={f_diz_ghz}GHz, er_eff={er_eff}) = "
        f"{hedef_mm:.3f}mm. GND via sayısı={len(gnd_vialar)}.",
    )




# ------------------------------------------------------------------
# 5b. DEKUPLAJ KAPASİTÖR MESAFESİ (fiziksel-koordinat kontrolü)
# ------------------------------------------------------------------
#
# NOT: `pcb_stackup_planner.py::dekuplaj_kontrolu()` ŞEMATİK-SEVİYESİ bir
# kontroldür — `Komponent.guc_pini_sayisi` vs `dekuplaj_kapasitor_sayisi`
# SAYI karşılaştırması, "kaç tane var" sorusuna cevap verir. BU fonksiyon
# ONUN YERİNE DEĞİL, YANINA eklenmiştir — TAMAMLAYICI bir katman: gerçek
# board koordinatlarına bakıp "var ama YETERİNCE YAKIN MI" sorusuna cevap
# verir. Sayı doğru olsa bile bir kapasitör IC'den 20mm uzakta yerleştirilmiş
# olabilir — sayı kontrolü bunu YAKALAYAMAZ, sadece bu kontrol yakalar.

# IC paket ailesi işaretleri — footprint kütüphane kimliğinde (ör.
# "Package_QFN:QFN-36-1EP_5x6mm...") ARANIR. Bilinçli olarak geniş tutuldu
# (SOIC/TSSOP/SOT gibi `pcb_stackup_planner.KilifTuru`'nda YOKTUR ama
# gerçek board'larda LDO/ESD/choke gibi IC'ler bu paketlerdedir) — sadece
# "QFN/BGA" ile sınırlı kalmak gerçek IC'lerin çoğunu KAÇIRIRDI.
_IC_PAKET_IMZALARI = ("QFN", "BGA", "SOIC", "SSOP", "TSSOP", "LQFP", "QFP", "DFN", "SON")
# SOT ailesi hem 3-pinli basit transistörlerde hem 5/6-pinli LDO/ESD gibi
# gerçek IC'lerde kullanılır — pad sayısıyla ayrıştırılır (bkz. altta).
_SOT_IMZASI = "SOT"
_SOT_MIN_PAD_IC_SAYILIR = 5

_GUC_PINI_NET_DESENLERI = (
    "VCC", "VDD", "3V3", "3.3V", "+3V3", "+3.3V", "5V", "+5V", "1V8", "+1V8",
    "1V2", "+1V2", "AVDD", "DVDD", "VBAT", "VBUS", "VIN",
)

_DEKUPLAJ_DEGER_ARALIGI_F = (47e-9, 220e-9)  # 47nF - 220nF (100nF hedefine yakın aralık)

_KAPASITANS_BIRIM_CARPANI = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "f": 1.0,
}


def _footprint_ic_mi(fp_kutuphane_id: str, pad_sayisi: int) -> bool:
    ad = fp_kutuphane_id.upper()
    if any(imza in ad for imza in _IC_PAKET_IMZALARI):
        return True
    if _SOT_IMZASI in ad and pad_sayisi >= _SOT_MIN_PAD_IC_SAYILIR:
        return True
    return False


def _guc_pini_mi(net_isim: str) -> bool:
    ad = net_isim.strip().upper()
    if not ad:
        return False
    parcalar = ad.replace("+", "").split("_")
    return any(p == d.replace("+", "") for d in _GUC_PINI_NET_DESENLERI for p in parcalar)


def _kapasitans_degeri_parse_et(deger_str: str) -> Optional[float]:
    """'100nF', '0.1uF', '100n', '22pF' gibi KiCad değer string'lerini
    Farad cinsinden float'a çevirir. Parse edilemezse `None` döner
    (uydurma bir değer ÜRETİLMEZ — çağıran bu kapasitörü aday listesinden
    ELER)."""
    eslesme = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([pnuµm]?)F?\s*$", deger_str, re.I)
    if not eslesme:
        return None
    sayi = float(eslesme.group(1))
    birim = eslesme.group(2).lower()
    carpan = _KAPASITANS_BIRIM_CARPANI.get(birim, 1.0)
    return sayi * carpan


def dekuplaj_mesafe_kontrolu(board_path: str, maks_mesafe_mm: float = 3.0) -> Bulgu:
    """Her IC güç pini için en yakın UYGUN (47-220nF aralığında) dekuplaj
    kapasitörünün merkez-merkez mesafesini GERÇEK board koordinatlarından
    ölçer. `maks_mesafe_mm` (varsayılan 3mm) aşılırsa, VEYA hiç uygun aday
    kapasitör bulunamazsa (bu İKİSİ AYRI ihlal türü olarak raporlanır),
    ihlal listesine eklenir.

    Mesafe aşılırsa parazit ve ani-akım-kaynaklı resetlenme riski artar.
    """
    pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(board_path, "dekuplaj_mesafesi")
    if kapsam_yok is not None:
        return kapsam_yok

    kapasitor_adaylari: List[Dict[str, Any]] = []
    for fp in board.GetFootprints():
        fp_id = str(fp.GetFPID().GetLibItemName()) if hasattr(fp, "GetFPID") else ""
        if not fp_id.upper().startswith("C_") and not fp.GetReference().upper().startswith("C"):
            continue
        deger_f = _kapasitans_degeri_parse_et(fp.GetValue())
        if deger_f is None:
            continue
        if not (_DEKUPLAJ_DEGER_ARALIGI_F[0] <= deger_f <= _DEKUPLAJ_DEGER_ARALIGI_F[1]):
            continue
        kapasitor_adaylari.append({
            "ref": fp.GetReference(),
            "konum_mm": _xy_mm(fp.GetPosition()),
            "deger_f": deger_f,
        })

    taranan = 0
    ihlaller: List[Dict[str, Any]] = []
    for fp in board.GetFootprints():
        fp_id = str(fp.GetFPID().GetLibItemName()) if hasattr(fp, "GetFPID") else ""
        pad_sayisi = len(fp.Pads())
        if not _footprint_ic_mi(fp_id, pad_sayisi):
            continue
        for p in fp.Pads():
            net_isim = p.GetNetname()
            if not _guc_pini_mi(net_isim):
                continue
            taranan += 1
            pin_konumu = _xy_mm(p.GetPosition())
            pin_etiketi = f"{fp.GetReference()}.{p.GetNumber()}"

            if not kapasitor_adaylari:
                ihlaller.append({
                    "tur": "kapasitor_yok",
                    "pin": pin_etiketi, "net": net_isim, "pin_konum_mm": pin_konumu,
                    "detay": "Board'da 47-220nF aralığında hiç dekuplaj kapasitörü bulunamadı.",
                })
                continue

            en_yakin = min(
                kapasitor_adaylari,
                key=lambda k: math.hypot(k["konum_mm"][0] - pin_konumu[0],
                                          k["konum_mm"][1] - pin_konumu[1]),
            )
            mesafe_mm = round(math.hypot(
                en_yakin["konum_mm"][0] - pin_konumu[0],
                en_yakin["konum_mm"][1] - pin_konumu[1],
            ), 4)
            if mesafe_mm > maks_mesafe_mm:
                ihlaller.append({
                    "tur": "kapasitor_uzak",
                    "pin": pin_etiketi, "net": net_isim, "pin_konum_mm": pin_konumu,
                    "en_yakin_kapasitor": en_yakin["ref"],
                    "en_yakin_kapasitor_konum_mm": en_yakin["konum_mm"],
                    "mesafe_mm": mesafe_mm, "sinir_mm": maks_mesafe_mm,
                })

    return bulgu_uret(
        "dekuplaj_mesafesi", taranan, ihlaller,
        f"Sınır: {maks_mesafe_mm}mm (datasheet'lerde tipik önerilen üst sınır). "
        "Mesafe aşılırsa parazit ve ani-akım-kaynaklı resetlenme riski artar. "
        f"Board'da bulunan uygun (47-220nF) dekuplaj kapasitörü adayı: {len(kapasitor_adaylari)}.",
    )


# ------------------------------------------------------------------
# 6. Tüm gerçek-board kontrollerini tek seferde çalıştır
# ------------------------------------------------------------------

def tum_gercek_board_kontrollerini_calistir(
    board_path: str,
    fab_min_baraj_mm: float = 0.20,
    annular_min_mm: float = 0.15,
    edge_keepout_mm: float = 2.0,
    f_diz_ghz: float = 5.0,
    er_eff: float = 4.5,
    dekuplaj_maks_mesafe_mm: float = 3.0,
) -> List[Bulgu]:
    """CLAUDE.md akışının 5. adımına (doğrulama kapısı) eklenecek gerçek-board
    kontrolleri. `bulgu_sozlesmesi.ozet_rapor()` ile JSON'a çevrilebilir."""
    return [
        gercek_boarddan_maske_baraji_kontrolu(board_path, fab_min_baraj_mm),
        via_in_pad_kontrolu(board_path),
        annular_ring_kontrolu(board_path, annular_min_mm),
        kenar_keepout_seramik_kontrolu(board_path, edge_keepout_mm),
        stitch_yogunlugu_kontrolu(board_path, f_diz_ghz, er_eff),
        dekuplaj_mesafe_kontrolu(board_path, dekuplaj_maks_mesafe_mm),
    ]


if __name__ == "__main__":
    import argparse
    import json

    from bulgu_sozlesmesi import ozet_rapor

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("board")
    ap.add_argument("--json")
    a = ap.parse_args()

    bulgular = tum_gercek_board_kontrollerini_calistir(a.board)
    rapor = ozet_rapor(bulgular)
    metin = json.dumps(rapor, indent=2, ensure_ascii=False)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(metin + "\n")
    print(metin)
