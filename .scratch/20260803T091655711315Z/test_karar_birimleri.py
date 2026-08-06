"""karar_birimleri.py için test suite (GÖREV 5-6 — governance katmanı)."""

import pytest

from karar_birimleri import (
    DongusuHatasi,
    KararBirimi,
    KararDurumu,
    kabul_edilmemis_kararlari_bul,
    karar_dosyasi_yolu,
    karar_ekle_veya_guncelle,
    karar_gecersiz_kil,
    karar_grafigi_dogrula,
    kararlari_kaydet,
    kararlari_yukle,
)


def _karar(karar_id, bagimliliklar=None, durum=KararDurumu.ACIK):
    return KararBirimi(
        karar_id=karar_id,
        soru=f"{karar_id} sorusu?",
        bagimliliklar=bagimliliklar or [],
        durum=durum,
    )


# ------------------------------------------------------------------
# 1. yükle/kaydet round-trip
# ------------------------------------------------------------------

def test_kararlari_yukle_dosya_yoksa_bos_liste(tmp_path):
    assert kararlari_yukle(str(tmp_path)) == []


def test_kaydet_yukle_roundtrip_durumu_korur(tmp_path):
    kararlar = [
        _karar("stackup-katman-sayisi", durum=KararDurumu.KABUL_EDILDI),
        _karar("guc-topolojisi", bagimliliklar=["stackup-katman-sayisi"]),
    ]
    kararlari_kaydet(str(tmp_path), kararlar)

    yuklenen = kararlari_yukle(str(tmp_path))

    assert len(yuklenen) == 2
    by_id = {k.karar_id: k for k in yuklenen}
    assert by_id["stackup-katman-sayisi"].durum == KararDurumu.KABUL_EDILDI
    assert by_id["guc-topolojisi"].bagimliliklar == ["stackup-katman-sayisi"]
    assert karar_dosyasi_yolu(str(tmp_path)).exists()


def test_karar_ekle_veya_guncelle_var_olani_degistirir(tmp_path):
    kararlari_kaydet(str(tmp_path), [_karar("x", durum=KararDurumu.ACIK)])

    karar_ekle_veya_guncelle(str(tmp_path), _karar("x", durum=KararDurumu.KABUL_EDILDI))

    yuklenen = kararlari_yukle(str(tmp_path))
    assert len(yuklenen) == 1
    assert yuklenen[0].durum == KararDurumu.KABUL_EDILDI


def test_karar_ekle_veya_guncelle_yeniyi_ekler(tmp_path):
    kararlari_kaydet(str(tmp_path), [_karar("x")])
    karar_ekle_veya_guncelle(str(tmp_path), _karar("y"))
    assert {k.karar_id for k in kararlari_yukle(str(tmp_path))} == {"x", "y"}


# ------------------------------------------------------------------
# 2. karar_grafigi_dogrula — DAG + döngü tespiti
# ------------------------------------------------------------------

def test_grafik_dogrula_dongusuz_topolojik_sira_doner():
    kararlar = [
        _karar("A", bagimliliklar=["B"]),
        _karar("B", bagimliliklar=["C"]),
        _karar("C"),
    ]
    sira = karar_grafigi_dogrula(kararlar)
    # C, B'den önce; B, A'dan önce gelmeli (bağımlılıklar önce)
    assert sira.index("C") < sira.index("B") < sira.index("A")


def test_grafik_dogrula_dongu_tespit_edilir():
    """FAULT-INJECTION: A->B->C->A çevrimi kasıtlı kuruldu — gerçek bir
    döngü tespit edilmeli, sessizce yutulmamalı."""
    kararlar = [
        _karar("A", bagimliliklar=["B"]),
        _karar("B", bagimliliklar=["C"]),
        _karar("C", bagimliliklar=["A"]),
    ]
    with pytest.raises(DongusuHatasi):
        karar_grafigi_dogrula(kararlar)


def test_grafik_dogrula_bilinmeyen_bagimlilik_hata():
    kararlar = [_karar("A", bagimliliklar=["YOK_BOYLE_BIR_KARAR"])]
    with pytest.raises(ValueError):
        karar_grafigi_dogrula(kararlar)


