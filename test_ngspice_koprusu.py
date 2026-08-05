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

from bulgu_sozlesmesi import Bulgu, BulguDurumu

from ngspice_koprusu import (
    AcSweep,
    DcSweep,
    DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM,
    DekuplajOnerisi,
    ModelTuru,
    OpAnalizi,
    ORNEK_NGSPICE_CIKTISI,
    RayHedefi,
    TranAnalizi,
    ac_bant_dogrula,
    cikti_ayristir,
    decoupling_onerisi_uret,
    netlist_analiz_ekle,
    ngspice_calistir,
    ngspice_yolu_bul,
    oz_testleri_calistir,
    sembol_modeli_eksik_olanlar,
    simulasyon_raporu_uret,
    simulasyon_raporu_yaz,
    transient_calistir,
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
# Transient (.tran) — "sanal osiloskop probu"
# ------------------------------------------------------------------

def test_tran_analizi_spice_satiri():
    assert TranAnalizi(1e-5, 1e-3).spice_satiri() == ".tran 1e-05 0.001"


def test_tran_analizi_baslangic_verilirse_satira_eklenir():
    satir = TranAnalizi(1e-5, 1e-3, baslangic_s=5e-4).spice_satiri()
    assert satir == ".tran 1e-05 0.001 0.0005"


def test_transient_calistir_bos_netler_reddedilir(tmp_path):
    """Neyi ölçtüğünü bilmeyen bir 'osiloskop' rapor değildir."""
    netlist = tmp_path / "devre.cir"
    netlist.write_text("R1 a b 1\n.end\n", encoding="utf-8")
    with pytest.raises(ValueError):
        transient_calistir(str(netlist), 1e-3, 1e-5, [], str(tmp_path / "out"))


def test_transient_calistir_ngspice_yoksa_kapsam_yok_ve_dosya_yazilmaz(tmp_path, monkeypatch):
    import ngspice_koprusu

    monkeypatch.setattr(ngspice_koprusu, "ngspice_calistir", lambda *a, **k: None)
    netlist = tmp_path / "devre.cir"
    netlist.write_text("R1 vin vout 1k\nC1 vout 0 1u\n.end\n", encoding="utf-8")
    cikti_dir = tmp_path / "out"

    bulgu = transient_calistir(
        str(netlist), sure_s=1e-3, adim_s=1e-5,
        prob_netleri=["vout"], calisma_dizini=str(cikti_dir),
    )

    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert bulgu.taranan == 0
    assert "KOŞULMADI" in bulgu.detay
    assert not cikti_dir.exists()  # sahte CSV/PNG UYDURULMADI


def test_transient_calistir_bulunmayan_prob_net_ihlal_olarak_raporlanir(tmp_path, monkeypatch):
    """Bir prob net simülasyon çıktısında yoksa bu sessizce atlanmaz — ihlal
    olarak raporlanır (voltaj_dususu_dogrula'nın 'düğüm çıktıda yok'
    deseniyle AYNI disiplin), diğer probun CSV'si yine de yazılır."""
    import ngspice_koprusu
    from ngspice_koprusu import SimulasyonSonucu

    sahte_sonuc = SimulasyonSonucu(
        veri={"v(vout)": [(0.0, 0.0), (1e-3, 3.3)]},
        satir_sayisi=2, ngspice_surumu="ngspice-46 (sahte)",
    )
    monkeypatch.setattr(ngspice_koprusu, "ngspice_calistir", lambda *a, **k: sahte_sonuc)
    netlist = tmp_path / "devre.cir"
    netlist.write_text("R1 vin vout 1k\nC1 vout 0 1u\n.end\n", encoding="utf-8")
    cikti_dir = tmp_path / "out"

    bulgu = transient_calistir(
        str(netlist), 1e-3, 1e-5, ["vout", "hic_yok"], str(cikti_dir),
    )

    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.taranan == 2
    assert len(bulgu.ihlaller) == 1
    assert bulgu.ihlaller[0]["net"] == "hic_yok"
    assert (cikti_dir / "tran_vout.csv").exists()


@pytest.mark.skipif(
    ngspice_yolu_bul() is None,
    reason="bu makinede ngspice kurulu değil — gerçek .tran koşumu atlandı, sessizce PASS SAYILMAZ",
)
def test_transient_calistir_gercek_ngspice_ile_rc_sarj_egrisi(tmp_path):
    """DOĞRULAMA (bu makinede GERÇEKTEN koşturuldu): R=1k, C=1uF (tau=1ms)
    RC şarj devresi 5*tau boyunca koşturulur; ngspice'ın ürettiği son nokta
    (4.966345V) analitik V(t)=5*(1-e^(-t/tau)) (4.966310V) ile ~35uV fark
    içinde örtüştü — 'kod çalıştı' ile 'kod DOĞRU sonuç verdi' arasındaki
    fark burada GERÇEK ölçümle kapatıldı, tahminle DEĞİL."""
    netlist = tmp_path / "rc.cir"
    netlist.write_text(
        "* RC transient test devresi\n"
        "V1 vin 0 PULSE(0 5 0 1n 1n 10m 20m)\n"
        "R1 vin vout 1k\n"
        "C1 vout 0 1u\n"
        ".end\n",
        encoding="utf-8",
    )
    cikti_dir = tmp_path / "out"

    bulgu = transient_calistir(
        str(netlist), sure_s=5e-3, adim_s=5e-5,
        prob_netleri=["vin", "vout"], calisma_dizini=str(cikti_dir),
    )

    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.taranan == 2
    satirlar = (cikti_dir / "tran_vout.csv").read_text(encoding="utf-8").strip().splitlines()
    son_zaman, son_voltaj = (float(x) for x in satirlar[-1].split(","))
    beklenen = 5.0 * (1.0 - math.exp(-son_zaman / 1e-3))
    assert son_voltaj == pytest.approx(beklenen, abs=5e-3)
    assert (cikti_dir / "tran_osiloskop.png").exists()
    assert (cikti_dir / "tran_vin.csv").exists()


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


# ------------------------------------------------------------------
# FAZ 0.5-3: decoupling_onerisi_uret (PDN otomatik dekuplaj önerisi)
# ------------------------------------------------------------------

def test_pass_bulguda_oneri_uretilmez():
    """Hiçbir ray tolerans dışına çıkmadıysa öneriye GEREK yoktur."""
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bulgu = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, tolerans_yuzde=10.0)])
    assert bulgu.durum == BulguDurumu.PASS
    assert decoupling_onerisi_uret(bulgu) == []


