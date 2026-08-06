"""
pcbnew_diff_pair_router.py için test suite (2026-08-03, ADIM 2 — Hibrit
Routing Mimarisi).

`test_pcbnew_koprusu.py` ile AYNI disiplin: gerçek `pcbnew` modülünü
import ETMEZ (bu ortamda kurulu değil) — `sys.modules["pcbnew"]`'e bir
taklit yerleştirip duck-typing mock nesneleriyle test eder. Ayrıca
`TestPcbnewYokFallback` sınıfı gerçek `ModuleNotFoundError` ile (mock
KALDIRILARAK) fail-closed KAPSAM_YOK davranışını kanıtlar.

EN KRİTİK TEST: `test_basarili_route_locked_isaretlenir` — çizilen HER
track'in `SetLocked(True)` ile işaretlendiğini doğrudan doğrular (kullanıcı
talimatının "EN KRİTİK KURAL" dediği madde).
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

import pytest

import pcbnew_diff_pair_router as router_modulu
from pcbnew_diff_pair_router import (
    DiffPairNeti,
    diff_ciftlerini_rotala,
    en_yakin_eslesmeyi_bul,
    net_pad_konumlarini_bul,
    paralellik_acisi_derece,
)

NM_PER_MM = 1_000_000


# ------------------------------------------------------------------
# Taklit `pcbnew` modülü + mock nesneler
# ------------------------------------------------------------------

class SahteNokta:
    def __init__(self, x_mm: float, y_mm: float):
        self.x = int(round(x_mm * NM_PER_MM))
        self.y = int(round(y_mm * NM_PER_MM))


class SahtePad:
    def __init__(self, numara: str, x_mm: float, y_mm: float, net_adi: str):
        self._numara = numara
        self._pos = SahteNokta(x_mm, y_mm)
        self._net_adi = net_adi

    def GetNumber(self) -> str:
        return self._numara

    def GetPosition(self) -> SahteNokta:
        return self._pos

    def GetNetname(self) -> str:
        return self._net_adi


class SahteFootprint:
    def __init__(self, ref: str, padlar: List[SahtePad]):
        self._ref = ref
        self._padlar = padlar

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[SahtePad]:
        return self._padlar


class SahteNet:
    def __init__(self, isim: str):
        self._isim = isim

    def GetNetname(self) -> str:
        return self._isim


class SahteTrack:
    def __init__(self, board):
        self._board = board
        self.start = None
        self.end = None
        self.width = None
        self.layer = None
        self.net = None
        self.locked = False

    def SetStart(self, v) -> None:
        self.start = v

    def SetEnd(self, v) -> None:
        self.end = v

    def SetWidth(self, w) -> None:
        self.width = w

    def SetLayer(self, layer) -> None:
        self.layer = layer

    def SetNet(self, net) -> None:
        self.net = net

    def SetLocked(self, deger: bool) -> None:
        self.locked = deger

    def IsLocked(self) -> bool:
        return self.locked


class SahteBoard:
    def __init__(self, footprints: List[SahteFootprint], netler: Optional[List[str]] = None):
        self._footprints = footprints
        self._netler: Dict[str, SahteNet] = {isim: SahteNet(isim) for isim in (netler or [])}
        self.eklenen_tracklar: List[SahteTrack] = []
        self.kaydedildi_mi = False
        self.kaydedilen_yol: Optional[str] = None

    def GetFootprints(self) -> List[SahteFootprint]:
        return self._footprints

    def FindNet(self, isim: str) -> Optional[SahteNet]:
        return self._netler.get(isim)

    def GetLayerID(self, isim: str) -> int:
        return {"F.Cu": 0, "In2.Cu": 1, "B.Cu": 2}.get(isim, 0)

    def Add(self, item) -> None:
        self.eklenen_tracklar.append(item)

    def Save(self, yol: str) -> None:
        self.kaydedildi_mi = True
        self.kaydedilen_yol = yol


class TaklitPcbnew:
    def __init__(self, board: SahteBoard):
        self._board = board

    def LoadBoard(self, yol: str) -> SahteBoard:
        return self._board

    def FromMM(self, deger: float) -> int:
        return int(round(deger * NM_PER_MM))

    def VECTOR2I(self, x, y):
        return (x, y)

    def PCB_TRACK(self, board) -> SahteTrack:
        return SahteTrack(board)


def _taklit_pcbnew_yukle(board: SahteBoard) -> TaklitPcbnew:
    taklit = TaklitPcbnew(board)
    sys.modules["pcbnew"] = taklit
    return taklit


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik():
    orijinal = sys.modules.get("pcbnew")
    taklit = TaklitPcbnew(SahteBoard([]))
    sys.modules["pcbnew"] = taklit
    yield taklit
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _gecici_board_yolu(tmp_path, icerik: str = "( orijinal-board-icerigi )") -> str:
    """`diff_ciftlerini_rotala()`'ya verilecek GERÇEK bir geçici dosya
    yolu üretir. GEREKÇE (2026-08-04 düzeltmesi): modül, en az bir çift
    başarıyla routelandığında GERÇEK bir `shutil.copy(board_path,
    board_path + '.bak')` çağrısı yapar (mock'lanmamış, bilinçli — .bak
    disiplini GERÇEK dosya sisteminde doğrulanmalı). Çıplak bir
    `"board.kicad_pcb"` string'i (cwd'ye göre çözülür, çoğu zaman
    mevcut DEĞİL) bu adımda `FileNotFoundError` üretir — önceki test
    suite'inde ~22 testin çoğu bu YÜZDEN, tesadüfen (sadece HANGİ
    çiftin başarılı olduğuna bağlı olarak) geçiyor/kalıyordu. `tmp_path`
    ile HER testin kendi izole, gerçek dosyası olur."""
    yol = tmp_path / "board.kicad_pcb"
    yol.write_text(icerik, encoding="utf-8")
    return str(yol)


def _basit_paralel_board() -> SahteBoard:
    """P: (0,0)->(10,0), N: (0,0.3)->(10,0.3) — tam paralel (açı=0°),
    başarıyla routelanmalı."""
    fp1 = SahteFootprint("J1", [SahtePad("1", 0.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 0.0, 0.3, "ETH_TRD0_N")])
    fp2 = SahteFootprint("D1", [SahtePad("1", 10.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 10.0, 0.3, "ETH_TRD0_N")])
    return SahteBoard([fp1, fp2], netler=["ETH_TRD0_P", "ETH_TRD0_N"])


# ------------------------------------------------------------------
# 1. net_pad_konumlarini_bul
# ------------------------------------------------------------------

def test_net_pad_konumlarini_bul_dogru_pedleri_bulur():
    board = _basit_paralel_board()
    pedler = net_pad_konumlarini_bul(board, "ETH_TRD0_P")
    assert len(pedler) == 2
    assert {(p[2], p[3]) for p in pedler} == {(0.0, 0.0), (10.0, 0.0)}


def test_net_pad_konumlarini_bul_eslesmeyen_net_bos_liste_doner():
    board = _basit_paralel_board()
    assert net_pad_konumlarini_bul(board, "OLMAYAN_NET") == []


# ------------------------------------------------------------------
# 2. en_yakin_eslesmeyi_bul
# ------------------------------------------------------------------

def test_en_yakin_eslesme_ayni_sirali_durumda_dogru_secilir():
    p1, p2 = (0.0, 0.0), (10.0, 0.0)
    n1, n2 = (0.0, 0.3), (10.0, 0.3)
    p_start, n_start, p_end, n_end = en_yakin_eslesmeyi_bul(p1, p2, n1, n2)
    assert p_start == p1 and n_start == n1
    assert p_end == p2 and n_end == n2


def test_en_yakin_eslesme_capraz_sirali_durumda_dogru_secilir():
    """N pad'leri TERS sırada verilse bile (n1 aslında p2'ye yakın),
    fonksiyon FİZİKSEL yakınlığa göre doğru eşleşmeyi bulmalı."""
    p1, p2 = (0.0, 0.0), (10.0, 0.0)
    n1, n2 = (10.0, 0.3), (0.0, 0.3)  # ters sıra
    p_start, n_start, p_end, n_end = en_yakin_eslesmeyi_bul(p1, p2, n1, n2)
    assert p_start == p1 and n_start == (0.0, 0.3)
    assert p_end == p2 and n_end == (10.0, 0.3)


# ------------------------------------------------------------------
# 3. paralellik_acisi_derece
# ------------------------------------------------------------------

def test_paralellik_acisi_tam_paralelde_sifir():
    aci = paralellik_acisi_derece((0.0, 0.0), (10.0, 0.0), (0.0, 0.3), (10.0, 0.3))
    assert aci == pytest.approx(0.0, abs=1e-6)


def test_paralellik_acisi_dik_acida_90():
    aci = paralellik_acisi_derece((0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (0.0, 10.0))
    assert aci == pytest.approx(90.0, abs=1e-6)


def test_paralellik_acisi_sifir_uzunluklu_vektorde_180_doner():
    """Start==End (sıfır-uzunluklu vektör) TANIMSIZ bir açı — fonksiyon
    sessizce 0 VARSAYMAZ, en güvensiz değeri (180) döner."""
    aci = paralellik_acisi_derece((5.0, 5.0), (5.0, 5.0), (0.0, 0.0), (10.0, 0.0))
    assert aci == 180.0


# ------------------------------------------------------------------
# 4. diff_ciftlerini_rotala — ana orkestrasyon
# ------------------------------------------------------------------

def test_basit_paralel_cift_basariyla_routelanir_ve_kilitlenir(tmp_path):
    board = _basit_paralel_board()
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path), [DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N")],
    )

    assert bulgu.durum.value == "PASS"
    assert bulgu.taranan == 1
    assert len(sonuclar) == 1
    assert sonuclar[0].basarili is True
    assert len(board.eklenen_tracklar) == 2
    for track in board.eklenen_tracklar:
        assert track.locked is True, "EN KRİTİK KURAL: her çizilen track LOCKED olmalı"


def test_acili_fark_cok_buyukse_basarisiz_ve_hicbir_track_cizilmez(tmp_path):
    """P: (0,0)->(10,0) [0°], N: (0,0)->(0,10) [90°] — tolerans (15°)
    aşıldığı için REDDEDİLMELİ, board'a HİÇBİR ŞEY yazılmamalı."""
    fp1 = SahteFootprint("J1", [SahtePad("1", 0.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 0.0, 0.0, "ETH_TRD0_N")])
    fp2 = SahteFootprint("D1", [SahtePad("1", 10.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 0.0, 10.0, "ETH_TRD0_N")])
    board = SahteBoard([fp1, fp2], netler=["ETH_TRD0_P", "ETH_TRD0_N"])
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path), [DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N")],
    )

    assert bulgu.durum.value == "FAIL"
    assert sonuclar[0].basarili is False
    assert "pair twist" in sonuclar[0].detay.lower() or "açı" in sonuclar[0].detay
    assert board.eklenen_tracklar == []
    assert board.kaydedildi_mi is False


