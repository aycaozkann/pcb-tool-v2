"""
kicad_koprusu.py için test suite.

NOT: Bu testler SAF/dosya-bağımsız fonksiyonları kapsar (net_class_json_uret,
drc_raporunu_ozetle, drc_temiz_mi, erc_raporunu_ozetle, erc_temiz_mi).
`drc_calistir`/`erc_calistir`'in ÇALIŞTIRILMASI (gerçek kicad-cli subprocess),
`net_classleri_projeye_yaz` (gerçek .kicad_pro şeması) ve
`canli_baglanti_kur`/`aktif_board_ozeti_al` (gerçek KiCad oturumu) burada
TEST EDİLEMEDİ. AMA: bu iki fonksiyonun ÜRETTİĞİ JSON'un şeması artık
doğrulanmadı DEĞİL — `GERCEK_KICAD10_ERC_YAPISI` ve `unconnected_items`
testleri, bu makinede gerçek `kicad-cli pcb drc`/`sch erc --format json`
çalıştırılıp gerçek `ESP32C3_SmartBand` proje dosyalarına karşı elde edilen
GERÇEK şemayı yansıtır (bkz. `kicad_koprusu.py::erc_calistir` ve
`_drc_tum_ihlaller` docstring'leri).
"""

import pytest

from pcb_stackup_planner import DiferansiyelCift, AraBirimTuru
from kicad_koprusu import (
    net_class_json_uret,
    drc_raporunu_ozetle,
    drc_temiz_mi,
    erc_raporunu_ozetle,
    erc_temiz_mi,
    sema_taninmadi_mi,
    DuzlemPoligonu,
    IzSegmenti,
    check_reference_plane_continuity,
    insert_test_points,
    tp_kapsam_kontrolu,
    generate_bringup_checklist,
    TpSinifi,
)


def test_net_class_json_temel_alanlari_dogru():
    cift = DiferansiyelCift(
        isim="USB_D+/D-", arayuz=AraBirimTuru.USB3_x,
        uzunluk_pozitif_mm=42.0, uzunluk_negatif_mm=41.9, veri_hizi_Gbps=5.0,
    )
    sonuc = net_class_json_uret(cift, track_width_mm=0.2, dp_gap_mm=0.127,
                                  net_isimleri=["USB_D+", "USB_D-"])
    assert sonuc["track_width"] == 0.2
    assert sonuc["diff_pair_gap"] == 0.127
    assert sonuc["nets"] == ["USB_D+", "USB_D-"]


def test_net_class_isim_kicad_uyumlu_karakterlere_cevrilir():
    cift = DiferansiyelCift(
        isim="USB_D+/D-", arayuz=AraBirimTuru.USB3_x,
        uzunluk_pozitif_mm=1.0, uzunluk_negatif_mm=1.0,
    )
    sonuc = net_class_json_uret(cift, 0.2, 0.127, ["USB_D+", "USB_D-"])
    # boşluk, '/', '+', '-' gibi karakterler net class ismi için sorunlu olabilir
    assert " " not in sonuc["name"]
    assert "/" not in sonuc["name"]
    assert "+" not in sonuc["name"]


def test_drc_raporu_ozetleme_ihlalleri_okunabilir_satira_cevirir():
    rapor = {
        "violations": [
            {"severity": "error", "description": "Clearance violation between X and Y"},
            {"severity": "warning", "description": "Silkscreen overlap"},
        ]
    }
    ozet = drc_raporunu_ozetle(rapor)
    assert len(ozet) == 2
    assert "error" in ozet[0]
    assert "warning" in ozet[1]


def test_drc_raporu_bos_ihlal_listesinde_bos_ozet_dondurur():
    assert drc_raporunu_ozetle({"violations": []}) == []
    assert drc_raporunu_ozetle({}) == []


def test_drc_temiz_mi_hata_yoksa_true():
    rapor = {"violations": [{"severity": "warning", "description": "x"}]}
    assert drc_temiz_mi(rapor) is True


