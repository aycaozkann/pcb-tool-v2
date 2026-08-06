"""test_routing_karar_tablosu.py — routing_karar_tablosu.py testleri.

`test_pcbnew_koprusu.py` ile AYNI disiplin: gerçek `pcbnew` import
EDİLMEZ, `sys.modules["pcbnew"]`'e taklit (duck-typing) nesneler
yerleştirilir.
"""

import sys
from typing import List, Optional, Tuple

import pytest

NM_PER_MM = 1_000_000


class SahteNokta:
    def __init__(self, x_mm: float, y_mm: float):
        self.x = int(round(x_mm * NM_PER_MM))
        self.y = int(round(y_mm * NM_PER_MM))


class SahtePad:
    def __init__(self, numara: str, x_mm: float, y_mm: float, net: str):
        self._numara = numara
        self._konum = SahteNokta(x_mm, y_mm)
        self._net = net

    def GetNumber(self) -> str:
        return self._numara

    def GetPosition(self) -> SahteNokta:
        return self._konum

    def GetNetname(self) -> str:
        return self._net


class SahteFootprint:
    def __init__(self, ref: str, padlar: List[SahtePad]):
        self._ref = ref
        self._padlar = padlar

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[SahtePad]:
        return self._padlar


class SahteIz:
    def __init__(self, tip: str, baslangic_mm, bitis_mm, genislik_mm=0.2,
                 net: str = "", ust_katman=0, alt_katman=1, katman=0):
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

    def GetWidth(self) -> int:
        return self._genislik

    def GetNetname(self) -> str:
        return self._net

    def GetPosition(self) -> SahteNokta:
        return self._s

    def GetLayer(self):
        return self._katman

    def TopLayer(self):
        return self._ust

    def BottomLayer(self):
        return self._alt


class SahteBoard:
    def __init__(self, footprints, izler=None):
        self._footprints = footprints
        self._izler = izler or []
        self._katman_adlari = {0: "F.Cu", 1: "B.Cu", 2: "In1.Cu", 6: "In2.Cu"}

    def GetFootprints(self):
        return self._footprints

    def GetTracks(self):
        return self._izler

    def GetLayerName(self, katman_id):
        return self._katman_adlari.get(katman_id, str(katman_id))


class TaklitPcbnew:
    def __init__(self, board: SahteBoard):
        self._board = board

    def LoadBoard(self, yol: str) -> SahteBoard:
        return self._board


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik(monkeypatch):
    """TEK mekanizma: `monkeypatch.setitem`/`delitem` — testlerin İÇİNDE
    de (ör. pcbnew-yok senaryosu) SADECE `monkeypatch` üzerinden mutasyon
    yapılmalı, asla `sys.modules["pcbnew"] = ...` ile DOĞRUDAN. Aksi halde
    bu fixture'ın elle (monkeypatch DIŞI) save/restore'u ile testin kendi
    `monkeypatch.delitem` çağrısının teardown SIRASI çakışır — pytest'in
    LIFO fixture teardown'ında monkeypatch'in KENDİ restore'u bu fixture'ın
    manuel restore'undan SONRA çalışıp onu EZER, ve test dosyasının mock
    board'u `sys.modules['pcbnew']`'de SIZINTI olarak kalıp SONRAKİ test
    dosyasına (ör. `test_uretim_ciktilari_cli.py`) bulaşır — 2026-08-04'te
    tam bu şekilde gerçek bir cross-file test kirliliği olarak yakalandı."""
    monkeypatch.setitem(sys.modules, "pcbnew", TaklitPcbnew(SahteBoard([])))
    yield monkeypatch


def _yukle(board: SahteBoard):
    # Ham atama (monkeypatch İZLEMESİ OLMADAN) BİLEREK yeterli: autouse
    # fixture, testin GERÇEK orijinal `sys.modules["pcbnew"]` durumunu
    # ZATEN `monkeypatch.setitem` ile kayıt altına aldı — bu ham üzerine
    # yazma teardown'da doğru şekilde geri alınır (aşağıdaki fixture notu).
    sys.modules["pcbnew"] = TaklitPcbnew(board)


# ------------------------------------------------------------------
# 1. İsim sezgileri — diff pair / arayüz / kategori (pcbnew GEREKMEZ)
# ------------------------------------------------------------------

from routing_karar_tablosu import (  # noqa: E402
    diff_pair_esini_bul,
    arabirim_turu_tahmin_et,
    empedans_hedefi_getir_net_isminden,
    net_kategorisi_ve_gerekce,
    skew_hesapla_ve_degerlendir,
    net_segmentlerini_cikar,
    katman_sirasi_metni_uret,
    routing_tablosu_uret,
    onerilen_katman,
)


