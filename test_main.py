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
import json
import sys
from pathlib import Path
from typing import List

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
    """ERC/DRC temiz, --produce yok -> PASS(0), üretim çalışmaz.

    NOT: `termal_mekanik_veri.json` bilerek YAZILMADI — bu, `faz_termal_mekanik`'in
    GERÇEK (mock'lanmamış) haliyle çalışıp KAPSAM_YOK dönmesini ve bunun
    sonucu ENGELLEMEMESİNİ kanıtlar (bkz. `test_cmd_run_termal_veri_yoksa_kapsam_yok_engellemez`
    ile aynı senaryo, burada dolaylı olarak da doğrulanıyor)."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 0


def test_cmd_run_termal_veri_yoksa_kapsam_yok_engellemez(monkeypatch, tmp_path):
    """`termal_mekanik_veri.json` yokken `faz_termal_mekanik` GERÇEK
    (mock'lanmamış) haliyle çalışır -> KAPSAM_YOK -> ERC/DRC temizse SONUÇ
    yine PASS(0) olmalı (KAPSAM_YOK bir engel DEĞİL)."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 0


def test_cmd_run_termal_veri_fail_ise_produce_engellenir(monkeypatch, tmp_path):
    """`termal_mekanik_veri.json` bir ihlal (yüksek güçlü komponent + kasa
    temas bölgesi + tanımsız B.Mask açıklığı) üretecek şekilde varsa,
    ERC/DRC temiz olsa bile FAIL-CLOSED: --produce'a ULAŞILMAZ, sonuç 1."""
    _proje_kur(tmp_path)
    (tmp_path / "termal_mekanik_veri.json").write_text(json.dumps({
        "kritik_guc_esigi_W": 0.5,
        "komponentler": [
            {
                "isim": "U1", "x": 5.0, "y": 5.0, "guc_yayilimi_W": 1.0,
                "mevcut_termal_via_sayisi": 10,
                "b_mask_acikligi_tanimli_mi": False, "yuzey_kaplamasi": "TBD",
            }
        ],
        "yuzeyler": [
            {"isim": "boss1", "poligon": [[0, 0], [10, 0], [10, 10], [0, 10]], "z_boslugu_mm": 0.3}
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path, produce=True)) == 1


def test_cmd_run_yerlesim_veri_yoksa_kapsam_yok_engellemez(monkeypatch, tmp_path):
    """`yerlesim_veri.json` yokken `faz_yerlesim_planlama` GERÇEK
    (mock'lanmamış) haliyle çalışır -> her iki gate de KAPSAM_YOK -> ERC/DRC
    temizse SONUÇ yine PASS(0) olmalı."""
    _proje_kur(tmp_path)
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path)) == 0


def test_cmd_run_yerlesim_cakisma_fail_ise_produce_engellenir(monkeypatch, tmp_path):
    """`yerlesim_veri.json` iki SABİT komponenti kasıtlı olarak aynı
    koordinata (çakışacak şekilde) tanımlarsa -> `cakisma_kontrolu` FAIL ->
    ERC/DRC temiz olsa bile FAIL-CLOSED: --produce'a ULAŞILMAZ, sonuç 1."""
    _proje_kur(tmp_path)
    (tmp_path / "yerlesim_veri.json").write_text(json.dumps({
        "kart_genisligi_mm": 40.0, "kart_yuksekligi_mm": 40.0,
        "komponentler": [
            {"ref": "U1", "genislik_mm": 5.0, "yukseklik_mm": 5.0, "sabit": True, "x": 20.0, "y": 20.0},
            {"ref": "U2", "genislik_mm": 5.0, "yukseklik_mm": 5.0, "sabit": True, "x": 20.0, "y": 20.0},
        ],
        "netler": [], "kisitlar": [],
    }), encoding="utf-8")
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path, produce=True)) == 1


