"""
karar_birimleri.py
===================
"Karar birimi" şeması + bağımlılık grafiği — GÖREV 5-6 (governance
katmanı, 2026-08-03).

NEDEN BU DOSYA VAR: Ayrı bir projede (ProjectE/Otonom-PCB-Ajani) görülüp
pcb-tool-v2'de eksik olan mimari parça buydu. `DOCS/06_Kararlar/` bugüne
kadar serbest metin Markdown'dı — hangi kararın hangi kanıtla kapandığı,
hangi önceki karara bağımlı olduğu ve bir öncül karar değişince hangi
sonraki kararların OTOMATİK geçersiz sayılması gerektiği sadece insan
hafızasındaydı. Bu modül `DOCS/06_Kararlar/`'ın YERİNE geçmez (nesir
gerekçe hâlâ orada yazılır) — üstüne, makine tarafından SORGULANABİLİR
bir durum makinesi ekler: `main.py promote` artık "tüm kararlar kapandı
mı" diye insan hafızasına güvenmeden SORABİLİR (bkz. `main.py::cmd_promote`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class KararDurumu(str, Enum):
    ACIK = "ACIK"
    KANIT_BEKLIYOR = "KANIT_BEKLIYOR"
    KABUL_EDILDI = "KABUL_EDILDI"
    GECERSIZ_KILINDI = "GECERSIZ_KILINDI"


@dataclass
class KararBirimi:
    """Tek bir tasarım kararının durum makinesi kaydı.

    - `karar_id`: kalıcı, benzersiz kimlik (ör. "stackup-katman-sayisi").
    - `soru`: TEK, test edilebilir soru (ör. "Stackup 4 katman mı 6
      katman mı?") — belirsiz/çok parçalı sorular bu şemaya UYMAZ.
    - `sahip_skill`: bu kararı üreten `.claude/skills/*` yolu.
    - `bagimliliklar`: bu kararın doğrudan ÖNCÜLÜ olan karar_id'ler —
      bu karar, listelenen kararlar KABUL_EDILDI olmadan mantıken
      anlamlı değildir.
    - `gereken_kanit`: karar KABUL_EDILDI'ye geçmeden önce hangi dosya/
      DRC-sonucu/ölçüm gösterilmeli (serbest metin — otomatik doğrulama
      İSTEĞE BAĞLI, `main.py::cmd_promote` şimdilik sadece `durum`
      alanına bakar).
    - `gecersizlik_tetikleyicileri`: hangi olay bu kararı otomatik
      yeniden ACIK'a döndürür (serbest metin açıklama — makine
      tarafından TETİKLENMEZ, `karar_gecersiz_kil()` çağrısı elle/başka
      bir kontrol tarafından yapılır; bu alan SADECE dokümantasyondur).
    """

    karar_id: str
    soru: str
    sahip_skill: str = ""
    bagimliliklar: List[str] = field(default_factory=list)
    kisitlar: List[str] = field(default_factory=list)
    secenekler: List[str] = field(default_factory=list)
    gereken_kanit: str = ""
    durum: KararDurumu = KararDurumu.ACIK
    gecersizlik_tetikleyicileri: List[str] = field(default_factory=list)
    secilen_secenek: Optional[str] = None
    gecersiz_kilinma_sebebi: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["durum"] = self.durum.value if isinstance(self.durum, KararDurumu) else self.durum
        return d

    @staticmethod
    def from_dict(d: dict) -> "KararBirimi":
        d = dict(d)
        durum = d.get("durum", "ACIK")
        d["durum"] = KararDurumu(durum) if not isinstance(durum, KararDurumu) else durum
        alanlar = {f.name for f in KararBirimi.__dataclass_fields__.values()}
        return KararBirimi(**{k: v for k, v in d.items() if k in alanlar})


DOSYA_ADI = "karar_birimleri.json"


def karar_dosyasi_yolu(project_dir: str) -> Path:
    return Path(project_dir) / "DOCS" / DOSYA_ADI


def kararlari_yukle(project_dir: str) -> List[KararBirimi]:
    """`project_dir/DOCS/karar_birimleri.json`'u okur. Dosya yoksa boş
    liste döner (henüz hiç karar kaydedilmemiş projeler için normal
    durum — hata FIRLATMAZ)."""
    yol = karar_dosyasi_yolu(project_dir)
    if not yol.exists():
        return []
    veri = json.loads(yol.read_text(encoding="utf-8"))
    kayitlar = veri.get("kararlar", []) if isinstance(veri, dict) else veri
    return [KararBirimi.from_dict(k) for k in kayitlar]


def kararlari_kaydet(project_dir: str, kararlar: List[KararBirimi]) -> None:
    yol = karar_dosyasi_yolu(project_dir)
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = {"kararlar": [k.to_dict() for k in kararlar]}
    yol.write_text(json.dumps(veri, indent=2, ensure_ascii=False), encoding="utf-8")


def karar_ekle_veya_guncelle(project_dir: str, karar: KararBirimi) -> None:
    """`karar.karar_id` zaten varsa YERİNE geçer, yoksa eklenir. Diskten
    okuyup diske yazan tek-adımlı bir sarmalayıcı — küçük entegrasyon
    noktaları (ör. Faz akışındaki tek bir karar kaydı) için."""
    kararlar = kararlari_yukle(project_dir)
    for i, k in enumerate(kararlar):
        if k.karar_id == karar.karar_id:
            kararlar[i] = karar
            break
    else:
        kararlar.append(karar)
    kararlari_kaydet(project_dir, kararlar)


# ---------------------------------------------------------------------
# Bağımlılık grafiği — GÖREV 6
# ---------------------------------------------------------------------

class DongusuHatasi(ValueError):
    """Karar bağımlılık grafiğinde döngü tespit edildiğinde fırlatılır."""


def karar_grafigi_dogrula(kararlar: List[KararBirimi]) -> List[str]:
    """Tüm kararların `bagimliliklar` alanından bir DAG kurar.

    - Bilinmeyen bir `karar_id`'ye bağımlılık varsa `ValueError`.
    - Döngü varsa `DongusuHatasi` (döngüyü oluşturan yolu mesajda taşır).
    - Aksi halde bağımlılıkları ÖNCE gelecek şekilde topolojik sıralanmış
      `karar_id` listesi döner.
    """
    id_seti = {k.karar_id for k in kararlar}
    komsuluk: Dict[str, List[str]] = {k.karar_id: list(k.bagimliliklar) for k in kararlar}

    for kid, bagimlar in komsuluk.items():
        for b in bagimlar:
            if b not in id_seti:
                raise ValueError(f"{kid}: bilinmeyen bağımlılık karar_id={b!r}")

    BEYAZ, GRI, SIYAH = 0, 1, 2
    renk = {kid: BEYAZ for kid in id_seti}
    sira: List[str] = []
    yol_yigini: List[str] = []

    def dfs(kid: str) -> None:
        renk[kid] = GRI
        yol_yigini.append(kid)
        for b in komsuluk[kid]:
            if renk[b] == GRI:
                baslangic = yol_yigini.index(b)
                dongu = " -> ".join(yol_yigini[baslangic:] + [b])
                raise DongusuHatasi(f"karar bağımlılık grafiğinde döngü: {dongu}")
            if renk[b] == BEYAZ:
                dfs(b)
        yol_yigini.pop()
        renk[kid] = SIYAH
        sira.append(kid)

    for kid in sorted(id_seti):  # deterministik gezinme sırası
        if renk[kid] == BEYAZ:
            dfs(kid)
    return sira


def _bagimli_olanlari_bul(kararlar: List[KararBirimi], karar_id: str) -> List[str]:
    """`karar_id`'ye DOĞRUDAN veya DOLAYLI bağımlı (onu `bagimliliklar`
    zincirinde barındıran) tüm karar_id'leri BFS ile bulur."""
    ters_komsuluk: Dict[str, List[str]] = {}
    for k in kararlar:
        for b in k.bagimliliklar:
            ters_komsuluk.setdefault(b, []).append(k.karar_id)

    gorulen: List[str] = []
    kuyruk = list(ters_komsuluk.get(karar_id, []))
    while kuyruk:
        cur = kuyruk.pop(0)
        if cur in gorulen:
            continue
        gorulen.append(cur)
        kuyruk.extend(ters_komsuluk.get(cur, []))
    return gorulen


