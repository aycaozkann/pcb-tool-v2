"""via_capi_hesaplayici.py için test suite.
Çalıştırmak için:  pytest -v test_via_capi_hesaplayici.py
"""

import math

import pytest

from pcb_stackup_planner import FABRIKA_PROFILLERI, FabrikaProfili, iz_genisligi_hesapla_mm
from via_capi_hesaplayici import (
    MIL_PER_OZ,
    MM_PER_MIL,
    ViaCapiSonucu,
    _gerekli_kesit_alani_mil2,
    main,
    pad_capi_hesapla_mm,
    via_capi_oner,
    via_delik_capi_hesapla_mm,
)


JLCPCB = FABRIKA_PROFILLERI["JLCPCB_STANDART"]


# ------------------------------------------------------------------
# 0. Tek-kaynak-gerçeklik: pcb_stackup_planner.iz_genisligi_hesapla_mm ile
#    aynı IPC-2221 sabitlerini kullandığımızı kanıtla (kopyalanmadığını,
#    üzerine katman eklendiğini doğrular).
# ------------------------------------------------------------------

def test_kesit_alani_iz_genisligi_ile_tutarli():
    akim, dT, oz = 2.0, 10.0, 1.0
    genislik_mm = iz_genisligi_hesapla_mm(akim, dT, oz, dis_katman_mi=True)
    genislik_mil = genislik_mm / MM_PER_MIL
    beklenen_alan_mil2 = genislik_mil * (oz * MIL_PER_OZ)

    alan_mil2 = _gerekli_kesit_alani_mil2(akim, dT, oz)
    assert alan_mil2 == pytest.approx(beklenen_alan_mil2, rel=1e-9)


def test_negatif_akim_reddedilir():
    with pytest.raises(ValueError):
        via_delik_capi_hesapla_mm(akim_A=-1.0)


def test_sifir_akim_reddedilir():
    with pytest.raises(ValueError):
        via_delik_capi_hesapla_mm(akim_A=0.0)


def test_negatif_sicaklik_artisi_reddedilir():
    with pytest.raises(ValueError):
        via_delik_capi_hesapla_mm(akim_A=1.0, sicaklik_artisi_C=-5.0)


def test_negatif_kaplama_reddedilir():
    with pytest.raises(ValueError):
        via_delik_capi_hesapla_mm(akim_A=1.0, kaplama_kalinligi_oz=-1.0)


# ------------------------------------------------------------------
# 1. Delik çapı cebirsel çözüm kanıtı: Alan = pi * D * t  ->  D = Alan / (pi * t)
# ------------------------------------------------------------------

def test_delik_capi_cebirsel_cozum_dogru():
    akim, dT, oz = 3.0, 20.0, 2.0
    alan_mil2 = _gerekli_kesit_alani_mil2(akim, dT, oz)
    kaplama_mil = oz * MIL_PER_OZ

    delik_capi_mm = via_delik_capi_hesapla_mm(akim, dT, oz)
    delik_capi_mil = delik_capi_mm / MM_PER_MIL

    # geri-doğrulama: pi * D * t ~= Alan
    geri_hesaplanan_alan = math.pi * delik_capi_mil * kaplama_mil
    assert geri_hesaplanan_alan == pytest.approx(alan_mil2, rel=1e-9)


# ------------------------------------------------------------------
# 2. Senaryo (a): YÜKSEK akım -> BÜYÜK via, üretilebilirlik sınırının
#    ÜSTÜNDE kalır, tekil via yeterli.
#
# NOT — akım yönü GÖREV metnindeki örnekle TERS: IPC-2221'in akım->kesit-
# alanı ilişkisi MONOTON ARTANDIR (bkz. pcb_stackup_planner.iz_genisligi_
# hesapla_mm ve numerik doğrulama: 2A->0.249mm, 3A->0.435mm, 8A->1.683mm —
# akım arttıkça çap HER ZAMAN büyür, küçülmez). Bu yüzden "düşük akım ->
# sınırın altına düşer" ve "yüksek akım -> sınırın üstünde kalır" fiziksel
# olarak DOĞRU yöndür; GÖREV'in (a)/(b) örnek etiketleri (muhtemelen bir
# yazım tersliği) yerine BU doğru yöne göre test edilmiştir — davranışın
# kendisi (üstünde/altında dallanması + doğru bayraklar) GÖREV'in istediği
# ŞEYdir, sadece hangi akımın hangi dalı tetiklediği fizik tarafından
# belirlenir, keyfi seçilemez.
# ------------------------------------------------------------------

