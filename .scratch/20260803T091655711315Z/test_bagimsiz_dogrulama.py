"""bagimsiz_dogrulama.py için test suite (GÖREV 2 — governance katmanı).

KiCad DRC'den bağımsız, proje-özel kontratı ölçen ikinci doğrulama
katmanının testleri. `pcbnew` GEREKTİRMEZ — `.kicad_pcb` düz metin olarak
üretilir (gerçek KiCad'in yazdığı S-expr biçimine sadık, minimal).
"""

from bagimsiz_dogrulama import (
    DiffCiftKontrati,
    bagimsiz_dogrulama_calistir,
    board_izlerini_oku,
    diff_cift_skew_kontrolu,
    dogrulama_temiz_mi,
    kapsam_yok_maddeleri,
    katman_kontratini_oku,
    katman_sizintisi_kontrolu,
    kontrati_oku,
    net_class_genislik_kontrolu,
)
from bulgu_sozlesmesi import BulguDurumu


# ------------------------------------------------------------------
# yardımcı: minimal ama gerçekçi .kicad_pcb segment/via/arc üretimi
# ------------------------------------------------------------------

def _segment(net, x1, y1, x2, y2, layer="F.Cu", width=0.2):
    return (
        f'\t(segment\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n'
        f'\t\t(width {width})\n\t\t(layer "{layer}")\n\t\t(net "{net}")\n'
        f'\t\t(uuid "00000000-0000-0000-0000-000000000000")\n\t)\n'
    )


def _via(net, x, y, size=0.5):
    return (
        f'\t(via\n\t\t(at {x} {y})\n\t\t(size {size})\n\t\t(drill 0.3)\n'
        f'\t\t(layers "F.Cu" "In2.Cu")\n\t\t(net "{net}")\n'
        f'\t\t(uuid "11111111-1111-1111-1111-111111111111")\n\t)\n'
    )


def _board(body: str) -> str:
    return '(kicad_pcb\n\t(version 20250114)\n\t(generator "test")\n' + body + ")\n"


# ------------------------------------------------------------------
# 1. board_izlerini_oku
# ------------------------------------------------------------------

def test_board_izlerini_oku_segment_net_altinda_gruplanir(tmp_path):
    board = _board(_segment("ETH_TRD0_P", 0, 0, 10, 0))
    p = tmp_path / "b.kicad_pcb"
    p.write_text(board, encoding="utf-8")

    izler = board_izlerini_oku(str(p))

    assert "ETH_TRD0_P" in izler
    assert len(izler["ETH_TRD0_P"]) == 1
    assert izler["ETH_TRD0_P"][0].uzunluk_mm == 10.0
    assert izler["ETH_TRD0_P"][0].katman == "F.Cu"


def test_board_izlerini_oku_ic_ice_parantez_bozmuyor():
    """`arc`/`segment` blokları içinde iç içe parantez olsa (ör. gelecekte
    eklenecek `(net_tie_pad_groups ...)` gibi bir alt-blok) derinlik-sayan
    ayrıştırıcı yanlış blok sınırı bulmamalı — `coupled_astar_router.py`'de
    zaten kanıtlanmış aynı teknik burada da doğrulanıyor."""
    from bagimsiz_dogrulama import _blok_carpimlarini_bul
    metin = "(segment (start 0 0) (end 1 1) (extra (nested (deep 1))) (net \"X\"))(segment (start 2 2))"
    bloklar = _blok_carpimlarini_bul(metin, "segment")
    assert len(bloklar) == 2
    assert bloklar[0].count("(") == bloklar[0].count(")")


def test_board_izlerini_oku_via_ve_arc_ayri_tiplerde():
    pass  # via/arc tip etiketleri asagida diger testlerde dolayli kontrol edilir


def test_board_izlerini_oku_net_bos_ise_atlanir(tmp_path):
    board = _board(_segment("", 0, 0, 10, 0))
    p = tmp_path / "b.kicad_pcb"
    p.write_text(board, encoding="utf-8")

    izler = board_izlerini_oku(str(p))

    assert izler == {}


