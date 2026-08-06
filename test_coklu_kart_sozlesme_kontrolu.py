"""coklu_kart_sozlesme_kontrolu.py için test suite.

`test_pcbnew_koprusu.py` ile AYNI disiplini izler: gerçek `pcbnew`'i
import ETMEZ (bu ortamda kurulu değil), `sys.modules["pcbnew"]`'e taklit
bir modül yerleştirip duck-typing mock nesneleriyle test eder.

Test planı (görev tanımından):
  1. Sözleşmeyle TUTARLI iki sahte board -> PASS.
  2. Kamera kartında bir pinin net adı DEĞİŞTİRİLMİŞ -> FAIL, hangi pin
     olduğu ihlallerde görünür.
  3. Ana kartta 6 konnektörden birinin pin sırası TERS -> sadece o
     konnektör için FAIL, diğer 5'i etkilemez.
  4. VC ID'lerden ikisi aynı değere atanmış -> FAIL, hangi iki kart
     raporlanır.
  5. Güç bütçesi aşımı senaryosu -> FAIL.
  + taranan=0 hiçbir zaman PASS sayılmaz (konnektör/atama bulunamama
    senaryoları KAPSAM_YOK).
"""

from __future__ import annotations

import sys
from typing import List, Optional

import pytest

from bulgu_sozlesmesi import BulguDurumu
from coklu_kart_sozlesme_kontrolu import (
    ArayuzSozlesmesi,
    GucButcesi,
    KonnektorTanimi,
    PinTanimi,
    VcIdPlani,
    ana_kart_dogrula,
    coklu_kart_karari_olustur,
    guc_butcesi_kontrolu,
    kamera_karti_dogrula,
    sozlesme_yukle,
    tum_coklu_kart_kontrollerini_calistir,
    vc_id_cakisma_kontrolu,
)

# ------------------------------------------------------------------
# Taklit `pcbnew` modülü — sadece bu modülün kullandığı yüzey:
# board.GetFootprints() / fp.GetReference() / fp.Pads() /
# pad.GetNumber() / pad.GetNetname()
# ------------------------------------------------------------------


class SahtePad:
    def __init__(self, numara: str, net: str):
        self._numara = numara
        self._net = net

    def GetNumber(self) -> str:
        return self._numara

    def GetNetname(self) -> str:
        return self._net


class SahteFootprint:
    def __init__(self, ref: str, padlar: List[SahtePad]):
        self._ref = ref
        self._padlar = padlar

    def GetReference(self) -> str:
        return self._ref

    def Pads(self) -> List[SahtePad]:
        return self._padlar


class SahteBoard:
    def __init__(self, footprints: List[SahteFootprint]):
        self._footprints = footprints

    def GetFootprints(self):
        return self._footprints


class TaklitPcbnew:
    def __init__(self, board: SahteBoard):
        self._board = board

    def LoadBoard(self, yol: str) -> SahteBoard:
        return self._board


def _taklit_pcbnew_yukle(board: SahteBoard) -> TaklitPcbnew:
    taklit = TaklitPcbnew(board)
    sys.modules["pcbnew"] = taklit
    return taklit


@pytest.fixture(autouse=True)
def _taklit_pcbnew_otomatik():
    orijinal = sys.modules.get("pcbnew")
    yield
    if orijinal is None:
        sys.modules.pop("pcbnew", None)
    else:
        sys.modules["pcbnew"] = orijinal


# ------------------------------------------------------------------
# Ortak sözleşme + board fabrikaları
# ------------------------------------------------------------------


def _ornek_sozlesme(**overrides) -> ArayuzSozlesmesi:
    pinler = [
        PinTanimi(no=1, net="GMSL_A_P", yon="diferansiyel_cikis", voltaj=None),
        PinTanimi(no=2, net="GMSL_A_N", yon="diferansiyel_cikis", voltaj=None),
        PinTanimi(no=3, net="VCAM", yon="guc_girisi", voltaj="12V"),
        PinTanimi(no=4, net="GND", yon="guc_donusu", voltaj=None),
    ]
    konnektor = KonnektorTanimi(
        pin_sayisi=4,
        kamera_karti_referans="J1",
        ana_kart_referans_sablonu="J{kart}",
        pinler=pinler,
        ana_kart_net_sablonu="{net}",
    )
    guc_butcesi = GucButcesi(
        kart_basi_maks_akim_a=0.4, kart_sayisi=6, ana_kart_giris_marj_yuzde=25,
        ana_kart_guc_girisi_maks_a=3.5,
    )
    vc_id = VcIdPlani(
        aralik=(0, 5),
        atama={f"kart_{i}": i - 1 for i in range(1, 7)},
    )
    sozlesme = ArayuzSozlesmesi(versiyon=1, konnektor=konnektor, guc_butcesi=guc_butcesi, vc_id=vc_id)
    for anahtar, deger in overrides.items():
        setattr(sozlesme, anahtar, deger)
    return sozlesme


