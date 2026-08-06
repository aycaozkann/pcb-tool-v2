"""openems_3d_extractor.py için test suite.

`test_pcbnew_koprusu.py`/`test_openems_koprusu.py` ile AYNI sahte-pcbnew
mock desenini kullanır (gerçek `pcbnew` bu ortamda kurulu değil).
`katman_z_konumu_getir()` ayrıca GERÇEK `pcb_stackup_planner.stackup_planla()`
çıktısına karşı test edilir (uydurma bir "StackupSonucu" tipi YOK — gerçek
`Dict[str, str]` dönüş tipine bağlandığının kanıtı).
"""

from __future__ import annotations

import sys

import pytest

from bulgu_sozlesmesi import BulguDurumu
from openems_3d_extractor import (
    csxcad_kutu_olustur,
    esleş_diferansiyel_ciftler,
    izleri_ve_vialari_cikar,
    katman_z_konumu_getir,
)


# ------------------------------------------------------------------
# esleş_diferansiyel_ciftler — pcbnew mock (sadece GetNetsByName gerekir)
# ------------------------------------------------------------------


class _SahteNetInfo:
    def __init__(self, kod):
        self._kod = kod

    def GetNetCode(self):
        return self._kod


class SahteBoardNetler:
    def __init__(self, net_adlari):
        self._netler = {ad: _SahteNetInfo(i) for i, ad in enumerate(net_adlari)}

    def GetNetsByName(self):
        return self._netler


class TestEslesDiferansiyelCiftler:
    def test_sonek_eslesen_ciftler_bulunur(self):
        board = SahteBoardNetler(["MIPI_D0_P", "MIPI_D0_N", "MIPI_CLK_P", "MIPI_CLK_N"])
        ciftler = esleş_diferansiyel_ciftler(board)
        assert set(ciftler) == {("MIPI_CLK_P", "MIPI_CLK_N"), ("MIPI_D0_P", "MIPI_D0_N")}

    def test_alt_string_degil_sonek_esler(self):
        """"GPIO_D0_EN"/"LED0" gibi alakasız netler alt-string olarak
        eşleşse bile SONEK uymadığı için ELENIR."""
        board = SahteBoardNetler(["GPIO_D0_EN", "LED0", "MIPI_D0_P", "MIPI_D0_N"])
        ciftler = esleş_diferansiyel_ciftler(board)
        assert ciftler == [("MIPI_D0_P", "MIPI_D0_N")]

    def test_karsiligi_olmayan_pozitif_net_eslesmez(self):
        board = SahteBoardNetler(["MIPI_D0_P", "GND"])
        assert esleş_diferansiyel_ciftler(board) == []

    def test_bos_board(self):
        assert esleş_diferansiyel_ciftler(SahteBoardNetler([])) == []


# ------------------------------------------------------------------
# katman_z_konumu_getir — GERÇEK pcb_stackup_planner.stackup_planla() ile
# ------------------------------------------------------------------


