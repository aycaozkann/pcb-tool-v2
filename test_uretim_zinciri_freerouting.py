"""
uretim_zinciri_koprusu.py'nin BÖLÜM 1 (FreeRouting) fonksiyonları için
test suite — 2026-07-31 GÜNCELLEMESİ (GÖREV 10, `DOCS/12_FreeRouting_
Fizibilite.md`).

Kod, "kicad-cli DSN desteklemiyor" tespitinden (o tespit DOĞRUYDU ama
zincirin SONU DEĞİLDİ) `pcbnew` (KiCad gömülü Python) tabanlı GERÇEK bir
zincire geçti: `dsn_disa_aktar()`/`ses_iceri_aktar()` artık
`DsnDisaAktarSonucu`/`SesIceriAktarSonucu` döndürüyor, `kicad_python=`
parametresi alıyor, `freerouting_calistir()` 240sn timeout + fail-fast Java
hatası taraması + `-Xss`/headless bayrakları içeriyor, ve
`freerouting_zinciri_calistir()` timeout/Java hatası durumunda
`otonom_kurtarma_motoru`'na devrediyor.

Bu test dosyası, TÜM bu davranışı mock/monkeypatch ile izole eder — hiçbir
test gerçek `pcbnew`/Java/FreeRouting ÇALIŞTIRMAZ (makinede KiCad olsa
bile; gerçek araçlar SENİN makinende ayrıca doğrulanmalı). `kicad_python_
yolunu_bul` ve `_pcbnew_script_calistir` fonksiyon seviyesinde sahtelenir.

**Sahteleme hedefi notu (regresyon sonrası düzeltildi):** `dsn_disa_aktar`/
`ses_iceri_aktar`, `kicad_python_yolunu_bul`'u modül seviyesinde DEĞİL,
fonksiyon gövdesi içinde `from arac_yollari import kicad_python_yolunu_bul`
ile yerel olarak import eder — bu yüzden `_sahte_script_calistir` bunu
`arac_yollari.kicad_python_yolunu_bul` üzerine `monkeypatch.setattr` ile
sahteler, `uretim_zinciri_koprusu` (`mod`) üzerine DEĞİL; `mod` üzerine
setattr yapmak bu yerel import'u yakalamaz ve gerçek KiCad kurulu olmayan
bir makinede testler `FreeRoutingDesteklenmiyorHatasi` ile başarısız olur.
"""

import subprocess
import time

import pytest

import arac_yollari
import uretim_zinciri_koprusu as mod
from uretim_zinciri_koprusu import (
    FreeRoutingDesteklenmiyorHatasi,
    dsn_disa_aktar,
    freerouting_calistir,
    freerouting_zinciri_calistir,
    ses_iceri_aktar,
)


# ------------------------------------------------------------------
# Yardımcılar — sahte `kicad_python_yolunu_bul` ve sahte Popen
# ------------------------------------------------------------------

class SahtePopen:
    """`subprocess.Popen` taklidi — `freerouting_calistir`'in satır satır
    okuma + fail-fast döngüsünü süresiz gerçek Java süreci olmadan test
    etmek için. `satirlar` tükendiğinde `poll()` `returncode` döner;
    `timeout_mi=True` ise süreç asla bitmez (readline hep boş, poll hep
    None) ve döngü ancak `zaman_asimi_sn` ile kesilir."""

    def __init__(self, komut, stdout=None, stderr=None, text=None, bufsize=None, **kwargs):
        self.komut = komut
        self.returncode = 0
        self.stdout = self  # koddaki `proc.stdout.readline()` çağrısı bu sahteyi kullanır
        self._satirlar = kwargs.pop("sahte_satirlar", [])
        self._timeout_mi = kwargs.pop("sahte_timeout_mi", False)
        self._java_hatasi = kwargs.pop("sahte_java_hatasi", None)
        self._killed = False
        self._tukendi = False
        self._index = 0
        self.cagrildi = []

    def readline(self):
        if self._index < len(self._satirlar):
            satir = self._satirlar[self._index]
            self._index += 1
            return satir
        self._tukendi = True
        if self._timeout_mi:
            time.sleep(0.01)
        return ""

    def poll(self):
        if self._timeout_mi:
            return None
        if self._tukendi:
            return self.returncode
        return None

    def kill(self):
        self._killed = True

    def wait(self, timeout=None):
        return self.returncode