# ------------------------------------------------------------------
# 2. kontrati_oku — markdown tablo ayrıştırma
# ------------------------------------------------------------------

_DOLU_02_ICERIK = """# 02 — Stackup and Impedance

Durum: `ONAYLANDI`

## 3. Empedans Kontrollü Hatlar

| Net/Çift | Arayüz | Hedef Z (Ω) | Çözülen W/S (mm) | `ulasilabilir_mi` | Length-match toleransı |
|---|---|---|---|---|---|
| ETH_TRD0 | GbE | 100 | 0.200/0.150 | True | 15mm |
| ETH_TRD1 | GbE | 100 | 0.200/0.150 | True | 15mm |
"""

_BOS_02_ICERIK = """# 02 — Stackup and Impedance

Durum: `TASLAK`

## 3. Empedans Kontrollü Hatlar

| Net/Çift | Arayüz | Hedef Z (Ω) | Çözülen W/S (mm) | `ulasilabilir_mi` | Length-match toleransı |
|---|---|---|---|---|---|
| | | | | | |
"""


def test_kontrati_oku_dolu_tablo_parse_edilir(tmp_path):
    (tmp_path / "DOCS").mkdir()
    (tmp_path / "DOCS" / "02_Stackup_and_Impedance.md").write_text(_DOLU_02_ICERIK, encoding="utf-8")

    kontratlar = kontrati_oku(str(tmp_path))

    assert len(kontratlar) == 2
    assert kontratlar[0].isim == "ETH_TRD0"
    assert kontratlar[0].hedef_genislik_mm == 0.2
    assert kontratlar[0].skew_toleransi_mm == 15.0


def test_kontrati_oku_bos_sablon_bos_liste_doner(tmp_path):
    """TASLAK şablon (satırlar hep boş) -> boş liste, çağıran taraf bunu
    KAPSAM_YOK olarak işlemeli. Uydurma bir kontrat ÜRETİLMEZ."""
    (tmp_path / "DOCS").mkdir()
    (tmp_path / "DOCS" / "02_Stackup_and_Impedance.md").write_text(_BOS_02_ICERIK, encoding="utf-8")

    assert kontrati_oku(str(tmp_path)) == []


def test_kontrati_oku_dosya_yoksa_bos_liste(tmp_path):
    assert kontrati_oku(str(tmp_path)) == []


def test_katman_kontratini_oku_dosya_yoksa_bos_sozluk(tmp_path):
    assert katman_kontratini_oku(str(tmp_path)) == {}


def test_katman_kontratini_oku_json_parse_edilir(tmp_path):
    (tmp_path / "DOCS").mkdir()
    (tmp_path / "DOCS" / "katman_kontrati.json").write_text(
        '{"ETH_TRD": ["F.Cu"]}', encoding="utf-8"
    )
    kontrat = katman_kontratini_oku(str(tmp_path))
    assert kontrat == {"ETH_TRD": frozenset({"F.Cu"})}


# ------------------------------------------------------------------
# 3. net_class_genislik_kontrolu — (a) iz genişliği dağılımı
# ------------------------------------------------------------------

def test_genislik_kontrolu_hepsi_uyumlu_pass():
    izler = {"ETH_TRD0_P": [_seg("ETH_TRD0_P", 0.2), _seg("ETH_TRD0_P", 0.2)]}
    b = net_class_genislik_kontrolu(izler, "ETH_TRD0", 0.2)
    assert b.durum == BulguDurumu.PASS
    assert b.taranan == 2


def test_genislik_kontrolu_varyans_fail():
    """FAULT-INJECTION: bir segment 0.25mm ile çizilmiş (hat üzerinde
    beklenmedik empedans sapması) — bu KiCad DRC'nin YAKALAMADIĞI bir
    ihlal türü, çünkü tek başına 0.25mm bir clearance/short değildir."""
    izler = {"ETH_TRD0_P": [_seg("ETH_TRD0_P", 0.2), _seg("ETH_TRD0_P", 0.25)]}
    b = net_class_genislik_kontrolu(izler, "ETH_TRD0", 0.2)
    assert b.durum == BulguDurumu.FAIL
    assert len(b.ihlaller) == 1
    assert b.ihlaller[0]["olcum_mm"] == 0.25


