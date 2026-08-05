#!/usr/bin/env python3
"""
kuvvet_yonelimli_yerlesim.py
=============================
Force-Directed Placement — komponentleri "göze uygun görünen" bir sezgiyle
DEĞİL, elektriksel bağlantı (ratsnest) ağırlıklarına göre çeken/iten bir
fizik grafiği motoruyla yerleştirir.

NEDEN BU DOSYA VAR:
-------------------
`.claude/skills/pcb-layout/SKILL.md` **Aşama 3.0** (Ratsnest Bazlı Gruplama)
şunu şart koşuyordu: "Dil modellerinin uzamsal zekası zayıftır — koordinatlar
asla serbestçe atanmaz, ÖNCE elektriksel bağlara göre kümelenir." Ama o
kuralın KOD KARŞILIĞI yoktu: kümeleme/koordinat ataması hâlâ modelin
kafasından çıkan sayılara bırakılmıştı. Bu modül o boşluğu kapatır —
Aşama 3.0'ın somut, tekrarlanabilir, ölçülebilir uygulamasıdır.

SINIRLARI (BİLEREK — bu modül tek başına yerleşimi BİTİRMEZ):
--------------------------------------------------------------
Bu motorun çıktısı bir **TOHUM (seed) yerleşimdir**, üretime giden son
yerleşim DEĞİL. Şunları BİLMEZ ve dolayısıyla ondan sonra ayrıca
koşturulmalıdır:
  - 3D/Z-ekseni ve kasa keepout'ları -> `mekanik_dxf_koprusu.py::z_kontrolu_yap()`
  - mm bazlı sabit kurallar (decoupling <=1.5mm, osilatör <=5mm, LDO-I2C
    >=10mm) -> `pcb-layout` Aşama 3.1-3.5. Bu kurallar bu motora
    `MesafeKisiti` olarak GİRDİ verilebilir (aşağıya bak) ama motorun
    yakınsaması onları GARANTİ ETMEZ; sonrasında `kisitlari_dogrula()` ile
    ölçülmeleri ZORUNLUDUR.
  - Termal ayrışma (Faz 4b), EMI bölgeleri, yüksek hızlı bölge boşluğu.

DETERMİNİZM (kasıtlı tasarım kararı):
--------------------------------------
Klasik force-directed algoritmalar rastgele başlangıç kullanır. Bu proje
"kafadan/rastgele sayı" üretmeyi her yerde yasakladığı için burada da
başlangıç yerleşimi RASTGELE DEĞİL: altın-açı (golden angle) spirali ile
DETERMİNİSTİK olarak üretilir. Aynı netlist -> her zaman aynı koordinatlar;
aksi halde "iki çalıştırmada iki farklı kart" çıkar ve hiçbir rapor
tekrarlanabilir olmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from ecad_mcad_termal_kopru import KomponentTermalDurumu, TermalTemasBolgesi, soguturucu_yuzey_bul

# Güç/toprak netleri force-directed grafiğine DAHİL EDİLMEZ (ağırlık 0):
# MASTER_RULEBOOK Faz 7'ye göre GND bir DÜZLEM olarak dökülür, nokta-nokta
# çekilen bir iz değildir. Grafiğe dahil edilirse yüzlerce pinli GND neti
# tüm komponentleri tek bir noktaya çöker (fiziksel olarak anlamsız) ve
# gerçek sinyal kümeleri kaybolur.
DUZLEM_NET_DESENLERI: Tuple[str, ...] = (
    "GND", "GNDA", "AGND", "DGND", "VSS",
    "+3V3", "+3.3V", "+5V", "+1V8", "VCC", "VDD", "VBAT", "VBUS",
)


def duzlem_neti_mi(net_ismi: str, desenler: Sequence[str] = DUZLEM_NET_DESENLERI) -> bool:
    """Net ismi bir güç/toprak DÜZLEMİ mi (grafikten çıkarılmalı mı)?

    Basit ön-ek/tam-eşleşme kontrolü — `pcb_stackup_planner.py`'nin net-class
    isimlendirme konvansiyonuyla aynı yaklaşım. Bilinçli olarak regex değil:
    sürpriz eşleşme (`GND_SENSE` gibi gerçekten çizilen bir sense hattının
    yanlışlıkla düzlem sayılması) riskini azaltmak için tam isim eşleşmesi
    aranır.
    """
    ad = net_ismi.strip().upper()
    return any(ad == d.upper() for d in desenler)


@dataclass
class Komponent:
    """Yerleştirilecek bir komponent.

    `sabit=True` olanlar (konnektörler, montaj delikleri, anten) HİÇ
    hareket etmez — `pcb-layout` Aşama 3.1'in "koordinatları kilitlenir
    (Lock)" kuralının motor içindeki karşılığıdır.
    """

    ref: str
    genislik_mm: float = 2.0   # courtyard genişliği (itme kuvvetinin yarıçapı)
    yukseklik_mm: float = 2.0
    x: float = 0.0
    y: float = 0.0
    sabit: bool = False

    @property
    def yaricap_mm(self) -> float:
        """Courtyard'ı çevreleyen dairenin yarıçapı — itme kuvvetinin
        etki mesafesi bundan türetilir (kare courtyard'ı daireyle
        yaklaştırmak, kesin çakışma testinden (`cakisma_kontrolu`) AYRI
        ve daha muhafazakâr bir tahmindir)."""
        return math.hypot(self.genislik_mm, self.yukseklik_mm) / 2.0


@dataclass
class Net:
    """Bir net ve ona bağlı komponent referansları."""

    isim: str
    baglantilar: List[str]
    agirlik: float = 1.0  # kritik netler (diferansiyel çift, CLK) için >1 verilir


@dataclass
class MesafeKisiti:
    """`pcb-layout` Aşama 3.3/3.5'ten gelen SERT mm kısıtı.

    `maks_mm` verilirse iki komponent en fazla o kadar uzak olabilir
    (decoupling <=1.5mm, osilatör <=5mm); `min_mm` verilirse en az o kadar
    yakın OLAMAZ (LDO <-> I2C >=10mm). Motor bunları yumuşak kuvvet olarak
    kullanır, `kisitlari_dogrula()` ise SERT kabul kriteri olarak ölçer.
    """

    ref_a: str
    ref_b: str
    maks_mm: Optional[float] = None
    min_mm: Optional[float] = None
    aciklama: str = ""


class YerlesimKategorisi(str, Enum):
    """`main.py` Faz 4 orkestrasyonunun ZORUNLU kıldığı 3 aşamalı hiyerarşi
    (2026-08-03, MASTER_RULEBOOK "Akış Öncelikli Yerleşim ve Hiyerarşik
    Routing" kuralı): önce güç/dekuplaj, sonra kritik HS/diferansiyel,
    en son düşük hızlı I/O."""

    GUC_DEKUPLAJ = "guc_dekuplaj"
    KRITIK_HS = "kritik_hs"
    DUSUK_HIZ_IO = "dusuk_hiz_io"


_HIYERARSI_SIRASI: Tuple[YerlesimKategorisi, ...] = (
    YerlesimKategorisi.GUC_DEKUPLAJ,
    YerlesimKategorisi.KRITIK_HS,
    YerlesimKategorisi.DUSUK_HIZ_IO,
)


@dataclass
class YerlesimSonucu:
    koordinatlar: Dict[str, Tuple[float, float]]
    iterasyon: int
    yakinsadi_mi: bool
    son_hareket_mm: float
    baslangic_ratsnest_mm: float
    son_ratsnest_mm: float

    @property
    def iyilesme_orani(self) -> float:
        """Toplam ratsnest uzunluğunda sağlanan iyileşme (0-1 arası).

        Motorun gerçekten bir iş yaptığının TEK ölçülebilir kanıtı budur —
        `test_kuvvet_yonelimli_yerlesim.py` bunu doğrular."""
        if self.baslangic_ratsnest_mm <= 0:
            return 0.0
        return max(
            0.0,
            (self.baslangic_ratsnest_mm - self.son_ratsnest_mm) / self.baslangic_ratsnest_mm,
        )


# ------------------------------------------------------------------
# 1. GRAF KURULUMU (netlist -> ağırlıklı kenar listesi)
# ------------------------------------------------------------------

def netlistten_graf_kur(
    netler: Sequence[Net],
    duzlem_netlerini_atla: bool = True,
) -> Dict[Tuple[str, str], float]:
    """Netlist'i ağırlıklı, yönsüz bir komşuluk grafiğine çevirir.

    YILDIZ (star) MODELİ: N pinli bir net, N*(N-1)/2 tam kenar (clique)
    yerine `agirlik / (N - 1)` ağırlıklı kenarlar üretir. Gerekçe: 8 pinli
    bir bus'ın clique'i 28 kenar demektir ve 2 pinli kritik bir diferansiyel
    çifti (1 kenar) ezer geçer — bu, fiziksel olarak yanlış bir öncelik
    sıralaması yaratır. Bölme, çok-pinli netlerin toplam çekim bütçesini
    2 pinli netlerle karşılaştırılabilir tutar.

    Güç/toprak netleri (`duzlem_neti_mi`) varsayılan olarak ATLANIR —
    gerekçe modül başlığındaki `DUZLEM_NET_DESENLERI` notunda.
    """
    kenarlar: Dict[Tuple[str, str], float] = {}
    for net in netler:
        if duzlem_netlerini_atla and duzlem_neti_mi(net.isim):
            continue
        benzersiz = sorted(set(net.baglantilar))
        if len(benzersiz) < 2:
            continue  # tek pinli/bağlantısız net çekim üretmez
        # HighSpeedRuleManager (bkz. Bölüm 6): net.agirlik ELLE verilmemişse
        # (varsayılan 1.0'da kaldıysa) VE net yüksek-hızlı/diferansiyel
        # tespit edilirse ağırlık otomatik yükseltilir - kullanıcı ayrıca
        # `Net(agirlik=...)` YAZMAK ZORUNDA kalmaz. Elle 1.0 dışında bir
        # değer verilmişse (örn. bilinçli olarak 0.5) o değere dokunulmaz.
        etkin_agirlik = net.agirlik
        if etkin_agirlik == 1.0 and yuksek_hizli_net_mi(net.isim):
            etkin_agirlik = YUKSEK_HIZLI_VARSAYILAN_AGIRLIK
        pay = etkin_agirlik / (len(benzersiz) - 1)
        for i in range(len(benzersiz)):
            for j in range(i + 1, len(benzersiz)):
                anahtar = (benzersiz[i], benzersiz[j])
                kenarlar[anahtar] = kenarlar.get(anahtar, 0.0) + pay
    return kenarlar


def kumeleri_bul(
    kenarlar: Dict[Tuple[str, str], float],
    tum_refler: Sequence[str],
    agirlik_esigi: float = 0.5,
) -> List[List[str]]:
    """`agirlik_esigi`'nin ÜSTÜNDEKİ kenarlardan bağlı bileşenler (cluster)
    çıkarır — `pcb-layout` Aşama 3.0 madde 2'nin ("aynı neti paylaşanlar tek
    mantıksal küme") doğrudan karşılığı.

    Eşiğin altındaki zayıf kenarlar (ör. 10 pinli bir bus'tan gelen 0.11
    ağırlıklı bağlar) küme sınırı çizmez — aksi halde her şey tek dev bir
    kümeye girer ve kümeleme bilgi taşımaz. Hiçbir bağı olmayan komponentler
    tek elemanlı küme olarak DÖNER (sessizce düşürülmez — kapsam kaybı
    `bulgu_sozlesmesi.py`'nin yasakladığı şeydir).
    """
    ebeveyn: Dict[str, str] = {r: r for r in tum_refler}

    def bul(a: str) -> str:
        while ebeveyn[a] != a:
            ebeveyn[a] = ebeveyn[ebeveyn[a]]
            a = ebeveyn[a]
        return a

    def birlestir(a: str, b: str) -> None:
        ka, kb = bul(a), bul(b)
        if ka != kb:
            ebeveyn[kb] = ka

    for (a, b), w in kenarlar.items():
        if w >= agirlik_esigi and a in ebeveyn and b in ebeveyn:
            birlestir(a, b)

    gruplar: Dict[str, List[str]] = {}
    for ref in tum_refler:
        gruplar.setdefault(bul(ref), []).append(ref)
    return [sorted(g) for g in sorted(gruplar.values(), key=lambda g: (-len(g), g[0]))]


def ratsnest_uzunlugu_toplami(
    koordinatlar: Dict[str, Tuple[float, float]],
    kenarlar: Dict[Tuple[str, str], float],
) -> float:
    """Ağırlıklı toplam ratsnest (hava-hattı) uzunluğu, mm.

    Yerleşim kalitesinin tek sayılık ölçütü. Ağırlıkla çarpılır: kritik bir
    netin 1mm'si, sıradan bir GPIO'nun 1mm'sinden daha değerlidir.
    """
    toplam = 0.0
    for (a, b), w in kenarlar.items():
        if a not in koordinatlar or b not in koordinatlar:
            continue
        ax, ay = koordinatlar[a]
        bx, by = koordinatlar[b]
        toplam += w * math.hypot(ax - bx, ay - by)
    return toplam


# ------------------------------------------------------------------
# 2. DETERMİNİSTİK BAŞLANGIÇ YERLEŞİMİ
# ------------------------------------------------------------------

ALTIN_ACI_RAD = math.pi * (3.0 - math.sqrt(5.0))  # ~2.39996 rad


def baslangic_yerlesimi_uret(
    komponentler: Sequence[Komponent],
    kart_genisligi_mm: float,
    kart_yuksekligi_mm: float,
    baslangic_aci_offset_rad: float = 0.0,
    baslangic_koordinatlari: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Dict[str, Tuple[float, float]]:
    """Altın-açı (Vogel) spirali ile DETERMİNİSTİK başlangıç yerleşimi.

    `random` KULLANILMAZ (modül başlığındaki determinizm notu). Vogel
    spirali, noktaları kart alanına düzgün (kümelenmesiz) dağıtır — bu,
    force-directed motorun ilk iterasyonlarında yapay bir "her şey üst üste"
    itme patlaması yaşamamasını sağlar.

    `baslangic_aci_offset_rad` (FAZ 0.5 — çoklu yerleşim seçeneği için):
    spiralin BAŞLANGIÇ açısını döndürür. `random` KULLANMADAN farklı
    "başlangıç konfigürasyonları" üretmenin yolu budur — aynı offset her
    zaman aynı spirali üretir (hâlâ tam deterministik), ama FARKLI bir
    offset motoru farklı bir yerel minimuma yönlendirebilir
    (`coklu_yerlesim_dene()` bunu bir parametre boyutu olarak kullanır).

    `baslangic_koordinatlari` (FAZ 0.5 — anahat değişince yeniden yerleşim
    için): verilirse, HAREKETLİ (sabit=False) bir komponentin başlangıç
    konumu spiralden DEĞİL, bu sözlükten okunur (ref sözlükte YOKSA spirale
    düşülür — ör. anahat değiştikten sonra netliste eklenen YENİ bir
    komponent için önceki bir sonuç olamaz). Yeni kart sınırlarına göre
    KIRPILIR (`min/max` — anahat küçülmüş olabilir, eski koordinat kart
    dışında kalabilir). Amaç: mekanik anahat küçük bir değişiklik geçirdiğinde
    yerleşimi SIFIRDAN değil, ÖNCEKİ yakınsanmış sonuçtan devam ettirmek
    (`main.py`'nin anahat-değişimi tetikleyicisi bunu kullanır).

    `sabit=True` komponentlerin mevcut (x, y)'si KORUNUR — onlar kasa/mekanik
    kısıtından geliyor, spiral (veya `baslangic_koordinatlari`) onları ezmez.
    """
    if kart_genisligi_mm <= 0 or kart_yuksekligi_mm <= 0:
        raise ValueError("kart boyutları pozitif olmalı.")

    merkez_x, merkez_y = kart_genisligi_mm / 2.0, kart_yuksekligi_mm / 2.0
    maks_r = min(kart_genisligi_mm, kart_yuksekligi_mm) * 0.45
    hareketliler = [k for k in komponentler if not k.sabit]

    koordinatlar: Dict[str, Tuple[float, float]] = {
        k.ref: (k.x, k.y) for k in komponentler if k.sabit
    }
    n = max(1, len(hareketliler))
    spiral_sirasi = 0
    for k in hareketliler:
        if baslangic_koordinatlari is not None and k.ref in baslangic_koordinatlari:
            x, y = baslangic_koordinatlari[k.ref]
            koordinatlar[k.ref] = (
                min(max(x, k.genislik_mm / 2.0), kart_genisligi_mm - k.genislik_mm / 2.0),
                min(max(y, k.yukseklik_mm / 2.0), kart_yuksekligi_mm - k.yukseklik_mm / 2.0),
            )
            continue
        r = maks_r * math.sqrt((spiral_sirasi + 0.5) / n)
        aci = spiral_sirasi * ALTIN_ACI_RAD + baslangic_aci_offset_rad
        koordinatlar[k.ref] = (
            merkez_x + r * math.cos(aci),
            merkez_y + r * math.sin(aci),
        )
        spiral_sirasi += 1
    return koordinatlar


# ------------------------------------------------------------------
# 3. FİZİK MOTORU
# ------------------------------------------------------------------

def _cakismalari_ayir(
    koordinatlar: Dict[str, Tuple[float, float]],
    ref_haritasi: Dict[str, Komponent],
    kart_genisligi_mm: float,
    kart_yuksekligi_mm: float,
    gecis_sayisi: int = 4,
) -> None:
    """AYIRMA (separation) geçişi — çakışan courtyard'ları yerinden iterek
    ayırır. Koordinat sözlüğünü YERİNDE değiştirir.

    NEDEN AYRI BİR GEÇİŞ GEREKTİ (ölçülmüş bir tasarım hatası):
    Saf force-directed modelde çekim `k*w*d` ile SINIRSIZ büyür (uzaklık ve
    net ağırlığıyla), itme ise `k*ortusme` ile SINIRLIDIR (en fazla
    `k*(r_a+r_b)`). Ağırlığı yüksek bir net (ör. 6 pinli bir CLK/bus,
    agirlik=10) verildiğinde çekim itmeyi EZER ve komponentler üst üste
    biner — bu, testle bilfiil gözlemlendi (6 çiftin 6'sı da çakıştı).
    Bu yüzden çakışmama artık bir kuvvet DENGESİNE bırakılmaz, her
    iterasyonun sonunda geometrik olarak ZORLANIR (d3-force'un
    `forceCollide` yaklaşımı).

    Yine de GARANTİ vermez: kart çok küçükse ayırma kart sınırına dayanır
    ve çakışma kalır — bu durumda `cakisma_kontrolu()` FAIL döner ve
    yerleşim reddedilir. Sessiz bir "ayırdım sayılır" YOK.
    """
    hareketliler = [r for r in koordinatlar if not ref_haritasi[r].sabit]
    if not hareketliler:
        return
    refler = list(koordinatlar.keys())
    for _ in range(gecis_sayisi):
        hareket_var = False
        for i in range(len(refler)):
            for j in range(i + 1, len(refler)):
                ra, rb = refler[i], refler[j]
                ka, kb = ref_haritasi[ra], ref_haritasi[rb]
                if ka.sabit and kb.sabit:
                    continue
                ax, ay = koordinatlar[ra]
                bx, by = koordinatlar[rb]
                # AABB çakışması — `cakisma_kontrolu()` ile AYNI ölçüt
                # kullanılır ki motor, kapının ölçtüğü şeyi çözsün.
                ortusme_x = (ka.genislik_mm + kb.genislik_mm) / 2.0 - abs(ax - bx)
                ortusme_y = (ka.yukseklik_mm + kb.yukseklik_mm) / 2.0 - abs(ay - by)
                if ortusme_x <= 0 or ortusme_y <= 0:
                    continue
                hareket_var = True
                # En az itme gerektiren eksende ayır (en kısa kaçış yolu).
                if ortusme_x < ortusme_y:
                    yon = 1.0 if bx >= ax else -1.0
                    itme = (ortusme_x + 1e-4) * yon
                    dx_a, dy_a, dx_b, dy_b = -itme, 0.0, itme, 0.0
                else:
                    yon = 1.0 if by >= ay else -1.0
                    itme = (ortusme_y + 1e-4) * yon
                    dx_a, dy_a, dx_b, dy_b = 0.0, -itme, 0.0, itme

                # Sabit parça hareket etmez -> tüm ayırmayı diğeri üstlenir.
                if ka.sabit:
                    dx_b, dy_b = dx_b * 2.0, dy_b * 2.0
                    dx_a = dy_a = 0.0
                elif kb.sabit:
                    dx_a, dy_a = dx_a * 2.0, dy_a * 2.0
                    dx_b = dy_b = 0.0
                else:
                    dx_a, dy_a, dx_b, dy_b = dx_a / 2, dy_a / 2, dx_b / 2, dy_b / 2

                for ref, dx, dy in ((ra, dx_a, dy_a), (rb, dx_b, dy_b)):
                    if ref_haritasi[ref].sabit:
                        continue
                    k = ref_haritasi[ref]
                    x, y = koordinatlar[ref]
                    koordinatlar[ref] = (
                        min(max(x + dx, k.genislik_mm / 2.0),
                            kart_genisligi_mm - k.genislik_mm / 2.0),
                        min(max(y + dy, k.yukseklik_mm / 2.0),
                            kart_yuksekligi_mm - k.yukseklik_mm / 2.0),
                    )
        if not hareket_var:
            break


def yerlesim_coz(
    komponentler: Sequence[Komponent],
    netler: Sequence[Net],
    kart_genisligi_mm: float,
    kart_yuksekligi_mm: float,
    kisitlar: Sequence[MesafeKisiti] = (),
    maks_iterasyon: int = 400,
    cekim_katsayisi: float = 0.08,
    itme_katsayisi: float = 1.0,
    yakinsama_esigi_mm: float = 0.01,
    baslangic_adimi_mm: float = 2.0,
    keepoutlar: Sequence["YuksekHizKeepout"] = (),
    baslangic_aci_offset_rad: float = 0.0,
    baslangic_koordinatlari: Optional[Dict[str, Tuple[float, float]]] = None,
) -> YerlesimSonucu:
    """Force-directed yerleşim: bağlı komponentleri ÇEKER, çakışanları İTER.

    Kuvvet modeli (Fruchterman-Reingold türevi, PCB'ye uyarlanmış):
      - **Çekim (Hooke):** her ağırlıklı kenar için `F = k_cekim * w * d`,
        bağlı komponentleri birbirine yaklaştırır. Mesafeyle DOĞRU orantılı
        (yay) — uzak bağlar daha güçlü çeker, bu ratsnest toplamını
        minimize eder.
      - **İtme (courtyard bazlı):** SADECE iki courtyard dairesi üst üste
        binerken devreye girer (`ortusme > 0`), `F = k_itme * ortusme`.
        Klasik 1/d^2 Coulomb yerine bu seçildi çünkü PCB'de amaç
        "komponentleri birbirinden uzaklaştırmak" DEĞİL, sadece
        ÇAKIŞMAMALARINI sağlamak; uzaktaki bir komponenti itmek ratsnest'i
        gereksiz uzatır.
      - **Kısıt kuvveti:** `MesafeKisiti` ihlal ediliyorsa ihlal miktarıyla
        orantılı ek bir çekme/itme uygulanır (yumuşak kısıt — sert kabul
        `kisitlari_dogrula()`'da ölçülür).
      - **Keepout (HighSpeedRuleManager, Bölüm 6):** `keepoutlar` verilmişse,
        courtyard-courtyard itmesinden AYRI bir SONSUZ itme davranışı
        uygulanır — bir komponentin normal kuvvet adımı onu bir keepout
        dairesinin içine sokacaksa, o adım o komponent için TAMAMEN
        REDDEDİLİR (eski konumunda kalır), yumuşak bir kuvvetle
        "yaklaşabilir ama biraz" DEĞİL. Gerekçe: yumuşak bir kuvvet, güçlü
        bir çekim (örn. yüksek ağırlıklı bir HS net) tarafından ezilebilir
        — tam olarak `_cakismalari_ayir()`'ın courtyard çakışması için
        zaten çözdüğü sorunun keepout karşılığı.

    Soğutma (cooling): adım boyu iterasyonla lineer azalır — salınım
    (oscillation) yerine yakınsama sağlar. `sabit=True` komponentler hiç
    hareket etmez ama diğerlerine kuvvet UYGULAR.
    """
    if not komponentler:
        return YerlesimSonucu({}, 0, False, 0.0, 0.0, 0.0)

    kenarlar = netlistten_graf_kur(netler)
    koordinatlar = baslangic_yerlesimi_uret(
        komponentler, kart_genisligi_mm, kart_yuksekligi_mm, baslangic_aci_offset_rad,
        baslangic_koordinatlari,
    )
    baslangic_ratsnest = ratsnest_uzunlugu_toplami(koordinatlar, kenarlar)

    ref_haritasi = {k.ref: k for k in komponentler}
    hareketli_refler = [k.ref for k in komponentler if not k.sabit]

    son_hareket = float("inf")
    iterasyon = 0
    for iterasyon in range(1, maks_iterasyon + 1):
        adim = baslangic_adimi_mm * (1.0 - (iterasyon - 1) / maks_iterasyon)
        kuvvetler: Dict[str, List[float]] = {r: [0.0, 0.0] for r in koordinatlar}

        # --- Çekim (ratsnest kenarları) ---
        for (a, b), w in kenarlar.items():
            if a not in koordinatlar or b not in koordinatlar:
                continue
            ax, ay = koordinatlar[a]
            bx, by = koordinatlar[b]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            if d < 1e-9:
                continue
            f = cekim_katsayisi * w * d
            ux, uy = dx / d, dy / d
            kuvvetler[a][0] += f * ux
            kuvvetler[a][1] += f * uy
            kuvvetler[b][0] -= f * ux
            kuvvetler[b][1] -= f * uy

        # --- İtme (courtyard çakışması) ---
        refler = list(koordinatlar.keys())
        for i in range(len(refler)):
            for j in range(i + 1, len(refler)):
                ra, rb = refler[i], refler[j]
                ka, kb = ref_haritasi[ra], ref_haritasi[rb]
                ax, ay = koordinatlar[ra]
                bx, by = koordinatlar[rb]
                dx, dy = bx - ax, by - ay
                d = math.hypot(dx, dy)
                min_mesafe = ka.yaricap_mm + kb.yaricap_mm
                if d >= min_mesafe:
                    continue
                if d < 1e-9:
                    # Tam üst üste: deterministik bir yöne ayır (indeks
                    # farkından türetilir; `random` YOK).
                    dx, dy, d = 1.0, 0.0, 1.0
                ortusme = min_mesafe - d
                f = itme_katsayisi * ortusme
                ux, uy = dx / d, dy / d
                kuvvetler[ra][0] -= f * ux
                kuvvetler[ra][1] -= f * uy
                kuvvetler[rb][0] += f * ux
                kuvvetler[rb][1] += f * uy

        # --- Yumuşak mm kısıtları (Aşama 3.3/3.5) ---
        for kisit in kisitlar:
            if kisit.ref_a not in koordinatlar or kisit.ref_b not in koordinatlar:
                continue
            ax, ay = koordinatlar[kisit.ref_a]
            bx, by = koordinatlar[kisit.ref_b]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            if d < 1e-9:
                continue
            ux, uy = dx / d, dy / d
            f = 0.0
            if kisit.maks_mm is not None and d > kisit.maks_mm:
                f = +(d - kisit.maks_mm)          # çek
            elif kisit.min_mm is not None and d < kisit.min_mm:
                f = -(kisit.min_mm - d)           # it
            if f != 0.0:
                kuvvetler[kisit.ref_a][0] += f * ux
                kuvvetler[kisit.ref_a][1] += f * uy
                kuvvetler[kisit.ref_b][0] -= f * ux
                kuvvetler[kisit.ref_b][1] -= f * uy

        # --- Konum güncelleme (sadece hareketliler) + kart içine kırpma ---
        son_hareket = 0.0
        for ref in hareketli_refler:
            fx, fy = kuvvetler[ref]
            buyukluk = math.hypot(fx, fy)
            if buyukluk < 1e-12:
                continue
            olcek = min(adim, buyukluk) / buyukluk
            x, y = koordinatlar[ref]
            yeni_x = x + fx * olcek
            yeni_y = y + fy * olcek
            k = ref_haritasi[ref]
            # Komponentin courtyard'ı kart dışına taşmasın (Aşama 3.1).
            yeni_x = min(max(yeni_x, k.genislik_mm / 2.0), kart_genisligi_mm - k.genislik_mm / 2.0)
            yeni_y = min(max(yeni_y, k.yukseklik_mm / 2.0), kart_yuksekligi_mm - k.yukseklik_mm / 2.0)
            if keepoutlar and _keepout_ihlali_mi(ref, yeni_x, yeni_y, k, keepoutlar):
                # SONSUZ itme: yumuşak kuvvet yerine adımın TAMAMI reddedilir,
                # komponent bu iterasyonda eski konumunda kalır (bkz. yukarı
                # docstring notu ve HighSpeedRuleManager, Bölüm 6).
                continue
            son_hareket = max(son_hareket, math.hypot(yeni_x - x, yeni_y - y))
            koordinatlar[ref] = (yeni_x, yeni_y)

        # Çakışmama kuvvet dengesine bırakılmaz, geometrik olarak zorlanır.
        _cakismalari_ayir(koordinatlar, ref_haritasi, kart_genisligi_mm, kart_yuksekligi_mm)

        if son_hareket < yakinsama_esigi_mm:
            break

    return YerlesimSonucu(
        koordinatlar={r: (round(x, 4), round(y, 4)) for r, (x, y) in koordinatlar.items()},
        iterasyon=iterasyon,
        yakinsadi_mi=son_hareket < yakinsama_esigi_mm,
        son_hareket_mm=round(son_hareket, 6),
        baslangic_ratsnest_mm=round(baslangic_ratsnest, 4),
        son_ratsnest_mm=round(ratsnest_uzunlugu_toplami(koordinatlar, kenarlar), 4),
    )


# ------------------------------------------------------------------
# 3b. HİYERARŞİK (AŞAMALI) YERLEŞİM — main.py Faz 4 orkestrasyonu
# ------------------------------------------------------------------

def hiyerarsik_yerlesim_coz(
    komponentler: Sequence[Komponent],
    kategoriler: Dict[str, YerlesimKategorisi],
    netler: Sequence[Net],
    kart_genisligi_mm: float,
    kart_yuksekligi_mm: float,
    kisitlar: Sequence[MesafeKisiti] = (),
    **kwargs,
) -> YerlesimSonucu:
    """`yerlesim_coz()`'ü ZORUNLU 3 aşamalı hiyerarşiyle (güç/dekuplaj ->
    kritik HS/diferansiyel -> düşük hızlı I/O) çalıştırır.

    Her aşama bir ÖNCEKİ aşamada yerleşmiş komponentleri `sabit=True`
    KİLİTLER (o komponentler artık hareket etmez ama yeni aşamanın
    komponentlerine kuvvet uygulamaya devam eder) — yerleşim rastgele
    sırada değil, MASTER_RULEBOOK'un "Akış Öncelikli Yerleşim ve Hiyerarşik
    Routing" kuralına göre yapılır (Gerekçe: kör/sırasız yerleşim/routing
    süreçlerinde yoğunluk duvarı, kilitlenme ve kısa devre patolojileri
    yaşanır — bkz. bu oturumun `bulk_lowspeed_router.py` deneyimi).

    `kategoriler` içinde ADI OLMAYAN komponentler (örn. sabit konnektörler)
    HER aşamada zaten-sabit kabul edilir; `k.sabit=True` olanlar zaten
    hiçbir aşamada hareket etmez (motorun kendi kuralı, burada bozulmaz).
    """
    kilitli: Dict[str, Tuple[float, float]] = {}
    son_sonuc: Optional[YerlesimSonucu] = None
    dahil_kategoriler: List[YerlesimKategorisi] = []

    for kategori in _HIYERARSI_SIRASI:
        dahil_kategoriler.append(kategori)
        asama_komponentleri: List[Komponent] = []
        for k in komponentler:
            if k.sabit:
                asama_komponentleri.append(k)
            elif k.ref in kilitli:
                x, y = kilitli[k.ref]
                asama_komponentleri.append(
                    Komponent(k.ref, k.genislik_mm, k.yukseklik_mm, x, y, sabit=True)
                )
            elif kategoriler.get(k.ref) in dahil_kategoriler:
                asama_komponentleri.append(k)
            # else: bu komponentin sırası henüz gelmedi -> bu aşamaya DAHİL EDİLMEZ

        if not asama_komponentleri:
            continue
        sonuc = yerlesim_coz(
            asama_komponentleri, netler, kart_genisligi_mm, kart_yuksekligi_mm, kisitlar, **kwargs
        )
        for ref, xy in sonuc.koordinatlar.items():
            if kategoriler.get(ref) == kategori:
                kilitli[ref] = xy
        son_sonuc = sonuc

    if son_sonuc is None:
        return YerlesimSonucu({}, 0, False, 0.0, 0.0, 0.0)

    tum_koordinatlar: Dict[str, Tuple[float, float]] = dict(kilitli)
    for k in komponentler:
        if k.ref not in tum_koordinatlar:
            tum_koordinatlar[k.ref] = (k.x, k.y)  # sabit ama hiç aşamaya girmemiş olabilir

    kenarlar = netlistten_graf_kur(netler)
    return YerlesimSonucu(
        koordinatlar={r: (round(x, 4), round(y, 4)) for r, (x, y) in tum_koordinatlar.items()},
        iterasyon=son_sonuc.iterasyon,
        yakinsadi_mi=son_sonuc.yakinsadi_mi,
        son_hareket_mm=son_sonuc.son_hareket_mm,
        baslangic_ratsnest_mm=son_sonuc.baslangic_ratsnest_mm,
        son_ratsnest_mm=round(ratsnest_uzunlugu_toplami(tum_koordinatlar, kenarlar), 4),
    )


def termal_kisitlarini_uret(
    termal_durumlar: Sequence[KomponentTermalDurumu],
    yuzeyler: Sequence[TermalTemasBolgesi],
    maks_mesafe_mm: float = 3.0,
) -> Tuple[List[Komponent], List[MesafeKisiti]]:
    """Faz 4b'nin (`ecad_mcad_termal_kopru.py`) termal keepout bulgusunu,
    yerleşim motoruna GERÇEK bir GİRDİYE (`MesafeKisiti`) çevirir — ayrı,
    ondan habersiz bir sonraki adım OLARAK DEĞİL.

    Her komponent, kendi kasa termal temas yüzeyinin (`TermalTemasBolgesi`)
    İÇİNDEYSE (`soguturucu_yuzey_bul` ile bulunur): o yüzeyin poligon
    merkezinde SABİT (hareket etmeyen) sentetik bir "termal çapa" komponenti
    üretilir ve gerçek komponentin ondan `maks_mesafe_mm`'den daha uzağa
    gitmemesini zorlayan bir `MesafeKisiti(maks_mm=...)` eklenir — yerleşim
    motoru artık ısı kaynağını kasa temasından uzaklaştırmaz.

    Kasa temas verisi paylaşılmayan (`termal_durumlar`/`yuzeyler` boş)
    komponentler için hiçbir kısıt/çapa üretilmez — sessizce "termal olarak
    güvenli" varsayılmaz, sadece bu fonksiyonun ürettiği ek girdi YOK olur.
    """
    ekstra_komponentler: List[Komponent] = []
    kisitlar: List[MesafeKisiti] = []
    for durum in termal_durumlar:
        yuzey = soguturucu_yuzey_bul(durum.x, durum.y, yuzeyler)
        if yuzey is None:
            continue
        merkez_x = sum(p[0] for p in yuzey.poligon) / len(yuzey.poligon)
        merkez_y = sum(p[1] for p in yuzey.poligon) / len(yuzey.poligon)
        capa_ref = f"_TERMAL_CAPA_{durum.yonetim.isim}"
        ekstra_komponentler.append(Komponent(capa_ref, 0.1, 0.1, merkez_x, merkez_y, sabit=True))
        kisitlar.append(MesafeKisiti(
            ref_a=durum.yonetim.isim, ref_b=capa_ref, maks_mm=maks_mesafe_mm,
            aciklama=f"Faz 4b termal keepout: {durum.yonetim.isim} kasa temas "
                     f"yüzeyi '{yuzey.isim}'den {maks_mesafe_mm}mm'den uzağa gitmemeli",
        ))
    return ekstra_komponentler, kisitlar


# ------------------------------------------------------------------
# 6. HIGHSPEEDRULEMANAGER — Yüksek Hızlı Sinyal / Diferansiyel Çift Koruması
# ------------------------------------------------------------------
#
# NEDEN BU BÖLÜM VAR (`.scratch/cm4_d4d7_test/d4d7_corridor_test.py`,
# 2026-08-04 bulgusu): cm4-io-test'in D4-D7 ESD kümesi üzerinde çalıştırılan
# bir tanı testi, motorun ratsnest'i minimize ederken D4-D7'yi (hepsi aynı
# iki sabit çapaya - J1 ve J6 - bağlı) courtyard çakışması ÇÖZÜLENE kadar
# birbirine yaklaştırdığını ama sonrasında ARADA gerçek routing için
# gereken koridoru AÇMADIĞINI ölçtü - motor "çakışma yok" hedefini bilir,
# "bu ikisinin arasında bir diferansiyel çiftin via-pair'i geçecek kadar yer
# olsun" hedefini BİLMEZ. Bu bölüm o eksik hedefi somut bir girdiye çevirir:
# yüksek hızlı/diferansiyel netleri otomatik tanır (A), onların yol
# güzergâhı etrafında 3W kuralına göre bir dışlama (keepout) bölgesi
# hesaplar (B), ve bu bölgeye giren HERHANGİ bir komponenti hem yumuşak
# yerleşim sırasında (yerlesim_coz'daki SONSUZ itme, yukarı bak) hem de
# sert kabul kapısında (C) reddeder.

YUKSEK_HIZLI_VARSAYILAN_AGIRLIK = 3.0  # Net.agirlik docstring'indeki ">1" ile tutarlı


def yuksek_hizli_net_mi(net_ismi: str, net_class: str = "") -> bool:
    """Net class'ı 'DIFF_90OHM' gibi bir diferansiyel-empedans sınıfıysa,
    VEYA net ismi _P/_N ile bitiyorsa (diferansiyel çift kuyruğu) VEYA
    isimde CSI/MIPI geçiyorsa True döner. False-positive'i azaltmak için
    _P/_N kontrolü net ismi en az 2 karakter uzunlukta bir gövdeye
    sahipse uygulanır (tek karakterli "P"/"N" gibi kazara eşleşmeleri
    önle)."""
    ad = net_ismi.strip().upper()
    sinif = net_class.strip().upper()
    if "DIFF" in sinif:
        return True
    if "CSI" in ad or "MIPI" in ad:
        return True
    if ad.endswith("_P") or ad.endswith("_N"):
        govde = ad[:-2]
        if len(govde) >= 2:
            return True
    return False


@dataclass
class YuksekHizKeepout:
    """Bir yüksek hızlı net için hesaplanmış dışlama bölgesi.

    `kaynak_ref`/`hedef_ref`: bu keepout'u üreten pin çiftinin kendisi -
    spesifikasyonda İSTENMEYEN ama gerekli bir ek alan (varsayılanı boş
    string, geriye dönük uyumlu): keepout'un KENDİ iki ucu (örn. D4 ve D6
    net TRD0/TRD2'nin kendi bağlantı noktalarıysa) bu keepout'a göre
    "ihlalci" SAYILMAMALI - bir net kendi başlangıç/bitiş komponentinin
    kendi koridoruna göre reddedilmesi anlamsız olurdu (koridor tam da o
    komponentin PİMİNDEN başlıyor). Bu iki alan olmadan `keepout_
    cakismasi_kontrolu`/`_keepout_ihlali_mi` her keepout'u kendi
    uçlarına karşı hemen (yanlışlıkla) ihlalli bulurdu.
    """

    net_ismi: str
    merkez_x_mm: float
    merkez_y_mm: float
    yaricap_mm: float   # 3W kuralına göre: iz genişliği * 3 + pad/track marjı
    kaynak_ref: str = ""
    hedef_ref: str = ""


_KEEPOUT_PAD_TRACK_MARJI_MM = 0.15  # 3W'nin üstüne eklenen sabit pad/track payı


def yuksek_hiz_keepout_hesapla(
    net: Net,
    koordinatlar: Dict[str, Tuple[float, float]],
    iz_genisligi_mm: float,
) -> List["YuksekHizKeepout"]:
    """Netin bağlı olduğu pin çiftleri arasında (henüz routed değilse
    uçtan uca, routed ise gerçek track segmentleri boyunca) 3W kuralına
    göre bir keepout listesi üretir.

    Bu fonksiyon henüz yerleşim aşamasında (routing öncesi) çağrıldığı
    için "routed ise gerçek segment" yolu burada YOKTUR - segment verisi
    olmadığında iki pin arasındaki DOĞRU ÇİZGİNİN ORTA NOKTASI kullanılır
    (uçtan uca hattın basitleştirilmiş temsili). Gerçek routed segment
    verisi ileride mevcut olduğunda bu fonksiyonun segment-bazlı bir
    varyantı (örn. `yuksek_hiz_keepout_hesapla_routed()`) eklenebilir -
    bu, mevcut imzayı BOZMADAN yapılacak ayrı bir ek olur.

    3W kuralının formülü YENİDEN İCAT EDİLMEDİ: `pcb_stackup_planner.py::
    iz_genisligi_hesapla_mm()` akım -> genişlik türetir (ters yön); burada
    genişlik zaten girdi olduğundan doğrudan `iz_genisligi_mm * 3` alınır,
    üstüne `pcb_highspeed_escape.py`'nin escape/trim toleranslarıyla aynı
    mertebede sabit bir pad/track marjı (0.15mm) eklenir.
    """
    if not yuksek_hizli_net_mi(net.isim):
        return []
    yaricap = iz_genisligi_mm * 3.0 + _KEEPOUT_PAD_TRACK_MARJI_MM
    benzersiz = sorted(set(net.baglantilar))
    keepoutlar: List[YuksekHizKeepout] = []
    for i in range(len(benzersiz)):
        for j in range(i + 1, len(benzersiz)):
            a, b = benzersiz[i], benzersiz[j]
            if a not in koordinatlar or b not in koordinatlar:
                continue
            ax, ay = koordinatlar[a]
            bx, by = koordinatlar[b]
            keepoutlar.append(YuksekHizKeepout(
                net_ismi=net.isim,
                merkez_x_mm=(ax + bx) / 2.0,
                merkez_y_mm=(ay + by) / 2.0,
                yaricap_mm=yaricap,
                kaynak_ref=a,
                hedef_ref=b,
            ))
    return keepoutlar


def _keepout_ihlali_mi(
    ref: str,
    x: float,
    y: float,
    komponent: Komponent,
    keepoutlar: Sequence["YuksekHizKeepout"],
) -> bool:
    """Tek bir (ref, x, y) konumunun HERHANGİ bir keepout'u ihlal edip
    etmediğini test eder - `keepout_cakismasi_kontrolu()` (toplu, sert
    kapı) ve `yerlesim_coz()`'ün SONSUZ itmesi (yumuşak yerleşim sırasında,
    her iterasyon) AYNI mantığı kullansın diye ortak bir yardımcı olarak
    çıkarıldı (DRY - iki yerde ayrı ayrı yanlış senkronize kalma riski
    olmasın)."""
    for keepout in keepoutlar:
        if ref in (keepout.kaynak_ref, keepout.hedef_ref):
            continue  # netin kendi uç noktası - bkz. YuksekHizKeepout docstring'i
        mesafe = math.hypot(x - keepout.merkez_x_mm, y - keepout.merkez_y_mm)
        if mesafe < komponent.yaricap_mm + keepout.yaricap_mm:
            return True
    return False


def keepout_cakismasi_kontrolu(
    koordinatlar: Dict[str, Tuple[float, float]],
    komponentler: Dict[str, "Komponent"],
    keepoutlar: List["YuksekHizKeepout"],
) -> List[str]:
    """Her komponentin courtyard dairesi (`Komponent.yaricap_mm`) ile her
    keepout dairesi arasındaki mesafe, iki yarıçapın toplamından küçükse,
    o komponent referansını ihlal listesine ekler.

    Not: bu fonksiyon (spesifikasyonu gereği) eski `List[str]` sözleşmesini
    kullanır - `bulgu_sozlesmesi.Bulgu`'ya SARILMASI
    `yuksek_hiz_keepout_kontrolu()` (aşağıda) tarafından yapılır; bu ayrım
    `cakisma_kontrolu()`/`kisitlari_dogrula()`'nın kendi Bulgu sözleşmesini
    DEĞİŞTİRMEDEN yeni bir "yuksek_hiz_keepout_ihlali" ihlal tipini onların
    YANINA (yerine değil) eklemeyi mümkün kılar.
    """
    ihlaller: List[str] = []
    for ref, komponent in komponentler.items():
        if ref not in koordinatlar:
            continue
        x, y = koordinatlar[ref]
        if _keepout_ihlali_mi(ref, x, y, komponent, keepoutlar):
            ihlaller.append(ref)
    return ihlaller


def yuksek_hiz_keepout_kontrolu(
    koordinatlar: Dict[str, Tuple[float, float]],
    komponentler: Dict[str, Komponent],
    keepoutlar: Sequence["YuksekHizKeepout"],
) -> Bulgu:
    """`keepout_cakismasi_kontrolu()`'nu `bulgu_sozlesmesi.Bulgu`
    sözleşmesine sarar - `cakisma_kontrolu()`/`kisitlari_dogrula()`'nın
    YANINA çağrılacak, kendi başına SERT bir kabul kapısı (`main.py`'nin
    Faz 4 gate sırasına, mevcut ikisini DEĞİŞTİRMEDEN eklenir).
    """
    ihlal_refleri = keepout_cakismasi_kontrolu(koordinatlar, komponentler, list(keepoutlar))
    return bulgu_uret(
        "yuksek_hiz_keepout_ihlali",
        taranan=len(komponentler),
        ihlaller=[{"ref": r} for r in ihlal_refleri],
        detay=f"{len(keepoutlar)} yüksek hızlı keepout bölgesine karşı "
              f"{len(komponentler)} komponent test edildi (3W kuralı)",
    )


# ------------------------------------------------------------------
# 7. ÇOKLU YERLEŞİM SEÇENEĞİ + SKORLAMA (FAZ 0.5)
# ------------------------------------------------------------------
#
# NEDEN BU BÖLÜM VAR: force-directed motor TEK bir yerel minimuma yakınsar
# (başlangıç açısı/kuvvet katsayıları sabitse HER ZAMAN AYNI yerel minimum —
# bu determinizmin doğal sonucu). Ama "iyi bir yerleşim" tek bir sayıya
# (ratsnest uzunluğu) indirgenemez — keepout ihlali, termal risk, HS net
# kompaktlığı da önemlidir. Bu bölüm, aynı netlist'i FARKLI parametre
# setleriyle (hâlâ HER BİRİ kendi içinde tam deterministik — `random`
# HİÇBİR YERDE kullanılmaz) N kez çözüp çok-boyutlu bir skorla sıralar.

@dataclass
class YerlesimParametreSeti:
    """Bir yerleşim DENEMESİ için parametre demeti — `coklu_yerlesim_dene()`
    aynı netlist'i bu demetlerin HER BİRİYLE ayrı ayrı çözer."""

    isim: str
    cekim_katsayisi: float = 0.08
    itme_katsayisi: float = 1.0
    baslangic_adimi_mm: float = 2.0
    baslangic_aci_offset_rad: float = 0.0


# 4 varsayılan deneme: standart, güçlü çekim (daha sıkı kümeleme), güçlü
# itme (daha ferah/az çakışma riski), farklı başlangıç açısı (spiral
# offset — motor farklı bir yerel minimuma inebilir). Çağıran taraf
# kendi setini de verebilir; bunlar sadece "hiç düşünmeden N dene"
# isteyen bir çağıran için makul bir varsayılandır.
VARSAYILAN_PARAMETRE_SETLERI: Tuple[YerlesimParametreSeti, ...] = (
    YerlesimParametreSeti("standart", cekim_katsayisi=0.08, itme_katsayisi=1.0),
    YerlesimParametreSeti("guclu_cekim", cekim_katsayisi=0.16, itme_katsayisi=1.0),
    YerlesimParametreSeti("guclu_itme", cekim_katsayisi=0.08, itme_katsayisi=2.0),
    YerlesimParametreSeti("farkli_baslangic", cekim_katsayisi=0.08, itme_katsayisi=1.0,
                           baslangic_aci_offset_rad=math.pi / 3.0),
)


@dataclass
class YerlesimSkoru:
    parametre_seti_ismi: str
    toplam_skor: float
    ratsnest_mm: float
    keepout_ihlal_sayisi: int
    termal_yayilim_skoru: float
    hs_kompaktlik_skoru: float


def yerlesim_skoru(
    sonuc: YerlesimSonucu,
    netler: Sequence[Net],
    komponentler: Sequence[Komponent] = (),
    keepoutlar: Sequence["YuksekHizKeepout"] = (),
    termal_kisitlar: Sequence[MesafeKisiti] = (),
    parametre_seti_ismi: str = "",
    agirlik_ratsnest: float = 1.0,
    agirlik_keepout: float = 50.0,
    agirlik_termal: float = 1.0,
    agirlik_hs_kompaktlik: float = 1.0,
) -> YerlesimSkoru:
    """Bir yerleşim SONUCUNU tek bir sayıya indirger — DÜŞÜK = İYİ.
    `coklu_yerlesim_dene()`'nin "en iyi" seçimi bu skora göre yapılır.

    Bileşenler:
      - **ratsnest_mm**: `sonuc.son_ratsnest_mm` (zaten ağırlıklı toplam
        hava-hattı) — doğrudan kullanılır.
      - **keepout_ihlal_sayisi**: `keepout_cakismasi_kontrolu()` ihlal
        sayısı — varsayılan katsayı (50x) BİLEREK AĞIRDIR: bu SERT bir
        kabul kriteridir (Bölüm 6), "biraz ihlal" diye bir kategori YOKTUR,
        skor bunu yansıtmalı.
      - **termal_yayilim_skoru**: `termal_kisitlar` (ör.
        `termal_kisitlarini_uret()`'ten) verilmişse, HER kısıtın GERÇEK
        mesafesinin `maks_mm`'e ORANI toplanır (1.0'a yakın/üstü = riskli).
        SINIR: bu GERÇEK bir termal simülasyon DEĞİLDİR — sadece Faz 4b'nin
        kendi mm kısıtına göre "ne kadar sınırda" kaldığını ölçer (bkz.
        FAZ 0.5-4, `ecad_mcad_termal_kopru.py`'deki RθJA hesabı bu skoru
        İLERİDE daha doğru bir termal veriyle besleyebilir, şu an İÇİN
        BAĞLI DEĞİL).
      - **hs_kompaktlik_skoru**: her yüksek-hızlı net grubunun kendi
        bounding-box köşegeni toplanır — küçük köşegen "kompakt/kolay
        yönlendirilebilir" demektir.

    Toplam skor ağırlıklı TOPLAMDIR (düşük = iyi).
    """
    ihlal_sayisi = 0
    if keepoutlar and komponentler:
        komponent_haritasi = {k.ref: k for k in komponentler}
        ihlal_sayisi = len(
            keepout_cakismasi_kontrolu(sonuc.koordinatlar, komponent_haritasi, list(keepoutlar))
        )

    termal_skoru = 0.0
    for kisit in termal_kisitlar:
        if kisit.maks_mm is None:
            continue
        if kisit.ref_a not in sonuc.koordinatlar or kisit.ref_b not in sonuc.koordinatlar:
            continue
        ax, ay = sonuc.koordinatlar[kisit.ref_a]
        bx, by = sonuc.koordinatlar[kisit.ref_b]
        d = math.hypot(ax - bx, ay - by)
        termal_skoru += d / kisit.maks_mm

    hs_kompaktlik = 0.0
    for net in netler:
        if not yuksek_hizli_net_mi(net.isim):
            continue
        pinler = [p for p in sorted(set(net.baglantilar)) if p in sonuc.koordinatlar]
        if len(pinler) < 2:
            continue
        xs = [sonuc.koordinatlar[p][0] for p in pinler]
        ys = [sonuc.koordinatlar[p][1] for p in pinler]
        hs_kompaktlik += math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    toplam = (
        agirlik_ratsnest * sonuc.son_ratsnest_mm
        + agirlik_keepout * ihlal_sayisi
        + agirlik_termal * termal_skoru
        + agirlik_hs_kompaktlik * hs_kompaktlik
    )
    return YerlesimSkoru(
        parametre_seti_ismi=parametre_seti_ismi,
        toplam_skor=round(toplam, 4),
        ratsnest_mm=sonuc.son_ratsnest_mm,
        keepout_ihlal_sayisi=ihlal_sayisi,
        termal_yayilim_skoru=round(termal_skoru, 4),
        hs_kompaktlik_skoru=round(hs_kompaktlik, 4),
    )


@dataclass
class CokluYerlesimSonucu:
    en_iyi_isim: str
    en_iyi_sonuc: YerlesimSonucu
    tum_sonuclar: Dict[str, YerlesimSonucu]
    tum_skorlar: Dict[str, YerlesimSkoru]


def coklu_yerlesim_dene(
    komponentler: Sequence[Komponent],
    netler: Sequence[Net],
    kart_genisligi_mm: float,
    kart_yuksekligi_mm: float,
    kisitlar: Sequence[MesafeKisiti] = (),
    keepoutlar: Sequence["YuksekHizKeepout"] = (),
    termal_kisitlar: Sequence[MesafeKisiti] = (),
    parametre_setleri: Sequence[YerlesimParametreSeti] = VARSAYILAN_PARAMETRE_SETLERI,
    **ortak_kwargs,
) -> CokluYerlesimSonucu:
    """Aynı netlist'i `parametre_setleri`'ndeki HER parametre demetiyle AYRI
    AYRI çözer — HER biri kendi içinde TAM DETERMİNİSTİKTİR (aynı parametre
    seti + aynı netlist -> HER ZAMAN aynı sonuç, `random` hiçbir yerde
    kullanılmaz); `parametre_setleri` arasında ÇEŞİTLİLİK vardır (bu, motoru
    farklı yerel minimumlara yönlendirir), rastgelelik YOKTUR.

    `yerlesim_skoru()` ile HER sonuç puanlanır, EN DÜŞÜK skor (en iyi)
    önerilir — ama TÜM sonuçlar (skorlarıyla) `tum_sonuclar`/`tum_skorlar`
    içinde döner: "tek cevap" dayatılmaz, çağıran taraf (insan/ajan) neden
    A yerine B'nin önerildiğini görebilir.
    """
    if not parametre_setleri:
        raise ValueError("en az bir parametre seti verilmeli")

    tum_sonuclar: Dict[str, YerlesimSonucu] = {}
    tum_skorlar: Dict[str, YerlesimSkoru] = {}
    for pset in parametre_setleri:
        sonuc = yerlesim_coz(
            komponentler, netler, kart_genisligi_mm, kart_yuksekligi_mm, kisitlar,
            cekim_katsayisi=pset.cekim_katsayisi,
            itme_katsayisi=pset.itme_katsayisi,
            baslangic_adimi_mm=pset.baslangic_adimi_mm,
            baslangic_aci_offset_rad=pset.baslangic_aci_offset_rad,
            keepoutlar=keepoutlar,
            **ortak_kwargs,
        )
        skor = yerlesim_skoru(
            sonuc, netler, komponentler, keepoutlar=keepoutlar,
            termal_kisitlar=termal_kisitlar, parametre_seti_ismi=pset.isim,
        )
        tum_sonuclar[pset.isim] = sonuc
        tum_skorlar[pset.isim] = skor

    en_iyi_isim = min(tum_skorlar, key=lambda isim: tum_skorlar[isim].toplam_skor)
    return CokluYerlesimSonucu(
        en_iyi_isim=en_iyi_isim,
        en_iyi_sonuc=tum_sonuclar[en_iyi_isim],
        tum_sonuclar=tum_sonuclar,
        tum_skorlar=tum_skorlar,
    )


# ------------------------------------------------------------------
# 4. SERT KABUL KAPILARI (Bulgu sözleşmesiyle)
# ------------------------------------------------------------------

def cakisma_kontrolu(
    komponentler: Sequence[Komponent],
    koordinatlar: Dict[str, Tuple[float, float]],
) -> Bulgu:
    """Courtyard'lar (dikdörtgen, AABB) çakışıyor mu — SERT kapı.

    Motorun itme kuvveti çakışmayı AZALTIR ama GARANTİ ETMEZ (yakınsama
    yerel bir minimumda durabilir). Bu yüzden ayrı, kesin bir geometri
    testi ZORUNLUDUR — `mcp__kicad__check_courtyard_overlaps` ile aynı
    amaç, ama yerleşim henüz PCB'ye yazılmadan önce.
    """
    ref_haritasi = {k.ref: k for k in komponentler}
    refler = [r for r in koordinatlar if r in ref_haritasi]
    ihlaller: List[Dict[str, object]] = []
    for i in range(len(refler)):
        for j in range(i + 1, len(refler)):
            ra, rb = refler[i], refler[j]
            ka, kb = ref_haritasi[ra], ref_haritasi[rb]
            ax, ay = koordinatlar[ra]
            bx, by = koordinatlar[rb]
            ortusme_x = (ka.genislik_mm + kb.genislik_mm) / 2.0 - abs(ax - bx)
            ortusme_y = (ka.yukseklik_mm + kb.yukseklik_mm) / 2.0 - abs(ay - by)
            if ortusme_x > 0 and ortusme_y > 0:
                ihlaller.append({
                    "a": ra, "b": rb,
                    "ortusme_x_mm": round(ortusme_x, 4),
                    "ortusme_y_mm": round(ortusme_y, 4),
                })
    return bulgu_uret(
        "courtyard_cakismasi",
        taranan=len(refler),
        ihlaller=ihlaller,
        detay=f"{len(refler)} komponent çifti bazında AABB çakışma testi",
    )


def kisitlari_dogrula(
    kisitlar: Sequence[MesafeKisiti],
    koordinatlar: Dict[str, Tuple[float, float]],
) -> Bulgu:
    """`pcb-layout` Aşama 3.3/3.5 mm kısıtlarını ÖLÇER (yumuşak kuvvet değil,
    sert kabul kriteri).

    Motor yakınsasa bile bir kısıt ihlal kalmış olabilir; bu fonksiyon o
    ihlali sayı olarak raporlar. Kısıt listesi BOŞSA `KAPSAM_YOK` döner —
    "hiç kısıt vermedim" sessizce "kısıtlar sağlandı" sayılamaz
    (`bulgu_sozlesmesi.py`'nin var oluş nedeni).
    """
    ihlaller: List[Dict[str, object]] = []
    taranan = 0
    for kisit in kisitlar:
        if kisit.ref_a not in koordinatlar or kisit.ref_b not in koordinatlar:
            continue
        taranan += 1
        ax, ay = koordinatlar[kisit.ref_a]
        bx, by = koordinatlar[kisit.ref_b]
        d = math.hypot(ax - bx, ay - by)
        if kisit.maks_mm is not None and d > kisit.maks_mm:
            ihlaller.append({
                "kisit": f"{kisit.ref_a}-{kisit.ref_b}", "tip": "maks",
                "hedef_mm": kisit.maks_mm, "olculen_mm": round(d, 4),
                "aciklama": kisit.aciklama,
            })
        if kisit.min_mm is not None and d < kisit.min_mm:
            ihlaller.append({
                "kisit": f"{kisit.ref_a}-{kisit.ref_b}", "tip": "min",
                "hedef_mm": kisit.min_mm, "olculen_mm": round(d, 4),
                "aciklama": kisit.aciklama,
            })
    return bulgu_uret(
        "mesafe_kisitlari",
        taranan=taranan,
        ihlaller=ihlaller,
        detay="pcb-layout Aşama 3.3/3.5 mm kısıtlarının ölçümü",
    )


def yerlesim_raporu_uret(
    sonuc: YerlesimSonucu,
    kumeler: Sequence[Sequence[str]],
    bulgular: Sequence[Bulgu],
) -> str:
    """İnsan tarafından okunabilir Markdown özet (TEST/ dizinine yazılmak
    üzere — MASTER_RULEBOOK Bölüm 0'ın "her hesap raporlanır" kuralı)."""
    satirlar = [
        "# Force-Directed Yerleşim Raporu",
        "",
        f"- İterasyon: {sonuc.iterasyon}",
        f"- Yakınsadı mı: {'EVET' if sonuc.yakinsadi_mi else 'HAYIR (maks iterasyona takıldı)'}",
        f"- Ratsnest (ağırlıklı): {sonuc.baslangic_ratsnest_mm}mm -> "
        f"{sonuc.son_ratsnest_mm}mm (iyileşme %{sonuc.iyilesme_orani * 100:.1f})",
        "",
        "## Kümeler (ratsnest bazlı — pcb-layout Aşama 3.0)",
    ]
    for i, kume in enumerate(kumeler, 1):
        satirlar.append(f"{i}. {', '.join(kume)}")
    satirlar += ["", "## Kapılar", ""]
    for b in bulgular:
        satirlar.append(
            f"- **{b.kontrol}**: {b.durum.value} (taranan={b.taranan}, "
            f"ihlal={len(b.ihlaller)})"
        )
    satirlar += [
        "",
        "> UYARI: Bu bir TOHUM yerleşimdir. `mekanik_dxf_koprusu.py::z_kontrolu_yap()`",
        "> (3D/kasa keepout) ve `pcb-layout` Aşama 3.1-3.5 kuralları ayrıca",
        "> koşturulmadan bu yerleşim onaylanmış sayılmaz.",
    ]
    return "\n".join(satirlar) + "\n"


# ------------------------------------------------------------------
# 5. ÖZ-TEST (fault-injection dahil) — empedans_cozucu.py desenindeki gibi
# ------------------------------------------------------------------

def _testin_bos_olmadigini_kanitla() -> bool:
    """FAULT INJECTION: çekim katsayısını 0 yaparsak motor ratsnest'i
    İYİLEŞTİREMEMELİ. Bu, `iyilesme_orani` testinin gerçekten bir şey
    ölçtüğünün kanıtıdır (yoksa test her koşulda geçerdi).

    `empedans_cozucu.py::_testin_bos_olmadigini_kanitla()` ile aynı disiplin.
    """
    komponentler = [Komponent(f"U{i}", 2.0, 2.0) for i in range(6)]
    netler = [Net("SIG", ["U0", "U5"]), Net("SIG2", ["U1", "U4"])]
    bozuk = yerlesim_coz(komponentler, netler, 50.0, 50.0, cekim_katsayisi=0.0)
    return bozuk.iyilesme_orani < 0.01


def oz_testleri_calistir() -> List[str]:
    """Modülün kendi kendini doğrulaması; hata mesajı listesi döner (boş = PASS)."""
    hatalar: List[str] = []

    # 1. Determinizm: aynı girdi -> aynı çıktı
    komponentler = [Komponent(f"U{i}") for i in range(8)]
    netler = [Net("A", ["U0", "U1"]), Net("B", ["U2", "U3", "U4"])]
    s1 = yerlesim_coz(komponentler, netler, 40.0, 40.0)
    s2 = yerlesim_coz([Komponent(f"U{i}") for i in range(8)], netler, 40.0, 40.0)
    if s1.koordinatlar != s2.koordinatlar:
        hatalar.append("determinizm ihlali: aynı netlist iki farklı yerleşim üretti")

    # 2. Motor ratsnest'i gerçekten kısaltıyor mu
    if s1.iyilesme_orani <= 0.0:
        hatalar.append("motor ratsnest uzunluğunu iyileştirmedi")

    # 3. Fault injection gerçekten kırılıyor mu
    if not _testin_bos_olmadigini_kanitla():
        hatalar.append("fault-injection kırılmadı: iyileşme testi boş olabilir")

    # 4. Güç netleri grafiğe girmemeli
    if netlistten_graf_kur([Net("GND", ["U0", "U1", "U2"])]):
        hatalar.append("GND neti grafiğe dahil edildi (düzlem olmalı)")

    return hatalar


if __name__ == "__main__":
    sorunlar = oz_testleri_calistir()
    if sorunlar:
        for s in sorunlar:
            print(f"FAIL: {s}")
        raise SystemExit(1)
    print("PASS: kuvvet_yonelimli_yerlesim.py öz testleri temiz.")