def karar_gecersiz_kil(kararlar: List[KararBirimi], karar_id: str, sebep: str) -> List[str]:
    """`karar_id`'yi `GECERSIZ_KILINDI` yapar VE ona doğrudan/dolaylı
    bağımlı TÜM kararları otomatik `ACIK`'a döndürür (zincirleme
    geçersizleme). `kararlar` listesi YERİNDE (in-place) değiştirilir —
    çağıran taraf `kararlari_kaydet()` ile diske yazmalı.

    Zaten `GECERSIZ_KILINDI` olan bağımlı kararlar tekrar `ACIK`'a
    ÇEKİLMEZ (onlar zaten kendi zincirleme geçersizleşmesini yaşamış
    olabilir — üzerine yazmak o geçmişi kaybettirir).

    Döner: bu çağrıyla `ACIK`'a dönen karar_id'lerin listesi.
    """
    by_id = {k.karar_id: k for k in kararlar}
    if karar_id not in by_id:
        raise KeyError(f"bilinmeyen karar_id: {karar_id}")

    hedef = by_id[karar_id]
    hedef.durum = KararDurumu.GECERSIZ_KILINDI
    hedef.gecersiz_kilinma_sebebi = sebep

    etkilenen = _bagimli_olanlari_bul(kararlar, karar_id)
    acilanlar: List[str] = []
    for kid in etkilenen:
        k = by_id[kid]
        if k.durum == KararDurumu.GECERSIZ_KILINDI:
            continue
        k.durum = KararDurumu.ACIK
        k.gecersiz_kilinma_sebebi = f"öncül karar {karar_id!r} geçersiz kılındı: {sebep}"
        acilanlar.append(kid)
    return acilanlar