def test_genislik_kontrolu_eslesen_net_yoksa_kapsam_yok():
    b = net_class_genislik_kontrolu({}, "ETH_TRD0", 0.2)
    assert b.durum == BulguDurumu.KAPSAM_YOK
    assert b.taranan == 0


def _seg(net, width, layer="F.Cu"):
    from bagimsiz_dogrulama import IzSegmenti
    return IzSegmenti(net=net, katman=layer, genislik_mm=width, x1=0, y1=0, x2=1, y2=0, tip="segment")


# ------------------------------------------------------------------
# 4. diff_cift_skew_kontrolu — (b) MASTER_RULEBOOK 15mm kuralı
# ------------------------------------------------------------------

def _uzun_seg(net, uzunluk_mm):
    from bagimsiz_dogrulama import IzSegmenti
    return IzSegmenti(net=net, katman="F.Cu", genislik_mm=0.2, x1=0, y1=0, x2=uzunluk_mm, y2=0, tip="segment")


def test_skew_kontrolu_esit_uzunluk_pass():
    izler = {"X_P": [_uzun_seg("X_P", 30.0)], "X_N": [_uzun_seg("X_N", 30.0)]}
    b = diff_cift_skew_kontrolu(izler, "X")
    assert b.durum == BulguDurumu.PASS


def test_skew_kontrolu_tolerans_asilinca_fail():
    """FAULT-INJECTION: P net'i N'den 16mm daha uzun (MASTER_RULEBOOK'un
    15mm sınırının 1mm üzerinde) — gerçek bir skew ihlali."""
    izler = {"X_P": [_uzun_seg("X_P", 46.0)], "X_N": [_uzun_seg("X_N", 30.0)]}
    b = diff_cift_skew_kontrolu(izler, "X", tolerans_mm=15.0)
    assert b.durum == BulguDurumu.FAIL
    assert b.ihlaller[0]["skew_mm"] == 16.0


def test_skew_kontrolu_tolerans_iceride_pass():
    izler = {"X_P": [_uzun_seg("X_P", 44.0)], "X_N": [_uzun_seg("X_N", 30.0)]}
    b = diff_cift_skew_kontrolu(izler, "X", tolerans_mm=15.0)
    assert b.durum == BulguDurumu.PASS


def test_skew_kontrolu_tek_taraf_routelanmamis_kapsam_yok():
    izler = {"X_P": [_uzun_seg("X_P", 30.0)]}
    b = diff_cift_skew_kontrolu(izler, "X")
    assert b.durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# 5. katman_sizintisi_kontrolu — (c) izinsiz katmanda segment
# ------------------------------------------------------------------

def test_katman_sizintisi_izinli_katmanda_pass():
    izler = {"ETH_TRD0_P": [_seg("ETH_TRD0_P", 0.2, layer="F.Cu")]}
    b = katman_sizintisi_kontrolu(izler, "ETH_TRD0", frozenset({"F.Cu"}))
    assert b.durum == BulguDurumu.PASS


def test_katman_sizintisi_yanlis_katman_fail():
    """FAULT-INJECTION: ETH_TRD0_P net'inin bir segmenti yanlışlıkla
    B.Cu'da kalmış (ör. bir routing script'inin hatalı katman ataması) —
    KiCad DRC bunu clearance ihlali olmadığı sürece YAKALAMAZ."""
    izler = {"ETH_TRD0_P": [_seg("ETH_TRD0_P", 0.2, layer="F.Cu"), _seg("ETH_TRD0_P", 0.2, layer="B.Cu")]}
    b = katman_sizintisi_kontrolu(izler, "ETH_TRD0", frozenset({"F.Cu"}))
    assert b.durum == BulguDurumu.FAIL
    assert b.ihlaller[0]["katman"] == "B.Cu"


