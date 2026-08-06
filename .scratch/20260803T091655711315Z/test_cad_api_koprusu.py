"""cad_api_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_cad_api_koprusu.py

NOT: Bu ortamda ağ erişimi/API token YOK. Testler bu yüzden iki şeyi
kanıtlar: (1) token'sız çağrılar sahte URL/dosya ÜRETMİYOR, (2) indirilen
varlığı doğrulayan iki sert kapı (lifecycle + pin sayısı) gerçekten
çalışıyor. Gerçek indirme senin makinende token ile doğrulanmalı.
"""

import pytest

from bulgu_sozlesmesi import BulguDurumu
from bom_lifecycle_koprusu import LifecycleDurumu, TedarikVerisi

from cad_api_koprusu import (
    IZINLI_HOSTLAR,
    IndirilenVarlik,
    ORNEK_FOOTPRINT,
    ORNEK_SEMBOL,
    Saglayici,
    VarlikSorguSonucu,
    VarlikTipi,
    footprint_pad_numaralari,
    host_izinli_mi,
    indirmeden_once_lifecycle_kapisi,
    kutuphaneye_kaydet,
    lib_table_kaydi_ekle,
    oz_testleri_calistir,
    pin_sayisi_dogrula,
    sembol_pin_numaralari,
    varlik_indir,
    varlik_raporu_uret,
    varlik_raporu_yaz,
    varlik_sorgula,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# KAPI 1 — lifecycle (indirmeden ÖNCE)
# ------------------------------------------------------------------

def test_obsolete_parca_indirilemez():
    """MASTER_RULEBOOK Bölüm 0: prototip olsa bile Obsolete parça YASAK."""
    tedarik = TedarikVerisi("MPU-6050", LifecycleDurumu.OBSOLETE, kaynak="nexar")
    izin, gerekce = indirmeden_once_lifecycle_kapisi("MPU-6050", tedarik=tedarik)
    assert izin is False
    assert "İstisnasız" in gerekce or "istisnasız" in gerekce.lower()


def test_nrnd_parca_indirilemez():
    tedarik = TedarikVerisi("X", LifecycleDurumu.NRND, kaynak="nexar")
    assert indirmeden_once_lifecycle_kapisi("X", tedarik=tedarik)[0] is False


def test_eol_parca_indirilemez():
    tedarik = TedarikVerisi("ESP32-C3FN4", LifecycleDurumu.EOL, kaynak="nexar")
    assert indirmeden_once_lifecycle_kapisi("ESP32-C3FN4", tedarik=tedarik)[0] is False


def test_active_parca_indirilebilir():
    tedarik = TedarikVerisi("ICM-42688-P", LifecycleDurumu.ACTIVE, kaynak="nexar")
    izin, gerekce = indirmeden_once_lifecycle_kapisi("ICM-42688-P", tedarik=tedarik)
    assert izin is True
    assert "Active" in gerekce


def test_bilinmeyen_lifecycle_confirm_olarak_isaretlenir():
    """'Bilinmiyor' sessizce 'Active' sayılamaz — CONFIRM raporlanır."""
    izin, gerekce = indirmeden_once_lifecycle_kapisi("YENI-PARCA", api_key=None)
    assert izin is True
    assert "CONFIRM" in gerekce
    assert "BİLİNMİYOR" in gerekce


# ------------------------------------------------------------------
# Sorgu — token yoksa uydurma YASAK
# ------------------------------------------------------------------

def test_tokensiz_sorgu_url_uydurmaz():
    sonuc = varlik_sorgula("AD7124-8BCPZ", api_token=None)
    assert sonuc.kaynak == "TBD"
    assert sonuc.sembol_url is None
    assert sonuc.footprint_url is None
    assert sonuc.step_url is None
    assert not sonuc.kullanilabilir_mi
    assert any("uydurulmadı" in n for n in sonuc.notlar)


def test_tokenli_sorgu_dogrulanmadigini_soyler():
    """Şeması doğrulanmamış bir API için sahte sonuç dönmek yerine açıkça
    NotImplementedError — sessiz sahte veri üretmekten iyidir."""
    with pytest.raises(NotImplementedError):
        varlik_sorgula("AD7124-8BCPZ", api_token="sahte-token")


def test_saglayici_secilebilir():
    sonuc = varlik_sorgula("X", saglayici=Saglayici.NEXAR)
    assert sonuc.saglayici == Saglayici.NEXAR
    assert "nexar" in sonuc.notlar[0]


# ------------------------------------------------------------------
# İndirme güvenliği
# ------------------------------------------------------------------

def test_izinli_https_host_kabul_edilir():
    assert host_izinli_mi("https://www.snapeda.com/api/x.kicad_sym")


def test_http_reddedilir():
    assert not host_izinli_mi("http://www.snapeda.com/x.kicad_sym")


def test_beyaz_liste_disi_host_reddedilir():
    assert not host_izinli_mi("https://rastgele-site.example/x.kicad_sym")
    assert "snapeda.com" in IZINLI_HOSTLAR


def test_tokensiz_indirme_reddedilir(tmp_path):
    with pytest.raises(RuntimeError):
        varlik_indir("https://www.snapeda.com/x.kicad_sym", str(tmp_path / "x.kicad_sym"))


def test_kotu_host_indirme_reddedilir(tmp_path):
    with pytest.raises(ValueError):
        varlik_indir("https://kotu.example/x", str(tmp_path / "x"), api_token="t")


# ------------------------------------------------------------------
# KAPI 2 — pin sayısı (şematiğe işlemeden ÖNCE)
# ------------------------------------------------------------------

def test_cok_uniteli_sembolde_pin_tekrari_sayilmaz():
    """De Morgan / multi-unit tekrarları pin sayısını şişirmemeli."""
    assert sembol_pin_numaralari(ORNEK_SEMBOL) == ["1", "2", "3"]


def test_footprint_pad_numaralari_okunur():
    assert footprint_pad_numaralari(ORNEK_FOOTPRINT) == ["1", "2", "3"]


def test_dogru_pin_sayisi_pass():
    bulgu = pin_sayisi_dogrula(ORNEK_SEMBOL, 3, ORNEK_FOOTPRINT)
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.taranan == 3


def test_yanlis_pin_sayisi_fail_ve_farki_raporlar():
    bulgu = pin_sayisi_dogrula(ORNEK_SEMBOL, 8)
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["eksik_veya_fazla"] == -5


def test_footprint_sembol_uyusmazligi_yakalanir():
    """SnapEDA'da sembol bir varyanttan, footprint başkasından gelebilir —
    ERC/DRC bunu YAKALAMAZ, ilk kart lehimlenince anlaşılır."""
    pad_eksik = ORNEK_FOOTPRINT.replace(
        '  (pad "3" smd rect (at 1 0) (size 0.6 0.3) (layers "F.Cu" "F.Paste" "F.Mask"))\n', ""
    )
    bulgu = pin_sayisi_dogrula(ORNEK_SEMBOL, 3, pad_eksik)
    assert bulgu.durum == BulguDurumu.FAIL
    ihlal = next(i for i in bulgu.ihlaller if i["kontrol"] == "footprint_vs_sembol")
    assert ihlal["footprintte_olmayan_pinler"] == ["3"]


def test_exposed_pad_footprintte_sayilir():
    """MASTER_RULEBOOK Faz 1: soğutucu (exposed) pad de sayılır, atılmaz."""
    ep_footprint = ORNEK_FOOTPRINT.replace(
        ")\n",
        '  (pad "EP" smd rect (at 0 1) (size 2 2) (layers "F.Cu" "F.Paste" "F.Mask"))\n)\n',
    )
    assert "EP" in footprint_pad_numaralari(ep_footprint)


def test_pinsiz_sembol_kapsam_yok():
    """0 pin, 0 ihlal -> sahte PASS tuzağı `bulgu_sozlesmesi` ile kapalı."""
    bulgu = pin_sayisi_dogrula("(kicad_symbol_lib)", 0)
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert not bulgu.gecti_mi


# ------------------------------------------------------------------
# lib-table kaydı (idempotent)
# ------------------------------------------------------------------

def test_lib_table_yoksa_olusturulur(tmp_path):
    tablo = tmp_path / "sym-lib-table"
    assert lib_table_kaydi_ekle(str(tablo), "proje_lib", "${KIPRJMOD}/x.kicad_sym") is True
    icerik = tablo.read_text(encoding="utf-8")
    assert icerik.startswith("(sym_lib_table")
    assert '(name "proje_lib")' in icerik


def test_fp_lib_table_kok_dugumu_dogru(tmp_path):
    tablo = tmp_path / "fp-lib-table"
    lib_table_kaydi_ekle(str(tablo), "proje_lib", "${KIPRJMOD}/x.pretty")
    assert tablo.read_text(encoding="utf-8").startswith("(fp_lib_table")


def test_ayni_nick_ikinci_kez_eklenmez(tmp_path):
    """Duplicate nickname KiCad'de projeyi AÇILMAZ hale getirir."""
    tablo = tmp_path / "sym-lib-table"
    assert lib_table_kaydi_ekle(str(tablo), "proje_lib", "uri1") is True
    assert lib_table_kaydi_ekle(str(tablo), "proje_lib", "uri2") is False
    assert tablo.read_text(encoding="utf-8").count('(name "proje_lib")') == 1


def test_farkli_nick_eklenebilir(tmp_path):
    tablo = tmp_path / "sym-lib-table"
    lib_table_kaydi_ekle(str(tablo), "lib_a", "uri_a")
    assert lib_table_kaydi_ekle(str(tablo), "lib_b", "uri_b") is True
    icerik = tablo.read_text(encoding="utf-8")
    assert '(name "lib_a")' in icerik and '(name "lib_b")' in icerik


def test_bozuk_lib_table_reddedilir(tmp_path):
    tablo = tmp_path / "sym-lib-table"
    tablo.write_text("bu bir s-expression degil", encoding="utf-8")
    with pytest.raises(ValueError):
        lib_table_kaydi_ekle(str(tablo), "x", "uri")


# ------------------------------------------------------------------
# Projeye kayıt
# ------------------------------------------------------------------

def test_dogrulanmamis_varlik_kaydedilemez(tmp_path):
    """Pin kapısı geçilmeden kütüphaneye kayıt YASAK."""
    varlik = IndirilenVarlik("X", sembol_yolu=str(tmp_path / "x.kicad_sym"))
    with pytest.raises(PermissionError):
        kutuphaneye_kaydet(varlik, str(tmp_path))


def test_dogrulanmis_varlik_kaydedilir_ve_tablolara_yazilir(tmp_path):
    kaynak_sym = tmp_path / "indirilen.kicad_sym"
    kaynak_sym.write_text(ORNEK_SEMBOL, encoding="utf-8")
    kaynak_mod = tmp_path / "TEST_IC.kicad_mod"
    kaynak_mod.write_text(ORNEK_FOOTPRINT, encoding="utf-8")
    kaynak_step = tmp_path / "TEST_IC.step"
    kaynak_step.write_text("ISO-10303-21;", encoding="utf-8")

    proje = tmp_path / "proje"
    proje.mkdir()
    varlik = IndirilenVarlik(
        "TEST_IC",
        sembol_yolu=str(kaynak_sym),
        footprint_yolu=str(kaynak_mod),
        step_yolu=str(kaynak_step),
        kaynak="api",
        pin_dogrulandi_mi=True,
    )
    sonuc = kutuphaneye_kaydet(varlik, str(proje))

    assert (proje / "project_cad_api.kicad_sym").exists()
    assert (proje / "project_cad_api.pretty" / "TEST_IC.kicad_mod").exists()
    assert (proje / "3d_models" / "TEST_IC.step").exists()
    assert set(sonuc["kayitlar"]) == {"sym-lib-table", "fp-lib-table"}
    assert sonuc["eksikler"] == []


def test_eksik_varliklar_raporlanir(tmp_path):
    kaynak_sym = tmp_path / "x.kicad_sym"
    kaynak_sym.write_text(ORNEK_SEMBOL, encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    varlik = IndirilenVarlik("X", sembol_yolu=str(kaynak_sym), pin_dogrulandi_mi=True)
    sonuc = kutuphaneye_kaydet(varlik, str(proje))
    assert sonuc["eksikler"] == [VarlikTipi.FOOTPRINT.value, VarlikTipi.MODEL_3D.value]


# ------------------------------------------------------------------
# Rapor
# ------------------------------------------------------------------

def test_rapor_sorgulanmadi_ile_bulunamadiyi_ayirir():
    sorgular = [
        VarlikSorguSonucu("A", Saglayici.SNAPEDA, kaynak="TBD"),
        VarlikSorguSonucu("B", Saglayici.SNAPEDA, kaynak="CONFIRM"),
        VarlikSorguSonucu("C", Saglayici.SNAPEDA, kaynak="api", sembol_url="https://x"),
    ]
    rapor = varlik_raporu_uret(sorgular)
    assert "SORGULANMADI" in rapor
    assert "elle oluştur" in rapor
    assert "BULUNDU" in rapor


def test_rapor_pin_kapisi_bulgularini_yazar():
    bulgu = pin_sayisi_dogrula(ORNEK_SEMBOL, 8)
    rapor = varlik_raporu_uret([VarlikSorguSonucu("A", Saglayici.SNAPEDA)], [bulgu])
    assert "cad_varlik_pin_sayisi" in rapor
    assert "FAIL" in rapor


def test_rapor_dosyaya_yazilir(tmp_path):
    hedef = tmp_path / "TEST" / "cad_varlik_raporu.md"
    varlik_raporu_yaz(str(hedef), [VarlikSorguSonucu("A", Saglayici.SNAPEDA)])
    assert hedef.exists()
    assert "CAD Varlık Edinme Raporu" in hedef.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
