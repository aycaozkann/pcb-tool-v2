"""guvenli_routing_katmani.py için test suite.

`netclass_genislik_dogrula()`/`_bulgu()` SAF mantıktır (pcbnew GEREKMEZ) —
bu ortamda TAM olarak gerçek test edilir. `netclass_genislik_dogrula_
board()`/`guvenli_yaz_ve_dogrula()` gerçek `pcbnew`+`kicad-cli` gerektirir
— `test_pcbnew_koprusu.py` ile AYNI sahte-pcbnew mock desenini kullanır,
`kicad-cli` çağrısı ise `subprocess.run`'ı (kicad-cli ikili dosyasının
GERÇEKTEN çalıştığı gibi ilgili JSON dosyasına yazan bir sahte
fonksiyonla) monkeypatch'leyerek taklit edilir.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from bulgu_sozlesmesi import BulguDurumu
from guvenli_routing_katmani import (
    NetclassGenislikIhlali,
    guvenli_yaz_ve_dogrula,
    netclass_genislik_dogrula,
    netclass_genislik_dogrula_board,
    netclass_genislik_dogrula_bulgu,
)
from hata_hafizasi import HataHafizasi, HataKaydi, KontrolTipi, Sonuc


# ------------------------------------------------------------------
# 1. netclass_genislik_dogrula / _bulgu — saf mantık
# ------------------------------------------------------------------


class TestNetclassGenislikDogrula:
    def test_uyumlu_netclasslar_ihlal_uretmez(self):
        ihlaller = netclass_genislik_dogrula({"HS_MIPI_100": 0.2, "Default": 0.25}, board_min_track_width_mm=0.2)
        assert ihlaller == []

    def test_dar_netclass_ihlal_uretir(self):
        """REGRESYON KİLİDİ: cm4-io-test'in gerçek senaryosu — netclass
        0.18mm, board min 0.2mm."""
        ihlaller = netclass_genislik_dogrula({"HS_GBE_100": 0.18, "HS_MIPI_100": 0.18}, board_min_track_width_mm=0.2)
        assert len(ihlaller) == 2
        assert all(isinstance(i, NetclassGenislikIhlali) for i in ihlaller)
        assert ihlaller[0].tanimli_track_width_mm == 0.18
        assert ihlaller[0].board_min_track_width_mm == 0.2

    def test_tam_sinirdaki_genislik_ihlal_sayilmaz(self):
        ihlaller = netclass_genislik_dogrula({"X": 0.2}, board_min_track_width_mm=0.2)
        assert ihlaller == []

    def test_bulgu_sarmalayicisi_bos_sozlukte_kapsam_yok(self):
        bulgu = netclass_genislik_dogrula_bulgu({}, board_min_track_width_mm=0.2)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0

    def test_bulgu_sarmalayicisi_ihlalde_fail(self):
        bulgu = netclass_genislik_dogrula_bulgu({"HS_GBE_100": 0.18}, board_min_track_width_mm=0.2)
        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["netclass"] == "HS_GBE_100"

    def test_bulgu_sarmalayicisi_uyumluda_pass(self):
        bulgu = netclass_genislik_dogrula_bulgu({"Default": 0.25}, board_min_track_width_mm=0.2)
        assert bulgu.durum == BulguDurumu.PASS


# ------------------------------------------------------------------
# 2. Sahte pcbnew + sahte kicad-cli (subprocess.run monkeypatch)
# ------------------------------------------------------------------


class SahteZones:
    def __init__(self, zones=None):
        self._zones = zones or []

    def __iter__(self):
        return iter(self._zones)


class SahteDesignSettings:
    def __init__(self, min_track_width_nm, netclasslar):
        self.m_TrackMinWidth = min_track_width_nm
        self._netclasslar = netclasslar

    def GetNetClasses(self):
        return self._netclasslar


class SahteNetClass:
    def __init__(self, ad, genislik_nm):
        self._ad = ad
        self._genislik = genislik_nm

    def GetName(self):
        return self._ad

    def GetTrackWidth(self):
        return self._genislik


class SahteBoard:
    def __init__(self, settings):
        self._settings = settings
        self.kaydedilen_yollar = []

    def GetDesignSettings(self):
        return self._settings

    def Save(self, yol):
        self.kaydedilen_yollar.append(yol)

    def Zones(self):
        return SahteZones()


class SahteZoneFiller:
    def __init__(self, board):
        self.board = board
        self.fill_cagrildi = False

    def Fill(self, zones):
        self.fill_cagrildi = True
        return True


class SahtePcbnewModulu:
    def __init__(self, board):
        self._board = board

    def LoadBoard(self, yol):
        return self._board

    def ZONE_FILLER(self, board):
        return SahteZoneFiller(board)


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik():
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _pcbnew_yukle(board):
    sys.modules["pcbnew"] = SahtePcbnewModulu(board)


class TestNetclassGenislikDogrulaBoard:
    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu = netclass_genislik_dogrula_board("board.kicad_pcb")
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0

    def test_gercek_netclass_verisiyle_ihlal_yakalanir(self):
        settings = SahteDesignSettings(
            min_track_width_nm=200_000,  # 0.2mm
            netclasslar={"HS_GBE_100": SahteNetClass("HS_GBE_100", 180_000)},  # 0.18mm
        )
        _pcbnew_yukle(SahteBoard(settings))

        bulgu = netclass_genislik_dogrula_board("board.kicad_pcb")

        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["netclass"] == "HS_GBE_100"


# ------------------------------------------------------------------
# 3. guvenli_yaz_ve_dogrula — sahte kicad-cli subprocess.run ile
# ------------------------------------------------------------------


def _sahte_subprocess_run_uret(rapor_dizisi):
    """`subprocess.run` yerine geçer — komuttaki `--output` yolunu bulup
    sırayla `rapor_dizisi`'ndeki JSON'u oraya yazar (gerçek kicad-cli'nin
    `--output` davranışını taklit eder)."""
    durum = {"n": 0}

    def _sahte_run(komut, capture_output=True, text=True, timeout=None):
        idx = komut.index("--output")
        rapor_path = komut[idx + 1]
        i = min(durum["n"], len(rapor_dizisi) - 1)
        rapor = rapor_dizisi[i]
        durum["n"] += 1
        with open(rapor_path, "w", encoding="utf-8") as fh:
            json.dump(rapor, fh)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return _sahte_run


@pytest.fixture(autouse=True)
def _kicad_cli_yolunu_bul_taklit(monkeypatch):
    import arac_yollari

    monkeypatch.setattr(arac_yollari, "kicad_cli_yolunu_bul", lambda *_a, **_k: "kicad-cli-sahte")


class TestGuvenliYazVeDogrula:
    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch, tmp_path):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        bulgu = guvenli_yaz_ve_dogrula(str(tmp_path / "yok.kicad_pcb"), lambda b: None)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_board_dosyasi_yoksa_kapsam_yok(self, tmp_path):
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))
        bulgu = guvenli_yaz_ve_dogrula(str(tmp_path / "yok.kicad_pcb"), lambda b: None)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_regresyon_yoksa_pass_ve_degisiklik_korunur(self, tmp_path, monkeypatch):
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("sahte board icerigi", encoding="utf-8")

        settings = SahteDesignSettings(200_000, {})
        board = SahteBoard(settings)
        _pcbnew_yukle(board)

        # önceki DRC: 5 violation, 2 unconnected ; yeni DRC: 3 violation, 1 unconnected (İYİLEŞME)
        rapor_onceki = {"violations": [{}] * 5, "unconnected_items": [{}] * 2}
        rapor_yeni = {"violations": [{}] * 3, "unconnected_items": [{}] * 1}
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        degisiklik_cagrildi = {"evet": False}

        def _degisiklik(b):
            degisiklik_cagrildi["evet"] = True

        bulgu = guvenli_yaz_ve_dogrula(str(board_path), _degisiklik, zone_refill_yap=False)

        assert bulgu.durum == BulguDurumu.PASS
        assert degisiklik_cagrildi["evet"] is True
        assert board_path.with_suffix(board_path.suffix + ".guvenli_yaz_yedek").exists() or \
            (tmp_path / (board_path.name + ".guvenli_yaz_yedek")).exists()

    def test_violation_artarsa_geri_alinir(self, tmp_path, monkeypatch):
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")

        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        rapor_onceki = {"violations": [{}] * 2, "unconnected_items": [{}] * 0}
        rapor_yeni = {"violations": [{}] * 5, "unconnected_items": [{}] * 0}  # KÖTÜLEŞTİ
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(str(board_path), lambda b: None, zone_refill_yap=False)

        assert bulgu.durum == BulguDurumu.FAIL
        assert "GERİ ALINDI" in bulgu.ihlaller[0]["sebep"]
        # dosya İÇERİĞİ geri yüklenmiş olmalı (SahteBoard.Save() gerçek
        # dosyaya yazmadığı için içerik hâlâ "ORIJINAL" olmalı)
        assert board_path.read_text(encoding="utf-8") == "ORIJINAL"

    def test_sadece_unconnected_items_artarsa_da_geri_alinir(self, tmp_path, monkeypatch):
        """DOSYA BAŞLIĞI KURALI: 'sadece 0 violation görmek yetmez' —
        violations SABİT kalıp unconnected_items artarsa da regresyon
        SAYILMALI."""
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        rapor_onceki = {"violations": [], "unconnected_items": [{}] * 3}
        rapor_yeni = {"violations": [], "unconnected_items": [{}] * 10}  # unconnected KÖTÜLEŞTİ
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(str(board_path), lambda b: None, zone_refill_yap=False)

        assert bulgu.durum == BulguDurumu.FAIL
        assert board_path.read_text(encoding="utf-8") == "ORIJINAL"

    def test_onceki_drc_olculemezse_regresyon_yapilamadi_diye_isaretlenir(self, tmp_path, monkeypatch):
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("X", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        cagri_sayaci = {"n": 0}

        def _once_hata_sonra_basarili(komut, capture_output=True, text=True, timeout=None):
            cagri_sayaci["n"] += 1
            if cagri_sayaci["n"] == 1:
                raise RuntimeError("kicad-cli hiç çalışmadı (simüle hata)")
            idx = komut.index("--output")
            with open(komut[idx + 1], "w", encoding="utf-8") as fh:
                json.dump({"violations": [], "unconnected_items": []}, fh)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _once_hata_sonra_basarili)

        bulgu = guvenli_yaz_ve_dogrula(str(board_path), lambda b: None, zone_refill_yap=False)

        assert bulgu.durum == BulguDurumu.PASS
        assert "yapilamadi" in bulgu.detay


# ------------------------------------------------------------------
# 4. FAZ 0 madde 5: hata_hafizasi entegrasyonu
# ------------------------------------------------------------------


class TestGuvenliYazVeDogrulaHataHafizasi:
    def test_hafiza_verilmezse_davranis_eskisiyle_ayni(self, tmp_path, monkeypatch):
        """Geriye dönük uyumluluk: hata_hafizasi=None (varsayılan) iken
        detayda HAFIZA UYARISI görünmez, kayıt YAZILMAZ."""
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        rapor_onceki = {"violations": [{}] * 5, "unconnected_items": [{}] * 2}
        rapor_yeni = {"violations": [{}] * 3, "unconnected_items": [{}] * 1}
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(str(board_path), lambda b: None, zone_refill_yap=False)

        assert bulgu.durum == BulguDurumu.PASS
        assert "HAFIZA" not in bulgu.detay

    def test_gecmis_basarisiz_strateji_hafiza_uyarisi_uretir(self, tmp_path, monkeypatch):
        """Aynı `degisiklik_aciklamasi` daha önce BASARISIZ kaydedilmişse,
        bu strateji tekrar denenirken bir HAFIZA UYARISI eklenir — deneme
        yine de yapılır (fonksiyon kendiliğinden engel olmaz), sadece
        çağırana bilgi taşınır."""
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        hafiza = HataHafizasi(dosya_yolu=str(tmp_path / "hafiza.md"))
        hafiza.kaydet(HataKaydi(
            tip=KontrolTipi.DRC,
            mesaj="MIPI_CAM0 P/N coupled route, In2.Cu via gecisi",
            kok_neden="via annular ring yetersiz",
            cozum="Bu strateji DRC regresyonuna yol acti, geri alindi.",
            sonuc=Sonuc.BASARISIZ,
            proje="cm4-io-test",
        ))

        rapor_onceki = {"violations": [{}] * 5, "unconnected_items": [{}] * 2}
        rapor_yeni = {"violations": [{}] * 3, "unconnected_items": [{}] * 1}
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(
            str(board_path), lambda b: None, zone_refill_yap=False,
            hata_hafizasi=hafiza,
            degisiklik_aciklamasi="MIPI_CAM0 P/N coupled route, In2.Cu via gecisi",
        )

        assert bulgu.durum == BulguDurumu.PASS  # deneme yine de yapıldı
        assert "HAFIZA UYARISI" in bulgu.detay
        assert "cm4-io-test" in bulgu.detay

    def test_basarisiz_deneme_otomatik_hafizaya_yazilir(self, tmp_path, monkeypatch):
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        hafiza = HataHafizasi(dosya_yolu=str(tmp_path / "hafiza.md"))

        rapor_onceki = {"violations": [{}] * 2, "unconnected_items": [{}] * 0}
        rapor_yeni = {"violations": [{}] * 5, "unconnected_items": [{}] * 0}  # KÖTÜLEŞTİ
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(
            str(board_path), lambda b: None, zone_refill_yap=False,
            hata_hafizasi=hafiza, degisiklik_aciklamasi="HDMI0 J2->ESD hop, via/katman A*",
            proje="cm4-io-test",
        )

        assert bulgu.durum == BulguDurumu.FAIL
        kayitlar = hafiza.kayitlari_oku()
        assert len(kayitlar) == 1
        assert kayitlar[0].sonuc == Sonuc.BASARISIZ
        assert kayitlar[0].proje == "cm4-io-test"

    def test_basarili_deneme_otomatik_hafizaya_cozuldu_diye_yazilir(self, tmp_path, monkeypatch):
        board_path = tmp_path / "board.kicad_pcb"
        board_path.write_text("ORIJINAL", encoding="utf-8")
        settings = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings))

        hafiza = HataHafizasi(dosya_yolu=str(tmp_path / "hafiza.md"))

        rapor_onceki = {"violations": [{}] * 5, "unconnected_items": [{}] * 2}
        rapor_yeni = {"violations": [{}] * 3, "unconnected_items": [{}] * 1}
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([rapor_onceki, rapor_yeni]))

        bulgu = guvenli_yaz_ve_dogrula(
            str(board_path), lambda b: None, zone_refill_yap=False,
            hata_hafizasi=hafiza, degisiklik_aciklamasi="MIPI CAM1 coupled route",
        )

        assert bulgu.durum == BulguDurumu.PASS
        kayitlar = hafiza.kayitlari_oku()
        assert len(kayitlar) == 1
        assert kayitlar[0].sonuc == Sonuc.COZULDU

    def test_denemeler_arasi_ogrenme_uctan_uca(self, tmp_path, monkeypatch):
        """Bir board'da BAŞARISIZ olan bir strateji, AYNI hafıza dosyası
        kullanılarak farklı bir board'da (proje) tekrar denendiğinde
        HAFIZA UYARISI olarak geri gelir — 'dersin projeler arası
        taşınması' gereksinimini uçtan uca kanıtlar."""
        hafiza_yolu = str(tmp_path / "paylasilan_hafiza.md")

        # 1) İlk board: strateji dener, BAŞARISIZ olur.
        board1 = tmp_path / "board1.kicad_pcb"
        board1.write_text("B1", encoding="utf-8")
        settings1 = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings1))
        import guvenli_routing_katmani as grk
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([
            {"violations": [{}] * 2, "unconnected_items": []},
            {"violations": [{}] * 9, "unconnected_items": []},
        ]))
        hafiza1 = HataHafizasi(dosya_yolu=hafiza_yolu)
        b1 = guvenli_yaz_ve_dogrula(
            str(board1), lambda b: None, zone_refill_yap=False,
            hata_hafizasi=hafiza1, degisiklik_aciklamasi="GbE J1 ESD hop via tunelleme",
            proje="iot-kamera",
        )
        assert b1.durum == BulguDurumu.FAIL

        # 2) İkinci board (farklı proje), AYNI strateji + AYNI hafıza dosyası.
        board2 = tmp_path / "board2.kicad_pcb"
        board2.write_text("B2", encoding="utf-8")
        settings2 = SahteDesignSettings(200_000, {})
        _pcbnew_yukle(SahteBoard(settings2))
        monkeypatch.setattr(grk.subprocess, "run", _sahte_subprocess_run_uret([
            {"violations": [{}] * 2, "unconnected_items": []},
            {"violations": [{}] * 2, "unconnected_items": []},
        ]))
        hafiza2 = HataHafizasi(dosya_yolu=hafiza_yolu)
        b2 = guvenli_yaz_ve_dogrula(
            str(board2), lambda b: None, zone_refill_yap=False,
            hata_hafizasi=hafiza2, degisiklik_aciklamasi="GbE J1 ESD hop via tunelleme",
            proje="kafa-bandi-kamera",
        )
        assert "HAFIZA UYARISI" in b2.detay
        assert "iot-kamera" in b2.detay
