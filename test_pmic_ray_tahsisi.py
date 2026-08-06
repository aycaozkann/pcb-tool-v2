"""test_pmic_ray_tahsisi.py — pmic_ray_tahsisi.py testleri."""

import pytest

from pmic_ray_tahsisi import (
    PMICCikisi,
    PMICProfili,
    RayIhtiyaci,
    ray_tahsisi_kontrol_et,
)
from pcb_stackup_planner import MekanikVeTermalKisitlar
from bulgu_sozlesmesi import BulguDurumu


def _pmic(*ciktilar: PMICCikisi) -> PMICProfili:
    return PMICProfili(isim="TPS65916", ciktilar=list(ciktilar))


class TestRayTahsisiPass:
    def test_uygun_cikis_varsa_tum_raylar_tahsis_edilir(self):
        pmic = _pmic(
            PMICCikisi("BUCK1", "BUCK", maks_akim_mA=2000, nominal_gerilim_V=3.3),
            PMICCikisi("LDO1", "LDO", maks_akim_mA=300, nominal_gerilim_V=1.8),
        )
        ihtiyaclar = [
            RayIhtiyaci("3V3_MAIN", gerilim_V=3.3, tahmini_akim_mA=500),
            RayIhtiyaci("1V8_IO", gerilim_V=1.8, tahmini_akim_mA=100),
        ]
        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar)

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 2
        assert ihtiyaclar[0].kaynak == "BUCK1"
        assert ihtiyaclar[1].kaynak == "LDO1"

    def test_ayni_cikis_birden_fazla_raya_paylasilabilir_sinir_asilmazsa(self):
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=1000, nominal_gerilim_V=3.3))
        ihtiyaclar = [
            RayIhtiyaci("R1", gerilim_V=3.3, tahmini_akim_mA=400),
            RayIhtiyaci("R2", gerilim_V=3.3, tahmini_akim_mA=400),
        ]
        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar)

        assert bulgu.durum == BulguDurumu.PASS
        assert ihtiyaclar[0].kaynak == ihtiyaclar[1].kaynak == "BUCK1"


class TestRayTahsisiFail:
    def test_pmic_ciktilari_doluyken_yeni_ray_eklenince_fail(self):
        """KASITLI senaryo: PMIC'in TEK çıkışı zaten dolu (900/1000mA),
        yeni bir ray (200mA) eklenince artık sığmıyor -> FAIL."""
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=1000, nominal_gerilim_V=3.3))
        ihtiyaclar = [
            RayIhtiyaci("MEVCUT", gerilim_V=3.3, tahmini_akim_mA=900),
            RayIhtiyaci("YENI_RAY", gerilim_V=3.3, tahmini_akim_mA=200),
        ]
        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar)

        assert bulgu.durum == BulguDurumu.FAIL
        assert len(bulgu.ihlaller) == 1
        ihlal = bulgu.ihlaller[0]
        assert ihlal["tur"] == "ray_tahsis_edilemedi"
        assert ihlal["ray"] == "YENI_RAY"
        assert "ek (supplementary) regülatör" in ihlal["detay"]
        assert ihtiyaclar[1].kaynak == "TAHSIS_EDILMEDI"

    def test_uygun_gerilimde_cikis_hic_yoksa_fail(self):
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=2000, nominal_gerilim_V=5.0))
        ihtiyaclar = [RayIhtiyaci("1V2_CORE", gerilim_V=1.2, tahmini_akim_mA=100)]
        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar)

        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["tur"] == "ray_tahsis_edilemedi"

    def test_bos_ihtiyac_listesi_kapsam_yok(self):
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=1000, nominal_gerilim_V=3.3))
        bulgu = ray_tahsisi_kontrol_et(pmic, [])
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0


class TestTermalEntegrasyon:
    def test_tahsis_edilemeyen_ray_icin_isi_tahmini_raporlanir(self):
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=100, nominal_gerilim_V=3.3))
        ihtiyaclar = [RayIhtiyaci("BUYUK_RAY", gerilim_V=3.3, tahmini_akim_mA=1000)]
        termal = MekanikVeTermalKisitlar(maks_isi_yayilimi_W=0.5)

        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar, termal_kisitlar=termal)

        ihlal = bulgu.ihlaller[0]
        assert ihlal["ek_regulator_tahmini_isi_W"] > 0
        # 3.3V * 1A = 3.3W çıkış, %85 verimde kayıp = 3.3*(1/0.85-1) ~ 0.582W
        assert ihlal["ek_regulator_tahmini_isi_W"] == pytest.approx(0.582, abs=0.01)
        assert "termal bütçe" in bulgu.detay.lower() or "AŞIYOR" in bulgu.detay

    def test_termal_kisit_verilmezse_hata_vermez_sadece_isi_raporlanir(self):
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=100, nominal_gerilim_V=3.3))
        ihtiyaclar = [RayIhtiyaci("BUYUK_RAY", gerilim_V=3.3, tahmini_akim_mA=1000)]

        bulgu = ray_tahsisi_kontrol_et(pmic, ihtiyaclar)  # termal_kisitlar=None

        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["ek_regulator_tahmini_isi_W"] > 0


class TestAsiriYuklemeIkinciGecis:
    def test_disaridan_doldurulmus_kaynak_asiri_yuklemeyi_yakalar(self):
        """`kaynak` alanı DIŞARIDAN önceden doldurulmuş girdiler için de
        aşırı yükleme ikinci-geçiş kontrolü çalışmalı."""
        pmic = _pmic(PMICCikisi("BUCK1", "BUCK", maks_akim_mA=500, nominal_gerilim_V=3.3))
        r1 = RayIhtiyaci("R1", gerilim_V=3.3, tahmini_akim_mA=300, kaynak="BUCK1")
        r2 = RayIhtiyaci("R2", gerilim_V=3.3, tahmini_akim_mA=300)  # greedy ile BUCK1'e sığmaz
        bulgu = ray_tahsisi_kontrol_et(pmic, [r1, r2])

        # r1 zaten dışarıdan BUCK1'e atanmış olsa da, greedy algoritma r1'i
        # KENDİ akışında yeniden değerlendirir (kalan_akim sıfırdan
        # başlar) — bu yüzden r2 sığmayabilir, tahsis edilemez sayılır.
        turler = {i["tur"] for i in bulgu.ihlaller}
        assert "ray_tahsis_edilemedi" in turler or "cikis_asiri_yuklendi" in turler