def _sahte_script_calistir(monkeypatch, sonuc_objesi, timeout_firlat_mi=False):
    """`_pcbnew_script_calistir`'i, verilen `sonuc_objesi` değerini dönen
    (veya TimeoutExpired fırlatan) bir sahte ile değiştirir. Çağrıları
    `monkeypatch` nesnesine kaydeder (test içinden doğrulamak için).

    Ayrıca `arac_yollari.kicad_python_yolunu_bul`'u sahte bir yol dönecek
    şekilde değiştirir — `dsn_disa_aktar`/`ses_iceri_aktar` bunu
    `_pcbnew_script_calistir`'den ÖNCE, fonksiyon içi bir `from arac_yollari
    import kicad_python_yolunu_bul` ile çağırıyor (modül seviyesinde DEĞİL,
    bu yüzden hedef `mod` değil `arac_yollari` olmak ZORUNDA — `mod` üzerine
    setattr yapmak bu yerel import'u YAKALAMAZ). Bu olmadan gerçek KiCad
    kurulu olmayan/KICAD_PYTHON ayarsız bir makinede bu sahte zincir
    `_pcbnew_script_calistir`'e hiç ULAŞAMADAN `FreeRoutingDesteklenmiyorHatasi`
    ile patlar (bkz. `test_dsn_disa_aktar_pcbnew_yokken_fail_closed`'ın
    KASITLI olarak test ettiği aynı fail-closed yol)."""
    monkeypatch.cagrilar = []
    monkeypatch.setattr(arac_yollari, "kicad_python_yolunu_bul", lambda istenen_yol=None: "C:/sahte/kicad/python.exe")

    def sahte_script_calistir(script_metni, argv, kicad_python=None, zaman_asimi_s=60):
        monkeypatch.cagrilar.append((script_metni, argv, kicad_python, zaman_asimi_s))
        if timeout_firlat_mi:
            raise subprocess.TimeoutExpired(["python"], timeout=zaman_asimi_s)
        return sonuc_objesi

    monkeypatch.setattr(mod, "_pcbnew_script_calistir", sahte_script_calistir)


def _sonuc_objesi(returncode=0, stdout="", stderr=""):
    """Gerçek `subprocess.CompletedProcess` — `_pcbnew_script_calistir`'in
    döndürdüğü şey."""
    return subprocess.CompletedProcess(["python"], returncode=returncode, stdout=stdout, stderr=stderr)


# ------------------------------------------------------------------
# 1. dsn_disa_aktar
# ------------------------------------------------------------------

def test_dsn_disa_aktar_pcbnew_yokken_fail_closed(monkeypatch, tmp_path):
    """`pcbnew` bulunamazsa (`kicad_python_yolunu_bul` FileNotFoundError)
    zincir 'belki çalışır' diye sessizce varsaymamalı — özel istisna tipi
    fırlatmalı. (ESKİ test: NotImplementedError bekliyordu; artık
    `FreeRoutingDesteklenmiyorHatasi`, `NotImplementedError`'un alt sınıfı.)"""
    import arac_yollari

    def firtlat(istenen_yol=None):
        raise FileNotFoundError("yok (test)")

    monkeypatch.setattr(arac_yollari, "kicad_python_yolunu_bul", firtlat)
    monkeypatch.setattr(mod, "_pcbnew_script_calistir", lambda *a, **k: pytest.fail("ulaşılmamalı"))

    with pytest.raises(FreeRoutingDesteklenmiyorHatasi):
        dsn_disa_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.dsn"))

    assert issubclass(FreeRoutingDesteklenmiyorHatasi, NotImplementedError)


