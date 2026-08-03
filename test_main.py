"""main.py için test suite (GÖREV 3 — 2026-07-31; 2026-07-31 genişletme).

`cmd_run` — otonom akışın tek-komut yürütücüsü — tamamen yeni yazıldı ama
HİÇBİR testi yoktu. Bu dosya, denetimde tespit edilen bu boşluğu kapatır.

Öncelik: FAIL-CLOSED davranış. `cmd_run` DRC/ERC temiz olmadan `--produce`'a
GEÇMEMELİ (production'da bu en kritik kural). Testler `faz_*` fonksiyonlarını
monkeypatch'ler, gerçek `kicad-cli`/KiCad ÇALIŞTIRMAZ. Kapsanan yardımcılar:
`_erc_ihlallerini_topla`, `_erc_temiz_mi`, `_proje_dosyalarini_bul`,
`_drc_baglantisiz_netler`, `_wire_label_sayilarini_oku`, `cmd_run` (uçtan uca,
fail-closed dahil).
"""

import argparse
from pathlib import Path

import pytest

import main
from main import (
    _drc_baglantisiz_netler,
    _erc_ihlallerini_topla,
    _erc_temiz_mi,
    _proje_dosyalarini_bul,
    _wire_label_sayilarini_oku,
    cmd_run,
)


# ------------------------------------------------------------------
# 1. Saf yardımcılar
# ------------------------------------------------------------------

def test_erc_ihlalleri_sheets_altindan_toplanir():
    """ERC şeması DRC'den FARKLIDIR: ihlaller `sheets[].violations` altında,
    her sayfa için AYRI liste. Hepsi tek akışta toplanmalı — yalnızca ilk
    sayfaya bakmak sonraki sayfaların hatalarını kaçırırdı."""
    rapor = {
        "sheets": [
            {"path": "/", "violations": [{"severity": "warning", "description": "w1"}]},
            {"path": "/alt_sayfa", "violations": [{"severity": "error", "description": "e1"}]},
        ]
    }
    ihlaller = _erc_ihlallerini_topla(rapor)
    assert len(ihlaller) == 2
    assert [v["description"] for v in ihlaller] == ["w1", "e1"]


def test_erc_ihlalleri_bos_rapor_bos_liste():
    assert _erc_ihlallerini_topla({}) == []
    assert _erc_ihlallerini_topla({"sheets": []}) == []
    # sheets anahtarı yoksa da sessizce boş — ancak bu, "temiz" anlamına
    # GELMEZ (bkz. kicad_koprusu.sema_taninmadi_mi fail-closed notu)
    assert _erc_ihlallerini_topla({"violations": [{"severity": "error"}]}) == []


def test_erc_temiz_mi_sadece_error_sayar():
    """Uyarılar temiz sayılır; 'error' seviyesi herhangi bir sayfada varsa
    temiz DEĞİLDİR."""
    assert _erc_temiz_mi({"sheets": [{"violations": [{"severity": "warning"}]}]}) is True
    assert _erc_temiz_mi({"sheets": [{"violations": [{"severity": "error"}]}]}) is False
    # ikinci sayfadaki hata da yakalanmalı
    assert _erc_temiz_mi({
        "sheets": [
            {"violations": [{"severity": "warning"}]},
            {"violations": [{"severity": "error"}]},
        ]
    }) is False


def test_proje_dosyalarini_bul_tekli_proje(tmp_path):
    pro = tmp_path / "projem.kicad_pro"
    sch = tmp_path / "projem.kicad_sch"
    pcb = tmp_path / "projem.kicad_pcb"
    pro.write_text("x", encoding="utf-8")
    sch.write_text("x", encoding="utf-8")
    pcb.write_text("x", encoding="utf-8")

    bulunan = _proje_dosyalarini_bul(tmp_path)

    assert bulunan == (pro, sch, pcb)


def test_proje_dosyalarini_bul_sch_pcb_eksikse_none(tmp_path):
    """Gövde adı eşleşen .kicad_sch/.kicad_pcb yoksa o alanlar None döner
    (çağıran taraf --produce kapısında bunları kontrol eder)."""
    pro = tmp_path / "projem.kicad_pro"
    pro.write_text("x", encoding="utf-8")

    bulunan = _proje_dosyalarini_bul(tmp_path)

    assert bulunan[0] == pro
    assert bulunan[1] is None
    assert bulunan[2] is None


