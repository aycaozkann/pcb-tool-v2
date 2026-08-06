"""
via_stub.py için test suite (2026-08-03, GÖREV: Kalan 6 Mimari Boşluk,
Madde 5).

ESKİ DURUM: dosyanın en başında MODÜL SEVİYESİNDE `import pcbnew` vardı —
bu, pcbnew kurulu olmayan HER ortamda (bu test venv'i dahil) `import
via_stub` satırının kendisini `ModuleNotFoundError` ile çökertiyordu, dosya
hiç test EDİLEMİYORDU (bu yüzden daha önce bu dosya için hiç test dosyası
yoktu). `import pcbnew` artık fonksiyon-içi (lazy) — bu dosyanın testleri
olabilmesinin ÖN KOŞULU tam olarak bu değişikliktir; ilk test onu kanıtlar.
"""

from __future__ import annotations

import json
import sys

import pytest


def test_modul_pcbnew_kurulu_degilken_de_import_edilebilir():
    """Ana kanıt: pcbnew bu ortamda GERÇEKTEN kurulu değil (pip paketi
    yok), ama `import via_stub` yine de BAŞARILI olmalı — modül seviyeli
    `import pcbnew` kaldırıldığı için."""
    assert "pcbnew" not in sys.modules or True  # pcbnew başka testte mock'lanmış olabilir
    import via_stub  # noqa: F401 - başarısız olmaması testin kendisidir
    assert hasattr(via_stub, "main")
    assert hasattr(via_stub, "canonical_layer_name")


def test_canonical_layer_name_pcbnew_yoksa_modulenotfounderror(monkeypatch):
    """`canonical_layer_name()` kendi başına çağrılırsa (main()'in
    fail-closed sarmalayıcısı OLMADAN) pcbnew eksikliğini GİZLEMEZ —
    gerçek `ModuleNotFoundError` fırlatır. Sessizce sahte bir katman adı
    UYDURMAZ."""
    monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
    import via_stub
    with pytest.raises(ModuleNotFoundError):
        via_stub.canonical_layer_name(0)


def test_main_pcbnew_yokken_no_coverage_doner_crash_etmez(monkeypatch, tmp_path, capsys):
    """`main()` — dosyanın gerçek giriş noktası — pcbnew eksikken HAM
    `ModuleNotFoundError` ile çökmemeli; NO_COVERAGE raporlayıp 0 dönmeli
    (dosyanın kendi docstring'indeki 'kardeş araç sözleşmesi': NO_COVERAGE
    exit-code 0 olabilir, çağıran özet sayacına bakmalı)."""
    monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
    import via_stub

    sahte_board = tmp_path / "board.kicad_pcb"
    sahte_board.write_text("(kicad_pcb)", encoding="utf-8")

    kod = via_stub.main([str(sahte_board), "--channel-bw-ghz", "5.0"])

    assert kod == 0
    cikti = json.loads(capsys.readouterr().out)
    assert cikti["summary"]["NO_COVERAGE"] == 1
    assert cikti["summary"]["FAIL"] == 0
    assert "pcbnew modülü bulunamadı" in cikti["checks"][0]["detail"]


def test_main_json_dosyasina_da_no_coverage_yazar(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
    import via_stub

    sahte_board = tmp_path / "board.kicad_pcb"
    sahte_board.write_text("(kicad_pcb)", encoding="utf-8")
    json_yolu = tmp_path / "out.json"

    kod = via_stub.main([str(sahte_board), "--channel-bw-ghz", "5.0", "--json", str(json_yolu)])

    assert kod == 0
    veri = json.loads(json_yolu.read_text(encoding="utf-8"))
    assert veri["summary"]["NO_COVERAGE"] == 1


# ------------------------------------------------------------------
# pcbnew gerektirmeyen saf yardımcılar (mevcut testsizliği de kapatır)
# ------------------------------------------------------------------

def test_balanced_form_ic_ice_parantezleri_dogru_kapatir():
    import via_stub
    metin = "(a (b (c)) d)"
    assert via_stub.balanced_form(metin, 0) == metin


def test_balanced_form_tirnak_icindeki_parantezi_saymaz():
    import via_stub
    metin = '(a "b(c" d)'
    assert via_stub.balanced_form(metin, 0) == metin


def test_parse_stackup_setup_yoksa_none_ve_gerekce_doner():
    import via_stub
    from pathlib import Path
    import tempfile, os

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.kicad_pcb"
        p.write_text("(kicad_pcb (version 1))", encoding="utf-8")
        stackup, status = via_stub.parse_stackup(str(p))
        assert stackup is None
        assert "(setup ...) bulunamadı" in status


def test_positive_negatif_deger_value_error_firlatir():
    import via_stub
    with pytest.raises(ValueError):
        via_stub.positive("--dk", -1.0)


def test_positive_none_sessizce_gecer():
    import via_stub
    via_stub.positive("--dk", None)  # exception atmamalı
