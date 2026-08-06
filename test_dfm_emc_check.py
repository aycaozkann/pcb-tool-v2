"""dfm_emc_check.py için test suite.

REGRESYON KİLİDİ (bu görevde bulunup düzeltildi): modül eskiden koşulsuz
`import pcbnew` yapıyordu — CLAUDE.md'nin "pcbnew bağımlılığı HER ZAMAN
lazy olmalı" kuralını ihlal ediyordu ve bu modülü pcbnew kurulu olmayan
HERHANGİ bir ortamda import etmek bile `ModuleNotFoundError` ile
çöküyordu. `test_modul_pcbnew_yokken_import_edilebilir` bunu KİLİTLER.

`test_pcbnew_koprusu.py` ile AYNI sahte-pcbnew mock desenini kullanır.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

import pytest

NM_PER_MM = 1_000_000


def test_modul_pcbnew_yokken_import_edilebilir(monkeypatch):
    """DÜZELTİLEN REGRESYON: bu satır eskiden `ModuleNotFoundError`
    fırlatırdı — `dfm_emc_check` modül seviyesinde koşulsuz `import
    pcbnew` yapıyordu."""
    monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
    monkeypatch.delitem(sys.modules, "dfm_emc_check", raising=False)
    import dfm_emc_check  # noqa: F401 — import'un kendisi ÇÖKMEMELİ

    assert dfm_emc_check.pcbnew is None


# ------------------------------------------------------------------
# Bulgu kabı — pcbnew GEREKMEZ
# ------------------------------------------------------------------


def test_result_sifir_kapsam_no_coverage():
    from dfm_emc_check import result

    r = result("ornek", 0, [])
    assert r["status"] == "NO_COVERAGE"
    assert r["scanned"] == 0


def test_result_ihlalsiz_pass():
    from dfm_emc_check import result

    r = result("ornek", 5, [])
    assert r["status"] == "PASS"


def test_result_ihlalli_fail():
    from dfm_emc_check import result

    r = result("ornek", 5, [{"x": 1}])
    assert r["status"] == "FAIL"
    assert r["violations"] == [{"x": 1}]


# ------------------------------------------------------------------
# main() — pcbnew kurulu değilken NO_COVERAGE + exit 2 (DÜZELTME kanıtı)
# ------------------------------------------------------------------


def test_main_pcbnew_yokken_no_coverage_ve_exit_2(monkeypatch, tmp_path, capsys):
    monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
    monkeypatch.delitem(sys.modules, "dfm_emc_check", raising=False)
    import dfm_emc_check

    kod = dfm_emc_check.main([str(tmp_path / "yok.kicad_pcb")])

    assert kod == 2
    cikti = capsys.readouterr().out
    assert '"NO_COVERAGE"' in cikti
    assert "pcbnew import edilemedi" in cikti


# ------------------------------------------------------------------
# Sahte pcbnew — gerçek kontrol mantığı (test_pcbnew_koprusu.py ile AYNI desen)
# ------------------------------------------------------------------


class SahteNokta:
    def __init__(self, x_mm: float, y_mm: float):
        self.x = int(round(x_mm * NM_PER_MM))
        self.y = int(round(y_mm * NM_PER_MM))


class SahteBoyut:
    def __init__(self, x_mm: float, y_mm: float = 0.0):
        self.x = int(round(x_mm * NM_PER_MM))
        self.y = int(round(y_mm * NM_PER_MM))


class SahtePolygonAlan:
    def __init__(self, merkez: SahteNokta, boy_x_nm: int, boy_y_nm: int):
        self._merkez = merkez
        self._yarim_x = boy_x_nm / 2.0
        self._yarim_y = boy_y_nm / 2.0

    def Collide(self, nokta: SahteNokta) -> bool:
        return (
            abs(nokta.x - self._merkez.x) <= self._yarim_x
            and abs(nokta.y - self._merkez.y) <= self._yarim_y
        )

    def Area(self) -> float:
        return (self._yarim_x * 2) * (self._yarim_y * 2)


class SahtePad:
    def __init__(
        self, numara, x_mm, y_mm, boy_x_mm, boy_y_mm,
        attribute="SMD", drill_x_mm=0.0, net="", katmanlar=None, paste_margin_mm=0.0,
    ):
        self._numara = numara
        self._konum = SahteNokta(x_mm, y_mm)
        self._boy_x = int(round(boy_x_mm * NM_PER_MM))
        self._boy_y = int(round(boy_y_mm * NM_PER_MM))
        self._attribute = attribute
        self._drill = SahteBoyut(drill_x_mm)
        self._net = net
        self._katmanlar = katmanlar
        self._paste_margin = int(round(paste_margin_mm * NM_PER_MM))

    def GetNumber(self):
        return self._numara

    def GetNetname(self):
        return self._net

    def GetPosition(self):
        return self._konum

    def GetSizeX(self):
        return self._boy_x

    def GetSizeY(self):
        return self._boy_y

    def GetAttribute(self):
        return self._attribute

    def GetDrillSize(self):
        return self._drill

    def IsOnLayer(self, layer):
        return self._katmanlar is None or layer in self._katmanlar

    def GetEffectivePolygon(self, layer):
        return SahtePolygonAlan(self._konum, self._boy_x, self._boy_y)

    def GetSolderPasteMargin(self, layer):
        return SahteBoyut(self._paste_margin / NM_PER_MM)


class SahteFootprint:
    def __init__(self, ref, padlar, x_mm=0.0, y_mm=0.0, orientation_deg=0.0):
        self._ref = ref
        self._padlar = padlar
        self._konum = SahteNokta(x_mm, y_mm)
        self._orientation = orientation_deg

    def GetReference(self):
        return self._ref

    def Pads(self):
        return self._padlar

    def GetPosition(self):
        return self._konum

    def GetOrientationDegrees(self):
        return self._orientation


class SahteVia:
    def __init__(self, x_mm, y_mm, genislik_mm, drill_mm, net="", top_layer=0, bottom_layer=1):
        self._konum = SahteNokta(x_mm, y_mm)
        self._genislik_nm = int(round(genislik_mm * NM_PER_MM))
        self._drill_nm = int(round(drill_mm * NM_PER_MM))
        self._net = net
        self._top = top_layer
        self._bottom = bottom_layer

    def GetClass(self):
        return "PCB_VIA"

    def GetPosition(self):
        return self._konum

    def GetWidth(self, *_args):
        return self._genislik_nm

    def GetDrill(self):
        return self._drill_nm

    def GetNetname(self):
        return self._net

    def TopLayer(self):
        return self._top

    def BottomLayer(self):
        return self._bottom


class SahteNetInfo:
    def __init__(self, netclass_adi):
        self._nc = netclass_adi

    def GetNetClassName(self):
        return self._nc


class SahteBoard:
    def __init__(self, footprints=None, vialar=None, zones=None, netler=None, cizimler=None):
        self._footprints = footprints or []
        self._vialar = vialar or []
        self._zones = zones or []
        self._netler = netler or {}
        self._cizimler = cizimler or []

    def GetFootprints(self):
        return self._footprints

    def GetTracks(self):
        return self._vialar

    def Zones(self):
        return self._zones

    def GetNetsByName(self):
        return self._netler

    def GetDrawings(self):
        return self._cizimler


class TaklitPcbnew:
    PAD_ATTRIB_SMD = "SMD"
    PAD_ATTRIB_CONN = "CONN"
    PAD_ATTRIB_NPTH = "NPTH"
    F_Paste = "F.Paste"
    B_Paste = "B.Paste"
    F_Cu = "F.Cu"
    B_Cu = "B.Cu"
    Edge_Cuts = "Edge.Cuts"
    UNDEFINED_LAYER = -1
    ERROR_INSIDE = 0

    def __init__(self, board):
        self._board = board

    def LoadBoard(self, yol):
        return self._board

    def FromMM(self, v):
        return int(round(v * NM_PER_MM))

    def SHAPE_POLY_SET(self):
        class _Poly:
            def OutlineCount(self):
                return 0
        return _Poly()


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik(monkeypatch):
    monkeypatch.delitem(sys.modules, "dfm_emc_check", raising=False)
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _yukle(board: SahteBoard):
    taklit = TaklitPcbnew(board)
    sys.modules["pcbnew"] = taklit
    import dfm_emc_check
    return dfm_emc_check


class TestCheckViaInPad:
    def test_via_pad_icindeyse_ihlal(self):
        pad = SahtePad("1", 0.0, 0.0, 1.0, 1.0)
        fp = SahteFootprint("U1", [pad])
        via = SahteVia(0.0, 0.0, 0.3, 0.15, net="VCAM")
        mod = _yukle(SahteBoard(footprints=[fp], vialar=[via]))

        f = mod.check_via_in_pad(mod.pcbnew.LoadBoard(""))

        assert f["status"] == "FAIL"
        assert f["scanned"] == 1
        assert f["violations"][0]["pad"] == "U1.1"

    def test_via_pad_disindaysa_pass(self):
        pad = SahtePad("1", 5.0, 5.0, 1.0, 1.0)
        fp = SahteFootprint("U1", [pad])
        via = SahteVia(0.0, 0.0, 0.3, 0.15, net="VCAM")
        mod = _yukle(SahteBoard(footprints=[fp], vialar=[via]))

        f = mod.check_via_in_pad(mod.pcbnew.LoadBoard(""))

        assert f["status"] == "PASS"

    def test_via_yoksa_no_coverage(self):
        mod = _yukle(SahteBoard())
        f = mod.check_via_in_pad(mod.pcbnew.LoadBoard(""))
        assert f["status"] == "NO_COVERAGE"


class TestCheckAnnular:
    def test_tam_sinirdaki_via_tuzagi_yanlis_ihlal_uretmez(self):
        """TUZAK (e) regresyon kilidi: dosyanın kendi yorumunda anlatılan
        float mm sınır hatası (0.15 tam sınırında (0.7-0.4)/2 gibi ifadeler
        0.14999999999999997 üretebilir) — nm tam sayı aritmetiğiyle bu
        sınır hatası OLUŞMAMALI. via genişliği 0.7mm, delik 0.4mm ->
        halka TAM 0.15mm, min_mm=0.15 ile İHLAL SAYILMAMALI (>= sınır)."""
        via = SahteVia(0.0, 0.0, genislik_mm=0.7, drill_mm=0.4, net="GND")
        mod = _yukle(SahteBoard(vialar=[via]))

        f = mod.check_annular(mod.pcbnew.LoadBoard(""), min_mm=0.15)

        assert f["status"] == "PASS"
        assert f["scanned"] == 1

    def test_halka_sinirin_altindaysa_ihlal(self):
        via = SahteVia(0.0, 0.0, genislik_mm=0.6, drill_mm=0.4, net="GND")
        mod = _yukle(SahteBoard(vialar=[via]))

        f = mod.check_annular(mod.pcbnew.LoadBoard(""), min_mm=0.15)

        assert f["status"] == "FAIL"
        assert f["violations"][0]["type"] == "via"

    def test_pth_pad_da_kontrol_edilir_npth_atlanir(self):
        pth = SahtePad("1", 0.0, 0.0, 0.6, 0.6, drill_x_mm=0.4)
        npth = SahtePad("2", 1.0, 1.0, 0.6, 0.6, drill_x_mm=0.4, attribute="NPTH")
        fp = SahteFootprint("H1", [pth, npth])
        mod = _yukle(SahteBoard(footprints=[fp]))

        f = mod.check_annular(mod.pcbnew.LoadBoard(""), min_mm=0.15)

        assert f["scanned"] == 1  # NPTH sayılmadı


class TestCheckEdgeKeepout:
    def test_seramik_kenara_cok_yakinsa_ihlal(self):
        pad1 = SahtePad("1", -0.5, 0.0, 0.5, 0.5)
        pad2 = SahtePad("2", 0.5, 0.0, 0.5, 0.5)
        fp = SahteFootprint("C1", [pad1, pad2], x_mm=1.0, y_mm=0.0)

        class _Cizim:
            def GetLayer(self):
                return "Edge.Cuts"

            def GetEffectiveShape(self):
                return object()

            def TransformShapeToPolygon(self, poly, *a, **k):
                # board_outline_segments() sadece POLİGON KÖŞE noktalarını
                # toplar (aralarında interpolasyon YAPMAZ) — bu yüzden
                # "yakın" bir kenar noktası fp'nin KENDİSİNE yakın bir
                # KÖŞE olarak verilmeli, uzak bir doğru parçasının uç
                # noktaları DEĞİL.
                poly._outlines = [[SahteNokta(0.0, 0.0), SahteNokta(10.0, 0.0)]]

        board = SahteBoard(footprints=[fp], cizimler=[_Cizim()])

        class TaklitPcbnewPoly(TaklitPcbnew):
            def SHAPE_POLY_SET(self):
                class _Poly:
                    def __init__(self):
                        self._outlines = []

                    def OutlineCount(self):
                        return len(self._outlines)

                    def Outline(self, i):
                        return _Outline(self._outlines[i])

                class _Outline:
                    def __init__(self, noktalar):
                        self._noktalar = noktalar

                    def PointCount(self):
                        return len(self._noktalar)

                    def CPoint(self, i):
                        return self._noktalar[i]

                return _Poly()

        sys.modules["pcbnew"] = TaklitPcbnewPoly(board)
        import dfm_emc_check
        mod = dfm_emc_check

        f = mod.check_edge_keepout(mod.pcbnew.LoadBoard(""), keepout_mm=2.0)

        assert f["status"] == "FAIL"
        assert f["violations"][0]["ref"] == "C1"

    def test_direnc_iki_pedli_olmayan_parca_es_gecilir(self):
        pad1 = SahtePad("1", 0.0, 0.0, 0.5, 0.5)
        pad2 = SahtePad("2", 1.0, 0.0, 0.5, 0.5)
        pad3 = SahtePad("3", 2.0, 0.0, 0.5, 0.5)
        fp = SahteFootprint("U1", [pad1, pad2, pad3])  # 3 pad -> seramik SAYILMAZ
        board = SahteBoard(footprints=[fp], cizimler=[])
        mod = _yukle(board)

        f = mod.check_edge_keepout(mod.pcbnew.LoadBoard(""), keepout_mm=2.0)

        assert f["status"] == "NO_COVERAGE"  # Edge.Cuts hiç yok


class TestCheckReturnVias:
    def test_gnd_yakinsa_pass(self):
        gnd = SahteVia(0.0, 0.0, 0.3, 0.15, net="GND")
        hs = SahteVia(0.1, 0.1, 0.3, 0.15, net="USB_DP")
        mod = _yukle(SahteBoard(vialar=[gnd, hs]))

        f = mod.check_return_vias(mod.pcbnew.LoadBoard(""), hs_regex=r"(?i)usb", max_mm=2.5)

        assert f["status"] == "PASS"
        assert f["scanned"] == 1

    def test_gnd_uzaksa_ihlal(self):
        gnd = SahteVia(50.0, 50.0, 0.3, 0.15, net="GND")
        hs = SahteVia(0.0, 0.0, 0.3, 0.15, net="USB_DP")
        mod = _yukle(SahteBoard(vialar=[gnd, hs]))

        f = mod.check_return_vias(mod.pcbnew.LoadBoard(""), hs_regex=r"(?i)usb", max_mm=2.5)

        assert f["status"] == "FAIL"


class TestCheckNetclassCoverage:
    def test_default_netclassta_kalan_hizli_net_ihlal(self):
        board = SahteBoard(netler={"USB_DP": SahteNetInfo("Default"), "GND": SahteNetInfo("PowerClass")})
        mod = _yukle(board)

        f = mod.check_netclass_coverage(mod.pcbnew.LoadBoard(""), hs_regex=r"(?i)usb")

        assert f["status"] == "FAIL"
        assert f["scanned"] == 1

    def test_ozel_netclassta_ise_pass(self):
        board = SahteBoard(netler={"USB_DP": SahteNetInfo("HS_Diff")})
        mod = _yukle(board)

        f = mod.check_netclass_coverage(mod.pcbnew.LoadBoard(""), hs_regex=r"(?i)usb")

        assert f["status"] == "PASS"


class TestCheckTeardropsVePaste:
    def test_teardrop_yoksa_no_coverage_pass_sayilmaz(self):
        mod = _yukle(SahteBoard(zones=[]))
        f = mod.check_teardrops(mod.pcbnew.LoadBoard(""))
        assert f["status"] == "NO_COVERAGE"

    def test_epad_pasta_orani_asilirsa_ihlal(self):
        pad = SahtePad(
            "1", 0.0, 0.0, 3.0, 3.0, attribute="SMD", katmanlar=["F.Paste"],
            paste_margin_mm=0.5,  # geniş margin -> oran şişer
        )
        fp = SahteFootprint("U1", [pad])
        mod = _yukle(SahteBoard(footprints=[fp]))

        f = mod.check_paste_coverage(mod.pcbnew.LoadBoard(""), epad_area_mm2=4.0, ratio_max=0.80)

        assert f["status"] == "FAIL"
