"""topolojik_router_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_topolojik_router_koprusu.py

NOT: `pcbnew` bu ortamda kurulu değil — `TopolojikRouter.iz_yaz()` yolu
gerçek KiCad'de doğrulanmalı. Aşağıdaki testler geometri/karar motorunu
(gerçek işi yapan kısmı) tam olarak kapsar.
"""

import math

import pytest

from bulgu_sozlesmesi import BulguDurumu

from topolojik_router_koprusu import (
    Engel,
    Iz,
    Strateji,
    TopolojikRouter,
    YolIstegi,
    YolSonucu,
    akilli_yol_bul,
    dik_aci_sayisi,
    geometri_kurali_kontrolu,
    itip_kaydir_oner,
    koseleri_45_dereceye_cevir,
    manhattan_mesafe_mm,
    oz_testleri_calistir,
    routing_plan_satiri_uret,
    shove_ozetle,
    via_kurali_kontrolu,
    yol_engelli_mi,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Geometri temelleri
# ------------------------------------------------------------------

def test_manhattan_mesafe():
    assert manhattan_mesafe_mm((0, 0), (3, 4)) == 7.0


def test_engel_clearance_ile_sisiyor():
    e = Engel("pad", 0.0, 0.0, 1.0, 1.0, clearance_mm=0.2)
    assert e.sismis_kutu() == (-0.2, -0.2, 1.2, 1.2)
    assert e.nokta_icinde_mi((1.1, 1.1))
    assert not e.nokta_icinde_mi((1.5, 1.5))


def test_segment_engeli_keserse_yakalanir():
    e = Engel("bariyer", 4.0, -1.0, 6.0, 1.0)
    assert yol_engelli_mi([((0, 0), (10, 0))], [e], 0.2) == ["bariyer"]


def test_engelin_yanindan_gecen_yol_temiz():
    e = Engel("bariyer", 4.0, -1.0, 6.0, 1.0, clearance_mm=0.2)
    assert yol_engelli_mi([((0, 5), (10, 5))], [e], 0.2) == []


def test_iz_genisligi_engel_tespitine_dahil():
    """Merkez hattı kutunun dışından geçse bile GENİŞ bir iz kutuya girer."""
    e = Engel("pad", 0.0, 0.0, 1.0, 1.0, clearance_mm=0.0)
    yol = [((0.5, 1.3), (5.0, 1.3))]
    assert yol_engelli_mi(yol, [e], iz_genisligi_mm=0.2) == []
    assert yol_engelli_mi(yol, [e], iz_genisligi_mm=1.0) == ["pad"]


def test_izin_engel_kutusu_yari_genislik_kadar_genis():
    iz = Iz("T1", (0.0, 0.0), (10.0, 0.0), genislik_mm=0.4, net="SIG")
    e = iz.engel_olarak(clearance_mm=0.0)
    assert (e.x_min, e.y_min, e.x_max, e.y_max) == (-0.2, -0.2, 10.2, 0.2)


# ------------------------------------------------------------------
# Pathfinding merdiveni (CLAUDE.md kuralı)
# ------------------------------------------------------------------

def test_engelsiz_yol_dogrudan_cizilir():
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"))
    assert sonuc.strateji == Strateji.DOGRUDAN
    assert sonuc.uzunluk_mm == 10.0
    assert sonuc.via_sayisi == 0


def test_koseli_hedef_l_donusu_ile_cozulur():
    """Çapraz hedefte doğrudan segment 45°/eğik olur; L dönüşü dik açılıdır."""
    e = Engel("bariyer", 4.0, 4.0, 6.0, 6.0)
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 10), "SIG"), [e])
    assert sonuc.strateji == Strateji.L_DONUSU
    assert len(sonuc.segmentler) == 2


def test_bariyer_etrafindan_u_donusu_ile_dolanir():
    """Hem doğrudan hem iki L dönüşü de engelliyse waypoint'li U dönüşü."""
    engeller = [
        Engel("bariyer", 4.0, -1.0, 6.0, 1.0),
        Engel("kose1", 9.0, -1.0, 11.0, 1.0),
    ]
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 5), "SIG"), engeller)
    assert sonuc.bulundu_mu
    assert sonuc.via_sayisi == 0
    assert yol_engelli_mi(sonuc.segmentler, engeller, 0.2) == []


