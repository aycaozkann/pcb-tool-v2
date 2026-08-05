"""pcb_carpisma_radari.py için test suite.
Çalıştırmak için:  pytest -v test_pcb_carpisma_radari.py

`komponent_sinir_kutularini_al()` gerçek `pcbnew` modülünü import ETMEZ
(duck typing) — bu yüzden aşağıdaki `SahteBBox`/`SahteFootprint`/`SahteBoard`
mock sınıflarıyla, bu ortamda GERÇEK `pcbnew` kurulu OLMASA BİLE test
edilebilir (Görev 4'ün istediği "mock nesneleri kullanarak" testi budur).
`carpisma_json_uret()` (gerçek `pcbnew.LoadBoard()` çağıran CLI sarmalayıcı)
BU test dosyasına DAHİL EDİLMEDİ — `mcad_carpisma_koprusu.py`'nin
`step_disa_aktar()` ile ilgili aynı disiplini izler: gerçek dosya G/Ç'si
gerektiren ince katman, SENİN makinende elle doğrulanmalıdır.
"""

import pytest

from bulgu_sozlesmesi import BulguDurumu

from pcb_carpisma_radari import (
    IzEngeli,
    SinirKutusu,
    carpisan_ciftleri_bul,
    carpisma_radari_tara,
    kart_disina_tasmayi_bul,
    kart_sinir_kutusunu_al,
    komponent_sinir_kutularini_al,
    kutular_carpisiyor_mu,
    nokta_segmente_dik_mesafe,
    oz_testleri_calistir,
)

NM_PER_MM = 1_000_000


# ------------------------------------------------------------------
# Mock nesneler — pcbnew.BOARD/FOOTPRINT/BOX2I arayüzünü taklit eder
# ------------------------------------------------------------------

class SahteBBox:
    """`pcbnew.BOX2I` taklidi — tüm değerler NANOMETRE (pcbnew'in iç birimi)."""

    def __init__(self, sol_mm, ust_mm, sag_mm, alt_mm):
        self._sol = int(round(sol_mm * NM_PER_MM))
        self._ust = int(round(ust_mm * NM_PER_MM))
        self._sag = int(round(sag_mm * NM_PER_MM))
        self._alt = int(round(alt_mm * NM_PER_MM))

    def GetLeft(self):
        return self._sol

    def GetTop(self):
        return self._ust

    def GetRight(self):
        return self._sag

    def GetBottom(self):
        return self._alt


class SahteFootprint:
    def __init__(self, ref, bbox_mm):
        self._ref = ref
        self._bbox = SahteBBox(*bbox_mm)

    def GetReference(self):
        return self._ref

    def GetBoundingBox(self, aggregate=False, texts=False):
        # TUZAK (b) regresyon testi: çağıran taraf HER ZAMAN (False, False)
        # geçmeli — yanlışlıkla True geçilirse burada yakalanır.
        assert aggregate is False and texts is False, (
            "GetBoundingBox(False, False) ile çağrılmalı (silkscreen HARİÇ)"
        )
        return self._bbox


class SahteBoard:
    def __init__(self, footprints):
        self._footprints = footprints

    def GetFootprints(self):
        return self._footprints


# ------------------------------------------------------------------
# 1. Mock ile gerçek çıkarım
# ------------------------------------------------------------------

class TestKomponentSinirKutulariniAl:
    def test_tek_komponent_dogru_cevrilir(self):
        board = SahteBoard([SahteFootprint("U1", (0.0, 0.0, 2.0, 1.0))])
        kutular = komponent_sinir_kutularini_al(board)
        assert set(kutular) == {"U1"}
        assert kutular["U1"].x_min == pytest.approx(0.0)
        assert kutular["U1"].x_max == pytest.approx(2.0)
        assert kutular["U1"].genislik == pytest.approx(2.0)

    def test_birden_fazla_komponent(self):
        board = SahteBoard([
            SahteFootprint("U1", (0.0, 0.0, 2.0, 2.0)),
            SahteFootprint("C3", (5.0, 5.0, 6.0, 6.0)),
        ])
        kutular = komponent_sinir_kutularini_al(board)
        assert len(kutular) == 2
        assert "C3" in kutular

    def test_bbox_false_false_ile_cagrilir_yoksa_assertion(self):
        # SahteFootprint.GetBoundingBox kendi içinde (False, False) kontrolü
        # yapıyor; komponent_sinir_kutularini_al bunu doğru çağırmazsa patlar.
        board = SahteBoard([SahteFootprint("D2", (0.0, 0.0, 1.0, 0.5))])
        kutular = komponent_sinir_kutularini_al(board)  # patlamamalı
        assert kutular["D2"].yukseklik == pytest.approx(0.5)


# ------------------------------------------------------------------
# 2. Saf geometri — çakışma tespiti
# ------------------------------------------------------------------