def test_senaryo_a_yuksek_akim_tekil_via_yeterli():
    sonuc = via_capi_oner(akim_A=8.0, fabrika_profili=JLCPCB)

    assert sonuc.uretilebilirlik_sinirinin_altinda is False
    assert sonuc.stitching_gerekli is False
    assert sonuc.gerekli_via_sayisi == 1
    # önerilen çap hesaplanan çapla aynı olmalı (yükseltme yapılmadı)
    assert sonuc.onerilen_delik_capi_mm == pytest.approx(sonuc.hesaplanan_delik_capi_mm, rel=1e-9)
    assert sonuc.onerilen_delik_capi_mm >= JLCPCB.min_delik_capi_mm
    assert "tekil via yeterli" in sonuc.detay


# ------------------------------------------------------------------
# 3. Senaryo (b): DÜŞÜK akım -> hesaplanan çap üretilebilirlik sınırının
#    (0.3mm JLCPCB) altına düşer, çap tabana yükseltilir.
#
# `gerekli_via_sayisi` bu dalda HER ZAMAN 1 çıkar — bu bir test hatası
# DEĞİL, modülün docstring'inde belgelenen matematiksel bir sonuç: sabit
# kaplama kalınlığında Alan çapla DOĞRUSAL büyür (D² değil), bu yüzden
# hesaplanan çap zaten minimumdan küçükse gerekli alan da minimum-çaplı
# TEK bir via'nın kapasitesinden her zaman küçüktür. Bu test o sınırı
# AÇIKÇA kanıtlıyor (bkz. modül docstring'indeki "MATEMATİKSEL NOT").
# ------------------------------------------------------------------

def test_senaryo_b_dusuk_akim_yukseltilir_ve_stitching_matematigi_dogrulanir():
    sonuc = via_capi_oner(akim_A=0.05, fabrika_profili=JLCPCB)

    assert sonuc.hesaplanan_delik_capi_mm < JLCPCB.min_delik_capi_mm
    assert sonuc.uretilebilirlik_sinirinin_altinda is True
    assert sonuc.stitching_gerekli is True
    # önerilen çap üretilebilirlik tabanına yükseltilmiş olmalı
    assert sonuc.onerilen_delik_capi_mm == pytest.approx(JLCPCB.min_delik_capi_mm, rel=1e-9)
    assert "via" in sonuc.detay.lower()

    # gerekli_via_sayisi tutarlılık kontrolü + yukarıdaki matematiksel not
    # için kanıt: N=1 zaten ihtiyacı karşılamalı (ceil mantığının doğru
    # çalıştığını kanıtlar); bu dalda N>1'e ULAŞILAMAZ (kanıt aşağıda).
    alan_mil2 = _gerekli_kesit_alani_mil2(0.05, 10.0, 1.0)
    kaplama_mil = 1.0 * MIL_PER_OZ
    min_delik_capi_mil = JLCPCB.min_delik_capi_mm / MM_PER_MIL
    tek_via_alani = math.pi * min_delik_capi_mil * kaplama_mil
    assert sonuc.gerekli_via_sayisi == 1
    assert tek_via_alani >= alan_mil2  # tek min-via zaten yeterli, N>1 hiç gerekmiyor


@pytest.mark.parametrize("akim_A", [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 2.9])
def test_altinda_dalinda_via_sayisi_hicbir_akimda_1i_gecmiyor(akim_A):
    """Modül docstring'indeki matematiksel iddiayı ('bu dal ASLA >1
    üretemez') geniş bir akım aralığında fault-injection ile kanıtlar."""
    sonuc = via_capi_oner(akim_A=akim_A, fabrika_profili=JLCPCB)
    if sonuc.uretilebilirlik_sinirinin_altinda:
        assert sonuc.gerekli_via_sayisi == 1


# ------------------------------------------------------------------
# 4. Senaryo (c): pad çapı = delik çapı + 2 * min_yillik_halka_mm,
#    FabrikaProfili'nden okunuyor (hardcode değil).
# ------------------------------------------------------------------