class TestDiffPairEsi:
    def test_p_n_eslesir(self):
        assert diff_pair_esini_bul("PCIE_TX_P", {"PCIE_TX_P", "PCIE_TX_N"}) == "PCIE_TX_N"

    def test_esi_board_da_yoksa_none(self):
        assert diff_pair_esini_bul("PCIE_TX_P", {"PCIE_TX_P"}) is None

    def test_ek_uyusmuyorsa_none(self):
        assert diff_pair_esini_bul("GPIO5", {"GPIO5", "GPIO6"}) is None

    def test_dp_dm_eslesir(self):
        assert diff_pair_esini_bul("USB_DP", {"USB_DP", "USB_DM"}) == "USB_DM"


class TestArabirimTahmini:
    def test_pcie_taninir(self):
        assert arabirim_turu_tahmin_et("PCIE_TX_P") == "PCIE"

    def test_usb3_usb2den_once_taninir(self):
        assert arabirim_turu_tahmin_et("USB3_TX_P") == "USB3_x"

    def test_usb2_taninir(self):
        assert arabirim_turu_tahmin_et("USB_DP") == "USB2_0"

    def test_eslesme_yoksa_none(self):
        assert arabirim_turu_tahmin_et("GPIO17") is None


class TestEmpedansHedefi:
    def test_gercek_tablodan_pcie_85ohm(self):
        assert empedans_hedefi_getir_net_isminden("PCIE_TX_P") == 85.0

    def test_hdmi_100ohm(self):
        assert empedans_hedefi_getir_net_isminden("HDMI0_TX0_P") == 100.0

    def test_eslesmeyen_net_none_yani_na(self):
        assert empedans_hedefi_getir_net_isminden("GPIO17") is None


class TestKategoriGerekce:
    def test_gnd_dogru_kategori(self):
        kat, _ = net_kategorisi_ve_gerekce("GND", None, None)
        assert kat == "GÜÇ/GND"

    def test_guc_deseni_dogru_kategori(self):
        kat, _ = net_kategorisi_ve_gerekce("CARRIER_3V3", None, None)
        assert kat == "GÜÇ"

    def test_diff_pair_ve_arayuz_biliniyorsa_yuksek_hiz(self):
        kat, gerekce = net_kategorisi_ve_gerekce("PCIE_TX_P", "PCIE", "PCIE_TX_N")
        assert kat == "YÜKSEK HIZ"
        assert "PCIE_TX_N" in gerekce

    def test_diff_pair_ama_arayuz_bilinmiyorsa_belirsiz(self):
        kat, _ = net_kategorisi_ve_gerekce("CUSTOM_P", None, "CUSTOM_N")
        assert "belirsiz" in kat.lower()

    def test_standart_io_varsayilan(self):
        kat, _ = net_kategorisi_ve_gerekce("GPIO17", None, None)
        assert kat == "STANDART I/O"

    def test_onerilen_katman_yuksek_hiz_fcu(self):
        assert onerilen_katman("YÜKSEK HIZ") == "F.Cu"

    def test_onerilen_katman_standart_io_bcu(self):
        assert onerilen_katman("STANDART I/O") == "B.Cu"


class TestSkew:
    def test_esik_altinda_pass(self):
        sonuc = skew_hesapla_ve_degerlendir(100.0, 105.0)
        assert sonuc["durum"] == "PASS"
        assert sonuc["skew_mm"] == 5.0

    def test_esik_ustunde_fail(self):
        sonuc = skew_hesapla_ve_degerlendir(100.0, 120.0)
        assert sonuc["durum"] == "FAIL"
        assert sonuc["skew_mm"] == 20.0

    def test_tam_sinirda_pass(self):
        sonuc = skew_hesapla_ve_degerlendir(100.0, 115.0)
        assert sonuc["durum"] == "PASS"


# ------------------------------------------------------------------
# 2. Gerçek board koordinatlarıyla eşleşme (pcbnew mock ÜZERİNDEN)
# ------------------------------------------------------------------

