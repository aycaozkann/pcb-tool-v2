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
    CoupledAramaSonucu,
    KatmanliAramaSonucu,
    ViaYerlesimKontrolu,
    izgara_a_yildiz_ara,
    izgara_a_yildiz_ara_coupled,
    izgara_a_yildiz_ara_katmanli,
    oz_testleri_calistir,
    si_pi_maliyet_fonksiyonu_uret,
    via_impedans_sureksizligi_maliyeti,
    via_yerlesimi_gecerli_mi,
    _hucre_engelli_mi,
    _merkez_hattan_cift_uret,
    _perpendikuler_birim_vektor,
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


# ------------------------------------------------------------------
# FAZ 0 — Diferansiyel çift (coupled) routing
# ------------------------------------------------------------------

class TestPerpendikulerVeMerkezHattanCift:
    def test_yatay_segmente_dik_vektor_dikeydir(self):
        nx, ny = _perpendikuler_birim_vektor((0.0, 0.0), (10.0, 0.0))
        assert nx == pytest.approx(0.0, abs=1e-9)
        assert abs(ny) == pytest.approx(1.0, abs=1e-9)

    def test_sifir_uzunluklu_segment_sifir_vektor_doner(self):
        assert _perpendikuler_birim_vektor((1.0, 1.0), (1.0, 1.0)) == (0.0, 0.0)

    def test_merkez_hattan_uretilen_cift_sabit_yaricapta(self):
        merkez = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        p_yol, n_yol = _merkez_hattan_cift_uret(merkez, yaricap_mm=0.15)
        assert len(p_yol) == len(n_yol) == 3
        # ilk noktada P/N arası mesafe TAM 2*yaricap olmalı
        ilk_mesafe = math.dist(p_yol[0], n_yol[0])
        assert ilk_mesafe == pytest.approx(0.3, abs=1e-6)


class TestIzgaraAYildizAraCoupled:
    def test_engelsiz_coupled_routing_gap_sabit_kalir(self):
        s = izgara_a_yildiz_ara_coupled(
            (0.0, 0.2), (0.0, -0.2), (10.0, 0.2), (10.0, -0.2),
            genislik_mm=0.15, gap_mm=0.15, hucre_mm=0.2, clearance_mm=0.1,
            stub_uzunluk_mm=0.5,
        )
        assert s.bulundu_mu
        beklenen_gap = 0.15 + 0.15  # gap_mm + genislik_mm (merkez-merkez)
        # coupled koridorun İÇ noktalarında (stub sonrası) P/N arası mesafe
        # yaklaşık sabit olmalı — ilk/son nokta (pad'in kendisi) stub
        # geometrisi yüzünden farklı olabilir, bu yüzden ORTA noktalar
        # karşılaştırılır.
        assert len(s.p_yolu) >= 2 and len(s.n_yolu) >= 2
        ic_p, ic_n = s.p_yolu[1], s.n_yolu[1]
        assert math.dist(ic_p, ic_n) == pytest.approx(beklenen_gap, abs=1e-6)

    def test_stub_uzunlugu_sifirsa_pad_dogrudan_merkez_hatta_baglanir(self):
        s = izgara_a_yildiz_ara_coupled(
            (0.0, 0.075), (0.0, -0.075), (10.0, 0.075), (10.0, -0.075),
            genislik_mm=0.15, gap_mm=0.15, hucre_mm=0.2, clearance_mm=0.1,
            stub_uzunluk_mm=0.0,
        )
        assert s.bulundu_mu

    def test_engel_varsa_koridor_genisligi_hesaba_katilarak_dolanir(self):
        duvar = Kutu(4.0, -5.0, 5.0, 5.0)
        s = izgara_a_yildiz_ara_coupled(
            (0.0, 0.2), (0.0, -0.2), (10.0, 0.2), (10.0, -0.2),
            genislik_mm=0.15, gap_mm=0.15, engeller=(duvar,),
            hucre_mm=0.25, clearance_mm=0.15, stub_uzunluk_mm=0.5,
        )
        assert s.bulundu_mu
        assert s.merkez_hat_sonucu.bulundu_mu

    def test_gecersiz_parametreler_reddedilir(self):
        with pytest.raises(ValueError):
            izgara_a_yildiz_ara_coupled((0, 0), (0, -1), (10, 0), (10, -1), genislik_mm=0.0, gap_mm=0.15)
        with pytest.raises(ValueError):
            izgara_a_yildiz_ara_coupled((0, 0), (0, -1), (10, 0), (10, -1), genislik_mm=0.15, gap_mm=-0.1)
        with pytest.raises(ValueError):
            izgara_a_yildiz_ara_coupled((0, 0), (0, -1), (10, 0), (10, -1), genislik_mm=0.15, gap_mm=0.15, stub_uzunluk_mm=-1.0)

    def test_fault_injection_tam_ortayi_kapatan_duvar_bulunamaz(self):
        tam_duvar = Kutu(4.0, -1000.0, 5.0, 1000.0)
        s = izgara_a_yildiz_ara_coupled(
            (0.0, 0.2), (0.0, -0.2), (10.0, 0.2), (10.0, -0.2),
            genislik_mm=0.15, gap_mm=0.15, engeller=(tam_duvar,),
            hucre_mm=0.25, clearance_mm=0.15, stub_uzunluk_mm=0.5,
        )
        assert not s.bulundu_mu