def test_proje_dosyalarini_bul_coklu_proje_fail_closed(tmp_path):
    """Birden fazla .kicad_pro varsa HİÇBİRİNİ seçmeden (None, None, None)
    — uydurma bir varsayılan isim SEÇİLMEZ."""
    (tmp_path / "a.kicad_pro").write_text("x", encoding="utf-8")
    (tmp_path / "b.kicad_pro").write_text("x", encoding="utf-8")

    assert _proje_dosyalarini_bul(tmp_path) == (None, None, None)


def test_proje_dosyalarini_bul_proje_yoksa_fail_closed(tmp_path):
    assert _proje_dosyalarini_bul(tmp_path) == (None, None, None)


def test_drc_baglantisiz_netler_adlari_cikarir():
    """`unconnected_items` girdilerinin items[].description alanındaki
    `[NET_ADI]` köşeli parantezli kısımdan net adlarını çıkarır (KiCad 10
    DRC şeması). Gerçek ESP32C3_SmartBand raporuyla birebir şekillendi."""
    rapor = {
        "unconnected_items": [
            {
                "description": "Missing connection between items",
                "items": [
                    {"description": "5 için [IMU_INT1] U1 ayak F.Cu"},
                    {"description": "4 için [IMU_INT1] U2 ayak F.Cu"},
                ],
            },
            {
                "description": "Missing connection between items",
                "items": [
                    {"description": "11 için [DISPLAY_RESET] J1 ayak F.Cu"},
                    {"description": "10 için [DISPLAY_RESET] U1 ayak F.Cu"},
                ],
            },
        ]
    }
    assert _drc_baglantisiz_netler(rapor) == ["IMU_INT1", "DISPLAY_RESET"]


def test_drc_baglantisiz_netler_tekilleştirir():
    """Aynı net adı birden fazla girdide geçse bile TEK kez listelenir —
    aday sayısı (U1.5↔U2.4 gibi) net sayısı değildir."""
    rapor = {
        "unconnected_items": [
            {"items": [{"description": "5 için [IMU_INT1] U1 ayak F.Cu"}]},
            {"items": [{"description": "4 için [IMU_INT1] U2 ayak F.Cu"}]},
        ]
    }
    assert _drc_baglantisiz_netler(rapor) == ["IMU_INT1"]


def test_drc_baglantisiz_netler_parcalanamayan_girdi_atanir():
    """description'ında `[net]` deseni OLMAYAN girdiler (ör. eski kicad-cli
    formatı, uyumsuz sürüm) sessizce atlanır — hata fırlatılmaz."""
    rapor = {
        "unconnected_items": [
            {"items": [{"description": "item with no net name"}, {"description": "other"}]},
            {"items": [{"description": "3 için [GND] U1 ayak F.Cu"}]},
        ]
    }
    assert _drc_baglantisiz_netler(rapor) == ["GND"]


def test_drc_baglantisiz_netler_rapor_boşsa_bos_liste():
    assert _drc_baglantisiz_netler({}) == []
    assert _drc_baglantisiz_netler({"unconnected_items": []}) == []


def test_wire_label_sayilari_okunur(tmp_path):
    sch = tmp_path / "test.kicad_sch"
    sch.write_text(
        "(kicad_sch (version 20231120)\n"
        "  (wire (pts (xy 0 0) (xy 1 0)))\n"
        "  (wire (pts (xy 2 2) (xy 3 2)))\n"
        "  (label \"VCC\" (at 4 4))\n"
        "  (global_label \"GND\" (at 5 5))\n"
        "  (hierarchical_label \"CLK\" (at 6 6))\n"
        ")",
        encoding="utf-8",
    )

    wire_n, label_n = _wire_label_sayilarini_oku(sch)

    assert wire_n == 2
    assert label_n == 3


def test_wire_label_sayilari_sifir(tmp_path):
    sch = tmp_path / "test.kicad_sch"
    sch.write_text("(kicad_sch)\n", encoding="utf-8")

    assert _wire_label_sayilarini_oku(sch) == (0, 0)


# ------------------------------------------------------------------
# 2. cmd_run — orkestratör (faz_* monkeypatch ile izole)
# ------------------------------------------------------------------

def _args(project_dir, produce=False):
    return argparse.Namespace(
        project_dir=str(project_dir), kicad_cli=None, produce=produce,
    )


def _proje_kur(tmp_path, sch_var_mi=True, pcb_var_mi=True):
    pro = tmp_path / "projem.kicad_pro"
    pro.write_text("x", encoding="utf-8")
    if sch_var_mi:
        (tmp_path / "projem.kicad_sch").write_text("x", encoding="utf-8")
    if pcb_var_mi:
        (tmp_path / "projem.kicad_pcb").write_text("x", encoding="utf-8")
    return pro