def test_dolanma_yolu_gercekten_engelsiz():
    """Motor 'buldum' dediği yol, engel testinden GEÇMEK zorunda."""
    engeller = [Engel("blok", 2.0, -3.0, 8.0, 3.0)]
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"), engeller)
    assert sonuc.bulundu_mu
    assert yol_engelli_mi(sonuc.segmentler, engeller, 0.2) == []


def test_tamamen_kapali_yolda_alt_katman_engelleri_verilmezse_via_onerilmez():
    """Alt katman 'boş' VARSAYILMAZ — veri yoksa öneri yok (NEEDS_HUMAN)."""
    duvar = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"), [duvar])
    assert sonuc.strateji == Strateji.BULUNAMADI
    assert any("VARSAYILMADI" in n for n in sonuc.notlar)


def test_alt_katman_bos_verilirse_via_ile_cozulur():
    duvar = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    sonuc = akilli_yol_bul(
        YolIstegi((0, 0), (10, 0), "SIG"), [duvar], alt_katman_engelleri=[]
    )
    assert sonuc.strateji == Strateji.KATMAN_DEGISIMI
    assert sonuc.via_sayisi == 2
    assert sonuc.katmanlar == ["F.Cu", "B.Cu", "F.Cu"]


def test_alt_katman_da_dolu_ise_bulunamadi():
    duvar = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    sonuc = akilli_yol_bul(
        YolIstegi((0, 0), (10, 0), "SIG"), [duvar], alt_katman_engelleri=[duvar]
    )
    assert sonuc.strateji == Strateji.BULUNAMADI
    assert not sonuc.bulundu_mu


def test_yuksek_hizli_net_asla_via_kullanmaz():
    """MASTER_RULEBOOK Faz 4 Öncelik 2 — alt katman BOŞ verilse bile."""
    duvar = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    sonuc = akilli_yol_bul(
        YolIstegi((0, 0), (10, 0), "MIPI_D0_P", yuksek_hiz_mi=True),
        [duvar],
        alt_katman_engelleri=[],
    )
    assert sonuc.strateji == Strateji.BULUNAMADI
    assert sonuc.via_sayisi == 0
    assert any("YERLEŞİMDE" in n for n in sonuc.notlar)


def test_notlar_hangi_engelin_bloke_ettigini_soyler():
    e = Engel("C7_pad", 4.0, -1.0, 6.0, 1.0)
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"), [e])
    assert any("C7_pad" in n for n in sonuc.notlar)


def test_bulunamadi_sonucu_bos_segment_dondurur():
    duvar = Engel("duvar", -100.0, -1.0, 100.0, 1.0)
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"), [duvar])
    assert sonuc.segmentler == []
    assert sonuc.uzunluk_mm == 0.0


# ------------------------------------------------------------------
# 45° köşe dönüşümü (Faz 7)
# ------------------------------------------------------------------

def test_dik_aci_sayisi_olcer():
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))]
    assert dik_aci_sayisi(yol) == 1


def test_45_donusumu_dik_aci_birakmaz():
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))]
    donusmus = koseleri_45_dereceye_cevir(yol, pah_mm=0.5)
    assert dik_aci_sayisi(donusmus) == 0
    assert len(donusmus) == 3  # kısaltılmış + pah + kısaltılmış


def test_45_donusumu_uc_noktalari_korur():
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))]
    donusmus = koseleri_45_dereceye_cevir(yol, pah_mm=0.5)
    assert donusmus[0][0] == (0.0, 0.0)
    assert donusmus[-1][1] == (5.0, 5.0)


def test_45_pah_segmenti_gercekten_45_derece():
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))]
    (ax, ay), (bx, by) = koseleri_45_dereceye_cevir(yol, pah_mm=0.5)[1]
    assert abs(abs(bx - ax) - abs(by - ay)) < 1e-9