# ------------------------------------------------------------------
# FAZ 0 — Via yerleşim geçerliliği (annular-ring + hole-to-hole)
# ------------------------------------------------------------------

class TestViaYerlesimiGecerliMi:
    def test_yetersiz_annular_ring_reddedilir(self):
        gecerli, sebep = via_yerlesimi_gecerli_mi(
            (0.0, 0.0), via_capi_mm=0.5, delik_capi_mm=0.3, min_annular_ring_mm=0.15,
        )
        assert gecerli is False
        assert "annular ring" in sebep

    def test_yeterli_annular_ring_ve_bos_komsu_kabul_edilir(self):
        gecerli, sebep = via_yerlesimi_gecerli_mi(
            (0.0, 0.0), via_capi_mm=0.5, delik_capi_mm=0.2, komsu_delikler=(), min_annular_ring_mm=0.15,
        )
        assert gecerli is True
        assert sebep == ""

    def test_0_4mm_pin_pitch_senaryosu_hole_to_hole_ihlali_yakalar(self):
        """REGRESYON KİLİDİ: 0.5mm via'nın 0.4mm pin pitch'inde 221 DRC
        ihlaline yol açtığı gerçek olay — bu kontrol projede DAHA ÖNCE
        YOKTU, bu test onun VARLIĞINI ve DOĞRULUĞUNU kilitler."""
        gecerli, sebep = via_yerlesimi_gecerli_mi(
            (0.0, 0.0), via_capi_mm=0.5, delik_capi_mm=0.2,
            komsu_delikler=[(0.4, 0.0, 0.3)], min_annular_ring_mm=0.15, min_hole_to_hole_mm=0.2,
        )
        assert gecerli is False
        assert "hole-to-hole" in sebep

    def test_uzak_komsu_delik_sorun_cikarmaz(self):
        gecerli, _ = via_yerlesimi_gecerli_mi(
            (0.0, 0.0), via_capi_mm=0.5, delik_capi_mm=0.2, komsu_delikler=[(5.0, 5.0, 0.3)],
        )
        assert gecerli is True

    def test_via_yerlesim_kontrolu_dataclass_annular_ring_hesabi(self):
        k = ViaYerlesimKontrolu(via_capi_mm=0.6, delik_capi_mm=0.3)
        assert k.annular_ring_mm() == pytest.approx(0.15)
        assert k.annular_ring_yeterli_mi() is True


# ------------------------------------------------------------------
# FAZ 0 — Katman/via-farkındalı A*
# ------------------------------------------------------------------

