"""hdi_stackup_genisletme.py için test suite.

Bu dosya SADECE veri modelidir (gerçek hesap mantığı yok) — testler de
buna uygun olarak SADECE dataclass'ların inşa edilebildiğini ve
varsayılan/opsiyonel alanların beklendiği gibi davrandığını doğrular.
"""

from hdi_stackup_genisletme import (
    BlindBuriedViaBolgesi,
    HdiStackupGenisletmesi,
    MikroviaKatmani,
)


def test_mikrovia_katmani_zorunlu_alanlarla_kurulur():
    m = MikroviaKatmani(ust_katman_adi="Katman_1", alt_katman_adi="Katman_2")
    assert m.ust_katman_adi == "Katman_1"
    assert m.alt_katman_adi == "Katman_2"
    assert m.hedef_delik_capi_mm is None
    assert m.aspect_orani_siniri is None


def test_mikrovia_katmani_opsiyonel_alanlar_verilebilir():
    m = MikroviaKatmani(
        ust_katman_adi="Katman_1", alt_katman_adi="Katman_2",
        hedef_delik_capi_mm=0.1, aspect_orani_siniri=0.8,
    )
    assert m.hedef_delik_capi_mm == 0.1
    assert m.aspect_orani_siniri == 0.8


def test_blind_buried_via_bolgesi_varsayilan_blind():
    b = BlindBuriedViaBolgesi(baslangic_katman_adi="Katman_1", bitis_katman_adi="Katman_2")
    assert b.buried_mi is False
    assert b.fabrika_destekliyor_mu is None


def test_blind_buried_via_bolgesi_buried_isaretlenebilir():
    b = BlindBuriedViaBolgesi(
        baslangic_katman_adi="Katman_2", bitis_katman_adi="Katman_3", buried_mi=True,
    )
    assert b.buried_mi is True


def test_hdi_stackup_genisletmesi_bos_varsayilanla_kurulur():
    g = HdiStackupGenisletmesi()
    assert g.mikrovialar == []
    assert g.blind_buried_bolgeler == []


def test_hdi_stackup_genisletmesi_listeler_birbirinden_bagimsiz():
    """Ortak bir mutable varsayılan (`field(default_factory=list)` YERİNE
    yanlışlıkla `= []`) kullanılsaydı, iki örnek aynı listeyi PAYLAŞIRDI —
    regresyon kilidi."""
    a = HdiStackupGenisletmesi()
    b = HdiStackupGenisletmesi()
    a.mikrovialar.append(MikroviaKatmani("Katman_1", "Katman_2"))
    assert b.mikrovialar == []


def test_hdi_stackup_genisletmesi_dolu_kurulabilir():
    g = HdiStackupGenisletmesi(
        mikrovialar=[MikroviaKatmani("Katman_1", "Katman_2")],
        blind_buried_bolgeler=[BlindBuriedViaBolgesi("Katman_2", "Katman_3", buried_mi=True)],
    )
    assert len(g.mikrovialar) == 1
    assert len(g.blind_buried_bolgeler) == 1