def _uyumlu_konnektor(ref: str, pinler: List[PinTanimi]) -> SahteFootprint:
    return SahteFootprint(ref, [SahtePad(str(p.no), p.net) for p in pinler])


def _kamera_karti_board(sozlesme: ArayuzSozlesmesi, ref: Optional[str] = None) -> SahteBoard:
    ref = ref or sozlesme.konnektor.kamera_karti_referans
    return SahteBoard([_uyumlu_konnektor(ref, sozlesme.konnektor.pinler)])


def _ana_kart_board(sozlesme: ArayuzSozlesmesi, konnektor_sayisi: int = 6) -> SahteBoard:
    fps = []
    for kart_no in range(1, konnektor_sayisi + 1):
        ref = sozlesme.konnektor.ana_kart_referans_sablonu.format(kart=kart_no)
        fps.append(_uyumlu_konnektor(ref, sozlesme.konnektor.pinler))
    return SahteBoard(fps)


# ------------------------------------------------------------------
# 1. Sözleşmeyle TUTARLI -> PASS
# ------------------------------------------------------------------


class TestTutarliDurum:
    def test_kamera_karti_pass(self):
        sozlesme = _ornek_sozlesme()
        board = _kamera_karti_board(sozlesme)
        _taklit_pcbnew_yukle(board)

        bulgu = kamera_karti_dogrula("kamera.kicad_pcb", sozlesme)

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 4
        assert bulgu.ihlaller == []

    def test_ana_kart_pass_6_konnektor(self):
        sozlesme = _ornek_sozlesme()
        board = _ana_kart_board(sozlesme, konnektor_sayisi=6)
        _taklit_pcbnew_yukle(board)

        bulgu = ana_kart_dogrula("ana_kart.kicad_pcb", sozlesme, konnektor_sayisi=6)

        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 24  # 6 konnektor x 4 pin
        assert bulgu.ihlaller == []


# ------------------------------------------------------------------
# 2. Kamera kartında bir pinin net adı DEĞİŞTİRİLMİŞ -> FAIL
# ------------------------------------------------------------------


class TestKameraKartiPinDegisikligi:
    def test_tek_pin_net_uyumsuz_fail_ve_pin_raporlanir(self):
        sozlesme = _ornek_sozlesme()
        bozuk_pinler = [
            PinTanimi(no=1, net="GMSL_A_P", yon="diferansiyel_cikis", voltaj=None),
            PinTanimi(no=2, net="GMSL_A_N", yon="diferansiyel_cikis", voltaj=None),
            PinTanimi(no=3, net="YANLIS_NET", yon="guc_girisi", voltaj="12V"),  # bilerek bozuldu
            PinTanimi(no=4, net="GND", yon="guc_donusu", voltaj=None),
        ]
        board = SahteBoard([_uyumlu_konnektor("J1", bozuk_pinler)])
        _taklit_pcbnew_yukle(board)

        bulgu = kamera_karti_dogrula("kamera.kicad_pcb", sozlesme)

        assert bulgu.durum == BulguDurumu.FAIL
        assert len(bulgu.ihlaller) == 1
        ihlal = bulgu.ihlaller[0]
        assert ihlal["pin"] == 3
        assert ihlal["beklenen_net"] == "VCAM"
        assert ihlal["bulunan_net"] == "YANLIS_NET"
        assert ihlal["sorun"] == "net_uyumsuz"


# ------------------------------------------------------------------
# 3. Ana kartta 6 konnektörden BİRİNİN pin sırası TERS -> sadece o
#    konnektör FAIL, diğer 5'i etkilemez
# ------------------------------------------------------------------


