#!/usr/bin/env python3
"""
mcad_carpisma_koprusu.py
==========================
MCAD (mekanik kasa) ile ECAD (PCB) arasında Z-EKSENİNDE gerçek 3D çarpışma
(collision) testi — `mekanik_dxf_koprusu.py::z_kontrolu_yap()`'ın TEK bir
"bölge-bazlı maksimum yükseklik" modelinin ötesine geçer: burada her
komponentin GERÇEK 3D kutusu (genişlik × derinlik × yükseklik, konum +
rotasyon dahil) kasanın GERÇEK engel hacimleriyle (vida bossu, konnektör
kesimi, kapak iç yüzeyi...) tek tek çakıştırılır ve "J1 konnektörü kutunun
kapağına çarpıyor" gibi İSİMLENDİRİLMİŞ bir çarpışma raporu üretir.

NEDEN AYRI BİR MODÜL (mekanik_dxf_koprusu.py'nin YERİNE değil, ÜSTÜNE):
--------------------------------------------------------------------------
`z_kontrolu_yap()` "bu bölgede en fazla X mm yükseklik olabilir" der —
TEK bir düzlem eşiği. Ama gerçek bir kasada engeller nokta nokta farklı
yerlerde, farklı boyutlarda hacimlerdir (bir vida bossu 3mm çapında ve
5mm yüksekliktedir, kapağın geneli 8mm boşluk bırakır) — bunları tek bir
"max_allowed_height_mm" sayısına indirgemek bilgi kaybıdır. Bu modül o
kaybı gidermek için AYRI, hacim-hacim (component AABB × engel AABB) bir
test sunar; `z_kontrolu_yap()`'ın YERİNE geçmez, onu TAMAMLAR — ikisi de
`pcb-layout` Aşama 3.1'in placement bariyerinin girdisidir.

DOĞRULAMA DURUMU (bu makinede GERÇEKTEN denendi):
----------------------------------------------------
  - **`kicad-cli pcb export step`: GERÇEKTEN koşturuldu.** Gerçek
    `ESP32C3_SmartBand.kicad_pcb` üzerinde `--force --output board.step
    --subst-models` bayraklarıyla çalıştı, 2.58MB geçerli bir
    `ISO-10303-21` (STEP AP214) dosyası üretti (~25 saniyede). Bu modüldeki
    `step_disa_aktar()` o GERÇEK komut satırını sarmalar.
  - **`.kicad_pcb`'den komponent yerleşimi çıkarma: GERÇEK VERİYLE test
    edildi.** `kicad_pcb_yerlesimlerini_cikar()`, gerçek
    `ESP32C3_SmartBand.kicad_pcb` dosyasından alınmış BİREBİR
    `(footprint ...)` bloklarıyla (`test_mcad_carpisma_koprusu.py` içindeki
    `GERCEK_KICAD10_FOOTPRINT_PARCASI`) test edildi — refdes, konum,
    rotasyon ve katman doğru ayrıştırılıyor.
  - **GERÇEKTEN YAPILMAYAN (dürüstlük notu):** üretilen `.step` dosyasının
    İÇİNİN (B-rep katıları, gerçek komponent gövde geometrisi) ayrıştırılması.
    Bu ortamda `cadquery`/`python-occ` KURULU DEĞİL ve STEP AP214 formatı
    elle regex ile güvenilir ayrıştırılamayacak kadar karmaşıktır (B-spline
    yüzeyler, referans döngüleri). Bu yüzden çarpışma testi, komponent
    GÖVDESİNİ (genişlik/derinlik/yükseklik) `KomponentGovdesi3D` olarak
    DIŞARIDAN alır (datasheet/3D model'den elle veya ayrı bir araçla
    okunmuş) — `ecad_mcad_termal_kopru.py`'nin `TermalTemasBolgesi`yi STEP'ten
    "önceden ayrıştırılmış" almasıyla AYNI, kanıtlanmış desen. Gerçek
    B-rep'ten otomatik gövde çıkarımı SENİN makinende `cadquery` kurulunca
    eklenmelidir; sessizce "yaptım" denmez.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

Kutu3D = Tuple[float, float, float, float, float, float]  # x_min,y_min,z_min,x_max,y_max,z_max


# ------------------------------------------------------------------
# 1. kicad-cli STEP İHRACI (gerçekten koşturuldu — dosya başlığına bak)
# ------------------------------------------------------------------

def step_disa_aktar(
    board_path: str,
    cikti_path: str = "board.step",
    kicad_cli: str = "kicad-cli",
    subst_models: bool = True,
    zaman_asimi_s: int = 180,
) -> str:
    """`kicad-cli pcb export step` sarmalayıcısı.

    `subst_models=True` (varsayılan): eksik/bulunamayan 3D model varsa
    (bu makinede gerçekten yaşandı: `SW1` için `.step` bulunamadı) KiCad
    onu bir VRML/basit modelle DEĞİŞTİRİR ve dışa aktarmaya DEVAM eder —
    tek bir eksik model yüzünden tüm STEP ihracının durmasını önler; eksik
    modeller `sonuc.stderr`'de listelenir, ÇAĞIRAN TARAF bunları
    KULLANICIYA raporlamalıdır (sessizce yutulmaz).

    `zaman_asimi_s` varsayılanı 180: gerçek koşumda ~25 saniye sürdü, üç
    kata kadar güvenlik payı bırakıldı (daha büyük/karmaşık kartlarda süre
    artabilir).
    """
    komut = [
        kicad_cli, "pcb", "export", "step",
        "--force", "--output", cikti_path,
    ]
    if subst_models:
        komut.append("--subst-models")
    komut.append(board_path)

    sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi_s)
    if sonuc.returncode != 0:
        raise RuntimeError(f"kicad-cli STEP ihracı başarısız: {sonuc.stderr}")
    if not Path(cikti_path).exists():
        raise RuntimeError(f"{cikti_path} oluşmadı — kicad-cli çıktısı: {sonuc.stdout}")
    return cikti_path


def eksik_3d_modelleri_ayikla(kicad_cli_stderr: str) -> List[str]:
    """`step_disa_aktar()`'ın stderr'inden "File not found: ..." /
    "Could not add 3D model for X" satırlarını çıkarır — gerçek koşumda
    bilfiil gözlemlenen çıktı biçimi:

        Could not add 3D model for SW1.
        File not found: ${KICAD10_3DMODEL_DIR}/.../SW_SPDT_....step

    Bu liste boş DÖNMEYEBİLİR bile STEP dosyası başarıyla üretilmiş olsun —
    eksik model, o komponent GÖRÜNMEDEN dışa aktarılmış demektir ve bu,
    çarpışma testinin o komponent için KÖRDÜR anlamına gelir; çağıran taraf
    bunu `carpisma_raporu_uret()`'e uyarı olarak geçirmelidir.
    """
    return [
        m.group(1) for m in re.finditer(r"Could not add 3D model for (\S+?)\.?\s*$", kicad_cli_stderr, re.MULTILINE)
    ]


# ------------------------------------------------------------------
# 2. .kicad_pcb'DEN GERÇEK YERLEŞİM ÇIKARIMI (regex — pcbnew GEREKMEZ)
# ------------------------------------------------------------------

@dataclass
class KomponentYerlesimi:
    refdes: str
    footprint_kutuphanesi: str
    x_mm: float
    y_mm: float
    aci_derece: float
    katman: str  # "F.Cu" | "B.Cu"


_FOOTPRINT_BLOK_BASI = re.compile(r'\(footprint\s+"([^"]+)"')
_AT_SATIRI = re.compile(r'^\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)\s*$', re.MULTILINE)
_LAYER_SATIRI = re.compile(r'^\s*\(layer\s+"([^"]+)"\)\s*$', re.MULTILINE)
_REFERENCE_SATIRI = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')


def _footprint_bloklarina_ayir(pcb_metni: str) -> List[str]:
    """`.kicad_pcb` metnini her biri TEK bir `(footprint ...)` ile
    başlayan parça listesine böler (basit parantez dengesi sayacıyla —
    tam bir S-expression parser DEĞİL, bilinçli bir sadelik: proje diğer
    köprülerde de (`ecad_mcad_termal_kopru.py`) tam parser yerine hedefe
    yönelik regex kullanıyor).
    """
    parcalar: List[str] = []
    basla = 0
    while True:
        m = _FOOTPRINT_BLOK_BASI.search(pcb_metni, basla)
        if not m:
            break
        derinlik = 0
        i = m.start()
        blok_basi = pcb_metni.rfind("(", 0, m.start())
        blok_basi = blok_basi if blok_basi != -1 and pcb_metni[blok_basi:m.start()].strip() == "" else m.start()
        j = blok_basi
        while j < len(pcb_metni):
            if pcb_metni[j] == "(":
                derinlik += 1
            elif pcb_metni[j] == ")":
                derinlik -= 1
                if derinlik == 0:
                    j += 1
                    break
            j += 1
        parcalar.append(pcb_metni[blok_basi:j])
        basla = j
    return parcalar


def kicad_pcb_yerlesimlerini_cikar(pcb_metni: str) -> List[KomponentYerlesimi]:
    """`.kicad_pcb` metninden her footprint'in refdes/konum/rotasyon/katmanını
    çıkarır — `pcbnew` GEREKMEZ, saf metin işleme (`kicad_koprusu.py`'nin
    `.kicad_pcb`'ye doğrudan S-expr yazma desenindeki gibi metin
    seviyesinde çalışır).

    Referans (`Reference` property'si) BULUNAMAYAN bir footprint (bozuk/
    yarım blok) SESSİZCE ATLANIR — kısmi/yanlış bir yerleşim kaydı
    üretmek, hiç kayıt üretmemekten DAHA tehlikelidir.
    """
    sonuc: List[KomponentYerlesimi] = []
    for blok in _footprint_bloklarina_ayir(pcb_metni):
        kutuphane_m = _FOOTPRINT_BLOK_BASI.search(blok)
        ref_m = _REFERENCE_SATIRI.search(blok)
        katman_m = _LAYER_SATIRI.search(blok)
        at_m = _AT_SATIRI.search(blok)
        if not (kutuphane_m and ref_m and at_m):
            continue
        x, y = float(at_m.group(1)), float(at_m.group(2))
        aci = float(at_m.group(3)) if at_m.group(3) else 0.0
        katman = katman_m.group(1) if katman_m else "F.Cu"
        sonuc.append(KomponentYerlesimi(
            refdes=ref_m.group(1),
            footprint_kutuphanesi=kutuphane_m.group(1),
            x_mm=x, y_mm=y, aci_derece=aci, katman=katman,
        ))
    return sonuc


# ------------------------------------------------------------------
# 3. KOMPONENT GÖVDESİ + KASA ENGEL HACMİ (dışarıdan sağlanır — bkz. dürüstlük notu)
# ------------------------------------------------------------------

@dataclass
class KomponentGovdesi3D:
    """Bir komponentin 3D gövde kutusu — YERLEŞİM koordinatından BAĞIMSIZ,
    footprint origin'ine göre (rotasyon UYGULANMADAN önceki) boyutlar.

    `genislik_mm`/`derinlik_mm`: rotasyon 0°'deyken X/Y eksenindeki
    boyutlar. `yukseklik_mm`: PCB yüzeyinden itibaren dikey yükseklik
    (bkz. `carpisma_tara`'nın Z hesaplaması).
    """

    genislik_mm: float
    derinlik_mm: float
    yukseklik_mm: float


@dataclass
class KasaEngelHacmi:
    """Kasadan (mekanik STEP/DXF'ten türetilmiş) bir engel hacmi — vida
    bossu, konnektör kesimi, kapak iç yüzeyi vb.

    `mekanik_dxf_koprusu.TavanHaritasiBolgesi` ile aynı KAYNAK VERİYE
    (STEP) dayanır ama BURADA tam bir 3D hacim olarak temsil edilir
    (o modülde sadece `max_allowed_height_mm` — tek düzlem eşiği vardı).
    """

    isim: str
    x_min_mm: float
    y_min_mm: float
    x_max_mm: float
    y_max_mm: float
    z_min_mm: float  # PCB üst yüzeyi = 0 referans alınır
    z_max_mm: float


@dataclass
class Carpisma:
    komponent_ref: str
    engel_isim: str
    ortusme_mm: Tuple[float, float, float]  # (x, y, z) örtüşme miktarları


# ------------------------------------------------------------------
# 4. GEOMETRİ: rotasyonlu AABB + 3D AABB çakışması
# ------------------------------------------------------------------

def rotasyonlu_aabb(
    merkez_x: float, merkez_y: float, genislik: float, derinlik: float, aci_derece: float,
) -> Tuple[float, float, float, float]:
    """Rotasyonlu bir dikdörtgenin EKSEN-HİZALI (axis-aligned) bounding
    box'ı — döndürülmüş dikdörtgenin 4 köşesini hesaplayıp min/max alır.

    Bu, gerçek şekli rotasyon açısına bağlı olarak GENİŞLETİR (45°'de bir
    kare, kenarının √2 katı genişliğinde bir AABB'ye sığar) — DAİMA
    muhafazakâr yönde (dosya başlığındaki "asla daha dar bir alan
    varsayma" disipliniyle tutarlı, `gerber_dfm_gorsel_koprusu.py`'deki
    bounding-box yaklaşımıyla AYNI gerekçe).
    """
    yari_g, yari_d = genislik / 2.0, derinlik / 2.0
    rad = math.radians(aci_derece)
    kose_ler = [(-yari_g, -yari_d), (yari_g, -yari_d), (yari_g, yari_d), (-yari_g, yari_d)]
    xler, yler = [], []
    for kx, ky in kose_ler:
        rx = kx * math.cos(rad) - ky * math.sin(rad)
        ry = kx * math.sin(rad) + ky * math.cos(rad)
        xler.append(merkez_x + rx)
        yler.append(merkez_y + ry)
    return (min(xler), min(yler), max(xler), max(yler))


def komponent_3d_kutusu(
    yerlesim: KomponentYerlesimi, govde: KomponentGovdesi3D, pcb_kalinligi_mm: float = 1.6,
) -> Kutu3D:
    """Bir komponentin GERÇEK 3D kutusunu (yerleşim + rotasyon + katman)
    üretir.

    Z ekseni: PCB'nin ÜST yüzeyi (F.Cu tarafı, `pcb_kalinligi_mm` kalınlık
    varsayılan referans) z=0 alınır. `F.Cu`'daki bir komponent
    `[0, yukseklik]` aralığını, `B.Cu`'daki bir komponent (alttan monte)
    `[-pcb_kalinligi_mm - yukseklik, -pcb_kalinligi_mm]` aralığını kaplar
    — iki tarafın birbirine karışmaması için PCB kalınlığı payı bilinçli
    olarak dahil edilir.
    """
    x_min, y_min, x_max, y_max = rotasyonlu_aabb(
        yerlesim.x_mm, yerlesim.y_mm, govde.genislik_mm, govde.derinlik_mm, yerlesim.aci_derece,
    )
    if yerlesim.katman == "F.Cu":
        z_min, z_max = 0.0, govde.yukseklik_mm
    else:
        z_min, z_max = -pcb_kalinligi_mm - govde.yukseklik_mm, -pcb_kalinligi_mm
    return (x_min, y_min, z_min, x_max, y_max, z_max)


def kutu_3d_carpisiyor_mu(a: Kutu3D, b: Tuple[float, float, float, float, float, float]) -> Optional[Tuple[float, float, float]]:
    """İki 3D AABB çakışıyorsa (X, Y, Z örtüşme miktarları) döner, aksi
    halde `None`. Üç eksende de örtüşme > 0 olmalı — SADECE XY'de çakışıp
    Z'de ayrık olan komponentler (ör. kartın altındaki bir parça ile
    kapaktaki bir çıkıntı) çarpışma SAYILMAZ."""
    ox = min(a[3], b[3]) - max(a[0], b[0])
    oy = min(a[4], b[4]) - max(a[1], b[1])
    oz = min(a[5], b[5]) - max(a[2], b[2])
    if ox > 0 and oy > 0 and oz > 0:
        return (round(ox, 4), round(oy, 4), round(oz, 4))
    return None


# ------------------------------------------------------------------
# 5. TARAMA + KABUL KAPISI
# ------------------------------------------------------------------

def carpisma_tara(
    yerlesimler: Sequence[KomponentYerlesimi],
    govdeler: Dict[str, KomponentGovdesi3D],
    kasa_hacimleri: Sequence[KasaEngelHacmi],
    pcb_kalinligi_mm: float = 1.6,
) -> Bulgu:
    """Her komponentin GERÇEK 3D kutusunu her kasa engel hacmiyle test eder.

    `govdeler` sözlüğünde OLMAYAN bir refdes (gövde verisi sağlanmamış)
    SESSİZCE ATLANIR ama `taranan` sayısına DAHİL EDİLMEZ — dosya
    başlığındaki dürüstlük notunun kod karşılığı: gövde verisi yoksa o
    komponent için "çarpışma yok" denmez, sadece TEST EDİLMEMİŞ sayılır.
    Sonuçta hiçbir komponent test edilemezse (ör. hiç gövde verisi
    sağlanmadıysa) `KAPSAM_YOK` döner.
    """
    ihlaller: List[Dict[str, object]] = []
    taranan = 0
    for yerlesim in yerlesimler:
        govde = govdeler.get(yerlesim.refdes)
        if govde is None:
            continue
        taranan += 1
        kutu = komponent_3d_kutusu(yerlesim, govde, pcb_kalinligi_mm)
        for hacim in kasa_hacimleri:
            hacim_kutusu = (hacim.x_min_mm, hacim.y_min_mm, hacim.z_min_mm,
                            hacim.x_max_mm, hacim.y_max_mm, hacim.z_max_mm)
            ortusme = kutu_3d_carpisiyor_mu(kutu, hacim_kutusu)
            if ortusme is not None:
                ihlaller.append({
                    "komponent": yerlesim.refdes,
                    "engel": hacim.isim,
                    "ortusme_x_mm": ortusme[0],
                    "ortusme_y_mm": ortusme[1],
                    "ortusme_z_mm": ortusme[2],
                    "mesaj": f"{yerlesim.refdes} konnektörü/komponenti '{hacim.isim}' ile çarpışıyor "
                             f"(X={ortusme[0]}mm, Y={ortusme[1]}mm, Z={ortusme[2]}mm örtüşme).",
                })

    return bulgu_uret(
        "mcad_3d_carpisma",
        taranan=taranan,
        ihlaller=ihlaller,
        detay=f"{len(yerlesimler)} yerleşimden {taranan} tanesi için gövde verisi vardı, "
              f"{len(kasa_hacimleri)} kasa engel hacmine karşı test edildi",
    )


# ------------------------------------------------------------------
# 6. RAPOR
# ------------------------------------------------------------------

def carpisma_raporu_uret(bulgu: Bulgu, eksik_3d_modeller: Sequence[str] = ()) -> str:
    """`TEST/mcad_carpisma_raporu.md` içeriği."""
    satirlar = [
        "# MCAD-ECAD 3D Çarpışma Testi",
        "",
        f"- **Durum:** {bulgu.durum.value}",
        f"- **Taranan komponent:** {bulgu.taranan}",
        f"- **Çarpışma sayısı:** {len(bulgu.ihlaller)}",
        f"- **Detay:** {bulgu.detay}",
        "",
        "## Çarpışmalar",
        "",
    ]
    if bulgu.ihlaller:
        for ihlal in bulgu.ihlaller:
            satirlar.append(f"- ⚠️ {ihlal['mesaj']}")
    else:
        satirlar.append("- (çarpışma yok)")

    if eksik_3d_modeller:
        satirlar += [
            "",
            "## Eksik 3D Modeller (STEP ihracında sessizce değiştirildi)",
            "",
            "> Bu komponentler için gerçek 3D model bulunamadı — kicad-cli",
            "> onları yer tutucu bir modelle değiştirip devam etti. Çarpışma",
            "> testi bu komponentler için GERÇEK gövde yerine sağlanan",
            "> `KomponentGovdesi3D` verisine güveniyor; o veri de tahminiyse",
            "> sonuç KESİN DEĞİLDİR.",
            "",
        ] + [f"- {m}" for m in eksik_3d_modeller]

    return "\n".join(satirlar) + "\n"


def carpisma_raporu_yaz(hedef_yol: str, bulgu: Bulgu, eksik_3d_modeller: Sequence[str] = ()) -> str:
    yol = Path(hedef_yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(carpisma_raporu_uret(bulgu, eksik_3d_modeller), encoding="utf-8")
    return str(yol)


# ------------------------------------------------------------------
# 7. ÖZ-TEST (fault-injection dahil)
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: engeli komponentin TAM üstüne (3 eksende de
    örtüşecek şekilde) koyarsak çarpışma KESİNLİKLE tespit edilmeli."""
    yerlesim = KomponentYerlesimi("J1", "Conn:Header", 0.0, 0.0, 0.0, "F.Cu")
    govde = {"J1": KomponentGovdesi3D(5.0, 5.0, 8.0)}
    kapak = [KasaEngelHacmi("kapak_ic_yuzeyi", -10, -10, 10, 10, 5.0, 20.0)]
    bulgu = carpisma_tara([yerlesim], govde, kapak)
    return bulgu.durum.value == "FAIL"


def oz_testleri_calistir() -> List[str]:
    hatalar: List[str] = []

    # 1. Rotasyonsuz AABB doğru
    kutu = rotasyonlu_aabb(0, 0, 4, 2, 0.0)
    if kutu != (-2.0, -1.0, 2.0, 1.0):
        hatalar.append(f"0° rotasyonda AABB yanlış: {kutu}")

    # 2. 90° rotasyonda genişlik/derinlik yer değiştirir
    kutu90 = rotasyonlu_aabb(0, 0, 4, 2, 90.0)
    if not (abs(kutu90[0] - (-1.0)) < 1e-6 and abs(kutu90[2] - 1.0) < 1e-6):
        hatalar.append(f"90° rotasyonda AABB yanlış: {kutu90}")

    # 3. Z ekseninde ayrık olan (XY'de çakışan) kutular çarpışma SAYILMAMALI
    a = (0.0, 0.0, 0.0, 5.0, 5.0, 2.0)
    b = (1.0, 1.0, 10.0, 4.0, 4.0, 15.0)
    if kutu_3d_carpisiyor_mu(a, b) is not None:
        hatalar.append("Z'de ayrık kutular yanlışlıkla çarpışma sayıldı")

    # 4. Gövde verisi olmayan komponent taranan sayısına girmemeli
    bulgu = carpisma_tara(
        [KomponentYerlesimi("U1", "x", 0, 0, 0, "F.Cu")], {}, [],
    )
    if bulgu.taranan != 0 or bulgu.durum.value != "KAPSAM_YOK":
        hatalar.append("gövde verisi olmayan komponent yanlış raporlandı")

    # 5. Fault injection
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: çarpışma testi boş olabilir")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: mcad_carpisma_koprusu.py öz testleri temiz.")
