"""hata_hafizasi.py için test suite.
Çalıştırmak için:  pytest -v test_hata_hafizasi.py
"""

import pytest

from hata_hafizasi import (
    BASLIK,
    HataHafizasi,
    HataKaydi,
    KontrolTipi,
    Sonuc,
    VARSAYILAN_HAFIZA_YOLU,
    benzerlik,
    drc_raporundan_kayit_uret,
    hafizaya_ogret,
    imza_uret,
    kaydi_markdown_a_cevir,
    markdown_i_kayitlara_cevir,
    mesaji_normalize_et,
    onceki_cozumleri_rapora_dok,
    oz_testleri_calistir,
    _etiket_tahmin_et,
    _testin_bos_olmadigini_kanitla,
)

CLEARANCE_1 = 'Clearance violation (net "GND" and net "+3V3") at (12.34, 56.78)'
CLEARANCE_2 = 'Clearance violation (net "GND" and net "+3V3") at (98.76, 54.32)'
CLEARANCE_FARKLI_NET = 'Clearance violation (net "SDA" and net "SCL") at (5.0, 5.0)'


# ------------------------------------------------------------------
# Normalizasyon / imza
# ------------------------------------------------------------------

def test_koordinat_yer_tutucuya_cevrilir():
    assert "<koord>" in mesaji_normalize_et(CLEARANCE_1)


def test_tirnakli_net_ismi_yer_tutucuya_cevrilir():
    n = mesaji_normalize_et(CLEARANCE_1)
    assert "<net>" in n
    assert "gnd" not in n


def test_refdes_yer_tutucuya_cevrilir():
    assert "<cref>" in mesaji_normalize_et("Courtyard overlap C7 and C8")


def test_ayni_sinif_farkli_koordinat_ayni_imza():
    """Hafızanın çalışmasının ön koşulu."""
    assert imza_uret(CLEARANCE_1) == imza_uret(CLEARANCE_2)


def test_farkli_sinif_farkli_imza():
    assert imza_uret(CLEARANCE_1) != imza_uret("Track width too small (0.15mm < 0.2mm)")


def test_imza_8_karakter_ve_kararli():
    imza = imza_uret(CLEARANCE_1)
    assert len(imza) == 8
    assert imza == imza_uret(CLEARANCE_1)


def test_benzerlik_ayni_mesajda_1():
    assert benzerlik(CLEARANCE_1, CLEARANCE_1) == pytest.approx(1.0)


def test_benzerlik_alakasiz_mesajda_dusuk():
    assert benzerlik(CLEARANCE_1, "Symbol pin not connected to any net") < 0.55


def test_bos_mesaj_benzerligi_sifir():
    assert benzerlik("", CLEARANCE_1) == 0.0


# ------------------------------------------------------------------
# Markdown yaz/oku turu
# ------------------------------------------------------------------

def test_kayit_markdown_a_cevrilir():
    kayit = HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "sıkışık", "C7 kaydırıldı",
                      Sonuc.COZULDU, "P1", etiketler=["drc", "clearance"])
    md = kaydi_markdown_a_cevir(kayit)
    assert md.startswith("## DRC — ")
    assert "- **cozum:** C7 kaydırıldı" in md
    assert "#drc #clearance" in md


def test_markdown_geri_ayristirilir():
    kayit = HataKaydi(KontrolTipi.ERC, "Pin not driven", "PWR_FLAG yok",
                      "kök neden bulundu, PWR_FLAG eklendi", Sonuc.COZULDU, "P2")
    geri = markdown_i_kayitlara_cevir(BASLIK + kaydi_markdown_a_cevir(kayit))
    assert len(geri) == 1
    assert geri[0].tip == KontrolTipi.ERC
    assert geri[0].sonuc == Sonuc.COZULDU
    assert geri[0].imza == kayit.imza


def test_imzasiz_bolum_atlanir():
    """Yarım kayıt yanlış öneriye dönüşebilir — ayrıştırılmaz."""
    bozuk = "## DRC — x\n- **mesaj:** bir şey\n\n"
    assert markdown_i_kayitlara_cevir(BASLIK + bozuk) == []