# ---------------------------------------------------------------------
# Promotion kapısı yardımcıları — GÖREV 7
# ---------------------------------------------------------------------

def kabul_edilmemis_kararlari_bul(kararlar: List[KararBirimi]) -> List[KararBirimi]:
    """`KABUL_EDILDI` OLMAYAN (ACIK/KANIT_BEKLIYOR/GECERSIZ_KILINDI) tüm
    kararları döner. Boşsa (ve en az bir karar KABUL_EDILDI'ye
    ulaşabiliyorsa) promotion bu kapıdan geçebilir — bkz.
    `main.py::cmd_promote`."""
    return [k for k in kararlar if k.durum != KararDurumu.KABUL_EDILDI]


# ---------------------------------------------------------------------
# KRİTİK PİN DATASHEET-TEYİT KAPISI (2026-08-04) — Madde 1'in entegre
# edilebilir kısmı: datasheet'i OKUMAZ, teyit EDİLMEDEN promotion'ın
# GEÇMESİNİ engeller (mevcut DAG/geçersizleme mantığı DEĞİŞTİRİLMEDİ —
# sadece bu şemayı KULLANAN yeni bir üretici fonksiyon eklendi).
# ---------------------------------------------------------------------

# İsim deseni ile tespit edilen kritik pin kategorileri — "boot-strap",
# "mode-select", "reserved/NDA" ailesi. Basit substring eşleşmesi
# (regex DEĞİL) BİLİNÇLİ: sürpriz eşleşmeyi (ör. "SUBOOTH" gibi rastgele
# bir net adı) azaltmak için kelime sınırına yakın kısa/spesifik desenler
# seçildi. SIRA ÖNEMLİ: "SYSBOOT" gibi daha UZUN/spesifik desenler, "BOOT"
# gibi daha KISA/genel bir alt-dizeyi de İÇERDİĞİ için ÖNCE denenir —
# aksi halde "SYSBOOT0" gibi bir net her zaman genel "BOOT" kategorisine
# düşer, daha spesifik "SYSBOOT" kategorisi hiç yakalanmaz.
KRITIK_PIN_DESENLERI: tuple = ("SYSBOOT", "BOOT", "MODE_SEL", "NC_RESERVED", "NDA")