def test_3_pedli_net_basarisiz_steiner_onerisi_verir(tmp_path):
    fp1 = SahteFootprint("J1", [
        SahtePad("1", 0.0, 0.0, "SIG_P"), SahtePad("2", 0.0, 0.3, "SIG_N"),
        SahtePad("3", 5.0, 0.0, "SIG_P"),  # 3. pad -> P net'i artık 3-pedli
    ])
    board = SahteBoard([fp1], netler=["SIG_P", "SIG_N"])
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(_gecici_board_yolu(tmp_path), [DiffPairNeti("SIG_P", "SIG_N")])

    assert sonuclar[0].basarili is False
    assert "steiner_agaci_motoru" in sonuclar[0].detay
    assert board.eklenen_tracklar == []


def test_net_board_seviyesinde_bulunamazsa_basarisiz(tmp_path):
    """Pad'ler netname taşısa bile board.FindNet() net'i döndürmezse
    (tutarsız/bozuk board verisi) fail-closed davranmalı."""
    board = _basit_paralel_board()
    board._netler = {}  # net kaydı YOK
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path), [DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N")],
    )

    assert sonuclar[0].basarili is False
    assert "FindNet" in sonuclar[0].detay
    assert board.eklenen_tracklar == []


def test_bos_cift_listesi_kapsam_yok_doner(tmp_path):
    board = _basit_paralel_board()
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(_gecici_board_yolu(tmp_path), [])

    assert bulgu.durum.value == "KAPSAM_YOK"
    assert bulgu.taranan == 0
    assert sonuclar == []