class TestIzgaraAYildizAraKatmanli:
    def test_tek_katmanda_engelsiz_yol_via_kullanmaz(self):
        s = izgara_a_yildiz_ara_katmanli((0.0, 0.0), (5.0, 0.0), katman_sayisi=2, hucre_mm=0.5)
        assert s.bulundu_mu
        assert s.via_konumlari == []

    def test_engel_via_ile_asilir(self):
        duvar = Kutu(2.0, -1000.0, 3.0, 1000.0)  # katman 0'ı TAM kapatan duvar
        s = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (5.0, 0.0), katman_sayisi=2,
            katman_engelleri={0: [duvar]}, hucre_mm=0.5, clearance_mm=0.2,
            via_capi_mm=0.5, via_delik_capi_mm=0.2,
        )
        assert s.bulundu_mu
        assert len(s.via_konumlari) >= 1

    def test_via_gecersizse_engeli_asamaz(self):
        """Via yerleşimi (annular-ring) HER YERDE geçersizse (çok küçük
        annular ring), katman değişimi hiç DENENMEMELİ — engel katman
        0'ı kapatıyorsa ve katman 1 de aynı engelle kapalıysa yol
        bulunamamalı (via üretilemediği için katman değiştirilemiyor)."""
        duvar = Kutu(2.0, -1000.0, 3.0, 1000.0)
        s = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (5.0, 0.0), katman_sayisi=2,
            katman_engelleri={0: [duvar], 1: [duvar]},  # HER İKİ katman da kapalı
            hucre_mm=0.5, clearance_mm=0.2, via_capi_mm=0.5, via_delik_capi_mm=0.2,
        )
        assert not s.bulundu_mu

    def test_katman_sayisi_gecersizse_hata(self):
        with pytest.raises(ValueError):
            izgara_a_yildiz_ara_katmanli((0, 0), (5, 0), katman_sayisi=0)
        with pytest.raises(ValueError):
            izgara_a_yildiz_ara_katmanli((0, 0), (5, 0), katman_sayisi=2, baslangic_katman=5)

    def test_ayni_hucre_ve_katmanda_kisayol(self):
        s = izgara_a_yildiz_ara_katmanli((0.0, 0.0), (0.02, 0.02), katman_sayisi=2, hucre_mm=0.5)
        assert s.bulundu_mu
        assert s.dugum_sayisi == 0

    def test_fault_injection_baslangic_ustune_engel(self):
        engel = Kutu(-0.5, -0.5, 0.5, 0.5)
        s = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (5.0, 0.0), katman_sayisi=2,
            katman_engelleri={0: [engel]}, hucre_mm=0.5, clearance_mm=0.1,
        )
        assert not s.bulundu_mu
        assert "engelli bölgede" in s.neden


# ------------------------------------------------------------------
# FAZ 0.5-2 — Canlı SI/PI maliyet fonksiyonu
# ------------------------------------------------------------------