def test_dsn_disa_aktar_basarili_sonuc_dondurur(monkeypatch, tmp_path):
    """pcbnew scripti başarılı dönerse `DsnDisaAktarSonucu.basarili=True`
    ve dsn_yolu set edilir."""
    dsn_path = tmp_path / "board.dsn"
    dsn_path.write_text("(pcb test)", encoding="utf-8")  # script 'dosya var' kontrolü için oluşturur
    sonuc = _sonuc_objesi(returncode=0, stdout='{"basarili": true}')
    _sahte_script_calistir(monkeypatch, sonuc)

    cikti = dsn_disa_aktar(str(tmp_path / "board.kicad_pcb"), str(dsn_path))

    assert cikti.basarili is True
    assert cikti.dsn_yolu == str(dsn_path)
    assert cikti.stderr == ""


def test_dsn_disa_aktar_script_hatasinda_basarisiz(monkeypatch, tmp_path):
    """Script returncode != 0 döndüğünde (pcbnew ExportSpecctraDSN False)
    `basarili=False` dönmeli — 'başardım' DEMEMELİ."""
    dsn_path = tmp_path / "board.dsn"
    dsn_path.write_text("x", encoding="utf-8")
    sonuc = _sonuc_objesi(returncode=2, stdout="", stderr="export hatası (test)")
    _sahte_script_calistir(monkeypatch, sonuc)

    cikti = dsn_disa_aktar(str(tmp_path / "board.kicad_pcb"), str(dsn_path))

    assert cikti.basarili is False
    assert cikti.dsn_yolu is None


def test_dsn_disa_aktar_cikti_dosyasi_yoksa_basarisiz(monkeypatch, tmp_path):
    """Script returncode=0 ama çıktı .dsn dosyası oluşmamışsa — bu da
    başarısız sayılmalı (returncode'a körü körüne güvenilmez)."""
    sonuc = _sonuc_objesi(returncode=0, stdout="")
    _sahte_script_calistir(monkeypatch, sonuc)

    cikti = dsn_disa_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "yok.dsn"))

    assert cikti.basarili is False
    assert cikti.dsn_yolu is None


def test_dsn_disa_aktar_timeout_zaman_asimi_olarak_raporlanir(monkeypatch, tmp_path):
    """Script `subprocess.TimeoutExpired` fırlatırsa bu bir çalışma hatası
    değil zaman aşımı — `basarili=False` ve stderr'de timeout mesajı."""
    _sahte_script_calistir(monkeypatch, None, timeout_firlat_mi=True)

    cikti = dsn_disa_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.dsn"))

    assert cikti.basarili is False
    assert "timeout" in cikti.stderr.lower()


# ------------------------------------------------------------------
# 2. ses_iceri_aktar
# ------------------------------------------------------------------

def test_ses_iceri_aktar_pcbnew_yokken_fail_closed(monkeypatch, tmp_path):
    import arac_yollari

    def firtlat(istenen_yol=None):
        raise FileNotFoundError("yok (test)")

    monkeypatch.setattr(arac_yollari, "kicad_python_yolunu_bul", firtlat)
    monkeypatch.setattr(mod, "_pcbnew_script_calistir", lambda *a, **k: pytest.fail("ulaşılmamalı"))

    with pytest.raises(FreeRoutingDesteklenmiyorHatasi):
        ses_iceri_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.ses"))


def test_ses_iceri_aktar_izler_degistiyse_basarili(monkeypatch, tmp_path):
    """SES import scripti 'izler değişti' döndürürse `basarili=True` ve
    `izler_degisti=True` — çağıran taraf ikisini birden kontrol eder."""
    stdout = '{"basarili": true, "iz_sayisi_once": 0, "iz_sayisi_sonra": 5, "izler_degisti": true}'
    _sahte_script_calistir(monkeypatch, _sonuc_objesi(returncode=0, stdout=stdout))

    cikti = ses_iceri_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.ses"))

    assert cikti.basarili is True
    assert cikti.izler_degisti is True
    assert cikti.iz_sayisi_once == 0
    assert cikti.iz_sayisi_sonra == 5


