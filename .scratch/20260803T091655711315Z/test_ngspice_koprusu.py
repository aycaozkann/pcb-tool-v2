"""ngspice_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_ngspice_koprusu.py

NOT: Bu ortamda `ngspice` KURULU DEĞİL. Bu yüzden testler iki gruba ayrılır:
  1. Ayrıştırma/karar/rapor mantığı — gerçek ngspice ÇIKTI METNİ üzerinde
     tam olarak test edilir (ORNEK_NGSPICE_CIKTISI).
  2. Çalıştırma (`ngspice_calistir`) — aracın yokluğunda `None` dönmesi ve
     bunun `KAPSAM_YOK`'a çevrilmesi test edilir; gerçek koşum senin
     makinende doğrulanmalı.
"""

import math

import pytest

from bulgu_sozlesmesi import BulguDurumu

from ngspice_koprusu import (
    AcSweep,
    DcSweep,
    ModelTuru,
    OpAnalizi,
    ORNEK_NGSPICE_CIKTISI,
    RayHedefi,
    ac_bant_dogrula,
    cikti_ayristir,
    netlist_analiz_ekle,
    ngspice_calistir,
    ngspice_yolu_bul,
    oz_testleri_calistir,
    sembol_modeli_eksik_olanlar,
    simulasyon_raporu_uret,
    simulasyon_raporu_yaz,
    voltaj_dususu_dogrula,
    _testin_bos_olmadigini_kanitla,
)


# ------------------------------------------------------------------
# Analiz komutu üretimi
# ------------------------------------------------------------------

def test_dc_sweep_spice_satiri():
    assert DcSweep("Vin", 3.0, 4.2, 0.1).spice_satiri() == ".dc Vin 3.0 4.2 0.1"


def test_ac_sweep_spice_satiri():
    assert AcSweep(10.0, 1e6, 20, "dec").spice_satiri() == ".ac dec 20 10.0 1000000.0"


def test_ac_sweep_gecersiz_tip_reddedilir():
    with pytest.raises(ValueError):
        AcSweep(10.0, 1e6, 20, "logaritmik").spice_satiri()


def test_op_analizi_spice_satiri():
    assert OpAnalizi().spice_satiri() == ".op"


# ------------------------------------------------------------------
# Netlist'e analiz ekleme
# ------------------------------------------------------------------

def test_netlist_analiz_ekle_control_blogu_uretir():
    netlist = "* devre\nR1 vin vout 10\n.end"
    cikti = netlist_analiz_ekle(netlist, OpAnalizi(), ["vout"])
    assert ".op" in cikti
    assert ".control" in cikti and ".endc" in cikti
    assert "print v(vout)" in cikti
    assert cikti.strip().endswith(".end")


def test_netlist_analiz_ekle_mevcut_end_i_tekrarlamaz():
    cikti = netlist_analiz_ekle("R1 a b 1\n.end", OpAnalizi(), ["b"])
    assert cikti.count(".end\n") == 1


def test_netlist_analiz_ekle_hazir_v_ifadesini_sarmalar():
    cikti = netlist_analiz_ekle("R1 a b 1", OpAnalizi(), ["v(b)"])
    assert "print v(b)" in cikti
    assert "v(v(b))" not in cikti


def test_izlenen_dugum_yoksa_reddedilir():
    """Neyi ölçtüğünü bilmeyen bir simülasyon rapor değildir."""
    with pytest.raises(ValueError):
        netlist_analiz_ekle("R1 a b 1", OpAnalizi(), [])


# ------------------------------------------------------------------
# SPICE modeli ön kontrolü
# ------------------------------------------------------------------

GERCEK_KICAD10_NETLIST = """\
.title KiCad schematic
C18 /+3V3 GND 1u
C14 /+3V3 GND 10n
U4 __U4
U2 __U2
SW1 __SW1
R5 /PROG_NET GND 10k
Y1 __Y1
J1 __J1
.end
"""


def test_kicad10_modelsiz_sembolleri_yakalanir():
    """REGRESYON: gerçek `kicad-cli sch export netlist --format spice`
    çıktısı (KiCad 10.0, ESP32C3_SmartBand.kicad_sch) modelsiz sembolleri
    `U4 __U4` biçiminde yazıyor — `X` ön ekli subckt olarak DEĞİL. İlk
    taslaktaki sezgisel bu 12 parçayı hiç görmüyordu."""
    eksikler = sembol_modeli_eksik_olanlar(GERCEK_KICAD10_NETLIST)
    assert eksikler == ["U4", "U2", "SW1", "Y1", "J1"]


def test_gercek_netlistte_pasifler_eksik_sayilmaz():
    eksikler = sembol_modeli_eksik_olanlar(GERCEK_KICAD10_NETLIST)
    assert "C18" not in eksikler and "R5" not in eksikler


