#!/usr/bin/env python3
"""
device_tree_uretici.py
========================
`arayuz_sozlesmesi.yaml` (konnektör pin tablosu, `vc_id.atama`) +
`sistem_orkestratoru.py`'nin ürettiği `i2c_adres_cevirisi` bölümünden
RK3588 (mainline Linux) için bir Device Tree Overlay (`.dts`) FRAGMENT'i
üretir. Kod tabanında bu iş için hiçbir altyapı YOKTU (kod incelemesinde
`device.?tree|\\.dts|dtsi` deseni tüm projede 0 sonuç verdi) — bu modül o
boşluğu, MEVCUT iki veri kaynağını (arayuz_sozlesmesi.yaml,
sistem_orkestratoru.py) TEK KAYNAK olarak kullanarak kapatır; I2C
adresini/VC ID'yi burada YENİDEN HESAPLAMAZ, sadece OKUR.

SoC HEDEFİ SINIRI (bilerek, KAPSAM_YOK/Taslak disipliniyle):
--------------------------------------------------------------
- **RK3588**: mainline Linux çekirdeğinin device tree binding'leri AÇIK
  kaynak ve kamuya açıktır (`Documentation/devicetree/bindings/`) — bu
  modül bu SoC için GERÇEK, syntax olarak makul bir `.dts` fragment'i
  üretmeye ÇALIŞIR.
- **Ambarella (CV5S/CV72S)**: KAPALI/NDA'lı bir SDK kullanır. Bu SoC
  ailesi için GERÇEK bir device tree syntax'ı bu modülde BİLİNMİYOR —
  `ambarella_kamera_overlay_uret()` hiçbir `.dts` İÇERİĞİ ÜRETMEZ,
  `dts_fragment_uret()` bu SoC için HER ZAMAN `KAPSAM_YOK` (taranan=0)
  döner. Ambarella'nın resmi BSP dokümantasyonu olmadan burada syntax
  UYDURULMASI, "sayı uydurma yasağı" (bkz. `bulgu_sozlesmesi.py`) ile
  doğrudan çelişir.

DOĞRULAMA DURUMU: Bu modülün RK3588 `.dts` ÇIKTISI hiçbir gerçek `dtc`
(device tree compiler) ile derlenip TEST EDİLMEDİ — bu ortamda `dtc`
kurulu değil. Üretilen fragment SENİN bir RK3588 kernel ağacında
`dtc -@ -I dts -O dtb` ile derlenip GERÇEK donanımda (veya en azından
QEMU) doğrulanmadan production için KULLANILMAMALI. Saf veri okuma/
metin üretme mantığı (`sozlesmeden_ve_plandan_dts_girdileri_uret`,
`rk3588_kamera_overlay_uret`, `dts_fragment_uret`) bu ortamda GERÇEKTEN
test edildi (`test_device_tree_uretici.py`) — üretilen METNİN GERÇEK bir
device tree derleyicisinden geçtiği DEĞİL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from bulgu_sozlesmesi import Bulgu, bulgu_uret

SOC_RK3588 = "rk3588"
SOC_AMBARELLA = "ambarella"
DESTEKLENEN_SOC = (SOC_RK3588, SOC_AMBARELLA)


@dataclass
class KameraKanaliDtsGirdisi:
    kart_no: int
    i2c_bus: str            # RK3588 tarafında gerçek örn: "i2c3"
    i2c_adres: str           # deserializer'ın host'a gösterdiği hedef adres, ör "0x40"
    vc_id: int
    mipi_lane_sayisi: int = 2


def sozlesmeden_ve_plandan_dts_girdileri_uret(
    sozlesme_yolu: Path, i2c_bus_haritasi: Dict[int, str],
) -> List[KameraKanaliDtsGirdisi]:
    """`arayuz_sozlesmesi.yaml`'ı (`vc_id.atama` + `i2c_adres_cevirisi`,
    bkz. `sistem_orkestratoru.py::plani_sozlesmeye_birlestir`) okuyup her
    kart için bir DTS girdisi üretir.

    `i2c_bus_haritasi`, hangi `kart_no`'nun ana karttaki HANGİ fiziksel
    I2C bus'a (RK3588'de ör. `"i2c3"`) bağlı olduğunu verir — bu bilgi
    `arayuz_sozlesmesi.yaml`'da YOKTUR (o sadece konnektör pin tablosu
    tutar, board-level I2C mux/bus atamasını TUTMAZ), bu yüzden çağıran
    taraf AYRICA sağlamalı; uydurma bir varsayılan ÜRETİLMEZ — haritada
    olmayan kart adayları sessizce ATLANIR (hata FIRLATILMAZ, çağıran
    `dts_fragment_uret()` boş girdi listesini KAPSAM_YOK olarak ele alır).
    """
    veri = yaml.safe_load(sozlesme_yolu.read_text(encoding="utf-8")) or {}
    vc_id_atama = veri.get("vc_id", {}).get("atama", {})
    i2c_cevirisi = veri.get("i2c_adres_cevirisi", {})

    girdiler: List[KameraKanaliDtsGirdisi] = []
    for kart_anahtari, vc_id in sorted(vc_id_atama.items(), key=lambda kv: kv[1]):
        try:
            kart_no = int(kart_anahtari.split("_")[-1])
        except ValueError:
            continue
        adres_bilgisi = i2c_cevirisi.get(kart_anahtari)
        if adres_bilgisi is None:
            continue
        i2c_bus = i2c_bus_haritasi.get(kart_no)
        if i2c_bus is None:
            continue
        girdiler.append(KameraKanaliDtsGirdisi(
            kart_no=kart_no, i2c_bus=i2c_bus,
            i2c_adres=adres_bilgisi["deserializer_hedef_i2c_adresi"],
            vc_id=vc_id,
        ))
    return girdiler


def rk3588_kamera_overlay_uret(
    girdiler: List[KameraKanaliDtsGirdisi], sensor_compatible: str = "ovti,og05b10",
) -> str:
    """RK3588 mainline Linux stiliyle bir Device Tree Overlay FRAGMENT'i
    (metin) üretir — HER kart için bir I2C cihaz node'u + MIPI-CSI2 port
    bağlantısı iskeleti.

    SINIR: `&i2c3`/`&mipi4_csi2` gibi node isimleri TEMSİLİDİR — gerçek
    RK3588 pin/bus ataması KARTIN kendi şematik/pinmux kararına bağlıdır,
    burada SABİT DEĞİL, `i2c_bus_haritasi` üzerinden DIŞARIDAN verilir
    (bkz. `sozlesmeden_ve_plandan_dts_girdileri_uret`). `remote-endpoint`
    hedefi (hangi `&mipiN_csi2` port'una bağlanacağı) board-özel bir
    karardır — burada TODO olarak bırakıldı, uydurulmadı.
    """
    if not girdiler:
        return ""
    satirlar = ["/dts-v1/;", "/plugin/;", ""]
    for g in girdiler:
        adres_hex = g.i2c_adres[2:] if g.i2c_adres.lower().startswith("0x") else g.i2c_adres
        satirlar += [
            f"&{g.i2c_bus} {{",
            "    status = \"okay\";",
            "",
            f"    camera{g.kart_no}: camera@{adres_hex} {{",
            f"        compatible = \"{sensor_compatible}\";",
            f"        reg = <{g.i2c_adres}>;",
            "        clock-names = \"xvclk\";",
            f"        /* VC ID {g.vc_id} — deserializer register eşlemesi ayrı bir",
            "         * konfigürasyon adımıdır (bring-up sırasında strap/OTP ile),",
            "         * bu .dts fragment'i sadece host tarafı I2C/MIPI node'unu tanımlar. */",
            "",
            "        port {",
            f"            camera{g.kart_no}_out: endpoint {{",
            f"                data-lanes = <{' '.join(str(i + 1) for i in range(g.mipi_lane_sayisi))}>;",
            "                /* TODO: gerçek &mipiN_csi2 remote-endpoint hedefi",
            "                 * board-özel pinmux kararına göre BURADA doldurulmalı. */",
            "            };",
            "        };",
            "    };",
            "};",
            "",
        ]
    return "\n".join(satirlar)


def ambarella_kamera_overlay_uret(girdiler: List[KameraKanaliDtsGirdisi]) -> str:
    """Ambarella CV5S/CV72S KAPALI/NDA'lı bir SDK kullanır — bu SoC
    ailesi için GERÇEK device tree/BSP syntax'ı BU MODÜLDE BİLİNMİYOR.
    Sadece TASLAK bir yorum bloğu döner, GERÇEK bir `.dts` İDDİA EDİLMEZ
    (`dts_fragment_uret()` bu çıktıyı asla dosyaya YAZMAZ — bkz. o
    fonksiyon, bu metin sadece raporlama/görünürlük içindir)."""
    return (
        "/* TASLAK — Ambarella CV5S/CV72S device tree syntax'ı DOĞRULANMADI/BİLİNMİYOR.\n"
        " * Bu SoC ailesi kapalı/NDA'lı bir SDK kullanır; gerçek binding söz\n"
        " * dizimi Ambarella'nın resmi BSP dokümantasyonundan alınmadan burada\n"
        " * ÜRETİLMEMELİDİR (sayı/syntax uydurma yasağı, bkz. bulgu_sozlesmesi.py).\n"
        f" * {len(girdiler)} kart için VC ID/I2C planı MEVCUT (bkz. çağıran fonksiyon),\n"
        " * ama .dts çevirisi YAPILMADI ve YAPILAMAZ (bilgi eksikliği).\n"
        " */\n"
    )


def dts_fragment_uret(
    soc: str,
    sozlesme_yolu: Path,
    i2c_bus_haritasi: Dict[int, str],
    cikti_yolu: Optional[Path] = None,
    sensor_compatible: str = "ovti,og05b10",
) -> Bulgu:
    """`soc` için (`SOC_RK3588`/`SOC_AMBARELLA`) tek giriş noktası.

    Ambarella için HER ZAMAN `KAPSAM_YOK` (taranan=0) döner — girdi sayısı
    ne olursa olsun, çünkü bu SoC için GERÇEK bir `.dts` ÜRETİLEMEZ (bkz.
    `ambarella_kamera_overlay_uret`). `cikti_yolu` verilirse SADECE
    RK3588 dalında dosyaya yazılır; Ambarella dalında (taslak/placeholder
    metin) HİÇBİR dosyaya YAZILMAZ — uydurma bir `.dts` diskte kalıcı
    hale GETİRİLMEZ.
    """
    kontrol = "device_tree_fragment_uretimi"
    if soc not in DESTEKLENEN_SOC:
        return bulgu_uret(kontrol, taranan=0, detay=f"Bilinmeyen SoC: {soc!r} (desteklenen: {DESTEKLENEN_SOC}).")

    if not sozlesme_yolu.exists():
        return bulgu_uret(kontrol, taranan=0, detay=f"{sozlesme_yolu} bulunamadı.")

    girdiler = sozlesmeden_ve_plandan_dts_girdileri_uret(sozlesme_yolu, i2c_bus_haritasi)

    if soc == SOC_AMBARELLA:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                f"{len(girdiler)} kart için VC ID/I2C planı MEVCUT ama Ambarella "
                "CV5S/CV72S device tree syntax'ı bu modülde DOĞRULANMADI/BİLİNMİYOR "
                "(kapalı/NDA'lı SDK) — .dts ÜRETİLMEDİ, dosyaya YAZILMADI, uydurma "
                "syntax kullanılmadı (KAPSAM_YOK, PASS DEĞİL)."
            ),
        )

    if not girdiler:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                "arayuz_sozlesmesi.yaml'da eşleşen i2c_adres_cevirisi/i2c_bus_haritasi "
                "girdisi bulunamadı (KAPSAM_YOK) — önce "
                "'python main.py sistem-atama-plani-uret --sozlesme ...' ile "
                "i2c_adres_cevirisi bölümü yazılmalı, ve/veya i2c_bus_haritasi "
                "eksiksiz verilmeli."
            ),
        )

    metin = rk3588_kamera_overlay_uret(girdiler, sensor_compatible)
    if cikti_yolu is not None:
        cikti_yolu.parent.mkdir(parents=True, exist_ok=True)
        cikti_yolu.write_text(metin, encoding="utf-8")

    detay = (
        f"{len(girdiler)} kart için rk3588 .dts fragment'i üretildi"
        + (f", {cikti_yolu} dosyasına yazıldı" if cikti_yolu else " (dosyaya yazılmadı)")
        + ". UYARI: gerçek `dtc` ile derlenip donanımda DOĞRULANMADI (bkz. dosya başlığı)."
    )
    return bulgu_uret(kontrol, taranan=len(girdiler), detay=detay)