def test_drc_temiz_mi_hata_varsa_false():
    rapor = {"violations": [{"severity": "error", "description": "x"}]}
    assert drc_temiz_mi(rapor) is False


def test_drc_temiz_mi_bos_raporda_true():
    assert drc_temiz_mi({}) is True


# ------------------------------------------------------------------
# REGRESYON — gerçek kicad-cli JSON şemasıyla bu makinede doğrulandı
# (kicad-cli pcb drc / sch erc --format json, KiCad 10.0.4,
# ESP32C3_SmartBand.kicad_pcb/.kicad_sch). Dış incelemede "ERC şeması
# doğrulanmadı" olarak işaretlenen P1 bulgusu buradaki testlerle kapatıldı
# — ve gerçek koşum, dış incelemenin farkına bile varmadığı DAHA CİDDİ bir
# ikinci kaçağı (unconnected_items) ortaya çıkardı.
# ------------------------------------------------------------------

def test_drc_unconnected_items_de_taranir():
    """GERÇEK bulgu: DRC raporunda ihlaller İKİ ayrı anahtar altında gelir
    — `violations` VE `unconnected_items`. Önceki sürüm sadece ilkine
    bakıyordu; gerçek board'da (ESP32C3_SmartBand) 6 tane 'error' seviyeli
    unconnected_items vardı ve SESSİZCE PASS sayılıyordu."""
    rapor = {
        "violations": [],
        "unconnected_items": [
            {"severity": "error", "description": "Missing connection between items"},
        ],
    }
    assert drc_temiz_mi(rapor) is False
    ozet = drc_raporunu_ozetle(rapor)
    assert len(ozet) == 1
    assert "error" in ozet[0]


def test_drc_unconnected_items_yoksa_eskisi_gibi_calisir():
    """`unconnected_items` anahtarı hiç yoksa (eski/farklı bir kicad-cli
    sürümü) geriye dönük uyumluluk bozulmamalı."""
    assert drc_temiz_mi({"violations": []}) is True
    assert drc_temiz_mi({"violations": [{"severity": "error", "description": "x"}]}) is False


# --- ERC şeması: sheets[].violations — üst seviye 'violations' DEĞİL ---
# (gerçek `kicad-cli sch erc --format json` çıktısının BİREBİR yapısı)
GERCEK_KICAD10_ERC_YAPISI = {
    "$schema": "https://schemas.kicad.org/erc.v1.json",
    "sheets": [
        {
            "path": "/",
            "violations": [
                {"severity": "warning", "description": "Label connected to only one pin", "type": "isolated_pin_label"},
                {"severity": "error", "description": "Pin not driven", "type": "pin_not_driven"},
            ],
        }
    ],
}


def test_erc_gercek_semada_ihlaller_okunur():
    """ESKİ davranış (üst seviye 'violations' arayan `drc_raporunu_ozetle`)
    bu GERÇEK ERC yapısında HER ZAMAN boş liste bulup sessizce PASS
    derdi (gerçek şematikle test edilince ortaya çıktı: 7 gerçek uyarı
    varken 0 döndürüyordu)."""
    ozet = erc_raporunu_ozetle(GERCEK_KICAD10_ERC_YAPISI)
    assert len(ozet) == 2
    assert any("Pin not driven" in s for s in ozet)


def test_erc_gercek_semada_error_varsa_kirli():
    assert erc_temiz_mi(GERCEK_KICAD10_ERC_YAPISI) is False


def test_erc_sadece_uyari_varsa_temiz():
    sema = {"sheets": [{"path": "/", "violations": [
        {"severity": "warning", "description": "x"}
    ]}]}
    assert erc_temiz_mi(sema) is True


def test_erc_birden_fazla_sayfa_hepsi_toplanir():
    """Hiyerarşik şematikte birden fazla `sheets[]` girdisi olabilir —
    sadece ilkine bakmak diğer sayfalardaki hataları kaçırır."""
    sema = {
        "sheets": [
            {"path": "/", "violations": [{"severity": "warning", "description": "a"}]},
            {"path": "/power/", "violations": [{"severity": "error", "description": "b"}]},
        ]
    }
    assert len(erc_raporunu_ozetle(sema)) == 2
    assert erc_temiz_mi(sema) is False


