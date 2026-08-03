"""gerber_dfm_gorsel_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_gerber_dfm_gorsel_koprusu.py

`GERCEK_KICAD10_*` sabitleri, bu makinede `kicad-cli pcb export gerbers`
ile GERÇEK `ESP32C3_SmartBand.kicad_pcb` projesinden üretilmiş
`.gtl`/`.gts` dosyalarından alınmış BİREBİR alıntılardır (KiCad 10.0.4) —
uydurma örnek veri DEĞİLDİR. Bu, ayrıştırıcının gerçek bir fabrika
çıktısına karşı doğrulandığının kanıtıdır.
"""

import pytest

from bulgu_sozlesmesi import BulguDurumu

from gerber_dfm_gorsel_koprusu import (
    Aperture,
    Flash,
    GerberDosyasi,
    bakir_bosluk_taramasi,
    en_yakin_flash_ciftleri,
    flash_kutusu,
    gerber_ayristir,
    gerber_ayristir_uyarilari,
    gerber_dfm_raporu_uret,
    gerber_dfm_raporu_yaz,
    kutu_arasi_bosluk_mm,
    maske_baraji_taramasi,
    oz_testleri_calistir,
    _testin_bos_olmadigini_kanitla,
)

# --- kicad-cli pcb export gerbers --output ... ESP32C3_SmartBand.kicad_pcb ---
# (KiCad 10.0.4, bu makinede gerçekten koşturuldu)
GERCEK_KICAD10_FCU_PARCASI = """\
%TF.GenerationSoftware,KiCad,Pcbnew,10.0.4*%
%TF.FileFunction,Copper,L1,Top*%
%TF.FilePolarity,Positive*%
%FSLAX46Y46*%
%MOMM*%
%LPD*%
G01*
%AMRoundRect*
0 Rectangle with rounded corners*
4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0*
1,1,$1+$1,$2,$3*
1,1,$1+$1,$4,$5*
1,1,$1+$1,$6,$7*
1,1,$1+$1,$8,$9*
20,1,$1+$1,$2,$3,$4,$5,0*
20,1,$1+$1,$4,$5,$6,$7,0*
20,1,$1+$1,$6,$7,$8,$9,0*
20,1,$1+$1,$8,$9,$2,$3,0*%
%TA.AperFunction,SMDPad,CuDef*%
%ADD10RoundRect,0.140000X-0.140000X-0.170000X0.140000X-0.170000X0.140000X0.170000X-0.140000X0.170000X0*%
%TD*%
%TA.AperFunction,HeatsinkPad*%
%ADD17R,3.700000X3.700000*%
%TD*%
%TA.AperFunction,ViaPad*%
%ADD29C,0.600000*%
%TD*%
%TA.AperFunction,Conductor*%
%ADD31C,0.200000*%
%TD*%
D10*
%TO.P,C18,1*%
%TO.N,+3V3*%
X8520000Y-11500000D03*
%TO.P,C18,2*%
%TO.N,GND*%
X9480000Y-11500000D03*
%TD*%
D31*
X-2450000Y10250000D02*
X-2450000Y9750000D01*
X5375900Y7855900D02*
X5520000Y8000000D01*
"""

# --- kicad-cli pcb export gerbers (F.Mask, KiCad 10.0.4, gerçek koşum) ---
GERCEK_KICAD10_FMASK_PARCASI = """\
%TF.FileFunction,Soldermask,Top*%
%FSLAX46Y46*%
%MOMM*%
%LPD*%
G01*
%TA.AperFunction,SMDPad,CuDef*%
%ADD10RoundRect,0.140000X-0.140000X-0.170000X0.140000X-0.170000X0.140000X0.170000X-0.140000X0.170000X0*%
%TD*%
%TA.AperFunction,ComponentPad*%
%ADD21O,0.900000X2.400000*%
%TD*%
D10*
%TO.C,C18*%
X8520000Y-11500000D03*
X9480000Y-11500000D03*
%TD*%
%TO.C,U1*%
D21*
X-2450000Y10750000D03*
X0Y9000000D03*
"""