def test_ses_iceri_aktar_izler_degismediyse_basarisiz_sayilmalidir(monkeypatch, tmp_path):
    """DOCS/12 E2 tuzağı: `ImportSpecctraSES` True dönse bile iz sayısı
    değişmediyse (padstack eşleşmedi) bu 'routing tamamlandı' SAYILMAMALI —
    `izler_degisti=False` açıkça raporlanır, çağıran kontrol eder."""
    stdout = '{"basarili": true, "iz_sayisi_once": 5, "iz_sayisi_sonra": 5, "izler_degisti": false}'
    _sahte_script_calistir(monkeypatch, _sonuc_objesi(returncode=0, stdout=stdout))

    cikti = ses_iceri_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.ses"))

    assert cikti.basarili is True
    assert cikti.izler_degisti is False


def test_ses_iceri_aktar_json_parse_hatasinda_basarisiz(monkeypatch, tmp_path):
    """Script çıktısı JSON değilse sessizce 'başardım' DENMEMELİ — çıktı
    okunamıyorsa `basarili=False`."""
    _sahte_script_calistir(monkeypatch, _sonuc_objesi(returncode=0, stdout="JUNK çıktı"))

    cikti = ses_iceri_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.ses"))

    assert cikti.basarili is False


def test_ses_iceri_aktar_timeout_zaman_asimi_olarak_raporlanir(monkeypatch, tmp_path):
    _sahte_script_calistir(monkeypatch, None, timeout_firlat_mi=True)

    cikti = ses_iceri_aktar(str(tmp_path / "board.kicad_pcb"), str(tmp_path / "board.ses"))

    assert cikti.basarili is False
    assert "timeout" in cikti.stderr.lower()


# ------------------------------------------------------------------
# 3. freerouting_calistir (Popen mock)
# ------------------------------------------------------------------

