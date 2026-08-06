"""ezdxf_okuyucu.py için test suite.

Bu ortamda `ezdxf` KURULU DEĞİL — KAPSAM_YOK dalı GERÇEKTEN tetiklenir.
Geri kalan mantık (INSUNITS ayrıştırma, inch->mil ölçek düzeltmesi,
LWPOLYLINE/LINE/ARC/CIRCLE tarama) `sys.modules["ezdxf"]`'e yerleştirilen
bir taklit modülle test edilir — `test_pcbnew_koprusu.py`'nin sahte-pcbnew
deseniyle AYNI disiplin, farklı bir dış kütüphane için.

`kicad_edge_cuts_a_yaz()` `topolojik_router_koprusu.py::TopolojikRouter.
iz_yaz()` ile AYNI sahte-pcbnew yazma deseniyle test edilir.
"""

from __future__ import annotations

import math
import sys
from types import SimpleNamespace
from typing import List

import pytest

from bulgu_sozlesmesi import BulguDurumu
from mekanik_dxf_koprusu import DxfOutline, import_board_outline
from ezdxf_okuyucu import ezdxf_dosyasindan_outline_oku, kicad_edge_cuts_a_yaz


# ------------------------------------------------------------------
# Taklit `ezdxf` modülü
# ------------------------------------------------------------------


class SahteLWPolyline:
    def __init__(self, points):
        self._points = points

    def get_points(self):
        return self._points


class SahteLine:
    def __init__(self, start, end):
        self.dxf = SimpleNamespace(
            start=SimpleNamespace(x=start[0], y=start[1]),
            end=SimpleNamespace(x=end[0], y=end[1]),
        )


class SahteArc:
    def __init__(self, center, radius, baslangic_aci, bitis_aci):
        self.dxf = SimpleNamespace(
            center=SimpleNamespace(x=center[0], y=center[1]),
            radius=radius, start_angle=baslangic_aci, end_angle=bitis_aci,
        )


class SahteCircle:
    def __init__(self, center, radius):
        self.dxf = SimpleNamespace(center=SimpleNamespace(x=center[0], y=center[1]), radius=radius)


class SahteModelSpace:
    def __init__(self, varliklar):
        self._varliklar = varliklar  # List[(tip, layer, obj)]

    def query(self, sorgu: str):
        import re
        m = re.match(r'^(\w+)\[layer=="([^"]*)"\]$', sorgu)
        assert m, f"beklenmeyen sorgu formatı: {sorgu}"
        tip, layer = m.group(1), m.group(2)
        return [obj for (t, l, obj) in self._varliklar if t == tip and l == layer]


class SahteDoc:
    def __init__(self, insunits, varliklar):
        self.header = {"$INSUNITS": insunits}
        self._msp = SahteModelSpace(varliklar)

    def modelspace(self):
        return self._msp


class SahteEzdxfModulu:
    class DXFStructureError(Exception):
        pass

    def __init__(self, doc=None, ac_hata=None):
        self._doc = doc
        self._ac_hata = ac_hata

    def readfile(self, yol):
        if self._ac_hata is not None:
            raise self._ac_hata
        return self._doc


@pytest.fixture(autouse=True)
def _taklit_ezdxf_otomatik():
    orijinal = sys.modules.get("ezdxf")
    yield
    if orijinal is None:
        sys.modules.pop("ezdxf", None)
    else:
        sys.modules["ezdxf"] = orijinal


def _yukle(doc=None, ac_hata=None):
    sys.modules["ezdxf"] = SahteEzdxfModulu(doc, ac_hata)


def _kare_lwpolyline(kenar_uzunluk, katman="Board_Outline"):
    return SahteLWPolyline([
        (0.0, 0.0), (kenar_uzunluk, 0.0), (kenar_uzunluk, kenar_uzunluk), (0.0, kenar_uzunluk),
        (0.0, 0.0),
    ])


# ------------------------------------------------------------------
# ezdxf kurulu değilken KAPSAM_YOK (bu ortamda GERÇEK)
# ------------------------------------------------------------------


def test_ezdxf_kurulu_degilse_kapsam_yok(monkeypatch):
    monkeypatch.delitem(sys.modules, "ezdxf", raising=False)
    bulgu, outline = ezdxf_dosyasindan_outline_oku("yok.dxf")
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert bulgu.taranan == 0
    assert outline is None


def test_dxf_acilamazsa_kapsam_yok():
    _yukle(ac_hata=IOError("dosya bulunamadı"))
    bulgu, outline = ezdxf_dosyasindan_outline_oku("bozuk.dxf")
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert outline is None


# ------------------------------------------------------------------
# mm birimi (INSUNITS=4) — doğrudan geçmeli
# ------------------------------------------------------------------