def test_karisik_basarili_ve_basarisiz_ciftler_dogru_raporlanir(tmp_path):
    fp1 = SahteFootprint("J1", [
        SahtePad("1", 0.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 0.0, 0.3, "ETH_TRD0_N"),
        SahtePad("3", 0.0, 1.0, "USB_P"), SahtePad("4", 0.0, 1.0, "USB_N"),
    ])
    fp2 = SahteFootprint("D1", [
        SahtePad("1", 10.0, 0.0, "ETH_TRD0_P"), SahtePad("2", 0.0, 10.0, "ETH_TRD0_N"),  # 90° -> FAIL
        SahtePad("3", 10.0, 1.0, "USB_P"), SahtePad("4", 10.0, 1.3, "USB_N"),  # paralel -> PASS
    ])
    board = SahteBoard([fp1, fp2], netler=["ETH_TRD0_P", "ETH_TRD0_N", "USB_P", "USB_N"])
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path),
        [DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N"), DiffPairNeti("USB_P", "USB_N")],
    )

    assert bulgu.taranan == 2
    assert len(bulgu.ihlaller) == 1
    basarili_haritasi = {s.p_net_adi: s.basarili for s in sonuclar}
    assert basarili_haritasi["ETH_TRD0_P"] is False
    assert basarili_haritasi["USB_P"] is True
    assert len(board.eklenen_tracklar) == 2  # sadece USB çifti için (2 track)
    assert board.kaydedildi_mi is True  # en az bir başarılı -> kaydedildi


