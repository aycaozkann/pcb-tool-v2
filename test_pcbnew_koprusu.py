"""pcbnew_koprusu.py için test suite (GÖREV 2 — 2026-07-31).

Bu test dosyası, `test_pcb_carpisma_radari.py` ile AYNI disiplini izler:
gerçek `pcbnew` modülünü import ETMEZ (bu ortamda kurulu değil) — bunun
yerine `sys.modules["pcbnew"]`'e aşağıdaki taklit modülü yerleştirir ve
`kanal_ciftlerini_bul` / `gercek_boarddan_maske_baraji_kontrolu` /
`stitch_yogunlugu_kontrolu` fonksiyonlarını duck-typing mock nesneleriyle
test eder.

KİLİTLENEN ÜÇ REGRESYON (denetimde tespit edildi, gerçek board'larda
yaşanmıştı — bkz. `HAFIZA/Hafiza_Defteri.md`):
  1. `kanal_ciftlerini_bul`: `pad_uzunlugu_mm = h1 + h2` OLMALI — eskiden
     `(h1 + h2) * 2` vardı; bu, `kanal_genisligi`'ni gerçek boşluktan küçük
     gösterip sıradan 2-pedli pasifleri "kanal yok, kısa devre" diye
     YANLIŞ işaretliyordu (gerçek board'da 175.815 sahte-pozitif).
  2. `gercek_boarddan_maske_baraji_kontrolu`: bir kanala yalnızca orta
     noktasına `yakinlik_mm=0.5` içinde kalan izler atfedilmeli — eskiden
     HER kanal x HER iz kombinasyonu (yakınlık kontrolsüz) taranıyordu.
  3. `stitch_yogunlugu_kontrolu`: kart kenarı `TransformShapeToPolygon` ile
     polygonlaştırılmış GERÇEK dış hattan örneklenmeli — eskiden her
     Edge.Cuts öğesi `GetStart()`/`GetEnd()` ile DÜZ DOĞRU gibi yorumlanıp
     (gr_circle/gr_arc'ta bu noktalar merkez/yardımcı) kart merkezinden
     dışarı sahte radyal çizgiler üretiyordu.
"""

import sys
from typing import List, Optional, Tuple

import pytest

import pcbnew_koprusu
from pcbnew_koprusu import (
    gercek_boarddan_maske_baraji_kontrolu,
    kanal_ciftlerini_bul,
    stitch_yogunlugu_kontrolu,
)
from pcb_highspeed_escape import kanal_genisligi_hesapla_mm

NM_PER_MM = 1_000_000


# ------------------------------------------------------------------
# Taklit `pcbnew` modülü + mock nesneler (tüm değerler NANOMETRE)
# ------------------------------------------------------------------

class SahteNokta:
    def __init__(self, x_mm: float, y_mm: float):
        self.x = int(round(x_mm * NM_PER_MM))
        self.y = int(round(y_mm * NM_PER_MM))


class SahtePolySet:
    def __init__(self):
        self._outlines: List[List[SahteNokta]] = []

    def OutlineCount(self) -> int:
        return len(self._outlines)

    def Outline(self, i: int) -> "SahteOutline":
        return SahteOutline(self._outlines[i])

    def PointCount(self) -> int:
        return sum(len(o) for o in self._outlines)


class SahteOutline:
    def __init__(self, noktalar: List[SahteNokta]):
        self._noktalar = noktalar

    def PointCount(self) -> int:
        return len(self._noktalar)

    def CPoint(self, i: int) -> SahteNokta:
        return self._noktalar[i]


class SahteCizim:
    """Edge.Cuts çizim öğesi taklidi. TUZAK (gerçek pcbnew'de gr_circle/
    gr_arc): `GetStart()`/`GetEnd()` ÇEVRE noktalarını DEĞİL merkez/yardımcı
    noktaları döndürür — eski bug bunları doğru gibi yorumluyordu; doğru
    çevre bilgisi yalnızca `TransformShapeToPolygon`'dan gelir."""

    def __init__(self, katman, poligon_noktalari_mm: List[Tuple[float, float]]):
        self._katman = katman
        self._noktalar = [SahteNokta(*n) for n in poligon_noktalari_mm]
        self.transform_cagrildi = False

    def GetLayer(self):
        return self._katman

    def GetStart(self) -> SahteNokta:
        # merkez (ör. (0,0)) — gerçek gr_circle'ın GetStart'i gibi YANILTICI
        return SahteNokta(0, 0)

    def GetEnd(self) -> SahteNokta:
        # yardımcı nokta (ör. çevre üzerinde bir nokta) — doğru çevre DEĞİL
        return SahteNokta(10, 0)

    def TransformShapeToPolygon(self, poly: SahtePolySet, *args, **kwargs) -> None:
        self.transform_cagrildi = True
        poly._outlines = [self._noktalar]


