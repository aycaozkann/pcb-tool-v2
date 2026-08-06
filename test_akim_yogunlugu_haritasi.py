"""akim_yogunlugu_haritasi.py için test suite.

İki test grubu:
  1. Çekirdek çözücü (`bakir_seridi_coz`, `bakir_poligonu_coz`,
     `isi_haritasi_kaydet`) — openEMS/pcbnew GEREKTİRMEZ, `numpy`/`scipy`/
     `matplotlib` bu ortamda KURULU olduğu için TAM olarak gerçek test
     edilir (görev tanımının kendi kabul kriteri: "basit dikdörtgen bir
     bakır şerit için analitik olarak bilinen akım dağılımıyla (düzgün
     dağılım) karşılaştırma").
  2. `akim_yogunlugu_haritasi_uret()` — pcbnew köprüsü, `test_pcbnew_
     koprusu.py` ile AYNI sahte-pcbnew mock desenini kullanır.
"""

from __future__ import annotations

import sys
from typing import List, Tuple

import numpy as np
import pytest

from bulgu_sozlesmesi import BulguDurumu
from akim_yogunlugu_haritasi import (
    ResistifMeshSonucu,
    _nokta_poligon_icinde_mi,
    akim_yogunlugu_haritasi_uret,
    bakir_poligonu_coz,
    bakir_seridi_coz,
    isi_haritasi_kaydet,
)


# ------------------------------------------------------------------
# 1. Çekirdek çözücü — dikdörtgen şerit, analitik karşılaştırma
# ------------------------------------------------------------------


class TestBakirSeridiCoz:
    def test_duzgun_dagilim_analitik_degerle_ortusur(self):
        """DOĞRULAMA (görev tanımının kendi kabul kriteri): 20mm x 5mm bir
        şerit, uçtan uca 2A akım. Analitik beklenti: J = I / genislik =
        2 / 0.005m = 400 A/m, ŞERİDİN HER YERİNDE (dikdörtgen + uçtan-uca
        düzgün enjeksiyon -> tam düzgün dağılım, kenar etkisi YOK)."""
        sonuc = bakir_seridi_coz(
            uzunluk_mm=20.0, genislik_mm=5.0, akim_a=2.0,
            bakir_agirligi_oz=1.0, n_boy=40, n_en=10,
        )
        beklenen_a_m = 2.0 / (5.0 / 1000.0)
        gecerli = sonuc.gecerli_yogunluklar()
        assert gecerli.size > 0
        assert np.allclose(gecerli, beklenen_a_m, rtol=1e-6)
        assert sonuc.maks_akim_yogunlugu_a_m == pytest.approx(beklenen_a_m, rel=1e-6)

    def test_toplam_akim_alaninda_tasinir(self):
        sonuc = bakir_seridi_coz(10.0, 2.0, akim_a=1.5, n_boy=20, n_en=6)
        assert sonuc.toplam_akim_a == 1.5

    def test_daha_kalin_bakir_daha_dusuk_gerilim_dususu_uretir(self):
        """Levha direnci kalınlıkla TERS orantılı — 2oz bakır, 1oz'a göre
        aynı akımda YARI gerilim düşümü üretmeli (Rs = rho/kalinlik)."""
        ince = bakir_seridi_coz(20.0, 5.0, 1.0, bakir_agirligi_oz=1.0, n_boy=20, n_en=6)
        kalin = bakir_seridi_coz(20.0, 5.0, 1.0, bakir_agirligi_oz=2.0, n_boy=20, n_en=6)
        dv_ince = float(np.nanmax(ince.node_gerilim_v) - np.nanmin(ince.node_gerilim_v))
        dv_kalin = float(np.nanmax(kalin.node_gerilim_v) - np.nanmin(kalin.node_gerilim_v))
        assert dv_kalin == pytest.approx(dv_ince / 2.0, rel=1e-3)

    def test_giris_esit_cikis_sutun_reddedilir(self):
        from akim_yogunlugu_haritasi import _mesh_coz
        maske = np.ones((3, 5), dtype=bool)
        with pytest.raises(ValueError):
            _mesh_coz(maske, 10.0, 2.0, 1.0, 1.0, giris_sutun=2, cikis_sutun=2)


# ------------------------------------------------------------------
# Nokta-poligon içi testi
# ------------------------------------------------------------------


class TestNoktaPoligonIcindeMi:
    def test_kare_icindeki_nokta(self):
        kare = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _nokta_poligon_icinde_mi(5, 5, kare) is True

    def test_kare_disindaki_nokta(self):
        kare = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _nokta_poligon_icinde_mi(15, 5, kare) is False

    def test_l_seklinde_cikinti_disindaki_nokta(self):
        # L şekli: 10x10 kare + sağ-üstten 5x5'lik bir çentik ÇIKARILMIŞ
        l_sekli = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        assert _nokta_poligon_icinde_mi(7, 7, l_sekli) is False  # çentik bölgesi
        assert _nokta_poligon_icinde_mi(2, 2, l_sekli) is True


