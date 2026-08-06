"""
pcbnew_diff_pair_router.py
============================
Hibrit routing mimarisi: diferansiyel çiftleri FreeRouting'e göndermeden
ÖNCE, doğrudan `pcbnew` API'siyle board üzerine çizip KİLİTLER (LOCKED) —
`MASTER_RULEBOOK.md` FAZ 7 "FreeRouting/DSN Diferansiyel Çift Sınırı"
maddesinin kod karşılığı.

NEDEN BU MODÜL VAR:
`pcbnew.ExportSpecctraDSN()` diferansiyel çift eşleştirme/coupling
bilgisini DSN'e hiç TAŞIMAZ — bu, 2026-08-03'te cm4-io-test projesinde
gerçek bir `.dsn` export'u incelenerek DOĞRULANDI (bkz.
`HAFIZA/Hafiza_Defteri.md` aynı tarihli kayıt, `DOCS/10_Otonomluk_Engel_
Raporu.md` D1.1/D1.5). Bu yüzden yüksek hızlı diferansiyel çiftler
FreeRouting'e verilmeden ÖNCE, GERÇEK pcbnew geometrisiyle burada
çözülmelidir. Bu modülün çizdiği track'ler `SetLocked(True)` ile
kilitlenir — FreeRouting'in kendisi (sonradan çalıştırılsa bile) bunları
aşılmaz bir engel olarak görür, bozmaz.

KAPSAM VE DÜRÜSTLÜK SINIRI (bilerek):
Bu modül GENEL bir "her diferansiyel çifti çöz" motoru DEĞİLDİR. Sadece
İKİ ucu (start/end) DOĞRUDAN, tek segmentli düz bir hatla bağlanabilen
"basit" diferansiyel çiftleri çözer — P ve N net'lerinin bağlantı
vektörleri birbirine yeterince PARALEL (`tolerans_derece` içinde) olmalı.
P/N bağlantı vektörleri arasında büyük bir açı farkı varsa — bu, tam
olarak cm4-io-test J1'in "pair twist" problemine yol açan geometridir —
bu araç o çifti ÇÖZMEYE ÇALIŞMAZ, `basarili=False` + açık gerekçeyle
raporlar. Yanlış/kısa-devre riskli bir geometri üretmek yerine dürüstçe
reddetmek, bu projenin genel disipliniyle (bkz. `edge_cuts_yarigi_oner()`
docstring'i — "termal izolasyon KAZANIP mekanik dayanım KAYBETMEK YASAK,
bu fonksiyon o ödünü sessizce vermez") AYNI ilkedir. J1 gibi zorlu vakalar
hâlâ `karar_birimleri.json: j1-pair-twist-cozumu` açık kararı kapsamındadır.

Ayrıca: sadece TAM 2 pedli P/N net çiftlerini kapsar — 3+ pedli/dallanan
netler bu araca verilmeden ÖNCE `steiner_agaci_motoru.py` ile 2'li
segmentlere bölünmelidir (MASTER_RULEBOOK FAZ 7 "Çok-Pedli Net
Segmentasyonu" maddesi).
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

VARSAYILAN_TOLERANS_DERECE = 15.0
VARSAYILAN_GENISLIK_MM = 0.2
VARSAYILAN_KATMAN = "F.Cu"


@dataclass
class DiffPairNeti:
    """Routelanacak tek bir diferansiyel çift girdisi."""

    p_net_adi: str
    n_net_adi: str
    genislik_mm: float = VARSAYILAN_GENISLIK_MM
    katman: str = VARSAYILAN_KATMAN


@dataclass
class DiffPairSonucu:
    """Tek bir çiftin işlem sonucu — hem başarı hem RET durumunda
    gerekçe/ölçüm taşır (sessiz "denedim ama olmadı" YOK)."""

    p_net_adi: str
    n_net_adi: str
    basarili: bool
    detay: str
    p_uzunluk_mm: Optional[float] = None
    n_uzunluk_mm: Optional[float] = None
    skew_mm: Optional[float] = None


def _mesafe(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def net_pad_konumlarini_bul(board, net_adi: str) -> List[Tuple[str, str, float, float]]:
    """`net_adi` net'ine ait TÜM pad konumlarını `(ref, pad_no, x_mm, y_mm)`
    olarak döner. `pcbnew` import ETMEZ — `board` zaten yüklü bir nesne
    olarak verilir, bu fonksiyon sadece onun sağladığı `GetFootprints()`/
    `Pads()`/`GetNetname()`/`GetPosition()` API'sini kullanır (nanometre
    birimini mm'ye çevirir)."""
    NM_PER_MM = 1_000_000
    sonuc: List[Tuple[str, str, float, float]] = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == net_adi:
                pos = pad.GetPosition()
                sonuc.append((fp.GetReference(), pad.GetNumber(), pos.x / NM_PER_MM, pos.y / NM_PER_MM))
    return sonuc


