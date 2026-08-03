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
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret

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
        pay = net.agirlik / (len(benzersiz) - 1)
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
) -> Dict[str, Tuple[float, float]]:
    """Altın-açı (Vogel) spirali ile DETERMİNİSTİK başlangıç yerleşimi.

    `random` KULLANILMAZ (modül başlığındaki determinizm notu). Vogel
    spirali, noktaları kart alanına düzgün (kümelenmesiz) dağıtır — bu,
    force-directed motorun ilk iterasyonlarında yapay bir "her şey üst üste"
    itme patlaması yaşamamasını sağlar.

    `sabit=True` komponentlerin mevcut (x, y)'si KORUNUR — onlar kasa/mekanik
    kısıtından geliyor, spiral onları ezmez.
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
    for i, k in enumerate(hareketliler):
        r = maks_r * math.sqrt((i + 0.5) / n)
        aci = i * ALTIN_ACI_RAD
        koordinatlar[k.ref] = (
            merkez_x + r * math.cos(aci),
            merkez_y + r * math.sin(aci),
        )
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

    Soğutma (cooling): adım boyu iterasyonla lineer azalır — salınım
    (oscillation) yerine yakınsama sağlar. `sabit=True` komponentler hiç
    hareket etmez ama diğerlerine kuvvet UYGULAR.
    """
    if not komponentler:
        return YerlesimSonucu({}, 0, False, 0.0, 0.0, 0.0)

    kenarlar = netlistten_graf_kur(netler)
    koordinatlar = baslangic_yerlesimi_uret(komponentler, kart_genisligi_mm, kart_yuksekligi_mm)
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
