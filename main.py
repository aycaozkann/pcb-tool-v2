#!/usr/bin/env python3
"""pcb-tool-v2 otonom akışının tek-komut yürütücüsü.

    python main.py run --project-dir "yol/proje" [--produce] [--kicad-cli ...]
    python main.py promote --project-dir "yol/proje" [--scratch-id ID] [--kicad-cli ...]

`CLAUDE.md`'deki "Otonom akış (sırayla)" listesinin adım 1 (ortam), adım 3
(şematik + ERC) ve adım 5 (DRC kapısı) bölümlerini TEK bir komuta bağlar.
Adım 4 (yerleşim/routing) ve adım 6-7 (checker/üretim) BİLİNÇLİ OLARAK bu
komuta dahil EDİLMEDİ: onlar `pcbnew` + insan onayı (routing_plan.md) veya
ayrı bir skill (design-checker) gerektiriyor, tek bir CLI komutunun arkasına
sessizce gizlenemezler (bkz. MASTER_RULEBOOK "Ne zaman dur").

**Faz 4b: Mekanik-Termal Entegrasyon (2026-08-03):** DRC kapısından hemen
sonra `faz_termal_mekanik()` çalışır — proje kökünde `termal_mekanik_veri.json`
varsa `ecad_mcad_termal_kopru.termal_mekanik_taramasi_calistir()` ile
komponent/kasa termal teması taranır (`bulgu_sozlesmesi.Bulgu` sözleşmesi:
`FAIL` -> hem `run` hem `promote` durur; `KAPSAM_YOK` -> veri paylaşılmamış,
engel DEĞİL). Dosya yoksa faz sessizce KAPSAM_YOK raporlar, hata FIRLATMAZ. Bu script,
DRC/ERC temiz olmadan `uretim_ciktilari_cli.py`'nin çağrılamayacağını
GERÇEKTEN uygular — "fail-closed" davranışı elle tekrarlamak yerine mevcut
modülleri sırayla çağırır.

**Governance katmanı (2026-08-03, GÖREV 1-7):** `run` artık kanonik proje
dosyalarına DİREKT yazmaz — önce `.scratch/<id>/` altına kopyalar, TÜM
fazlar scratch kopya üzerinde çalışır. Kanonik dosyaya geçiş SADECE
`promote` komutuyla, SADECE (a) taze DRC/ERC temiz VE (b) proje-özel
kontratı ölçen bağımsız verifier (`bagimsiz_dogrulama.py`) temiz VE (c)
tüm `karar_birimleri.json` kayıtları `KABUL_EDILDI` olduğunda olur —
bkz. `cmd_promote`. Bu, MASTER_RULEBOOK BÖLÜM 0 "Rapor-Veri Tutarlılığı"
maddesinin YAPTIRIM MEKANİZMASIDIR: bir rapor "temiz"/"güvenli" diyebilmesi
için artık GERÇEKTEN bu kapılardan geçmiş olması gerekir, iddia tek başına
yetmez.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from arac_yollari import tum_araclari_kontrol_et
from bagimsiz_dogrulama import (
    bagimsiz_dogrulama_calistir,
    dogrulama_temiz_mi,
    kapsam_yok_maddeleri,
)
from bulgu_sozlesmesi import Bulgu, BulguDurumu, ozet_rapor
from ecad_mcad_termal_kopru import (
    KomponentTermalDurumu,
    TermalTemasBolgesi,
    termal_mekanik_taramasi_calistir,
)
from karar_birimleri import kabul_edilmemis_kararlari_bul, kararlari_yukle
from kicad_koprusu import (
    drc_calistir,
    drc_raporunu_ozetle,
    drc_temiz_mi,
    erc_calistir,
)
from kuvvet_yonelimli_yerlesim import (
    Komponent,
    MesafeKisiti,
    Net,
    YerlesimKategorisi,
    cakisma_kontrolu,
    hiyerarsik_yerlesim_coz,
    kisitlari_dogrula,
    termal_kisitlarini_uret,
    yerlesim_raporu_uret,
)
from pcb_stackup_planner import TermalYonetim
from scratch_yonetimi import (
    kanonige_yukselt,
    scratch_kok_dizini,
    scratch_listele,
    scratch_olustur,
)

TERMAL_MEKANIK_VERI_DOSYASI = "termal_mekanik_veri.json"
YERLESIM_VERI_DOSYASI = "yerlesim_veri.json"
YERLESIM_SONUC_DOSYASI = "TEST/yerlesim_sonucu.json"
ANAHAT_DURUM_DOSYASI = "TEST/anahat_durumu.json"


def _konsol_utf8_ayarla() -> None:
    """Windows konsolunda Türkçe karakterlerin bozuk görünmesini (mojibake,
    `TEM�Z` gibi) önler: `sys.stdout`/`sys.stderr` UTF-8'e çevrilir. Eski
    Python/ortamlarda `reconfigure` yoksa sessizce atlanır."""
    for akim in (sys.stdout, sys.stderr):
        if akim is not None and hasattr(akim, "reconfigure"):
            try:
                akim.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _erc_ihlallerini_topla(rapor: dict) -> list[dict]:
    """`erc_calistir()` şeması `sheets[].violations` altında gelir (DRC'den
    farklı) — bkz. `kicad_koprusu.erc_calistir` docstring'i."""
    ihlaller: list[dict] = []
    for sayfa in rapor.get("sheets", []):
        ihlaller.extend(sayfa.get("violations", []))
    return ihlaller


def _erc_temiz_mi(rapor: dict) -> bool:
    return not any(v.get("severity") == "error" for v in _erc_ihlallerini_topla(rapor))


def _drc_baglantisiz_netler(rapor: dict) -> list[str]:
    """`unconnected_items` girdilerinden NET ADLARINI çıkarır.

    KiCad 10 DRC şemasında `unconnected_items[].items[].description`
    `"5 için [IMU_INT1] U1 ayak F.Cu"` biçimindedir — köşeli parantez
    içindeki değer net adıdır. Sıralı ve tekilleştirilmiş liste döner;
    parse edilemeyen girdiler (net adı yoksa) atlanır. Bu, kullanıcıya
    "HANGİ net yarım kalmış" bilgisini verir — `[error] Missing connection`
    satırı tek başına hangi net olduğunu söylemez."""
    netler: list[str] = []
    for ihlal in rapor.get("unconnected_items", []):
        for madde in ihlal.get("items", []):
            eslesme = re.search(r"\[([^\]]+)\]", madde.get("description", ""))
            if eslesme and eslesme.group(1) not in netler:
                netler.append(eslesme.group(1))
    return netler


def _proje_dosyalarini_bul(project_dir: Path) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """`project_dir` içinde tek bir `.kicad_pro` bulur, aynı gövde adıyla
    `.kicad_sch`/`.kicad_pcb` eşleştirir. Birden fazla/hiç bulunamazsa None
    döner — uydurma bir varsayılan İSİM SEÇİLMEZ."""
    adaylar = sorted(project_dir.glob("*.kicad_pro"))
    if len(adaylar) != 1:
        return None, None, None
    pro = adaylar[0]
    govde = pro.with_suffix("")
    sch = govde.with_suffix(".kicad_sch")
    pcb = govde.with_suffix(".kicad_pcb")
    return pro, (sch if sch.exists() else None), (pcb if pcb.exists() else None)


