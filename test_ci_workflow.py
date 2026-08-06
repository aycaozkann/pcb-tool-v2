"""
.github/workflows/ci.yml için test suite (2026-08-03, GÖREV: Kalan 6
Mimari Boşluk, Madde 6).

Tam bir YAML şema doğrulaması İÇİN `pyyaml`'ı yeni bir proje bağımlılığı
olarak eklemek bu görevin kapsamı dışında kalırdı (scope creep) — bu
yüzden testler dosyanın VAR OLDUĞUNU, temel YAML girinti/anahtar
yapısının bozulmadığını ve üç kritik adımın (bağımlılık kurulumu, pytest,
orkestrasyon duman testi) GERÇEKTEN dosyada bulunduğunu basit metin
tabanlı kontrollerle doğrular.
"""

from __future__ import annotations

from pathlib import Path

_CI_YOLU = Path(__file__).resolve().parent / ".github" / "workflows" / "ci.yml"


def test_ci_dosyasi_var():
    assert _CI_YOLU.is_file()


def test_ci_tetikleyicileri_push_ve_pr_icerir():
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "push:" in metin
    assert "pull_request:" in metin


def test_ci_uv_ile_bagimlilik_kurar():
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "astral-sh/setup-uv" in metin
    assert "uv sync" in metin


def test_ci_pytest_calistirir():
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "pytest -q" in metin


def test_ci_statik_kontrol_icerir():
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "py_compile" in metin


def test_ci_orkestrasyon_duman_testi_icerir():
    """`main.py run`'ın CI'de (KiCad kurulu olmadan) çağrıldığını ve
    kontrollü/fail-closed davranış beklendiğini doğrular."""
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "main.py run" in metin
    assert "Traceback" in metin  # ham traceback'e KARŞI kontrol var mı


def test_ci_gecerli_yaml_girintisi_boyle_bir_hata_uretmez():
    """Tam YAML parse'ı (pyyaml bağımlılığı olmadan) mümkün değil, ama
    en azından sekme (tab) karakteri İÇERMEDİĞİNİ doğrula — YAML sekmeyi
    kabul etmez, bu en yaygın "geçersiz YAML" hatasıdır."""
    metin = _CI_YOLU.read_text(encoding="utf-8")
    assert "\t" not in metin
