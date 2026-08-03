"""
bom_lifecycle_koprusu.py için test suite.
NOT: `nexar_sorgula` gerçek ağ/API key gerektirdiği için burada sadece
placeholder (api_key=None) davranışı test edilir — gerçek entegrasyon
gerçek bir Nexar hesabıyla ayrıca doğrulanmalı.
"""

import pytest

from bom_lifecycle_koprusu import (
    BomSatiri,
    TedarikVerisi,
    LifecycleDurumu,
    nexar_sorgula,
    validate_bom_lifecycle,
    risk_skoru_hesapla,
    lifecycle_raporu_olustur,
    AlternatifAday,
    find_pin_compatible,
    alternatif_karari_ozetle,
)


def test_nexar_sorgula_api_key_yoksa_tbd_doner_uydurmaz():
    sonuc = nexar_sorgula("HERHANGI_BIR_MPN")
    assert sonuc.kaynak == "TBD"
    assert sonuc.lifecycle == LifecycleDurumu.BILINMIYOR
    assert sonuc.toplam_stok is None


def test_nexar_sorgula_api_key_varsa_gercek_entegrasyon_gerektigini_belirtir():
    with pytest.raises(NotImplementedError):
        nexar_sorgula("MPN", api_key="sahte-key")


def test_validate_bom_lifecycle_her_satiri_sorgular():
    bom = [BomSatiri(refdes="U1", mpn="A"), BomSatiri(refdes="U2", mpn="B")]
    sonuc = validate_bom_lifecycle(bom)
    assert set(sonuc.keys()) == {"A", "B"}


def test_risk_skoru_active_ve_bol_stok_dusuk():
    satir = BomSatiri(refdes="R1", mpn="X")
    tedarik = TedarikVerisi(mpn="X", lifecycle=LifecycleDurumu.ACTIVE, toplam_stok=100000, tedarikci_sayisi=5, lead_time_gun=10, kaynak="nexar")
    risk = risk_skoru_hesapla(satir, tedarik)
    assert risk.skor == 0.0
    assert risk.alternatif_aranmali_mi is False


def test_risk_skoru_eol_single_source_yuksek():
    satir = BomSatiri(refdes="U3", mpn="OLD", kritik=True)
    tedarik = TedarikVerisi(mpn="OLD", lifecycle=LifecycleDurumu.EOL, toplam_stok=50, tedarikci_sayisi=1, lead_time_gun=300, kaynak="nexar")
    risk = risk_skoru_hesapla(satir, tedarik)
    assert risk.skor > 1.0
    assert risk.alternatif_aranmali_mi is True
    assert "single-source" in " ".join(risk.nedenler)


def test_lifecycle_raporu_en_riskliden_siralar():
    bom = [BomSatiri(refdes="U1", mpn="A"), BomSatiri(refdes="U2", mpn="B")]
    tedarik = {
        "A": TedarikVerisi(mpn="A", lifecycle=LifecycleDurumu.ACTIVE, tedarikci_sayisi=5),
        "B": TedarikVerisi(mpn="B", lifecycle=LifecycleDurumu.EOL, tedarikci_sayisi=1),
    }
    rapor = lifecycle_raporu_olustur(bom, tedarik)
    assert rapor[0].mpn == "B"  # en riskli önce


def test_find_pin_compatible_sadece_gercekten_uyumlu_olani_secer():
    orijinal = BomSatiri(refdes="U3", mpn="OLD")
    adaylar = [
        AlternatifAday("AYNI_PAKET_FARKLI_PINOUT", True, False, True, False),
        AlternatifAday("GERCEK_UYUMLU", True, True, True, False),
        AlternatifAday("ELEKTRIKSEL_UYMUYOR", True, True, False, False),
    ]
    uygun = find_pin_compatible(orijinal, adaylar)
    assert [a.mpn for a in uygun] == ["GERCEK_UYUMLU"]


def test_alternatif_karari_ozetle_dusuk_riskte_aranmaz():
    from bom_lifecycle_koprusu import RiskSkoru
    orijinal = BomSatiri(refdes="R1", mpn="X")
    risk = RiskSkoru(mpn="X", skor=0.1)
    ozet = alternatif_karari_ozetle(orijinal, risk, [])
    assert "aranmadı" in ozet


def test_alternatif_karari_ozetle_yuksek_risk_uygun_yoksa_needs_human():
    from bom_lifecycle_koprusu import RiskSkoru
    orijinal = BomSatiri(refdes="U3", mpn="OLD")
    risk = RiskSkoru(mpn="OLD", skor=0.9, nedenler=["lifecycle=EOL"])
    ozet = alternatif_karari_ozetle(orijinal, risk, [])
    assert "NEEDS_HUMAN" in ozet


def test_alternatif_karari_ozetle_footprint_degisirse_feedback_notu_ekler():
    from bom_lifecycle_koprusu import RiskSkoru
    orijinal = BomSatiri(refdes="U3", mpn="OLD")
    risk = RiskSkoru(mpn="OLD", skor=0.9, nedenler=["lifecycle=EOL"])
    aday = AlternatifAday("YENI", True, True, True, footprint_degisiyor=True)
    ozet = alternatif_karari_ozetle(orijinal, risk, [aday])
    assert "feedback" in ozet
