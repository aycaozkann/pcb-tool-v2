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
    net_iz_ve_via_listesi_topla,
    stitch_yogunlugu_kontrolu,
    via_in_pad_kontrolu,
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


class SahtePolygonAlan:
    """`PAD.GetEffectivePolygon(layer)` taklidi — sadece `Collide(nokta)`
    gerektiren via-in-pad testi için, dikdörtgen pad alanı yaklaşımı."""

    def __init__(self, merkez: SahteNokta, boy_x_nm: int, boy_y_nm: int):
        self._merkez = merkez
        self._yarim_x = boy_x_nm / 2.0
        self._yarim_y = boy_y_nm / 2.0

    def Collide(self, nokta: SahteNokta) -> bool:
        return (
            abs(nokta.x - self._merkez.x) <= self._yarim_x
            and abs(nokta.y - self._merkez.y) <= self._yarim_y
        )


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
        attribute: str = "SMD",
        katmanlar: Optional[List[int]] = None,
        net: str = "",
    ):
        self._numara = numara
        self._konum = SahteNokta(x_mm, y_mm)
        self._boy_x = int(round(boy_x_mm * NM_PER_MM))
        self._boy_y = int(round(boy_y_mm * NM_PER_MM))
        self._npth = npth
        self._mask_exp = int(round(mask_exp_mm * NM_PER_MM))
        self._attribute = "NPTH" if npth else attribute
        # None -> her katmanda var sayılır (via_in_pad testleri için yeterli
        # basitleştirme; annular_ring/maske_baraji testleri katman ayrımına
        # bakmıyor, mevcut davranış BOZULMADI).
        self._katmanlar = katmanlar
        self._net = net

    def GetNumber(self) -> str:
        return self._numara

    def GetNetname(self) -> str:
        return self._net

    def GetPosition(self) -> SahteNokta:
        return self._konum

    def GetSizeX(self) -> int:
        return self._boy_x

    def GetSizeY(self) -> int:
        return self._boy_y

    def GetAttribute(self) -> str:
        return self._attribute

    def GetSolderMaskExpansion(self, layer) -> int:
        return self._mask_exp

    def IsOnLayer(self, layer) -> bool:
        return self._katmanlar is None or layer in self._katmanlar

    def GetEffectivePolygon(self, layer) -> SahtePolygonAlan:
        return SahtePolygonAlan(self._konum, self._boy_x, self._boy_y)


class SahteFPID:
    """`footprint.GetFPID().GetLibItemName()` taklidi — `str()` ile
    doğrudan paket adına (ör. 'SOT-23-6', 'C_0402_1005Metric') çevrilir,
    gerçek pcbnew'in `UTF8` proxy nesnesiyle DAVRANIŞSAL olarak uyumlu."""

    def __init__(self, lib_item_adi: str):
        self._ad = lib_item_adi

    def GetLibItemName(self) -> "SahteFPID":
        return self

    def __str__(self) -> str:
        return self._ad


class SahteFootprint:
    def __init__(
        self, ref: str, padlar: List[SahtePad],
        fpid: str = "", deger: str = "", x_mm: float = 0.0, y_mm: float = 0.0,
    ):
        self._ref = ref
        self._padlar = padlar
        self._fpid = fpid
        self._deger = deger
        self._konum = SahteNokta(x_mm, y_mm)

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[SahtePad]:
        return self._padlar

    def GetFPID(self) -> SahteFPID:
        return SahteFPID(self._fpid)

    def GetValue(self) -> str:
        return self._deger

    def GetPosition(self) -> SahteNokta:
        return self._konum


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
        katman: int = 0,
    ):
        self._tip = tip
        self._s = SahteNokta(*baslangic_mm)
        self._e = SahteNokta(*bitis_mm)
        self._genislik = int(round(genislik_mm * NM_PER_MM))
        self._net = net
        self._ust = ust_katman
        self._alt = alt_katman
        self._katman = katman

    def GetClass(self) -> str:
        return self._tip

    def GetStart(self) -> SahteNokta:
        return self._s

    def GetEnd(self) -> SahteNokta:
        return self._e

    def GetWidth(self, *_katman_argumani) -> int:
        # gerçek pcbnew'de PCB_TRACK.GetWidth() argümansız, PCB_VIA.GetWidth(katman)
        # BİR argüman ister (tuzak (d)/(e), bkz. dosya başlığı) — bu taklit
        # HER İKİSİNİ de kabul eder, verilen argümanı yok sayar.
        return self._genislik

    def GetNetname(self) -> str:
        return self._net

    def GetPosition(self) -> SahteNokta:
        return self._s

    def TopLayer(self) -> int:
        return self._ust

    def BottomLayer(self) -> int:
        return self._alt

    def GetLayer(self) -> int:
        return self._katman


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
    PAD_ATTRIB_SMD = "SMD"
    PAD_ATTRIB_CONN = "CONN"
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
# 0b. net_iz_ve_via_listesi_topla — ortak yardımcı
# ------------------------------------------------------------------