class TestKatmanZKonumuGetir:
    def test_literal_stackup_sozlugunde_z_sirayla_hesaplanir(self):
        stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND", "Katman_3": "GÜÇ", "Katman_4": "SİNYAL"}
        from pcb_stackup_planner import KATMAN_KALINLIK_VARSAYIMI_MM

        assert katman_z_konumu_getir(stackup, "Katman_1") == (0.0, KATMAN_KALINLIK_VARSAYIMI_MM)
        assert katman_z_konumu_getir(stackup, "Katman_2") == (
            KATMAN_KALINLIK_VARSAYIMI_MM, 2 * KATMAN_KALINLIK_VARSAYIMI_MM,
        )
        assert katman_z_konumu_getir(stackup, "Katman_4") == (
            3 * KATMAN_KALINLIK_VARSAYIMI_MM, 4 * KATMAN_KALINLIK_VARSAYIMI_MM,
        )

    def test_bilinmeyen_katman_none_doner(self):
        assert katman_z_konumu_getir({"Katman_1": "SİNYAL"}, "Katman_99") is None

    def test_ozel_kalinlik_verilirse_kullanilir(self):
        stackup = {"Katman_1": "SİNYAL", "Katman_2": "GND"}
        assert katman_z_konumu_getir(stackup, "Katman_2", katman_kalinlik_mm=0.2) == (0.2, 0.4)

    def test_gercek_stackup_planla_ciktisiyla_entegre(self):
        """DOĞRULAMA: bu fonksiyon `pcb_stackup_planner.py`'nin UYDURULMUŞ
        bir tipini DEĞİL, GERÇEK `stackup_planla()` çağrısının ürettiği
        `Dict[str, str]`'i kabul eder — burada gerçekten çağrılıp
        sonucun anahtarlarıyla test edilir."""
        from pcb_stackup_planner import (
            Komponent, KilifTuru, MekanikVeTermalKisitlar, Net, SinyalTuru, stackup_planla,
        )

        sinyaller = [
            Net("3V3", SinyalTuru.GUC, maks_akim=1.0),
            Net("GND", SinyalTuru.GND),
            Net("MIPI_D0", SinyalTuru.HIZLI_DIJITAL, empedans_kontrolu_gerekli_mi=True),
        ]
        komponentler = [Komponent("U1", KilifTuru.QFN, pin_sayisi=32, guc_pini_sayisi=2, dekuplaj_kapasitor_sayisi=2)]
        kisitlar = MekanikVeTermalKisitlar(hedef_kalinlik_mm=1.6)

        stackup = stackup_planla(sinyaller, komponentler, kisitlar)

        assert "Katman_1" in stackup
        sonuc = katman_z_konumu_getir(stackup, "Katman_1")
        assert sonuc is not None
        z_ust, z_alt = sonuc
        assert z_ust == 0.0
        assert z_alt > z_ust


# ------------------------------------------------------------------
# izleri_ve_vialari_cikar / _geometri_topla — pcbnew mock
# ------------------------------------------------------------------


class SahteNokta:
    def __init__(self, x_mm, y_mm):
        self.x = int(round(x_mm * 1_000_000))
        self.y = int(round(y_mm * 1_000_000))


class SahteIz:
    def __init__(self, tip, baslangic_mm, bitis_mm, genislik_mm, net_kodu, net_adi, katman_adi="F.Cu"):
        self._tip = tip
        self._s = SahteNokta(*baslangic_mm)
        self._e = SahteNokta(*bitis_mm)
        self._genislik = int(round(genislik_mm * 1_000_000))
        self._net_kodu = net_kodu
        self._net_adi = net_adi
        self._katman_adi = katman_adi
        self._drill = int(round(0.2 * 1_000_000))

    def GetClass(self):
        return self._tip

    def GetNetCode(self):
        return self._net_kodu

    def GetNetname(self):
        return self._net_adi

    def GetStart(self):
        return self._s

    def GetEnd(self):
        return self._e

    def GetPosition(self):
        return self._s

    def GetWidth(self, *_args):
        return self._genislik

    def GetDrillValue(self):
        return self._drill

    def GetLayer(self):
        return 0


class SahteBoardTracks:
    def __init__(self, net_adlari, izler):
        self._netler = {ad: _SahteNetInfo(i) for i, ad in enumerate(net_adlari)}
        self._izler = izler

    def GetNetsByName(self):
        return self._netler

    def GetTracks(self):
        return self._izler

    def GetLayerName(self, katman_id):
        return "F.Cu"


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


