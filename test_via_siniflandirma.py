"""test_via_siniflandirma.py — HDI via sınıflandırma modülü testleri."""

import pytest

from via_siniflandirma import (
    MAKS_ASPECT_ORANI,
    Via,
    ViaTipiDetay,
    select_via_type_for_bga,
)
from pcb_stackup_planner import KATMAN_KALINLIK_VARSAYIMI_MM, via_tipi_aspect_ratio_kontrolu
from bulgu_sozlesmesi import BulguDurumu


# ------------------------------------------------------------------
# 1. Via.aspect_oran — KATMAN_KALINLIK_VARSAYIMI_MM ile TUTARLI mı
# ------------------------------------------------------------------

class TestViaAspectOran:
    def test_boydan_boya_iki_katman_dogru_hesap(self):
        via = Via("NET1", 1, 2, ViaTipiDetay.BOYDAN_BOYA, matkap_capi_mm=0.3, pad_capi_mm=0.5)
        beklenen = (1 * KATMAN_KALINLIK_VARSAYIMI_MM) / 0.3
        assert via.aspect_oran == pytest.approx(beklenen)

    def test_matkap_capi_sifirsa_sonsuz_doner_cokme_yok(self):
        via = Via("NET1", 1, 8, ViaTipiDetay.MIKROVIA, matkap_capi_mm=0.0, pad_capi_mm=0.2)
        assert via.aspect_oran == float("inf")

    def test_katman_araligi_mutlak_deger(self):
        via_ileri = Via("N", 1, 4, ViaTipiDetay.KOR, 0.15, 0.35)
        via_geri = Via("N", 4, 1, ViaTipiDetay.KOR, 0.15, 0.35)
        assert via_ileri.katman_araligi == via_geri.katman_araligi == 3

    def test_maks_izinli_aspect_oran_tabloyla_esler(self):
        for tip, sinir in MAKS_ASPECT_ORANI.items():
            via = Via("N", 1, 2, tip, 0.2, 0.4)
            assert via.maks_izinli_aspect_oran == sinir


# ------------------------------------------------------------------
# 2. via_tipi_aspect_ratio_kontrolu — her via tipi için sınır doğru mu
# ------------------------------------------------------------------

class TestViaTipiAspectRatioKontrolu:
    def test_boydan_boya_8_1_altinda_pass(self):
        # derinlik = 7*0.15 = 1.05mm, matkap 0.3mm -> oran 3.5 (<8)
        via = Via("N1", 1, 8, ViaTipiDetay.BOYDAN_BOYA, matkap_capi_mm=0.3, pad_capi_mm=0.5)
        bulgu = via_tipi_aspect_ratio_kontrolu(via)
        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 1

    def test_boydan_boya_8_1_ustunde_fail(self):
        # derinlik = 40*0.15 = 6.0mm, matkap 0.3mm -> oran 20 (>8)
        via = Via("N1", 1, 41, ViaTipiDetay.BOYDAN_BOYA, matkap_capi_mm=0.3, pad_capi_mm=0.5)
        bulgu = via_tipi_aspect_ratio_kontrolu(via)
        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["via_tipi"] == "BOYDAN_BOYA"
        assert bulgu.ihlaller[0]["izinli_sinir"] == 8.0

    def test_kor_1_1_ustunde_fail(self):
        # derinlik = 2*0.15 = 0.30mm, matkap 0.15mm -> oran 2.0 (>1)
        via = Via("N2", 1, 3, ViaTipiDetay.KOR, matkap_capi_mm=0.15, pad_capi_mm=0.35)
        bulgu = via_tipi_aspect_ratio_kontrolu(via)
        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["izinli_sinir"] == 1.0

    def test_mikrovia_1_1_altinda_pass(self):
        # derinlik = 1*0.15 = 0.15mm, matkap 0.1mm -> oran 1.5... adjust to pass
        via = Via("N3", 1, 2, ViaTipiDetay.MIKROVIA, matkap_capi_mm=0.2, pad_capi_mm=0.4)
        bulgu = via_tipi_aspect_ratio_kontrolu(via)
        assert bulgu.durum == BulguDurumu.PASS

    def test_gomulu_sinirda_fail_detayinda_dogru_bilgiler(self):
        via = Via("N4", 3, 6, ViaTipiDetay.GOMULU, matkap_capi_mm=0.15, pad_capi_mm=0.35)
        bulgu = via_tipi_aspect_ratio_kontrolu(via)
        assert bulgu.durum == BulguDurumu.FAIL
        ihlal = bulgu.ihlaller[0]
        assert ihlal["via_net"] == "N4"
        assert ihlal["baslangic_katman"] == 3
        assert ihlal["bitis_katman"] == 6


# ------------------------------------------------------------------
# 3. select_via_type_for_bga — en az 3 farklı pitch senaryosu
# ------------------------------------------------------------------

class TestSelectViaTypeForBga:
    def test_genis_pitch_boydan_boya_secer(self):
        via = select_via_type_for_bga(pad_pitch_mm=1.0, routing_layer_gap=4)
        assert via.tipi == ViaTipiDetay.BOYDAN_BOYA
        assert via.pad_icinde_mi is False
        assert via.dolgu_ve_kapak_var_mi is False

    def test_orta_pitch_yuzeysel_gecis_kor_secer(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.65, routing_layer_gap=2)
        assert via.tipi == ViaTipiDetay.KOR
        assert via.pad_icinde_mi is False

    def test_orta_pitch_derin_gecis_mikrovia_stack_uyarisina_duser(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.65, routing_layer_gap=4)
        assert via.tipi == ViaTipiDetay.MIKROVIA
        assert via.pad_icinde_mi is True
        assert via.dolgu_ve_kapak_var_mi is True

    def test_ince_pitch_mikrovia_ve_via_in_pad_secer(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.4, routing_layer_gap=2)
        assert via.tipi == ViaTipiDetay.MIKROVIA
        assert via.pad_icinde_mi is True
        assert via.dolgu_ve_kapak_var_mi is True

    def test_via_in_pad_secilirse_ipc4761_type_vii_otomatik_isaretli(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.3, routing_layer_gap=1)
        assert via.pad_icinde_mi is True
        assert via.dolgu_ve_kapak_var_mi is True

    def test_gecersiz_pitch_hata_firlatir(self):
        with pytest.raises(ValueError):
            select_via_type_for_bga(pad_pitch_mm=0.0, routing_layer_gap=2)

    def test_gecersiz_katman_araligi_hata_firlatir(self):
        with pytest.raises(ValueError):
            select_via_type_for_bga(pad_pitch_mm=0.5, routing_layer_gap=0)

    def test_sinir_deger_0_8mm_boydan_boya(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.8, routing_layer_gap=1)
        assert via.tipi == ViaTipiDetay.BOYDAN_BOYA

    def test_sinir_deger_0_5mm_kor(self):
        via = select_via_type_for_bga(pad_pitch_mm=0.5, routing_layer_gap=1)
        assert via.tipi == ViaTipiDetay.KOR
