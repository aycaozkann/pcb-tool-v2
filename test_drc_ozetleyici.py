"""
drc_ozetleyici.py için test suite (GÖREV 11).

Proje disiplini: her A-seviyesi kontrol için fault-injection kanıtı —
önce doğru kümeleme (PASS), sonra `hucre_boyutu_mm` bilerek küçültülüp
kümelerin GERÇEKTEN ayrıştığı (yani testin bir şey ÖLÇTÜĞÜ) kanıtlanır.
"""

from __future__ import annotations

import json

import pytest

from bulgu_sozlesmesi import BulguDurumu
from drc_ozetleyici import (
    Kume,
    drc_kumeleri_bulgu_uret,
    en_yakin_footprint_bul,
    ihlalden_temsili_konum,
    ihlalleri_kumele,
    kume_ozeti_uret,
)


def _ihlal(x: float, y: float, severity: str = "error", aciklama: str = "kısa devre") -> dict:
    return {
        "severity": severity,
        "description": aciklama,
        "items": [{"pos": {"x": x, "y": y}, "description": aciklama}],
    }


# ------------------------------------------------------------------
# 1. ihlalden_temsili_konum
# ------------------------------------------------------------------

def test_ihlalden_temsili_konum_tek_item_dogru_konum():
    assert ihlalden_temsili_konum(_ihlal(12.5, 34.0)) == (12.5, 34.0)


def test_ihlalden_temsili_konum_coklu_item_centroid_hesaplar():
    ihlal = {
        "severity": "error",
        "items": [
            {"pos": {"x": 0.0, "y": 0.0}},
            {"pos": {"x": 10.0, "y": 0.0}},
        ],
    }
    assert ihlalden_temsili_konum(ihlal) == (5.0, 0.0)


def test_ihlalden_temsili_konum_pos_yoksa_none_doner():
    """UYDURMA KOORDİNAT üretilmez — items boşsa veya pos eksikse None."""
    assert ihlalden_temsili_konum({"severity": "error", "items": []}) is None
    assert ihlalden_temsili_konum({"severity": "error"}) is None
    assert ihlalden_temsili_konum({"severity": "error", "items": [{"description": "x"}]}) is None


# ------------------------------------------------------------------
# 2. ihlalleri_kumele — ana kümeleme mantığı + FAULT INJECTION
# ------------------------------------------------------------------

def test_ihlalleri_kumele_yakin_ihlalleri_tek_kumede_toplar():
    """Bir IC'nin (ör. U1) 4 pad'i etrafında yakın koordinatlı 12 sahte
    'short' ihlali + 2 uzak tekil ihlal: 12'si TEK kümede, 2 uzak ihlal
    AYRI kümelerde kalmalı — kabul kriterinin senaryosu."""
    yakinlar = [_ihlal(10.0 + (i % 4) * 0.1, 10.0 + (i % 3) * 0.1) for i in range(12)]
    uzaklar = [_ihlal(100.0, 100.0), _ihlal(200.0, 200.0)]

    kumeler = ihlalleri_kumele(yakinlar + uzaklar, hucre_boyutu_mm=2.0)

    sayilar = sorted((k.sayi for k in kumeler), reverse=True)
    assert sayilar == [12, 1, 1], f"beklenen [12,1,1], alınan {sayilar}"
    buyuk_kume = kumeler[0]
    assert buyuk_kume.sayi == 12
    assert buyuk_kume.merkez is not None
    assert 10.0 <= buyuk_kume.merkez[0] <= 10.4
    assert 10.0 <= buyuk_kume.merkez[1] <= 10.3


def test_ihlalleri_kumele_konumsuz_ihlal_ayri_grupta_kalir_atilmaz():
    """Konum bilgisi taşımayan bir ihlal SESSİZCE ATILMAZ — ayrı bir
    'konumsuz' kümede toplanır, toplam sayıya dahil edilir."""
    konumlu = [_ihlal(5.0, 5.0), _ihlal(5.1, 5.0)]
    konumsuz = [{"severity": "warning", "description": "items yok", "items": []}]

    kumeler = ihlalleri_kumele(konumlu + konumsuz, hucre_boyutu_mm=2.0)

    konumsuz_kumeler = [k for k in kumeler if k.konumsuz_mu]
    assert len(konumsuz_kumeler) == 1
    assert konumsuz_kumeler[0].sayi == 1
    toplam = sum(k.sayi for k in kumeler)
    assert toplam == 3  # hiçbir ihlal kaybolmadı