def test_erc_bos_sheets_temiz_sayilir():
    assert erc_temiz_mi({"sheets": []}) is True
    assert erc_raporunu_ozetle({"sheets": []}) == []


def test_sema_taninmadi_mi_drc_semasini_tanir():
    assert sema_taninmadi_mi({"violations": []}) is False


def test_sema_taninmadi_mi_erc_semasini_tanir():
    assert sema_taninmadi_mi({"sheets": []}) is False


def test_sema_taninmadi_mi_bilinmeyen_semada_true():
    """Fail-closed: ne 'violations' ne 'sheets' varsa, bu bilinmeyen bir
    şemadır — `erc_temiz_mi`/`drc_temiz_mi`'nin 'True' dönmesi buna
    GÜVENMEDEN kabul edilmemeli."""
    assert sema_taninmadi_mi({"baska_bir_anahtar": []}) is True
    assert sema_taninmadi_mi({}) is True


def test_tekrarlanan_ihlal_tespit_esik_alti_bosdur():
    from kicad_koprusu import tekrarlanan_ihlal_tespit_et
    tek_rapor = {"violations": [{"severity": "error", "description": "Clearance violation X"}]}
    assert tekrarlanan_ihlal_tespit_et([tek_rapor, tek_rapor], esik=3) == []


def test_tekrarlanan_ihlal_3_kez_ayni_ihlal_tespit_edilir():
    from kicad_koprusu import tekrarlanan_ihlal_tespit_et
    ayni_ihlal = {"violations": [{"severity": "error", "description": "Clearance violation X"}]}
    sonuc = tekrarlanan_ihlal_tespit_et([ayni_ihlal, ayni_ihlal, ayni_ihlal], esik=3)
    assert "[error] Clearance violation X" in sonuc


def test_tekrarlanan_ihlal_farkli_ihlallerde_bos_doner():
    from kicad_koprusu import tekrarlanan_ihlal_tespit_et
    r1 = {"violations": [{"severity": "error", "description": "Clearance violation X"}]}
    r2 = {"violations": [{"severity": "error", "description": "Different violation Y"}]}
    r3 = {"violations": [{"severity": "error", "description": "Clearance violation X"}]}
    assert tekrarlanan_ihlal_tespit_et([r1, r2, r3], esik=3) == []


def test_custom_dru_yaz_tek_kural_dogru_formatta(tmp_path):
    from kicad_koprusu import custom_dru_yaz, OzelDrcKurali
    hedef = tmp_path / "proje.kicad_dru"
    kural = OzelDrcKurali(
        isim="Yüksek Akım Yolları",
        net_class_kosulu="HIGH_CURRENT",
        min_iz_genisligi_mm=1.5,
    )
    custom_dru_yaz(str(hedef), [kural])
    icerik = hedef.read_text(encoding="utf-8")
    assert "HIGH_CURRENT" in icerik
    assert "track_width (min 1.5mm)" in icerik
    assert '(rule "Yüksek Akım Yolları"' in icerik


def test_custom_dru_yaz_birden_fazla_kural_ayri_bloklar_olusturur(tmp_path):
    from kicad_koprusu import custom_dru_yaz, OzelDrcKurali
    hedef = tmp_path / "proje.kicad_dru"
    kurallar = [
        OzelDrcKurali("Kural A", "HIGH_CURRENT", 1.5),
        OzelDrcKurali("Kural B", "USB_DIFF", 0.2),
    ]
    custom_dru_yaz(str(hedef), kurallar)
    icerik = hedef.read_text(encoding="utf-8")
    assert icerik.count("(rule ") == 2
    assert "USB_DIFF" in icerik and "HIGH_CURRENT" in icerik


# ------------------------------------------------------------------
# Referans düzlemi sürekliliği (yeni)
# ------------------------------------------------------------------

