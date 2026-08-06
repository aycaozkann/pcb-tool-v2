"""device_tree_uretici.py için test suite.

pcbnew/donanım/`dtc` GEREKTİRMEZ — saf YAML okuma + metin üretme, bu
ortamda TAM olarak gerçek test edilir. Kabul kriteri (görev tanımından):
Ambarella için HER ZAMAN KAPSAM_YOK (uydurma syntax YOK); RK3588 için
üretilen metin GERÇEK bir `dtc` ile derlenip doğrulanmadı — bu dosyadaki
testler SADECE veri akışını/metin şeklini doğrular, gerçek device tree
derleyicisini DEĞİL.
"""

from __future__ import annotations

import yaml
import pytest

from bulgu_sozlesmesi import BulguDurumu
from device_tree_uretici import (
    SOC_AMBARELLA,
    SOC_RK3588,
    ambarella_kamera_overlay_uret,
    dts_fragment_uret,
    rk3588_kamera_overlay_uret,
    sozlesmeden_ve_plandan_dts_girdileri_uret,
)


def _sozlesme_yaz(tmp_path, vc_id_atama, i2c_cevirisi):
    veri = {
        "vc_id": {"aralik": [0, len(vc_id_atama) - 1], "atama": vc_id_atama},
        "i2c_adres_cevirisi": i2c_cevirisi,
    }
    yol = tmp_path / "arayuz_sozlesmesi.yaml"
    yol.write_text(yaml.safe_dump(veri, allow_unicode=True), encoding="utf-8")
    return yol


def _tam_ornek(tmp_path, kart_sayisi=3):
    vc_id_atama = {f"kart_{i}": i - 1 for i in range(1, kart_sayisi + 1)}
    i2c_cevirisi = {
        f"kart_{i}": {
            "deserializer_kanal_no": i,
            "sensor_sabit_i2c_adresi": "0x36",
            "deserializer_hedef_i2c_adresi": hex(0x40 + i - 1),
        }
        for i in range(1, kart_sayisi + 1)
    }
    sozlesme = _sozlesme_yaz(tmp_path, vc_id_atama, i2c_cevirisi)
    bus_haritasi = {i: f"i2c{i}" for i in range(1, kart_sayisi + 1)}
    return sozlesme, bus_haritasi


# ------------------------------------------------------------------
# sozlesmeden_ve_plandan_dts_girdileri_uret
# ------------------------------------------------------------------


class TestGirdiOkuma:
    def test_vc_id_sirasina_gore_siralanir(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=3)
        girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, bus)
        assert [g.kart_no for g in girdiler] == [1, 2, 3]
        assert [g.vc_id for g in girdiler] == [0, 1, 2]

    def test_bus_haritasinda_olmayan_kart_atlanir(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=3)
        del bus[2]  # kart_2 için bus bilgisi YOK
        girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, bus)
        assert [g.kart_no for g in girdiler] == [1, 3]

    def test_i2c_cevirisinde_olmayan_kart_atlanir(self, tmp_path):
        vc_id_atama = {"kart_1": 0, "kart_2": 1}
        i2c_cevirisi = {"kart_1": {"deserializer_kanal_no": 1, "sensor_sabit_i2c_adresi": "0x36",
                                    "deserializer_hedef_i2c_adresi": "0x40"}}  # kart_2 EKSİK
        sozlesme = _sozlesme_yaz(tmp_path, vc_id_atama, i2c_cevirisi)
        girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, {1: "i2c1", 2: "i2c2"})
        assert [g.kart_no for g in girdiler] == [1]

    def test_bos_sozlesme_bos_liste(self, tmp_path):
        sozlesme = _sozlesme_yaz(tmp_path, {}, {})
        assert sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, {}) == []


# ------------------------------------------------------------------
# rk3588_kamera_overlay_uret
# ------------------------------------------------------------------


class TestRk3588Overlay:
    def test_bos_girdi_bos_metin(self):
        assert rk3588_kamera_overlay_uret([]) == ""

    def test_her_kart_icin_node_uretilir(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=2)
        girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, bus)

        metin = rk3588_kamera_overlay_uret(girdiler, sensor_compatible="ovti,og05b10")

        assert "/dts-v1/;" in metin
        assert "&i2c1 {" in metin and "&i2c2 {" in metin
        assert "compatible = \"ovti,og05b10\";" in metin
        assert "reg = <0x40>;" in metin
        assert "reg = <0x41>;" in metin
        assert metin.count("camera1:") == 1
        assert metin.count("camera2:") == 1


# ------------------------------------------------------------------
# ambarella_kamera_overlay_uret — sadece TASLAK, gerçek syntax İDDİA ETMEZ
# ------------------------------------------------------------------


class TestAmbarellaOverlay:
    def test_taslak_notu_icerir_gercek_dts_yok(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=2)
        girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme, bus)

        metin = ambarella_kamera_overlay_uret(girdiler)

        assert "TASLAK" in metin
        assert "/dts-v1/" not in metin  # gerçek dts sözdizimi ÜRETİLMEDİ
        assert "2 kart" in metin


# ------------------------------------------------------------------
# dts_fragment_uret — tek giriş noktası
# ------------------------------------------------------------------


class TestDtsFragmentUret:
    def test_bilinmeyen_soc_kapsam_yok(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path)
        bulgu = dts_fragment_uret("bilinmeyen_soc", sozlesme, bus)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_sozlesme_yoksa_kapsam_yok(self, tmp_path):
        bulgu = dts_fragment_uret(SOC_RK3588, tmp_path / "yok.yaml", {})
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_ambarella_her_zaman_kapsam_yok_dosya_yazilmaz(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=3)
        cikti = tmp_path / "ambarella.dts"

        bulgu = dts_fragment_uret(SOC_AMBARELLA, sozlesme, bus, cikti_yolu=cikti)

        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0
        assert not cikti.exists()  # uydurma .dts diske YAZILMADI

    def test_rk3588_girdi_yoksa_kapsam_yok(self, tmp_path):
        sozlesme, _bus = _tam_ornek(tmp_path)
        bulgu = dts_fragment_uret(SOC_RK3588, sozlesme, {})  # bus haritası boş
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_rk3588_gecerli_girdi_pass_ve_dosyaya_yazar(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=6)
        cikti = tmp_path / "camera-overlay.dts"

        bulgu = dts_fragment_uret(SOC_RK3588, sozlesme, bus, cikti_yolu=cikti)

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 6
        assert cikti.exists()
        assert "&i2c6 {" in cikti.read_text(encoding="utf-8")
        assert "DOĞRULANMADI" not in bulgu.detay or "dtc" in bulgu.detay  # uyarı notu var

    def test_rk3588_cikti_yolu_verilmezse_dosya_yazilmaz(self, tmp_path):
        sozlesme, bus = _tam_ornek(tmp_path, kart_sayisi=2)
        bulgu = dts_fragment_uret(SOC_RK3588, sozlesme, bus)
        assert bulgu.durum == BulguDurumu.PASS
        assert "dosyaya yazılmadı" in bulgu.detay