def test_45_donusumu_cok_kisa_segmentte_pahi_kucultur():
    """Pah, segmentin yarısından büyük olamaz — yoksa yol ters döner."""
    yol = [((0.0, 0.0), (0.4, 0.0)), ((0.4, 0.0), (0.4, 0.4))]
    donusmus = koseleri_45_dereceye_cevir(yol, pah_mm=5.0)
    assert dik_aci_sayisi(donusmus) == 0
    for (ax, ay), (bx, by) in donusmus:
        assert 0.0 - 1e-9 <= ax <= 0.4 + 1e-9
        assert 0.0 - 1e-9 <= by <= 0.4 + 1e-9


def test_45_donusumu_tek_segmenti_degistirmez():
    yol = [((0.0, 0.0), (5.0, 0.0))]
    assert koseleri_45_dereceye_cevir(yol) == yol


def test_45_donusumu_zaten_45_olan_kosede_islem_yapmaz():
    yol = [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (8.0, 3.0))]
    assert len(koseleri_45_dereceye_cevir(yol)) == 2


def test_negatif_pah_reddedilir():
    with pytest.raises(ValueError):
        koseleri_45_dereceye_cevir([((0, 0), (1, 0)), ((1, 0), (1, 1))], pah_mm=0.0)


# ------------------------------------------------------------------
# Push & Shove
# ------------------------------------------------------------------

def test_shove_engelleyen_izi_kaydirir():
    engelleyen = Iz("T1", (0.0, 0.0), (10.0, 0.0), 0.25, "GPIO1")
    istek = YolIstegi((0.0, 0.05), (10.0, 0.05), "SIG", 0.2, 0.2)
    oneri = itip_kaydir_oner(engelleyen, istek)
    assert oneri is not None
    # Hedef yol y=+0.05'te olduğu için engelleyen iz AŞAĞI (-y) kaymalı.
    assert oneri.baslangic[1] < 0.0
    ayrilma = abs(istek.baslangic[1] - oneri.baslangic[1])
    assert ayrilma >= 0.25 / 2 + 0.2 / 2 + 0.2 - 1e-9


def test_shove_dikey_izi_de_kaydirir():
    engelleyen = Iz("T2", (0.0, 0.0), (0.0, 10.0), 0.25, "GPIO2")
    istek = YolIstegi((0.05, 0.0), (0.05, 10.0), "SIG", 0.2, 0.2)
    oneri = itip_kaydir_oner(engelleyen, istek)
    assert oneri is not None
    assert oneri.baslangic[0] < 0.0


def test_kilitli_iz_asla_itilmez():
    """Yüksek hızlı/elle çizilmiş iz bu proje tarafından bozulmaz."""
    engelleyen = Iz("USB_DP", (0.0, 0.0), (10.0, 0.0), 0.25, "USB_D+", kilitli=True)
    istek = YolIstegi((0.0, 0.05), (10.0, 0.05), "SIG")
    assert itip_kaydir_oner(engelleyen, istek) is None


def test_egik_iz_itilmez():
    """Eğik izde 'dik yön' seçimi kafadan bir karar olurdu -> NEEDS_HUMAN."""
    engelleyen = Iz("T3", (0.0, 0.0), (10.0, 5.0), 0.25, "GPIO3")
    istek = YolIstegi((0.0, 0.05), (10.0, 0.05), "SIG")
    assert itip_kaydir_oner(engelleyen, istek) is None


def test_zaten_yeterince_uzaksa_kaydirma_onerilmez():
    engelleyen = Iz("T1", (0.0, 0.0), (10.0, 0.0), 0.25, "GPIO1")
    istek = YolIstegi((0.0, 5.0), (10.0, 5.0), "SIG")
    assert itip_kaydir_oner(engelleyen, istek) is None


def test_kaydirma_baska_engele_carparsa_reddedilir():
    """Zincirleme (kaskad) shove UYGULANMAZ — çarpıyorsa öneri yok."""
    engelleyen = Iz("T1", (0.0, 0.0), (10.0, 0.0), 0.25, "GPIO1")
    istek = YolIstegi((0.0, 0.05), (10.0, 0.05), "SIG", 0.2, 0.2)
    komsu = Engel("T0", -1.0, -1.0, 11.0, -0.2)
    assert itip_kaydir_oner(engelleyen, istek, diger_engeller=[komsu]) is None