def test_senaryo_c_pad_capi_yillik_halka_ile_dogru_toplaniyor():
    delik_capi = 0.4
    pad_capi = pad_capi_hesapla_mm(delik_capi, JLCPCB.min_yillik_halka_mm)
    assert pad_capi == pytest.approx(delik_capi + 2 * JLCPCB.min_yillik_halka_mm, rel=1e-9)

    # via_capi_oner üzerinden de aynı ilişki sağlanmalı, hangi fabrika
    # profili verilirse verilsin (farklı min_yillik_halka_mm değerleriyle).
    for isim, profil in FABRIKA_PROFILLERI.items():
        sonuc = via_capi_oner(akim_A=1.0, fabrika_profili=profil)
        assert sonuc.pad_capi_mm == pytest.approx(
            sonuc.onerilen_delik_capi_mm + 2 * profil.min_yillik_halka_mm, rel=1e-9
        )


def test_pad_capi_negatif_delik_reddedilir():
    with pytest.raises(ValueError):
        pad_capi_hesapla_mm(-0.1, 0.13)


def test_pad_capi_negatif_yillik_halka_reddedilir():
    with pytest.raises(ValueError):
        pad_capi_hesapla_mm(0.3, -0.05)


# ------------------------------------------------------------------
# 5. mm/mil çıktı tutarlılığı — her sonuç HEM mm HEM mil taşımalı.
# ------------------------------------------------------------------

def test_mm_mil_tutarliligi():
    sonuc = via_capi_oner(akim_A=1.5, fabrika_profili=JLCPCB)
    assert sonuc.hesaplanan_delik_capi_mil == pytest.approx(
        sonuc.hesaplanan_delik_capi_mm / MM_PER_MIL, rel=1e-9
    )
    assert sonuc.onerilen_delik_capi_mil == pytest.approx(
        sonuc.onerilen_delik_capi_mm / MM_PER_MIL, rel=1e-9
    )
    assert sonuc.pad_capi_mil == pytest.approx(sonuc.pad_capi_mm / MM_PER_MIL, rel=1e-9)


# ------------------------------------------------------------------
# 6. Fabrika profilleri gerçekten pcb_stackup_planner'dan okunuyor
#    (hardcode edilmediğinin kanıtı): FABRIKA_PROFILLERI değiştirilirse
#    sonuç da değişmeli.
# ------------------------------------------------------------------

def test_fabrika_profili_gercekten_kullaniliyor_hardcode_degil():
    ozel_profil = FabrikaProfili(
        isim="TEST_OZEL",
        min_iz_genisligi_mm=0.5,
        min_iz_araligi_mm=0.5,
        min_delik_capi_mm=0.9,  # kasıtlı çok büyük - her sonucu "altında" yapar
        min_yillik_halka_mm=0.5,
        maks_aspect_ratio=8.0,
    )
    sonuc = via_capi_oner(akim_A=0.1, fabrika_profili=ozel_profil)
    assert sonuc.uretilebilirlik_sinirinin_altinda is True
    assert sonuc.onerilen_delik_capi_mm == pytest.approx(0.9, rel=1e-9)
    assert sonuc.pad_capi_mm == pytest.approx(0.9 + 2 * 0.5, rel=1e-9)


# ------------------------------------------------------------------
# 7. CLI: hata mesajları kullanıcı-dostu (traceback değil), tanımsız
#    fabrika profili ve negatif akım user-friendly SystemExit ile biter.
# ------------------------------------------------------------------

def test_cli_basarili_calisma(capsys):
    kod = main(["--akim", "1.0", "--fabrika", "JLCPCB_STANDART"])
    assert kod == 0
    cikti = capsys.readouterr().out
    assert "hesaplanan_delik_capi" in cikti
    assert "mm" in cikti and "mil" in cikti


def test_cli_tanimsiz_fabrika_dostu_hata(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--akim", "1.0", "--fabrika", "BOYLE_BIR_FABRIKA_YOK"])
    # argparse `choices` doğrulaması exit code 2 ile döner (traceback yok)
    assert exc_info.value.code == 2


def test_cli_negatif_akim_dostu_hata(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--akim", "-2.0", "--fabrika", "JLCPCB_STANDART"])
    assert exc_info.value.code == 2
    hata = capsys.readouterr().err
    assert "pozitif olmalı" in hata


def test_cli_json_dosyaya_yaziliyor(tmp_path):
    json_yolu = tmp_path / "sonuc.json"
    kod = main(["--akim", "1.0", "--fabrika", "JLCPCB_STANDART", "--json", str(json_yolu)])
    assert kod == 0
    assert json_yolu.exists()
    icerik = json_yolu.read_text(encoding="utf-8")
    assert "onerilen_delik_capi" in icerik