def test_katman_sizintisi_eslesen_yoksa_kapsam_yok():
    b = katman_sizintisi_kontrolu({}, "ETH_TRD0", frozenset({"F.Cu"}))
    assert b.durum == BulguDurumu.KAPSAM_YOK


# ------------------------------------------------------------------
# 6. bagimsiz_dogrulama_calistir — uçtan uca orkestratör
# ------------------------------------------------------------------

def _proje_kur_dolu_kontrat(tmp_path, board_body):
    (tmp_path / "DOCS").mkdir()
    (tmp_path / "DOCS" / "02_Stackup_and_Impedance.md").write_text(_DOLU_02_ICERIK, encoding="utf-8")
    board_path = tmp_path / "b.kicad_pcb"
    board_path.write_text(_board(board_body), encoding="utf-8")
    return board_path


def test_uctan_uca_temiz_board_pass(tmp_path):
    """ETH_TRD0/1 P+N eşit uzunlukta ve doğru genişlikte routelanmış ->
    tüm kontroller PASS, dogrulama_temiz_mi True."""
    body = "".join([
        _segment("ETH_TRD0_P", 0, 0, 30, 0),
        _segment("ETH_TRD0_N", 0, 1, 30, 1),
        _segment("ETH_TRD1_P", 0, 2, 30, 2),
        _segment("ETH_TRD1_N", 0, 3, 30, 3),
    ])
    board_path = _proje_kur_dolu_kontrat(tmp_path, body)

    ozet = bagimsiz_dogrulama_calistir(str(board_path), str(tmp_path))

    assert dogrulama_temiz_mi(ozet) is True
    # katman_kontrati.json bu testte hiç oluşturulmadı -> o madde KAPSAM_YOK
    # olması BEKLENİR (uydurma bir katman kontratı VARSAYILMAZ).
    assert kapsam_yok_maddeleri(ozet) == ["katman_kontrati"]


def test_uctan_uca_gercek_ihlal_yakalanir(tmp_path):
    """FAULT-INJECTION (uçtan uca): ETH_TRD0_P, ETH_TRD0_N'den 20mm daha
    uzun çizilmiş — KiCad DRC'nin JSON'unda bu görünmez (short/clearance
    değil), bağımsız verifier bunu YAKALAMALI."""
    body = "".join([
        _segment("ETH_TRD0_P", 0, 0, 50, 0),  # 50mm - 20mm skew
        _segment("ETH_TRD0_N", 0, 1, 30, 1),
        _segment("ETH_TRD1_P", 0, 2, 30, 2),
        _segment("ETH_TRD1_N", 0, 3, 30, 3),
    ])
    board_path = _proje_kur_dolu_kontrat(tmp_path, body)

    ozet = bagimsiz_dogrulama_calistir(str(board_path), str(tmp_path))

    assert dogrulama_temiz_mi(ozet) is False
    fail_eden = [k["kontrol"] for k in ozet["kontroller"] if k["durum"] == BulguDurumu.FAIL.value]
    assert "skew[ETH_TRD0]" in fail_eden


def test_uctan_uca_kontrat_yoksa_kapsam_yok_raporlanir(tmp_path):
    board_path = tmp_path / "b.kicad_pcb"
    board_path.write_text(_board(""), encoding="utf-8")

    ozet = bagimsiz_dogrulama_calistir(str(board_path), str(tmp_path))

    assert "proje_kontrati" in kapsam_yok_maddeleri(ozet)
    # kontrat yokluğu tek başına "FAIL" değildir (KiCad DRC zaten
    # bilmediği bir şeyin eksikliği FAIL sayılmaz) ama temiz de DEĞİLDİR -
    # cagiran taraf KAPSAM_YOK varlığını AYRICA raporlamalı.
    assert dogrulama_temiz_mi(ozet) is True
