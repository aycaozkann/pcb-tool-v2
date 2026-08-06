"""main.py::cmd_promote için test suite (GÖREV 3 + 7 — governance katmanı,
2026-08-03).

`cmd_promote`, scratch -> kanonik yükseltme kapısıdır: (1) taze DRC/ERC,
(2) proje-özel kontrat (`bagimsiz_dogrulama.py`), (3) tüm `karar_birimleri`
kayıtlarının `KABUL_EDILDI` olması — ÜÇÜ DE geçmeden kanonik dosyaya
HİÇBİR ŞEY yazılmamalı. Bu dosyanın en kritik testi budur (FAIL-CLOSED):
`test_cmd_promote_drc_fail_kanonik_dosyaya_dokunmaz` ve benzerleri.

Testler `faz_sematik`/`faz_drc`/`bagimsiz_dogrulama_calistir`/
`kararlari_yukle`'yi monkeypatch'ler — gerçek kicad-cli/pcbnew ÇALIŞTIRMAZ.
`scratch_yonetimi` gerçek (mock'lanmadı) çalışır — scratch/kanonik ayrımının
GERÇEKTEN iş yaptığını kanıtlamak bu dosyanın amacı.
"""

import argparse
import json
from pathlib import Path

import pytest

import main
from karar_birimleri import KararBirimi, KararDurumu
from scratch_yonetimi import scratch_olustur


def _proje_kur(tmp_path):
    (tmp_path / "projem.kicad_pro").write_text("pro", encoding="utf-8")
    (tmp_path / "projem.kicad_sch").write_text("sch", encoding="utf-8")
    (tmp_path / "projem.kicad_pcb").write_text("pcb-kanonik-v1", encoding="utf-8")
    return tmp_path


def _args(project_dir, scratch_id=None):
    return argparse.Namespace(project_dir=str(project_dir), scratch_id=scratch_id, kicad_cli=None)


def _temiz_dogrulama_ozeti():
    return {"kontroller": [], "ozet": {}}


def _kirli_dogrulama_ozeti():
    return {
        "kontroller": [
            {"kontrol": "skew[ETH_TRD0]", "durum": "FAIL", "taranan": 1, "ihlal_sayisi": 1,
             "ihlaller": [{"skew_mm": 20}], "detay": ""},
        ],
        "ozet": {},
    }


def _tum_kapilari_ac(monkeypatch, dogrulama_ozeti=None, kararlar=None):
    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "bagimsiz_dogrulama_calistir", lambda *a, **k: dogrulama_ozeti or _temiz_dogrulama_ozeti())
    monkeypatch.setattr(main, "kararlari_yukle", lambda *a, **k: kararlar or [])
    monkeypatch.setattr(main, "_otonom_commit_at", lambda *a, **k: False)  # tmp_path git deposu değil


# ------------------------------------------------------------------
# 1. erken fail-closed kontroller (kapılara ulaşmadan)
# ------------------------------------------------------------------

def test_cmd_promote_proje_dizini_yoksa_2_doner(tmp_path):
    assert main.cmd_promote(_args(tmp_path / "yok")) == 2


def test_cmd_promote_scratch_yoksa_2_doner(tmp_path):
    _proje_kur(tmp_path)
    assert main.cmd_promote(_args(tmp_path, scratch_id="hic-olmayan-id")) == 2


def test_cmd_promote_hic_scratch_uretilmemisse_2_doner(tmp_path):
    _proje_kur(tmp_path)
    assert main.cmd_promote(_args(tmp_path)) == 2  # scratch_id verilmedi VE hiç scratch yok


# ------------------------------------------------------------------
# 2. FAIL-CLOSED çekirdek: hangi kapı FAIL olursa olsun kanonik dosya
#    DEĞİŞMEMELİ
# ------------------------------------------------------------------

def test_cmd_promote_drc_fail_kanonik_dosyaya_dokunmaz(monkeypatch, tmp_path):
    """FAULT-INJECTION: DRC kirli. Scratch'teki board kanonikten FARKLI
    içerikte olsa bile (bir routing script'i scratch'i değiştirmiş gibi),
    kanonik `projem.kicad_pcb` İÇERİĞİ AYNEN KALMALI — promotion HİÇBİR
    kapıya (DRC/verifier/karar) bakılmaksızın kanoniğe dokunmamalı. Diğer
    kapılar da (kasıtlı olarak) çalışır — `cmd_promote` ilk FAIL'de
    KISA-DEVRE YAPMAZ, TÜM red nedenlerini tek raporda toplar; bu yüzden
    burada onları da normal/temiz döndürüyoruz, asıl iddia kanonik dosyanın
    değişmediğidir."""
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-KIRLI-degisiklik", encoding="utf-8")

    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: True)
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: False)  # DRC kirli
    monkeypatch.setattr(main, "bagimsiz_dogrulama_calistir", lambda *a, **k: _temiz_dogrulama_ozeti())
    monkeypatch.setattr(main, "kararlari_yukle", lambda *a, **k: [])
    monkeypatch.setattr(main, "_otonom_commit_at", lambda *a, **k: pytest_fail_erisilmemeli())

    kod = main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    assert kod == 1
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-kanonik-v1"
    assert not (tmp_path / "DOCS" / "07_Dogrulama").exists()


def pytest_fail_erisilmemeli(*a, **k):
    pytest.fail("bu adıma ULAŞILMAMALI — promotion RED olduğu için kanoniğe yazma/commit adımına hiç girilmemeli")