def test_ihlalleri_kumele_fault_injection_kucuk_hucre_ayristirir():
    """FAULT INJECTION: aynı 12 'yakın' ihlal, `hucre_boyutu_mm` bilerek
    çok küçük yapılınca (0.01mm) ARTIK aynı kümede TOPLANMAMALI — bu,
    ilk testin gerçekten `hucre_boyutu_mm` parametresini ÖLÇTÜĞÜNÜN,
    hep 'tek küme' döndüren sabit-kodlanmış bir mantık OLMADIĞININ kanıtı."""
    yakinlar = [_ihlal(10.0 + (i % 4) * 0.1, 10.0 + (i % 3) * 0.1) for i in range(12)]

    buyuk_hucreyle = ihlalleri_kumele(yakinlar, hucre_boyutu_mm=2.0)
    kucuk_hucreyle = ihlalleri_kumele(yakinlar, hucre_boyutu_mm=0.01)

    assert len(buyuk_hucreyle) == 1, "2mm hücrede 12'si TEK kümede toplanmalıydı"
    assert len(kucuk_hucreyle) > 1, (
        "0.01mm hücrede ihlaller AYRIŞMADI — kümeleme hucre_boyutu_mm'den "
        "bağımsız çalışıyor olabilir (sahte-pozitif risk)"
    )
    assert sum(k.sayi for k in kucuk_hucreyle) == 12  # hiçbiri kaybolmadı


def test_ihlalleri_kumele_severity_dagilimini_dogru_sayar():
    # 4.0/4.1 bilerek seçildi: hucre_boyutu_mm=2.0 ızgarasında İKİSİ de
    # aynı hücreye (round(x/2)=2) düşer — bir hücre SINIRINA yakın
    # değerler (ör. 1.0/1.05) yuvarlama yönüne göre YANLIŞLIKLA farklı
    # hücrelere düşebilir, bu ayrı, bilinen bir grid-sınırı davranışıdır.
    ihlaller = [_ihlal(4.0, 4.0, severity="error"), _ihlal(4.1, 4.0, severity="warning")]
    kumeler = ihlalleri_kumele(ihlaller, hucre_boyutu_mm=2.0)
    assert len(kumeler) == 1
    assert kumeler[0].severity_dagilimi == {"error": 1, "warning": 1}


def test_ihlalleri_kumele_gecersiz_hucre_boyutu_reddedilir():
    with pytest.raises(ValueError):
        ihlalleri_kumele([_ihlal(1.0, 1.0)], hucre_boyutu_mm=0)


def test_ihlalleri_kumele_bos_liste_bos_doner():
    assert ihlalleri_kumele([], hucre_boyutu_mm=2.0) == []


# ------------------------------------------------------------------
# 3. kume_ozeti_uret — kabul kriteri formatı
# ------------------------------------------------------------------

def test_kume_ozeti_uret_refdes_ile_kabul_kriteri_formati():
    kume = Kume(merkez=(12.0, 34.0), sayi=12, severity_dagilimi={"error": 12}, refdes="U1")
    ozet = kume_ozeti_uret(kume)
    assert ozet == (
        "Özet: U1 etrafında 12 adet error ihlali kümelendi. "
        "Öneri: U1 bölgesindeki yerleşimi genişletin."
    )


def test_kume_ozeti_uret_refdes_yoksa_konum_ile_ifade_eder():
    kume = Kume(merkez=(12.345, 34.0), sayi=3, severity_dagilimi={"warning": 3})
    ozet = kume_ozeti_uret(kume)
    assert "12.35, 34.00" in ozet or "12.34, 34.00" in ozet or "(12.3" in ozet
    assert "Öneri:" in ozet
    assert "bu bölgedeki yerleşimi genişletin" in ozet


def test_kume_ozeti_uret_konumsuz_kume_farkli_mesaj_uretir():
    kume = Kume(merkez=None, sayi=2, severity_dagilimi={"warning": 2})
    ozet = kume_ozeti_uret(kume)
    assert "konum bilgisi taşımayan" in ozet
    assert "2 adet warning" in ozet


# ------------------------------------------------------------------
# 4. en_yakin_footprint_bul — board_path yoksa / pcbnew yoksa çökmez
# ------------------------------------------------------------------

def test_en_yakin_footprint_bul_board_path_yoksa_none():
    assert en_yakin_footprint_bul((0.0, 0.0), board_path=None) is None