def test_bilinmeyen_tip_ve_sonuc_varsayilana_duser():
    md = (
        "## GARIP — abc12345\n- **tip:** GARIP\n- **imza:** abc12345\n"
        "- **mesaj:** x\n- **sonuc:** BILINMEYEN\n\n"
    )
    kayit = markdown_i_kayitlara_cevir(BASLIK + md)[0]
    assert kayit.tip == KontrolTipi.DIGER
    assert kayit.sonuc == Sonuc.NEEDS_HUMAN


def test_varsayilan_yol_proje_icinde():
    """Kullanıcının kişisel Obsidian kasasına sorulmadan yazılmaz."""
    assert VARSAYILAN_HAFIZA_YOLU.startswith("HAFIZA/")


# ------------------------------------------------------------------
# HataHafizasi — kaydet / oku / ara
# ------------------------------------------------------------------

def test_hafiza_yoksa_okuma_bos_liste(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "yok.md"))
    assert hafiza.kayitlari_oku() == []


def test_ilk_kayit_dosyayi_olusturur(tmp_path):
    yol = tmp_path / "alt" / "Hata_Hafizasi.md"
    hafiza = HataHafizasi(str(yol))
    assert hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "b", Sonuc.COZULDU))
    assert yol.exists()
    assert "tags: [pcb, hata-hafizasi" in yol.read_text(encoding="utf-8")


def test_ayni_kayit_ikinci_kez_eklenmez(tmp_path):
    """Aynı DRC hatası bir koşuda 40 kez çıkabilir; hafıza şişmemeli."""
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    kayit = HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "b", Sonuc.COZULDU)
    assert hafiza.kaydet(kayit) is True
    assert hafiza.kaydet(kayit) is False
    assert len(hafiza.kayitlari_oku()) == 1


def test_ayni_imza_farkli_cozum_ayri_kayit(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "cozum-1", Sonuc.COZULDU))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "cozum-2", Sonuc.BASARISIZ))
    assert len(hafiza.kayitlari_oku()) == 2


def test_imza_esleşmesi_farkli_koordinatta_da_bulur(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "sıkışık", "C7 kaydırıldı", Sonuc.COZULDU))
    sonuclar = hafiza.benzer_kayitlari_bul(CLEARANCE_2)
    assert len(sonuclar) == 1
    assert sonuclar[0][0] == 1.0


def test_alakasiz_mesaj_esleşmez(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "b", Sonuc.COZULDU))
    assert hafiza.benzer_kayitlari_bul("Symbol pin not connected to any net") == []


def test_tip_filtresi_calisir(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a", "b", Sonuc.COZULDU))
    assert hafiza.benzer_kayitlari_bul(CLEARANCE_1, tip=KontrolTipi.ERC) == []
    assert hafiza.benzer_kayitlari_bul(CLEARANCE_1, tip=KontrolTipi.DRC)


# ------------------------------------------------------------------
# cozum_oner — başarısızları ASLA önermez
# ------------------------------------------------------------------

def test_basarisiz_cozum_oneri_olarak_sunulmaz(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a",
                            "iz genişliği 0.15mm'ye düşürüldü", Sonuc.BASARISIZ))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a",
                            "C7 2mm kaydırıldı", Sonuc.COZULDU))
    gruplar = hafiza.cozum_oner(CLEARANCE_2)
    assert [o["cozum"] for o in gruplar["oneriler"]] == ["C7 2mm kaydırıldı"]
    assert "0.15mm" in gruplar["denenmis_basarisizlar"][0]["cozum"]


def test_needs_human_gecmisi_ayri_grupta(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "mimari", "", Sonuc.NEEDS_HUMAN))
    gruplar = hafiza.cozum_oner(CLEARANCE_1)
    assert gruplar["insan_gerekenler"] and not gruplar["oneriler"]


def test_hafiza_bossa_tum_gruplar_bos(tmp_path):
    gruplar = HataHafizasi(str(tmp_path / "h.md")).cozum_oner(CLEARANCE_1)
    assert gruplar == {"oneriler": [], "denenmis_basarisizlar": [], "insan_gerekenler": []}


# ------------------------------------------------------------------
# DRC raporundan otomatik öğrenme
# ------------------------------------------------------------------