class SahtePad:
    def __init__(
        self,
        numara: str,
        x_mm: float,
        y_mm: float,
        boy_x_mm: float,
        boy_y_mm: float,
        npth: bool = False,
        mask_exp_mm: float = 0.05,
    ):
        self._numara = numara
        self._konum = SahteNokta(x_mm, y_mm)
        self._boy_x = int(round(boy_x_mm * NM_PER_MM))
        self._boy_y = int(round(boy_y_mm * NM_PER_MM))
        self._npth = npth
        self._mask_exp = int(round(mask_exp_mm * NM_PER_MM))

    def GetNumber(self) -> str:
        return self._numara

    def GetPosition(self) -> SahteNokta:
        return self._konum

    def GetSizeX(self) -> int:
        return self._boy_x

    def GetSizeY(self) -> int:
        return self._boy_y

    def GetAttribute(self) -> str:
        return "NPTH" if self._npth else "SMD"

    def GetSolderMaskExpansion(self, layer) -> int:
        return self._mask_exp


class SahteFootprint:
    def __init__(self, ref: str, padlar: List[SahtePad]):
        self._ref = ref
        self._padlar = padlar

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[SahtePad]:
        return self._padlar


class SahteIz:
    def __init__(
        self,
        tip: str,
        baslangic_mm: Tuple[float, float],
        bitis_mm: Tuple[float, float],
        genislik_mm: float = 0.2,
        net: str = "",
        ust_katman: int = 0,
        alt_katman: int = 1,
    ):
        self._tip = tip
        self._s = SahteNokta(*baslangic_mm)
        self._e = SahteNokta(*bitis_mm)
        self._genislik = int(round(genislik_mm * NM_PER_MM))
        self._net = net
        self._ust = ust_katman
        self._alt = alt_katman

    def GetClass(self) -> str:
        return self._tip

    def GetStart(self) -> SahteNokta:
        return self._s

    def GetEnd(self) -> SahteNokta:
        return self._e

    def GetWidth(self) -> int:
        return self._genislik

    def GetNetname(self) -> str:
        return self._net

    def GetPosition(self) -> SahteNokta:
        return self._s

    def TopLayer(self) -> int:
        return self._ust

    def BottomLayer(self) -> int:
        return self._alt


class SahteBoard:
    def __init__(self, footprints, izler=None, cizimler=None):
        self._footprints = footprints
        self._izler = izler or []
        self._cizimler = cizimler or []

    def GetFootprints(self):
        return self._footprints

    def GetTracks(self):
        return self._izler

    def GetDrawings(self):
        return self._cizimler


class TaklitPcbnew:
    """`sys.modules["pcbnew"]`'e yerleştirilen taklit — yalnızca
    `pcbnew_koprusu` fonksiyonlarının kullandığı sabitler/fabrika."""

    PAD_ATTRIB_NPTH = "NPTH"
    F_Cu = 0
    Edge_Cuts = "Edge.Cuts"
    UNDEFINED_LAYER = -999
    ERROR_INSIDE = 0

    def __init__(self, board: SahteBoard):
        self._board = board

    def FromMM(self, deger: float) -> int:
        return int(round(deger * NM_PER_MM))

    def LoadBoard(self, yol: str) -> SahteBoard:
        return self._board

    def SHAPE_POLY_SET(self) -> SahtePolySet:
        return SahtePolySet()


def _taklit_pcbnew_yukle(board: SahteBoard) -> TaklitPcbnew:
    taklit = TaklitPcbnew(board)
    sys.modules["pcbnew"] = taklit
    return taklit


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik(monkeypatch):
    """Her testten önce `sys.modules["pcbnew"]`'e boş bir taklit yerleştirir;
    testler `_taklit_pcbnew_yukle()` ile kendi board'unu kurar. Test bitince
    gerçek (yok olan) pcbnew durumu geri gelir."""
    orijinal = sys.modules.get("pcbnew")
    taklit = TaklitPcbnew(SahteBoard([]))
    sys.modules["pcbnew"] = taklit
    yield taklit
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _iki_pedli_pasif(aralik_mm: float = 2.0, pad_boyu_mm: float = 1.0) -> SahteFootprint:
    """Merkez-merkez `aralik_mm`'de iki adet `pad_boyu_mm`'lik SMD pedli
    sıradan bir pasif (kondansatör gibi) — regresyon-1'in ana senaryosu."""
    y = pad_boyu_mm / 2.0
    p1 = SahtePad("1", -aralik_mm / 2.0, 0.0, pad_boyu_mm, pad_boyu_mm)
    p2 = SahtePad("2", aralik_mm / 2.0, 0.0, pad_boyu_mm, pad_boyu_mm)
    return SahteFootprint("C1", [p1, p2])