class TestAnaKartTekKonnektorHatasi:
    def test_pin_sirasi_ters_sadece_o_konnektoru_etkiler(self):
        sozlesme = _ornek_sozlesme()
        fps = []
        for kart_no in range(1, 7):
            ref = f"J{kart_no}"
            if kart_no == 3:
                # pin sırası TERS: pad numaraları 1<->2, 3<->4 çapraz bağlı
                ters_pinler = [
                    PinTanimi(no=1, net="GMSL_A_N", yon="diferansiyel_cikis", voltaj=None),
                    PinTanimi(no=2, net="GMSL_A_P", yon="diferansiyel_cikis", voltaj=None),
                    PinTanimi(no=3, net="GND", yon="guc_donusu", voltaj=None),
                    PinTanimi(no=4, net="VCAM", yon="guc_girisi", voltaj="12V"),
                ]
                fps.append(_uyumlu_konnektor(ref, ters_pinler))
            else:
                fps.append(_uyumlu_konnektor(ref, sozlesme.konnektor.pinler))
        board = SahteBoard(fps)
        _taklit_pcbnew_yukle(board)

        bulgu = ana_kart_dogrula("ana_kart.kicad_pcb", sozlesme, konnektor_sayisi=6)

        assert bulgu.durum == BulguDurumu.FAIL
        # SADECE konnektor_3'e ait ihlaller olmalı, diğer 5 konnektör temiz
        konumlar = {ihlal["konum"] for ihlal in bulgu.ihlaller}
        assert all(konum.startswith("konnektor_3.") for konum in konumlar)
        assert len(bulgu.ihlaller) == 4  # 4 pinin hepsi çapraz bağlı


# ------------------------------------------------------------------
# taranan=0 durumları -> KAPSAM_YOK, ASLA sessiz PASS değil
# ------------------------------------------------------------------


class TestKapsamYok:
    def test_kamera_karti_konnektoru_bulunamazsa_kapsam_yok(self):
        sozlesme = _ornek_sozlesme()
        board = SahteBoard([])  # J1 hiç yok
        _taklit_pcbnew_yukle(board)

        bulgu = kamera_karti_dogrula("kamera.kicad_pcb", sozlesme)

        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0
        assert bulgu.gecti_mi is False

    def test_ana_kartta_hicbir_konnektor_bulunamazsa_kapsam_yok(self):
        sozlesme = _ornek_sozlesme()
        board = SahteBoard([])
        _taklit_pcbnew_yukle(board)

        bulgu = ana_kart_dogrula("ana_kart.kicad_pcb", sozlesme, konnektor_sayisi=6)

        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0

    def test_ana_kartta_bir_konnektor_eksikse_ihlal_olarak_raporlanir(self):
        sozlesme = _ornek_sozlesme()
        board = _ana_kart_board(sozlesme, konnektor_sayisi=6)
        # J4'ü sil
        board._footprints = [fp for fp in board._footprints if fp.GetReference() != "J4"]
        _taklit_pcbnew_yukle(board)

        bulgu = ana_kart_dogrula("ana_kart.kicad_pcb", sozlesme, konnektor_sayisi=6)

        assert bulgu.durum == BulguDurumu.FAIL  # diğer 5 konnektör tarandı, taranan>0
        eksik_ihlali = [i for i in bulgu.ihlaller if i.get("sorun") == "konnektor_bulunamadi"]
        assert len(eksik_ihlali) == 1
        assert "J4" in eksik_ihlali[0]["konnektor_referanslari"]

    def test_pcbnew_kurulu_degilse_kapsam_yok(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "pcbnew", raising=False)
        sozlesme = _ornek_sozlesme()

        bulgu = kamera_karti_dogrula("kamera.kicad_pcb", sozlesme)

        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0


# ------------------------------------------------------------------
# 4. VC ID çakışması -> FAIL, hangi kartlar çakıştığı raporlanır
# ------------------------------------------------------------------


