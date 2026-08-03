"""uretim_ciktilari_cli.py için test suite — gerçek kicad-cli/kibot/pcbnew
gerektirmeden, monkeypatch ile kapı MANTIĞINI izole test eder."""

import pytest

import uretim_ciktilari_cli as cli


def test_dogrulama_kapisi_hepsi_temizse_true(monkeypatch):
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"violations": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu
    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi",
                        lambda board_path: (True, {}), raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is True
    assert sorunlar == []


def test_dogrulama_kapisi_drc_kirliyse_false(monkeypatch):
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": [{"severity": "error"}]})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: False)
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"violations": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is False
    assert any("DRC" in s for s in sorunlar)


def test_main_force_bayragi_olmadan_kirli_kapida_durur(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "dogrulama_kapisini_calistir",
        lambda board, sch, **kw: (False, ["DRC temiz değil — üretim çıktısı ÜRETİLMEYECEK."]),
    )
    kod = cli.main(["b.kicad_pcb", "s.kicad_sch"])
    assert kod == 1
    cikti = capsys.readouterr()
    assert "Durduruldu" in cikti.err


def test_main_temizse_kibot_calistirir(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "dogrulama_kapisini_calistir", lambda board, sch, **kw: (True, []))

    cagrildi = {}

    class SahteSonuc:
        basarili = True
        stdout = "ok"
        stderr = ""
        cikti_dizini = str(tmp_path / "uretim")

    def sahte_kibot_calistir(board, config, cikti_dizini):
        cagrildi["cagrildi"] = True
        return SahteSonuc()

    monkeypatch.setattr(cli, "kibot_calistir", sahte_kibot_calistir)
    monkeypatch.setattr(cli, "kibot_config_yaz", lambda hedef: hedef)

    kibot_yaml = tmp_path / "kibot.yaml"
    kibot_yaml.write_text("mevcut")  # config zaten var -> yeniden yazılmamalı

    kod = cli.main(["b.kicad_pcb", "s.kicad_sch", "--kibot-config", str(kibot_yaml),
                    "--cikti-dizini", str(tmp_path / "uretim")])
    assert kod == 0
    assert cagrildi.get("cagrildi") is True


def test_main_force_bayragiyla_dogrulamayi_atlar(monkeypatch, tmp_path, capsys):
    cagrildi = {"dogrulama": False}
    monkeypatch.setattr(cli, "dogrulama_kapisini_calistir",
                        lambda *a, **kw: cagrildi.__setitem__("dogrulama", True) or (True, []))

    class SahteSonuc:
        basarili = True
        stdout = "ok"
        stderr = ""
        cikti_dizini = str(tmp_path / "uretim")

    monkeypatch.setattr(cli, "kibot_calistir", lambda *a, **kw: SahteSonuc())
    monkeypatch.setattr(cli, "kibot_config_yaz", lambda hedef: hedef)

    kibot_yaml = tmp_path / "kibot.yaml"
    kibot_yaml.write_text("mevcut")

    kod = cli.main(["b.kicad_pcb", "s.kicad_sch", "--kibot-config", str(kibot_yaml),
                    "--cikti-dizini", str(tmp_path / "uretim"), "--force-atla-dogrulama"])
    assert kod == 0
    assert cagrildi["dogrulama"] is False  # doğrulama fonksiyonu HİÇ çağrılmadı
    cikti = capsys.readouterr()
    assert "BİLEREK atlandı" in cikti.err


# ------------------------------------------------------------------
# REGRESYON — dış incelemede bulunan iki P0:
#   1. pcbnew yokken kapı sessizce PASS dönüyordu (UYARI ön ekiyle
#      filtreleniyordu).
#   2. Bilinmeyen DRC/ERC şeması bu release CLI'sinde HİÇ kontrol
#      edilmiyordu (sema_taninmadi_mi() var ama çağrılmıyordu).
# Bu testler `dogrulama_kapisini_calistir()`'in kendisini (main() değil)
# hedef alır — gerçek karar mantığı burada.
# ------------------------------------------------------------------

def test_pcbnew_yoksa_varsayilan_olarak_fail(monkeypatch):
    """pcbnew kurulu değilse VARSAYILAN davranış artık FAIL'dır — önceki
    sürüm bunu sessizce PASS sayıyordu (UYARI ön ekiyle dışlanan mesaj)."""
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"violations": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu

    def patlayan_gate(board_path):
        raise ModuleNotFoundError("pcbnew yok")

    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi", patlayan_gate, raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is False
    assert any("pcbnew" in s and "gercek-board-kontrolu-atla" in s for s in sorunlar)