class TestKutularCarpisiyorMu:
    def test_ayrik_kutular_none_doner(self):
        a = SinirKutusu("U1", 0, 0, 2, 2)
        b = SinirKutusu("C3", 5, 5, 6, 6)
        assert kutular_carpisiyor_mu(a, b) is None

    def test_kenar_kenar_temas_carpisma_sayilmaz(self):
        a = SinirKutusu("U1", 0, 0, 2, 2)
        b = SinirKutusu("U2", 2, 0, 4, 2)
        assert kutular_carpisiyor_mu(a, b) is None

    def test_gercek_carpisma_dogru_miktar(self):
        a = SinirKutusu("U1", 0, 0, 2, 2)
        b = SinirKutusu("C3", 1.2, 0.5, 3.2, 2.5)
        ix, iy = kutular_carpisiyor_mu(a, b)
        assert ix == pytest.approx(0.8)
        assert iy == pytest.approx(1.5)


# ------------------------------------------------------------------
# 3. JSON şeması — Görev 2'nin TAM örneğiyle uyum
# ------------------------------------------------------------------

class TestCarpisanCiftleriBul:
    def test_carpisma_json_semasi_dogru(self):
        kutular = {
            "U1": SinirKutusu("U1", 0, 0, 2, 2),
            "C3": SinirKutusu("C3", 1.2, 0.5, 3.2, 2.5),
        }
        ihlaller = carpisan_ciftleri_bul(kutular)
        assert len(ihlaller) == 1
        ihlal = ihlaller[0]
        assert ihlal["hata_tipi"] == "CARPISMA"
        assert {ihlal["parca_1"], ihlal["parca_2"]} == {"U1", "C3"}
        assert ihlal["ic_ice_gecme_X_mm"] == pytest.approx(0.8)
        assert ihlal["ic_ice_gecme_Y_mm"] == pytest.approx(1.5)
        # tavsiye edilen kaçış, örtüşmeden BÜYÜK olmalı (emniyet payı)
        assert abs(ihlal["tavsiye_edilen_kacis_X_mm"]) > ihlal["ic_ice_gecme_X_mm"]

    def test_carpismayan_parcalar_bos_liste(self):
        kutular = {
            "U1": SinirKutusu("U1", 0, 0, 2, 2),
            "C3": SinirKutusu("C3", 10, 10, 12, 12),
        }
        assert carpisan_ciftleri_bul(kutular) == []

    def test_uc_parcali_karma_senaryo(self):
        # U1-C3 çakışıyor, R1 hiçbirine dokunmuyor
        kutular = {
            "U1": SinirKutusu("U1", 0, 0, 2, 2),
            "C3": SinirKutusu("C3", 1.5, 0, 3.5, 2),
            "R1": SinirKutusu("R1", 20, 20, 21, 21),
        }
        ihlaller = carpisan_ciftleri_bul(kutular)
        assert len(ihlaller) == 1
        assert {ihlaller[0]["parca_1"], ihlaller[0]["parca_2"]} == {"U1", "C3"}


# ------------------------------------------------------------------
# 4. Kart dışına taşma
# ------------------------------------------------------------------

class TestKartDisinaTasmayiBul:
    def test_tasan_parca_tespit_edilir(self):
        kart = SinirKutusu("EDGE_CUTS", 0, 0, 10, 10)
        kutular = {"J1": SinirKutusu("J1", -1.0, 2, 1.0, 4)}
        ihlaller = kart_disina_tasmayi_bul(kutular, kart)
        assert len(ihlaller) == 1
        assert ihlaller[0]["hata_tipi"] == "KART_DISI_TASMA"
        assert ihlaller[0]["parca_2"] is None
        assert ihlaller[0]["ic_ice_gecme_X_mm"] == pytest.approx(1.0)

    def test_kart_icindeki_parca_temiz(self):
        kart = SinirKutusu("EDGE_CUTS", 0, 0, 10, 10)
        kutular = {"R1": SinirKutusu("R1", 1, 1, 2, 2)}
        assert kart_disina_tasmayi_bul(kutular, kart) == []

    def test_her_iki_eksende_tasma(self):
        kart = SinirKutusu("EDGE_CUTS", 0, 0, 10, 10)
        kutular = {"J2": SinirKutusu("J2", -2, -2, 1, 1)}
        ihlaller = kart_disina_tasmayi_bul(kutular, kart)
        assert ihlaller[0]["ic_ice_gecme_X_mm"] == pytest.approx(2.0)
        assert ihlaller[0]["ic_ice_gecme_Y_mm"] == pytest.approx(2.0)


# ------------------------------------------------------------------
# 5. Bulgu sözleşmesi entegrasyonu
# ------------------------------------------------------------------