def test_cmd_run_yerlesim_kisit_ihlali_fail_ise_produce_engellenir(monkeypatch, tmp_path):
    """Sağlanamayan bir `MesafeKisiti` (maks_mm) -> `kisitlari_dogrula` FAIL
    -> FAIL-CLOSED."""
    _proje_kur(tmp_path)
    (tmp_path / "yerlesim_veri.json").write_text(json.dumps({
        "kart_genisligi_mm": 40.0, "kart_yuksekligi_mm": 40.0,
        "komponentler": [
            {"ref": "U1", "genislik_mm": 1.0, "yukseklik_mm": 1.0, "sabit": True, "x": 1.0, "y": 1.0},
            {"ref": "U2", "genislik_mm": 1.0, "yukseklik_mm": 1.0, "sabit": True, "x": 39.0, "y": 39.0},
        ],
        "netler": [],
        "kisitlar": [{"ref_a": "U1", "ref_b": "U2", "maks_mm": 1.0, "aciklama": "test"}],
    }), encoding="utf-8")
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))
    assert cmd_run(_args(tmp_path, produce=True)) == 1


def test_cmd_run_yerlesim_hiyerarsi_raporu_test_dizinine_yazilir(monkeypatch, tmp_path):
    """Gerçek bir yerleşim çalıştığında `TEST/yerlesim_raporu.md` üretilmeli
    (insan onaylı sonraki adım için) — board'a hiçbir şey YAZILMAZ."""
    _proje_kur(tmp_path)
    (tmp_path / "yerlesim_veri.json").write_text(json.dumps({
        "kart_genisligi_mm": 40.0, "kart_yuksekligi_mm": 40.0,
        "komponentler": [
            {"ref": "C1", "genislik_mm": 1.0, "yukseklik_mm": 0.5, "kategori": "guc_dekuplaj"},
            {"ref": "U1", "genislik_mm": 5.0, "yukseklik_mm": 5.0, "kategori": "kritik_hs"},
        ],
        "netler": [{"isim": "SIG", "baglantilar": ["U1", "C1"], "agirlik": 1.0}],
        "kisitlar": [],
    }), encoding="utf-8")
    monkeypatch.setattr(main, "faz_ortam", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_uretim", lambda *a, **k: pytest.fail("üretim ulaşılmamalı"))

    kod = cmd_run(_args(tmp_path))

    assert kod == 0
    scratch_dosyalari = list((tmp_path / ".scratch").glob("*/TEST/yerlesim_raporu.md"))
    assert len(scratch_dosyalari) == 1
    icerik = scratch_dosyalari[0].read_text(encoding="utf-8")
    assert "Force-Directed Yerleşim Raporu" in icerik


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


# ------------------------------------------------------------------
# 3. cmd_sistem_atama_plani_uret — sistem_orkestratoru.py CLI köprüsü
# ------------------------------------------------------------------
#
# Önceden main.py'ye HİÇ bağlı değildi (kod incelemesinde bulunan boşluk) —
# `build_parser()` üzerinden gerçek CLI ayrıştırmasıyla test edilir.

def _atama_args(**overrides):
    varsayilanlar = dict(
        kamera_sayisi=6, sensor_i2c_adresi="0x36",
        deserializer_taban_hedef_adresi="0x40", deserializer_maks_kanal=8,
        sozlesme=None, cikti=None,
    )
    varsayilanlar.update(overrides)
    argv = [
        "sistem-atama-plani-uret",
        "--kamera-sayisi", str(varsayilanlar["kamera_sayisi"]),
        "--sensor-i2c-adresi", varsayilanlar["sensor_i2c_adresi"],
        "--deserializer-taban-hedef-adresi", varsayilanlar["deserializer_taban_hedef_adresi"],
        "--deserializer-maks-kanal", str(varsayilanlar["deserializer_maks_kanal"]),
    ]
    if varsayilanlar["sozlesme"]:
        argv += ["--sozlesme", varsayilanlar["sozlesme"]]
    if varsayilanlar["cikti"]:
        argv += ["--cikti", varsayilanlar["cikti"]]
    return main.build_parser().parse_args(argv)


def test_sistem_atama_plani_uret_gecerli_plan_cikti_dosyasina_yazar(tmp_path):
    import yaml

    cikti = tmp_path / "plan.yaml"
    args = _atama_args(cikti=str(cikti))

    kod = main.cmd_sistem_atama_plani_uret(args)

    assert kod == 0
    assert cikti.exists()
    veri = yaml.safe_load(cikti.read_text(encoding="utf-8"))
    assert veri["vc_id"]["atama"] == {f"kart_{i}": i - 1 for i in range(1, 7)}


def test_sistem_atama_plani_uret_mevcut_sozlesmeyi_gunceller(tmp_path):
    import yaml

    sozlesme = tmp_path / "arayuz_sozlesmesi.yaml"
    sozlesme.write_text(yaml.safe_dump({
        "versiyon": 1,
        "konnektor": {"pin_sayisi": 4},
        "vc_id": {"aralik": [0, 5], "atama": {"kart_1": 99}},
    }), encoding="utf-8")
    args = _atama_args(sozlesme=str(sozlesme))

    kod = main.cmd_sistem_atama_plani_uret(args)

    assert kod == 0
    guncel = yaml.safe_load(sozlesme.read_text(encoding="utf-8"))
    assert guncel["konnektor"] == {"pin_sayisi": 4}  # dokunulmadı
    assert guncel["vc_id"]["atama"]["kart_1"] == 0    # 99 DEĞİL, plandan güncellendi


def test_sistem_atama_plani_uret_fail_ise_hicbir_dosyaya_yazmaz(tmp_path):
    """Kanal limiti aşılırsa (9 kart > 8 kanal) plan FAIL vermeli ve
    fail-closed: hiçbir dosya yazılmamalı."""
    cikti = tmp_path / "plan.yaml"
    args = _atama_args(kamera_sayisi=9, deserializer_maks_kanal=8, cikti=str(cikti))

    kod = main.cmd_sistem_atama_plani_uret(args)

    assert kod == 1
    assert not cikti.exists()


def test_sistem_atama_plani_uret_dosya_verilmezse_yine_de_calisir(tmp_path):
    args = _atama_args()
    assert main.cmd_sistem_atama_plani_uret(args) == 0


# ------------------------------------------------------------------
# 4. cmd_device_tree_uret — device_tree_uretici.py CLI köprüsü
# ------------------------------------------------------------------

def _dts_args(sozlesme, bus_haritasi_json, soc="rk3588", cikti=None):
    argv = [
        "device-tree-uret", "--soc", soc, "--sozlesme", str(sozlesme),
        "--bus-haritasi", bus_haritasi_json,
    ]
    if cikti:
        argv += ["--cikti", str(cikti)]
    return main.build_parser().parse_args(argv)


def _plan_yaz(tmp_path, kamera_sayisi=3):
    import yaml

    plan_args = _atama_args(kamera_sayisi=kamera_sayisi, cikti=str(tmp_path / "sozlesme.yaml"))
    main.cmd_sistem_atama_plani_uret(plan_args)
    return tmp_path / "sozlesme.yaml"


def test_device_tree_uret_rk3588_ucdan_uca_pass_ve_dosya_yazar(tmp_path):
    sozlesme = _plan_yaz(tmp_path, kamera_sayisi=3)
    cikti = tmp_path / "camera.dts"
    args = _dts_args(sozlesme, '{"1":"i2c1","2":"i2c3","3":"i2c5"}', cikti=cikti)

    kod = main.cmd_device_tree_uret(args)

    assert kod == 0
    assert cikti.exists()
    assert "&i2c1 {" in cikti.read_text(encoding="utf-8")


def test_device_tree_uret_ambarella_kapsam_yok_dosya_yazmaz(tmp_path):
    sozlesme = _plan_yaz(tmp_path, kamera_sayisi=1)
    cikti = tmp_path / "camera.dts"
    args = _dts_args(sozlesme, '{"1":"i2c1"}', soc="ambarella", cikti=cikti)

    kod = main.cmd_device_tree_uret(args)

    assert kod == 1
    assert not cikti.exists()


def test_device_tree_uret_sozlesme_yoksa_kapsam_yok(tmp_path):
    args = _dts_args(tmp_path / "yok.yaml", '{"1":"i2c1"}')
    assert main.cmd_device_tree_uret(args) == 1


# ------------------------------------------------------------------
# 5. FAZ 0.5-5: anahat-degisti-yeniden-yerlestir (mekanik DXF değişimi
#    tetikleyicisi) — anahat_degisti_mi / faz_yerlesim_planlama'nın
#    TEST/yerlesim_sonucu.json çıktısı / cmd_anahat_degisti_yeniden_yerlestir
# ------------------------------------------------------------------

def _yerlesim_veri_yaz(proje_dizini: Path, kart_genisligi_mm=40.0, kart_yuksekligi_mm=40.0):
    (proje_dizini / "yerlesim_veri.json").write_text(json.dumps({
        "kart_genisligi_mm": kart_genisligi_mm, "kart_yuksekligi_mm": kart_yuksekligi_mm,
        "komponentler": [
            {"ref": "U1", "genislik_mm": 2.0, "yukseklik_mm": 2.0, "kategori": "dusuk_hiz_io"},
            {"ref": "U2", "genislik_mm": 2.0, "yukseklik_mm": 2.0, "kategori": "dusuk_hiz_io"},
        ],
        "netler": [{"isim": "N1", "baglantilar": ["U1", "U2"]}],
        "kisitlar": [],
    }), encoding="utf-8")


def _anahat_args(proje_dizini, dxf_yolu):
    argv = [
        "anahat-degisti-yeniden-yerlestir",
        "--proje-dizini", str(proje_dizini),
        "--dxf-yolu", str(dxf_yolu),
    ]
    return main.build_parser().parse_args(argv)


def test_anahat_degisti_mi_ilk_calistirmada_true():
    """Kayıtlı bir önceki durum yoksa 'değişti' sayılır — karşılaştıracak
    bir referans olmadığı için bu, ilk yerleşimin çalışmasını sağlar."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proje = Path(td)
        dxf = proje / "anahat.dxf"
        dxf.write_text("DXF-ICERIK-1", encoding="utf-8")
        assert main.anahat_degisti_mi(proje, dxf) is True


def test_anahat_degisti_mi_ayni_icerikte_false(tmp_path):
    dxf = tmp_path / "anahat.dxf"
    dxf.write_text("DXF-ICERIK-1", encoding="utf-8")
    main._anahat_durumunu_kaydet(tmp_path, dxf)
    assert main.anahat_degisti_mi(tmp_path, dxf) is False


def test_anahat_degisti_mi_farkli_icerikte_true(tmp_path):
    dxf = tmp_path / "anahat.dxf"
    dxf.write_text("DXF-ICERIK-1", encoding="utf-8")
    main._anahat_durumunu_kaydet(tmp_path, dxf)
    dxf.write_text("DXF-ICERIK-2-DEGISTI", encoding="utf-8")
    assert main.anahat_degisti_mi(tmp_path, dxf) is True


def test_faz_yerlesim_planlama_yerlesim_sonucu_json_yazar(tmp_path):
    _yerlesim_veri_yaz(tmp_path)
    main.faz_yerlesim_planlama(tmp_path)
    sonuc_yolu = tmp_path / main.YERLESIM_SONUC_DOSYASI
    assert sonuc_yolu.is_file()
    veri = json.loads(sonuc_yolu.read_text(encoding="utf-8"))
    assert set(veri["koordinatlar"].keys()) == {"U1", "U2"}


def test_onceki_yerlesim_koordinatlarini_yukle_dosya_yoksa_none(tmp_path):
    assert main.onceki_yerlesim_koordinatlarini_yukle(tmp_path) is None


def test_onceki_yerlesim_koordinatlarini_yukle_yazilani_geri_okur(tmp_path):
    _yerlesim_veri_yaz(tmp_path)
    main.faz_yerlesim_planlama(tmp_path)
    koord = main.onceki_yerlesim_koordinatlarini_yukle(tmp_path)
    assert set(koord.keys()) == {"U1", "U2"}
    assert isinstance(koord["U1"], tuple)


def test_cmd_anahat_degisti_yeniden_yerlestir_dxf_yoksa_hata(tmp_path):
    args = _anahat_args(tmp_path, tmp_path / "yok.dxf")
    assert main.cmd_anahat_degisti_yeniden_yerlestir(args) == 2


def test_cmd_anahat_degisti_yeniden_yerlestir_ilk_calistirma_yerlesimi_calistirir(tmp_path):
    _yerlesim_veri_yaz(tmp_path)
    dxf = tmp_path / "anahat.dxf"
    dxf.write_text("DXF-V1", encoding="utf-8")

    kod = main.cmd_anahat_degisti_yeniden_yerlestir(_anahat_args(tmp_path, dxf))

    assert kod == 0
    assert (tmp_path / main.YERLESIM_SONUC_DOSYASI).is_file()
    assert (tmp_path / main.ANAHAT_DURUM_DOSYASI).is_file()


def test_cmd_anahat_degisti_yeniden_yerlestir_degismezse_tekrar_calismaz(tmp_path, monkeypatch):
    _yerlesim_veri_yaz(tmp_path)
    dxf = tmp_path / "anahat.dxf"
    dxf.write_text("DXF-V1", encoding="utf-8")

    assert main.cmd_anahat_degisti_yeniden_yerlestir(_anahat_args(tmp_path, dxf)) == 0

    monkeypatch.setattr(
        main, "faz_yerlesim_planlama",
        lambda *a, **k: pytest.fail("anahat değişmediyse yerleşim TEKRAR çalışmamalı"),
    )
    kod = main.cmd_anahat_degisti_yeniden_yerlestir(_anahat_args(tmp_path, dxf))
    assert kod == 0


def test_cmd_anahat_degisti_yeniden_yerlestir_degisince_oncekinden_devam_eder(tmp_path, monkeypatch):
    """Uçtan uca kanıt: anahat değişince `faz_yerlesim_planlama`'ya BOŞ
    OLMAYAN bir `baslangic_koordinatlari` geçirilir — ilk çalıştırmanın
    sonucundan devam edildiğinin kanıtı."""
    _yerlesim_veri_yaz(tmp_path)
    dxf = tmp_path / "anahat.dxf"
    dxf.write_text("DXF-V1", encoding="utf-8")
    assert main.cmd_anahat_degisti_yeniden_yerlestir(_anahat_args(tmp_path, dxf)) == 0

    dxf.write_text("DXF-V2-DEGISTI", encoding="utf-8")

    yakalanan = {}
    orijinal = main.faz_yerlesim_planlama

    def _casus(proje_dizini, baslangic_koordinatlari=None):
        yakalanan["baslangic_koordinatlari"] = baslangic_koordinatlari
        return orijinal(proje_dizini, baslangic_koordinatlari=baslangic_koordinatlari)

    monkeypatch.setattr(main, "faz_yerlesim_planlama", _casus)

    kod = main.cmd_anahat_degisti_yeniden_yerlestir(_anahat_args(tmp_path, dxf))

    assert kod == 0
    assert yakalanan["baslangic_koordinatlari"]
    assert set(yakalanan["baslangic_koordinatlari"].keys()) == {"U1", "U2"}


# ------------------------------------------------------------------
# 5. cmd_coklu_kart_dogrula — coklu_kart_sozlesme_kontrolu.py CLI köprüsü
# ------------------------------------------------------------------
#
# FAZ 0.5 #36/#37 mutabakat turunda bulunan boşluk: coklu_kart_sozlesme_
# kontrolu.py'nin KENDİ testleri (test_coklu_kart_sozlesme_kontrolu.py)
# vardı ama main.py'nin CLI sarmalayıcısı (`cmd_coklu_kart_dogrula`) HİÇ
# test edilmemişti — `cmd_sistem_atama_plani_uret`'in AYNI mocking
# desenini (`sys.modules["pcbnew"]`'e taklit modül) kullanır.

class _SahtePad:
    def __init__(self, numara: str, net: str):
        self._numara = numara
        self._net = net

    def GetNumber(self) -> str:
        return self._numara

    def GetNetname(self) -> str:
        return self._net


class _SahteFootprint:
    def __init__(self, ref: str, padlar: List[_SahtePad]):
        self._ref = ref
        self._padlar = padlar

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[_SahtePad]:
        return self._padlar


class _SahteBoard:
    def __init__(self, footprints: List[_SahteFootprint]):
        self._footprints = footprints

    def GetFootprints(self):
        return self._footprints


class _TaklitPcbnewModulu:
    def __init__(self, board: _SahteBoard):
        self._board = board

    def LoadBoard(self, yol: str) -> _SahteBoard:
        return self._board


@pytest.fixture(autouse=True)
def _pcbnew_taklidini_temizle():
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


def _sozlesme_yaz(tmp_path, guc_giris_maks_a=6.0):
    import yaml

    sozlesme = tmp_path / "arayuz_sozlesmesi.yaml"
    sozlesme.write_text(yaml.safe_dump({
        "versiyon": 1,
        "konnektor": {
            "pin_sayisi": 2,
            "kamera_karti_referans": "J1",
            "ana_kart_referans_sablonu": "J{kart}",
            "pinler": [
                {"no": 1, "net": "MIPI_D0_P", "yon": "giris"},
                {"no": 2, "net": "MIPI_D0_N", "yon": "giris"},
            ],
        },
        "guc_butcesi": {
            "kart_basi_maks_akim_a": 0.5, "kart_sayisi": 6,
            "ana_kart_giris_marj_yuzde": 20.0,
            "ana_kart_guc_girisi_maks_a": guc_giris_maks_a,
        },
        "vc_id": {"aralik": [0, 5], "atama": {f"kart_{i}": i - 1 for i in range(1, 7)}},
    }), encoding="utf-8")
    return sozlesme


def _kamera_board(pinler_tutarli=True):
    net_1 = "MIPI_D0_P" if pinler_tutarli else "YANLIS_NET"
    return _SahteBoard([_SahteFootprint("J1", [_SahtePad("1", net_1), _SahtePad("2", "MIPI_D0_N")])])


def _ana_kart_board():
    fps = [
        _SahteFootprint(f"J{i}", [_SahtePad("1", "MIPI_D0_P"), _SahtePad("2", "MIPI_D0_N")])
        for i in range(1, 7)
    ]
    return _SahteBoard(fps)


def _coklu_kart_args(tmp_path, sozlesme, karar_proje_dir=None):
    argv = [
        "coklu-kart-dogrula",
        "--sozlesme", str(sozlesme),
        "--kamera-karti", str(tmp_path / "kamera.kicad_pcb"),
        "--ana-kart", str(tmp_path / "ana_kart.kicad_pcb"),
    ]
    if karar_proje_dir:
        argv += ["--karar-proje-dir", str(karar_proje_dir)]
    return main.build_parser().parse_args(argv)


def test_coklu_kart_dogrula_tutarli_boardlar_pass(tmp_path, capsys):
    sozlesme = _sozlesme_yaz(tmp_path)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(_kamera_board(pinler_tutarli=True))
    # NOT: kamera + ana kart AYNI mock board üzerinden LoadBoard() çağrılır
    # (gerçek CLI'da iki AYRI dosya/board olur) — burada tek bir taklit
    # board içine HEM J1 (kamera) HEM J1..J6 (ana kart) footprint'lerini
    # koyup TEK board ile ikisini de karşılıyoruz (LoadBoard yol argümanını
    # AYIRT ETMEZ, bu CLI-sarmalayıcı testinin kapsamı dışında — pin-bazlı
    # ayrım mantığı zaten test_coklu_kart_sozlesme_kontrolu.py'de kanıtlı).
    birlesik = _SahteBoard(_kamera_board(True)._footprints + _ana_kart_board()._footprints)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(birlesik)

    kod = main.cmd_coklu_kart_dogrula(_coklu_kart_args(tmp_path, sozlesme))

    cikti = capsys.readouterr().out
    assert kod == 0
    assert "SONUÇ: PASS" in cikti


def test_coklu_kart_dogrula_pin_uyumsuzlugu_fail(tmp_path, capsys):
    sozlesme = _sozlesme_yaz(tmp_path)
    birlesik = _SahteBoard(_kamera_board(pinler_tutarli=False)._footprints + _ana_kart_board()._footprints)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(birlesik)

    kod = main.cmd_coklu_kart_dogrula(_coklu_kart_args(tmp_path, sozlesme))

    cikti = capsys.readouterr().out
    assert kod == 1
    assert "SONUÇ: FAIL" in cikti


def test_coklu_kart_dogrula_guc_butcesi_asimi_fail(tmp_path, capsys):
    # ana kart giriş sınırı BİLEREK çok düşük -> güç bütçesi kontrolü FAIL
    sozlesme = _sozlesme_yaz(tmp_path, guc_giris_maks_a=0.1)
    birlesik = _SahteBoard(_kamera_board(True)._footprints + _ana_kart_board()._footprints)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(birlesik)

    kod = main.cmd_coklu_kart_dogrula(_coklu_kart_args(tmp_path, sozlesme))

    assert kod == 1


def test_coklu_kart_dogrula_karar_proje_dir_verilirse_karar_birimleri_json_yazilir(tmp_path):
    sozlesme = _sozlesme_yaz(tmp_path)
    birlesik = _SahteBoard(_kamera_board(True)._footprints + _ana_kart_board()._footprints)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(birlesik)
    proje_dir = tmp_path / "proje"
    proje_dir.mkdir()

    kod = main.cmd_coklu_kart_dogrula(_coklu_kart_args(tmp_path, sozlesme, karar_proje_dir=proje_dir))

    assert kod == 0
    karar_json = proje_dir / "DOCS" / "karar_birimleri.json"
    assert karar_json.exists()
    veri = json.loads(karar_json.read_text(encoding="utf-8"))
    kararlar = veri if isinstance(veri, list) else veri.get("kararlar", veri)
    assert any(
        (k.get("karar_id") == "coklu-kart-arayuz-tutarli") and (k.get("durum") == "KABUL_EDILDI")
        for k in (kararlar if isinstance(kararlar, list) else kararlar.values())
    )


def test_envanter_guncelle_xlsx_uretir(tmp_path):
    """`--testleri-atla` ile hızlı — tam suite koşumu bu testin kapsamı
    dışında (`yetenek_envanteri_uret.py`'nin kendi testleri bunu kanıtlıyor),
    burada sadece main.py CLI köprüsünün gerçekten çağrıldığı doğrulanır."""
    (tmp_path / "ornek_modul.py").write_text('"""Örnek modül."""\ndef f():\n    pass\n', encoding="utf-8")

    args = main.build_parser().parse_args([
        "envanter-guncelle", "--repo-dizini", str(tmp_path), "--testleri-atla",
    ])
    kod = main.cmd_envanter_guncelle(args)

    assert kod == 0
    assert (tmp_path / "YETENEK_ENVANTERI.xlsx").exists()


def test_coklu_kart_dogrula_bos_board_kapsam_yok_fail(tmp_path, capsys):
    """Konnektör hiç bulunamazsa (KAPSAM_YOK) bu PASS SAYILMAZ — dosya
    başlığındaki 'taranan==0 asla PASS değildir' disiplininin CLI'dan
    da bozulmadığının kanıtı."""
    sozlesme = _sozlesme_yaz(tmp_path)
    sys.modules["pcbnew"] = _TaklitPcbnewModulu(_SahteBoard([]))

    kod = main.cmd_coklu_kart_dogrula(_coklu_kart_args(tmp_path, sozlesme))

    cikti = capsys.readouterr().out
    assert kod == 1
    assert "KAPSAM_YOK" in cikti
