"""sistem_orkestratoru.py için test suite.

pcbnew/donanım GEREKTİRMEZ — saf veri/YAML dönüşümü, bu ortamda TAM
olarak gerçek test edilir. `plani_yaml_e_yaz()`/`plani_sozlesmeye_
birlestir()` testleri, üretilen YAML'ın `coklu_kart_sozlesme_kontrolu.py::
VcIdPlani` ile GERÇEKTEN uyumlu olduğunu (uydurma bir iddia değil) ayrıca
kanıtlar.
"""

from __future__ import annotations

import yaml
import pytest

from bulgu_sozlesmesi import BulguDurumu
from sistem_orkestratoru import (
    KameraKartiAtamasi,
    SistemAtamaPlani,
    atama_plani_uret,
    plani_dogrula,
    plani_sozlesmeye_birlestir,
    plani_yaml_e_yaz,
)


# ------------------------------------------------------------------
# atama_plani_uret
# ------------------------------------------------------------------


class TestAtamaPlaniUret:
    def test_vc_id_sirali_0dan_baslar(self):
        plan = atama_plani_uret(6, sensor_sabit_i2c_adresi="0x36")
        assert [a.vc_id for a in plan.atamalar] == [0, 1, 2, 3, 4, 5]

    def test_sensor_adresi_tum_kartlarda_ayni(self):
        """MİMARİ NOKTA: sensörün kendi I2C adresi ASLA değişmemeli —
        adres çevirisi deserializer'ın işi."""
        plan = atama_plani_uret(6, sensor_sabit_i2c_adresi="0x36")
        assert all(a.sensor_sabit_i2c_adresi == "0x36" for a in plan.atamalar)

    def test_deserializer_hedef_adresleri_benzersiz(self):
        plan = atama_plani_uret(6, sensor_sabit_i2c_adresi="0x36", deserializer_taban_hedef_adresi=0x40)
        hedefler = [a.deserializer_hedef_i2c_adresi for a in plan.atamalar]
        assert len(set(hedefler)) == 6
        assert hedefler[0] == hex(0x40)
        assert hedefler[-1] == hex(0x40 + 5)

    def test_kart_no_1den_baslar(self):
        plan = atama_plani_uret(3, "0x36")
        assert [a.kart_no for a in plan.atamalar] == [1, 2, 3]


# ------------------------------------------------------------------
# plani_dogrula
# ------------------------------------------------------------------


class TestPlaniDogrula:
    def test_gecerli_plan_pass(self):
        plan = atama_plani_uret(6, "0x36")
        bulgu = plani_dogrula(plan, deserializer_maks_kanal=8)
        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 6

    def test_vc_id_cakismasi_fail(self):
        plan = atama_plani_uret(3, "0x36")
        plan.atamalar[1].vc_id = plan.atamalar[0].vc_id  # bilerek çakıştır

        bulgu = plani_dogrula(plan, deserializer_maks_kanal=8)

        assert bulgu.durum == BulguDurumu.FAIL
        sebepler = [i["sebep"] for i in bulgu.ihlaller]
        assert "VC ID çakışması" in sebepler

    def test_kanal_limiti_asilirsa_fail(self):
        plan = atama_plani_uret(9, "0x36")
        bulgu = plani_dogrula(plan, deserializer_maks_kanal=8)
        assert bulgu.durum == BulguDurumu.FAIL
        assert any(i["sebep"].startswith("kamera sayısı") for i in bulgu.ihlaller)

    def test_deserializer_hedef_adres_cakismasi_fail(self):
        plan = atama_plani_uret(3, "0x36")
        plan.atamalar[1].deserializer_hedef_i2c_adresi = plan.atamalar[0].deserializer_hedef_i2c_adresi

        bulgu = plani_dogrula(plan, deserializer_maks_kanal=8)

        assert bulgu.durum == BulguDurumu.FAIL
        assert any("deserializer hedef I2C adresi çakışması" == i["sebep"] for i in bulgu.ihlaller)

    def test_bos_plan_kapsam_yok(self):
        bulgu = plani_dogrula(SistemAtamaPlani(kamera_sayisi=0, atamalar=[]), deserializer_maks_kanal=8)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# plani_yaml_e_yaz — arayuz_sozlesmesi.yaml vc_id şemasıyla GERÇEK uyum
# ------------------------------------------------------------------