def test_mm_dosyasi_dogru_okunur():
    doc = SahteDoc(4, [("LWPOLYLINE", "Board_Outline", _kare_lwpolyline(50.0))])
    _yukle(doc)

    bulgu, outline = ezdxf_dosyasindan_outline_oku("kart.dxf")

    assert bulgu.durum == BulguDurumu.PASS
    assert outline.birim == "mm"
    assert outline.nokta_listesi[1] == pytest.approx((50.0, 0.0))


# ------------------------------------------------------------------
# inch->mil ölçek düzeltmesi (bu görevin kilit testi)
# ------------------------------------------------------------------


def test_inch_dosyasinda_1000x_olcek_hatasi_olusmaz():
    """DOĞRULAMA: $INSUNITS=1 (Inches) bir DXF'te 1x1 inch'lik kare, TAM
    OLARAK 25.4x25.4mm'ye çevrilmeli (1 inch = 25.4mm, matematiksel
    tanım). Düzeltilmemiş (eski) kod bu değeri 0.0254mm (1000 kat küçük)
    üretirdi — bkz. dosya başlığı 'ÇÖZÜLEN inch->mil ÖLÇEK SORUNU'."""
    doc = SahteDoc(1, [("LWPOLYLINE", "Board_Outline", _kare_lwpolyline(1.0))])
    _yukle(doc)

    bulgu, outline_ham = ezdxf_dosyasindan_outline_oku("inch_kart.dxf")
    assert outline_ham.birim == "mil"
    # ham (ölçeklenmiş) değer MİL cinsinden olmalı: 1 inch = 1000 mil
    assert outline_ham.nokta_listesi[1] == pytest.approx((1000.0, 0.0))

    # import_board_outline() (mekanik_dxf_koprusu.py, DEĞİŞTİRİLMEDİ)
    # mil->mm çevrimini yapar — sonuç TAM 25.4mm olmalı, 0.0254mm DEĞİL.
    outline_mm = import_board_outline(outline_ham)
    assert outline_mm.birim == "mm"
    assert outline_mm.nokta_listesi[1] == pytest.approx((25.4, 0.0))


def test_insunits_bilinmiyorsa_confirm_gerekir():
    doc = SahteDoc(0, [("LWPOLYLINE", "Board_Outline", _kare_lwpolyline(10.0))])
    _yukle(doc)

    bulgu, outline = ezdxf_dosyasindan_outline_oku("belirsiz.dxf")

    assert bulgu.durum == BulguDurumu.FAIL  # taranan=1, ihlal var -> FAIL (KAPSAM_YOK DEĞİL)
    assert outline is None
    assert bulgu.ihlaller[0]["insunits_kodu"] == 0


# ------------------------------------------------------------------
# LWPOLYLINE + LINE + ARC birlikte taranır
# ------------------------------------------------------------------


def test_line_ve_arc_da_taranir():
    doc = SahteDoc(4, [
        ("LINE", "Board_Outline", SahteLine((0.0, 0.0), (10.0, 0.0))),
        ("ARC", "Board_Outline", SahteArc((10.0, 5.0), 5.0, 270.0, 90.0)),
    ])
    _yukle(doc)

    bulgu, outline = ezdxf_dosyasindan_outline_oku("karma.dxf")

    assert bulgu.durum in (BulguDurumu.PASS, BulguDurumu.FAIL)  # taranan>0
    assert bulgu.taranan > 2  # 2 LINE noktası + ARC'ın ürettiği segment_sayisi+1 nokta
    assert outline is not None


def test_baska_katmandaki_geometri_yok_sayilir():
    doc = SahteDoc(4, [("LWPOLYLINE", "Baska_Katman", _kare_lwpolyline(10.0))])
    _yukle(doc)
    bulgu, outline = ezdxf_dosyasindan_outline_oku("kart.dxf", outline_katman_adi="Board_Outline")
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert outline is None


def test_delik_katmani_okunur():
    doc = SahteDoc(4, [
        ("LWPOLYLINE", "Board_Outline", _kare_lwpolyline(20.0)),
        ("CIRCLE", "Board_Outline_Deliği", SahteCircle((2.0, 2.0), 1.0)),
    ])
    _yukle(doc)

    bulgu, outline = ezdxf_dosyasindan_outline_oku("kart.dxf")

    assert len(outline.delik_listesi) == 1
    assert outline.delik_listesi[0] == pytest.approx((2.0, 2.0, 2.0))