class TestNetSegmentleriCikar:
    def test_iki_segment_bir_via_dogru_cikarilir(self):
        """KİLİT TEST (görev talimatı madde 2): üretilen katman/genişlik/
        uzunluk verisi GERÇEK board koordinatlarıyla BİREBİR eşleşmeli."""
        pad_a = SahtePad("1", 0.0, 0.0, net="TEST_NET")
        pad_b = SahtePad("2", 10.0, 0.0, net="TEST_NET")
        fp = SahteFootprint("U1", [pad_a, pad_b])
        seg1 = SahteIz("PCB_TRACK", (0.0, 0.0), (5.0, 0.0), genislik_mm=0.2, net="TEST_NET", katman=0)
        via = SahteIz("PCB_VIA", (5.0, 0.0), (5.0, 0.0), net="TEST_NET", ust_katman=0, alt_katman=6)
        seg2 = SahteIz("PCB_TRACK", (5.0, 0.0), (10.0, 0.0), genislik_mm=0.25, net="TEST_NET", katman=6)
        board = SahteBoard([fp], izler=[seg1, via, seg2])

        veri = net_segmentlerini_cikar(board, "TEST_NET")

        assert len(veri["pinler"]) == 2
        assert veri["pinler"][0]["konum_mm"] == (0.0, 0.0)
        assert veri["pinler"][1]["konum_mm"] == (10.0, 0.0)
        assert len(veri["segmentler"]) == 2
        assert veri["segmentler"][0]["genislik_mm"] == pytest.approx(0.2)
        assert veri["segmentler"][1]["genislik_mm"] == pytest.approx(0.25)
        # toplam uzunluk = 5.0 + 5.0 = 10.0mm (GERÇEK koordinat farkından)
        assert veri["toplam_uzunluk_mm"] == pytest.approx(10.0)
        assert len(veri["vialar"]) == 1
        assert veri["vialar"][0]["konum_mm"] == (5.0, 0.0)
        assert veri["vialar"][0]["ust_katman"] == "F.Cu"
        assert veri["vialar"][0]["alt_katman"] == "In2.Cu"

    def test_arc_atlanmaz(self):
        """TUZAK (a): GetClass()=='PCB_ARC' de segment olarak sayılmalı."""
        pad = SahtePad("1", 0.0, 0.0, net="N1")
        fp = SahteFootprint("U1", [pad])
        arc = SahteIz("PCB_ARC", (0.0, 0.0), (3.0, 4.0), net="N1", katman=0)
        board = SahteBoard([fp], izler=[arc])

        veri = net_segmentlerini_cikar(board, "N1")

        assert len(veri["segmentler"]) == 1
        assert veri["toplam_uzunluk_mm"] == pytest.approx(5.0)  # 3-4-5 üçgeni

    def test_routsuz_net_bos_liste(self):
        pad = SahtePad("1", 0.0, 0.0, net="N2")
        board = SahteBoard([SahteFootprint("U1", [pad])], izler=[])
        veri = net_segmentlerini_cikar(board, "N2")
        assert veri["segmentler"] == []
        assert veri["vialar"] == []
        assert veri["toplam_uzunluk_mm"] == 0.0


class TestKatmanSirasiMetni:
    def test_zincir_dogru_sirada_kurulur(self):
        pad_a = SahtePad("1", 0.0, 0.0, net="N1")
        fp = SahteFootprint("U1", [pad_a])
        seg = SahteIz("PCB_TRACK", (0.0, 0.0), (5.0, 0.0), net="N1", katman=0)
        via = SahteIz("PCB_VIA", (5.0, 0.0), (5.0, 0.0), net="N1", ust_katman=0, alt_katman=6)
        seg2 = SahteIz("PCB_TRACK", (5.0, 0.0), (10.0, 0.0), net="N1", katman=6)
        board = SahteBoard([fp], izler=[seg, via, seg2])
        veri = net_segmentlerini_cikar(board, "N1")

        metin = katman_sirasi_metni_uret(veri)

        assert "F.Cu" in metin
        assert "VIA" in metin
        assert "In2.Cu" in metin
        assert metin.index("F.Cu") < metin.index("VIA") < metin.index("In2.Cu")

    def test_routsuz_net_acik_mesaj(self):
        veri = {"pinler": [], "segmentler": [], "vialar": []}
        assert "routsuz" in katman_sirasi_metni_uret(veri)


class TestRoutingTablosuUret:
    def test_pcbnew_yokken_none_doner(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        assert routing_tablosu_uret("board.kicad_pcb") is None

    def test_routelanmis_ve_routsuz_ayrimi_dogru(self):
        pad_a = SahtePad("1", 0.0, 0.0, net="ROUTED_NET")
        pad_b = SahtePad("2", 5.0, 0.0, net="ROUTED_NET")
        pad_c = SahtePad("1", 20.0, 20.0, net="UNROUTED_NET")
        pad_d = SahtePad("2", 30.0, 20.0, net="UNROUTED_NET")
        fp1 = SahteFootprint("R1", [pad_a, pad_b])
        fp2 = SahteFootprint("R2", [pad_c, pad_d])
        seg = SahteIz("PCB_TRACK", (0.0, 0.0), (5.0, 0.0), net="ROUTED_NET", katman=0)
        board = SahteBoard([fp1, fp2], izler=[seg])
        _yukle(board)

        sonuc = routing_tablosu_uret("board.kicad_pcb")

        routed_isimler = {r["Net Adı"] for r in sonuc["routelanmis"]}
        unrouted_isimler = {r["Net Adı"] for r in sonuc["routsuz"]}
        assert routed_isimler == {"ROUTED_NET"}
        assert unrouted_isimler == {"UNROUTED_NET"}
        # kuş uçuşu mesafe GERÇEK koordinat farkından: (30-20, 20-20) -> 10.0mm
        unrouted_satir = sonuc["routsuz"][0]
        assert unrouted_satir["Kuş Uçuşu Mesafe (mm)"] == pytest.approx(10.0)
        assert unrouted_satir["Neden Çizilemedi"] == "denenmedi"
