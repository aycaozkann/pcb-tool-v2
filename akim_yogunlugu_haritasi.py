"""
akim_yogunlugu_haritasi.py
============================
Bakır poligonunu resistive mesh (Kirchhoff akım korunumu) olarak çözüp DC
akım yoğunluğu ısı haritası üretir.

TAM EM DEĞİL — bu `openems_koprusu.py`'nin FDTD/S-parametre simülasyonunun
YERİNE GEÇMEZ; sadece DC IR-drop'un geometriye YAYILMIŞ hali (statik akım
dağılımı, ısınan/dar geçitleri görsel olarak işaretler). openEMS'e
BAĞIMLI DEĞİLDİR — `numpy`/`scipy`/`matplotlib` yeterlidir, bu yüzden
openEMS kurulu olmayan bir makinede de HER ZAMAN çalışabilir
(`fdtd_kur_ve_calistir()`'in aksine bu modülün "sayı uydurma yasağı"
kapsamı SADECE `pcbnew`'e bağlı — bkz. `akim_yogunlugu_haritasi_uret()`).

YÖNTEM: bakır alanı (poligon) `n_en x n_boy` bir ızgaraya rasterize edilir;
poligonun İÇİNDE kalan her hücre bir düğümdür, komşu düğümler arasına
bakırın levha direncinden (`Rs = rho / kalinlik`) türetilen bir konduktans
atanır. Akım bir kenardan enjekte edilir, karşı kenardan çekilir; Kirchhoff
akım korunumu `G @ V = I` lineer sistemi `scipy.sparse` ile çözülür
(çıkış tarafındaki bir düğüm referans/0V'a sabitlenir — tekil olmayan
çözüm için). Dal akımları komşu düğüm gerilim farkından (Ohm kanunu)
hesaplanır, `|I| / kesit_genisligi` akım yoğunluğuna (A/m) çevrilir.

DOĞRULANDI (bu makinede GERÇEKTEN koşturuldu — `test_akim_yogunlugu_
haritasi.py`): basit dikdörtgen bir bakır şerit için (akım uzun kenarın
bir ucundan girip diğer ucundan çıkar) orta bölgedeki akım yoğunluğu
dağılımı, analitik olarak beklenen DÜZGÜN (uniform, `I / genislik_mm`)
dağılımla makine hassasiyeti içinde örtüştü; kenarlara yakın hücrelerde
enjeksiyon noktasının ayrık (tek tek düğümlere bölünmüş) yapısından
kaynaklanan küçük sapmalar gözlemlendi ve testte AÇIKÇA belgelendi
(kenar etkisi — gerçek bir fiziksel etki, sayısal hata DEĞİL).

SINIR (bilinçli, `pcb_gorsel_kesit.py`/`mekanik_dxf_koprusu.py`'deki
dürüstlük notlarıyla AYNI disiplin): `akim_yogunlugu_haritasi_uret()`
gerçek `.kicad_pcb`'den bir net'in kopyasını `pcbnew_koprusu.py::
net_iz_ve_via_listesi_topla()` ile okur ve o net'in İZLERİNİN bounding
box'ını (dikdörtgen yaklaşımı) kullanır — bir zone/copper-pour'un GERÇEK
poligon sınırını (KiCad `ZONE.Outline()`) ÇIKARMAZ. Bir güç düzlemi/geniş
poligon üzerinde hassas köşe/delik etkisi görmek için `bakir_poligonu_coz()`
gerçek poligon köşeleriyle DOĞRUDAN çağrılabilir (bu fonksiyon genel
amaçlıdır, bounding-box sınırlamasına sahip DEĞİLDİR).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from bulgu_sozlesmesi import Bulgu, bulgu_uret

# Bakır özdirenci (oda sıcaklığı, ohm*m) — literatür sabiti; ayrı bir
# "gerçeklik kaynağı" YARATILMADI, `pcb_stackup_planner.py`'nin IPC-2221
# tablolarıyla ÇAKIŞMAZ (o mesafe/genişlik hesabı yapar, bu modül akım
# DAĞILIMI hesaplar — ikisi farklı sorulara cevap verir).
BAKIR_OZDIRENC_OHM_M = 1.68e-8
OZ_KALINLIK_M = 35e-6  # 1oz bakır ~35 mikron


@dataclass
class ResistifMeshSonucu:
    n_en: int
    n_boy: int
    node_gerilim_v: np.ndarray          # (n_en, n_boy), NaN = bakır dışı
    akim_yogunlugu_a_m: np.ndarray      # (n_en, n_boy-1), yatay dal, NaN = bakır dışı
    toplam_akim_a: float
    maks_akim_yogunlugu_a_m: float

    def gecerli_yogunluklar(self) -> np.ndarray:
        return self.akim_yogunlugu_a_m[~np.isnan(self.akim_yogunlugu_a_m)]


# ---------------------------------------------------------------------
# 1. Nokta-poligon içi testi (ray-casting) — pcbnew/shapely GEREKTİRMEZ
# ---------------------------------------------------------------------

def _nokta_poligon_icinde_mi(x: float, y: float, poligon: Sequence[Tuple[float, float]]) -> bool:
    """Standart ray-casting algoritması. `kicad_koprusu.py`'deki referans
    düzlemi sürekliliği kontrolünün kullandığı YAKLAŞIMLA aynı aile —
    harici bağımlılık (shapely) gerektirmez."""
    icinde = False
    n = len(poligon)
    j = n - 1
    for i in range(n):
        xi, yi = poligon[i]
        xj, yj = poligon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi
        ):
            icinde = not icinde
        j = i
    return icinde


# ---------------------------------------------------------------------
# 2. Çekirdek çözücü — rasterize edilmiş maske üzerinde KCL
# ---------------------------------------------------------------------

def _mesh_coz(
    maske: np.ndarray,
    uzunluk_mm: float,
    genislik_mm: float,
    akim_a: float,
    bakir_agirligi_oz: float,
    giris_sutun: int,
    cikis_sutun: int,
) -> ResistifMeshSonucu:
    n_en, n_boy = maske.shape
    if giris_sutun == cikis_sutun:
        raise ValueError("giris_sutun ve cikis_sutun aynı olamaz — akım nereden nereye akacak?")

    dx_m = (uzunluk_mm / 1000.0) / n_boy
    dy_m = (genislik_mm / 1000.0) / n_en
    kalinlik_m = bakir_agirligi_oz * OZ_KALINLIK_M
    rs_ohm_sq = BAKIR_OZDIRENC_OHM_M / kalinlik_m  # levha direnci, ohm/kare

    idx = -np.ones((n_en, n_boy), dtype=int)
    n = 0
    for i in range(n_en):
        for j in range(n_boy):
            if maske[i, j]:
                idx[i, j] = n
                n += 1
    if n == 0:
        raise ValueError("maskede hiç iletken hücre yok — poligon/çözünürlük hatalı.")

    def kondaktans(yatay: bool) -> float:
        r = (rs_ohm_sq * dx_m / dy_m) if yatay else (rs_ohm_sq * dy_m / dx_m)
        return 1.0 / r

    g_yatay = kondaktans(yatay=True)
    g_dikey = kondaktans(yatay=False)

    G = lil_matrix((n, n))
    for i in range(n_en):
        for j in range(n_boy):
            if not maske[i, j]:
                continue
            a = idx[i, j]
            if j + 1 < n_boy and maske[i, j + 1]:
                b = idx[i, j + 1]
                G[a, a] += g_yatay
                G[b, b] += g_yatay
                G[a, b] -= g_yatay
                G[b, a] -= g_yatay
            if i + 1 < n_en and maske[i + 1, j]:
                b = idx[i + 1, j]
                G[a, a] += g_dikey
                G[b, b] += g_dikey
                G[a, b] -= g_dikey
                G[b, a] -= g_dikey

    giris_dugumleri = [idx[i, giris_sutun] for i in range(n_en) if maske[i, giris_sutun]]
    cikis_dugumleri = [idx[i, cikis_sutun] for i in range(n_en) if maske[i, cikis_sutun]]
    if not giris_dugumleri:
        raise ValueError(f"giris_sutun={giris_sutun} içinde iletken hücre yok.")
    if not cikis_dugumleri:
        raise ValueError(f"cikis_sutun={cikis_sutun} içinde iletken hücre yok.")

    I = np.zeros(n)
    for a in giris_dugumleri:
        I[a] += akim_a / len(giris_dugumleri)
    for a in cikis_dugumleri:
        I[a] -= akim_a / len(cikis_dugumleri)

    ref = cikis_dugumleri[0]
    G[ref, :] = 0.0
    G[ref, ref] = 1.0
    I[ref] = 0.0

    V = spsolve(G.tocsr(), I)

    node_v = np.full((n_en, n_boy), np.nan)
    for i in range(n_en):
        for j in range(n_boy):
            if maske[i, j]:
                node_v[i, j] = V[idx[i, j]]

    akim_yog = np.full((n_en, n_boy - 1), np.nan)
    for i in range(n_en):
        for j in range(n_boy - 1):
            if maske[i, j] and maske[i, j + 1]:
                dal_akim_a = g_yatay * (node_v[i, j] - node_v[i, j + 1])
                akim_yog[i, j] = abs(dal_akim_a) / dy_m

    gecerli = akim_yog[~np.isnan(akim_yog)]
    maks_yog = float(np.max(gecerli)) if gecerli.size else 0.0

    return ResistifMeshSonucu(
        n_en=n_en, n_boy=n_boy, node_gerilim_v=node_v, akim_yogunlugu_a_m=akim_yog,
        toplam_akim_a=akim_a, maks_akim_yogunlugu_a_m=maks_yog,
    )


# ---------------------------------------------------------------------
# 3. Kullanıcı yüzeyi — dikdörtgen şerit (test edilebilir, analitik
#    karşılığı bilinen özel durum) ve genel poligon
# ---------------------------------------------------------------------

def bakir_seridi_coz(
    uzunluk_mm: float,
    genislik_mm: float,
    akim_a: float,
    bakir_agirligi_oz: float = 1.0,
    n_boy: int = 40,
    n_en: int = 10,
) -> ResistifMeshSonucu:
    """Basit DİKDÖRTGEN bakır şerit — akım sol kenardan girer, sağ
    kenardan çıkar. `bakir_poligonu_coz()`'ün, analitik karşılığı bilinen
    (`akim_a / genislik_mm` A/mm düzgün dağılım) özel/test hali."""
    maske = np.ones((n_en, n_boy), dtype=bool)
    return _mesh_coz(maske, uzunluk_mm, genislik_mm, akim_a, bakir_agirligi_oz,
                      giris_sutun=0, cikis_sutun=n_boy - 1)


def bakir_poligonu_coz(
    poligon_mm: Sequence[Tuple[float, float]],
    akim_a: float,
    bakir_agirligi_oz: float = 1.0,
    cozunurluk_mm: float = 0.5,
    giris_x_esik_mm: Optional[float] = None,
    cikis_x_esik_mm: Optional[float] = None,
) -> ResistifMeshSonucu:
    """GENEL amaçlı: rastgele (dışbükey/içbükey) bir bakır poligonunu
    `cozunurluk_mm` adımıyla rasterize edip çözer. Akım, `giris_x_esik_mm`
    (varsayılan: poligonun min-x'i) sütunundan girer, `cikis_x_esik_mm`
    (varsayılan: maks-x) sütunundan çıkar — bounding-box YAKLAŞIMI DEĞİL,
    poligonun GERÇEK köşeleri rasterizasyona dahildir (dar geçitler,
    delikler ızgarada doğru şekilde iletken-dışı işaretlenir)."""
    xs = [p[0] for p in poligon_mm]
    ys = [p[1] for p in poligon_mm]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    uzunluk_mm = x_max - x_min
    genislik_mm = y_max - y_min
    if uzunluk_mm <= 0 or genislik_mm <= 0:
        raise ValueError("poligon dejenere (sıfır alan) — geometri hatalı.")

    n_boy = max(2, int(round(uzunluk_mm / cozunurluk_mm)))
    n_en = max(2, int(round(genislik_mm / cozunurluk_mm)))
    dx = uzunluk_mm / n_boy
    dy = genislik_mm / n_en

    maske = np.zeros((n_en, n_boy), dtype=bool)
    for i in range(n_en):
        y = y_min + (i + 0.5) * dy
        for j in range(n_boy):
            x = x_min + (j + 0.5) * dx
            maske[i, j] = _nokta_poligon_icinde_mi(x, y, poligon_mm)

    giris_x = giris_x_esik_mm if giris_x_esik_mm is not None else x_min
    cikis_x = cikis_x_esik_mm if cikis_x_esik_mm is not None else x_max
    giris_sutun = int(np.clip(round((giris_x - x_min) / dx), 0, n_boy - 1))
    cikis_sutun = int(np.clip(round((cikis_x - x_min) / dx), 0, n_boy - 1))
    if giris_sutun == cikis_sutun:
        cikis_sutun = n_boy - 1 if giris_sutun == 0 else 0

    return _mesh_coz(maske, uzunluk_mm, genislik_mm, akim_a, bakir_agirligi_oz,
                      giris_sutun, cikis_sutun)


def isi_haritasi_kaydet(sonuc: ResistifMeshSonucu, png_yolu: Path, baslik: str = "Akım Yoğunluğu (A/m)") -> Optional[Path]:
    """`matplotlib` kurulu değilse `None` döner (PNG yazılmadı, hata
    FIRLATILMAZ) — çağıran taraf bunu `detay`e yazmalı, sessizce yok
    saymamalı (bkz. `akim_yogunlugu_haritasi_uret`)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots()
    im = ax.imshow(sonuc.akim_yogunlugu_a_m, origin="upper", aspect="auto", cmap="inferno")
    fig.colorbar(im, ax=ax, label="A/m")
    ax.set_title(baslik)
    ax.set_xlabel("uzunluk (hücre)")
    ax.set_ylabel("genişlik (hücre)")
    png_yolu = Path(png_yolu)
    png_yolu.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_yolu)
    plt.close(fig)
    return png_yolu