def test_skew_dogru_hesaplanir(tmp_path):
    """P uzunluğu 10.0mm, N uzunluğu farklı bir başlangıç noktasıyla
    biraz daha uzun (10.05mm) olacak şekilde kurulup skew doğrulanır."""
    fp1 = SahteFootprint("J1", [SahtePad("1", 0.0, 0.0, "SIG_P"), SahtePad("2", 0.0, 0.3, "SIG_N")])
    fp2 = SahteFootprint("D1", [SahtePad("1", 10.0, 0.0, "SIG_P"), SahtePad("2", 10.05, 0.3, "SIG_N")])
    board = SahteBoard([fp1, fp2], netler=["SIG_P", "SIG_N"])
    _taklit_pcbnew_yukle(board)

    bulgu, sonuclar = diff_ciftlerini_rotala(_gecici_board_yolu(tmp_path), [DiffPairNeti("SIG_P", "SIG_N")])

    assert sonuclar[0].basarili is True
    assert sonuclar[0].p_uzunluk_mm == pytest.approx(10.0, abs=1e-3)
    assert sonuclar[0].n_uzunluk_mm == pytest.approx(10.05, abs=1e-3)
    assert sonuclar[0].skew_mm == pytest.approx(0.05, abs=1e-3)


def test_ozel_genislik_ve_katman_kullanilir(tmp_path):
    board = _basit_paralel_board()
    _taklit_pcbnew_yukle(board)

    cift = DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N", genislik_mm=0.15, katman="In2.Cu")
    diff_ciftlerini_rotala(_gecici_board_yolu(tmp_path), [cift])

    for track in board.eklenen_tracklar:
        assert track.width == pytest.approx(0.15 * NM_PER_MM)
        assert track.layer == 1  # In2.Cu -> SahteBoard.GetLayerID eşlemesi