class TestNetIzVeViaListesiTopla:
    """`net_iz_ve_via_listesi_topla()` — `openems_koprusu.py::geometri_cikar()`
    gibi başka köprülerin tekrar yazmak yerine ÇAĞIRACAĞI ortak yardımcı."""

    def test_sadece_hedef_nete_ait_izler_toplanir(self):
        hedef = SahteIz("PCB_TRACK", (0.0, 0.0), (1.0, 0.0), genislik_mm=0.2, net="MIPI_P", katman=0)
        diger = SahteIz("PCB_TRACK", (0.0, 1.0), (1.0, 1.0), genislik_mm=0.2, net="MIPI_N", katman=0)
        board = SahteBoard([], izler=[hedef, diger])

        sonuc = net_iz_ve_via_listesi_topla(board, "MIPI_P")

        assert len(sonuc["izler"]) == 1
        assert sonuc["izler"][0]["baslangic_mm"] == (0.0, 0.0)
        assert sonuc["izler"][0]["bitis_mm"] == (1.0, 0.0)
        assert sonuc["izler"][0]["genislik_mm"] == pytest.approx(0.2)
        assert sonuc["vialar"] == []

    def test_pcb_arc_tuzagi_atlanmaz(self):
        """TUZAK (a): PCB_ARC, PCB_TRACK'ten AYRI bir GetClass() döner —
        her ikisi de 'izler' listesine dahil edilmeli."""
        yay = SahteIz("PCB_ARC", (0.0, 0.0), (1.0, 1.0), net="MIPI_P")
        board = SahteBoard([], izler=[yay])

        sonuc = net_iz_ve_via_listesi_topla(board, "MIPI_P")

        assert len(sonuc["izler"]) == 1

    def test_via_ayri_listede_toplanir_ve_katman_argumanli_genislik_okunur(self):
        via = SahteIz("PCB_VIA", (2.0, 2.0), (2.0, 2.0), genislik_mm=0.3, net="MIPI_P",
                       ust_katman=0, alt_katman=2)
        board = SahteBoard([], izler=[via])

        sonuc = net_iz_ve_via_listesi_topla(board, "MIPI_P")

        assert sonuc["izler"] == []
        assert len(sonuc["vialar"]) == 1
        assert sonuc["vialar"][0]["konum_mm"] == (2.0, 2.0)
        assert sonuc["vialar"][0]["cap_mm"] == pytest.approx(0.3)
        assert sonuc["vialar"][0]["ust_katman"] == 0
        assert sonuc["vialar"][0]["alt_katman"] == 2

    def test_baska_nete_ait_ogeler_disarida_birakilir(self):
        board = SahteBoard([], izler=[SahteIz("PCB_TRACK", (0, 0), (1, 0), net="GND")])
        sonuc = net_iz_ve_via_listesi_topla(board, "MIPI_P")
        assert sonuc == {"izler": [], "vialar": []}


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