class TestPlaniYamlEYaz:
    def test_vc_id_bolumu_gercek_semayla_uyumlu(self, tmp_path):
        plan = atama_plani_uret(6, "0x36")
        cikti = tmp_path / "plan.yaml"

        plani_yaml_e_yaz(plan, cikti)

        veri = yaml.safe_load(cikti.read_text(encoding="utf-8"))
        assert veri["vc_id"]["aralik"] == [0, 5]
        assert veri["vc_id"]["atama"] == {f"kart_{i}": i - 1 for i in range(1, 7)}

    def test_i2c_adres_cevirisi_additif_bolumde(self, tmp_path):
        plan = atama_plani_uret(2, "0x36", deserializer_taban_hedef_adresi=0x40)
        cikti = tmp_path / "plan.yaml"
        plani_yaml_e_yaz(plan, cikti)
        veri = yaml.safe_load(cikti.read_text(encoding="utf-8"))
        assert veri["i2c_adres_cevirisi"]["kart_1"]["sensor_sabit_i2c_adresi"] == "0x36"
        assert veri["i2c_adres_cevirisi"]["kart_1"]["deserializer_hedef_i2c_adresi"] == hex(0x40)

    def test_uretilen_vc_id_gercekten_coklu_kart_sozlesme_kontroluyle_calisiyor(self, tmp_path):
        """DOĞRULAMA: bu YAML'ın `vc_id` bölümü, `coklu_kart_sozlesme_
        kontrolu.py::VcIdPlani`'ye DOĞRUDAN yüklenip GERÇEKTEN PASS
        alıyor mu — uydurma bir 'uyumlu' iddiası DEĞİL."""
        from coklu_kart_sozlesme_kontrolu import VcIdPlani, vc_id_cakisma_kontrolu

        plan = atama_plani_uret(6, "0x36")
        cikti = tmp_path / "plan.yaml"
        plani_yaml_e_yaz(plan, cikti)
        veri = yaml.safe_load(cikti.read_text(encoding="utf-8"))

        vc_plani = VcIdPlani(aralik=tuple(veri["vc_id"]["aralik"]), atama=dict(veri["vc_id"]["atama"]))

        class _SahteSozlesme:
            pass

        sahte = _SahteSozlesme()
        sahte.vc_id = vc_plani
        bulgu = vc_id_cakisma_kontrolu(sahte)
        assert bulgu.durum == BulguDurumu.PASS


# ------------------------------------------------------------------
# plani_sozlesmeye_birlestir — mevcut arayuz_sozlesmesi.yaml'ı GÜNCELLER
# ------------------------------------------------------------------


class TestPlaniSozlesmeyeBirlestir:
    def test_dosya_yoksa_hata_uydurma_yok(self, tmp_path):
        plan = atama_plani_uret(2, "0x36")
        with pytest.raises(FileNotFoundError):
            plani_sozlesmeye_birlestir(plan, tmp_path / "yok.yaml")

    def test_diger_bolumler_dokunulmadan_kalir(self, tmp_path):
        mevcut = {
            "versiyon": 1,
            "konnektor": {"pin_sayisi": 4, "kamera_karti_referans": "J1"},
            "guc_butcesi": {"kart_basi_maks_akim_a": 0.4, "kart_sayisi": 6},
            "vc_id": {"aralik": [0, 5], "atama": {"kart_1": 99}},  # eski/yanlış değer
        }
        sozlesme_yolu = tmp_path / "arayuz_sozlesmesi.yaml"
        sozlesme_yolu.write_text(yaml.safe_dump(mevcut), encoding="utf-8")

        plan = atama_plani_uret(6, "0x36")
        plani_sozlesmeye_birlestir(plan, sozlesme_yolu)

        guncel = yaml.safe_load(sozlesme_yolu.read_text(encoding="utf-8"))
        assert guncel["konnektor"] == mevcut["konnektor"]
        assert guncel["guc_butcesi"] == mevcut["guc_butcesi"]
        assert guncel["vc_id"]["atama"]["kart_1"] == 0  # ESKİ 99 DEĞİL, plandan güncellendi
        assert "i2c_adres_cevirisi" in guncel

    def test_gercek_repo_sozlesmesiyle_birlesir(self, tmp_path):
        """`arayuz_sozlesmesi.yaml` (repo kökü) ÜZERİNE değil, bir
        KOPYASINA yazar — gerçek repo dosyası bu testle DEĞİŞTİRİLMEZ."""
        import shutil
        from pathlib import Path

        kaynak = Path(__file__).resolve().parent / "arayuz_sozlesmesi.yaml"
        kopya = tmp_path / "arayuz_sozlesmesi.yaml"
        shutil.copy(kaynak, kopya)

        plan = atama_plani_uret(6, "0x36")
        plani_sozlesmeye_birlestir(plan, kopya)

        guncel = yaml.safe_load(kopya.read_text(encoding="utf-8"))
        assert guncel["vc_id"]["atama"] == {f"kart_{i}": i - 1 for i in range(1, 7)}
        assert guncel["konnektor"]["pin_sayisi"] == 6  # orijinal repo değeri korunmuş