class TestIzleriVeVialariCikar:
    def test_pcbnew_kurulu_degilse_kapsam_yok_bos_liste(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu, geometri = izleri_ve_vialari_cikar("board.kicad_pcb", ["D_P", "D_N"])
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0
        assert geometri == []

    def test_hedef_net_bulunamazsa_kapsam_yok(self):
        board = SahteBoardTracks(["BASKA_NET"], [])
        _yukle(board)
        bulgu, geometri = izleri_ve_vialari_cikar("board.kicad_pcb", ["D_P", "D_N"])
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert geometri == []

    def test_dondurulen_tuple_bulgu_ve_liste_ayri_kanallardan_gelir(self):
        """DÜZELTME kanıtı: dönüş `Tuple[Bulgu, List[Dict]]`'tir — Bulgu
        TEK BAŞINA veri taşımaz."""
        # SahteBoardTracks.GetNetsByName() net kodlarını LİSTE SIRASINA göre
        # atar (D_P=0, D_N=1, BASKA=2) — iz/via'ların net_kodu bu sırayla
        # TUTARLI olmalı, yoksa `izleri_ve_vialari_cikar` içindeki net-kodu
        # eşleştirmesi (gerçek pcbnew davranışıyla AYNI mantık) hiçbir şeyi
        # bulamaz.
        izler = [
            SahteIz("PCB_TRACK", (0.0, 0.0), (5.0, 0.0), 0.15, net_kodu=0, net_adi="D_P"),
            SahteIz("PCB_TRACK", (0.0, 0.2), (5.0, 0.2), 0.15, net_kodu=1, net_adi="D_N"),
            SahteIz("PCB_VIA", (5.0, 0.0), (5.0, 0.0), 0.3, net_kodu=0, net_adi="D_P"),
            SahteIz("PCB_TRACK", (0.0, 5.0), (5.0, 5.0), 0.15, net_kodu=2, net_adi="BASKA"),
        ]
        board = SahteBoardTracks(["D_P", "D_N", "BASKA"], izler)
        _yukle(board)

        bulgu, geometri = izleri_ve_vialari_cikar("board.kicad_pcb", ["D_P", "D_N"])

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 4  # board'daki TÜM iz+via sayısı
        assert len(geometri) == 3  # sadece D_P/D_N'e ait 3 obje
        tipler = {g["tip"] for g in geometri}
        assert tipler == {"iz", "via"}
        assert all(g["net_adi"] in ("D_P", "D_N") for g in geometri)


# ------------------------------------------------------------------
# csxcad_kutu_olustur — saf geometri matematiği (CSXCAD GEREKMEZ)
# ------------------------------------------------------------------


class SahteMetalOzelligi:
    def __init__(self):
        self.cagrilar = []

    def AddPolygon(self, points, norm_dir, elevation, priority=10):
        self.cagrilar.append((points, norm_dir, elevation, priority))
        return object()


class TestCsxcadKutuOlustur:
    def test_yatay_iz_dogru_koseler_uretir(self):
        metal = SahteMetalOzelligi()
        iz = {"baslangic": (0.0, 0.0), "bitis": (10.0, 0.0), "genislik_mm": 1.0}

        csxcad_kutu_olustur(metal, iz, z_ust_mm=0.035)

        points, norm_dir, elevation, priority = metal.cagrilar[0]
        xs, ys = points
        assert xs == pytest.approx([0.0, 10.0, 10.0, 0.0])
        assert ys == pytest.approx([0.5, 0.5, -0.5, -0.5])
        assert norm_dir == "z"
        assert elevation == pytest.approx(0.035)
        assert priority == 10

    def test_dikey_iz_dogru_koseler_uretir(self):
        metal = SahteMetalOzelligi()
        iz = {"baslangic": (0.0, 0.0), "bitis": (0.0, 10.0), "genislik_mm": 2.0}
        csxcad_kutu_olustur(metal, iz, z_ust_mm=0.0)
        xs, ys = metal.cagrilar[0][0]
        assert xs == pytest.approx([-1.0, -1.0, 1.0, 1.0])
        assert ys == pytest.approx([0.0, 10.0, 10.0, 0.0])

    def test_45_derece_iz_genislik_bbox_ile_KARISTIRILMAZ(self):
        """DÜZELTME kanıtı: eski `AddBox(min/max)` deseni 45°'de genişliği
        ~1.4x büyük gösterirdi. Burada köşeler arası MESAFE (genişlik
        yönünde) TAM `genislik_mm` olmalı, bbox köşegeni DEĞİL."""
        import math

        metal = SahteMetalOzelligi()
        iz = {"baslangic": (0.0, 0.0), "bitis": (10.0, 10.0), "genislik_mm": 1.0}
        csxcad_kutu_olustur(metal, iz, z_ust_mm=0.0)
        xs, ys = metal.cagrilar[0][0]
        kose0 = (xs[0], ys[0])
        kose3 = (xs[3], ys[3])
        genislik_olculen = math.hypot(kose0[0] - kose3[0], kose0[1] - kose3[1])
        assert genislik_olculen == pytest.approx(1.0)

    def test_dejenere_segment_reddedilir(self):
        metal = SahteMetalOzelligi()
        iz = {"baslangic": (1.0, 1.0), "bitis": (1.0, 1.0), "genislik_mm": 0.5}
        with pytest.raises(ValueError):
            csxcad_kutu_olustur(metal, iz, z_ust_mm=0.0)