# ------------------------------------------------------------------
# 1. REGRESYON-1: kanal_ciftlerini_bul — pad_uzunlugu_mm = h1 + h2
# ------------------------------------------------------------------

class TestKanalCiftleriniBul:
    def test_pad_uzunlugu_h1_art_h2_olmalı(self):
        """REGRESYON-1 kilidi: `kanal.pad_uzunlugu_mm` == h1+h2 (=1.0) OLMALI.
        Eski `(h1+h2)*2` (=2.0) olsaydı `kanal_genisligi` 0 çıkar ve
        `maske_baraji_kontrolu` "kanal yok, kısa devre" YANLIŞ-pozitif üretirdi."""
        board = SahteBoard([_iki_pedli_pasif(aralik_mm=2.0, pad_boyu_mm=1.0)])
        _taklit_pcbnew_yukle(board)

        ciftler = kanal_ciftlerini_bul(board)

        assert len(ciftler) == 1
        cift = ciftler[0]
        # h1 = abs(0.5*1) + abs(0) = 0.5, h2 = 0.5  ->  h1+h2 = 1.0
        assert cift["kanal"].pad_uzunlugu_mm == pytest.approx(1.0)
        # kilit: kanal genişliği gerçek boşluğa (mesafe - h1 - h2) eşit olmalı
        assert kanal_genisligi_hesapla_mm(cift["kanal"]) == pytest.approx(1.0)

    def test_bosluk_ve_orta_nokta_dogru(self):
        board = SahteBoard([_iki_pedli_pasif(aralik_mm=2.0, pad_boyu_mm=1.0)])
        _taklit_pcbnew_yukle(board)

        cift = kanal_ciftlerini_bul(board)[0]

        assert cift["pad_a"] == "C1.1"
        assert cift["pad_b"] == "C1.2"
        assert cift["bosluk_mm"] == pytest.approx(1.0)
        assert cift["orta_nokta_mm"][0] == pytest.approx(0.0)
        assert cift["orta_nokta_mm"][1] == pytest.approx(0.0)

    def test_mask_expansion_padden_alinir(self):
        p1 = SahtePad("1", 0.0, 0.0, 1.0, 1.0, mask_exp_mm=0.12)
        p2 = SahtePad("2", 2.0, 0.0, 1.0, 1.0, mask_exp_mm=0.12)
        board = SahteBoard([SahteFootprint("R1", [p1, p2])])
        _taklit_pcbnew_yukle(board)

        cift = kanal_ciftlerini_bul(board)[0]

        assert cift["kanal"].mask_expansion_mm == pytest.approx(0.12)

    def test_npth_pad_aday_olarak_alınmaz(self):
        p1 = SahtePad("1", 0.0, 0.0, 1.0, 1.0)
        p2 = SahtePad("2", 2.0, 0.0, 1.0, 1.0, npth=True)
        board = SahteBoard([SahteFootprint("J1", [p1, p2])])
        _taklit_pcbnew_yukle(board)

        assert kanal_ciftlerini_bul(board) == []

    def test_ayni_footprint_ayni_pad_numarasi_eslenir(self):
        # aynı ref + aynı numara -> pad çifti adayı DEĞİL (kendi iki pad'i değil)
        p1 = SahtePad("1", 0.0, 0.0, 1.0, 1.0)
        p2 = SahtePad("1", 2.0, 0.0, 1.0, 1.0)  # aynı numara, farklı yer
        board = SahteBoard([SahteFootprint("U1", [p1, p2])])
        _taklit_pcbnew_yukle(board)

        assert kanal_ciftlerini_bul(board) == []

    def test_arama_mm_disindaki_kanal_elenir(self):
        board = SahteBoard([_iki_pedli_pasif(aralik_mm=3.0, pad_boyu_mm=1.0)])
        _taklit_pcbnew_yukle(board)

        assert kanal_ciftlerini_bul(board, arama_mm=1.0) == []
        assert len(kanal_ciftlerini_bul(board, arama_mm=3.0)) == 1

    def test_uyuşmayan_köşegen_yön_h1_hesabı(self):
        # 1x1 pad'ler (0,0) ve (1,0.5)'te: mesafe=1.118mm, h1=h2≈0.671mm
        # -> bosluk ≈ -0.22mm (pad'ler çakışır) -> elenmeli.
        p1 = SahtePad("1", 0.0, 0.0, 1.0, 1.0)
        p2 = SahtePad("2", 1.0, 0.5, 1.0, 1.0)
        board = SahteBoard([SahteFootprint("Q1", [p1, p2])])
        _taklit_pcbnew_yukle(board)

        assert kanal_ciftlerini_bul(board) == []