def en_yakin_eslesmeyi_bul(
    p1: Tuple[float, float], p2: Tuple[float, float],
    n1: Tuple[float, float], n2: Tuple[float, float],
) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    """(p1,p2) P pad'lerini (n1,n2) N pad'leriyle FİZİKSEL yakınlığa göre
    eşleştirir — rastgele/ilk-sıradaki eşleşme DEĞİL. Gerçek diferansiyel
    çiftlerde aynı konnektör/IC ucundaki P/N pad'leri birbirine yakın
    konumlanır; bu fonksiyon o fiziksel gerçekliği kullanarak hangi P
    pad'inin hangi N pad'iyle "aynı uç" olduğunu belirler.

    Döner: `(p_start, n_start, p_end, n_end)` — start/end etiketleri
    keyfidir (sadece iki ucu ayırt etmek için), ama p_start HER ZAMAN
    n_start ile "aynı uçtur" (fiziksel olarak en yakın eşleşme)."""
    d_ayni_sira = _mesafe(p1, n1) + _mesafe(p2, n2)
    d_capraz = _mesafe(p1, n2) + _mesafe(p2, n1)
    if d_ayni_sira <= d_capraz:
        return p1, n1, p2, n2
    return p1, n2, p2, n1


def paralellik_acisi_derece(
    p_start: Tuple[float, float], p_end: Tuple[float, float],
    n_start: Tuple[float, float], n_end: Tuple[float, float],
) -> float:
    """P bağlantı vektörü (`p_end - p_start`) ile N bağlantı vektörü
    (`n_end - n_start`) arasındaki açıyı derece cinsinden döner (0-180).
    Sıfır-uzunluklu bir vektör (start==end, örn. aynı noktadaki iki pad)
    TANIMSIZ bir açı üretir — bu fonksiyon o durumda 180.0 (en güvensiz
    değer) döner, sessizce 0 VARSAYMAZ."""
    vp = (p_end[0] - p_start[0], p_end[1] - p_start[1])
    vn = (n_end[0] - n_start[0], n_end[1] - n_start[1])
    lp, ln = math.hypot(*vp), math.hypot(*vn)
    if lp < 1e-9 or ln < 1e-9:
        return 180.0
    kosinus = max(-1.0, min(1.0, (vp[0] * vn[0] + vp[1] * vn[1]) / (lp * ln)))
    return math.degrees(math.acos(kosinus))


def _duz_track_ciz(pcbnew, board, start_mm, end_mm, net, katman_id: int, genislik_mm: float):
    """Tek bir düz `pcbnew.PCB_TRACK` segmenti oluşturur, board'a ekler,
    ve HEMEN `SetLocked(True)` ile kilitler — EN KRİTİK KURAL (kullanıcı
    talimatı): kilitlenmemiş bir track, sonradan çalışan FreeRouting
    tarafından bozulabilir."""
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start_mm[0]), pcbnew.FromMM(start_mm[1])))
    track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end_mm[0]), pcbnew.FromMM(end_mm[1])))
    track.SetWidth(pcbnew.FromMM(genislik_mm))
    track.SetLayer(katman_id)
    if net is not None:
        track.SetNet(net)
    track.SetLocked(True)
    board.Add(track)
    return track


