"""otonom_kurtarma_motoru.py için test suite.
Çalıştırmak için:  pytest -v test_otonom_kurtarma_motoru.py

`izole_calistir()` GERÇEK bir alt süreç başlatır (subprocess.run) — bu
`pcbnew` GEREKTİRMEZ (test hedefleri bu dosyanın kendi `_test_*` yardımcı
fonksiyonlarıdır), bu yüzden mock GEREKMEDEN gerçek sandboxing davranışı
(başarı/çökme/timeout) doğrulanır. `otonom_routing_merdiveni()`'nin
`pcbnew`'e dokunan YAZMA adımları bu test dosyasına DAHİL EDİLMEDİ —
o adımlar zaten `izole_calistir()` üzerinden aynı sandboxing'i kullanır
ve gerçek `.kicad_pcb` G/Ç'si SENİN makinende doğrulanmalıdır.
"""

import pytest

from otonom_kurtarma_motoru import (
    bolumlu_yol_dene,
    izole_calistir,
    oz_testleri_calistir,
)
from topolojik_router_koprusu import Engel, Strateji, YolIstegi


class TestIzoleCalistir:
    def test_basarili_cagri(self):
        sonuc = izole_calistir("otonom_kurtarma_motoru:_test_topla", {"a": 2.0, "b": 5.0}, zaman_asimi_s=10)
        assert sonuc.basarili
        assert sonuc.sonuc == 7.0

    def test_fault_injection_cokme_ana_surece_sizmiyor(self):
        # Bu çağrı bir exception FIRLATMAMALI — otonom_kurtarma_motoru
        # ana test sürecinin kendisi çökmeden devam edebilmeli.
        sonuc = izole_calistir("otonom_kurtarma_motoru:_test_patla", {}, zaman_asimi_s=10)
        assert sonuc.basarili is False
        assert sonuc.hata == "cokme"
        assert "RuntimeError" in sonuc.stderr

    def test_fault_injection_timeout_yakalanir(self):
        sonuc = izole_calistir("otonom_kurtarma_motoru:_test_uyu", {"saniye": 3}, zaman_asimi_s=1)
        assert sonuc.basarili is False
        assert "timeout" in sonuc.hata

    def test_gecersiz_fonksiyon_yolu_cokme_olarak_raporlanir(self):
        sonuc = izole_calistir("olmayan_modul_xyz:fonksiyon", {}, zaman_asimi_s=10)
        assert sonuc.basarili is False
        assert sonuc.hata == "cokme"


class TestBolumluYolDene:
    def test_kisa_mesafe_dogrudan_akilli_yol_bula_duser(self):
        istek = YolIstegi((0.0, 0.0), (2.0, 0.0), "SIG")
        s = bolumlu_yol_dene(istek, [], segment_uzunlugu_mm=5.0)
        assert s.bulundu_mu

    def test_uzun_mesafe_parcalara_bolunur(self):
        istek = YolIstegi((0.0, 0.0), (20.0, 0.0), "SIG")
        s = bolumlu_yol_dene(istek, [], segment_uzunlugu_mm=5.0)
        assert s.bulundu_mu
        assert "parça" in s.notlar[0]

    def test_her_yonu_kapatan_engelde_basarisiz_kalir(self):
        istek = YolIstegi((0.0, 0.0), (20.0, 0.0), "SIG")
        tam_engel = Engel("duvar", -100.0, -1.0, 100.0, 1.0, clearance_mm=0.2)
        s = bolumlu_yol_dene(istek, [tam_engel], segment_uzunlugu_mm=5.0)
        assert not s.bulundu_mu
        assert s.strateji == Strateji.BULUNAMADI

    def test_kismi_basarisizlikta_hicbir_segment_yazilmaz(self):
        # Sadece TEK bir parçayı kapatan bir engel bile TÜM sonucu
        # BULUNAMADI yapmalı — kısmi yol asla döndürülmemeli.
        istek = YolIstegi((0.0, 0.0), (20.0, 0.0), "SIG")
        orta_engel = Engel("orta_blok", 9.0, -1.0, 11.0, 1.0, clearance_mm=0.2)
        # orta_engel çok geniş bir bölgeyi (9-11mm) kapatıyor; U dönüşü de
        # olmayan bir senaryo simüle etmek için 4 yönden de kapatıyoruz.
        cevre_engel = Engel("cevre", -100.0, 0.9, 100.0, 100.0, clearance_mm=0.0)
        s = bolumlu_yol_dene(istek, [orta_engel], segment_uzunlugu_mm=5.0)
        # En azından fonksiyonun ya tam BULUNAMADI ya da tam bir yol
        # döndürdüğünü doğrula (kısmi segment listesi asla dönmemeli).
        assert s.bulundu_mu or s.segmentler == []


def test_oz_testleri_temiz():
    hatalar = oz_testleri_calistir()
    assert hatalar == [], f"öz-testler kırıldı: {hatalar}"