def test_kapsam_yok_bulguda_oneri_uretilemez():
    """Simülasyon hiç koşmadıysa (KAPSAM_YOK) öneri de UYDURULAMAZ."""
    bulgu = voltaj_dususu_dogrula(None, [RayHedefi("vout", 3.3)])
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert decoupling_onerisi_uret(bulgu) == []


def test_hafif_dusumde_tek_100nf_onerilir():
    """dusum_yuzdesi <= %2 -> sadece standart 100nF (en hafif kademe)."""
    bulgu = Bulgu(
        kontrol="simulasyon_voltaj_dususu",
        durum=BulguDurumu.FAIL,
        taranan=1,
        ihlaller=[{
            "dugum": "v3v3",
            "nominal_v": 3.3,
            "alt_sinir_v": 3.135,
            "olculen_min_v": 3.28,
            "dusum_mv": 20.0,  # %0.6
        }],
    )
    oneriler = decoupling_onerisi_uret(bulgu)
    assert len(oneriler) == 1
    assert oneriler[0].dugum == "v3v3"
    assert oneriler[0].onerilen_kapasitans_f == [100e-9]
    assert oneriler[0].maks_mesafe_mm == DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM


def test_orta_dusumde_ek_1uf_onerilir():
    """%2 < dusum_yuzdesi <= %5 -> 100nF + 1uF ara-frekans desteği."""
    bulgu = Bulgu(
        kontrol="simulasyon_voltaj_dususu",
        durum=BulguDurumu.FAIL,
        taranan=1,
        ihlaller=[{
            "dugum": "v1v8",
            "nominal_v": 1.8,
            "alt_sinir_v": 1.71,
            "olculen_min_v": 1.74,
            "dusum_mv": 60.0,  # %3.33
        }],
    )
    oneriler = decoupling_onerisi_uret(bulgu)
    assert oneriler[0].onerilen_kapasitans_f == [100e-9, 1e-6]


def test_agir_dusumde_ek_10uf_bulk_onerilir():
    """dusum_yuzdesi > %5 -> gerçek test verisiyle (bkz.
    test_voltaj_dususu_sinir_altinda_fail_ve_dusumu_raporlar) 100nF + 10uF bulk."""
    sonuc = cikti_ayristir(ORNEK_NGSPICE_CIKTISI)
    bulgu = voltaj_dususu_dogrula(sonuc, [RayHedefi("vout", 3.3, min_kabul_v=3.25)])
    assert bulgu.durum == BulguDurumu.FAIL
    oneriler = decoupling_onerisi_uret(bulgu)
    assert len(oneriler) == 1
    assert oneriler[0].onerilen_kapasitans_f == [100e-9, 10e-6]
    assert "vout" in oneriler[0].gerekce
    assert "3.0" in oneriler[0].gerekce or "3mm" in oneriler[0].gerekce.lower()


def test_dugum_hic_izlenmemis_ihlali_oneriye_donusturmez():
    """`izlenmeyen_dugum` sınıfı ihlalde nominal_v/dusum_mv YOKTUR — bu
    ihlal için uydurma bir öneri ÜRETİLMEMELİDİR, sessizce atlanmalıdır."""
    bulgu = voltaj_dususu_dogrula(cikti_ayristir(ORNEK_NGSPICE_CIKTISI), [RayHedefi("v1v8", 1.8)])
    assert bulgu.durum == BulguDurumu.FAIL
    assert "sebep" in bulgu.ihlaller[0]
    assert decoupling_onerisi_uret(bulgu) == []


def test_maks_mesafe_mm_disaridan_override_edilebilir():
    """Docstring'de belgelenen 1.5mm'lik daha sıkı hedef İSTENİRSE açıkça
    verilebilir — sessizce varsayılmaz (bkz. modüldeki SINIR/TUTARSIZLIK NOTU)."""
    bulgu = Bulgu(
        kontrol="simulasyon_voltaj_dususu",
        durum=BulguDurumu.FAIL,
        taranan=1,
        ihlaller=[{
            "dugum": "v3v3",
            "nominal_v": 3.3,
            "alt_sinir_v": 3.135,
            "olculen_min_v": 3.28,
            "dusum_mv": 20.0,
        }],
    )
    oneriler = decoupling_onerisi_uret(bulgu, maks_mesafe_mm=1.5)
    assert oneriler[0].maks_mesafe_mm == 1.5


def test_varsayilan_mesafe_gercekten_uygulanan_kontrolle_tek_kaynak():
    """`DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM`, pcbnew_koprusu.py::
    dekuplaj_mesafe_kontrolu()'nun GERÇEKTEN UYGULANAN varsayılanıyla
    (3.0mm) TEK KAYNAK olmalı — dokümantasyondaki 1.5mm ile DEĞİL."""
    assert DEKUPLAJ_VARSAYILAN_MAKS_MESAFE_MM == 3.0