def test_cmd_promote_erc_fail_kanonik_dosyaya_dokunmaz(monkeypatch, tmp_path):
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-degisti", encoding="utf-8")

    monkeypatch.setattr(main, "faz_sematik", lambda *a, **k: False)  # ERC kirli
    monkeypatch.setattr(main, "faz_drc", lambda *a, **k: True)
    monkeypatch.setattr(main, "bagimsiz_dogrulama_calistir", lambda *a, **k: _temiz_dogrulama_ozeti())
    monkeypatch.setattr(main, "kararlari_yukle", lambda *a, **k: [])

    kod = main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    assert kod == 1
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-kanonik-v1"


def test_cmd_promote_bagimsiz_verifier_fail_kanonik_dosyaya_dokunmaz(monkeypatch, tmp_path):
    """FAULT-INJECTION: KiCad DRC/ERC İKİSİ DE temiz ama proje-özel
    kontrat (bağımsız verifier) FAIL — bu, KiCad DRC'nin YAKALAYAMADIĞI
    bir ihlal türüdür (ör. skew). Promotion yine de RED dönmeli."""
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-degisti", encoding="utf-8")

    _tum_kapilari_ac(monkeypatch, dogrulama_ozeti=_kirli_dogrulama_ozeti())

    kod = main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    assert kod == 1
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-kanonik-v1"


def test_cmd_promote_acik_karar_varsa_red_doner(monkeypatch, tmp_path):
    """GÖREV 7: DRC/ERC/verifier hepsi temiz ama bir `karar_birimleri`
    kaydı hâlâ ACIK — promotion bunu da bir kapı olarak saymalı."""
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-degisti", encoding="utf-8")

    acik_karar = KararBirimi(karar_id="stackup-katman-sayisi", soru="4 mü 6 mı?", durum=KararDurumu.ACIK)
    _tum_kapilari_ac(monkeypatch, kararlar=[acik_karar])

    kod = main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    assert kod == 1
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-kanonik-v1"


def test_cmd_promote_kanit_bekliyor_karar_da_red_doner(monkeypatch, tmp_path):
    _proje_kur(tmp_path)
    scratch_olustur(str(tmp_path), scratch_id="sid1")
    karar = KararBirimi(karar_id="x", soru="?", durum=KararDurumu.KANIT_BEKLIYOR)
    _tum_kapilari_ac(monkeypatch, kararlar=[karar])

    assert main.cmd_promote(_args(tmp_path, scratch_id="sid1")) == 1


# ------------------------------------------------------------------
# 3. hepsi temiz -> gerçek promotion
# ------------------------------------------------------------------

def test_cmd_promote_hepsi_temizse_kanonige_yukseltir(monkeypatch, tmp_path):
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-v2-TEMIZ", encoding="utf-8")

    kabul_karar = KararBirimi(karar_id="x", soru="?", durum=KararDurumu.KABUL_EDILDI)
    _tum_kapilari_ac(monkeypatch, kararlar=[kabul_karar])

    kod = main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    assert kod == 0
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-scratch-v2-TEMIZ"


def test_cmd_promote_rapor_hash_alanlariyla_yazilir(monkeypatch, tmp_path):
    """(c) DRC raporunun board-hash + ruleset-hash + komut-hash'e bağlı
    olduğu — rapor dosyasının GERÇEKTEN bu üç alanı içerdiğini doğrula."""
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-scratch-v2", encoding="utf-8")
    _tum_kapilari_ac(monkeypatch)

    assert main.cmd_promote(_args(tmp_path, scratch_id="sid1")) == 0

    raporlar = list((tmp_path / "DOCS" / "07_Dogrulama").glob("promotion_*.json"))
    assert len(raporlar) == 1
    veri = json.loads(raporlar[0].read_text(encoding="utf-8"))
    assert len(veri["board_sha256"]) == 64
    assert len(veri["ruleset_sha256"]) == 64
    assert len(veri["komut_sha256"]) == 64
    assert veri["scratch_id"] == "sid1"
    assert veri["sonuc"] == "PROMOTED"


def test_cmd_promote_scratch_id_verilmezse_en_yeniyi_kullanir(monkeypatch, tmp_path):
    _proje_kur(tmp_path)
    scratch_olustur(str(tmp_path), scratch_id="20260101T000000000000Z")
    yeni = scratch_olustur(str(tmp_path), scratch_id="20260102T000000000000Z")
    (yeni / "projem.kicad_pcb").write_text("pcb-en-yeni-scratch", encoding="utf-8")
    _tum_kapilari_ac(monkeypatch)

    kod = main.cmd_promote(_args(tmp_path, scratch_id=None))

    assert kod == 0
    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-en-yeni-scratch"


def test_cmd_promote_board_hash_gercekten_scratch_pcbsine_ait(monkeypatch, tmp_path):
    """`board_sha256`'nin UYDURULMADIĞINI, gerçekten promote edilen
    `.kicad_pcb` içeriğinin SHA-256'sı olduğunu doğrudan hesaplayıp
    karşılaştır."""
    import hashlib

    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    icerik = "pcb-hash-dogrulama-icerigi"
    (scratch / "projem.kicad_pcb").write_text(icerik, encoding="utf-8")
    _tum_kapilari_ac(monkeypatch)

    main.cmd_promote(_args(tmp_path, scratch_id="sid1"))

    raporlar = list((tmp_path / "DOCS" / "07_Dogrulama").glob("promotion_*.json"))
    veri = json.loads(raporlar[0].read_text(encoding="utf-8"))
    beklenen_hash = hashlib.sha256(icerik.encode("utf-8")).hexdigest()
    assert veri["board_sha256"] == beklenen_hash
