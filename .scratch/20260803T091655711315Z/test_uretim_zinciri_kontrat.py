"""
uretim_zinciri_koprusu.py BÖLÜM 5 (Kontrat/Artifact kapıları) için test suite.

Kapsam: `drc.json`/`parts.json` kontrat şemalarının diskten okunduğunu (bellekteki
dict'ten DEĞİL), eksik dosyada fail-open OLMADIĞINI ve fault-injection ile
kapıların GERÇEKTEN kırıldığını kanıtlar (proje disiplini — bkz. modülün
kendi `_kontrat_kapilari_oz_testleri_calistir()` fonksiyonu, bu dosya onu
pytest üzerinden de çalıştırır + ek uç-durum testleri ekler).
"""

from __future__ import annotations

import json

import pytest

from uretim_zinciri_koprusu import (
    KiBotSonucu,
    KontratKapisiHatasi,
    ParcaKontratSatiri,
    _kontrat_kapilari_oz_testleri_calistir,
    drc_kapisi_gecti_mi,
    drc_kontrati_uret,
    drc_kontrati_yaz,
    parts_kapisi_gecti_mi,
    parts_kontrati_yaz,
    uretim_zincirini_kontratla_yurut,
)


def test_modulun_kendi_oz_testleri_temiz(tmp_path):
    hatalar = _kontrat_kapilari_oz_testleri_calistir(str(tmp_path))
    assert hatalar == []


def test_kibot_sonucu_artik_gercek_bir_sinif():
    """Regresyon kilidi: KiBotSonucu daha önce `@dataclass class` başlığı
    eksik olduğu için modül seviyesinde yalın tip-ipucu satırlarına
    düşmüştü (NameError riski) — artık gerçek bir dataclass olmalı."""
    s = KiBotSonucu(basarili=True, cikti_dizini="uretim", stdout="", stderr="")
    assert s.basarili is True


def test_drc_kapisi_dosya_yoksa_fail_open_degil(tmp_path):
    with pytest.raises(KontratKapisiHatasi):
        drc_kapisi_gecti_mi(str(tmp_path / "yok.json"))


def test_drc_kapisi_bozuk_json_fail_open_degil(tmp_path):
    yol = tmp_path / "bozuk.json"
    yol.write_text("{ bu gecerli json degil", encoding="utf-8")
    with pytest.raises(KontratKapisiHatasi):
        drc_kapisi_gecti_mi(str(yol))


def test_drc_kontrati_disktekiyle_belleteki_farklilassa_disk_kazanir(tmp_path):
    """Kontrat kapısının SADECE diski okuduğunu kanıtlar: temiz bir
    kontrat nesnesi üretilir ama diske YAZILMADAN önce dosyayı elle
    kirli bir içerikle değiştirirsek kapı diskteki (kirli) veriyi görmeli."""
    yol = tmp_path / "drc.json"
    kirli = drc_kontrati_uret("b.kicad_pcb", {"violations": [{"severity": "error"}]})
    drc_kontrati_yaz(kirli, str(yol))
    assert drc_kapisi_gecti_mi(str(yol)) is False

    temiz = drc_kontrati_uret("b.kicad_pcb", {"violations": []})
    drc_kontrati_yaz(temiz, str(yol))
    assert drc_kapisi_gecti_mi(str(yol)) is True


def test_erc_kaynagi_sheets_altindaki_ihlalleri_okur():
    ham = {"sheets": [{"violations": [{"severity": "fatal", "type": "x"}]}]}
    kontrat = drc_kontrati_uret("s.kicad_sch", ham, kaynak="erc")
    assert kontrat.ihlal_sayisi == 1


def test_bilinmeyen_kaynak_reddedilir():
    with pytest.raises(ValueError):
        drc_kontrati_uret("b.kicad_pcb", {}, kaynak="gecersiz")


def test_parts_kapisi_yuksek_risk_skoru_fail_verir(tmp_path):
    yol = tmp_path / "parts.json"
    parts_kontrati_yaz(
        [ParcaKontratSatiri("R1", "C1", 0.9, "Active", alternatif_bulundu_mu=False)],
        str(yol),
    )
    gecti, bulgular = parts_kapisi_gecti_mi(str(yol), max_risk_skoru=0.5)
    assert gecti is False
    assert bulgular


def test_parts_kapisi_eksik_alan_guvenli_tarafta_varsayar(tmp_path):
    """Şema alanı eksikse (risk_skoru yok) fonksiyon 1.0 (en riskli) varsayar
    — sessiz 0-risk varsayımı FAIL-OPEN olurdu."""
    yol = tmp_path / "parts.json"
    yol.write_text(
        json.dumps({"sema_surumu": 1, "satirlar": [{"refdes": "R1"}]}),
        encoding="utf-8",
    )
    gecti, bulgular = parts_kapisi_gecti_mi(str(yol))
    assert gecti is False
    assert "R1" in bulgular[0]


def test_uretim_zincirini_kontratla_yurut_drc_fail_ise_kibotu_hic_cagirmaz(tmp_path, monkeypatch):
    parts_yol = tmp_path / "parts.json"
    drc_yol = tmp_path / "drc.json"
    parts_kontrati_yaz(
        [ParcaKontratSatiri("R1", "C1", 0.1, "Active", alternatif_bulundu_mu=True)],
        str(parts_yol),
    )
    drc_kontrati_yaz(
        drc_kontrati_uret("b.kicad_pcb", {"violations": [{"severity": "error"}]}),
        str(drc_yol),
    )

    cagrildi = {"deger": False}

    def sahte_kibot_calistir(*a, **k):
        cagrildi["deger"] = True
        return KiBotSonucu(basarili=True, cikti_dizini="uretim", stdout="", stderr="")

    monkeypatch.setattr("uretim_zinciri_koprusu.kibot_calistir", sahte_kibot_calistir)

    with pytest.raises(KontratKapisiHatasi):
        uretim_zincirini_kontratla_yurut(
            "board.kicad_pcb",
            parts_kontrat_yolu=str(parts_yol),
            drc_kontrat_yolu=str(drc_yol),
            kibot_config_yolu=str(tmp_path / "kibot.yaml"),
            kibot_cikti_dizini=str(tmp_path / "uretim"),
        )
    assert cagrildi["deger"] is False, "DRC kapısı FAIL iken kibot_calistir() ÇAĞRILDI (fail-open regresyonu)"
