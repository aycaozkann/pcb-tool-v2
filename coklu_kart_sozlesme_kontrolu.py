"""
coklu_kart_sozlesme_kontrolu.py
=================================
Çoklu Kart (Kamera Kartı x6 + Ana Kart) Arayüz Orkestrasyonu.

NEDEN BU DOSYA VAR:
KiCad'de resmi bir "multi-board" modu yok. 360° kamera sisteminde kamera
kartı (TEK tasarım, 6 kez üretilir) ile ana/hub kart İKİ FARKLI KiCad
projesidir — aralarındaki tek gerçek bağ (konnektör pinout'u, VC ID atama
şeması, güç bütçesi toplamı) hiçbir yerde MAKİNE TARAFINDAN doğrulanmıyordu.
Biri değişip diğeri güncellenmezse (örn. kamera kartında bir pin sırası
değişir, ana kart konnektörü hâlâ eskisini bekler) bu ancak fiziksel
bring-up'ta, kart üretildikten SONRA fark edilirdi.

Bu modül KiCad'in KENDİ mimarisine müdahale ETMEZ (schematic-level
cross-board net highlighting yazmıyoruz) — iki projenin ÇIKTISINI
(`arayuz_sozlesmesi.yaml` tek-kaynak sözleşmesine karşı gerçek `.kicad_pcb`
konnektör pin haritaları) karşılaştıran, KiCad DIŞINDA bir kontrol
katmanıdır.

TASARIM KURALLARI (bkz. `bulgu_sozlesmesi.py`, `pcbnew_koprusu.py`):
- Her kontrol `Bulgu` sözleşmesiyle döner — eski `List[str]` deseni YOK.
- `taranan == 0` ASLA PASS değildir: konnektör bulunamazsa (isim eşleşmedi)
  bu KAPSAM_YOK'tur, sessizce "hata yok" denmez.
- Pin bazında karşılaştırma, isimden değil SIRADAN: her pin numarası kendi
  beklenen net adına karşı kontrol edilir (net'in board'da "bir yerde var
  olması" YETMEZ).
- Ana karttaki 6 konnektörün HER BİRİ AYRI AYRI doğrulanır — birinde pin
  sırası ters olsa da sadece O konnektör FAIL olur, diğer 5'i etkilemez.
- pcbnew erişimi `pcbnew_koprusu.py`'nin MEVCUT `_pcbnew_veya_kapsam_yok()`
  yardımcısını TEKRAR KULLANIR — yeni bir board-açma/KAPSAM_YOK deseni
  icat edilmedi.

AĞ/ARAÇ UYARISI (proje disipliniyle uyumlu, bkz. `pcbnew_koprusu.py`
başlığı): bu ortamda gerçek bir KiCad kurulumu ve dolayısıyla `pcbnew`
modülü YOKTUR. `import pcbnew` satırına kadar tüm mantık doğru yazılmış
olarak sunulur, ama pcbnew'e dokunan fonksiyonlar (`kamera_karti_dogrula`,
`ana_kart_dogrula`) SENİN makinende gerçek `.kicad_pcb` dosyalarıyla
ÇALIŞTIRILIP doğrulanmadan production'da güvenilmemelidir. Saf mantık
(`vc_id_cakisma_kontrolu`, `guc_butcesi_kontrolu`, `sozlesme_yukle`)
`pcbnew` GEREKTİRMEZ ve bu ortamda GERÇEKTEN test edildi
(`test_coklu_kart_sozlesme_kontrolu.py`, sahte pcbnew ile).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from pcbnew_koprusu import _pcbnew_veya_kapsam_yok

# ---------------------------------------------------------------------
# 1. Sözleşme şeması
# ---------------------------------------------------------------------


@dataclass
class PinTanimi:
    no: int
    net: str
    yon: str
    voltaj: Optional[str] = None


@dataclass
class KonnektorTanimi:
    pin_sayisi: int
    kamera_karti_referans: str
    ana_kart_referans_sablonu: str
    pinler: List[PinTanimi] = field(default_factory=list)
    ana_kart_net_sablonu: str = "{net}"


@dataclass
class GucButcesi:
    kart_basi_maks_akim_a: float
    kart_sayisi: int
    ana_kart_giris_marj_yuzde: float
    ana_kart_guc_girisi_maks_a: Optional[float] = None


@dataclass
class VcIdPlani:
    aralik: Tuple[int, int]
    atama: Dict[str, int] = field(default_factory=dict)


@dataclass
class ArayuzSozlesmesi:
    versiyon: int
    konnektor: KonnektorTanimi
    guc_butcesi: GucButcesi
    vc_id: VcIdPlani


def sozlesme_yukle(yaml_yolu: Path) -> ArayuzSozlesmesi:
    """`arayuz_sozlesmesi.yaml`'ı okuyup `ArayuzSozlesmesi`'e çevirir.

    Şemadaki zorunlu bir alan eksikse `KeyError` fırlatır — SESSİZCE
    varsayılan bir değer UYDURULMAZ, çağıran taraf bunu görmeli.
    """
    veri = yaml.safe_load(Path(yaml_yolu).read_text(encoding="utf-8"))

    konnektor_veri = veri["konnektor"]
    pinler = [PinTanimi(**p) for p in konnektor_veri["pinler"]]
    konnektor = KonnektorTanimi(
        pin_sayisi=konnektor_veri["pin_sayisi"],
        kamera_karti_referans=konnektor_veri["kamera_karti_referans"],
        ana_kart_referans_sablonu=konnektor_veri["ana_kart_referans_sablonu"],
        pinler=pinler,
        ana_kart_net_sablonu=konnektor_veri.get("ana_kart_net_sablonu", "{net}"),
    )

    guc_veri = veri["guc_butcesi"]
    guc_butcesi = GucButcesi(
        kart_basi_maks_akim_a=guc_veri["kart_basi_maks_akim_a"],
        kart_sayisi=guc_veri["kart_sayisi"],
        ana_kart_giris_marj_yuzde=guc_veri["ana_kart_giris_marj_yuzde"],
        ana_kart_guc_girisi_maks_a=guc_veri.get("ana_kart_guc_girisi_maks_a"),
    )

    vc_veri = veri["vc_id"]
    vc_id = VcIdPlani(
        aralik=tuple(vc_veri["aralik"]),
        atama=dict(vc_veri.get("atama", {})),
    )

    return ArayuzSozlesmesi(
        versiyon=veri["versiyon"], konnektor=konnektor, guc_butcesi=guc_butcesi, vc_id=vc_id,
    )


# ---------------------------------------------------------------------
# 2. pcbnew yardımcıları — board üzerinden konnektör/pin/net okuma
# ---------------------------------------------------------------------


def _konnektor_bul(board, referans: str):
    """Board üzerinde `referans` ile TAM eşleşen footprint'i döner,
    yoksa `None` (uydurma bir eşleşme YAPILMAZ)."""
    for fp in board.GetFootprints():
        if fp.GetReference() == referans:
            return fp
    return None


def _konnektor_pin_net_haritasi(fp) -> Dict[int, str]:
    """Footprint'in pad'lerinden {pad_numarasi: net_adi} haritası çıkarır.
    Sayısal olmayan pad numaraları (ör. mekanik/NPTH delikleri) atlanır —
    konnektör pinout kontrolü sadece numaralı sinyal pinleriyle ilgilenir."""
    harita: Dict[int, str] = {}
    for pad in fp.Pads():
        try:
            no = int(pad.GetNumber())
        except (TypeError, ValueError):
            continue
        harita[no] = pad.GetNetname()
    return harita


# ---------------------------------------------------------------------
# 3. Kamera kartı doğrulama — TEK konnektör, pin-bazında
# ---------------------------------------------------------------------


def kamera_karti_dogrula(pcb_yolu: Path, sozlesme: ArayuzSozlesmesi) -> Bulgu:
    kontrol = "coklu_kart_kamera_karti_konnektoru"
    _pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(str(pcb_yolu), kontrol)
    if kapsam_yok is not None:
        return kapsam_yok

    ref = sozlesme.konnektor.kamera_karti_referans
    fp = _konnektor_bul(board, ref)
    if fp is None:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                f"Kamera kartında '{ref}' referanslı konnektör bulunamadı — "
                "sözleşme kontrol EDİLEMEDİ (KAPSAM_YOK, PASS DEĞİL)."
            ),
        )

    pin_net_haritasi = _konnektor_pin_net_haritasi(fp)
    taranan = 0
    ihlaller: List[Dict[str, Any]] = []
    for pin in sozlesme.konnektor.pinler:
        taranan += 1
        bulunan_net = pin_net_haritasi.get(pin.no)
        if bulunan_net is None:
            ihlaller.append({
                "pin": pin.no, "beklenen_net": pin.net, "yon": pin.yon,
                "voltaj": pin.voltaj, "sorun": "pin_bulunamadi",
            })
        elif bulunan_net != pin.net:
            ihlaller.append({
                "pin": pin.no, "beklenen_net": pin.net, "bulunan_net": bulunan_net,
                "yon": pin.yon, "voltaj": pin.voltaj, "sorun": "net_uyumsuz",
            })

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"'{ref}' konnektörü, sözleşmenin {len(sozlesme.konnektor.pinler)} pinine karşı doğrulandı.",
    )


# ---------------------------------------------------------------------
# 4. Ana kart doğrulama — 6 konnektör, HER BİRİ AYRI AYRI pin-bazında
# ---------------------------------------------------------------------


def _tek_konnektor_dogrula(
    board, sozlesme: ArayuzSozlesmesi, kart_no: int,
) -> Tuple[int, List[Dict[str, Any]], bool]:
    """Ana karttaki TEK bir konnektörü (kart_no) doğrular.

    Döner: (taranan, ihlaller, konnektor_bulundu_mu). Konnektör board'da
    hiç bulunamazsa (False) çağıran bunu kendi KAPSAM_YOK/ihlal mantığına
    dahil eder — burada sessizce 0 ihlal/PASS gibi davranılmaz."""
    ref = sozlesme.konnektor.ana_kart_referans_sablonu.format(kart=kart_no)
    fp = _konnektor_bul(board, ref)
    if fp is None:
        return 0, [], False

    pin_net_haritasi = _konnektor_pin_net_haritasi(fp)
    taranan = 0
    ihlaller: List[Dict[str, Any]] = []
    for pin in sozlesme.konnektor.pinler:
        taranan += 1
        beklenen_net = sozlesme.konnektor.ana_kart_net_sablonu.format(net=pin.net, kart=kart_no)
        bulunan_net = pin_net_haritasi.get(pin.no)
        konum = f"konnektor_{kart_no}.pin_{pin.no}"
        if bulunan_net is None:
            ihlaller.append({
                "konum": konum, "konnektor_referansi": ref, "pin": pin.no,
                "beklenen_net": beklenen_net, "yon": pin.yon, "voltaj": pin.voltaj,
                "sorun": "pin_bulunamadi",
            })
        elif bulunan_net != beklenen_net:
            ihlaller.append({
                "konum": konum, "konnektor_referansi": ref, "pin": pin.no,
                "beklenen_net": beklenen_net, "bulunan_net": bulunan_net,
                "yon": pin.yon, "voltaj": pin.voltaj, "sorun": "net_uyumsuz",
            })
    return taranan, ihlaller, True


def ana_kart_dogrula(
    pcb_yolu: Path, sozlesme: ArayuzSozlesmesi, konnektor_sayisi: int = 6,
) -> Bulgu:
    """Her bir konnektör (1..konnektor_sayisi) için AYRI AYRI pin-bazlı
    karşılaştırma yapar; ihlalleri 'konnektor_3.pin_5' gibi konum
    bilgisiyle raporlar. Bir konnektördeki hata diğerlerini ETKİLEMEZ."""
    kontrol = "coklu_kart_ana_kart_konnektorleri"
    _pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(str(pcb_yolu), kontrol)
    if kapsam_yok is not None:
        return kapsam_yok

    taranan = 0
    ihlaller: List[Dict[str, Any]] = []
    bulunamayan_konnektorler: List[str] = []
    for kart_no in range(1, konnektor_sayisi + 1):
        alt_taranan, alt_ihlaller, bulundu = _tek_konnektor_dogrula(board, sozlesme, kart_no)
        if not bulundu:
            bulunamayan_konnektorler.append(
                sozlesme.konnektor.ana_kart_referans_sablonu.format(kart=kart_no)
            )
            continue
        taranan += alt_taranan
        ihlaller.extend(alt_ihlaller)

    if bulunamayan_konnektorler:
        ihlaller.append({
            "sorun": "konnektor_bulunamadi",
            "konnektor_referanslari": bulunamayan_konnektorler,
        })

    if taranan == 0:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                f"Ana kartta beklenen {konnektor_sayisi} konnektörden HİÇBİRİ "
                f"bulunamadı ({', '.join(bulunamayan_konnektorler)}) — sözleşme "
                "kontrol EDİLEMEDİ (KAPSAM_YOK, PASS DEĞİL)."
            ),
        )

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"{konnektor_sayisi} konnektör denendi, "
        f"{konnektor_sayisi - len(bulunamayan_konnektorler)} bulundu ve pin-bazında doğrulandı.",
    )


# ---------------------------------------------------------------------
# 5. VC ID çakışma kontrolü — saf küme matematiği, pcbnew GEREKTİRMEZ
# ---------------------------------------------------------------------


def vc_id_cakisma_kontrolu(sozlesme: ArayuzSozlesmesi) -> Bulgu:
    """`vc_id.atama` altındaki HER değerin `vc_id.aralik` içinde VE
    birbirinden farklı olduğunu doğrular. Çakışma varsa hangi iki (veya
    daha fazla) kartın çakıştığı `ihlaller` içinde açıkça raporlanır."""
    kontrol = "coklu_kart_vc_id_cakismasi"
    atama = sozlesme.vc_id.atama
    if not atama:
        return bulgu_uret(kontrol, taranan=0, detay="vc_id.atama boş — kontrol edilecek atama yok.")

    alt, ust = sozlesme.vc_id.aralik
    taranan = len(atama)
    ihlaller: List[Dict[str, Any]] = []

    for kart_id, vc_id in atama.items():
        if not (alt <= vc_id <= ust):
            ihlaller.append({
                "sorun": "aralik_disi", "kart": kart_id, "vc_id": vc_id, "aralik": [alt, ust],
            })

    vc_id_gruplari: Dict[int, List[str]] = {}
    for kart_id, vc_id in atama.items():
        vc_id_gruplari.setdefault(vc_id, []).append(kart_id)
    for vc_id, kartlar in vc_id_gruplari.items():
        if len(kartlar) > 1:
            ihlaller.append({"sorun": "cakisma", "vc_id": vc_id, "kartlar": sorted(kartlar)})

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"VC ID aralığı [{alt}, {ust}], {taranan} kart ataması kontrol edildi.",
    )


# ---------------------------------------------------------------------
# 6. Güç bütçesi kontrolü — saf aritmetik, pcbnew GEREKTİRMEZ
# ---------------------------------------------------------------------


def guc_butcesi_kontrolu(
    sozlesme: ArayuzSozlesmesi, ana_kart_guc_girisi_maks_a: Optional[float] = None,
) -> Bulgu:
    """`kart_basi_maks_akim_a * kart_sayisi * (1 + marj/100)` hesaplayıp
    ana karttaki gerçek giriş konnektörünün/sigortasının bunu karşıladığını
    doğrular. `ana_kart_guc_girisi_maks_a` verilmezse sözleşmedeki
    `guc_butcesi.ana_kart_guc_girisi_maks_a` kullanılır; o da tanımlı
    değilse KAPSAM_YOK (uydurma bir sınır değeri KULLANILMAZ)."""
    kontrol = "coklu_kart_guc_butcesi"
    gb = sozlesme.guc_butcesi
    sinir_a = (
        ana_kart_guc_girisi_maks_a
        if ana_kart_guc_girisi_maks_a is not None
        else gb.ana_kart_guc_girisi_maks_a
    )

    if sinir_a is None:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                "ana_kart_guc_girisi_maks_a tanımlı değil (ne sözleşmede ne "
                "çağrıda) — güç bütçesi kontrol EDİLEMEDİ (KAPSAM_YOK)."
            ),
        )

    gerekli_a = gb.kart_basi_maks_akim_a * gb.kart_sayisi * (1 + gb.ana_kart_giris_marj_yuzde / 100.0)
    taranan = 1
    ihlaller: List[Dict[str, Any]] = []
    if gerekli_a > sinir_a:
        ihlaller.append({
            "sorun": "guc_butcesi_asimi",
            "gerekli_a": round(gerekli_a, 3),
            "ana_kart_giris_siniri_a": sinir_a,
            "kart_basi_maks_akim_a": gb.kart_basi_maks_akim_a,
            "kart_sayisi": gb.kart_sayisi,
            "marj_yuzde": gb.ana_kart_giris_marj_yuzde,
        })

    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"Gerekli={gerekli_a:.3f}A (kart_basi={gb.kart_basi_maks_akim_a}A x {gb.kart_sayisi} kart "
        f"x (1+{gb.ana_kart_giris_marj_yuzde}%)), ana kart giriş sınırı={sinir_a}A.",
    )


# ---------------------------------------------------------------------
# 7. Governance köprüsü — karar_birimleri.py entegrasyonu
# ---------------------------------------------------------------------

COKLU_KART_KARAR_ID = "coklu-kart-arayuz-tutarli"


def coklu_kart_karari_olustur(pass_mi: bool, ozet_detay: str = ""):
    """`karar_birimleri.KararBirimi` üretir — PASS ise doğrudan
    `KABUL_EDILDI`, değilse `ACIK` (bu, `main.py::cmd_promote`'un mevcut
    `kabul_edilmemis_kararlari_bul()` kapısından GEÇİLEMEMESİNİ sağlar,
    `cmd_promote`'a HİÇBİR yeni kod eklenmeden — `karar_birimleri.py`'nin
    `kritik_pin_teyit_karari_olustur()` ile AYNI desen)."""
    from karar_birimleri import KararBirimi, KararDurumu

    return KararBirimi(
        karar_id=COKLU_KART_KARAR_ID,
        soru=(
            "Kamera kartı <-> ana kart arayüz sözleşmesi (konnektör pinout, "
            "VC ID ataması, güç bütçesi) tüm kontrollerden PASS aldı mı?"
        ),
        sahip_skill="coklu_kart_sozlesme_kontrolu.py",
        gereken_kanit="'python main.py coklu-kart-dogrula' komutunun PASS çıktısı.",
        durum=KararDurumu.KABUL_EDILDI if pass_mi else KararDurumu.ACIK,
        gecersizlik_tetikleyicileri=[
            "kamera kartı veya ana kart konnektör pinoutu değişirse",
            "VC ID ataması veya güç bütçesi parametreleri değişirse",
        ],
        gecersiz_kilinma_sebebi=None if pass_mi else (ozet_detay or "coklu-kart-dogrula FAIL/KAPSAM_YOK döndü"),
    )


def coklu_kart_karari_kaydet(project_dir: str, pass_mi: bool, ozet_detay: str = "") -> None:
    """`coklu_kart_karari_olustur()`'ün ürettiği kararı `project_dir/DOCS/
    karar_birimleri.json`'a yazar — `main.py promote` bu projeyi
    yükseltmeden önce artık bu kararın `KABUL_EDILDI` olmasını ister."""
    from karar_birimleri import karar_ekle_veya_guncelle

    karar_ekle_veya_guncelle(project_dir, coklu_kart_karari_olustur(pass_mi, ozet_detay))


# ---------------------------------------------------------------------
# 8. Toplu çalıştırıcı
# ---------------------------------------------------------------------


def tum_coklu_kart_kontrollerini_calistir(
    sozlesme_yolu: Path,
    kamera_karti_pcb: Path,
    ana_kart_pcb: Path,
    konnektor_sayisi: int = 6,
    ana_kart_guc_girisi_maks_a: Optional[float] = None,
) -> List[Bulgu]:
    """`main.py coklu-kart-dogrula` alt-komutunun çağırdığı tek giriş
    noktası — `bulgu_sozlesmesi.ozet_rapor()` ile JSON'a çevrilebilir."""
    sozlesme = sozlesme_yukle(sozlesme_yolu)
    return [
        kamera_karti_dogrula(kamera_karti_pcb, sozlesme),
        ana_kart_dogrula(ana_kart_pcb, sozlesme, konnektor_sayisi),
        vc_id_cakisma_kontrolu(sozlesme),
        guc_butcesi_kontrolu(sozlesme, ana_kart_guc_girisi_maks_a),
    ]


if __name__ == "__main__":
    import argparse
    import json

    from bulgu_sozlesmesi import ozet_rapor

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sozlesme", required=True)
    ap.add_argument("--kamera-karti", required=True, dest="kamera_karti")
    ap.add_argument("--ana-kart", required=True, dest="ana_kart")
    ap.add_argument("--konnektor-sayisi", type=int, default=6, dest="konnektor_sayisi")
    ap.add_argument("--ana-kart-guc-girisi-maks-a", type=float, default=None, dest="ana_kart_guc_girisi_maks_a")
    ap.add_argument("--json")
    a = ap.parse_args()

    bulgular = tum_coklu_kart_kontrollerini_calistir(
        Path(a.sozlesme), Path(a.kamera_karti), Path(a.ana_kart),
        a.konnektor_sayisi, a.ana_kart_guc_girisi_maks_a,
    )
    rapor = ozet_rapor(bulgular)
    metin = json.dumps(rapor, indent=2, ensure_ascii=False)
    if a.json:
        Path(a.json).write_text(metin + "\n", encoding="utf-8")
    print(metin)
