"""
uretim_zinciri_koprusu.py'nin BÖLÜM 4 (CPL/panelizasyon) fonksiyonları için
test suite. Ayrı dosya: mevcut `test_pcb_stackup_planner.py`/
`test_kicad_koprusu.py` konvansiyonuna uyar (modül-başına test dosyası),
ama tüm `uretim_zinciri_koprusu.py` zaten büyük olduğu için sadece bu yeni
bölüm için ayrı dosya açıldı.
"""

import pytest

from uretim_zinciri_koprusu import (
    RotasyonMapKaydi,
    rotation_map_versiyonla,
    rotation_map_degisti_mi,
    FootprintGeometrisi,
    generate_cpl_file,
    rotasyon_duzeltmesi_uygula,
    KutupluParca,
    KutupluParcaTipi,
    check_orientation,
    PanelKisiti,
    panelizasyon_kontrolu,
)


def _kayitlar():
    return [RotasyonMapKaydi(fab_adi="JLCPCB", footprint_lib_id="Package_TO_SOT_SMD:SOT-23-6", fab_ofset_derece=90.0)]


def test_rotation_map_versiyonlama_ayni_icerik_ayni_hash():
    v1 = rotation_map_versiyonla(_kayitlar())
    v2 = rotation_map_versiyonla(_kayitlar())
    assert v1.hash == v2.hash
    assert rotation_map_degisti_mi(v1, v2) is False


def test_rotation_map_versiyonlama_farkli_icerik_farkli_hash():
    v1 = rotation_map_versiyonla(_kayitlar())
    v2 = rotation_map_versiyonla(_kayitlar() + [RotasyonMapKaydi("JLCPCB", "LED_SMD:LED_0603", 180.0)])
    assert rotation_map_degisti_mi(v1, v2) is True


def test_generate_cpl_file_centroid_courtyard_merkezidir():
    fp = FootprintGeometrisi(
        refdes="D1", footprint_lib_id="Package_TO_SOT_SMD:SOT-23-6",
        footprint_origin=(0, 0), courtyard_bbox=(-1, -0.5, 3, 1.5),
        footprint_aci_derece=0.0, katman="F.Cu",
    )
    cpl = generate_cpl_file([fp], rotation_map_versiyonla(_kayitlar()))
    assert cpl[0]["MidX"] == pytest.approx(1.0)  # (-1+3)/2
    assert cpl[0]["MidY"] == pytest.approx(0.5)  # (-0.5+1.5)/2


def test_rotasyon_duzeltmesi_eslesen_footprinte_ofset_ekler():
    fp = FootprintGeometrisi(
        refdes="D1", footprint_lib_id="Package_TO_SOT_SMD:SOT-23-6",
        footprint_origin=(0, 0), courtyard_bbox=(-1, -0.5, 1, 0.5),
        footprint_aci_derece=0.0, katman="F.Cu",
    )
    v = rotation_map_versiyonla(_kayitlar())
    cpl = generate_cpl_file([fp], v)
    uyarilar = rotasyon_duzeltmesi_uygula(cpl, [fp], v)
    assert uyarilar == []
    assert cpl[0]["Rotation"] == pytest.approx(90.0)
    assert cpl[0]["_rotasyon_map_eslesti"] is True


def test_rotasyon_duzeltmesi_eslesmeyen_footprinte_uyari_verir():
    fp = FootprintGeometrisi(
        refdes="U1", footprint_lib_id="Bilinmeyen:Footprint",
        footprint_origin=(0, 0), courtyard_bbox=(-1, -1, 1, 1),
        footprint_aci_derece=45.0, katman="F.Cu",
    )
    v = rotation_map_versiyonla(_kayitlar())
    cpl = generate_cpl_file([fp], v)
    uyarilar = rotasyon_duzeltmesi_uygula(cpl, [fp], v)
    assert len(uyarilar) == 1
    assert cpl[0]["Rotation"] == pytest.approx(45.0)  # ofset uygulanmadı
    assert cpl[0]["_rotasyon_map_eslesti"] is False


def test_check_orientation_uyumlu_parcada_bulgu_yok():
    fp = FootprintGeometrisi(
        refdes="D1", footprint_lib_id="Package_TO_SOT_SMD:SOT-23-6",
        footprint_origin=(0, 0), courtyard_bbox=(-1, -0.5, 1, 0.5),
        footprint_aci_derece=0.0, katman="F.Cu",
    )
    v = rotation_map_versiyonla(_kayitlar())
    cpl = generate_cpl_file([fp], v)
    rotasyon_duzeltmesi_uygula(cpl, [fp], v)  # 0 + 90 = 90
    kutuplu = [KutupluParca("D1", KutupluParcaTipi.DIYOT, sematik_beklenen_aci_derece=90.0)]
    assert check_orientation(kutuplu, cpl) == []


def test_check_orientation_ters_montaj_yakalanir():
    fp = FootprintGeometrisi(
        refdes="D1", footprint_lib_id="Package_TO_SOT_SMD:SOT-23-6",
        footprint_origin=(0, 0), courtyard_bbox=(-1, -0.5, 1, 0.5),
        footprint_aci_derece=0.0, katman="F.Cu",
    )
    v = rotation_map_versiyonla(_kayitlar())
    cpl = generate_cpl_file([fp], v)
    rotasyon_duzeltmesi_uygula(cpl, [fp], v)  # gerçek: 90
    kutuplu = [KutupluParca("D1", KutupluParcaTipi.DIYOT, sematik_beklenen_aci_derece=270.0)]
    bulgular = check_orientation(kutuplu, cpl)
    assert len(bulgular) == 1
    assert "ters monte" in bulgular[0]


def test_panelizasyon_kontrolu_tum_kurallar_gecerse_bos():
    kisit = PanelKisiti(global_fiducial_sayisi=3, bga_local_fiducial_var_mi=True,
                         rail_genislik_mm=6.0, hassas_parca_depanel_mesafesi_mm=8.0)
    assert panelizasyon_kontrolu(kisit) == []


def test_panelizasyon_kontrolu_tum_ihlalleri_yakalar():
    kisit = PanelKisiti(global_fiducial_sayisi=1, bga_local_fiducial_var_mi=False,
                         rail_genislik_mm=3.0, hassas_parca_depanel_mesafesi_mm=1.0)
    bulgular = panelizasyon_kontrolu(kisit)
    assert len(bulgular) == 4