# ------------------------------------------------------------------
# 2. REGRESYON-2: gercek_boarddan_maske_baraji_kontrolu — 0.5mm yakınlık
# ------------------------------------------------------------------

def _maske_kanal_boardu():
    """Orta noktası (1.0, 0.0) olan bir kanal (pad'ler (0,0)-(2,0), her biri
    1mm)."""
    p1 = SahtePad("1", 0.0, 0.0, 1.0, 1.0)
    p2 = SahtePad("2", 2.0, 0.0, 1.0, 1.0)
    return SahteBoard([SahteFootprint("U1", [p1, p2])])


class TestGercekBoarddanMaskeBaraji:
    def test_kanaldan_gecen_iz_ihlal_uretir(self, monkeypatch):
        # kanal ortasından geçen 0.6mm iz -> maske barajı < 0.20mm -> ihlal
        iz = SahteIz("PCB_TRACK", (0.5, -0.5), (1.5, 0.5), genislik_mm=0.6, net="5V")
        board = _maske_kanal_boardu()
        board._izler = [iz]
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1
        assert bulgu.ihlaller, "kanal ortasından geçen kalın iz ihlal üretmeli"
        assert bulgu.ihlaller[0]["pad_a"] == "U1.1"
        assert bulgu.ihlaller[0]["pad_b"] == "U1.2"
        assert bulgu.ihlaller[0]["net"] == "5V"
        assert bulgu.gecti_mi is False

    def test_ince_iz_ihlal_uretmez(self, monkeypatch):
        iz = SahteIz("PCB_TRACK", (0.5, -0.5), (1.5, 0.5), genislik_mm=0.2, net="AUDIO")
        board = _maske_kanal_boardu()
        board._izler = [iz]
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1
        assert bulgu.ihlaller == []
        assert bulgu.gecti_mi is True

    def test_uzak_iz_kanala_atfedilmez(self, monkeypatch):
        """REGRESYON-2 kilidi: kanal orta noktasından 0.5mm'den uzak iz
        (burada 2.5mm) o kanala atfedilmemeli — eski kod HER kanal x HER iz
        kombinasyonunu tarayıp uzaktaki kalın izi alakasız kanala ihlal
        yazıyordu."""
        iz = SahteIz("PCB_TRACK", (3.0, 0.0), (4.0, 0.0), genislik_mm=0.9, net="AUDIO")
        board = _maske_kanal_boardu()
        board._izler = [iz]
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1
        assert bulgu.ihlaller == []
        assert bulgu.gecti_mi is True

    def test_arc_iz_havuzuna_alınmaz(self, monkeypatch):
        """TUZAK (a): `GetClass() == "PCB_ARC"` olan iz `PCB_TRACK` havuzuna
        GİRMEMELİ — yoksa yaylar pad'e değen düz iz gibi yanlış raporlanır."""
        iz = SahteIz("PCB_ARC", (0.5, -0.5), (1.5, 0.5), genislik_mm=0.6, net="5V")
        board = _maske_kanal_boardu()
        board._izler = [iz]
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1
        assert bulgu.ihlaller == []
        assert bulgu.gecti_mi is True

    def test_kanaldan_iz_gecmiyorsa_ihlal_olmaz(self, monkeypatch):
        board = _maske_kanal_boardu()  # iz yok
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1
        assert bulgu.ihlaller == []
        assert bulgu.gecti_mi is True

    def test_kanal_yoksa_kapsam_yok(self, monkeypatch):
        board = SahteBoard([])
        _taklit_pcbnew_yukle(board)

        bulgu = gercek_boarddan_maske_baraji_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 0
        assert bulgu.durum.name == "KAPSAM_YOK"
        assert bulgu.gecti_mi is False


# ------------------------------------------------------------------
# 3. REGRESYON-3: stitch_yogunlugu_kontrolu — polygonlaştırılmış kenar
# ------------------------------------------------------------------

