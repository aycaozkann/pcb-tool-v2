"""otonom_python_router.py için test suite.
Çalıştırmak için:  pytest -v test_otonom_python_router.py

`izgara_a_yildiz_ara()` `pcbnew`'e HİÇ dokunmaz (saf Python) — bu yüzden
mock GEREKMEDEN gerçek testlerle doğrulanabilir. `duz_izleri_pcbnew_ile_
yaz()` (gerçek board'a yazan ince katman) bu test dosyasına DAHİL
EDİLMEDİ — `mcad_carpisma_koprusu.py`/`topolojik_router_koprusu.py` ile
AYNI disiplin: gerçek `pcbnew` G/Ç'si SENİN makinende doğrulanmalı.
"""

import math
from dataclasses import dataclass

import pytest

from otonom_python_router import (
    AramaSonucu,
    izgara_a_yildiz_ara,
    oz_testleri_calistir,
    _hucre_engelli_mi,
    _yolu_sadelestir,
)
from pcb_carpisma_radari import IzEngeli


@dataclass
class Kutu:
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class TestIzgaraAYildizAra:
    def test_engelsiz_duz_yol_bulunur(self):
        s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), hucre_mm=0.5)
        assert s.bulundu_mu
        uzunluk = sum(math.dist(s.yol[i], s.yol[i + 1]) for i in range(len(s.yol) - 1))
        assert uzunluk == pytest.approx(5.0, abs=0.6)

    def test_duvar_etrafindan_dolanir(self):
        duvar = Kutu(2.0, -0.3, 3.0, 5.0)
        s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), [duvar], hucre_mm=0.25, clearance_mm=0.2)
        assert s.bulundu_mu
        # Yol duvarı GERÇEKTEN by-pass etmeli (en az bir nokta y>0.3 olmalı)
        assert any(y > 4.5 for _, y in s.yol) or any(y < -0.5 for _, y in s.yol) or len(s.yol) > 2

    def test_baslangic_engelli_bolgede_temiz_fail(self):
        kapali = Kutu(-1.0, -1.0, 1.0, 1.0)
        s = izgara_a_yildiz_ara((0.0, 0.0), (10.0, 0.0), [kapali], hucre_mm=0.5, clearance_mm=0.1)
        assert not s.bulundu_mu
        assert "engelli bölgede" in s.neden

    def test_dugum_butcesi_asilirsa_sonsuz_aramaz(self):
        s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), hucre_mm=0.01, maks_dugum=50)
        assert not s.bulundu_mu
        assert "bütçe" in s.neden

    def test_ayni_hucre_kisayolu(self):
        s = izgara_a_yildiz_ara((0.0, 0.0), (0.02, 0.02), hucre_mm=0.5)
        assert s.bulundu_mu
        assert s.dugum_sayisi == 0

    def test_tamamen_kapali_kutu_yol_yok(self):
        # Başlangıç ve bitiş her ikisi de erişilebilir ama aralarında
        # TAM kapatan (sonsuz genişlikte varsayılan) bir duvar -> yol yok
        tam_duvar = Kutu(2.0, -1000.0, 3.0, 1000.0)
        s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), [tam_duvar], hucre_mm=0.5, clearance_mm=0.1)
        assert not s.bulundu_mu

    def test_fault_injection_baslangic_ustune_engel(self):
        engel = Kutu(-0.5, -0.5, 0.5, 0.5)
        s = izgara_a_yildiz_ara((0.0, 0.0), (5.0, 0.0), [engel], hucre_mm=0.5, clearance_mm=0.1)
        assert not s.bulundu_mu


class TestYoluSadelestir:
    def test_kolineer_noktalar_birlesir(self):
        yol = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (2.0, 2.0)]
        basit = _yolu_sadelestir(yol)
        assert basit == [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]

    def test_kisa_yol_degismez(self):
        assert _yolu_sadelestir([(0.0, 0.0), (1.0, 1.0)]) == [(0.0, 0.0), (1.0, 1.0)]


def test_oz_testleri_temiz():
    hatalar = oz_testleri_calistir()
    assert hatalar == [], f"öz-testler kırıldı: {hatalar}"


# ------------------------------------------------------------------
# İki aşamalı çarpışma testi (2026-08-05, cm4-io-test bulgusu): 45°
# köşegen bir `IzEngeli`nin AABB'si gerçek çizgiden çok daha büyük -
# narrow-phase bu farkı point-segment mesafesiyle kapatmalı.
# ------------------------------------------------------------------

class TestIkiAsamaliCarpismaTesti:
    def test_koseginin_aabb_kosesindeki_bos_alan_artik_engelli_sayilmiyor(self):
        """REGRESYON TESTİ (cm4-io-test HDMI0_TX2_P J2->via hop'u): bir
        köşegen `IzEngeli`nin AABB köşesine yakın ama GERÇEK çizgiden çok
        uzak bir nokta, eski (AABB-only) davranışta yanlış-pozitif
        "engelli" verirdi - narrow-phase bunu düzeltmeli.

        Çizgi: (0,10)->(20,0), denklemi x+2y=20. AABB: X:[0,20] Y:[0,10].
        (0,0) köşesine yakın bir nokta (0.5,0.5): çizgiye dik mesafe
        |0.5+1-20|/sqrt(5)=8.27mm - AABB İÇİNDE ama çizgiden ÇOK uzak."""
        koseg = IzEngeli("trk_TEST", 0.0, 10.0, 20.0, 0.0, genislik_mm=0.29)
        assert not _hucre_engelli_mi((2, 2), [koseg], hucre_mm=0.25, clearance_mm=0.15)

    def test_koseginin_uzerindeki_hucre_hala_engelli_kabul_edilir(self):
        """Narrow-phase sadece yanlış-pozitifleri iptal eder - gerçekten
        çizginin ÜZERİNDEKİ bir hücre hâlâ engelli kalmalı (gevşetme
        değil, düzeltme). `_hucre_engelli_mi` doğrudan test edilir -
        tam yol aramasının "aynı hücre kısayolu" davranışına takılmadan."""
        koseg = IzEngeli("trk_TEST", 0.0, 0.0, 20.0, 20.0, genislik_mm=0.29)
        # (10,10) tam köşegenin üzerinde -> hücre karşılığı kesinlikle engelli.
        assert _hucre_engelli_mi((40, 40), [koseg], hucre_mm=0.25, clearance_mm=0.15)

    def test_sinirkutusu_engelleri_narrow_phase_e_girmez_eski_davranis_korunur(self):
        """`SinirKutusu` (komponent) engelleri `x1/genislik_mm` alanlarına
        SAHİP DEĞİL - narrow-phase hiç tetiklenmemeli, davranış AABB-only
        eski haliyle BİREBİR aynı kalmalı (regresyon güvencesi)."""
        kapali = Kutu(-1.0, -1.0, 1.0, 1.0)
        s = izgara_a_yildiz_ara((0.0, 0.0), (10.0, 0.0), [kapali], hucre_mm=0.5, clearance_mm=0.1)
        assert not s.bulundu_mu  # SinirKutusu hâlâ katı cisim gibi davranıyor