def test_freerouting_calistir_basarili_akış(monkeypatch, tmp_path):
    """Java süreci normal biterse (returncode 0 + .ses oluştu) `basarili=True`."""
    ses_path = tmp_path / "board.ses"
    ses_path.write_text("(session x)", encoding="utf-8")

    def sahte_popen(komut, **kwargs):
        return SahtePopen(komut, sahte_satirlar=["INFO routing bitti\n"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", sahte_popen)

    cikti = freerouting_calistir(str(tmp_path / "board.dsn"), str(ses_path), zaman_asimi_sn=5)

    assert cikti.basarili is True
    assert cikti.zaman_asimi_mi is False
    assert cikti.java_hatasi_mi is False
    assert cikti.ses_dosya_yolu == str(ses_path)


def test_freerouting_calistir_timeout_zaman_asimi_mi(monkeypatch, tmp_path):
    """Süreç hiç bitmiyorsa (poll hep None, satır yok) `zaman_asimi_mi=True`
    ve `basarili=False` — 240sn doluncaya kadar beklemez, küçük zaman_asimi_sn
    ile hızlı test edilir."""
    def sahte_popen(komut, **kwargs):
        return SahtePopen(komut, sahte_timeout_mi=True, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", sahte_popen)

    cikti = freerouting_calistir(str(tmp_path / "board.dsn"), str(tmp_path / "board.ses"), zaman_asimi_sn=1)

    assert cikti.zaman_asimi_mi is True
    assert cikti.basarili is False


def test_freerouting_calistir_java_hatasi_fail_fast(monkeypatch, tmp_path):
    """stdout'ta Java hata deseni görülür görülmez süreç HEMEN kill edilir
    (tam zaman aşımı beklenmez) ve `java_hatasi_mi=True` döner."""
    kill_edildi = {}

    def sahte_popen(komut, **kwargs):
        p = SahtePopen(komut, sahte_satirlar=["INFO ... java.lang.StackOverflowError ..."], **kwargs)
        return p

    monkeypatch.setattr(subprocess, "Popen", sahte_popen)

    cikti = freerouting_calistir(str(tmp_path / "board.dsn"), str(tmp_path / "board.ses"), zaman_asimi_sn=60)

    assert cikti.java_hatasi_mi is True
    assert cikti.basarili is False
    assert "StackOverflowError" in cikti.stderr


# ------------------------------------------------------------------
# 4. freerouting_zinciri_calistir (orkestratör)
# ------------------------------------------------------------------

def test_freerouting_zinciri_bayrak_kapaliyken_en_tepede_durur(monkeypatch, tmp_path):
    """`KICAD10_DSN_DESTEKLENIYOR=False` iken zincir dsn_disa_aktar'a HİÇ
    ulaşmadan `FreeRoutingDesteklenmiyorHatasi` fırlatmalı — savunma
    derinliği kapısı."""
    monkeypatch.setattr(mod, "KICAD10_DSN_DESTEKLENIYOR", False)
    monkeypatch.setattr(mod, "dsn_disa_aktar", lambda *a, **k: pytest.fail("ulaşılmamalı"))

    with pytest.raises(FreeRoutingDesteklenmiyorHatasi, match="KICAD10_DSN_DESTEKLENIYOR"):
        freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))


def test_freerouting_zinciri_dsn_export_basarisizsa_durur(monkeypatch, tmp_path):
    """DSN export başarısızsa FreeRouting ÇALIŞTIRILMAMALI — `basarili=False`."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(False, None, "", "dsn hatası (test)")
    monkeypatch.setattr(mod, "dsn_disa_aktar", lambda *a, **k: dsn_sonuc)
    monkeypatch.setattr(mod, "freerouting_calistir", lambda *a, **k: pytest.fail("ulaşılmamalı"))

    cikti = freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))

    assert cikti.basarili is False


def test_freerouting_zinciri_timeout_otonom_fallbacka_devreder(monkeypatch, tmp_path):
    """FreeRouting 240sn'de bitmezse (zaman_asimi_mi) zincir
    `freerouting_zaman_asiminda_otonom_devam_et`'i çağırır, kararlar logu
    yazar ve fallback sonucunu döner — NEEDS_HUMAN ile DURMAZ."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(True, "board.dsn", "", "")
    fr_sonuc = mod.FreeRoutingSonucu(False, None, "", "timeout", zaman_asimi_mi=True)

    cagrildi = {}

    def sahte_dsn(*a, **k):
        return dsn_sonuc

    def sahte_fr(*a, **k):
        return fr_sonuc

    def sahte_fallback(*a, **k):
        cagrildi["fallback"] = True
        return {"toplam_net": 2, "yonlendirilen_net": 2, "basarisiz_net_sayisi": 0, "detaylar": []}

    def sahte_log(*a, **k):
        cagrildi["log"] = True

    monkeypatch.setattr(mod, "dsn_disa_aktar", sahte_dsn)
    monkeypatch.setattr(mod, "freerouting_calistir", sahte_fr)
    monkeypatch.setattr(mod, "freerouting_zaman_asiminda_otonom_devam_et", sahte_fallback)
    monkeypatch.setattr(mod, "_kararlar_logu_yaz", sahte_log)

    cikti = freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))

    assert cagrildi["fallback"] is True
    assert cagrildi["log"] is True
    assert cikti.zaman_asimi_mi is True
    assert cikti.basarili is True  # fallback'te 0 başarısız net -> başarılı