def test_acik_poligon_ihlal_olarak_isaretlenir_ama_outline_donuyor():
    acik_kare = SahteLWPolyline([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])  # kapanmıyor
    doc = SahteDoc(4, [("LWPOLYLINE", "Board_Outline", acik_kare)])
    _yukle(doc)

    bulgu, outline = ezdxf_dosyasindan_outline_oku("acik.dxf")

    assert bulgu.durum == BulguDurumu.FAIL
    assert "KAPALI DEĞİL" in bulgu.ihlaller[0]["sebep"]
    assert outline is not None  # veri yine de dönüyor, çağıran karar verir


# ------------------------------------------------------------------
# kicad_edge_cuts_a_yaz — sahte-pcbnew yazma deseni
# (topolojik_router_koprusu.py::TopolojikRouter.iz_yaz ile AYNI)
# ------------------------------------------------------------------


class SahteVector2I:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class SahtePcbShape:
    def __init__(self, board):
        self.board = board
        self.shape = None
        self.start = None
        self.end = None
        self.layer = None
        self.width = None

    def SetShape(self, s):
        self.shape = s

    def SetStart(self, v):
        self.start = v

    def SetEnd(self, v):
        self.end = v

    def SetLayer(self, l):
        self.layer = l

    def SetWidth(self, w):
        self.width = w


class SahteBoardW:
    def __init__(self):
        self.eklenenler: List[SahtePcbShape] = []
        self.kaydedilen_yol = None

    def Add(self, obj):
        self.eklenenler.append(obj)

    def Save(self, yol):
        self.kaydedilen_yol = yol


class SahtePcbnewModulu:
    Edge_Cuts = "Edge.Cuts"
    SHAPE_T_SEGMENT = "SEGMENT"

    def __init__(self, board):
        self._board = board

    def LoadBoard(self, yol):
        return self._board

    def PCB_SHAPE(self, board):
        return SahtePcbShape(board)

    def VECTOR2I(self, x, y):
        return SahteVector2I(x, y)

    def FromMM(self, mm):
        return int(round(mm * 1_000_000))


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik():
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _pcbnew_yukle():
    board = SahteBoardW()
    sys.modules["pcbnew"] = SahtePcbnewModulu(board)
    return board


class TestKicadEdgeCutsAYaz:
    def test_mil_birimindeki_outline_reddedilir(self):
        outline = DxfOutline(nokta_listesi=[(0, 0), (10, 0)], birim="mil")
        with pytest.raises(ValueError):
            kicad_edge_cuts_a_yaz("board.kicad_pcb", outline)

    def test_acik_poligon_pcbnew_hic_cagrilmadan_reddedilir(self, monkeypatch):
        """Kapalı olmayan bir outline `pcbnew`'e HİÇ dokunmadan FAIL
        döner — bu ortamda zaten pcbnew yok, bu test onu KANITLAR."""
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        outline = DxfOutline(nokta_listesi=[(0, 0), (10, 0), (10, 10)], birim="mm")
        bulgu = kicad_edge_cuts_a_yaz("board.kicad_pcb", outline)
        assert bulgu.durum == BulguDurumu.FAIL
        assert "KAPALI DEĞİL" in bulgu.ihlaller[0]["sebep"]

    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        kapali_kare = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
        outline = DxfOutline(nokta_listesi=kapali_kare, birim="mm")
        bulgu = kicad_edge_cuts_a_yaz("board.kicad_pcb", outline)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_kapali_poligon_dogru_segment_sayisiyla_yazilir_ve_kaydedilir(self):
        board = _pcbnew_yukle()
        # 4 köşe + kapanış noktası (ilk==son) = 5 nokta -> 4 SEGMENT beklenir
        kapali_kare = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
        outline = DxfOutline(nokta_listesi=kapali_kare, birim="mm")

        bulgu = kicad_edge_cuts_a_yaz("board.kicad_pcb", outline)

        assert bulgu.durum == BulguDurumu.PASS
        assert len(board.eklenenler) == 4
        assert board.kaydedilen_yol == "board.kicad_pcb"
        for sekil in board.eklenenler:
            assert sekil.layer == "Edge.Cuts"
            assert sekil.shape == "SEGMENT"

    def test_acikca_kapatilmamis_ama_toleransta_kapali_poligon_kapanis_segmenti_EKLEMEZ(self):
        """`poligon_kapali_mi` toleransı (0.01mm) içinde son nokta ilk
        noktaya eşitse, kapanış segmenti TEKRAR eklenmemeli (çift
        segment/çakışan iz riski)."""
        board = _pcbnew_yukle()
        kapali_kare = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0001, 0.0001)]
        outline = DxfOutline(nokta_listesi=kapali_kare, birim="mm")

        kicad_edge_cuts_a_yaz("board.kicad_pcb", outline)

        assert len(board.eklenenler) == 4  # 5 nokta - 1, kapanış segmenti EKLENMEDİ
