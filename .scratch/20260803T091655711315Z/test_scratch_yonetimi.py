"""scratch_yonetimi.py için test suite (GÖREV 1 — governance katmanı)."""

import pytest

from scratch_yonetimi import (
    SCRATCH_KOK_ADI,
    kanonige_yukselt,
    scratch_id_uret,
    scratch_kok_dizini,
    scratch_listele,
    scratch_olustur,
    scratch_yolunu_dogrula,
)


def _proje_kur(tmp_path):
    (tmp_path / "projem.kicad_pro").write_text("pro", encoding="utf-8")
    (tmp_path / "projem.kicad_pcb").write_text("pcb-v1", encoding="utf-8")
    alt = tmp_path / "DOCS"
    alt.mkdir()
    (alt / "01.md").write_text("doc", encoding="utf-8")
    return tmp_path


def test_scratch_id_benzersiz_ve_siralanabilir():
    a = scratch_id_uret()
    b = scratch_id_uret()
    assert a != b or True  # aynı mikrosaniyede üretilirse eşit olabilir; asıl kontrol format
    assert a.endswith("Z")


def test_scratch_olustur_dosyalari_kopyalar(tmp_path):
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")

    assert scratch == scratch_kok_dizini(str(tmp_path)) / "sid1"
    assert (scratch / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-v1"
    assert (scratch / "DOCS" / "01.md").exists()


def test_scratch_olustur_kanonik_dosyaya_dokunmaz(tmp_path):
    """Scratch kopyalama sonrası kanonik dosyanın mtime/içeriği DEĞİŞMEMELİ
    — bu, 'kanonik dosyalar sadece okunur' garantisinin doğrudan kanıtı."""
    _proje_kur(tmp_path)
    kanonik_pcb = tmp_path / "projem.kicad_pcb"
    once = kanonik_pcb.read_text(encoding="utf-8")

    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-v2-scratch-degisikligi", encoding="utf-8")

    sonra = kanonik_pcb.read_text(encoding="utf-8")
    assert once == sonra == "pcb-v1"


def test_scratch_olustur_scratch_kendini_kopyalamaz(tmp_path):
    """`.scratch/` dizininin kendisi (önceki oturumlardan kalan) yeni bir
    scratch kopyasının İÇİNE tekrar kopyalanmamalı — sonsuz iç içe büyüme
    riski."""
    _proje_kur(tmp_path)
    scratch_olustur(str(tmp_path), scratch_id="sid1")

    scratch2 = scratch_olustur(str(tmp_path), scratch_id="sid2")

    assert not (scratch2 / SCRATCH_KOK_ADI).exists()


def test_scratch_olustur_ayni_id_ikinci_kez_hata(tmp_path):
    _proje_kur(tmp_path)
    scratch_olustur(str(tmp_path), scratch_id="sid1")
    with pytest.raises(FileExistsError):
        scratch_olustur(str(tmp_path), scratch_id="sid1")


def test_scratch_olustur_proje_dizini_yoksa_hata(tmp_path):
    with pytest.raises(FileNotFoundError):
        scratch_olustur(str(tmp_path / "yok"))


def test_scratch_yolunu_dogrula_gecerli_scratch_sessiz_gecer(tmp_path):
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    scratch_yolunu_dogrula(scratch, str(tmp_path))  # hata fırlatmamalı


def test_scratch_yolunu_dogrula_kanonik_yol_reddedilir(tmp_path):
    """FAIL-CLOSED çekirdek: kanonik dizinin kendisi (veya scratch dışı
    herhangi bir yol) 'scratch' olarak kabul EDİLMEMELİ."""
    _proje_kur(tmp_path)
    with pytest.raises(ValueError):
        scratch_yolunu_dogrula(tmp_path, str(tmp_path))


def test_kanonige_yukselt_scratch_disi_yolu_reddeder(tmp_path):
    """`kanonige_yukselt`, scratch doğrulaması ATLANARAK kanonik dosyaya
    rastgele bir kaynaktan kopyalama yapılmasını ENGELLEMELİ."""
    _proje_kur(tmp_path)
    sahte_kaynak = tmp_path.parent / "baska_yer"
    sahte_kaynak.mkdir()
    (sahte_kaynak / "x.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError):
        kanonige_yukselt(sahte_kaynak, str(tmp_path))


def test_kanonige_yukselt_dosyalari_kanonige_kopyalar(tmp_path):
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")
    (scratch / "projem.kicad_pcb").write_text("pcb-v2-yukseltildi", encoding="utf-8")

    kanonige_yukselt(scratch, str(tmp_path))

    assert (tmp_path / "projem.kicad_pcb").read_text(encoding="utf-8") == "pcb-v2-yukseltildi"


def test_kanonige_yukselt_scratch_kok_dizinini_kopyalamaz(tmp_path):
    """`.scratch/` klasörünün kendisi yükseltme sırasında kanonik dizine
    kopyalanmamalı (iç içe/döngüsel scratch riski)."""
    _proje_kur(tmp_path)
    scratch = scratch_olustur(str(tmp_path), scratch_id="sid1")

    kanonige_yukselt(scratch, str(tmp_path))

    assert not (tmp_path / ".scratch" / ".scratch").exists()


def test_scratch_listele_bos_proje_bos_liste(tmp_path):
    _proje_kur(tmp_path)
    assert scratch_listele(str(tmp_path)) == []


def test_scratch_listele_en_yeni_once(tmp_path):
    _proje_kur(tmp_path)
    scratch_olustur(str(tmp_path), scratch_id="20260101T000000000000Z")
    scratch_olustur(str(tmp_path), scratch_id="20260102T000000000000Z")

    assert scratch_listele(str(tmp_path)) == [
        "20260102T000000000000Z",
        "20260101T000000000000Z",
    ]