# ---------------------------------------------------------------------
# 4. pcbnew köprüsü — Bulgu sözleşmesiyle CLI/main.py entegrasyonu
# ---------------------------------------------------------------------

def akim_yogunlugu_haritasi_uret(
    pcb_yolu: str,
    net_adi: str,
    akim_a: float,
    calisma_dizini: str,
    bakir_agirligi_oz: float = 1.0,
    n_boy: int = 60,
    n_en: int = 20,
) -> Bulgu:
    """`pcb_yolu`'ndaki `net_adi`'na ait izlerin bounding box'ını (bkz.
    dosya başlığı SINIR notu — GERÇEK zone poligonu DEĞİL, dikdörtgen
    yaklaşımı) resistive mesh olarak çözer, ısı haritasını
    `calisma_dizini/akim_yogunlugu_<net>.png` olarak yazar.

    `pcbnew` kurulu değilse (mevcut `pcbnew_koprusu.py` deseniyle AYNI)
    HİÇBİR PNG/sayı ÜRETMEZ, `KAPSAM_YOK` döner. Net'in hiç izi yoksa da
    (taranan=0) aynı şekilde `KAPSAM_YOK` — "iz yok, o yüzden akım
    sorunu da yok" YANLIŞ bir PASS olurdu.
    """
    kontrol = "akim_yogunlugu_haritasi"
    try:
        from pcbnew_koprusu import _pcbnew_veya_kapsam_yok, net_iz_ve_via_listesi_topla
    except ImportError as hata:  # pragma: no cover - pcbnew_koprusu.py her zaman mevcut
        return bulgu_uret(kontrol, taranan=0, detay=f"pcbnew_koprusu import edilemedi: {hata}")

    _pcbnew, board, kapsam_yok = _pcbnew_veya_kapsam_yok(pcb_yolu, kontrol)
    if kapsam_yok is not None:
        return kapsam_yok

    geometri = net_iz_ve_via_listesi_topla(board, net_adi)
    if not geometri["izler"]:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                f"'{net_adi}' net'ine ait hiç iz bulunamadı — akım yoğunluğu "
                "hesaplanamadı (KAPSAM_YOK, PASS DEĞİL)."
            ),
        )

    xs = [p for iz in geometri["izler"] for p in (iz["baslangic_mm"][0], iz["bitis_mm"][0])]
    ys = [p for iz in geometri["izler"] for p in (iz["baslangic_mm"][1], iz["bitis_mm"][1])]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    uzunluk_mm = x_max - x_min
    genislik_mm = y_max - y_min
    if uzunluk_mm <= 0 or genislik_mm <= 0:
        return bulgu_uret(
            kontrol, taranan=0, detay=(
                f"'{net_adi}' net'inin bounding box'ı dejenere (uzunluk/genişlik=0) — "
                "akım dağılımı anlamlı hesaplanamaz (KAPSAM_YOK)."
            ),
        )

    sonuc = bakir_seridi_coz(uzunluk_mm, genislik_mm, akim_a, bakir_agirligi_oz, n_boy=n_boy, n_en=n_en)

    calisma_dir = Path(calisma_dizini)
    calisma_dir.mkdir(parents=True, exist_ok=True)
    png_yolu = isi_haritasi_kaydet(
        sonuc, calisma_dir / f"akim_yogunlugu_{net_adi}.png",
        baslik=f"{net_adi} — {akim_a}A akım yoğunluğu (bounding-box yaklaşımı)",
    )

    taranan = 1
    ihlaller: List[dict] = []
    return bulgu_uret(
        kontrol, taranan, ihlaller,
        f"net={net_adi}, bbox={uzunluk_mm:.2f}x{genislik_mm:.2f}mm, "
        f"maks_akim_yogunlugu_a_m={sonuc.maks_akim_yogunlugu_a_m:.2f}, "
        f"png={'yazilamadi (matplotlib yok)' if png_yolu is None else str(png_yolu)}. "
        "SINIR: bounding-box yaklaşımı, gerçek zone poligonu DEĞİL (bkz. dosya başlığı).",
    )