def test_reference_plane_continuity_split_uzerinden_gecen_izi_yakalar():
    duzlem = DuzlemPoligonu(layer="In1.Cu", net_adi="GND",
                             nokta_listesi=[(0, 0), (50, 0), (50, 30), (0, 30)])
    iz_ok = IzSegmenti(net_adi="USB_D+", layer="In1.Cu", x1=5, y1=5, x2=20, y2=5)
    iz_kotu = IzSegmenti(net_adi="USB_D-", layer="In1.Cu", x1=45, y1=5, x2=60, y2=5)
    bulgular = check_reference_plane_continuity([iz_ok, iz_kotu], [duzlem])
    assert len(bulgular) == 1
    assert "USB_D-" in bulgular[0]


def test_reference_plane_duzlem_tanimi_yoksa_kritik_uyari():
    iz = IzSegmenti(net_adi="MIPI_CLK", layer="F.Cu", x1=0, y1=0, x2=10, y2=0)
    bulgular = check_reference_plane_continuity([iz], [], referans_net="GND")
    assert "hiç bulunamadı" in bulgular[0]


# ------------------------------------------------------------------
# DFT / test noktaları (yeni)
# ------------------------------------------------------------------

def test_insert_test_points_guc_ve_debug_kapsar():
    rail_tree = {"3V3": {"vout": 3.3}, "1V2_CORE": {"vout": 1.2}}
    tps = insert_test_points(rail_tree)
    guc_sayisi = sum(1 for t in tps if t.sinif == TpSinifi.GUC)
    debug_sayisi = sum(1 for t in tps if t.sinif == TpSinifi.DEBUG)
    assert guc_sayisi == 2
    assert debug_sayisi == 5  # varsayılan SWDIO/SWCLK/nRST/UART_TX/UART_RX


def test_tp_kapsam_kontrolu_eksik_yakalar():
    tps = insert_test_points({"3V3": {"vout": 3.3}})
    bulgular = tp_kapsam_kontrolu(tps, beklenen_guc_rayi_sayisi=2,
                                          beklenen_debug_net_listesi=["SWDIO", "SWCLK", "nRST", "UART_TX", "UART_RX"])
    assert any("EKSİK: 2 güç rayı" in b for b in bulgular)


def test_generate_bringup_checklist_sirayi_korur(tmp_path):
    tps = insert_test_points({"3V3": {"vout": 3.3}, "1V2_CORE": {"vout": 1.2}})
    cikti = tmp_path / "bringup.md"
    generate_bringup_checklist(tps, ["3V3", "1V2_CORE"], cikti_path=str(cikti))
    icerik = cikti.read_text(encoding="utf-8")
    assert icerik.index("3V3") < icerik.index("1V2_CORE")
    assert "3.3 V" in icerik


def test_generate_bringup_checklist_olculen_hucresi_ve_checkbox_icerir():
    """Dijitalleştirme: her ray satırı laboratuvarda doldurulacak bir
    'Ölçülen' hücresi VE tıklanabilir bir checkbox içermeli — dosya
    sadece statik bir liste değil, canlı bir test kaydı olmalı."""
    tps = insert_test_points({"3V3": {"vout": 3.3}})
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cikti = os.path.join(d, "bringup.md")
        generate_bringup_checklist(tps, ["3V3"], cikti_path=cikti)
        icerik = open(cikti, encoding="utf-8").read()
    assert "Ölçülen" in icerik
    assert "[ ]" in icerik
    assert "PASS/FAIL/NEEDS_HUMAN" in icerik


def test_generate_bringup_checklist_kabul_araligi_toleranstan_hesaplanir():
    """Kabul aralığı kafadan yazılmaz — tolerans_yuzde parametresinden
    hesaplanır (bulgu_sozlesmesi disipliniyle tutarlı: açık formül)."""
    tps = insert_test_points({"3V3": {"vout": 3.3}})
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cikti = os.path.join(d, "bringup.md")
        generate_bringup_checklist(tps, ["3V3"], cikti_path=cikti, tolerans_yuzde=10.0)
        icerik = open(cikti, encoding="utf-8").read()
    # 3.3V * 0.9 = 2.97, 3.3V * 1.1 = 3.63
    assert "2.97" in icerik and "3.63" in icerik
    assert "±10.0%" in icerik