# ------------------------------------------------------------------
# Genel poligon çözücü — L şekli (bounding-box YAKLAŞIMI DEĞİL)
# ------------------------------------------------------------------


class TestBakirPoligonuCoz:
    def test_l_seklinde_poligon_disindaki_hucreler_nan(self):
        l_sekli = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        sonuc = bakir_poligonu_coz(l_sekli, akim_a=1.0, cozunurluk_mm=1.0)
        # çentik bölgesindeki (poligon dışı) hücrelerin gerilimi NaN olmalı
        assert np.isnan(sonuc.node_gerilim_v).any()
        # poligon içindeki en az bir hücre GERÇEKTEN çözülmüş olmalı
        assert not np.isnan(sonuc.node_gerilim_v).all()

    def test_dikdortgen_ozel_hali_bakir_seridi_ile_tutarli(self):
        dikdortgen = [(0, 0), (20, 0), (20, 5), (0, 5)]
        sonuc = bakir_poligonu_coz(dikdortgen, akim_a=2.0, cozunurluk_mm=0.5)
        beklenen_a_m = 2.0 / (5.0 / 1000.0)
        gecerli = sonuc.gecerli_yogunluklar()
        # kenarlarda ayrık rasterizasyon küçük sapma yaratabilir; orta
        # bölge (ilk/son birkaç sütun hariç) analitik değere yakın olmalı
        orta = sonuc.akim_yogunlugu_a_m[:, 3:-3]
        orta_gecerli = orta[~np.isnan(orta)]
        assert orta_gecerli.size > 0
        assert np.allclose(orta_gecerli, beklenen_a_m, rtol=0.05)

    def test_dejenere_poligon_reddedilir(self):
        with pytest.raises(ValueError):
            bakir_poligonu_coz([(0, 0), (0, 0), (0, 0)], akim_a=1.0)


# ------------------------------------------------------------------
# Isı haritası PNG üretimi (matplotlib bu ortamda KURULU)
# ------------------------------------------------------------------


class TestIsiHaritasiKaydet:
    def test_png_gercekten_yazilir(self, tmp_path):
        sonuc = bakir_seridi_coz(10.0, 2.0, 1.0, n_boy=10, n_en=4)
        yol = isi_haritasi_kaydet(sonuc, tmp_path / "alt" / "harita.png")
        assert yol is not None
        assert yol.exists()
        assert yol.stat().st_size > 0


# ------------------------------------------------------------------
# 2. pcbnew köprüsü — sahte pcbnew mock deseni (test_pcbnew_koprusu.py ile AYNI)
# ------------------------------------------------------------------


class SahteIz:
    def __init__(self, tip, baslangic_mm, bitis_mm, genislik_mm=0.2, net=""):
        self._tip = tip
        self._s = baslangic_mm
        self._e = bitis_mm
        self._genislik_mm = genislik_mm
        self._net = net

    def GetClass(self):
        return self._tip

    def GetNetname(self):
        return self._net

    class _Nokta:
        def __init__(self, x_mm, y_mm):
            self.x = int(round(x_mm * 1_000_000))
            self.y = int(round(y_mm * 1_000_000))

    def GetStart(self):
        return SahteIz._Nokta(*self._s)

    def GetEnd(self):
        return SahteIz._Nokta(*self._e)

    def GetPosition(self):
        return SahteIz._Nokta(*self._s)

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


class TestAkimYogunluguHaritasiUret:
    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch, tmp_path):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu = akim_yogunlugu_haritasi_uret("board.kicad_pcb", "VCAM", 1.0, str(tmp_path))
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0

    def test_net_ize_sahip_degilse_kapsam_yok(self, tmp_path):
        _yukle(SahteBoard([SahteIz("PCB_TRACK", (0, 0), (1, 0), net="BASKA_NET")]))
        bulgu = akim_yogunlugu_haritasi_uret("board.kicad_pcb", "VCAM", 1.0, str(tmp_path))
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0

    def test_gercek_izlerle_hesaplanir_ve_png_yazilir(self, tmp_path):
        izler = [
            SahteIz("PCB_TRACK", (0.0, 0.0), (0.0, 2.0), genislik_mm=0.5, net="VCAM"),
            SahteIz("PCB_TRACK", (0.0, 0.0), (15.0, 0.0), genislik_mm=0.5, net="VCAM"),
            SahteIz("PCB_TRACK", (15.0, 0.0), (15.0, 2.0), genislik_mm=0.5, net="VCAM"),
        ]
        _yukle(SahteBoard(izler))

        bulgu = akim_yogunlugu_haritasi_uret("board.kicad_pcb", "VCAM", 0.5, str(tmp_path))

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 1
        png_dosyalari = list(tmp_path.glob("akim_yogunlugu_*.png"))
        assert len(png_dosyalari) == 1
        assert png_dosyalari[0].stat().st_size > 0