class TestStitchYogunlugu:
    def test_kart_kenari_polygondan_okunur_start_end_degil(self, monkeypatch):
        """REGRESYON-3 kilidi: `_kart_kenari_noktalari` kenar noktalarını
        `TransformShapeToPolygon` (GERÇEK çevre) üzerinden almalı — çizimin
        `GetStart()`/`GetEnd()` değerleri değil (gr_circle/gr_arc'ta bunlar
        merkez/yardımcı noktalardır ve eski bug kart merkezinden dışarı
        sahte radyal çizgiler üretiyordu). Bu testte çizimin doğru çevre
        bilgisi YALNIZCA polygon'dadır."""
        kenar_noktalari = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        cizim = SahteCizim("Edge.Cuts", kenar_noktalari)
        board = SahteBoard([], cizimler=[cizim])
        _taklit_pcbnew_yukle(board)

        noktalar = pcbnew_koprusu._kart_kenari_noktalari(board)

        assert cizim.transform_cagrildi is True
        assert noktalar == [(x, y) for x, y in kenar_noktalari]

    def test_gnd_via_yoksa_kapsam_yok(self, monkeypatch):
        """GND via YOKSA PASS DEĞİL KAPSAM_YOK dönmeli — 'via yok, o yüzden
        ihlal de yok' yanlış bir PASS olurdu."""
        iz = SahteIz("PCB_VIA", (5.0, 5.0), (5.0, 5.0), net="5V")
        board = SahteBoard([], izler=[iz])
        _taklit_pcbnew_yukle(board)

        bulgu = stitch_yogunlugu_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 0
        assert bulgu.durum.name == "KAPSAM_YOK"
        assert bulgu.gecti_mi is False

    def test_aralikli_gnd_via_pass(self, monkeypatch):
        """Kart ortasında tek GND via + hedef λ/20 >= köşe mesafesi -> tüm
        kenar örnekleri hedef içinde -> PASS."""
        # 2x2 kart, merkezde (1,1) GND via. f_diz=3 -> λ/20 ≈ 2.36mm.
        # köşe uzaklığı 1.414mm < 2.36mm -> ihlal yok.
        kenar = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
        cizim = SahteCizim("Edge.Cuts", kenar)
        via = SahteIz("PCB_VIA", (1.0, 1.0), (1.0, 1.0), net="GND", ust_katman=0, alt_katman=1)
        board = SahteBoard([], izler=[via], cizimler=[cizim])
        _taklit_pcbnew_yukle(board)

        bulgu = stitch_yogunlugu_kontrolu("board.kicad_pcb", f_diz_ghz=3.0)

        assert bulgu.taranan > 0
        assert bulgu.ihlaller == []
        assert bulgu.gecti_mi is True

    def test_sintirli_gnd_via_fail(self, monkeypatch):
        """Hedef λ/20 kenardan KÜÇÜK -> kenar örnekleri hedefi aşar -> FAIL
        (kenar örneklemesinin ÇALIŞTIĞINI kanıtlar)."""
        kenar = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        cizim = SahteCizim("Edge.Cuts", kenar)
        via = SahteIz("PCB_VIA", (5.0, 5.0), (5.0, 5.0), net="GND", ust_katman=0, alt_katman=1)
        board = SahteBoard([], izler=[via], cizimler=[cizim])
        _taklit_pcbnew_yukle(board)

        bulgu = stitch_yogunlugu_kontrolu("board.kicad_pcb", f_diz_ghz=5.0)

        assert bulgu.taranan > 0
        assert bulgu.ihlaller, "λ/20 kart kenarından küçükse kenar ihlali olmalı"
        assert all(i["tur"] == "kenar" for i in bulgu.ihlaller)
        assert bulgu.gecti_mi is False

    def test_sinyal_via_gnd_via_denetimi(self, monkeypatch):
        """Katman değiştiren sinyal via'sının en yakın GND via'ya mesafesi
        hedeften büyükse 'via_donusu' ihlali üretilmeli."""
        kenar = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        cizim = SahteCizim("Edge.Cuts", kenar)
        gnd_via = SahteIz("PCB_VIA", (5.0, 5.0), (5.0, 5.0), net="GND", ust_katman=0, alt_katman=1)
        sinyal_via = SahteIz("PCB_VIA", (0.5, 0.5), (0.5, 0.5), net="DATA", ust_katman=0, alt_katman=1)
        board = SahteBoard([], izler=[gnd_via, sinyal_via], cizimler=[cizim])
        _taklit_pcbnew_yukle(board)

        bulgu = stitch_yogunlugu_kontrolu("board.kicad_pcb", f_diz_ghz=5.0)

        turler = [i["tur"] for i in bulgu.ihlaller]
        assert "via_donusu" in turler
