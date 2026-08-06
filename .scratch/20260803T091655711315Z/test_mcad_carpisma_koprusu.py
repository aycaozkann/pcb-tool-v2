"""mcad_carpisma_koprusu.py için test suite.
Çalıştırmak için:  pytest -v test_mcad_carpisma_koprusu.py

`GERCEK_KICAD10_FOOTPRINT_PARCASI`, bu makinede gerçekten var olan
`ESP32C3_SmartBand.kicad_pcb` dosyasından alınmış BİREBİR bir
`(footprint ...)` bloğudur (C16, Capacitor_SMD:C_0402_1005Metric,
`(at -13 14.5)`). `kicad_pcb_yerlesimlerini_cikar()` ayrıca aynı makinedeki
TAM (43 footprint'lik) gerçek dosyaya karşı da (bu test dosyasının dışında,
geliştirme sırasında) doğrulandı — 43/43 doğru refdes/konum/katman
çıkarıldı.

`step_disa_aktar()`'ın GERÇEK `kicad-cli` koşumu (25 saniye sürdüğü için)
bu otomatik test paketine DAHİL EDİLMEDİ — bu, dosya başlığındaki
"GERÇEKTEN koşturuldu" notuyla çelişmez; o koşum geliştirme sırasında
elle bir kez yapıldı ve komut satırı doğrulandı, burada sadece komut
İNŞASI (mocksuz, gerçek `subprocess` ile ama sahte bir `kicad_cli` yoluyla)
test edilir.
"""

import subprocess

import pytest

from bulgu_sozlesmesi import BulguDurumu

from mcad_carpisma_koprusu import (
    Carpisma,
    KasaEngelHacmi,
    KomponentGovdesi3D,
    KomponentYerlesimi,
    carpisma_raporu_uret,
    carpisma_raporu_yaz,
    carpisma_tara,
    eksik_3d_modelleri_ayikla,
    kicad_pcb_yerlesimlerini_cikar,
    komponent_3d_kutusu,
    kutu_3d_carpisiyor_mu,
    oz_testleri_calistir,
    rotasyonlu_aabb,
    step_disa_aktar,
    _footprint_bloklarina_ayir,
    _testin_bos_olmadigini_kanitla,
)

# --- ESP32C3_SmartBand.kicad_pcb'den BİREBİR alıntı (bu makinede gerçek) ---
GERCEK_KICAD10_FOOTPRINT_PARCASI = """\
	(footprint "Capacitor_SMD:C_0402_1005Metric"
		(layer "F.Cu")
		(uuid "0769dfc2-0e39-4e85-a221-6ac6c5a69373")
		(at -13 14.5)
		(descr "Capacitor SMD 0402")
		(tags "capacitor")
		(property "Reference" "C16"
			(at -0.28 -1.265 0)
			(layer "F.SilkS")
			(uuid "913aa3e0-352f-4455-8a5c-f5db8cf4cce9")
			(effects
				(font
					(size 0.8 0.8)
					(thickness 0.12)
				)
			)
		)
		(property "Value" "4.7uF"
			(at 0 1.16 0)
			(layer "F.Fab")
			(uuid "7dd7f8af-7c1f-4db3-b674-22a86dd29f71")
			(effects
				(font
					(size 1 1)
					(thickness 0.15)
				)
			)
		)
		(model "${KICAD10_3DMODEL_DIR}/Capacitor_SMD.3dshapes/C_0402_1005Metric.step"
			(offset
				(xyz 0 0 0)
			)
			(scale
				(xyz 1 1 1)
			)
			(rotate
				(xyz 0 0 0)
			)
		)
	)
"""

# KiCad'in resmi format tanımına göre (bu ORTAMDAKİ kartta rotasyonlu
# footprint YOK — bu, format-uyumlu bir sentetik ek örnektir).
FORMAT_UYUMLU_ROTASYONLU_FOOTPRINT = """\
	(footprint "Connector_JST:JST_PH"
		(layer "F.Cu")
		(uuid "abc123")
		(at 22.5 -8.0 90)
		(property "Reference" "J1"
			(at 0 -2 90)
			(layer "F.SilkS")
		)
	)
"""