RAPOR = {
    "violations": [
        {"severity": "error", "description": CLEARANCE_1},
        {"severity": "error", "description": CLEARANCE_2},   # aynı sınıf, tekilleşmeli
        {"severity": "warning", "description": "Silkscreen overlaps pad R5"},
        {"severity": "error", "description": "Track width too small (0.15mm < 0.2mm)"},
    ]
}


def test_ayni_sinif_ihlaller_tekillesir():
    kayitlar = drc_raporundan_kayit_uret(RAPOR, "kök", "çözüm", Sonuc.COZULDU)
    assert len(kayitlar) == 2  # clearance (tek) + track width


def test_uyarilar_varsayilan_olarak_atlanir():
    kayitlar = drc_raporundan_kayit_uret(RAPOR, "k", "c", Sonuc.COZULDU)
    assert not any("Silkscreen" in k.mesaj for k in kayitlar)


def test_uyarilar_istenirse_dahil_edilir():
    kayitlar = drc_raporundan_kayit_uret(RAPOR, "k", "c", Sonuc.COZULDU, sadece_hatalar=False)
    assert any("Silkscreen" in k.mesaj for k in kayitlar)


def test_bos_aciklamali_ihlal_atlanir():
    kayitlar = drc_raporundan_kayit_uret(
        {"violations": [{"severity": "error", "description": "  "}]}, "k", "c", Sonuc.COZULDU
    )
    assert kayitlar == []


def test_etiket_tahmini_konuya_gore():
    assert _etiket_tahmin_et(CLEARANCE_1) == "clearance"
    assert _etiket_tahmin_et("Track width too small") == "iz-genisligi"
    assert _etiket_tahmin_et("bambaşka bir şey") == "genel"


def test_hafizaya_ogret_eklenen_sayisini_doner(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    assert hafizaya_ogret(hafiza, RAPOR, "kök", "çözüm", Sonuc.COZULDU, "P1") == 2
    assert hafizaya_ogret(hafiza, RAPOR, "kök", "çözüm", Sonuc.COZULDU, "P1") == 0


# ------------------------------------------------------------------
# Rapor
# ------------------------------------------------------------------

def test_rapor_gecmis_cozumu_yazar(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "sıkışık",
                            "C7 2mm kaydırıldı", Sonuc.COZULDU, "OncekiProje"))
    rapor = onceki_cozumleri_rapora_dok(hafiza, RAPOR)
    assert "İŞE YARAYAN" in rapor
    assert "C7 2mm kaydırıldı" in rapor
    assert "OncekiProje" in rapor


def test_rapor_denemeyin_uyarisini_yazar(tmp_path):
    hafiza = HataHafizasi(str(tmp_path / "h.md"))
    hafiza.kaydet(HataKaydi(KontrolTipi.DRC, CLEARANCE_1, "a",
                            "iz genişliği düşürüldü", Sonuc.BASARISIZ))
    assert "DENEMEYİN" in onceki_cozumleri_rapora_dok(hafiza, RAPOR)


def test_rapor_bos_hafizayi_acikca_soyler(tmp_path):
    """'Hafızada yok' ile 'hafızaya bakılmadı' karışmamalı."""
    rapor = onceki_cozumleri_rapora_dok(HataHafizasi(str(tmp_path / "h.md")), RAPOR)
    assert "hafızada eşleşme YOK" in rapor
    assert "Hafıza tarandı" in rapor


def test_rapor_ihlalsiz_raporda_bunu_yazar(tmp_path):
    rapor = onceki_cozumleri_rapora_dok(HataHafizasi(str(tmp_path / "h.md")), {"violations": []})
    assert "raporda ihlal yok" in rapor


def test_rapor_ayni_imzayi_tekrarlamaz(tmp_path):
    rapor = onceki_cozumleri_rapora_dok(HataHafizasi(str(tmp_path / "h.md")), RAPOR)
    assert rapor.count(f"`{imza_uret(CLEARANCE_1)}`") == 1


# ------------------------------------------------------------------
# Öz test
# ------------------------------------------------------------------

def test_fault_injection_gercekten_kirilir():
    assert _testin_bos_olmadigini_kanitla()


def test_oz_testleri_temiz():
    assert oz_testleri_calistir() == []
