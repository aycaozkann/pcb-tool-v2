#!/usr/bin/env python3
"""
sistem_orkestratoru.py
========================
6 kamera kartı (ayrı fiziksel PCB, aynı tasarım) + 1 ana/hub kart arasındaki
VC ID ve I2C adres çevirisi planını, ana karttaki deserializer bağlantı
topolojisiyle tutarlı üretir.

MİMARİ DÜZELTME (orijinal taslağa göre):
--------------------------------------------------------------------------
Orijinal `SystemOrchestrator`, 6 kamerayı KiCad HİYERARŞİK ŞEMA SHEET'İ
olarak modelliyordu (`generate_hierarchical_sheets`). Bu YANLIŞ araç:
hiyerarşik sheet, TEK bir fiziksel board'un içindeki alt-devre
organizasyonudur — 6 AYRI fiziksel kartı temsil etmez. Kamera kartlarının
"modüler" (ayrı fiziksel PCB) olması gereksinimiyle çelişir.

Bunun yerine bu modül, `coklu_kart_sozlesme_kontrolu.py` ile aynı veri
modelini (`arayuz_sozlesmesi.yaml`) kullanır: kamera kartı TEK bir KiCad
projesi (6 kez üretilir), ana kart AYRI bir proje. Bu dosyanın işi şema
sheet'i üretmek DEĞİL, 6 kart için VC ID + I2C adres çevirisi planını
hesaplayıp `arayuz_sozlesmesi.yaml`'ın `vc_id` bölümüyle UYUMLU (gerçekten
aynı şema — bkz. altta) formatta yazmak/doğrulamak.

I2C ADRES DÜZELTMESİ:
----------------------
Orijinal taslak her sensöre `hex(0x30+i)` ile benzersiz bir I2C adresi
atıyordu — bu, sensörün DONANIMSAL OLARAK bu kadar çok adresi
desteklediğini varsayıyor. Gerçekte çoğu kamera sensörü (muhtemelen
OG05B10 dahil) yalnızca 1-2 pin-seçilebilir SCCB adresine sahiptir.
6 aynı sensörün adres çakışmasını çözen katman SENSÖRDE değil,
**deserializer'ın I2C adres çevirisi (address translation)**
özelliğindedir — GMSL2 (MAX9296) ve FPD-Link III (DS90UB954) gibi
deserializer'ların standart bir özelliği: her kanal için "kaynak adres →
hedef adres" eşlemesi deserializer register'ına yazılır, sensörün kendi
adresi HİÇ DEĞİŞMEZ. Bu modül o yüzden sensör adresini SABİT tutar, sadece
deserializer eşleme tablosunu üretir.

YAML UYUMLULUK DÜZELTMESİ (bu görevde ayrıca istendi): orijinal
`plani_yaml_e_yaz()`, docstring'inde "arayuz_sozlesmesi.yaml'ın vc_id.atama
bölümüyle UYUMLU" diye İDDİA EDİYORDU ama fiilen TAMAMEN FARKLI bir şema
yazıyordu (üst seviye "atamalar" listesi, dataclass'ların ham dump'ı) —
`coklu_kart_sozlesme_kontrolu.py::VcIdPlani.atama` (`Dict[str, int]`,
`{"kart_1": 0, ...}`) ile UYUŞMUYORDU. Şimdi GERÇEKTEN o şemaya yazıyor;
I2C adres çevirisi bilgisi (`arayuz_sozlesmesi.yaml`'da HENÜZ karşılığı
olmayan yeni bir bilgi) ayrı, ADDİTİF bir `i2c_adres_cevirisi` anahtarı
altında tutulur — mevcut şemanın hiçbir alanını EZMEZ/ÇAKIŞTIRMAZ.

DOĞRULAMA DURUMU: OG05B10'un SCCB adres pin stratejisi (kaç adres
seçilebiliyor, hangi pinle) NDA'lı datasheet'te — bu modül şimdilik
`sensor_sabit_i2c_adresi` parametresini DIŞARIDAN alır, varsayım
ÜRETMEZ. Gerçek datasheet gelince bu değer main.py çağrısında sabitlenmeli.
`atama_plani_uret()`/`plani_dogrula()`/`plani_yaml_e_yaz()`/`plani_
sozlesmeye_birlestir()` bu ortamda GERÇEKTEN test edildi (`test_sistem_
orkestratoru.py`, pyyaml zaten bu projede kurulu) — pcbnew/donanım
GEREKTİRMEZ, saf veri/YAML dönüşümüdür.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml

from bulgu_sozlesmesi import Bulgu, bulgu_uret


@dataclass
class KameraKartiAtamasi:
    kart_no: int  # 1..N
    vc_id: int
    deserializer_kanal_no: int  # ana karttaki fiziksel giriş no
    sensor_sabit_i2c_adresi: str  # ör. "0x36" — TÜM kartlarda AYNI, değişmez
    deserializer_hedef_i2c_adresi: str  # deserializer'ın host tarafına
    # gösterdiği, benzersiz sanal adres — BU farklılaşır


@dataclass
class SistemAtamaPlani:
    kamera_sayisi: int
    atamalar: List[KameraKartiAtamasi] = field(default_factory=list)


def atama_plani_uret(
    kamera_sayisi: int,
    sensor_sabit_i2c_adresi: str,
    deserializer_taban_hedef_adresi: int = 0x40,
) -> SistemAtamaPlani:
    """Her kart için VC ID (0..N-1) ve deserializer hedef adresi üretir.

    Sensörün kendi adresi (`sensor_sabit_i2c_adresi`) TÜM kartlarda aynı
    kalır — bu, gerçek donanımda sensör tarafında hiçbir strap/OTP
    değişikliği gerekmediği anlamına gelir. Farklılaşan tek şey
    deserializer'ın o kanalı hangi "sanal" adrese çevireceğidir.
    """
    atamalar = [
        KameraKartiAtamasi(
            kart_no=i,
            vc_id=i - 1,
            deserializer_kanal_no=i,
            sensor_sabit_i2c_adresi=sensor_sabit_i2c_adresi,
            deserializer_hedef_i2c_adresi=hex(deserializer_taban_hedef_adresi + i - 1),
        )
        for i in range(1, kamera_sayisi + 1)
    ]
    return SistemAtamaPlani(kamera_sayisi=kamera_sayisi, atamalar=atamalar)


def plani_dogrula(plan: SistemAtamaPlani, deserializer_maks_kanal: int) -> Bulgu:
    """VC ID çakışması, kanal sayısı sınırı ve deserializer hedef I2C
    adresi çakışması kontrolü."""
    ihlaller = []
    vc_idler = [a.vc_id for a in plan.atamalar]
    if len(set(vc_idler)) != len(vc_idler):
        tekrarlar = [v for v in vc_idler if vc_idler.count(v) > 1]
        ihlaller.append({"sebep": "VC ID çakışması", "cakisan_idler": sorted(set(tekrarlar))})

    if plan.kamera_sayisi > deserializer_maks_kanal:
        ihlaller.append({
            "sebep": "kamera sayısı deserializer kanal limitini aşıyor",
            "kamera_sayisi": plan.kamera_sayisi,
            "deserializer_maks_kanal": deserializer_maks_kanal,
        })

    hedef_adresler = [a.deserializer_hedef_i2c_adresi for a in plan.atamalar]
    if len(set(hedef_adresler)) != len(hedef_adresler):
        ihlaller.append({"sebep": "deserializer hedef I2C adresi çakışması"})

    return bulgu_uret(
        kontrol="sistem_atama_plani_dogrulama",
        taranan=len(plan.atamalar),
        ihlaller=ihlaller,
        detay="VC ID + deserializer I2C adres çevirisi planı kontrol edildi.",
    )


def _plan_vc_id_sozluk(plan: SistemAtamaPlani) -> Dict[str, int]:
    """`coklu_kart_sozlesme_kontrolu.py::VcIdPlani.atama` ile BİREBİR AYNI
    şema: `{"kart_N": vc_id}` — anahtar adı `arayuz_sozlesmesi.yaml`
    örneğindeki `kart_1..kart_6` deseniyle TUTARLI."""
    return {f"kart_{a.kart_no}": a.vc_id for a in plan.atamalar}


def plani_yaml_e_yaz(plan: SistemAtamaPlani, cikti_yolu: Path) -> None:
    """`arayuz_sozlesmesi.yaml`'ın `vc_id` bölümüyle GERÇEKTEN uyumlu
    formatta yazar (`{"vc_id": {"aralik": [...], "atama": {...}}}` —
    `coklu_kart_sozlesme_kontrolu.VcIdPlani` bu sözlüğü DOĞRUDAN
    `VcIdPlani(aralik=tuple(...), atama=dict(...))` ile okuyabilir).

    I2C adres çevirisi bilgisi (henüz `arayuz_sozlesmesi.yaml`'ın bir
    parçası DEĞİL) ayrı, ADDİTİF bir `i2c_adres_cevirisi` anahtarı altında
    yazılır — mevcut şemanın hiçbir alanını EZMEZ."""
    veri = {
        "vc_id": {
            "aralik": [0, plan.kamera_sayisi - 1],
            "atama": _plan_vc_id_sozluk(plan),
        },
        "i2c_adres_cevirisi": {
            f"kart_{a.kart_no}": {
                "deserializer_kanal_no": a.deserializer_kanal_no,
                "sensor_sabit_i2c_adresi": a.sensor_sabit_i2c_adresi,
                "deserializer_hedef_i2c_adresi": a.deserializer_hedef_i2c_adresi,
            }
            for a in plan.atamalar
        },
    }
    cikti_yolu.write_text(yaml.safe_dump(veri, allow_unicode=True, sort_keys=False), encoding="utf-8")


def plani_sozlesmeye_birlestir(plan: SistemAtamaPlani, sozlesme_yolu: Path) -> None:
    """Mevcut bir `arayuz_sozlesmesi.yaml`'ı okuyup SADECE `vc_id` ve
    `i2c_adres_cevirisi` anahtarlarını bu plandan GÜNCELLER — `konnektor`/
    `guc_butcesi` gibi diğer bölümlere DOKUNMAZ. Dosya yoksa `FileNotFoundError`
    (sessizce boş bir sözleşme UYDURULMAZ — `arayuz_sozlesmesi.yaml` insan
    tarafından elle başlatılmış olmalı, bkz. o dosyanın kendi başlığı)."""
    if not sozlesme_yolu.exists():
        raise FileNotFoundError(
            f"{sozlesme_yolu} bulunamadı — önce insan tarafından elle "
            "oluşturulmuş bir arayuz_sozlesmesi.yaml gerekli."
        )
    veri = yaml.safe_load(sozlesme_yolu.read_text(encoding="utf-8")) or {}
    veri["vc_id"] = {
        "aralik": [0, plan.kamera_sayisi - 1],
        "atama": _plan_vc_id_sozluk(plan),
    }
    veri["i2c_adres_cevirisi"] = {
        f"kart_{a.kart_no}": {
            "deserializer_kanal_no": a.deserializer_kanal_no,
            "sensor_sabit_i2c_adresi": a.sensor_sabit_i2c_adresi,
            "deserializer_hedef_i2c_adresi": a.deserializer_hedef_i2c_adresi,
        }
        for a in plan.atamalar
    }
    sozlesme_yolu.write_text(yaml.safe_dump(veri, allow_unicode=True, sort_keys=False), encoding="utf-8")