def test_cmd_run_proje_dizini_yoksa_2_doner(monkeypatch, tmp_path):
    yok = tmp_path / "yok"
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: pytest.fail("ulaşılmamalı"))
    assert cmd_run(_args(yok)) == 2


def test_cmd_run_kicad_cli_eksikse_1_doner(monkeypatch, tmp_path):
    """faz_ortam False dönerse (KiCad CLI kritik araç eksik) akış DURUR —
    sonraki fazlara geçilmez."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: False)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: pytest.fail("ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 1


def test_cmd_run_proje_bulunamazsa_2_doner(monkeypatch, tmp_path):
    """Dizin var ama .kicad_pro yok -> hangi proje olduğu belirsiz -> 2."""
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: pytest.fail("ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 2


def test_cmd_run_erc_hatasi_varken_produce_yoksa_fail(monkeypatch, tmp_path):
    """FAIL-CLOSED kilidi (en kritik): ERC'de error varsa ve --produce
    verilmese bile sonuç FAIL(1) olmalı — üretim çıktısı koduna ULAŞILMAZ."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: False)  # ERC hatası
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 1


def test_cmd_run_drc_hatasi_varken_produce_gitmez(monkeypatch, tmp_path):
    """FAIL-CLOSED kilidi: DRC'de error varsa --produce VERİLSE BİLE üretim
    çalıştırılmamalı, FAIL(1) dönmeli."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: False)  # DRC hatası
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path, produce=True)) == 1


def test_cmd_run_temiz_produce_yoksa_pass(monkeypatch, tmp_path):
    """ERC/DRC temiz, --produce yok -> PASS(0), üretim çalışmaz."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 0


def test_cmd_run_temiz_produce_var_sch_pcb_yoksa_2(monkeypatch, tmp_path):
    """--produce verilmiş ama .kicad_sch/.kicad_pcb yok -> üretime
    geçmeden 2 dönmeli."""
    _proje_kur(tmp_path, sch_var_mi=False, pcb_var_mi=False)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path, produce=True)) == 2


def test_cmd_run_temiz_produce_var_uretim_kodunu_dondurur(monkeypatch, tmp_path):
    """Tam yol: ERC/DRC temiz + sch/pcb var + --produce -> faz_uretim çağrılır,
    onun dönüş kodu cmd_run'un sonucudur.

    GÖREV 1 (governance/scratch, 2026-08-03): `cmd_run` artık kanonik
    `tmp_path`'e DEĞİL, onun `.scratch/<id>/` kopyasına yazar/orada çalışır
    — `proje` argümanı bu yüzden `tmp_path`'in KENDİSİ değil, `tmp_path/
    .scratch/` ALTINDAKİ bir yol olmalı (kanonik dosyaya asla direkt
    yazılmaması garantisinin dolaylı kanıtı)."""
    _proje_kur(tmp_path)
    cagrilar = []

    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)

    def sahte_uretim(pcb, sch, project_dir):
        cagrilar.append((str(pcb), str(sch), str(project_dir)))
        return 0

    monkeypatch.setattr(main, "faz_uretim", sahte_uretim)

    assert cmd_run(_args(tmp_path, produce=True)) == 0
    assert len(cagrilar) == 1
    pcb, sch, proje = cagrilar[0]
    assert pcb.endswith("projem.kicad_pcb")
    assert sch.endswith("projem.kicad_sch")
    assert proje != str(tmp_path)
    assert Path(proje).is_relative_to(tmp_path / ".scratch")