def _wire_label_sayilarini_oku(sch_path: Path) -> tuple[int, int]:
    """`.kicad_sch` içindeki üst-seviye `(wire ...)` ve `(label ...)` /
    `(global_label ...)` bloklarını sayar — `sch_wire.py`'nin "0-wire
    defekti" tespitiyle AYNI ölçüt (bkz. Changelog 2026-07-31 P0 notu)."""
    metin = sch_path.read_text(encoding="utf-8")
    wire_sayisi = metin.count("(wire ")
    label_sayisi = metin.count("(label ") + metin.count("(global_label ") + metin.count("(hierarchical_label ")
    return wire_sayisi, label_sayisi


def faz_ortam(kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ -1: Ortam ön kontrolü ===")
    sonuclar = tum_araclari_kontrol_et(kicad_cli)
    for durum in sonuclar:
        print(" ", durum.satir())
    kritik = {"KiCad CLI"}
    kritik_gecti = all(d.gecti_mi for d in sonuclar if d.isim in kritik)
    if not kritik_gecti:
        print("KRİTİK ARAÇ EKSİK (KiCad CLI) — devam edilemiyor, bkz. KURULUM.md.")
        return False
    eksikler = [d.isim for d in sonuclar if not d.gecti_mi]
    if eksikler:
        print(f"Opsiyonel araçlar eksik ({', '.join(eksikler)}) — ilgili fazlar bu makinede atlanacak/sınırlı çalışacak.")
    return True


def faz_sematik(sch_path: Path, kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ 2-3: Şematik + ERC ===")
    wire_n, label_n = _wire_label_sayilarini_oku(sch_path)
    if wire_n == 0 and label_n > 0:
        print(f"  UYARI: 0-wire deseni ({wire_n} wire / {label_n} label) — "
              f"'python rewire.py \"{sch_path}\" --write' ile gerçek wire'a çevrilmesi önerilir.")
    else:
        print(f"  wire={wire_n}, label={label_n}")

    rapor = erc_calistir(str(sch_path), kicad_cli=kicad_cli)
    ihlaller = _erc_ihlallerini_topla(rapor)
    for v in ihlaller:
        print(f"  [{v.get('severity', '?')}] {v.get('type', '')}: {v.get('description', '')}")
    temiz = _erc_temiz_mi(rapor)
    print(f"  ERC: {'TEMİZ (sadece uyarı olabilir)' if temiz else 'HATA VAR'} ({len(ihlaller)} bulgu)")
    return temiz


def _termal_mekanik_veri_yukle(
    proje_dizini: Path,
) -> tuple[list[KomponentTermalDurumu], list[TermalTemasBolgesi]]:
    """`proje_dizini/termal_mekanik_veri.json` varsa parse eder, yoksa
    BOŞ listeler döner (dosya yokluğu hata DEĞİL — `ecad_mcad_termal_kopru.py`
    modülünün "kasa/güç verisi paylaşılmadıysa sessizce atla" disipliniyle
    tutarlı; `faz_termal_mekanik` bu boşluğu `taranan=0` -> `KAPSAM_YOK`
    olarak raporlar, sessizce YOK SAYMAZ)."""
    veri_yolu = proje_dizini / TERMAL_MEKANIK_VERI_DOSYASI
    if not veri_yolu.is_file():
        return [], []

    veri = json.loads(veri_yolu.read_text(encoding="utf-8"))
    kritik_esik = veri.get("kritik_guc_esigi_W", 0.5)

    komponentler = [
        KomponentTermalDurumu(
            yonetim=TermalYonetim(
                isim=k["isim"],
                guc_yayilimi_W=k["guc_yayilimi_W"],
                mevcut_termal_via_sayisi=k.get("mevcut_termal_via_sayisi", 0),
            ),
            x=k["x"],
            y=k["y"],
            b_mask_acikligi_tanimli_mi=k.get("b_mask_acikligi_tanimli_mi", False),
            yuzey_kaplamasi=k.get("yuzey_kaplamasi", "TBD"),
        )
        for k in veri.get("komponentler", [])
    ]
    yuzeyler = [
        TermalTemasBolgesi(
            isim=y["isim"],
            poligon=[tuple(nokta) for nokta in y["poligon"]],
            z_boslugu_mm=y["z_boslugu_mm"],
        )
        for y in veri.get("yuzeyler", [])
    ]
    # kritik_esik şu an KomponentTermalDurumu'na taşınmıyor, faz fonksiyonu
    # termal_mekanik_taramasi_calistir()'a ayrıca geçirir.
    return komponentler, yuzeyler


def faz_termal_mekanik(proje_dizini: Path) -> Bulgu:
    print("\n=== FAZ 4b: Mekanik-Termal Entegrasyon ===")
    veri_yolu = proje_dizini / TERMAL_MEKANIK_VERI_DOSYASI
    if not veri_yolu.is_file():
        print(f"  ATLANDI: {TERMAL_MEKANIK_VERI_DOSYASI} bulunamadı — kasa/güç verisi "
              "paylaşılmamış (KAPSAM_YOK, hata değil).")
        return Bulgu("termal_mekanik_entegrasyonu", BulguDurumu.KAPSAM_YOK, 0, [], "veri dosyası yok")

    komponentler, yuzeyler = _termal_mekanik_veri_yukle(proje_dizini)
    veri = json.loads(veri_yolu.read_text(encoding="utf-8"))
    bulgu = termal_mekanik_taramasi_calistir(
        komponentler, yuzeyler, kritik_guc_esigi_W=veri.get("kritik_guc_esigi_W", 0.5)
    )
    for ihlal in bulgu.ihlaller:
        print(f"  [{ihlal.get('komponent', '?')}] {ihlal.get('mesaj', '')}")
    print(f"  Termal-mekanik: {bulgu.durum.value} ({bulgu.taranan} komponent, "
          f"{len(bulgu.ihlaller)} ihlal)")
    return bulgu


_KATEGORI_HARITASI = {
    "guc_dekuplaj": YerlesimKategorisi.GUC_DEKUPLAJ,
    "kritik_hs": YerlesimKategorisi.KRITIK_HS,
    "dusuk_hiz_io": YerlesimKategorisi.DUSUK_HIZ_IO,
}


def _yerlesim_veri_yukle(proje_dizini: Path):
    """`proje_dizini/yerlesim_veri.json` varsa parse eder — yoksa
    `faz_yerlesim_planlama` bunu KAPSAM_YOK olarak ele alır (dosya
    yokluğu hata değil, `faz_termal_mekanik`'in aynı disiplini)."""
    veri = json.loads((proje_dizini / YERLESIM_VERI_DOSYASI).read_text(encoding="utf-8"))

    komponentler = [
        Komponent(
            ref=k["ref"], genislik_mm=k.get("genislik_mm", 2.0), yukseklik_mm=k.get("yukseklik_mm", 2.0),
            x=k.get("x", 0.0), y=k.get("y", 0.0), sabit=k.get("sabit", False),
        )
        for k in veri.get("komponentler", [])
    ]
    kategoriler = {
        k["ref"]: _KATEGORI_HARITASI[k["kategori"]]
        for k in veri.get("komponentler", []) if "kategori" in k
    }
    netler = [
        Net(isim=n["isim"], baglantilar=n["baglantilar"], agirlik=n.get("agirlik", 1.0))
        for n in veri.get("netler", [])
    ]
    kisitlar = [
        MesafeKisiti(
            ref_a=k["ref_a"], ref_b=k["ref_b"], maks_mm=k.get("maks_mm"), min_mm=k.get("min_mm"),
            aciklama=k.get("aciklama", ""),
        )
        for k in veri.get("kisitlar", [])
    ]
    return (
        komponentler, kategoriler, netler, kisitlar,
        veri.get("kart_genisligi_mm", 100.0), veri.get("kart_yuksekligi_mm", 100.0),
    )


def faz_yerlesim_planlama(
    proje_dizini: Path,
    baslangic_koordinatlari: Optional[Dict[str, Tuple[float, float]]] = None,
) -> List[Bulgu]:
    """Faz 4: Hiyerarşik force-directed yerleşim PLANLAMASI.

    ÖNEMLİ SINIR (bilinçli, MASTER_RULEBOOK "Ne zaman dur" ile TUTARLI):
    Bu faz `.kicad_pcb`'ye HİÇBİR ŞEY YAZMAZ — `kuvvet_yonelimli_yerlesim.py`
    bir TOHUM/planlama motorudur (bkz. modülün kendi "bu modül tek başına
    yerleşimi BİTİRMEZ" notu), gerçek `pcbnew` yazımı ayrı, insan onaylı bir
    adımdır (dosyanın en başındaki "Adım 4 (yerleşim/routing) BİLİNÇLİ
    OLARAK bu komuta dahil EDİLMEDİ" kuralı BOZULMAZ). Çıktı, `TEST/`
    dizinine bir Markdown rapor olarak yazılır — insan bunu inceleyip
    gerçek board'a elle/`pcbnew` script'iyle uygular.

    Hiyerarşi ZORUNLU (`hiyerarsik_yerlesim_coz`): 1) güç/dekuplaj,
    2) kritik HS/diferansiyel, 3) düşük hızlı I/O.

    Termal keepout GİRDİ (habersiz ayrı adım DEĞİL): `termal_mekanik_veri.json`
    (Faz 4b) paylaşılmışsa, kasa temas bölgesindeki ısı kaynağı komponentler
    `termal_kisitlarini_uret()` ile ek sabit "termal çapa" komponentleri +
    `MesafeKisiti` olarak BU yerleşimin girdisine eklenir.

    `baslangic_koordinatlari` (FAZ 0.5 — anahat değişimi tetikleyicisi):
    verilirse `hiyerarsik_yerlesim_coz()`'e geçirilir, motor SIFIRDAN
    (altın-açı spiralinden) değil, verilen koordinatlardan başlar (bkz.
    `cmd_anahat_degisti_yeniden_yerlestir`). Bu faz her çağrıldığında,
    üretilen KESİN koordinatlar da `TEST/yerlesim_sonucu.json`'a
    (Markdown rapordan AYRI, makine tarafından okunabilir bir kopya)
    yazılır — bir SONRAKİ anahat değişimi bu dosyayı okuyup buradan
    devam eder.
    """
    print("\n=== FAZ 4: Yerleşim Planlaması (Hiyerarşik Force-Directed) ===")
    veri_yolu = proje_dizini / YERLESIM_VERI_DOSYASI
    if not veri_yolu.is_file():
        print(f"  ATLANDI: {YERLESIM_VERI_DOSYASI} bulunamadı (KAPSAM_YOK, hata değil).")
        kapsam_yok = lambda isim: Bulgu(isim, BulguDurumu.KAPSAM_YOK, 0, [], "veri dosyası yok")
        return [kapsam_yok("courtyard_cakismasi"), kapsam_yok("mesafe_kisitlari")]

    komponentler, kategoriler, netler, kisitlar, genislik, yukseklik = _yerlesim_veri_yukle(proje_dizini)

    termal_veri_yolu = proje_dizini / TERMAL_MEKANIK_VERI_DOSYASI
    if termal_veri_yolu.is_file():
        termal_komponentler, termal_yuzeyler = _termal_mekanik_veri_yukle(proje_dizini)
        termal_capalar, termal_kisitlar = termal_kisitlarini_uret(termal_komponentler, termal_yuzeyler)
        komponentler = list(komponentler) + termal_capalar
        kisitlar = list(kisitlar) + termal_kisitlar
        if termal_capalar:
            print(f"  Faz 4b termal keepout girdisi: {len(termal_capalar)} komponent için "
                  "ek kasa-temas kısıtı eklendi.")

    sonuc = hiyerarsik_yerlesim_coz(
        komponentler, kategoriler, netler, genislik, yukseklik, kisitlar,
        baslangic_koordinatlari=baslangic_koordinatlari,
    )
    cakisma_bulgu = cakisma_kontrolu(komponentler, sonuc.koordinatlar)
    kisit_bulgu = kisitlari_dogrula(kisitlar, sonuc.koordinatlar)

    print(f"  Yerleşim: {sonuc.iterasyon} iterasyon, yakınsadı={sonuc.yakinsadi_mi}, "
          f"ratsnest {sonuc.baslangic_ratsnest_mm}mm -> {sonuc.son_ratsnest_mm}mm")
    print(f"  Çakışma kontrolü: {cakisma_bulgu.durum.value} ({len(cakisma_bulgu.ihlaller)} ihlal)")
    print(f"  Mesafe kısıtları: {kisit_bulgu.durum.value} ({len(kisit_bulgu.ihlaller)} ihlal)")

    kumeler_ref_listesi = [[k.ref for k in komponentler]]
    rapor = yerlesim_raporu_uret(sonuc, kumeler_ref_listesi, [cakisma_bulgu, kisit_bulgu])
    rapor_dizini = proje_dizini / "TEST"
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "yerlesim_raporu.md").write_text(rapor, encoding="utf-8")
    print(f"  Rapor: {rapor_dizini / 'yerlesim_raporu.md'}")

    (proje_dizini / YERLESIM_SONUC_DOSYASI).write_text(
        json.dumps({"koordinatlar": {ref: list(xy) for ref, xy in sonuc.koordinatlar.items()}}, indent=2),
        encoding="utf-8",
    )

    return [cakisma_bulgu, kisit_bulgu]


# ------------------------------------------------------------------
# FAZ 0.5: Board anahat (DXF) değişimine otomatik yeniden yerleşim
# ------------------------------------------------------------------
#
# NEDEN AYRI BİR TETİKLEYİCİ (cmd_run'ın İÇİNE GÖMÜLMEDİ): DXF/mekanik
# anahat entegrasyonu şu an `main.py`'nin otomatik akışına (adım 1-7)
# HENÜZ BAĞLANMADI (bkz. CLAUDE.md — `mekanik_dxf_koprusu.py` elle/ayrı
# çağrılıyor). Bu yüzden "anahat değişti mi" sorusunu `cmd_run` içine
# sessizce gömmek, olmayan bir entegrasyonu VARMIŞ gibi göstermek olurdu.
# Bunun yerine bağımsız bir CLI komutu: kullanıcı/ajan mekanik DXF'i
# güncellediğinde AÇIKÇA çağırır, `main.py anahat-degisti-yeniden-yerlestir`.

def _dxf_icerik_hash_hesapla(dxf_yolu: Path) -> str:
    return hashlib.sha256(dxf_yolu.read_bytes()).hexdigest()


def anahat_degisti_mi(proje_dizini: Path, dxf_yolu: Path) -> bool:
    """DXF dosyasının İÇERİK hash'ini (mtime DEĞİL — mtime dosya kopyalanınca/
    checkout edilince bile değişir, sahte pozitif üretir) `TEST/anahat_
    durumu.json`'daki KAYITLI hash ile karşılaştırır.

    Kayıt hiç YOKSA (ilk çalıştırma) `True` döner — "değişti" değil ama
    karşılaştıracak bir önceki durum da yok; bu fonksiyonun çağıranı
    (`cmd_anahat_degisti_yeniden_yerlestir`) bu durumda zaten önceki bir
    yerleşim sonucu bulamayacağı için spiralden başlar, davranış doğru
    sonuca varır.
    """
    durum_yolu = proje_dizini / ANAHAT_DURUM_DOSYASI
    if not durum_yolu.is_file():
        return True
    kayitli = json.loads(durum_yolu.read_text(encoding="utf-8"))
    return kayitli.get("dxf_sha256") != _dxf_icerik_hash_hesapla(dxf_yolu)


def _anahat_durumunu_kaydet(proje_dizini: Path, dxf_yolu: Path) -> None:
    durum_yolu = proje_dizini / ANAHAT_DURUM_DOSYASI
    durum_yolu.parent.mkdir(parents=True, exist_ok=True)
    durum_yolu.write_text(
        json.dumps({"dxf_sha256": _dxf_icerik_hash_hesapla(dxf_yolu), "dxf_yolu": str(dxf_yolu)}, indent=2),
        encoding="utf-8",
    )


def onceki_yerlesim_koordinatlarini_yukle(proje_dizini: Path) -> Optional[Dict[str, Tuple[float, float]]]:
    """`faz_yerlesim_planlama()`'nın en son yazdığı `TEST/yerlesim_sonucu.json`'u
    okur. Dosya YOKSA (hiç yerleşim çalışmamış) `None` döner — sessizce
    boş bir koordinat kümesi UYDURULMAZ, çağıran bunu "spiralden başla"
    sinyali olarak okur."""
    yol = proje_dizini / YERLESIM_SONUC_DOSYASI
    if not yol.is_file():
        return None
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return {ref: (float(xy[0]), float(xy[1])) for ref, xy in veri.get("koordinatlar", {}).items()}


def cmd_anahat_degisti_yeniden_yerlestir(args: argparse.Namespace) -> int:
    """`main.py anahat-degisti-yeniden-yerlestir` — mekanik DXF anahatı
    DEĞİŞTİYSE, force-directed yerleşimi SIFIRDAN değil, önceki yakınsanmış
    sonucu başlangıç noktası alarak yeniden çalıştırır (FAZ 0.5 madde 8).

    Anahat DEĞİŞMEDİYSE (hash aynı) yerleşim TEKRAR ÇALIŞTIRILMAZ — gereksiz
    bir yeniden-hesaplama yapılmaz, `0` (başarı, "değişiklik yok") döner.
    """
    proje_dizini = Path(args.proje_dizini)
    dxf_yolu = Path(args.dxf_yolu)
    if not dxf_yolu.is_file():
        print(f"HATA: DXF dosyası bulunamadı: {dxf_yolu}")
        return 2

    if not anahat_degisti_mi(proje_dizini, dxf_yolu):
        print(f"Anahat DEĞİŞMEDİ ({dxf_yolu.name}) — yeniden yerleşim tetiklenmedi.")
        return 0

    onceki_koordinatlar = onceki_yerlesim_koordinatlarini_yukle(proje_dizini)
    if onceki_koordinatlar:
        print(
            f"Anahat DEĞİŞTİ ({dxf_yolu.name}) — önceki yerleşimin "
            f"{len(onceki_koordinatlar)} komponentlik koordinat kümesi başlangıç "
            "noktası olarak kullanılıyor (SIFIRDAN DEĞİL)."
        )
    else:
        print(f"Anahat DEĞİŞTİ ({dxf_yolu.name}) — önceki bir yerleşim sonucu yok, spiralden başlanıyor.")

    bulgular = faz_yerlesim_planlama(proje_dizini, baslangic_koordinatlari=onceki_koordinatlar)
    _anahat_durumunu_kaydet(proje_dizini, dxf_yolu)

    basarisiz = [b for b in bulgular if b.durum == BulguDurumu.FAIL]
    if basarisiz:
        print(f"  SONUÇ: {len(basarisiz)} bulgu FAIL — yerleşim raporu incelenmeli.")
        return 1
    print("  SONUÇ: yeniden yerleşim tamamlandı, sert kabul kapıları PASS/KAPSAM_YOK.")
    return 0


def faz_drc(pcb_path: Path, kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ 5: DRC kapısı ===")
    rapor = drc_calistir(str(pcb_path), kicad_cli=kicad_cli)
    for satir in drc_raporunu_ozetle(rapor):
        print(" ", satir)
    temiz = drc_temiz_mi(rapor)
    if not temiz:
        baglantisiz = _drc_baglantisiz_netler(rapor)
        if baglantisiz:
            print(f"  Bağlantısız netler: {', '.join(baglantisiz)} — bu netler routelanmamış;"
                  f" pcbnew'de iz çizimi (routing) tamamlanmadan DRC temizlenemez.")
    print(f"  DRC: {'TEMİZ (sadece uyarı olabilir)' if temiz else 'HATA VAR'}")
    return temiz


def faz_uretim(pcb_path: Path, sch_path: Path, project_dir: Path) -> int:
    print("\n=== FAZ 7: Üretim çıktıları (uretim_ciktilari_cli) ===")
    import shutil
    if shutil.which("kibot") is None:
        print("  UYARI: KiBot PATH'te bulunamadı (bkz. KURULUM.md madde 8).")
        print("  Üretim çıktıları (Gerber/BOM/CPL) KiBot ile üretilir;")
        print("  kurmak için: pip install kibot")
        print("  KiBot kurulmadan üretim çıktısı ÜRETİLEMEZ — DRC/ERC temiz olsa bile.")
        return 1
    import uretim_ciktilari_cli

    return uretim_ciktilari_cli.main([
        str(pcb_path), str(sch_path),
        "--kibot-config", str(project_dir / "kibot.yaml"),
        "--cikti-dizini", str(project_dir / "uretim"),
    ])


def cmd_via_capi(args: argparse.Namespace) -> int:
    """İnce alt-komut sarmalayıcısı — tüm mantık `via_capi_hesaplayici.main()`'de;
    burada sadece argparse Namespace'ini o modülün kendi CLI'sine devrediyoruz."""
    import via_capi_hesaplayici

    argv = ["--akim", str(args.akim), "--fabrika", args.fabrika]
    if args.sicaklik_artisi is not None:
        argv += ["--sicaklik-artisi", str(args.sicaklik_artisi)]
    if args.kaplama_oz is not None:
        argv += ["--kaplama-oz", str(args.kaplama_oz)]
    if args.json:
        argv += ["--json", args.json]
    return via_capi_hesaplayici.main(argv)


def cmd_coklu_kart_dogrula(args: argparse.Namespace) -> int:
    """Çoklu Kart (Kamera Kartı x6 + Ana Kart) arayüz sözleşmesi kapısı —
    `coklu_kart_sozlesme_kontrolu.py`'yi CLI'ye bağlar. KiCad'de resmi bir
    "multi-board" modu olmadığı için iki projenin ÇIKTISINI (konnektör
    pinout'u, VC ID ataması, güç bütçesi) `arayuz_sozlesmesi.yaml`'a karşı
    çapraz doğrulayan tek giriş noktasıdır (bkz. dosyanın kendi
    docstring'i). PASS/FAIL sonucu, `--karar-proje-dir` verilmişse
    `karar_birimleri.json`'a "coklu-kart-arayuz-tutarli" kararı olarak da
    yazılır — bu, o projenin `promote` kapısını (mevcut
    `kabul_edilmemis_kararlari_bul()` mekanizması ÜZERİNDEN, `cmd_promote`'a
    HİÇBİR yeni kod eklenmeden) otomatik olarak bağlar."""
    import coklu_kart_sozlesme_kontrolu as ckk

    print("\n=== ÇOKLU KART: kamera kartı <-> ana kart arayüz sözleşmesi ===")
    bulgular = ckk.tum_coklu_kart_kontrollerini_calistir(
        Path(args.sozlesme), Path(args.kamera_karti), Path(args.ana_kart),
        konnektor_sayisi=args.konnektor_sayisi,
        ana_kart_guc_girisi_maks_a=args.ana_kart_guc_girisi_maks_a,
    )
    ozet = ozet_rapor(bulgular)
    for k in ozet["kontroller"]:
        print(f"  [{k['durum']}] {k['kontrol']} (taranan={k['taranan']}, ihlal={k['ihlal_sayisi']})")
        for ihlal in k["ihlaller"]:
            print(f"    - {ihlal}")

    fail_var = any(b.durum == BulguDurumu.FAIL for b in bulgular)
    kapsam_yok_var = any(b.durum == BulguDurumu.KAPSAM_YOK for b in bulgular)
    pass_mi = not fail_var and not kapsam_yok_var

    if args.karar_proje_dir:
        detay = "; ".join(
            f"{k['kontrol']}={k['durum']}" for k in ozet["kontroller"] if k["durum"] != "PASS"
        )
        ckk.coklu_kart_karari_kaydet(args.karar_proje_dir, pass_mi, detay)
        print(f"  karar_birimleri.json güncellendi ({args.karar_proje_dir}): "
              f"{ckk.COKLU_KART_KARAR_ID} -> {'KABUL_EDILDI' if pass_mi else 'ACIK'}")

    if fail_var:
        print("\nSONUÇ: FAIL — çoklu kart arayüz sözleşmesi ihlal edildi.")
        return 1
    if kapsam_yok_var:
        print("\nSONUÇ: KAPSAM_YOK — bazı kontroller hiç çalıştırılamadı, bu PASS SAYILMAZ.")
        return 1
    print("\nSONUÇ: PASS — çoklu kart arayüz sözleşmesi tüm kontrollerden geçti.")
    return 0


def cmd_sistem_atama_plani_uret(args: argparse.Namespace) -> int:
    """`sistem_orkestratoru.py`'yi CLI'ye bağlar — 6 kamera kartı için VC ID
    + deserializer I2C adres-çevirisi planını hesaplar, doğrular, ve
    (isteğe bağlı) `arayuz_sozlesmesi.yaml`'a yazar.

    Önceden bu modül `main.py`'ye HİÇ bağlı değildi (sadece kendi test
    dosyasından çağrılıyordu) — bu, kod incelemesinde bulunan somut bir
    boşluktu. `plani_dogrula()` FAIL verirse hiçbir dosyaya YAZILMAZ
    (fail-closed — `coklu_kart_sozlesme_kontrolu.py` ile AYNI disiplin:
    geçersiz bir plan sessizce kalıcı hale getirilmez)."""
    import sistem_orkestratoru as so

    taban_adres = int(args.deserializer_taban_hedef_adresi, 0)
    plan = so.atama_plani_uret(
        args.kamera_sayisi, args.sensor_i2c_adresi, deserializer_taban_hedef_adresi=taban_adres,
    )

    print(f"\n=== SİSTEM ATAMA PLANI: {args.kamera_sayisi} kamera kartı ===")
    for a in plan.atamalar:
        print(f"  kart_{a.kart_no}: vc_id={a.vc_id}, kanal={a.deserializer_kanal_no}, "
              f"sensor={a.sensor_sabit_i2c_adresi}, deserializer_hedef={a.deserializer_hedef_i2c_adresi}")

    bulgu = so.plani_dogrula(plan, deserializer_maks_kanal=args.deserializer_maks_kanal)
    print(f"\n  [{bulgu.durum.value}] {bulgu.kontrol} (taranan={bulgu.taranan}, ihlal={len(bulgu.ihlaller)})")
    for ihlal in bulgu.ihlaller:
        print(f"    - {ihlal}")

    if bulgu.durum != BulguDurumu.PASS:
        print("\nSONUÇ: FAIL — plan doğrulamadan geçmedi, HİÇBİR dosyaya yazılmadı.")
        return 1

    if args.sozlesme:
        so.plani_sozlesmeye_birlestir(plan, Path(args.sozlesme))
        print(f"\nSONUÇ: PASS — {args.sozlesme} güncellendi (vc_id + i2c_adres_cevirisi).")
    elif args.cikti:
        so.plani_yaml_e_yaz(plan, Path(args.cikti))
        print(f"\nSONUÇ: PASS — plan {args.cikti} dosyasına yazıldı.")
    else:
        print("\nSONUÇ: PASS (dosyaya yazılmadı — --sozlesme veya --cikti verilmedi).")
    return 0


def cmd_device_tree_uret(args: argparse.Namespace) -> int:
    """`device_tree_uretici.py`'yi CLI'ye bağlar — `arayuz_sozlesmesi.yaml`
    + `sistem_orkestratoru.py` çıktısından (vc_id + i2c_adres_cevirisi)
    RK3588 için bir `.dts` fragment'i üretir.

    Ambarella için bu komut HER ZAMAN KAPSAM_YOK (çıkış kodu 1) döner —
    bu bir HATA DEĞİL, `device_tree_uretici.py`'nin kendi dosya
    başlığındaki bilinçli sınırdır (kapalı/NDA'lı SDK, syntax
    UYDURULMAZ)."""
    import json

    import device_tree_uretici as dtu

    bus_haritasi = {int(k): v for k, v in json.loads(args.bus_haritasi).items()}
    cikti_yolu = Path(args.cikti) if args.cikti else None

    bulgu = dtu.dts_fragment_uret(
        args.soc, Path(args.sozlesme), bus_haritasi,
        cikti_yolu=cikti_yolu, sensor_compatible=args.sensor_compatible,
    )
    print(f"\n=== DEVICE TREE FRAGMENT ÜRETİMİ ({args.soc}) ===")
    print(f"  [{bulgu.durum.value}] {bulgu.kontrol} (taranan={bulgu.taranan})")
    print(f"  {bulgu.detay}")

    if bulgu.durum == BulguDurumu.PASS:
        print("\nSONUÇ: PASS")
        return 0
    print("\nSONUÇ: KAPSAM_YOK — .dts üretilemedi/yazılmadı (bkz. detay).")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"HATA: proje dizini bulunamadı: {project_dir}")
        return 2

    if not faz_ortam(args.kicad_cli):
        return 1

    scratch_dir = scratch_olustur(str(project_dir))
    print(f"\nScratch çalışma alanı: {scratch_dir}")
    print("  Kanonik proje dosyaları bu oturumda DEĞİŞTİRİLMEYECEK.")
    print(f"  Kanonik konuma yazmak için: python main.py promote --project-dir \"{project_dir}\" --scratch-id {scratch_dir.name}")

    pro, sch, pcb = _proje_dosyalarini_bul(scratch_dir)
    if pro is None:
        # Kullanıcıya doğru --project-dir ipucunu KANONİK ağaçtan göster —
        # scratch içi bir yol göstermek yanıltıcı olurdu (ephemeral, promote
        # edilmeden kaybolur).
        alt_adaylar = sorted(project_dir.rglob("*.kicad_pro"))
        print(f"HATA: {project_dir} içinde tam olarak 1 adet .kicad_pro bulunamadı — hangi projeyi çalıştıracağım belirsiz.")
        if len(alt_adaylar) == 1:
            print(f"  İPUCU: proje dosyası alt klasörde bulundu: {alt_adaylar[0].parent}.")
            print(f"         --project-dir \"{alt_adaylar[0].parent}\" ile çalıştırın.")
        elif len(alt_adaylar) > 1:
            print("  İPUCU: birden fazla .kicad_pro alt klasörde bulundu:")
            for aday in alt_adaylar:
                print(f"         - {aday.parent}")
            print("         Hangi projeyi çalıştıracağınızı --project-dir ile açıkça belirtin.")
        return 2
    print(f"\nProje: {pro.name}  [scratch-id={scratch_dir.name}]")

    # DÜZELTME (cmd_promote'daki AYNI hata sınıfı — tutarlılık için burada da
    # düzeltildi): önceden `sematik_temiz = True` varsayılıp `.kicad_sch`
    # yoksa sessizce True kalıyordu — "ERC PASS oldu" ile "ERC hiç
    # KOŞMADI" ayırt edilemiyordu. Şimdi `None` (koşmadı) / `True` (PASS) /
    # `False` (FAIL) üç durumlu — sadece `sematik_temiz is False` gate'i
    # engeller, `None` (PCB-only akış meşru olabilir) engellemez.
    sematik_temiz = None
    if sch is not None:
        sematik_temiz = faz_sematik(sch, args.kicad_cli)
    else:
        print("\n=== FAZ 2-3: Şematik + ERC === \n  ATLANDI: .kicad_sch bulunamadı — "
              "ERC bu koşumda KOŞMADI (PASS SAYILMADI, sadece atlandı).")

    drc_temiz = True
    if pcb is not None:
        drc_temiz = faz_drc(pcb, args.kicad_cli)
    else:
        print("\n=== FAZ 5: DRC kapısı === \n  ATLANDI: .kicad_pcb bulunamadı")

    termal_bulgu = faz_termal_mekanik(scratch_dir)
    termal_temiz = termal_bulgu.durum != BulguDurumu.FAIL

    yerlesim_bulgulari = faz_yerlesim_planlama(scratch_dir)
    yerlesim_temiz = all(b.durum != BulguDurumu.FAIL for b in yerlesim_bulgulari)

    sematik_fail = sematik_temiz is False
    if sematik_fail or not (drc_temiz and termal_temiz and yerlesim_temiz):
        print("\nSONUÇ: FAIL — ERC/DRC/termal-mekanik/yerleşim hatası temizlenmeden üretime geçilmez.")
        return 1

    if args.produce:
        if sch is None or pcb is None:
            print("\nHATA: --produce için hem .kicad_sch hem .kicad_pcb gerekli.")
            return 2
        kod = faz_uretim(pcb, sch, scratch_dir)
        print(f"\nSONUÇ: {'PASS' if kod == 0 else 'FAIL'} (üretim çıktısı kodu={kod})")
        return kod

    print("\nSONUÇ: PASS (ERC/DRC temiz, scratch üzerinde). Kanonik konuma yazmak için "
          f"'python main.py promote --project-dir \"{project_dir}\" --scratch-id {scratch_dir.name}' çalıştırın.")
    return 0


# ------------------------------------------------------------------
# promote — scratch -> kanonik yükseltme kapısı (GÖREV 3 + 7)
# ------------------------------------------------------------------

def _dosya_sha256(yol: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(yol.read_bytes())
    return h.hexdigest()


def _ruleset_hash(scratch_dir: Path) -> str:
    """Bu promotion'da geçerli olan kural setinin (MASTER_RULEBOOK.md +
    varsa proje-özel `.kicad_dru`) TEK bir hash'e indirgenmesi — rapor
    hangi kural setine göre üretildiğini KANITLAR, sadece İDDİA ETMEZ."""
    import hashlib

    h = hashlib.sha256()
    rulebook = Path(__file__).resolve().parent / "MASTER_RULEBOOK.md"
    if rulebook.exists():
        h.update(rulebook.read_bytes())
    for dru in sorted(scratch_dir.glob("*.kicad_dru")):
        h.update(dru.read_bytes())
    return h.hexdigest()


def _komut_hash(argv: list) -> str:
    import hashlib

    return hashlib.sha256(" ".join(argv).encode("utf-8")).hexdigest()


def _otonom_commit_at(project_dir: Path, mesaj: str) -> bool:
    """FAZ -0.5 otonom commit kuralının promote karşılığı: `project_dir`
    bir git deposu İÇİNDEYSE `git add`/`git commit` çalıştırır. Depo
    değilse (veya git yoksa) sessizce False döner — promotion'ın BAŞARISI
    buna bağlı DEĞİLDİR, dosyalar zaten kanonik konuma kopyalanmış olur;
    commit sadece ek bir geri-alınabilirlik katmanıdır."""
    import subprocess

    try:
        kok = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if kok.returncode != 0:
            return False
        subprocess.run(["git", "-C", str(project_dir), "add", "."], check=True, timeout=30)
        subprocess.run(["git", "-C", str(project_dir), "commit", "-m", mesaj], check=True, timeout=30)
        return True
    except (OSError, ImportError):
        return False
    except Exception:
        # subprocess.SubprocessError alt sınıfları (CalledProcessError,
        # TimeoutExpired) dahil — commit'in başarısız olması promotion'ı
        # GERİ ALMAZ (dosyalar zaten kanonik konumda), sadece raporlanır.
        return False


def cmd_promote(args: argparse.Namespace) -> int:
    print("\n=== PROMOTE: scratch -> kanonik ===")
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"HATA: proje dizini bulunamadı: {project_dir}")
        return 2

    scratch_id = args.scratch_id
    if scratch_id is None:
        adaylar = scratch_listele(str(project_dir))
        if not adaylar:
            print("HATA: hiç scratch bulunamadı — önce 'python main.py run' çalıştırın.")
            return 2
        scratch_id = adaylar[0]
        print(f"  --scratch-id verilmedi, en yeni scratch kullanılıyor: {scratch_id}")

    scratch_dir = scratch_kok_dizini(str(project_dir)) / scratch_id
    if not scratch_dir.is_dir():
        print(f"HATA: scratch bulunamadı: {scratch_dir}")
        return 2

    pro, sch, pcb = _proje_dosyalarini_bul(scratch_dir)
    if pro is None or pcb is None:
        print("PROMOTION RED: scratch içinde tek bir .kicad_pro + .kicad_pcb bulunamadı.")
        return 2

    kapilar_gecti = True
    red_nedenleri: list = []

    # (1) taze DRC/ERC
    if sch is not None:
        sematik_temiz = faz_sematik(sch, args.kicad_cli)
        if not sematik_temiz:
            kapilar_gecti = False
            red_nedenleri.append("ERC temiz değil")
    else:
        # DÜZELTME: önceden burada sessizce sematik_temiz=True varsayılıyordu
        # — bu, "ERC PASS oldu" ile "ERC hiç KOŞMADI" durumlarını promote
        # çıktısında AYIRT EDİLEMEZ hale getiriyordu (bulgu_sozlesmesi.py'nin
        # önlemeye çalıştığı SESSİZ SAHTE PASS deseni). Şimdilik promotion'ı
        # ENGELLEMİYORUZ (bazı projelerde .kicad_sch olmadan PCB-only akış
        # meşru olabilir) ama durumu açıkça görünür kılıyoruz.
        # NOT: red_nedenleri sadece kapilar_gecti=False olduğunda (RED
        # yolunda) okunuyor — buraya eklemek promotion BAŞARILI olduğunda
        # hiç görünmeyen ölü bir satır olurdu. Asıl düzeltme aşağıdaki
        # anlık print — bu, promote BAŞARILI da olsa görünür.
        print("UYARI: .kicad_sch bulunamadı — ERC bu promote koşumunda "
              "KOŞMADI (PASS SAYILMADI, sadece atlandı).")
        sematik_temiz = None  # True/False DEĞİL — rapora "koşmadı" olarak
        # geçsin (JSON'da null), sessizce True ile karıştırılmasın (rapor
        # dict'indeki "erc_temiz" alanı).

    drc_temiz = faz_drc(pcb, args.kicad_cli)
    if not drc_temiz:
        kapilar_gecti = False
        red_nedenleri.append("DRC temiz değil")

    termal_bulgu = faz_termal_mekanik(scratch_dir)
    if termal_bulgu.durum == BulguDurumu.FAIL:
        kapilar_gecti = False
        red_nedenleri.append("termal-mekanik entegrasyonu FAIL")

    yerlesim_bulgulari = faz_yerlesim_planlama(scratch_dir)
    yerlesim_fail = [b for b in yerlesim_bulgulari if b.durum == BulguDurumu.FAIL]
    if yerlesim_fail:
        kapilar_gecti = False
        red_nedenleri.append(
            "yerleşim planlaması FAIL: " + ", ".join(b.kontrol for b in yerlesim_fail)
        )

    # (2) bağımsız verifier — proje-özel kontrat, KiCad DRC'den BAĞIMSIZ
    print("\n=== Bağımsız doğrulama (proje-özel kontrat) ===")
    dogrulama_ozeti = bagimsiz_dogrulama_calistir(str(pcb), str(scratch_dir))
    for k in dogrulama_ozeti["kontroller"]:
        print(f"  [{k['durum']}] {k['kontrol']} (taranan={k['taranan']}, ihlal={k['ihlal_sayisi']})")
    if not dogrulama_temiz_mi(dogrulama_ozeti):
        kapilar_gecti = False
        red_nedenleri.append("bağımsız verifier (proje-özel kontrat) FAIL")
    kapsam_disi = kapsam_yok_maddeleri(dogrulama_ozeti)
    if kapsam_disi:
        print(f"  UYARI (KAPSAM_YOK — kontrol EDİLEMEDİ, PASS/FAIL sayılmadı): {', '.join(kapsam_disi)}")

    # (2b) karar birimleri kapısı — GÖREV 7
    print("\n=== Karar birimleri ===")
    kararlar = kararlari_yukle(str(scratch_dir))
    acik_kararlar = kabul_edilmemis_kararlari_bul(kararlar)
    if acik_kararlar:
        kapilar_gecti = False
        red_nedenleri.append(
            "kapanmamış kararlar: " + ", ".join(f"{k.karar_id}({k.durum.value})" for k in acik_kararlar)
        )
        for k in acik_kararlar:
            print(f"  [{k.durum.value}] {k.karar_id}: {k.soru}")
    elif kararlar:
        print(f"  {len(kararlar)} karar, hepsi KABUL_EDILDI.")
    else:
        print("  (bu projede hiç karar_birimleri.json kaydı yok — bu kapı atlanıyor)")

    if not kapilar_gecti:
        print("\nSONUÇ: PROMOTION RED")
        for sebep in red_nedenleri:
            print(f"  - {sebep}")
        print(f"  Kanonik dosyaya HİÇBİR ŞEY yazılmadı. Scratch olduğu gibi bırakıldı: {scratch_dir}")
        return 1

    # (3) hash'li rapor + kanonik kopyalama + otonom commit
    board_hash = _dosya_sha256(pcb)
    ruleset_hash = _ruleset_hash(scratch_dir)
    komut_argv = ["main.py", "promote", "--project-dir", str(project_dir), "--scratch-id", scratch_id]
    komut_hash = _komut_hash(komut_argv)

    rapor_dir = project_dir / "DOCS" / "07_Dogrulama"
    rapor_dir.mkdir(parents=True, exist_ok=True)
    zaman = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rapor_yolu = rapor_dir / f"promotion_{zaman}.json"
    rapor = {
        "zaman_utc": zaman,
        "scratch_id": scratch_id,
        "board_sha256": board_hash,
        "ruleset_sha256": ruleset_hash,
        "komut_sha256": komut_hash,
        "komut": komut_argv,
        "erc_temiz": sematik_temiz,
        "drc_temiz": drc_temiz,
        "termal_mekanik": {
            "durum": termal_bulgu.durum.value,
            "taranan": termal_bulgu.taranan,
            "ihlal_sayisi": len(termal_bulgu.ihlaller),
        },
        "yerlesim_planlama": [
            {"kontrol": b.kontrol, "durum": b.durum.value, "taranan": b.taranan,
             "ihlal_sayisi": len(b.ihlaller)}
            for b in yerlesim_bulgulari
        ],
        "bagimsiz_dogrulama": dogrulama_ozeti,
        "karar_sayisi": len(kararlar),
        "sonuc": "PROMOTED",
    }
    rapor_yolu.write_text(json.dumps(rapor, indent=2, ensure_ascii=False), encoding="utf-8")

    kanonige_yukselt(scratch_dir, str(project_dir))

    commit_atildi = _otonom_commit_at(
        project_dir,
        f"FAZ PROMOTE: scratch {scratch_id} kanonige yukseltildi (board={board_hash[:12]})",
    )

    print(f"\nSONUÇ: PROMOTED — rapor: {rapor_yolu}")
    print(f"  board_sha256={board_hash[:16]}...  ruleset_sha256={ruleset_hash[:16]}...  komut_sha256={komut_hash[:16]}...")
    print(f"  {'git commit atıldı.' if commit_atildi else 'git deposu değil/commit atılamadı — dosyalar yine de kanonik konumda.'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="komut", required=True)

    run = sub.add_parser("run", help="ortam + şematik/ERC + DRC kapısını çalıştırır (opsiyonel: üretim çıktıları)")
    run.add_argument("--project-dir", default=".", help="proje kök dizini (.kicad_pro'nun bulunduğu yer)")
    run.add_argument("--produce", action="store_true", help="ERC/DRC temizse Gerber/BOM/CPL de üret")
    run.add_argument("--kicad-cli", help="kicad-cli(.exe) tam yolu; KICAD_CLI ortam değişkenini ezer")
    run.set_defaults(func=cmd_run)

    via_capi = sub.add_parser(
        "via-capi",
        help="IPC-2221 tabanlı via delik çapı / pad çapı hesaplayıcı (via_capi_hesaplayici.py)",
    )
    via_capi.add_argument("--akim", type=float, required=True, help="via'dan geçmesi gereken akım, A")
    via_capi.add_argument(
        "--fabrika", required=True,
        help="fabrika DFM profili adı (pcb_stackup_planner.FABRIKA_PROFILLERI, ör. JLCPCB_STANDART)",
    )
    via_capi.add_argument("--sicaklik-artisi", dest="sicaklik_artisi", type=float, default=None, help="izin verilen sıcaklık artışı, °C (varsayılan 10)")
    via_capi.add_argument("--kaplama-oz", dest="kaplama_oz", type=float, default=None, help="via kaplama kalınlığı, oz (varsayılan 1.0)")
    via_capi.add_argument("--json", default=None, help="sonucu ayrıca bu dosyaya JSON olarak yaz")
    via_capi.set_defaults(func=cmd_via_capi)

    coklu_kart = sub.add_parser(
        "coklu-kart-dogrula",
        help="kamera kartı (x6) + ana kart arayüz sözleşmesi (konnektör pinout/VC ID/güç bütçesi) çapraz doğrulaması",
    )
    coklu_kart.add_argument("--sozlesme", required=True, help="arayuz_sozlesmesi.yaml yolu")
    coklu_kart.add_argument("--kamera-karti", required=True, dest="kamera_karti", help="kamera kartı .kicad_pcb yolu")
    coklu_kart.add_argument("--ana-kart", required=True, dest="ana_kart", help="ana kart .kicad_pcb yolu")
    coklu_kart.add_argument("--konnektor-sayisi", dest="konnektor_sayisi", type=int, default=6, help="ana karttaki kamera konnektörü sayısı (varsayılan 6)")
    coklu_kart.add_argument("--ana-kart-guc-girisi-maks-a", dest="ana_kart_guc_girisi_maks_a", type=float, default=None, help="ana kart güç giriş sınırı, A (verilmezse sözleşmedeki değer kullanılır)")
    coklu_kart.add_argument("--karar-proje-dir", dest="karar_proje_dir", default=None, help="sonucu bu projenin karar_birimleri.json'ına 'coklu-kart-arayuz-tutarli' kararı olarak yaz (verilmezse yazılmaz)")
    coklu_kart.set_defaults(func=cmd_coklu_kart_dogrula)

    atama_plani = sub.add_parser(
        "sistem-atama-plani-uret",
        help="6 kamera kartı için VC ID + deserializer I2C adres-çevirisi planı üretir/doğrular (sistem_orkestratoru.py)",
    )
    atama_plani.add_argument("--kamera-sayisi", dest="kamera_sayisi", type=int, required=True, help="kart sayısı (ör. 6)")
    atama_plani.add_argument("--sensor-i2c-adresi", dest="sensor_i2c_adresi", required=True, help="sensörün SABİT SCCB/I2C adresi, ör. 0x36 (TÜM kartlarda aynı)")
    atama_plani.add_argument("--deserializer-taban-hedef-adresi", dest="deserializer_taban_hedef_adresi", default="0x40", help="deserializer'ın ilk karta atayacağı hedef adres, ör. 0x40 (varsayılan 0x40)")
    atama_plani.add_argument("--deserializer-maks-kanal", dest="deserializer_maks_kanal", type=int, required=True, help="deserializer'ın desteklediği maksimum kanal sayısı")
    atama_plani.add_argument("--sozlesme", default=None, help="mevcut arayuz_sozlesmesi.yaml yolu — verilirse SADECE vc_id/i2c_adres_cevirisi bölümleri güncellenir")
    atama_plani.add_argument("--cikti", default=None, help="--sozlesme verilmezse planı bu yeni dosyaya yaz")
    atama_plani.set_defaults(func=cmd_sistem_atama_plani_uret)

    dts = sub.add_parser(
        "device-tree-uret",
        help="arayuz_sozlesmesi.yaml + sistem_orkestratoru.py çıktısından RK3588 .dts fragment'i üretir (Ambarella: HER ZAMAN KAPSAM_YOK, bkz. device_tree_uretici.py)",
    )
    dts.add_argument("--soc", required=True, choices=["rk3588", "ambarella"])
    dts.add_argument("--sozlesme", required=True, help="arayuz_sozlesmesi.yaml yolu (i2c_adres_cevirisi/vc_id bölümleri dolu olmalı)")
    dts.add_argument("--bus-haritasi", dest="bus_haritasi", required=True, help='kart_no->I2C bus JSON, ör. {"1":"i2c1","2":"i2c3"}')
    dts.add_argument("--sensor-compatible", dest="sensor_compatible", default="ovti,og05b10", help="devicetree compatible string (varsayılan OG05B10)")
    dts.add_argument("--cikti", default=None, help="üretilen .dts fragment'inin yazılacağı dosya")
    dts.set_defaults(func=cmd_device_tree_uret)

    promote = sub.add_parser(
        "promote",
        help="scratch -> kanonik yükseltme kapısı (DRC/ERC + proje-özel kontrat + karar birimleri)",
    )
    promote.add_argument("--project-dir", required=True, help="proje kök dizini (kanonik)")
    promote.add_argument("--scratch-id", default=None, help="yükseltilecek scratch id; verilmezse en yeni scratch kullanılır")
    promote.add_argument("--kicad-cli", help="kicad-cli(.exe) tam yolu; KICAD_CLI ortam değişkenini ezer")
    promote.set_defaults(func=cmd_promote)

    anahat = sub.add_parser(
        "anahat-degisti-yeniden-yerlestir",
        help="mekanik DXF anahatı değiştiyse, force-directed yerleşimi önceki sonucu başlangıç alarak yeniden çalıştırır (FAZ 0.5 madde 8)",
    )
    anahat.add_argument("--proje-dizini", dest="proje_dizini", required=True, help="proje kök dizini (yerlesim_veri.json'ın bulunduğu yer)")
    anahat.add_argument("--dxf-yolu", dest="dxf_yolu", required=True, help="mekanik board anahat DXF dosyasının yolu")
    anahat.set_defaults(func=cmd_anahat_degisti_yeniden_yerlestir)

    return ap


def main(argv: Optional[list[str]] = None) -> int:
    _konsol_utf8_ayarla()
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