def kritik_pin_kategorisi_tespit_et(net_isim: str, desenler: tuple = KRITIK_PIN_DESENLERI) -> Optional[str]:
    """Net adında bilinen bir kritik-pin deseni varsa o deseni (kategori
    adı olarak) döner, yoksa `None`."""
    ad = net_isim.strip().upper()
    for desen in desenler:
        if desen in ad:
            return desen
    return None


def kritik_pin_teyit_karari_olustur(pin_kategorisi: str, komponent: str, gerekce: str) -> KararBirimi:
    """Bir komponentin kritik pin kategorisi için `durum=ACIK` bir
    `KararBirimi` İNŞA EDER (henüz DİSKE YAZMAZ — bkz.
    `kritik_pin_karalarini_tespit_ve_kaydet` diske yazan üst-seviye
    fonksiyon için). `gereken_kanit` alanı BİLEREK sabit ve net: bu karar
    KABUL_EDILDI olmadan `main.py promote` zaten mevcut
    `kabul_edilmemis_kararlari_bul()` kapısından GEÇEMEZ — ek kod
    GEREKMEZ, bu fonksiyon sadece doğru ŞEMADA bir kayıt üretir."""
    karar_id = f"kritik-pin-teyit-{komponent}-{pin_kategorisi}".lower().replace("_", "-")
    return KararBirimi(
        karar_id=karar_id,
        soru=(
            f"{komponent} üzerindeki '{pin_kategorisi}' kategorisi kritik pin(ler) "
            "üreticinin GÜNCEL datasheet/errata belgesinden teyit edildi mi?"
        ),
        sahip_skill=".claude/skills/schematic-design",
        kisitlar=[gerekce],
        gereken_kanit=(
            "Üreticinin GÜNCEL datasheet/errata belgesinden pin seviyesi/direnç "
            "değeri teyit edilmeli (ör. pull-up/pull-down zorunluluğu, strap "
            "seviyesi, NC pininin GERÇEKTEN bağlantısız mı yoksa NDA-altı bir "
            "fonksiyonu mu olduğu)."
        ),
        durum=KararDurumu.ACIK,
        gecersizlik_tetikleyicileri=[f"{komponent} parça numarası/revizyonu değişirse"],
    )


def kritik_pin_karalarini_tespit_ve_kaydet(
    project_dir: str, komponent: str, net_isimleri: List[str],
) -> List[KararBirimi]:
    """`net_isimleri`'ni tarar, HER benzersiz kritik-pin kategorisi için
    (board'da o kategori için ZATEN bir kayıt yoksa) bir karar birimi
    oluşturup diske kaydeder. Mevcut bir `karar_id`'yi EZMEZ — daha önce
    `KABUL_EDILDI`'ye çekilmiş bir karar tekrar `ACIK`'a DÜŞÜRÜLMEZ (bu,
    mevcut geçersizleme mantığının işi, `karar_gecersiz_kil()` ile
    yapılır — bu fonksiyon ona DOKUNMAZ)."""
    mevcut_id_seti = {k.karar_id for k in kararlari_yukle(project_dir)}
    goruleen_kategoriler: List[str] = []
    for net in net_isimleri:
        kategori = kritik_pin_kategorisi_tespit_et(net)
        if kategori is None or kategori in goruleen_kategoriler:
            continue
        goruleen_kategoriler.append(kategori)
        karar = kritik_pin_teyit_karari_olustur(
            kategori, komponent, f"Net '{net}' kritik pin deseniyle eşleşti.",
        )
        if karar.karar_id in mevcut_id_seti:
            continue
        karar_ekle_veya_guncelle(project_dir, karar)

    guncel = kararlari_yukle(project_dir)
    return [k for k in guncel if k.karar_id.startswith(f"kritik-pin-teyit-{komponent.lower()}-")]