def _tek_cifti_isle(pcbnew, board, cift: DiffPairNeti, tolerans_derece: float) -> DiffPairSonucu:
    """Tek bir `DiffPairNeti`'ni işler: pad'leri bulur, eşleştirir,
    paralellik kontrolü yapar, geçerse track çizip kilitler; geçmezse
    board'a HİÇBİR ŞEY yazmadan gerekçeli bir RET döner."""
    p_pedler = net_pad_konumlarini_bul(board, cift.p_net_adi)
    n_pedler = net_pad_konumlarini_bul(board, cift.n_net_adi)

    if len(p_pedler) != 2 or len(n_pedler) != 2:
        return DiffPairSonucu(
            cift.p_net_adi, cift.n_net_adi, False,
            f"P/N net'lerinin İKİSİ de tam 2 pad içermeli (P={len(p_pedler)} pad, "
            f"N={len(n_pedler)} pad) — dallanan/3+ pedli netler bu araçla DEĞİL, önce "
            "steiner_agaci_motoru.py ile 2'li segmentlere bölünerek işlenmeli.",
        )

    p1 = (p_pedler[0][2], p_pedler[0][3])
    p2 = (p_pedler[1][2], p_pedler[1][3])
    n1 = (n_pedler[0][2], n_pedler[0][3])
    n2 = (n_pedler[1][2], n_pedler[1][3])

    p_start, n_start, p_end, n_end = en_yakin_eslesmeyi_bul(p1, p2, n1, n2)
    aci = paralellik_acisi_derece(p_start, p_end, n_start, n_end)

    if aci > tolerans_derece:
        return DiffPairSonucu(
            cift.p_net_adi, cift.n_net_adi, False,
            f"P/N bağlantı vektörleri arasındaki açı {aci:.1f}° > tolerans "
            f"{tolerans_derece:.1f}° — bu, cm4-io-test J1'in 'pair twist' problemiyle "
            "AYNI geometri sınıfı; bu araç YANLIŞ/kısa-devre riskli bir geometri "
            "üretmek yerine dürüstçe reddediyor (bkz. karar_birimleri.json: "
            "j1-pair-twist-cozumu). Gelişmiş bir coupled-router veya insan "
            "müdahalesi gerekir.",
        )

    p_net = board.FindNet(cift.p_net_adi)
    n_net = board.FindNet(cift.n_net_adi)
    if p_net is None or n_net is None:
        return DiffPairSonucu(
            cift.p_net_adi, cift.n_net_adi, False,
            f"board.FindNet() net'i bulamadı (P bulundu={p_net is not None}, "
            f"N bulundu={n_net is not None}) — pad'ler bir net adı taşısa bile board "
            "seviyesinde o net kayıtlı olmayabilir.",
        )

    katman_id = board.GetLayerID(cift.katman)
    _duz_track_ciz(pcbnew, board, p_start, p_end, p_net, katman_id, cift.genislik_mm)
    _duz_track_ciz(pcbnew, board, n_start, n_end, n_net, katman_id, cift.genislik_mm)

    p_uzunluk = _mesafe(p_start, p_end)
    n_uzunluk = _mesafe(n_start, n_end)
    return DiffPairSonucu(
        cift.p_net_adi, cift.n_net_adi, True,
        f"Doğrudan hat ile routelandı ve LOCKED işaretlendi (açı={aci:.1f}°).",
        p_uzunluk_mm=round(p_uzunluk, 4), n_uzunluk_mm=round(n_uzunluk, 4),
        skew_mm=round(abs(p_uzunluk - n_uzunluk), 4),
    )


def diff_ciftlerini_rotala(
    board_path: str,
    ciftler: List[DiffPairNeti],
    tolerans_derece: float = VARSAYILAN_TOLERANS_DERECE,
) -> Tuple[Bulgu, List[DiffPairSonucu]]:
    """Ana giriş noktası. `pcbnew` bu ortamda kurulu değilse (lazy import,
    MASTER_RULEBOOK "pcbnew Bağımlılığı Her Zaman Lazy" kuralı) exception
    FIRLATMAZ — `taranan=0` ile otomatik KAPSAM_YOK döner.

    En az bir çift BAŞARIYLA routelanmışsa: değişiklik diske yazılmadan
    ÖNCE orijinal dosyanın `.bak` yedeği alınır (bu projenin `ecad_mcad_
    termal_kopru.py`'deki "önce yedek, sonra yaz" disipliniyle AYNI), sonra
    `board.Save(board_path)` çağrılır. HİÇBİR çift başarılı olmazsa dosyaya
    DOKUNULMAZ (yedek de alınmaz — değişmeyen bir dosyanın yedeğini almak
    anlamsızdır).
    """
    try:
        import pcbnew
    except ImportError as hata:
        return bulgu_uret(
            "diff_pair_routing", taranan=0,
            detay=f"pcbnew modülü bulunamadı ({hata}) — bu araç KiCad'in gömülü "
                  "Python'unda çalıştırılmalı; sessizce PASS/çökme yerine KAPSAM_YOK raporlandı.",
        ), []

    board = pcbnew.LoadBoard(board_path)
    sonuclar = [_tek_cifti_isle(pcbnew, board, cift, tolerans_derece) for cift in ciftler]

    if any(s.basarili for s in sonuclar):
        shutil.copy(board_path, board_path + ".bak")
        board.Save(board_path)

    ihlaller = [
        {"p_net": s.p_net_adi, "n_net": s.n_net_adi, "detay": s.detay}
        for s in sonuclar if not s.basarili
    ]
    basarili_sayisi = sum(1 for s in sonuclar if s.basarili)
    bulgu = bulgu_uret(
        "diff_pair_routing", taranan=len(sonuclar), ihlaller=ihlaller,
        detay=f"{basarili_sayisi}/{len(sonuclar)} çift LOCKED track olarak routelandı.",
    )
    return bulgu, sonuclar