def test_cmd_run_uretim_kodu_basarisizsa_fail(monkeypatch, tmp_path):
    """faz_uretim 0'dan farklı dönerse (ör. kibot hata) cmd_run onu olduğu
    gibi iletir."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: 3)
    assert cmd_run(_args(tmp_path, produce=True)) == 3


def test_cmd_run_erc_atlandi_ama_drc_temizse_pass(monkeypatch, tmp_path):
    """sch yok (ERC ATLANDI) ama pcb var + DRC temiz -> PASS(0) — DRC kapısı
    tek başına karar verir."""
    _proje_kur(tmp_path, sch_var_mi=False, pcb_var_mi=True)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    assert cmd_run(_args(tmp_path)) == 0


# ------------------------------------------------------------------
# 3. UX iyileştirmeleri (2026-07-31): net adları + alt klasör ipucu + KiBot ön uyarısı
# ------------------------------------------------------------------

def test_cmd_run_proje_alt_klasordeyse_ipucu_verir(monkeypatch, tmp_path, capsys):
    """Üst dizin verildiğinde .kicad_pro bulunamaz -> hata + ALT KLASÖR
    ipucu. Kullanıcının "hangi klasör" diye aramaması için doğru dizin
    adresi gösterilir."""
    alt = tmp_path / "pcb-designer-tool"
    alt.mkdir()
    (alt / "projem.kicad_pro").write_text("x", encoding="utf-8")

    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: pytest.fail("ulaşılmamalı"))

    kod = cmd_run(_args(tmp_path))
    cikti = capsys.readouterr().out

    assert kod == 2
    assert "alt klasörde bulundu" in cikti
    assert str(alt) in cikti


def test_cmd_run_birden_fazla_alt_proje_listelenir(monkeypatch, tmp_path, capsys):
    """Birden fazla .kicad_pro alt klasörde varsa hepsi listelenir — tek bir
    adayı gizlice seçmek yerine kullanıcıya seçenek sunulur (fail-closed)."""
    for ad in ("pcb-designer-tool", "baska-proje"):
        klasor = tmp_path / ad
        klasor.mkdir()
        (klasor / f"{ad}.kicad_pro").write_text("x", encoding="utf-8")

    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)

    kod = cmd_run(_args(tmp_path))
    cikti = capsys.readouterr().out

    assert kod == 2
    assert "birden fazla .kicad_pro" in cikti
    assert "pcb-designer-tool" in cikti
    assert "baska-proje" in cikti


def test_faz_uretim_kibot_yoksa_1_doner(monkeypatch, tmp_path, capsys):
    """--produce akışı `faz_uretim`'e ulaştığında KiBot PATH'te yoksa üretim
    çıktısı üretilemeyeceği NET uyarıyla söylenir ve 1 dönülür. Sessizce
    atlayıp "PASS" demek yerine (önceki davranış belirsizdi) fail-closed
    net olmalı."""
    import shutil
    pcb = tmp_path / "projem.kicad_pcb"
    sch = tmp_path / "projem.kicad_sch"
    monkeypatch.setattr(shutil, "which", lambda isim: None if isim == "kibot" else "/usr/bin/x")

    kod = main.faz_uretim(pcb, sch, tmp_path)
    cikti = capsys.readouterr().out

    assert kod == 1
    assert "KiBot PATH'te bulunamadı" in cikti
    assert "pip install kibot" in cikti


def test_faz_uretim_kibot_varsa_cli_cagrilir(monkeypatch, tmp_path):
    """KiBot varsa (shutil.which "kibot" için yol döner) `uretim_ciktilari_cli`
    çağrılır ve onun kodu döner — ön uyarı işlemi BLOCKLAMAZ."""
    import sys
    import shutil
    pcb = tmp_path / "projem.kicad_pcb"
    sch = tmp_path / "projem.kicad_sch"
    cagrilar = []
    monkeypatch.setattr(shutil, "which", lambda isim: "/yol/kibot" if isim == "kibot" else None)

    sahte_cli = type("SahteCli", (), {
        "main": staticmethod(lambda argv: (cagrilar.append(argv) or 0)),
    })
    monkeypatch.setitem(sys.modules, "uretim_ciktilari_cli", sahte_cli)

    assert main.faz_uretim(pcb, sch, tmp_path) == 0
    assert len(cagrilar) == 1


def test_faz_drc_baglantisiz_netleri_yazar(monkeypatch, tmp_path, capsys):
    """faz_drc DRC hatası bulduğunda çıktıya net adlarını yazar — kullanıcı
    hangi netin yarım kaldığını anında görür (raporun "Missing connection"
    satırı tek başına bunu söylemezdi)."""
    rapor = {
        "unconnected_items": [
            {
                "description": "Missing connection between items",
                "items": [
                    {"description": "5 için [IMU_INT1] U1 ayak F.Cu"},
                    {"description": "4 için [IMU_INT1] U2 ayak F.Cu"},
                ],
            }
        ],
        "violations": [],
    }
    monkeypatch.setattr(main, "drc_calistir", lambda *a, **k: rapor)
    monkeypatch.setattr(main, "drc_raporunu_ozetle", lambda r: ["[error] Missing connection between items"])
    monkeypatch.setattr(main, "drc_temiz_mi", lambda r: False)

    temiz = main.faz_drc(tmp_path / "b.kicad_pcb", None)
    cikti = capsys.readouterr().out

    assert temiz is False
    assert "Bağlantısız netler: IMU_INT1" in cikti