def test_pcbnew_yoksa_bilincli_atlamada_needs_human_mesaji_var(monkeypatch):
    """`gercek_board_kontrolu_atla=True` ile üretim ENGELLENMEZ ama sonuç
    açıkça NEEDS_HUMAN olarak işaretlenir — sessiz bir PASS asla üretilmez."""
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"violations": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu

    def patlayan_gate(board_path):
        raise ModuleNotFoundError("pcbnew yok")

    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi", patlayan_gate, raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir(
        "b.kicad_pcb", "s.kicad_sch", gercek_board_kontrolu_atla=True
    )
    assert temiz_mi is True  # bilinçli izin -> üretim engellenmez
    assert any("NEEDS_HUMAN" in s for s in sorunlar)  # ama sessiz PASS da DEĞİL


def test_drc_semasi_taninmiyorsa_fail_closed(monkeypatch):
    """Beklenmeyen bir DRC rapor yapısı (ne 'violations' ne 'sheets')
    üretim çıktısını DURDURMALI — önceki sürüm bunu hiç kontrol etmiyordu."""
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"bilinmeyen_alan": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)  # gerçek fonksiyon da True dönerdi
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"violations": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu
    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi",
                        lambda board_path: (True, {}), raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is False
    assert any("TANINMADI" in s and "DRC" in s for s in sorunlar)


def test_erc_semasi_taninmiyorsa_fail_closed(monkeypatch):
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)
    monkeypatch.setattr(cli, "erc_calistir", lambda sch_path: {"bilinmeyen_alan": []})
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu
    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi",
                        lambda board_path: (True, {}), raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is False
    assert any("TANINMADI" in s and "ERC" in s for s in sorunlar)


def test_gercek_erc_semasiyla_kapi_dogru_calisir(monkeypatch):
    """`sema_taninmadi_mi`'nin gerçek `kicad_koprusu` fonksiyonu (mock
    DEĞİL) ile, gerçek ERC şemasında (sheets[].violations) yanlış pozitif
    üretmediğini doğrular."""
    monkeypatch.setattr(cli, "drc_calistir", lambda board_path: {"violations": []})
    monkeypatch.setattr(cli, "drc_temiz_mi", lambda rapor: True)
    monkeypatch.setattr(
        cli, "erc_calistir",
        lambda sch_path: {"sheets": [{"path": "/", "violations": [{"severity": "warning", "description": "x"}]}]},
    )
    monkeypatch.setattr(cli, "erc_temiz_mi", lambda rapor: True)

    import kicad_koprusu
    monkeypatch.setattr(kicad_koprusu, "gercek_board_dogrulama_kapisi",
                        lambda board_path: (True, {}), raising=False)

    temiz_mi, sorunlar = cli.dogrulama_kapisini_calistir("b.kicad_pcb", "s.kicad_sch")
    assert temiz_mi is True
    assert sorunlar == []


def test_main_gercek_board_kontrolu_atla_bayragi_iletilir(monkeypatch, tmp_path):
    """CLI bayrağı, `dogrulama_kapisini_calistir()`'e doğru kwarg olarak
    ulaşıyor mu — uçtan uca argparse -> fonksiyon çağrısı bağlantısı."""
    yakalanan = {}

    def sahte_dogrulama(board, sch, **kw):
        yakalanan.update(kw)
        return True, []

    monkeypatch.setattr(cli, "dogrulama_kapisini_calistir", sahte_dogrulama)

    class SahteSonuc:
        basarili = True
        stdout = "ok"
        stderr = ""
        cikti_dizini = str(tmp_path / "uretim")

    monkeypatch.setattr(cli, "kibot_calistir", lambda *a, **kw: SahteSonuc())
    monkeypatch.setattr(cli, "kibot_config_yaz", lambda hedef: hedef)
    kibot_yaml = tmp_path / "kibot.yaml"
    kibot_yaml.write_text("mevcut")

    cli.main(["b.kicad_pcb", "s.kicad_sch", "--kibot-config", str(kibot_yaml),
              "--cikti-dizini", str(tmp_path / "uretim"), "--gercek-board-kontrolu-atla"])
    assert yakalanan.get("gercek_board_kontrolu_atla") is True