class TestVcIdCakismasi:
    def test_tutarli_atama_pass(self):
        sozlesme = _ornek_sozlesme()
        bulgu = vc_id_cakisma_kontrolu(sozlesme)
        assert bulgu.durum == BulguDurumu.PASS
        assert bulgu.taranan == 6

    def test_iki_kart_ayni_vc_id_fail(self):
        sozlesme = _ornek_sozlesme()
        sozlesme.vc_id.atama["kart_2"] = sozlesme.vc_id.atama["kart_1"]  # bilerek çakıştır

        bulgu = vc_id_cakisma_kontrolu(sozlesme)

        assert bulgu.durum == BulguDurumu.FAIL
        cakisma_ihlalleri = [i for i in bulgu.ihlaller if i["sorun"] == "cakisma"]
        assert len(cakisma_ihlalleri) == 1
        assert set(cakisma_ihlalleri[0]["kartlar"]) == {"kart_1", "kart_2"}

    def test_araligin_disindaki_vc_id_fail(self):
        sozlesme = _ornek_sozlesme()
        sozlesme.vc_id.atama["kart_1"] = 99

        bulgu = vc_id_cakisma_kontrolu(sozlesme)

        assert bulgu.durum == BulguDurumu.FAIL
        aralik_ihlalleri = [i for i in bulgu.ihlaller if i["sorun"] == "aralik_disi"]
        assert len(aralik_ihlalleri) == 1
        assert aralik_ihlalleri[0]["kart"] == "kart_1"

    def test_atama_bossa_kapsam_yok(self):
        sozlesme = _ornek_sozlesme()
        sozlesme.vc_id.atama = {}
        bulgu = vc_id_cakisma_kontrolu(sozlesme)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0


# ------------------------------------------------------------------
# 5. Güç bütçesi aşımı -> FAIL
# ------------------------------------------------------------------


class TestGucButcesi:
    def test_butce_yeterliyse_pass(self):
        sozlesme = _ornek_sozlesme()
        # gerekli = 0.4 * 6 * 1.25 = 3.0A, sinir = 3.5A -> PASS
        bulgu = guc_butcesi_kontrolu(sozlesme)
        assert bulgu.durum == BulguDurumu.PASS

    def test_butce_asiliyorsa_fail(self):
        sozlesme = _ornek_sozlesme()
        sozlesme.guc_butcesi.ana_kart_guc_girisi_maks_a = 2.0  # 3.0A gerekliye yetersiz

        bulgu = guc_butcesi_kontrolu(sozlesme)

        assert bulgu.durum == BulguDurumu.FAIL
        assert len(bulgu.ihlaller) == 1
        ihlal = bulgu.ihlaller[0]
        assert ihlal["sorun"] == "guc_butcesi_asimi"
        assert ihlal["gerekli_a"] == pytest.approx(3.0)
        assert ihlal["ana_kart_giris_siniri_a"] == 2.0

    def test_cagri_zamaninda_sinir_verilirse_sozlesme_degerini_ezer(self):
        sozlesme = _ornek_sozlesme()
        bulgu = guc_butcesi_kontrolu(sozlesme, ana_kart_guc_girisi_maks_a=1.0)
        assert bulgu.durum == BulguDurumu.FAIL

    def test_sinir_hic_tanimli_degilse_kapsam_yok(self):
        sozlesme = _ornek_sozlesme()
        sozlesme.guc_butcesi.ana_kart_guc_girisi_maks_a = None
        bulgu = guc_butcesi_kontrolu(sozlesme)
        assert bulgu.durum == BulguDurumu.KAPSAM_YOK
        assert bulgu.taranan == 0


# ------------------------------------------------------------------
# sozlesme_yukle — gerçek YAML dosyasından round-trip
# ------------------------------------------------------------------


class TestSozlesmeYukle:
    def test_yaml_dosyasindan_dogru_parse_edilir(self, tmp_path):
        yaml_metni = """
versiyon: 1
konnektor:
  pin_sayisi: 2
  kamera_karti_referans: "J1"
  ana_kart_referans_sablonu: "J{kart}"
  pinler:
    - {"no": 1, net: "VCAM", yon: "guc_girisi", voltaj: "12V"}
    - {"no": 2, net: "GND", yon: "guc_donusu", voltaj: null}
guc_butcesi:
  kart_basi_maks_akim_a: 0.4
  kart_sayisi: 6
  ana_kart_giris_marj_yuzde: 25
  ana_kart_guc_girisi_maks_a: 3.5
vc_id:
  aralik: [0, 5]
  atama:
    kart_1: 0
    kart_2: 1
"""
        yol = tmp_path / "sozlesme.yaml"
        yol.write_text(yaml_metni, encoding="utf-8")

        sozlesme = sozlesme_yukle(yol)

        assert sozlesme.versiyon == 1
        assert sozlesme.konnektor.pin_sayisi == 2
        assert sozlesme.konnektor.pinler[0].net == "VCAM"
        assert sozlesme.konnektor.ana_kart_net_sablonu == "{net}"  # varsayılan
        assert sozlesme.guc_butcesi.ana_kart_guc_girisi_maks_a == 3.5
        assert sozlesme.vc_id.aralik == (0, 5)
        assert sozlesme.vc_id.atama == {"kart_1": 0, "kart_2": 1}

    def test_gercek_repo_sozlesmesi_yuklenebilir(self):
        """`arayuz_sozlesmesi.yaml` (repo kökü) gerçekten parse edilebiliyor mu."""
        from pathlib import Path

        yol = Path(__file__).resolve().parent / "arayuz_sozlesmesi.yaml"
        sozlesme = sozlesme_yukle(yol)
        assert sozlesme.versiyon == 1
        assert len(sozlesme.konnektor.pinler) == sozlesme.konnektor.pin_sayisi
        assert len(sozlesme.vc_id.atama) == sozlesme.guc_butcesi.kart_sayisi