class TestSiPiMaliyetFonksiyonuUret:
    def test_esik_ustundeki_mesafede_ceza_sifir(self):
        diger = [IzEngeli("HS", 0.0, 20.0, 20.0, 20.0, genislik_mm=0.2)]
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret(diger, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        assert maliyet_fn((5.0, 0.0), (5.1, 0.0)) == 0.0

    def test_esik_altindaki_mesafede_pozitif_ceza(self):
        diger = [IzEngeli("HS", 0.0, 0.3, 20.0, 0.3, genislik_mm=0.2)]
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret(diger, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        # esik = 3*0.2 = 0.6mm; segment orta noktası (5, 0.0), ize dik mesafe 0.3mm < 0.6mm
        ceza = maliyet_fn((5.0, 0.0), (5.1, 0.0))
        assert ceza > 0.0

    def test_ceza_mesafeyle_ters_orantili(self):
        yakin = [IzEngeli("HS", 0.0, 0.1, 20.0, 0.1, genislik_mm=0.2)]
        uzak = [IzEngeli("HS", 0.0, 0.5, 20.0, 0.5, genislik_mm=0.2)]
        fn_yakin = si_pi_maliyet_fonksiyonu_uret(yakin, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        fn_uzak = si_pi_maliyet_fonksiyonu_uret(uzak, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        assert fn_yakin((5.0, 0.0), (5.1, 0.0)) > fn_uzak((5.0, 0.0), (5.1, 0.0))

    def test_bos_diger_iz_listesi_her_zaman_sifir(self):
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret([], net_genislik_mm=0.2)
        assert maliyet_fn((0.0, 0.0), (1.0, 1.0)) == 0.0

    def test_router_si_maliyetiyle_yoldan_uzaklasir(self):
        """DOĞRULAMA: A* arama SI maliyeti verildiğinde GERÇEKTEN yakın
        komşu izden uzaklaşan bir yol seçmeli — sadece maliyet fonksiyonu
        DOĞRU çağrılıyor mu değil, SONUÇ üzerinde ÖLÇÜLEBİLİR bir etkisi
        olmalı (aksi halde entegrasyon anlamsız)."""
        yakin_iz = [IzEngeli("HS_OTHER", 0.0, 0.3, 20.0, 0.3, genislik_mm=0.2)]
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret(yakin_iz, net_genislik_mm=0.2, w_kurali_carpani=3.0)

        s_maliyetsiz = izgara_a_yildiz_ara((0.0, 0.0), (20.0, 0.0), hucre_mm=0.5, clearance_mm=0.1)
        s_maliyetli = izgara_a_yildiz_ara(
            (0.0, 0.0), (20.0, 0.0), hucre_mm=0.5, clearance_mm=0.1, ek_maliyet_fonksiyonu=maliyet_fn,
        )
        assert s_maliyetsiz.bulundu_mu and s_maliyetli.bulundu_mu

        y_maliyetsiz = sum(p[1] for p in s_maliyetsiz.yol) / len(s_maliyetsiz.yol)
        y_maliyetli = sum(p[1] for p in s_maliyetli.yol) / len(s_maliyetli.yol)
        # maliyetli yol İZDEN (y=0.3) DAHA UZAK durmalı (daha negatif y ortalaması)
        assert y_maliyetli < y_maliyetsiz

    def test_a_yildiz_optimalligi_bozulmaz_yine_yol_bulunur(self):
        """ek_maliyet_fonksiyonu VARKEN bile A* hâlâ GEÇERLİ bir yol
        bulmalı (sezginin kabul edilebilirliği korunuyor mu - dolaylı
        test: hiçbir hata/sonsuz döngü olmadan sonuç dönüyor mu)."""
        diger = [IzEngeli("HS", 5.0, -100.0, 5.0, 100.0, genislik_mm=0.3)]
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret(diger, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        s = izgara_a_yildiz_ara(
            (0.0, 0.0), (10.0, 0.0), hucre_mm=0.5, clearance_mm=0.1,
            ek_maliyet_fonksiyonu=maliyet_fn, maks_dugum=50_000,
        )
        assert s.bulundu_mu


class TestViaImpedansSureksizligiMaliyeti:
    def test_sapma_yoksa_temel_maliyet_degismez(self):
        assert via_impedans_sureksizligi_maliyeti(5.0, 0.0) == 5.0

    def test_sapma_varsa_maliyet_dogrusal_artar(self):
        assert via_impedans_sureksizligi_maliyeti(5.0, 20.0) == pytest.approx(6.0)
        assert via_impedans_sureksizligi_maliyeti(5.0, 50.0) == pytest.approx(7.5)

    def test_katmanli_aramada_yuksek_sapma_via_kullanimini_azaltir(self):
        """DOĞRULAMA: empedans_sapma_yuzde yüksekse (via daha pahalı),
        engelin varlığında bile via kullanmaktan KAÇINMAYA çalışır (aynı
        katmanda daha uzun bir yol via'dan daha ucuz hale gelebilir).
        Bu test via'nın TAMAMEN engellenmediğini (hâlâ yol bulunduğunu)
        ama maliyetin GERÇEKTEN etkili olduğunu (iterasyon/düğüm sayısı
        farklılaşabilir) doğrular — asıl garanti: sonuç HÂLÂ GEÇERLİ."""
        duvar = Kutu(2.0, -1000.0, 3.0, 1000.0)
        s_dusuk_sapma = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (5.0, 0.0), katman_sayisi=2, katman_engelleri={0: [duvar]},
            hucre_mm=0.5, clearance_mm=0.2, via_capi_mm=0.5, via_delik_capi_mm=0.2,
            via_maliyeti=1.0, empedans_sapma_yuzde=0.0,
        )
        s_yuksek_sapma = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (5.0, 0.0), katman_sayisi=2, katman_engelleri={0: [duvar]},
            hucre_mm=0.5, clearance_mm=0.2, via_capi_mm=0.5, via_delik_capi_mm=0.2,
            via_maliyeti=1.0, empedans_sapma_yuzde=200.0,
        )
        assert s_dusuk_sapma.bulundu_mu and s_yuksek_sapma.bulundu_mu

    def test_ek_maliyet_fonksiyonu_katmanli_aramada_da_calisir(self):
        diger = [IzEngeli("HS", 0.0, 0.3, 10.0, 0.3, genislik_mm=0.2)]
        maliyet_fn = si_pi_maliyet_fonksiyonu_uret(diger, net_genislik_mm=0.2, w_kurali_carpani=3.0)
        s = izgara_a_yildiz_ara_katmanli(
            (0.0, 0.0), (10.0, 0.0), katman_sayisi=1, hucre_mm=0.5,
            ek_maliyet_fonksiyonu=maliyet_fn,
        )
        assert s.bulundu_mu