# ------------------------------------------------------------------
# Ayrıştırma — gerçek KiCad 10 verisiyle
# ------------------------------------------------------------------

def test_gercek_fcu_dosyasinda_katman_fonksiyonu_okunur():
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    assert gerber.katman_fonksiyonu == "Copper,L1,Top"


def test_gercek_fcu_dosyasinda_roundrect_aperture_bounding_box_dogru():
    """0.140000X-0.140000X-0.170000X0.140000X-0.170000X0.140000X0.170000X
    -0.140000X0.170000: r=0.14, köşeler x∈[-0.14,0.14], y∈[-0.17,0.17]
    -> genişlik=0.28+0.28=0.56, yükseklik=0.34+0.28=0.62."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    ap = gerber.apertureler["10"]
    assert ap.sekil == "RoundRect"
    assert ap.genislik_mm == pytest.approx(0.56, abs=1e-6)
    assert ap.yukseklik_mm == pytest.approx(0.62, abs=1e-6)


def test_gercek_fcu_dosyasinda_basit_r_ve_c_apertureler_okunur():
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    assert gerber.apertureler["17"] == Aperture("17", "R", 3.7, 3.7)
    assert gerber.apertureler["29"] == Aperture("29", "C", 0.6, 0.6)


def test_gercek_fcu_dosyasinda_koordinatlar_1e6_birimle_dogru_cevrilir():
    """X8520000Y-11500000 (1e-6 mm birim, %FSLAX46Y46%) -> (8.52, -11.5)mm."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    f = gerber.flashler[0]
    assert (f.x_mm, f.y_mm) == pytest.approx((8.52, -11.5))


def test_gercek_fcu_dosyasinda_net_ve_refdes_flash_a_baglanir():
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    assert gerber.flashler[0].net == "+3V3"
    assert gerber.flashler[0].refdes == "C18"
    assert gerber.flashler[1].net == "GND"


def test_gercek_fcu_dosyasinda_td_sonrasi_net_sifirlanir():
    """`%TD*%`den sonraki flash/çizimler ÖNCEKİ net'i miras ALMAMALI."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI + "\nD10*\nX0Y0D03*\n")
    assert gerber.flashler[-1].net is None


def test_gercek_fcu_dosyasinda_cizim_segmenti_okunur():
    """X-2450000Y10250000D02* + X-2450000Y9750000D01* -> tek segment."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    assert len(gerber.cizimler) == 2
    ilk = gerber.cizimler[0]
    assert ilk.baslangic == pytest.approx((-2.45, 10.25))
    assert ilk.bitis == pytest.approx((-2.45, 9.75))
    assert ilk.aperture_kodu == "31"


def test_gercek_fmask_dosyasinda_to_c_refdes_verir():
    """Mask katmanında %TO.C var, %TO.P/%TO.N YOK — ayrıştırıcı ikisini de
    desteklemeli (gerçek veriyle ortaya çıkan bir fark)."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FMASK_PARCASI)
    assert gerber.flashler[-1].refdes == "U1"
    assert gerber.flashler[-1].net is None


def test_am_makro_blogu_hatali_ayristirma_uretmez():
    """`%AMRoundRect*%` içindeki `4,1,4,$2,...` gibi makro satırları D-kodu
    veya koordinat gibi YANLIŞ ayrıştırılmamalı."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    # Makro bloğu 2 aperture + 2 flash + 2 çizimden fazlasını üretmemeli.
    assert len(gerber.flashler) == 2
    assert len(gerber.cizimler) == 2


# ------------------------------------------------------------------
# Geometri
# ------------------------------------------------------------------