def test_freerouting_zinciri_java_hatasi_otonom_fallbacka_devreder(monkeypatch, tmp_path):
    """FreeRouting Java istisnasıyla çökerse de (java_hatasi_mi) AYNI
    fallback yolu izlenir — zaman aşımı beklenmeden."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(True, "board.dsn", "", "")
    fr_sonuc = mod.FreeRoutingSonucu(False, None, "", "StackOverflowError", java_hatasi_mi=True)

    cagrildi = {}

    def sahte_dsn(*a, **k):
        return dsn_sonuc

    def sahte_fr(*a, **k):
        return fr_sonuc

    def sahte_fallback(*a, **k):
        cagrildi["fallback"] = True
        return {"toplam_net": 1, "yonlendirilen_net": 0, "basarisiz_net_sayisi": 1, "detaylar": []}

    monkeypatch.setattr(mod, "dsn_disa_aktar", sahte_dsn)
    monkeypatch.setattr(mod, "freerouting_calistir", sahte_fr)
    monkeypatch.setattr(mod, "freerouting_zaman_asiminda_otonom_devam_et", sahte_fallback)

    cikti = freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))

    assert cagrildi["fallback"] is True
    assert cikti.java_hatasi_mi is True
    assert cikti.basarili is False  # fallback'te 1 başarısız net -> başarısız


def test_freerouting_zinciri_timeout_fallback_kapaliysa_fallback_cagrilmaz(monkeypatch, tmp_path):
    """`otonom_fallback=False` ise timeout durumunda fallback ÇAĞRILMAMALI —
    çağıran taraf kendi kararını verir."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(True, "board.dsn", "", "")
    fr_sonuc = mod.FreeRoutingSonucu(False, None, "", "timeout", zaman_asimi_mi=True)

    monkeypatch.setattr(mod, "dsn_disa_aktar", lambda *a, **k: dsn_sonuc)
    monkeypatch.setattr(mod, "freerouting_calistir", lambda *a, **k: fr_sonuc)
    monkeypatch.setattr(mod, "freerouting_zaman_asiminda_otonom_devam_et",
                        lambda *a, **k: pytest.fail("fallback çağrılmamalı"))

    cikti = freerouting_zinciri_calistir(
        "board.kicad_pcb", calisma_dizini=str(tmp_path), otonom_fallback=False,
    )

    assert cikti.zaman_asimi_mi is True
    assert cikti.basarili is False


def test_freerouting_zinciri_ses_import_iz_degismediyse_basarisiz(monkeypatch, tmp_path):
    """FreeRouting başarılı + SES import `izler_degisti=False` dönerse zincir
    'routing tamamlandı' SAYMAMALI — DOCS/12 E2 koruması."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(True, "board.dsn", "", "")
    fr_sonuc = mod.FreeRoutingSonucu(True, "board.ses", "", "")
    ses_sonuc = mod.SesIceriAktarSonucu(True, 5, 5, False, "", "")

    monkeypatch.setattr(mod, "dsn_disa_aktar", lambda *a, **k: dsn_sonuc)
    monkeypatch.setattr(mod, "freerouting_calistir", lambda *a, **k: fr_sonuc)
    monkeypatch.setattr(mod, "ses_iceri_aktar", lambda *a, **k: ses_sonuc)

    cikti = freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))

    assert cikti.basarili is False


def test_freerouting_zinciri_basarili_uçtan_uca_akis(monkeypatch, tmp_path):
    """Başarılı akış: DSN export OK -> FreeRouting OK -> SES import OK +
    izler değişti -> `basarili=True`."""
    dsn_sonuc = mod.DsnDisaAktarSonucu(True, "board.dsn", "", "")
    fr_sonuc = mod.FreeRoutingSonucu(True, "board.ses", "", "")
    ses_sonuc = mod.SesIceriAktarSonucu(True, 0, 8, True, "", "")

    monkeypatch.setattr(mod, "dsn_disa_aktar", lambda *a, **k: dsn_sonuc)
    monkeypatch.setattr(mod, "freerouting_calistir", lambda *a, **k: fr_sonuc)
    monkeypatch.setattr(mod, "ses_iceri_aktar", lambda *a, **k: ses_sonuc)

    cikti = freerouting_zinciri_calistir("board.kicad_pcb", calisma_dizini=str(tmp_path))

    assert cikti.basarili is True
    assert cikti.ses_dosya_yolu == "board.ses"
