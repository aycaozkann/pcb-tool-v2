"""
uretim_zinciri_koprusu.jlcpcb_dfm_kontrolu_gonder() için test suite
(2026-08-03, GÖREV: Kalan 6 Mimari Boşluk, Madde 2).

`jlcpcb_dfm_kontrolu_gonder()` artık bir `NotImplementedError` iskeleti
DEĞİL — gerçek HTTP/multipart/hata-yönetimi çalışır. Ama gerçek JLCPCB
endpoint'i/şeması bu ortamdan DOĞRULANAMADI (bkz. fonksiyonun docstring'i);
bu yüzden testler ağı hiç ÇAĞIRMAZ, `_istek_gonder` enjeksiyon noktasını
sahte bir gönderici ile değiştirir — asıl kanıtlanan şey FAIL-CLOSED
mantığın (token yok / ağ hatası / HTTP!=200 / bozuk JSON / şema uyuşmazlığı)
hiçbirinin sessizce "temiz" saymadığıdır.
"""

from __future__ import annotations

import json

import pytest

from uretim_zinciri_koprusu import DfmApiSonucu, dfm_uyarilarini_degerlendir, jlcpcb_dfm_kontrolu_gonder


def _sahte_govde(sozluk: dict) -> bytes:
    return json.dumps(sozluk).encode("utf-8")


def test_api_anahtari_yoksa_ag_hic_cagrilmaz():
    def _asla_cagrilmamali(*a, **k):
        pytest.fail("api_anahtari yokken ağ katmanına ULAŞILMAMALI")

    sonuc = jlcpcb_dfm_kontrolu_gonder(
        "gerber.zip", None, _istek_gonder=_asla_cagrilmamali,
    )
    assert sonuc.basarili is False
    assert sonuc.kritik_uyari_sayisi == 0
    assert "api_anahtari verilmedi" in sonuc.uyarilar[0]


def test_api_anahtari_bos_string_de_ag_cagrilmaz():
    def _asla_cagrilmamali(*a, **k):
        pytest.fail("boş api_anahtari ile ULAŞILMAMALI")

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "", _istek_gonder=_asla_cagrilmamali)
    assert sonuc.basarili is False


def test_ag_hatasinda_fail_closed_exception_firlatmaz():
    def _ag_hatasi_ver(*a, **k):
        import urllib.error
        raise urllib.error.URLError("offline")

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_ag_hatasi_ver)
    assert sonuc.basarili is False
    assert "ağ/offline" in sonuc.uyarilar[0]


def test_timeout_fail_closed():
    def _timeout_ver(*a, **k):
        raise TimeoutError("zaman aşımı")

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_timeout_ver)
    assert sonuc.basarili is False
    assert "ağ/offline" in sonuc.uyarilar[0]


def test_http_durumu_200_disinda_basarisiz():
    def _500_dondur(*a, **k):
        return 500, b'{"warnings": [], "criticalCount": 0}'

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_500_dondur)
    assert sonuc.basarili is False
    assert "HTTP 500" in sonuc.uyarilar[0]


def test_gecersiz_json_fail_closed():
    def _bozuk_json(*a, **k):
        return 200, b"<html>hata</html>"

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_bozuk_json)
    assert sonuc.basarili is False
    assert "geçerli JSON değil" in sonuc.uyarilar[0]


def test_beklenen_alanlar_eksikse_sema_uyusmazligi_raporlanir():
    def _eksik_sema(*a, **k):
        return 200, _sahte_govde({"foo": "bar"})

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_eksik_sema)
    assert sonuc.basarili is False
    assert "şema" in sonuc.uyarilar[0].lower()
    assert sonuc.ham_yanit == {"foo": "bar"}


def test_kritik_uyari_sifirsa_basarili():
    def _temiz_yanit(*a, **k):
        return 200, _sahte_govde({"warnings": [], "criticalCount": 0})

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_temiz_yanit)
    assert sonuc.basarili is True
    assert sonuc.kritik_uyari_sayisi == 0
    assert dfm_uyarilarini_degerlendir(sonuc) is True


def test_kritik_uyari_varsa_basarisiz():
    def _kirli_yanit(*a, **k):
        return 200, _sahte_govde({"warnings": ["pad çok küçük"], "criticalCount": 2})

    sonuc = jlcpcb_dfm_kontrolu_gonder("gerber.zip", "tok123", _istek_gonder=_kirli_yanit)
    assert sonuc.basarili is False
    assert sonuc.kritik_uyari_sayisi == 2
    assert sonuc.uyarilar == ["pad çok küçük"]
    assert dfm_uyarilarini_degerlendir(sonuc) is False


def test_istek_gonder_dogru_parametrelerle_cagrilir():
    yakalanan = {}

    def _yakala(gerber_zip_path, api_anahtari, endpoint_url, zaman_asimi_s):
        yakalanan["gerber_zip_path"] = gerber_zip_path
        yakalanan["api_anahtari"] = api_anahtari
        yakalanan["endpoint_url"] = endpoint_url
        yakalanan["zaman_asimi_s"] = zaman_asimi_s
        return 200, _sahte_govde({"warnings": [], "criticalCount": 0})

    jlcpcb_dfm_kontrolu_gonder(
        "cikti/gerber.zip", "tok456", endpoint_url="https://ozel.endpoint/x",
        zaman_asimi_s=30, _istek_gonder=_yakala,
    )
    assert yakalanan == {
        "gerber_zip_path": "cikti/gerber.zip",
        "api_anahtari": "tok456",
        "endpoint_url": "https://ozel.endpoint/x",
        "zaman_asimi_s": 30,
    }