def test_generate_bringup_checklist_tbd_railde_tbd_araligi():
    """Beklenen voltajı olmayan (TBD) bir ray için kabul aralığı da TBD
    olmalı — sahte bir sayı üretilmemeli."""
    tps: List[TpTanimi] = []
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cikti = os.path.join(d, "bringup.md")
        generate_bringup_checklist(tps, ["BILINMEYEN_RAY"], cikti_path=cikti)
        icerik = open(cikti, encoding="utf-8").read()
    assert "| BILINMEYEN_RAY | TBD | TBD |".replace(" ", "") in icerik.replace(" ", "").replace("`", "")


def test_generate_bringup_checklist_sonuc_arsivi_bolumu_var():
    """Ölçülen sonuçlar Dogrulama_Kaydi şablonuna bağlanmalı — kağıt
    üstünde kalan bir test raporu olmasın diye."""
    tps = insert_test_points({"3V3": {"vout": 3.3}})
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cikti = os.path.join(d, "bringup.md")
        generate_bringup_checklist(tps, ["3V3"], cikti_path=cikti)
        icerik = open(cikti, encoding="utf-8").read()
    assert "Dogrulama_Kaydi" in icerik
    assert "Sonuç Arşivi" in icerik


# ------------------------------------------------------------------
# FAULT-INJECTION — check_reference_plane_continuity'nin gerçekten
# split/void üzerinden geçen izi yakaladığını kanıtla.
# ------------------------------------------------------------------

def test_reference_plane_fault_injection_once_temiz_sonra_ihlal():
    duzlem = DuzlemPoligonu(layer="In1.Cu", net_adi="GND",
                             nokta_listesi=[(0, 0), (50, 0), (50, 30), (0, 30)])

    # 1) TEMİZ: iz tamamen düzlemin içinde
    iz_temiz = IzSegmenti(net_adi="USB_D+", layer="In1.Cu", x1=5, y1=5, x2=20, y2=5)
    assert check_reference_plane_continuity([iz_temiz], [duzlem]) == [], (
        "senaryo zaten FAIL — geçersiz"
    )

    # 2) FAULT INJECTION: aynı izi düzlemin dışına taşı (split üzerinden geçiyor)
    iz_bozuk = IzSegmenti(net_adi="USB_D+", layer="In1.Cu", x1=45, y1=5, x2=60, y2=5)
    bulgular = check_reference_plane_continuity([iz_bozuk], [duzlem])
    assert len(bulgular) == 1, "FAIL: enjekte edilen split/void ihlali yakalanmadı"
    assert "USB_D+" in bulgular[0]


# ------------------------------------------------------------------
# gercek_board_dogrulama_kapisi — pcbnew_koprusu.py entegrasyonu
# (gerçek pcbnew bu ortamda yok -> tum_gercek_board_kontrollerini_calistir
# monkeypatch edilerek karar mantığı izole test edilir)
# ------------------------------------------------------------------

def test_gercek_board_dogrulama_kapisi_hepsi_pass_ise_temiz(monkeypatch):
    from bulgu_sozlesmesi import bulgu_uret
    import pcbnew_koprusu

    def sahte_kontroller(board_path):
        return [bulgu_uret("via_in_pad", 5, []), bulgu_uret("annular_ring", 10, [])]

    monkeypatch.setattr(pcbnew_koprusu, "tum_gercek_board_kontrollerini_calistir", sahte_kontroller)
    from kicad_koprusu import gercek_board_dogrulama_kapisi
    temiz_mi, rapor = gercek_board_dogrulama_kapisi("sahte.kicad_pcb")
    assert temiz_mi is True
    assert rapor["ozet"]["PASS"] == 2


