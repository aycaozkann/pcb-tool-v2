"""openems_koprusu.py için test suite.

Bu ortamda `openEMS`/`CSXCAD`/`skrf` KURULU DEĞİL — bu üç modülün
KAPSAM_YOK dallarının HEPSİ bu makinede GERÇEKTEN tetiklenir (tahmin
edilmez, ölçülür). `geometri_cikar()` için `pcbnew` de kurulu değil, bu
yüzden onun pcbnew-bağımlı yolu `test_pcbnew_koprusu.py` ile AYNI
sahte-pcbnew mock desenini kullanır.

Kabul kriteri (görev tanımından): openEMS kurulu olmayan bir makinede
TÜM testler ya PASS ya da açıkça SKIP/KAPSAM_YOK olur — hiçbiri sessizce
sahte veri üretmez. `openEMS kurulu değilken KAPSAM_YOK` testleri GERÇEK
(bu ortamda openEMS/CSXCAD/skrf gerçekten kurulu değil). `fdtd_kur_ve_
calistir()`'in port/excitation MANTIĞI (mesh/GND/sinyal-iz/port
yerleşimi/S-parametre hesabı) `sys.modules["CSXCAD"]`/`["openEMS"]`'e
yerleştirilen sahte modüllerle test edilir — `AddLumpedPort`/`CalcPort`
GERÇEK openEMS API'sinin KENDİSİ DEĞİL, yalnızca bu fonksiyonun
ÇAĞIRDIĞI arayüz sözleşmesi (imza + akış) doğrulanır; gerçek openEMS ile
sayısal doğruluk (bilinen 100Ω referans yapı) SENİN makinende ayrıca
teyit edilmelidir (bkz. openems_koprusu.py docstring'i).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bulgu_sozlesmesi import BulguDurumu
from openems_koprusu import (
    DiferansiyelCiftGeometrisi,
    akim_yogunlugu_haritasi_uret,
    fdtd_kur_ve_calistir,
    geometri_cikar,
    openems_kurulu_mu,
    s_parametre_degerlendir,
)


def test_openems_kurulu_mu_bu_ortamda_false():
    """DOĞRULAMA: bu makinede CSXCAD/openEMS GERÇEKTEN kurulu değil."""
    assert openems_kurulu_mu() is False


# ------------------------------------------------------------------
# geometri_cikar — sahte pcbnew mock deseni (test_pcbnew_koprusu.py ile AYNI)
# ------------------------------------------------------------------


class SahteNokta:
    def __init__(self, x_mm, y_mm):
        self.x = int(round(x_mm * 1_000_000))
        self.y = int(round(y_mm * 1_000_000))


class SahteIz:
    def __init__(self, tip, baslangic_mm, bitis_mm, genislik_mm=0.15, net=""):
        self._tip = tip
        self._s = SahteNokta(*baslangic_mm)
        self._e = SahteNokta(*bitis_mm)
        self._genislik_mm = genislik_mm
        self._net = net

    def GetClass(self):
        return self._tip

    def GetNetname(self):
        return self._net

    def GetStart(self):
        return self._s

    def GetEnd(self):
        return self._e

    def GetPosition(self):
        return self._s

    def GetWidth(self, *_args):
        return int(round(self._genislik_mm * 1_000_000))

    def GetLayer(self):
        return 0

    def TopLayer(self):
        return 0

    def BottomLayer(self):
        return 1


class SahteBoard:
    def __init__(self, izler):
        self._izler = izler

    def GetTracks(self):
        return self._izler

    def GetFootprints(self):
        return []


class TaklitPcbnew:
    def __init__(self, board):
        self._board = board

    def LoadBoard(self, yol):
        return self._board


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik():
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _yukle(board):
    sys.modules["pcbnew"] = TaklitPcbnew(board)


class TestGeometriCikar:
    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        geometri, kapsam_yok = geometri_cikar("board.kicad_pcb", "MIPI_D0_P", "MIPI_D0_N")
        assert geometri is None
        assert kapsam_yok is not None
        assert kapsam_yok.durum == BulguDurumu.KAPSAM_YOK
        assert kapsam_yok.taranan == 0

    def test_her_iki_net_de_bossa_kapsam_yok(self):
        _yukle(SahteBoard([SahteIz("PCB_TRACK", (0, 0), (1, 0), net="BASKA_NET")]))
        geometri, kapsam_yok = geometri_cikar("board.kicad_pcb", "MIPI_D0_P", "MIPI_D0_N")
        assert geometri is None
        assert kapsam_yok is not None
        assert kapsam_yok.durum == BulguDurumu.KAPSAM_YOK

    def test_gercek_izlerle_geometri_dolar(self):
        izler = [
            SahteIz("PCB_TRACK", (0.0, 0.0), (10.0, 0.0), net="MIPI_D0_P"),
            SahteIz("PCB_ARC", (10.0, 0.0), (12.0, 1.0), net="MIPI_D0_P"),
            SahteIz("PCB_VIA", (10.0, 0.0), (10.0, 0.0), net="MIPI_D0_P"),
            SahteIz("PCB_TRACK", (0.0, 0.2), (10.0, 0.2), net="MIPI_D0_N"),
        ]
        _yukle(SahteBoard(izler))

        geometri, kapsam_yok = geometri_cikar("board.kicad_pcb", "MIPI_D0_P", "MIPI_D0_N")

        assert kapsam_yok is None
        assert isinstance(geometri, DiferansiyelCiftGeometrisi)
        assert len(geometri.iz_segmentleri_pozitif) == 2  # PCB_TRACK + PCB_ARC
        assert len(geometri.via_listesi_pozitif) == 1
        assert len(geometri.iz_segmentleri_negatif) == 1
        assert geometri.net_adi_pozitif == "MIPI_D0_P"
        assert geometri.net_adi_negatif == "MIPI_D0_N"

    def test_referans_duzlem_z_gecirilir(self):
        _yukle(SahteBoard([SahteIz("PCB_TRACK", (0, 0), (1, 0), net="P")]))
        geometri, _ = geometri_cikar("board.kicad_pcb", "P", "N", referans_duzlem_z_mm=1.6)
        assert geometri.referans_duzlem_z_mm == 1.6


# ------------------------------------------------------------------
# fdtd_kur_ve_calistir — openEMS kurulu değilken KAPSAM_YOK
# ------------------------------------------------------------------


class TestFdtdKurVeCalistir:
    def test_openems_kurulu_degilse_kapsam_yok_hicbir_dosya_yazilmaz(self, tmp_path):
        geometri = DiferansiyelCiftGeometrisi(
            net_adi_pozitif="P", net_adi_negatif="N",
            iz_segmentleri_pozitif=[{"baslangic_mm": (0, 0), "bitis_mm": (10, 0), "genislik_mm": 0.15, "katman": 0}],
        )
        bulgu = fdtd_kur_ve_calistir(geometri, str(tmp_path))
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0
        assert "KOŞULMADI" in bulgu.detay
        assert list(tmp_path.iterdir()) == []  # sahte .s4p UYDURULMADI


# ------------------------------------------------------------------
# Sahte CSXCAD/openEMS — port/excitation akışını arayüz-sözleşmesi
# seviyesinde doğrular (GERÇEK openEMS fiziği DEĞİL, bkz. dosya başlığı)
# ------------------------------------------------------------------

class SahtePort:
    def __init__(self, port_nr, excite):
        self.port_nr = port_nr
        self.excite = excite
        self.uf_inc = None
        self.uf_ref = None
        self.calc_cagrildi = False

    def CalcPort(self, sim_path, f):
        import numpy as np

        self.calc_cagrildi = True
        n = len(f)
        taban = self.excite if self.excite else 1.0
        self.uf_inc = np.full(n, taban, dtype=complex)
        # yakın uç (port 1/2) düşük yansıma, uzak uç (port 3/4) yüksek
        # "iletim" (sahte, sadece akışı test etmek için) taşır.
        self.uf_ref = np.full(n, 0.1 if self.port_nr in (1, 2) else 0.9, dtype=complex)


class SahteFDTD:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.portlar = []
        self.run_cagrildi = False
        self.gauss = None
        self.boundary = None

    def SetGaussExcite(self, f0, fc):
        self.gauss = (f0, fc)

    def SetBoundaryCond(self, cond):
        self.boundary = cond

    def SetCSX(self, csx):
        self.csx = csx

    def AddLumpedPort(self, port_nr, R, start, stop, direction, excite=0):
        assert direction == "z"
        p = SahtePort(port_nr, excite)
        self.portlar.append((p, R, start, stop))
        return p

    def Run(self, path, cleanup=True):
        self.run_cagrildi = True
        self.run_path = path


class SahteGrid:
    def __init__(self):
        self.lines = {}

    def SetDeltaUnit(self, v):
        self.delta_unit = v

    def AddLine(self, eksen, degerler):
        self.lines[eksen] = list(degerler)


class SahteMetalOzellik:
    def __init__(self, ad):
        self.ad = ad
        self.kutular = []
        self.poligonlar = []

    def AddBox(self, p1, p2):
        self.kutular.append((p1, p2))

    def AddPolygon(self, points, norm_dir, elevation, priority=10):
        self.poligonlar.append((points, norm_dir, elevation, priority))
        return object()


class SahteCSX:
    def __init__(self):
        self.grid = SahteGrid()
        self.metaller = {}

    def GetGrid(self):
        return self.grid

    def AddMetal(self, ad):
        m = SahteMetalOzellik(ad)
        self.metaller[ad] = m
        return m


class _CSXCADModulu:
    ContinuousStructure = SahteCSX


class _OpenEMSModulu:
    openEMS = SahteFDTD


@pytest.fixture
def _sahte_openems_kurulu(monkeypatch):
    monkeypatch.setitem(sys.modules, "CSXCAD", _CSXCADModulu())
    monkeypatch.setitem(sys.modules, "openEMS", _OpenEMSModulu())
    yield


def _diferansiyel_cift_geometrisi():
    return DiferansiyelCiftGeometrisi(
        net_adi_pozitif="MIPI_D0_P", net_adi_negatif="MIPI_D0_N",
        iz_segmentleri_pozitif=[
            {"baslangic_mm": (0.0, 0.0), "bitis_mm": (10.0, 0.0), "genislik_mm": 0.15, "katman": 0},
        ],
        iz_segmentleri_negatif=[
            {"baslangic_mm": (0.0, 0.2), "bitis_mm": (10.0, 0.2), "genislik_mm": 0.15, "katman": 0},
        ],
        referans_duzlem_z_mm=0.0,
    )


class TestFdtdKurVeCalistirSahteOpenems:
    def test_her_iki_iletken_de_yoksa_kapsam_yok(self, tmp_path, _sahte_openems_kurulu):
        geometri = DiferansiyelCiftGeometrisi(net_adi_pozitif="P", net_adi_negatif="N")
        bulgu = fdtd_kur_ve_calistir(geometri, str(tmp_path))
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_fdtd_kosumu_tamamlanir_ve_bulgu_pass_doner(self, tmp_path, _sahte_openems_kurulu):
        geometri = _diferansiyel_cift_geometrisi()
        bulgu = fdtd_kur_ve_calistir(geometri, str(tmp_path), mesh_cozunurlugu="kaba")

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 1
        assert "Sdd11" in bulgu.detay and "Sdd21" in bulgu.detay
        assert "DOĞRULANAMADI" in bulgu.detay  # dürüstlük notu HER ZAMAN raporda

    def test_portlar_doğru_yon_ve_excite_ile_kuruluyor(self, tmp_path, _sahte_openems_kurulu):
        """Port 1 (P, yakın uç) excite=1, Port 2 (N, yakın uç) excite=-1
        (diferansiyel sürüş), Port 3/4 (uzak uç) excite=0/None (pasif)."""
        import openems_koprusu as oe

        # FDTD sınıfını yakalamak için sarmalıyoruz (portlar listesine erişim için)
        kurulan_fdtd = []
        gercek_sinif = SahteFDTD

        class _YakalayanFDTD(gercek_sinif):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                kurulan_fdtd.append(self)

        import sys as _sys
        _sys.modules["openEMS"].openEMS = _YakalayanFDTD

        geometri = _diferansiyel_cift_geometrisi()
        oe.fdtd_kur_ve_calistir(geometri, str(tmp_path))

        assert len(kurulan_fdtd) == 1
        fdtd = kurulan_fdtd[0]
        assert fdtd.run_cagrildi is True
        assert [p[0].port_nr for p in fdtd.portlar] == [1, 2, 3, 4]
        assert [p[0].excite for p in fdtd.portlar] == [1, -1, 0, 0]
        # port 1/2 yakın uç (x=0), port 3/4 uzak uç (x=10)
        assert fdtd.portlar[0][2][0] == pytest.approx(0.0)   # port1 start.x
        assert fdtd.portlar[2][2][0] == pytest.approx(10.0)  # port3 start.x

    def test_skrf_yoksa_dosya_yazilmaz_ama_hesap_tamamlanir(self, tmp_path, _sahte_openems_kurulu, monkeypatch):
        monkeypatch.delitem(sys.modules, "skrf", raising=False)
        geometri = _diferansiyel_cift_geometrisi()

        bulgu = fdtd_kur_ve_calistir(geometri, str(tmp_path))

        assert bulgu.durum == BulguDurumu.PASS
        assert "skrf kurulu değil" in bulgu.detay
        assert not (tmp_path / "sonuc_diferansiyel.s2p").exists()


# ------------------------------------------------------------------
# s_parametre_degerlendir — dosya yok (FAIL) / skrf yok (KAPSAM_YOK)
# ------------------------------------------------------------------


class TestSParametreDegerlendir:
    def test_dosya_yoksa_fail_kapsam_yok_degil(self, tmp_path):
        bulgu = s_parametre_degerlendir(str(tmp_path / "yok.s4p"), hedef_empedans_ohm=100.0)
        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.taranan == 1
        assert bulgu.ihlaller[0]["sebep"] == "sonuç dosyası bulunamadı"

    def test_skrf_kurulu_degilse_kapsam_yok(self, tmp_path):
        """Bu makinede `skrf` kurulu değil — dosya var gibi davranıp
        (boş bir dosya oluşturup) skrf import KAPSAM_YOK dalının
        GERÇEKTEN tetiklendiğini doğrular."""
        sahte_s4p = tmp_path / "sonuc.s4p"
        sahte_s4p.write_text("! sahte dosya, skrf zaten import edilemeyecek\n", encoding="utf-8")

        bulgu = s_parametre_degerlendir(str(sahte_s4p), hedef_empedans_ohm=100.0)

        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0
        assert "skrf" in bulgu.detay


# ------------------------------------------------------------------
# akim_yogunlugu_haritasi_uret — openems_koprusu API'sinden yönlendirme
# ------------------------------------------------------------------


class TestAkimYogunluguYonlendirme:
    def test_pcbnew_yokken_kapsam_yok_akim_yogunlugu_haritasi_py_ile_ayni(self, tmp_path, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu = akim_yogunlugu_haritasi_uret("board.kicad_pcb", "VCAM", 1.0, str(tmp_path))
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.kontrol == "akim_yogunlugu_haritasi"