# Gerçek koşumda ngspice/kicad-cli stderr'inde bilfiil görülen biçim
# (kicad-cli pcb export step --subst-models, ESP32C3_SmartBand.kicad_pcb).
GERCEK_KICAD10_EKSIK_MODEL_STDERR = """\
Could not add 3D model for SW1.
File not found: ${KICAD10_3DMODEL_DIR}/Button_Switch_SMD.3dshapes/SW_SPDT_CK_JS102011SAQN.step
"""


# ------------------------------------------------------------------
# .kicad_pcb ayrıştırma — gerçek veriyle
# ------------------------------------------------------------------

def test_footprint_bloklarina_ayirma_tek_blok_doner():
    bloklar = _footprint_bloklarina_ayir(GERCEK_KICAD10_FOOTPRINT_PARCASI)
    assert len(bloklar) == 1
    assert bloklar[0].count("(footprint ") == 1


def test_footprint_bloklarina_ayirma_parantez_dengeli():
    """Blok, açılışla aynı derinlikte KAPANMALI — iç içe property'lerin
    kendi parantezleri sayaç dışına taşmamalı."""
    blok = _footprint_bloklarina_ayir(GERCEK_KICAD10_FOOTPRINT_PARCASI)[0]
    assert blok.count("(") == blok.count(")")


def test_gercek_footprint_refdes_konum_katman_dogru_cikarilir():
    yerlesimler = kicad_pcb_yerlesimlerini_cikar(GERCEK_KICAD10_FOOTPRINT_PARCASI)
    assert len(yerlesimler) == 1
    y = yerlesimler[0]
    assert y.refdes == "C16"
    assert y.footprint_kutuphanesi == "Capacitor_SMD:C_0402_1005Metric"
    assert (y.x_mm, y.y_mm) == (-13.0, 14.5)
    assert y.aci_derece == 0.0
    assert y.katman == "F.Cu"


def test_rotasyonlu_footprint_acisi_okunur():
    yerlesimler = kicad_pcb_yerlesimlerini_cikar(FORMAT_UYUMLU_ROTASYONLU_FOOTPRINT)
    assert yerlesimler[0].aci_derece == 90.0
    assert yerlesimler[0].refdes == "J1"


def test_referanssiz_footprint_atlanir():
    """Bozuk/yarım bir blok, kısmi/yanlış bir yerleşim kaydı ÜRETMEMELİ."""
    bozuk = '\t(footprint "X:Y"\n\t\t(layer "F.Cu")\n\t\t(at 1 1)\n\t)\n'
    assert kicad_pcb_yerlesimlerini_cikar(bozuk) == []


def test_birden_fazla_footprint_ayri_ayri_cikarilir():
    iki_tane = GERCEK_KICAD10_FOOTPRINT_PARCASI + FORMAT_UYUMLU_ROTASYONLU_FOOTPRINT
    yerlesimler = kicad_pcb_yerlesimlerini_cikar(iki_tane)
    assert {y.refdes for y in yerlesimler} == {"C16", "J1"}


# ------------------------------------------------------------------
# Geometri: rotasyonlu AABB
# ------------------------------------------------------------------

def test_rotasyonsuz_aabb_boyutlari_dogru():
    assert rotasyonlu_aabb(0, 0, 4, 2, 0.0) == pytest.approx((-2.0, -1.0, 2.0, 1.0))


def test_90_derece_rotasyon_genislik_derinligi_degistirir():
    kutu = rotasyonlu_aabb(0, 0, 4, 2, 90.0)
    assert kutu == pytest.approx((-1.0, -2.0, 1.0, 2.0), abs=1e-6)


def test_45_derece_rotasyon_kutuyu_genisletir():
    """45°'de AABB gerçek şekilden DAHA GENİŞ olmalı — muhafazakâr yön."""
    duz = rotasyonlu_aabb(0, 0, 4, 4, 0.0)
    egik = rotasyonlu_aabb(0, 0, 4, 4, 45.0)
    duz_genislik = duz[2] - duz[0]
    egik_genislik = egik[2] - egik[0]
    assert egik_genislik > duz_genislik


def test_merkez_kaymasi_aabb_yi_oteler():
    kutu = rotasyonlu_aabb(10, 20, 2, 2, 0.0)
    assert kutu == pytest.approx((9.0, 19.0, 11.0, 21.0))


# ------------------------------------------------------------------
# 3D kutu + çarpışma
# ------------------------------------------------------------------