# ------------------------------------------------------------------
# Governance köprüsü — karar_birimleri.py entegrasyonu
# ------------------------------------------------------------------


class TestGovernanceKoprusu:
    def test_pass_ise_karar_kabul_edildi(self):
        from karar_birimleri import KararDurumu

        karar = coklu_kart_karari_olustur(pass_mi=True)
        assert karar.durum == KararDurumu.KABUL_EDILDI
        assert karar.gecersiz_kilinma_sebebi is None

    def test_fail_ise_karar_acik(self):
        from karar_birimleri import KararDurumu

        karar = coklu_kart_karari_olustur(pass_mi=False, ozet_detay="vc id cakismasi")
        assert karar.durum == KararDurumu.ACIK
        assert "vc id cakismasi" in karar.gecersiz_kilinma_sebebi


# ------------------------------------------------------------------
# Toplu çalıştırıcı — kablolamanın doğru olduğunu doğrular
# ------------------------------------------------------------------


class TestTumKontrollerCalistir:
    def test_dort_bulgu_doner_ve_hepsi_pass(self, tmp_path):
        sozlesme = _ornek_sozlesme()
        kamera_board = _kamera_karti_board(sozlesme)
        # tek board nesnesi hem kamera hem ana kart LoadBoard çağrısına
        # dönmeli; iki ayrı çağrı olduğu için sırayla iki farklı board
        # döndürecek bir taklit kullanıyoruz.
        ana_board = _ana_kart_board(sozlesme, konnektor_sayisi=6)

        class SiraliTaklitPcbnew:
            def __init__(self, boardlar):
                self._boardlar = list(boardlar)

            def LoadBoard(self, yol):
                return self._boardlar.pop(0)

        sys.modules["pcbnew"] = SiraliTaklitPcbnew([kamera_board, ana_board])

        yaml_yolu = tmp_path / "sozlesme.yaml"
        import yaml as yamllib

        yaml_yolu.write_text(
            yamllib.dump({
                "versiyon": 1,
                "konnektor": {
                    "pin_sayisi": 4,
                    "kamera_karti_referans": "J1",
                    "ana_kart_referans_sablonu": "J{kart}",
                    "pinler": [
                        {"no": 1, "net": "GMSL_A_P", "yon": "diferansiyel_cikis", "voltaj": None},
                        {"no": 2, "net": "GMSL_A_N", "yon": "diferansiyel_cikis", "voltaj": None},
                        {"no": 3, "net": "VCAM", "yon": "guc_girisi", "voltaj": "12V"},
                        {"no": 4, "net": "GND", "yon": "guc_donusu", "voltaj": None},
                    ],
                },
                "guc_butcesi": {
                    "kart_basi_maks_akim_a": 0.4, "kart_sayisi": 6,
                    "ana_kart_giris_marj_yuzde": 25, "ana_kart_guc_girisi_maks_a": 3.5,
                },
                "vc_id": {"aralik": [0, 5], "atama": {f"kart_{i}": i - 1 for i in range(1, 7)}},
            }),
            encoding="utf-8",
        )

        bulgular = tum_coklu_kart_kontrollerini_calistir(
            yaml_yolu, "kamera.kicad_pcb", "ana_kart.kicad_pcb", konnektor_sayisi=6,
        )

        assert len(bulgular) == 4
        assert all(b.durum == BulguDurumu.PASS for b in bulgular)