def test_ozel_tolerans_parametresi_uygulanir(tmp_path):
    """20° açı farkı, varsayılan 15° tolerans ile REDDEDİLİR ama
    tolerans 25°'ye yükseltilince KABUL EDİLİR."""
    import math

    fp1 = SahteFootprint("J1", [SahtePad("1", 0.0, 0.0, "SIG_P"), SahtePad("2", 0.0, 0.3, "SIG_N")])
    aci_rad = math.radians(20)
    n_end = (10.0 * math.cos(aci_rad), 10.0 * math.sin(aci_rad) + 0.3)
    fp2 = SahteFootprint("D1", [SahtePad("1", 10.0, 0.0, "SIG_P"), SahtePad("2", n_end[0], n_end[1], "SIG_N")])
    board = SahteBoard([fp1, fp2], netler=["SIG_P", "SIG_N"])
    _taklit_pcbnew_yukle(board)

    _, sonuc_varsayilan = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path), [DiffPairNeti("SIG_P", "SIG_N")],
    )
    assert sonuc_varsayilan[0].basarili is False

    board2 = SahteBoard([fp1, fp2], netler=["SIG_P", "SIG_N"])
    _taklit_pcbnew_yukle(board2)
    _, sonuc_genis_tolerans = diff_ciftlerini_rotala(
        _gecici_board_yolu(tmp_path), [DiffPairNeti("SIG_P", "SIG_N")], tolerans_derece=25.0,
    )
    assert sonuc_genis_tolerans[0].basarili is True


# ------------------------------------------------------------------
# 5. pcbnew yokken KAPSAM_YOK (fail-closed, MASTER_RULEBOOK kuralı)
# ------------------------------------------------------------------

class TestPcbnewYokFallback:
    @pytest.fixture(autouse=True)
    def _pcbnew_yi_gercekten_kaldir(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        yield

    def test_pcbnew_yokken_kapsam_yok_doner(self):
        bulgu, sonuclar = diff_ciftlerini_rotala("board.kicad_pcb", [DiffPairNeti("A_P", "A_N")])
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0
        assert sonuclar == []
        assert "pcbnew modülü bulunamadı" in bulgu.detay


# ------------------------------------------------------------------
# 6. Gerçek dosya sistemi — .bak yedek disiplini (gerçek tmp_path, mock pcbnew)
# ------------------------------------------------------------------

def test_basarili_route_sonrasi_gercek_bak_dosyasi_olusturulur(tmp_path):
    board_dosyasi = tmp_path / "board.kicad_pcb"
    orijinal_icerik = "( orijinal-board-icerigi )"
    board_dosyasi.write_text(orijinal_icerik, encoding="utf-8")

    board = _basit_paralel_board()
    _taklit_pcbnew_yukle(board)

    diff_ciftlerini_rotala(str(board_dosyasi), [DiffPairNeti("ETH_TRD0_P", "ETH_TRD0_N")])

    yedek = tmp_path / "board.kicad_pcb.bak"
    assert yedek.is_file()
    assert yedek.read_text(encoding="utf-8") == orijinal_icerik
    assert board.kaydedildi_mi is True
    assert board.kaydedilen_yol == str(board_dosyasi)


def test_basarisiz_ciftte_bak_dosyasi_olusturulmaz(tmp_path):
    board_dosyasi = tmp_path / "board.kicad_pcb"
    board_dosyasi.write_text("( orijinal )", encoding="utf-8")

    fp1 = SahteFootprint("J1", [SahtePad("1", 0.0, 0.0, "P"), SahtePad("2", 0.0, 0.0, "N")])
    fp2 = SahteFootprint("D1", [SahtePad("1", 10.0, 0.0, "P"), SahtePad("2", 0.0, 10.0, "N")])
    board = SahteBoard([fp1, fp2], netler=["P", "N"])
    _taklit_pcbnew_yukle(board)

    diff_ciftlerini_rotala(str(board_dosyasi), [DiffPairNeti("P", "N")])

    assert not (tmp_path / "board.kicad_pcb.bak").is_file()
    assert board.kaydedildi_mi is False