def test_shove_ozeti_needs_human_yazar():
    engelleyen = Iz("USB_DP", (0.0, 0.0), (10.0, 0.0), 0.25, "USB_D+", kilitli=True)
    ozet = shove_ozetle(engelleyen, None)
    assert "NEEDS_HUMAN" in ozet and "kilitli" in ozet


def test_shove_ozeti_kaymayi_yazar():
    engelleyen = Iz("T1", (0.0, 0.0), (10.0, 0.0), 0.25, "GPIO1")
    istek = YolIstegi((0.0, 0.05), (10.0, 0.05), "SIG")
    oneri = itip_kaydir_oner(engelleyen, istek)
    assert "kaydırılması önerildi" in shove_ozetle(engelleyen, oneri)


# ------------------------------------------------------------------
# Kabul kapıları + routing_plan bağı
# ------------------------------------------------------------------

def test_via_yasagi_kapisi_ihlali_yakalar():
    sonuclar = {
        "MIPI_D0_P": YolSonucu([((0, 0), (1, 0))], Strateji.KATMAN_DEGISIMI, via_sayisi=2),
        "GPIO1": YolSonucu([((0, 0), (1, 0))], Strateji.KATMAN_DEGISIMI, via_sayisi=2),
    }
    bulgu = via_kurali_kontrolu(sonuclar, ["MIPI_D0_P"])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller == [{"net": "MIPI_D0_P", "via_sayisi": 2}]


def test_via_yasagi_kapisi_temizse_pass():
    sonuclar = {"MIPI_D0_P": YolSonucu([((0, 0), (1, 0))], Strateji.DOGRUDAN)}
    assert via_kurali_kontrolu(sonuclar, ["MIPI_D0_P"]).durum == BulguDurumu.PASS


def test_yuksek_hiz_neti_yoksa_kapsam_yok():
    assert via_kurali_kontrolu({}, ["MIPI_D0_P"]).durum == BulguDurumu.KAPSAM_YOK


def test_geometri_kapisi_dik_aciyi_yakalar():
    sonuclar = {
        "SIG": YolSonucu([((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))], Strateji.L_DONUSU)
    }
    bulgu = geometri_kurali_kontrolu(sonuclar)
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["dik_aci_sayisi"] == 1


def test_geometri_kapisi_45_donusumunden_sonra_pass():
    yol = koseleri_45_dereceye_cevir(
        [((0.0, 0.0), (5.0, 0.0)), ((5.0, 0.0), (5.0, 5.0))], pah_mm=0.5
    )
    assert geometri_kurali_kontrolu({"SIG": YolSonucu(yol, Strateji.L_DONUSU)}).durum == BulguDurumu.PASS


def test_routing_plan_satiri_asama_37_alanlarini_uretir():
    sonuc = akilli_yol_bul(YolIstegi((0, 0), (10, 0), "SIG"))
    satir = routing_plan_satiri_uret("SIG", sonuc)
    assert satir["net"] == "SIG"
    assert satir["strateji"] == "DOGRUDAN"
    assert satir["via_sayisi"] == 0
    assert satir["uzunluk_mm"] == 10.0
    assert satir["katmanlar"] == ["F.Cu"]


# ------------------------------------------------------------------
# pcbnew taslağı + öz test
# ------------------------------------------------------------------

def test_pcbnew_yoksa_kullanilamaz_ve_sessizce_yazmaz():
    router = TopolojikRouter("olmayan.kicad_pcb")
    if router.kullanilabilir_mi():
        pytest.skip("bu makinede pcbnew var — gerçek yazma ayrıca doğrulanmalı")
    with pytest.raises(RuntimeError):
        router.iz_yaz(YolSonucu([((0, 0), (1, 0))], Strateji.DOGRUDAN), "SIG", 0.2)


def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