def test_en_yakin_footprint_bul_pcbnew_bulunamazsa_none(monkeypatch):
    import arac_yollari

    def firlat(istenen_yol=None):
        raise FileNotFoundError("test: pcbnew yok")

    monkeypatch.setattr(arac_yollari, "kicad_python_yolunu_bul", firlat)

    assert en_yakin_footprint_bul((0.0, 0.0), board_path="board.kicad_pcb") is None


def test_en_yakin_footprint_bul_en_yakini_secer(monkeypatch, tmp_path):
    """`pcbnew_scripti_calistir`'i sahteleyip (gerçek pcbnew GEREKMEDEN)
    en yakın footprint seçim mantığını doğrular."""
    import subprocess

    import arac_yollari
    import drc_ozetleyici as mod

    monkeypatch.setattr(arac_yollari, "kicad_python_yolunu_bul", lambda istenen_yol=None: "python.exe")

    kutular = {
        "U1": {"x_min": 9.0, "y_min": 9.0, "x_max": 11.0, "y_max": 11.0},   # merkez (10,10)
        "C3": {"x_min": 99.0, "y_min": 99.0, "x_max": 101.0, "y_max": 101.0},  # merkez (100,100)
    }

    def sahte_calistir(script_path, argv, kicad_python=None, timeout_s=60):
        return subprocess.CompletedProcess(["python"], returncode=0, stdout=json.dumps(kutular), stderr="")

    monkeypatch.setattr(mod, "pcbnew_scripti_calistir", sahte_calistir, raising=False)
    monkeypatch.setattr(arac_yollari, "pcbnew_scripti_calistir", sahte_calistir)

    ref = en_yakin_footprint_bul((10.5, 10.5), board_path=str(tmp_path / "board.kicad_pcb"))
    assert ref == "U1"


# ------------------------------------------------------------------
# 5. drc_kumeleri_bulgu_uret — bulgu_sozlesmesi entegrasyonu
# ------------------------------------------------------------------

def test_drc_kumeleri_bulgu_uret_sema_taninmadiginda_kapsam_yok():
    """Rapor ne `violations` ne `unconnected_items` içeriyorsa (bozuk/
    beklenmeyen şema) — DRC'nin gerçekten çalıştığı BİLİNMİYOR, sessizce
    PASS SAYILMAZ, KAPSAM_YOK döner (bulgu_sozlesmesi'nin kendi kuralı:
    taranan=0 -> asla PASS)."""
    bulgu = drc_kumeleri_bulgu_uret({"bilinmeyen_alan": []})
    assert bulgu.durum == BulguDurumu.KAPSAM_YOK
    assert bulgu.taranan == 0
    assert bulgu.gecti_mi is False


def test_drc_kumeleri_bulgu_uret_temiz_board_pass_doner():
    """Şema tanınıyor (gerçek bir DRC çalıştırması) ve 0 ihlal varsa —
    bu GERÇEK bir PASS'tir, KAPSAM_YOK DEĞİL (DRC'ye özgü fark: 0 ihlal
    'hiç kontrol edilmedi' değil 'kontrol edildi, temiz' anlamına gelir)."""
    bulgu = drc_kumeleri_bulgu_uret({"violations": [], "unconnected_items": []})
    assert bulgu.durum == BulguDurumu.PASS
    assert bulgu.gecti_mi is True
    assert bulgu.ihlaller == []


def test_drc_kumeleri_bulgu_uret_ihlalli_board_fail_ve_kume_ozetleri_icerir():
    rapor = {
        "violations": [_ihlal(10.0 + i * 0.1, 10.0, aciklama="VCC/GND kısa devresi") for i in range(5)],
        "unconnected_items": [],
    }
    bulgu = drc_kumeleri_bulgu_uret(rapor, hucre_boyutu_mm=2.0)

    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.taranan == 1
    assert len(bulgu.ihlaller) == 1  # tek küme
    assert bulgu.ihlaller[0]["sayi"] == 5
    assert "Özet:" in bulgu.ihlaller[0]["ozet"]
    assert "Öneri:" in bulgu.ihlaller[0]["ozet"]


def test_drc_kumeleri_bulgu_uret_unconnected_items_de_dahil_edilir():
    """`_drc_tum_ihlaller`/`kicad_koprusu.py` ile AYNI disiplin:
    `unconnected_items` de taranmalı, sadece `violations` DEĞİL."""
    rapor = {
        "violations": [],
        "unconnected_items": [_ihlal(1.0, 1.0, severity="error", aciklama="bağlanmamış pad")],
    }
    bulgu = drc_kumeleri_bulgu_uret(rapor)
    assert bulgu.durum == BulguDurumu.FAIL
    assert bulgu.ihlaller[0]["sayi"] == 1