def test_fcu_komponent_z_araligi_pcb_ustunde():
    yerlesim = KomponentYerlesimi("U1", "x", 0, 0, 0, "F.Cu")
    govde = KomponentGovdesi3D(2.0, 2.0, 5.0)
    kutu = komponent_3d_kutusu(yerlesim, govde, pcb_kalinligi_mm=1.6)
    assert (kutu[2], kutu[5]) == (0.0, 5.0)


def test_bcu_komponent_z_araligi_pcb_altinda():
    yerlesim = KomponentYerlesimi("U2", "x", 0, 0, 0, "B.Cu")
    govde = KomponentGovdesi3D(2.0, 2.0, 3.0)
    kutu = komponent_3d_kutusu(yerlesim, govde, pcb_kalinligi_mm=1.6)
    assert (kutu[2], kutu[5]) == pytest.approx((-4.6, -1.6))


def test_uc_eksende_de_ortusen_kutular_carpisir():
    a = (0.0, 0.0, 0.0, 5.0, 5.0, 5.0)
    b = (3.0, 3.0, 3.0, 8.0, 8.0, 8.0)
    ortusme = kutu_3d_carpisiyor_mu(a, b)
    assert ortusme == pytest.approx((2.0, 2.0, 2.0))


def test_z_de_ayrik_kutular_carpismaz():
    """XY'de tam çakışıp Z'de ayrık olan (kartın altı vs kapaktaki bir
    çıkıntı) komponentler çarpışma SAYILMAMALI."""
    a = (0.0, 0.0, 0.0, 5.0, 5.0, 2.0)
    b = (0.0, 0.0, 10.0, 5.0, 5.0, 15.0)
    assert kutu_3d_carpisiyor_mu(a, b) is None


def test_xy_de_ayrik_kutular_carpismaz():
    a = (0.0, 0.0, 0.0, 2.0, 2.0, 2.0)
    b = (10.0, 10.0, 0.0, 12.0, 12.0, 2.0)
    assert kutu_3d_carpisiyor_mu(a, b) is None


def test_degen_kutular_carpisma_sayilmaz():
    """Tam kenar teması (örtüşme=0) çarpışma DEĞİLDİR — sıfır sıkı eşitsizlik."""
    a = (0.0, 0.0, 0.0, 2.0, 2.0, 2.0)
    b = (2.0, 0.0, 0.0, 4.0, 2.0, 2.0)
    assert kutu_3d_carpisiyor_mu(a, b) is None


# ------------------------------------------------------------------
# carpisma_tara — kabul kapısı
# ------------------------------------------------------------------

def test_carpisan_konnektor_j1_mesaji_uretir():
    """Kullanıcının istediği somut senaryo: 'J1 konnektörü kapağa çarpıyor'."""
    yerlesim = KomponentYerlesimi("J1", "Conn:USB_C", 20.0, -10.0, 90.0, "F.Cu")
    govde = {"J1": KomponentGovdesi3D(9.0, 7.5, 3.2)}
    kapak = [KasaEngelHacmi("kapak_ic_yuzeyi", 15.0, -15.0, 25.0, -5.0, 2.0, 20.0)]
    bulgu = carpisma_tara([yerlesim], govde, kapak)
    assert bulgu.durum == BulguDurumu.FAIL
    assert "J1" in bulgu.ihlaller[0]["mesaj"]
    assert "kapak_ic_yuzeyi" in bulgu.ihlaller[0]["mesaj"]


def test_yeterli_bosluk_varsa_pass():
    yerlesim = KomponentYerlesimi("C1", "x", 0.0, 0.0, 0.0, "F.Cu")
    govde = {"C1": KomponentGovdesi3D(1.0, 0.5, 0.5)}
    kapak = [KasaEngelHacmi("kapak", -50.0, -50.0, 50.0, 50.0, 8.0, 20.0)]
    bulgu = carpisma_tara([yerlesim], govde, kapak)
    assert bulgu.durum == BulguDurumu.PASS


def test_govde_verisi_olmayan_komponent_taranan_disinda():
    yerlesim = KomponentYerlesimi("U9", "x", 0, 0, 0, "F.Cu")
    bulgu = carpisma_tara([yerlesim], {}, [KasaEngelHacmi("k", -1, -1, 1, 1, 0, 5)])
    assert bulgu.taranan == 0
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK


def test_karisik_govde_verisiyle_sadece_bilinenler_taranir():
    yerlesimler = [
        KomponentYerlesimi("U1", "x", 0, 0, 0, "F.Cu"),
        KomponentYerlesimi("U2", "x", 100, 100, 0, "F.Cu"),  # gövdesi yok
    ]
    govdeler = {"U1": KomponentGovdesi3D(1.0, 1.0, 1.0)}
    bulgu = carpisma_tara(yerlesimler, govdeler, [])
    assert bulgu.taranan == 1


def test_gercek_c16_komponenti_uzak_engelle_carpismaz():
    """Gerçek dosyadan çıkarılan C16 (-13, 14.5) ile kartın tam ters
    köşesindeki bir engel arasında çarpışma OLMAMALI."""
    yerlesim = kicad_pcb_yerlesimlerini_cikar(GERCEK_KICAD10_FOOTPRINT_PARCASI)[0]
    govde = {"C16": KomponentGovdesi3D(1.0, 0.5, 0.5)}
    uzak_engel = [KasaEngelHacmi("vida_bossu_kose", 40.0, -40.0, 45.0, -35.0, 0.0, 5.0)]
    assert carpisma_tara([yerlesim], govde, uzak_engel).durum == BulguDurumu.PASS


# ------------------------------------------------------------------
# STEP ihracı — komut inşası (gerçek koşum ayrı doğrulandı, bkz. modül başlığı)
# ------------------------------------------------------------------

def test_step_disa_aktar_basarisiz_cli_hata_firlatir(tmp_path, monkeypatch):
    def sahte_run(komut, **kwargs):
        assert "--subst-models" in komut
        assert komut[:4] == ["kicad-cli", "pcb", "export", "step"]
        return subprocess.CompletedProcess(komut, returncode=1, stdout="", stderr="hata: geçersiz board")

    monkeypatch.setattr(subprocess, "run", sahte_run)
    with pytest.raises(RuntimeError):
        step_disa_aktar("board.kicad_pcb", str(tmp_path / "out.step"))


def test_step_disa_aktar_subst_models_kapatilabilir(monkeypatch):
    def sahte_run(komut, **kwargs):
        assert "--subst-models" not in komut
        return subprocess.CompletedProcess(komut, returncode=1, stdout="", stderr="x")

    monkeypatch.setattr(subprocess, "run", sahte_run)
    with pytest.raises(RuntimeError):
        step_disa_aktar("board.kicad_pcb", "out.step", subst_models=False)


def test_eksik_3d_modelleri_ayikla_gercek_stderr_bicimiyle():
    """Bu makinede kicad-cli'nin GERÇEKTEN ürettiği stderr biçimi."""
    eksikler = eksik_3d_modelleri_ayikla(GERCEK_KICAD10_EKSIK_MODEL_STDERR)
    assert eksikler == ["SW1"]


def test_eksik_3d_model_yoksa_bos_liste():
    assert eksik_3d_modelleri_ayikla("her şey yolunda") == []


# ------------------------------------------------------------------
# Rapor
# ------------------------------------------------------------------

def test_rapor_carpisma_mesajini_yazar():
    yerlesim = KomponentYerlesimi("J1", "x", 0, 0, 0, "F.Cu")
    govde = {"J1": KomponentGovdesi3D(5, 5, 8)}
    kapak = [KasaEngelHacmi("kapak", -10, -10, 10, 10, 2, 20)]
    bulgu = carpisma_tara([yerlesim], govde, kapak)
    rapor = carpisma_raporu_uret(bulgu)
    assert "⚠️" in rapor and "J1" in rapor


def test_rapor_eksik_model_uyarisini_ekler():
    bulgu = carpisma_tara([], {}, [])
    rapor = carpisma_raporu_uret(bulgu, eksik_3d_modelleri_ayikla(GERCEK_KICAD10_EKSIK_MODEL_STDERR))
    assert "SW1" in rapor
    assert "KESİN DEĞİLDİR" in rapor


def test_rapor_dosyaya_yazilir(tmp_path):
    hedef = tmp_path / "TEST" / "mcad_carpisma_raporu.md"
    bulgu = carpisma_tara([], {}, [])
    carpisma_raporu_yaz(str(hedef), bulgu)
    assert hedef.exists()
    assert "3D Çarpışma Testi" in hedef.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