def test_model_eksik_alt_devre_yakalanir():
    netlist = "* devre\nXU1 vin vout gnd ME6211\nR1 vout gnd 10k\n.end"
    assert sembol_modeli_eksik_olanlar(netlist) == ["XU1"]


def test_subckt_tanimliysa_eksik_sayilmaz():
    netlist = (
        "* devre\nXU1 vin vout gnd ME6211\n"
        ".subckt ME6211 in out gnd\nR1 in out 0.1\n.ends\n.end"
    )
    assert sembol_modeli_eksik_olanlar(netlist) == []


def test_include_varsa_eksik_sayilmaz():
    netlist = '* devre\n.include "me6211.lib"\nXU1 vin vout gnd ME6211\n.end'
    assert sembol_modeli_eksik_olanlar(netlist) == []


def test_pasif_elemanlar_model_eksigi_saymaz():
    assert sembol_modeli_eksik_olanlar("R1 a b 10k\nC1 b 0 100n\n.end") == []


# ------------------------------------------------------------------
# Çıktı ayrıştırma (gerçek ngspice ASCII biçimi)
# ------------------------------------------------------------------

def test_ayristirma_satir_ve_dugum_sayisi():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    assert sonuc.satir_sayisi == 3
    assert set(sonuc.veri) == {"v(vout)", "v(vin)"}


def test_ayristirma_sweep_eksenini_ayirir():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    assert sonuc.veri["v(vout)"][0] == (0.0, 3.3)
    assert sonuc.veri["v(vout)"][-1] == (1.0, 3.1)


def test_min_ve_son_deger():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    assert sonuc.min_deger("v(vout)") == 3.1
    assert sonuc.son_deger("v(vin)") == 4.0


def test_op_analizi_ciktisinda_sweep_sutunu_yok():
    metin = "Index   v(vout)\n-------------\n0\t3.290000e+00\n"
    sonuc = cikti_ayristir(metin)
    assert sonuc.veri["v(vout)"] == [(0.0, 3.29)]


def test_ayristirma_bos_metinde_bos_doner():
    sonuc = cikti_ayristir("ngspice hata verdi, hiç tablo basılmadı")
    assert sonuc.satir_sayisi == 0
    assert sonuc.veri == {}


def test_bilinmeyen_dugum_none_doner():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    assert sonuc.min_deger("v(yok)") is None


# ------------------------------------------------------------------
# Kabul kriterleri
# ------------------------------------------------------------------

def test_ray_alt_siniri_toleranstan_hesaplanir():
    assert RayHedefi("vout", 3.3, tolerans_yuzde=5.0).alt_sinir_v == pytest.approx(3.135)


def test_min_kabul_v_toleransi_ezer():
    assert RayHedefi("vout", 3.3, tolerans_yuzde=5.0, min_kabul_v=3.2).alt_sinir_v == 3.2


def test_voltaj_dususu_tolerans_icinde_pass():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bulgu = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, tolerans_yuzde=10.0)])
    assert bulgu.durum == BulguDurumu.PASS


def test_voltaj_dususu_sinir_altinda_fail_ve_dusumu_raporlar():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bulgu = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, min_kabul_v=3.25)])
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["olculen_min_v"] == 3.1
    assert bulgu.ihlaller[0]["dusum_mv"] == pytest.approx(200.0, abs=0.01)


def test_en_kotu_deger_kullanilir_ortalama_degil():
    """Sweep ortasında sınırın altına düşüp toparlanmak da başarısızlıktır."""
    metin = (
        "Index   v-sweep         v(vout)\n----\n"
        "0\t0.0\t3.300000e+00\n1\t0.5\t2.900000e+00\n2\t1.0\t3.300000e+00\n"
    )
    bulgu = voltaj_dususu_dogrula(cikti_ayristir(metin), [RayHedefi("vout", 3.3, tolerans_yuzde=5.0)])
    assert bulgu.durum == BulguDurumu.FAIL


def test_izlenmeyen_dugum_ihlal_olarak_raporlanir():
    """Düğüm hiç izlenmemişse bu sessizce PASS olmaz — eksik kapsam ihlaldir."""
    bulgu = voltaj_dususu_dogrula(cikti_ayristir(ORNEK_NGSPICE_CIKTISI), [RayHedefi("v1v8", 1.8)])
    assert bulgu.durum == BulguDurumu.FAIL
    assert "YOK" in bulgu.ihlaller[0]["sebep"]


def test_ngspice_yoksa_kapsam_yok_ve_pass_degil():
    bulgu = voltaj_dususu_dogrula(None, [RayHedefi("vout", 3.3)])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert not bulgu.gecti_mi
    assert "uydurulmadı" in bulgu.detay


