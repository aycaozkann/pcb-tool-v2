from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from arac_yollari import (
    KICAD_CLI_ENV,
    AracDurumu,
    _komut_kontrol,
    _python_import_kontrol,
    kicad_cli_yolunu_bul,
    tum_araclari_kontrol_et,
)


def test_acikca_verilen_yol_pathten_once_kullanilir(tmp_path):
    cli = tmp_path / "kicad-cli.exe"
    cli.touch()

    with patch("arac_yollari.shutil.which", return_value="PATH-CLI"):
        assert kicad_cli_yolunu_bul(str(cli)) == str(cli)


def test_ortam_degiskeni_pathten_once_kullanilir(tmp_path, monkeypatch):
    cli = tmp_path / "kicad-cli.exe"
    cli.touch()
    monkeypatch.setenv(KICAD_CLI_ENV, str(cli))

    with patch("arac_yollari.shutil.which", return_value="PATH-CLI"):
        assert kicad_cli_yolunu_bul() == str(cli)


def test_hicbir_aday_yokken_acik_hata_verir(monkeypatch):
    monkeypatch.delenv(KICAD_CLI_ENV, raising=False)
    with patch("arac_yollari.shutil.which", return_value=None), patch(
        "arac_yollari._windows_kicad_adaylari", return_value=[]
    ):
        with pytest.raises(FileNotFoundError, match="KICAD_CLI"):
            kicad_cli_yolunu_bul()


# ------------------------------------------------------------------
# _komut_kontrol / _python_import_kontrol — tek araç kontrolü
# ------------------------------------------------------------------

def test_komut_kontrol_arac_yoksa_hata_firlatmaz_fail_doner():
    """Araç PATH'te yoksa hata FIRLATILMAZ — AracDurumu(gecti_mi=False) döner,
    böylece tek eksik araç tüm kontrolü kesmez."""
    with patch("arac_yollari.shutil.which", return_value=None):
        durum = _komut_kontrol("Sahte Araç", ["olmayan-arac", "--version"], "madde X")
    assert durum.gecti_mi is False
    assert "bulunamadı" in durum.detay
    assert durum.kurulum_maddesi == "madde X"


def test_komut_kontrol_basarili_calisirsa_pass():
    with patch("arac_yollari.shutil.which", return_value="/usr/bin/git"), \
         patch("arac_yollari.subprocess.run") as sahte_run:
        sahte_run.return_value = subprocess.CompletedProcess(
            ["git", "--version"], 0, stdout="git version 2.54.0\n", stderr=""
        )
        durum = _komut_kontrol("git", ["git", "--version"], "madde 9")
    assert durum.gecti_mi is True
    assert "git version" in durum.detay


def test_komut_kontrol_timeout_fail_doner_cokme():
    with patch("arac_yollari.shutil.which", return_value="/usr/bin/x"), \
         patch("arac_yollari.subprocess.run", side_effect=subprocess.TimeoutExpired("x", 5)):
        durum = _komut_kontrol("X", ["x", "--version"], "madde X")
    assert durum.gecti_mi is False
    assert "çalıştırılamadı" in durum.detay


def test_python_import_kontrol_gercek_modulle_pass():
    """`os` her Python kurulumunda mevcuttur — gerçek subprocess ile test."""
    durum = _python_import_kontrol("os modülü", "os", "madde X")
    assert durum.gecti_mi is True


def test_python_import_kontrol_olmayan_modulle_fail():
    durum = _python_import_kontrol("Sahte", "kesinlikle_var_olmayan_modul_xyz", "madde X")
    assert durum.gecti_mi is False
    assert "ModuleNotFoundError" in durum.detay or "No module named" in durum.detay


def test_arac_durumu_fail_satirinda_kurulum_maddesi_gorunur():
    durum = AracDurumu("X", False, "bulunamadı", "KURULUM.md madde 7")
    assert "KURULUM.md madde 7" in durum.satir()
    assert "FAIL" in durum.satir()


def test_arac_durumu_pass_satirinda_kurulum_maddesi_gorunmez():
    """PASS satırı gereksiz yere kurulum talimatı göstermemeli."""
    durum = AracDurumu("X", True, "1.0", "KURULUM.md madde 7")
    satir = durum.satir()
    assert "PASS" in satir
    assert "KURULUM.md madde 7" not in satir


# ------------------------------------------------------------------
# tum_araclari_kontrol_et — tek eksik araç diğerlerini engellemiyor
# ------------------------------------------------------------------

def test_tum_araclari_kontrol_et_tek_eksik_arac_digerlerini_engellemez():
    """Bash zincirinin (`A && B && C`) TERSİ davranış: ilk araç eksik olsa
    bile SONRAKİ tüm araçlar yine de kontrol edilir."""
    with patch("arac_yollari.kicad_cli_surumu_dogrula", side_effect=FileNotFoundError("yok")):
        sonuclar = tum_araclari_kontrol_et()
    isimler = {d.isim for d in sonuclar}
    assert "KiCad CLI" in isimler
    assert "git" in isimler
    assert "uv" in isimler
    # KiCad CLI eksik olsa bile git/uv gibi diğer araçlar da listede VE
    # gerçekten denenmiş (bu makinede muhtemelen PASS).
    assert len(sonuclar) >= 8


def test_tum_araclari_kontrol_et_gercek_makinede_beklenen_araclar_pass():
    """Bu makinede git, uv ve pytest kurulu — gerçek koşumla doğrulanır
    (mock değil, bilfiil bu geliştirme ortamında çalıştı)."""
    sonuclar = tum_araclari_kontrol_et()
    durum_map = {d.isim: d for d in sonuclar}
    assert durum_map["git"].gecti_mi is True
    assert durum_map["uv"].gecti_mi is True


def test_tum_araclari_kontrol_et_kicad_cli_parametresi_iletilir():
    with patch("arac_yollari.kicad_cli_surumu_dogrula") as sahte:
        sahte.return_value = ("/yol/kicad-cli", "10.0.4")
        tum_araclari_kontrol_et(kicad_cli="/ozel/yol")
    sahte.assert_called_once_with("/ozel/yol")