class TestCarpismaRadariTara:
    def test_bos_liste_kapsam_yok(self):
        bulgu = carpisma_radari_tara({})
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK

    def test_temiz_board_pass(self):
        kutular = {
            "U1": SinirKutusu("U1", 0, 0, 2, 2),
            "C3": SinirKutusu("C3", 10, 10, 12, 12),
        }
        bulgu = carpisma_radari_tara(kutular)
        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.gecti_mi is True

    def test_carpisan_board_fail(self):
        kutular = {
            "U1": SinirKutusu("U1", 0, 0, 2, 2),
            "C3": SinirKutusu("C3", 1, 1, 3, 3),
        }
        bulgu = carpisma_radari_tara(kutular)
        assert bulgu.durum == BulguDurumu.FAIL
        assert len(bulgu.ihlaller) == 1

    def test_kart_disi_tasma_da_dahil_edilir(self):
        kutular = {"J1": SinirKutusu("J1", -1, 2, 1, 4)}
        kart = SinirKutusu("EDGE_CUTS", 0, 0, 10, 10)
        bulgu = carpisma_radari_tara(kutular, kart)
        assert bulgu.durum == BulguDurumu.FAIL
        assert bulgu.ihlaller[0]["hata_tipi"] == "KART_DISI_TASMA"


# ------------------------------------------------------------------
# 6. Fault-injection öz-test paketinin kendisi de yeşil olmalı
# ------------------------------------------------------------------

def test_oz_testleri_temiz():
    hatalar = oz_testleri_calistir()
    assert hatalar == [], f"öz-testler kırıldı: {hatalar}"


# ------------------------------------------------------------------
# 7. kart_sinir_kutusunu_al — pcbnew import edildiği için burada SADECE
#    modülün varlığını/importlanabilirliğini doğrularız (gerçek çağrı
#    pcbnew.Edge_Cuts sabitine ihtiyaç duyar, bu ortamda mevcut değil).
# ------------------------------------------------------------------

def test_kart_sinir_kutusunu_al_pcbnew_gerektirir():
    board = SahteBoard([])
    with pytest.raises(ImportError):
        kart_sinir_kutusunu_al(board)


# ------------------------------------------------------------------
# 8. nokta_segmente_dik_mesafe / IzEngeli — iki aşamalı çarpışma testi
#    (cm4-io-test, 2026-08-05: köşegen izlerin AABB'si gerçek çizgiden
#    çok daha büyük olup boş üçgen alanları yanlışlıkla engelli sayıyordu)
# ------------------------------------------------------------------

def test_nokta_segmente_mesafe_dik_izdusum():
    """Nokta, segmentin ORTASINA dik düşüyorsa mesafe basit dik uzaklık."""
    mesafe = nokta_segmente_dik_mesafe(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
    assert mesafe == pytest.approx(3.0)


def test_nokta_segmente_mesafe_uc_noktaya_kenetlenir():
    """Nokta, segmentin izdüşüm aralığının DIŞINDAYSA en yakın UCA mesafe
    döner (dik izdüşüm değil, sonsuz doğru mesafesi DEĞİL)."""
    mesafe = nokta_segmente_dik_mesafe(-3.0, 4.0, 0.0, 0.0, 10.0, 0.0)
    assert mesafe == pytest.approx(5.0)  # (-3,4) -> (0,0) uzaklığı


def test_nokta_segmente_mesafe_sifir_uzunluklu_segment_nokta_mesafesi():
    """Sıfır uzunluklu segment (via temsili, x1==x2,y1==y2) düz nokta-nokta
    mesafesine düşer."""
    mesafe = nokta_segmente_dik_mesafe(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
    assert mesafe == pytest.approx(5.0)


def test_izengeli_aabb_koseginin_gercek_cizgisinden_cok_daha_buyuk():
    """cm4-io-test'in gerçek bulgusu: 45° köşegen bir izin AABB'si, izin
    KENDİSİNDEN çok daha büyük bir alanı kapsar - narrow-phase bu farkı
    gerçek dik mesafeyle KAPATMALI (AABB içinde ama çizgiden uzak bir
    nokta narrow-phase'te güvenli çıkmalı)."""
    iz = IzEngeli("trk_TEST", 0.0, 0.0, 10.0, 10.0, genislik_mm=0.2)
    # AABB köşesine yakın bir nokta (0.5, 9.5) - AABB İÇİNDE ama gerçek
    # köşegen çizgisinden ÇOK uzak.
    assert 0.0 <= 0.5 <= iz.x_max and 0.0 <= 9.5 <= iz.y_max  # AABB içinde, doğrulama
    mesafe = nokta_segmente_dik_mesafe(0.5, 9.5, iz.x1, iz.y1, iz.x2, iz.y2)
    assert mesafe > iz.genislik_mm / 2.0 + 0.2  # gerçek engel sınırından çok uzak


def test_izengeli_gercekten_cizgi_uzerindeki_nokta_engelli_kalir():
    """Aynı köşegenin gerçek ÜZERİNDEKİ (veya çok yakınındaki) bir nokta
    hâlâ engelli sayılmalı - narrow-phase sadece yanlış-pozitifleri
    iptal eder, gerçek engelleri KAÇIRMAZ."""
    iz = IzEngeli("trk_TEST", 0.0, 0.0, 10.0, 10.0, genislik_mm=0.2)
    mesafe = nokta_segmente_dik_mesafe(5.0, 5.0, iz.x1, iz.y1, iz.x2, iz.y2)
    assert mesafe < 0.01  # tam çizgi üzerinde