def test_bos_cikti_kapsam_yok():
    bulgu = voltaj_dususu_dogrula(cikti_ayristir("hata"), [RayHedefi("vout", 3.3)])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# AC bant doğrulama
# ------------------------------------------------------------------

def test_ac_bant_kazanc_yeterliyse_pass():
    metin = (
        "Index   frequency       v(out)\n----\n"
        "0\t1.000000e+01\t9.500000e-01\n1\t1.000000e+02\t9.000000e-01\n"
    )
    bulgu = ac_bant_dogrula(cikti_ayristir(metin), "out", min_kazanc_db=-1.0, f_alt_hz=1.0, f_ust_hz=1e3)
    assert bulgu.durum == BulguDurumu.PASS


def test_ac_bant_kazanc_dusukse_fail():
    metin = "Index   frequency       v(out)\n----\n0\t1.000000e+02\t1.000000e-01\n"
    bulgu = ac_bant_dogrula(cikti_ayristir(metin), "out", min_kazanc_db=-1.0, f_alt_hz=1.0, f_ust_hz=1e3)
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["kazanc_db"] == pytest.approx(20 * math.log10(0.1), abs=0.01)


def test_ac_bant_sifir_deger_atlanir_ve_raporlanir():
    """0 veya negatif değere -inf dB basıp FAIL demek yanıltıcı olurdu."""
    metin = "Index   frequency       v(out)\n----\n0\t1.000000e+02\t0.000000e+00\n"
    bulgu = ac_bant_dogrula(cikti_ayristir(metin), "out", min_kazanc_db=-1.0, f_alt_hz=1.0, f_ust_hz=1e3)
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


def test_ac_bant_disindaki_noktalar_sayilmaz():
    metin = (
        "Index   frequency       v(out)\n----\n"
        "0\t1.000000e+00\t1.000000e-03\n1\t1.000000e+02\t9.500000e-01\n"
    )
    bulgu = ac_bant_dogrula(cikti_ayristir(metin), "out", min_kazanc_db=-1.0, f_alt_hz=50.0, f_ust_hz=1e3)
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.taranan == 1


def test_ac_bant_ngspice_yoksa_kapsam_yok():
    assert ac_bant_dogrula(None, "out", -1.0, 1.0, 1e3).durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# Rapor (MASTER_RULEBOOK Faz 3)
# ------------------------------------------------------------------

def test_davranissal_model_notu_zorunlu():
    """MASTER_RULEBOOK Faz 3: davranışsal modelde neyi yansıtmadığı YAZILMALI."""
    with pytest.raises(ValueError):
        simulasyon_raporu_uret([], ModelTuru.DAVRANISSAL, "", "ngspice-42")


def test_uretici_modelinde_not_zorunlu_degil():
    rapor = simulasyon_raporu_uret([], ModelTuru.URETICI_SPICE, "", "ngspice-42")
    assert "URETICI_SPICE" in rapor


def test_rapor_model_turunu_ve_cozucuyu_yazar():
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bulgu = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, tolerans_yuzde=10.0)])
    rapor = simulasyon_raporu_uret(
        [bulgu], ModelTuru.DAVRANISSAL, "ideal LDO; termal shutdown ve PSRR yansıtılmadı", "ngspice-42"
    )
    assert "DAVRANISSAL" in rapor
    assert "PSRR yansıtılmadı" in rapor
    assert "ngspice-42" in rapor
    assert "simulasyon_voltaj_dususu | PASS" in rapor


def test_rapor_kapsam_yok_uyarisini_ekler():
    bulgu = voltaj_dususu_dogrula(None, [RayHedefi("vout", 3.3)])
    rapor = simulasyon_raporu_uret([bulgu], ModelTuru.BILINMIYOR, "", "YOK")
    assert "KAPSAM_YOK" in rapor
    assert "PASS" in rapor  # "Bu bir PASS DEĞİLDİR" uyarısı
    assert "KURULUM.md" in rapor


def test_rapor_dosyaya_yazilir(tmp_path):
    hedef = tmp_path / "TEST" / "simulasyon_raporu.md"
    yol = simulasyon_raporu_yaz(str(hedef), [], ModelTuru.URETICI_SPICE, "", "ngspice-42")
    assert hedef.exists()
    assert "Simülasyon Raporu" in hedef.read_text(encoding="utf-8")
    assert yol == str(hedef)


# ------------------------------------------------------------------
# Araç yokluğu / öz test
# ------------------------------------------------------------------

def test_ngspice_kurulu_degilse_calistirma_none_doner():
    """Bu ortamda ngspice yok; kurulu olan bir makinede bu test atlanır."""
    if ngspice_yolu_bul() is not None:
        pytest.skip("bu makinede ngspice kurulu — gerçek koşum ayrıca doğrulanmalı")
    assert ngspice_calistir("olmayan.cir") is None


def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