class TestPcbnewYokFallback:
    """2026-08-03, Madde 5: `pcbnew` GERÇEKTEN kurulu değilken (autouse
    taklidi bilerek KALDIRILIR — bu ortamda `pcbnew` zaten pip-kurulu
    DEĞİL, `ModuleNotFoundError` gerçek/organik olarak oluşur) `board_path`
    alan dört `*_kontrolu()` fonksiyonu exception FIRLATMAMALI, KAPSAM_YOK
    `Bulgu` döndürmeli — sessiz crash yerine."""

    @pytest.fixture(autouse=True)
    def _pcbnew_yi_gercekten_kaldir(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        yield

    def test_via_in_pad_pcbnew_yokken_kapsam_yok(self):
        from pcbnew_koprusu import via_in_pad_kontrolu
        bulgu = via_in_pad_kontrolu("board.kicad_pcb")
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0
        assert "pcbnew modülü bulunamadı" in bulgu.detay

    def test_annular_ring_pcbnew_yokken_kapsam_yok(self):
        from pcbnew_koprusu import annular_ring_kontrolu
        bulgu = annular_ring_kontrolu("board.kicad_pcb")
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0

    def test_kenar_keepout_seramik_pcbnew_yokken_kapsam_yok(self):
        from pcbnew_koprusu import kenar_keepout_seramik_kontrolu
        bulgu = kenar_keepout_seramik_kontrolu("board.kicad_pcb")
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0

    def test_stitch_yogunlugu_pcbnew_yokken_kapsam_yok(self):
        bulgu = stitch_yogunlugu_kontrolu("board.kicad_pcb")
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0


# ------------------------------------------------------------------
# GÖREV (2026-08-04): via_in_pad_kontrolu GENİŞLETMESİ —
# via_siniflandirma_haritasi ile dolgu_ve_kapak_var_mi filtrelemesi
# ------------------------------------------------------------------

def _via_ve_smd_pad_ayni_konumda(via_konum_mm=(0.0, 0.0)) -> SahteBoard:
    """Tek bir SMD ped ve TAM ÜSTÜNDE (via-in-pad) bir via içeren board."""
    from pcbnew_koprusu import via_in_pad_kontrolu  # noqa: F401 (import doğrulama)

    pad = SahtePad("1", via_konum_mm[0], via_konum_mm[1], 0.6, 0.6, attribute="SMD")
    fp = SahteFootprint("U1", [pad])
    via = SahteIz(
        "PCB_VIA", baslangic_mm=via_konum_mm, bitis_mm=via_konum_mm,
        net="VDD_CORE", ust_katman=0, alt_katman=1,
    )
    return SahteBoard([fp], izler=[via])


class TestViaInPadGenisletme:
    def test_harita_yoksa_eski_davranis_ihlal_uretir(self):
        """`via_siniflandirma_haritasi=None` (varsayılan) -> GERİYE DÖNÜK
        UYUMLU: geometrik via-in-pad her zamanki gibi ihlal listesine girer."""
        board = _via_ve_smd_pad_ayni_konumda()
        _taklit_pcbnew_yukle(board)

        bulgu = via_in_pad_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "FAIL"
        assert bulgu.taranan == 1
        assert len(bulgu.ihlaller) == 1
        assert bulgu.ihlaller[0]["pad"] == "U1.1"
        assert bulgu.ihlaller[0]["dolgu_ve_kapak_biliniyor_mu"] is None

    def test_harita_dolgu_kapak_true_ise_ihlal_degil(self):
        """Via_siniflandirma.py::select_via_type_for_bga() ile bilinçli
        IPC-4761 Type VII olarak tasarlanmış via-in-pad -> gerçek DRC
        hatası SAYILMAZ (görev talimatı: 'zaten doğru tasarlanmış')."""
        board = _via_ve_smd_pad_ayni_konumda(via_konum_mm=(1.5, 2.5))
        _taklit_pcbnew_yukle(board)

        harita = {(1.5, 2.5): True}
        bulgu = via_in_pad_kontrolu("board.kicad_pcb", via_siniflandirma_haritasi=harita)

        assert bulgu.durum.value == "PASS"
        assert bulgu.taranan == 1
        assert bulgu.ihlaller == []

    def test_harita_dolgu_kapak_false_ise_gercek_drc_hatasi(self):
        """`dolgu_ve_kapak_var_mi=False` (sınıflandırma bilinçli olarak
        'yok' diyor) -> ESKİ 'fab notunda belirtilmeli' tavsiyesi değil,
        GERÇEK bir DRC hatası (FAIL) — görev talimatı madde 3."""
        board = _via_ve_smd_pad_ayni_konumda(via_konum_mm=(3.0, 3.0))
        _taklit_pcbnew_yukle(board)

        harita = {(3.0, 3.0): False}
        bulgu = via_in_pad_kontrolu("board.kicad_pcb", via_siniflandirma_haritasi=harita)

        assert bulgu.durum.value == "FAIL"
        assert bulgu.ihlaller[0]["dolgu_ve_kapak_biliniyor_mu"] is False

    def test_harita_verilmis_ama_konum_eslesmiyorsa_bilinmiyor_sayilir(self):
        """Harita verildi ama BU via'nın konumu haritada yoksa -> `None`
        (bilinmiyor) — sessizce 'temiz' SAYILMAZ, eski/güvenli davranışa
        (ihlal) düşer."""
        board = _via_ve_smd_pad_ayni_konumda(via_konum_mm=(5.0, 5.0))
        _taklit_pcbnew_yukle(board)

        harita = {(9.0, 9.0): True}  # başka bir via'ya ait, bu konumla eşleşmiyor
        bulgu = via_in_pad_kontrolu("board.kicad_pcb", via_siniflandirma_haritasi=harita)

        assert bulgu.durum.value == "FAIL"
        assert bulgu.ihlaller[0]["dolgu_ve_kapak_biliniyor_mu"] is None

    def test_via_pad_disindaysa_hala_ihlal_uretmez(self):
        """Regresyon: via pad'in İÇİNDE değilse (normal, ayrı bir via)
        harita hiç devreye girmeden zaten ihlal üretilmemeli."""
        pad = SahtePad("1", 0.0, 0.0, 0.6, 0.6, attribute="SMD")
        fp = SahteFootprint("U1", [pad])
        via = SahteIz("PCB_VIA", baslangic_mm=(5.0, 5.0), bitis_mm=(5.0, 5.0), net="VDD_CORE")
        board = SahteBoard([fp], izler=[via])
        _taklit_pcbnew_yukle(board)

        bulgu = via_in_pad_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "PASS"
        assert bulgu.ihlaller == []


# ------------------------------------------------------------------
# GÖREV (2026-08-04): dekuplaj_mesafe_kontrolu — fiziksel mesafe kontrolü
# ------------------------------------------------------------------

from pcbnew_koprusu import dekuplaj_mesafe_kontrolu  # noqa: E402


def _ic_footprint(ref: str, fpid: str, pad_net_x_y) -> SahteFootprint:
    """`pad_net_x_y`: [(pad_no, net, x_mm, y_mm), ...]"""
    padlar = [SahtePad(no, x, y, 0.5, 0.5, net=net) for no, net, x, y in pad_net_x_y]
    # SahtePad'in son parametresi net değil attribute — burada özel kurucu
    # kullanmak yerine doğrudan _net'i set ediyoruz (aşağıdaki yardımcı).
    return SahteFootprint(ref, padlar, fpid=fpid)


def _pad_net_ata(pad: SahtePad, net: str) -> SahtePad:
    pad._net = net  # test-only erişim, üretim kodu bu alana erişmez
    return pad


def _qfn_ic(ref: str, vdd_konum_mm, fpid: str = "QFN-36-1EP_5x6mm") -> SahteFootprint:
    vdd_pad = _pad_net_ata(SahtePad("1", vdd_konum_mm[0], vdd_konum_mm[1], 0.3, 0.3), "VDD")
    gnd_pad = _pad_net_ata(SahtePad("2", vdd_konum_mm[0] + 1, vdd_konum_mm[1], 0.3, 0.3), "GND")
    return SahteFootprint(ref, [vdd_pad, gnd_pad], fpid=fpid)


def _dekuplaj_kapasitoru(ref: str, x_mm: float, y_mm: float, deger: str = "100nF") -> SahteFootprint:
    pad1 = SahtePad("1", x_mm - 0.5, y_mm, 0.3, 0.3)
    pad2 = SahtePad("2", x_mm + 0.5, y_mm, 0.3, 0.3)
    return SahteFootprint(ref, [pad1, pad2], fpid="C_0402_1005Metric", deger=deger, x_mm=x_mm, y_mm=y_mm)


class TestDekuplajMesafeKontrolu:
    def test_pcbnew_yokken_kapsam_yok(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")
        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0

    def test_yakin_kapasitor_pass(self):
        """Kasıtlı YAKIN yerleştirilmiş kapasitör -> PASS."""
        ic = _qfn_ic("U1", (10.0, 10.0))
        cap = _dekuplaj_kapasitoru("C1", 10.5, 10.0)  # IC'nin VDD pininden 0.5mm
        board = SahteBoard([ic, cap])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb", maks_mesafe_mm=3.0)

        assert bulgu.durum.value == "PASS"
        assert bulgu.taranan == 1  # sadece VDD pini taranır (GND pini değil)
        assert bulgu.ihlaller == []

    def test_uzak_kapasitor_kasitli_fail(self):
        """KASITLI olarak uzak (20mm) yerleştirilmiş kapasitör -> FAIL,
        ihlal 'kapasitor_uzak' türünde ve doğru mesafeyi rapor eder."""
        ic = _qfn_ic("U1", (10.0, 10.0))
        cap = _dekuplaj_kapasitoru("C1", 30.0, 10.0, "100nF")  # 20mm uzak
        board = SahteBoard([ic, cap])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb", maks_mesafe_mm=3.0)

        assert bulgu.durum.value == "FAIL"
        assert len(bulgu.ihlaller) == 1
        ihlal = bulgu.ihlaller[0]
        assert ihlal["tur"] == "kapasitor_uzak"
        assert ihlal["pin"] == "U1.1"
        assert ihlal["mesafe_mm"] == pytest.approx(20.0)
        assert ihlal["en_yakin_kapasitor"] == "C1"

    def test_kapasitor_hic_yoksa_ayri_ihlal_turu(self):
        """Uygun kapasitör HİÇ yoksa 'kapasitor_yok' türü — 'kapasitor_uzak'
        ile KARIŞTIRILMAZ (görev talimatı madde 6)."""
        ic = _qfn_ic("U1", (10.0, 10.0))
        board = SahteBoard([ic])  # hiç kapasitör yok
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "FAIL"
        assert bulgu.ihlaller[0]["tur"] == "kapasitor_yok"

    def test_deger_araligi_disindaki_kapasitor_aday_sayilmaz(self):
        """10uF bulk kapasitör 47-220nF aralığı DIŞINDA -> aday sayılmaz,
        IC'nin yanında olsa bile 'kapasitor_yok' üretir."""
        ic = _qfn_ic("U1", (10.0, 10.0))
        bulk_cap = _dekuplaj_kapasitoru("C1", 10.2, 10.0, "10uF")
        board = SahteBoard([ic, bulk_cap])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "FAIL"
        assert bulgu.ihlaller[0]["tur"] == "kapasitor_yok"

    def test_ic_olmayan_footprint_taranmaz(self):
        """Basit bir direnç (SMD ama IC DEĞİL) taramaya dahil edilmemeli."""
        direnc_pad = _pad_net_ata(SahtePad("1", 0.0, 0.0, 0.3, 0.3), "VDD")
        direnc = SahteFootprint("R1", [direnc_pad], fpid="R_0402_1005Metric")
        board = SahteBoard([direnc])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0

    def test_sot_3_pinli_transistor_ic_sayilmaz(self):
        """3 pinli SOT-23 (basit transistör) IC SAYILMAMALI — sadece
        >=5 pinli SOT (LDO/ESD gibi) IC sayılır."""
        pad1 = _pad_net_ata(SahtePad("1", 0.0, 0.0, 0.3, 0.3), "VDD")
        pad2 = _pad_net_ata(SahtePad("2", 0.5, 0.0, 0.3, 0.3), "GND")
        pad3 = _pad_net_ata(SahtePad("3", 1.0, 0.0, 0.3, 0.3), "OUT")
        transistor = SahteFootprint("Q1", [pad1, pad2, pad3], fpid="SOT-23")
        board = SahteBoard([transistor])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")

        assert bulgu.durum.value == "KAPSAM_YOK"
        assert bulgu.taranan == 0

    def test_sot_6_pinli_ldo_ic_sayilir(self):
        """6 pinli SOT-23-6 (ör. LDO/ESD dizisi) IC SAYILMALI."""
        padlar = [_pad_net_ata(SahtePad(str(i), float(i), 0.0, 0.3, 0.3),
                                "VDD" if i == 1 else "GND") for i in range(1, 7)]
        ldo = SahteFootprint("U1", padlar, fpid="SOT-23-6")
        board = SahteBoard([ldo])
        _taklit_pcbnew_yukle(board)

        bulgu = dekuplaj_mesafe_kontrolu("board.kicad_pcb")

        assert bulgu.taranan == 1  # sadece VDD pini (pad 1)
        assert bulgu.ihlaller[0]["tur"] == "kapasitor_yok"

    def test_maks_mesafe_parametresi_uygulanir(self):
        """`maks_mesafe_mm` özelleştirilebilir — daha gevşek bir sınırla
        aynı mesafe artık PASS olmalı."""
        ic = _qfn_ic("U1", (10.0, 10.0))
        cap = _dekuplaj_kapasitoru("C1", 15.0, 10.0)  # 5mm uzak
        board = SahteBoard([ic, cap])
        _taklit_pcbnew_yukle(board)

        siki = dekuplaj_mesafe_kontrolu("board.kicad_pcb", maks_mesafe_mm=3.0)
        gevsek = dekuplaj_mesafe_kontrolu("board.kicad_pcb", maks_mesafe_mm=10.0)

        assert siki.durum.value == "FAIL"
        assert gevsek.durum.value == "PASS"