def test_gercek_board_dogrulama_kapisi_bir_fail_varsa_kirli(monkeypatch):
    from bulgu_sozlesmesi import bulgu_uret
    import pcbnew_koprusu

    def sahte_kontroller(board_path):
        return [
            bulgu_uret("via_in_pad", 5, []),
            bulgu_uret("annular_ring", 3, [{"mesaj": "ihlal"}]),
        ]

    monkeypatch.setattr(pcbnew_koprusu, "tum_gercek_board_kontrollerini_calistir", sahte_kontroller)
    from kicad_koprusu import gercek_board_dogrulama_kapisi
    temiz_mi, rapor = gercek_board_dogrulama_kapisi("sahte.kicad_pcb")
    assert temiz_mi is False
    assert rapor["ozet"]["FAIL"] == 1


def test_gercek_board_dogrulama_kapisi_kapsam_yok_fail_closed(monkeypatch):
    """REGRESYON: önceki sürüm KAPSAM_YOK'u temiz_mi'yi bozmadan geçiriyordu
    — bir board'da hiç via bulunamaması gibi bir durum sessizce üretime
    geçebiliyordu. Artık KAPSAM_YOK, açıkça izin verilmediği sürece
    kapıyı FAIL yapar (fail-closed) — dış incelemede bulunan gerçek bir
    kapsam kaçağı, buradaki düzeltmeyle kapatıldı."""
    from bulgu_sozlesmesi import bulgu_uret
    import pcbnew_koprusu

    def sahte_kontroller(board_path):
        return [bulgu_uret("via_in_pad", 0, [])]  # board'da hiç via yok

    monkeypatch.setattr(pcbnew_koprusu, "tum_gercek_board_kontrollerini_calistir", sahte_kontroller)
    from kicad_koprusu import gercek_board_dogrulama_kapisi
    temiz_mi, rapor = gercek_board_dogrulama_kapisi("sahte.kicad_pcb")
    assert temiz_mi is False
    assert rapor["ozet"]["KAPSAM_YOK"] == 1
    assert rapor["kontroller"][0]["kontrol"] == "via_in_pad"
    assert rapor["kapsam_yok_engelledi"] == ["via_in_pad"]


def test_gercek_board_dogrulama_kapisi_izinli_kapsam_yok_kapiyi_kapatmaz(monkeypatch):
    """Bir board tipi için (ör. via'sız, tamamen SMD) belirli bir kontrolün
    kapsam dışı kalması NORMALSE, bu AÇIKÇA `kapsam_yok_izinli_kontroller`
    listesine eklenmelidir — sessiz varsayılan istisna YOKTUR."""
    from bulgu_sozlesmesi import bulgu_uret
    import pcbnew_koprusu

    def sahte_kontroller(board_path):
        return [bulgu_uret("via_in_pad", 0, [])]

    monkeypatch.setattr(pcbnew_koprusu, "tum_gercek_board_kontrollerini_calistir", sahte_kontroller)
    from kicad_koprusu import gercek_board_dogrulama_kapisi
    temiz_mi, rapor = gercek_board_dogrulama_kapisi(
        "sahte.kicad_pcb", kapsam_yok_izinli_kontroller=["via_in_pad"]
    )
    assert temiz_mi is True
    assert rapor["kapsam_yok_engelledi"] == []


def test_gercek_board_dogrulama_kapisi_izin_listesi_kismi_ise_hala_kapali(monkeypatch):
    """Birden fazla KAPSAM_YOK kontrolünden sadece BİRİ izinliyse, diğeri
    kapıyı kapatmaya devam etmeli — izin listesi tüm-veya-hiç değildir."""
    from bulgu_sozlesmesi import bulgu_uret
    import pcbnew_koprusu

    def sahte_kontroller(board_path):
        return [bulgu_uret("via_in_pad", 0, []), bulgu_uret("annular_ring", 0, [])]

    monkeypatch.setattr(pcbnew_koprusu, "tum_gercek_board_kontrollerini_calistir", sahte_kontroller)
    from kicad_koprusu import gercek_board_dogrulama_kapisi
    temiz_mi, rapor = gercek_board_dogrulama_kapisi(
        "sahte.kicad_pcb", kapsam_yok_izinli_kontroller=["via_in_pad"]
    )
    assert temiz_mi is False
    assert rapor["kapsam_yok_engelledi"] == ["annular_ring"]