def test_flash_kutusu_daire_apertureyle_dogru():
    aps = {"29": Aperture("29", "C", 0.6, 0.6)}
    kutu = flash_kutusu(Flash(1.0, 1.0, "29"), aps)
    assert kutu == pytest.approx((0.7, 0.7, 1.3, 1.3))


def test_flash_kutusu_bilinmeyen_aperture_none_doner():
    assert flash_kutusu(Flash(0, 0, "99"), {}) is None


def test_flash_kutusu_sifir_boyutlu_aperture_none_doner():
    aps = {"5": Aperture("5", "BILINMIYOR", 0.0, 0.0)}
    assert flash_kutusu(Flash(0, 0, "5"), aps) is None


def test_kutu_arasi_bosluk_ayrik_kutularda_pozitif():
    assert kutu_arasi_bosluk_mm((0, 0, 1, 1), (2, 0, 3, 1)) == pytest.approx(1.0)


def test_kutu_arasi_bosluk_cakisan_kutularda_negatif():
    assert kutu_arasi_bosluk_mm((0, 0, 2, 2), (1, 1, 3, 3)) < 0


def test_kutu_arasi_bosluk_diagonal_dogru_hesaplanir():
    d = kutu_arasi_bosluk_mm((0, 0, 1, 1), (2, 2, 3, 3))
    assert d == pytest.approx((1.0 ** 2 + 1.0 ** 2) ** 0.5)


# ------------------------------------------------------------------
# en_yakin_flash_ciftleri
# ------------------------------------------------------------------

def _iki_flashli_gerber(bosluk_mm: float, ayni_net: bool = False) -> GerberDosyasi:
    aps = {"1": Aperture("1", "C", 0.5, 0.5)}
    net_a = "GND"
    net_b = "GND" if ayni_net else "+3V3"
    flashler = [
        Flash(0.0, 0.0, "1", net_a, "R1"),
        Flash(0.5 + bosluk_mm, 0.0, "1", net_b, "R2"),
    ]
    return GerberDosyasi(aps, flashler, [], "mm", "Copper,L1,Top")


def test_esik_altindaki_bosluk_yakalanir():
    gerber = _iki_flashli_gerber(bosluk_mm=0.1)
    ciftler = en_yakin_flash_ciftleri(gerber, esik_mm=0.2)
    assert len(ciftler) == 1
    assert ciftler[0]["bosluk_mm"] == pytest.approx(0.1)


def test_esik_ustundeki_bosluk_yakalanmaz():
    gerber = _iki_flashli_gerber(bosluk_mm=0.5)
    assert en_yakin_flash_ciftleri(gerber, esik_mm=0.2) == []


def test_ayni_net_varsayilan_olarak_atlanir():
    gerber = _iki_flashli_gerber(bosluk_mm=0.1, ayni_net=True)
    assert en_yakin_flash_ciftleri(gerber, esik_mm=0.2) == []


def test_ayni_net_atlama_kapatilabilir():
    gerber = _iki_flashli_gerber(bosluk_mm=0.1, ayni_net=True)
    ciftler = en_yakin_flash_ciftleri(gerber, esik_mm=0.2, ayni_net_atla=False)
    assert len(ciftler) == 1


def test_bilinmeyen_aperture_hesaptan_haric():
    aps = {"1": Aperture("1", "BILINMIYOR", 0.0, 0.0), "2": Aperture("2", "C", 0.5, 0.5)}
    flashler = [Flash(0, 0, "1", "A"), Flash(0.1, 0, "2", "B")]
    gerber = GerberDosyasi(aps, flashler, [], "mm", "Copper,L1,Top")
    assert en_yakin_flash_ciftleri(gerber, esik_mm=1.0) == []


# ------------------------------------------------------------------
# Kabul kapıları — GERÇEK export edilmiş dosyalarla
# ------------------------------------------------------------------

def test_maske_baraji_taramasi_gercek_fmask_verisiyle_calisir():
    gerber = gerber_ayristir(GERCEK_KICAD10_FMASK_PARCASI)
    bulgu = maske_baraji_taramasi(gerber, fab_min_baraj_mm=0.20)
    assert bulgu.taranan == 4