def test_grafik_dogrula_bos_liste_bos_sira():
    assert karar_grafigi_dogrula([]) == []


# ------------------------------------------------------------------
# 3. karar_gecersiz_kil — zincirleme geçersizleme
# ------------------------------------------------------------------

def test_gecersiz_kil_dogrudan_bagimlilari_acik_yapar():
    """Kullanıcının senaryosu: A ve C, doğrudan B'ye bağımlı. B geçersiz
    kılınınca hem A hem C otomatik ACIK'a dönmeli; B'nin kendisi ACIK
    DEĞİL, GECERSIZ_KILINDI olarak kalmalı."""
    kararlar = [
        _karar("A", bagimliliklar=["B"], durum=KararDurumu.KABUL_EDILDI),
        _karar("B", durum=KararDurumu.KABUL_EDILDI),
        _karar("C", bagimliliklar=["B"], durum=KararDurumu.KABUL_EDILDI),
    ]

    acilanlar = karar_gecersiz_kil(kararlar, "B", sebep="stackup 4->6 katmana çıktı")

    by_id = {k.karar_id: k for k in kararlar}
    assert by_id["B"].durum == KararDurumu.GECERSIZ_KILINDI
    assert by_id["A"].durum == KararDurumu.ACIK
    assert by_id["C"].durum == KararDurumu.ACIK
    assert set(acilanlar) == {"A", "C"}


def test_gecersiz_kil_dolayli_bagimlilar_da_acik_olur():
    """Zincir: C -> B -> A (C, B'ye; B, A'ya bağımlı). A geçersiz
    kılınınca DOLAYLI bağımlı C de (B üzerinden) ACIK'a dönmeli."""
    kararlar = [
        _karar("A", durum=KararDurumu.KABUL_EDILDI),
        _karar("B", bagimliliklar=["A"], durum=KararDurumu.KABUL_EDILDI),
        _karar("C", bagimliliklar=["B"], durum=KararDurumu.KABUL_EDILDI),
    ]

    acilanlar = karar_gecersiz_kil(kararlar, "A", sebep="konnektör değişti")

    by_id = {k.karar_id: k for k in kararlar}
    assert by_id["A"].durum == KararDurumu.GECERSIZ_KILINDI
    assert by_id["B"].durum == KararDurumu.ACIK
    assert by_id["C"].durum == KararDurumu.ACIK
    assert set(acilanlar) == {"B", "C"}


def test_gecersiz_kil_ilgisiz_karar_etkilenmez():
    kararlar = [
        _karar("A", durum=KararDurumu.KABUL_EDILDI),
        _karar("B", bagimliliklar=["A"], durum=KararDurumu.KABUL_EDILDI),
        _karar("ILGISIZ", durum=KararDurumu.KABUL_EDILDI),
    ]
    karar_gecersiz_kil(kararlar, "A", sebep="x")
    by_id = {k.karar_id: k for k in kararlar}
    assert by_id["ILGISIZ"].durum == KararDurumu.KABUL_EDILDI


def test_gecersiz_kil_bilinmeyen_id_hata():
    with pytest.raises(KeyError):
        karar_gecersiz_kil([_karar("A")], "YOK", sebep="x")


# ------------------------------------------------------------------
# 4. promotion kapısı yardımcısı
# ------------------------------------------------------------------

def test_kabul_edilmemis_kararlari_bul_hepsi_kabulse_bos():
    kararlar = [_karar("A", durum=KararDurumu.KABUL_EDILDI), _karar("B", durum=KararDurumu.KABUL_EDILDI)]
    assert kabul_edilmemis_kararlari_bul(kararlar) == []


def test_kabul_edilmemis_kararlari_bul_acik_olani_yakalar():
    kararlar = [_karar("A", durum=KararDurumu.KABUL_EDILDI), _karar("B", durum=KararDurumu.ACIK)]
    sonuc = kabul_edilmemis_kararlari_bul(kararlar)
    assert [k.karar_id for k in sonuc] == ["B"]


def test_kabul_edilmemis_kararlari_bul_kanit_bekliyor_da_yakalanir():
    kararlar = [_karar("A", durum=KararDurumu.KANIT_BEKLIYOR)]
    assert len(kabul_edilmemis_kararlari_bul(kararlar)) == 1