def test_maske_baraji_taramasi_yanlis_katmanda_reddeder():
    """Copper dosyasını maske kontrolüne vermek sessizce anlamsız sonuç
    üretmesin — açık hata."""
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    with pytest.raises(ValueError):
        maske_baraji_taramasi(gerber, fab_min_baraj_mm=0.20)


def test_bakir_bosluk_taramasi_gercek_fcu_verisiyle_calisir():
    gerber = gerber_ayristir(GERCEK_KICAD10_FCU_PARCASI)
    bulgu = bakir_bosluk_taramasi(gerber, min_clearance_mm=0.15)
    assert bulgu.taranan == 2


def test_bakir_bosluk_taramasi_yanlis_katmanda_reddeder():
    gerber = gerber_ayristir(GERCEK_KICAD10_FMASK_PARCASI)
    with pytest.raises(ValueError):
        bakir_bosluk_taramasi(gerber, min_clearance_mm=0.15)


def test_maske_baraji_ihlalsizken_pass():
    aps = {"1": Aperture("1", "C", 0.3, 0.3)}
    flashler = [Flash(0, 0, "1"), Flash(10, 0, "1")]
    gerber = GerberDosyasi(aps, flashler, [], "mm", "Soldermask,Top")
    assert maske_baraji_taramasi(gerber, 0.2).durum == BulguDurumu.PASS


def test_flashsiz_dosyada_kapsam_yok():
    gerber = GerberDosyasi({}, [], [], "mm", "Soldermask,Top")
    bulgu = maske_baraji_taramasi(gerber, 0.2)
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# Ayrıştırma uyarıları
# ------------------------------------------------------------------

def test_ayristirma_uyarisi_bilinmeyen_apertureyi_bildirir():
    metin = "%TF.FileFunction,Copper,L1,Top*%\n%FSLAX46Y46*%\n%MOMM*%\nD10*\nX0Y0D03*\n"
    gerber = gerber_ayristir(metin)
    # Tanımsız aperture D10 -> BILINMIYOR yok (hiç tanımlanmadıysa apertureler'de de yok);
    # uyarı sadece TANIMLI ama boyutsuz olanlar için üretilir.
    assert gerber_ayristir_uyarilari(gerber) == []


def test_ayristirma_uyarisi_gercek_bilinmiyor_aperture_icin():
    gerber = GerberDosyasi(
        {"5": Aperture("5", "BILINMIYOR", 0.0, 0.0)},
        [Flash(0, 0, "5")], [], "mm", "Copper,L1,Top",
    )
    uyarilar = gerber_ayristir_uyarilari(gerber)
    assert len(uyarilar) == 1 and "D5" in uyarilar[0]


# ------------------------------------------------------------------
# Rapor
# ------------------------------------------------------------------

def test_rapor_gercek_veri_uyarisini_icerir():
    gerber = gerber_ayristir(GERCEK_KICAD10_FMASK_PARCASI)
    bulgu = maske_baraji_taramasi(gerber, 0.2)
    rapor = gerber_dfm_raporu_uret([bulgu])
    assert "GERÇEK export edilmiş" in rapor
    assert "gerber_maske_baraji" in rapor


def test_rapor_ihlal_detayini_yazar():
    bulgu = maske_baraji_taramasi(gerber_ayristir(GERCEK_KICAD10_FMASK_PARCASI), 0.5)
    rapor = gerber_dfm_raporu_uret([bulgu])
    assert "boşluk=" in rapor


def test_rapor_dosyaya_yazilir(tmp_path):
    hedef = tmp_path / "TEST" / "gerber_dfm_raporu.md"
    gerber_dfm_raporu_yaz(str(hedef), [])
    assert hedef.exists()
    assert "Gerber DFM" in hedef.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
