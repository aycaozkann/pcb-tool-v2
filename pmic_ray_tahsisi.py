#!/usr/bin/env python3
"""
pmic_ray_tahsisi.py
=====================
PMIC (Power Management IC) çıkış RAYLARININ, board'un gerçek güç
ihtiyaçlarına (RayIhtiyaci listesi) TAHSİS edilip edilemediğini kontrol
eder — "kaç çıkışı var" (BOM/datasheet seviyesi) ile "bu ÇIKIŞLAR bu
PROJENİN raylarını GERÇEKTEN karşılıyor mu" (proje-özel tahsis) arasındaki
boşluğu kapatır. Basit bir greedy eşleştirme kullanır: her ray, gerilimi
en yakın VE yeterli kalan akım kapasitesi olan bir PMIC çıkışına atanır.

`pcb_stackup_planner.py::MekanikVeTermalKisitlar` ile ENTEGRE: bir ray
tahsis edilemezse (ek/supplementary regülatör gerekiyorsa), o ek
regülatörün TERMAL BÜTÇEYE (maks_isi_yayilimi_W) etkisi de TAHMİNİ olarak
raporlanır (yeni bir regülatör = yeni bir ısı kaynağı).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from pcb_stackup_planner import MekanikVeTermalKisitlar


@dataclass
class PMICCikisi:
    isim: str          # "BUCK1", "LDO2" gibi
    tip: str            # "BUCK" veya "LDO"
    maks_akim_mA: float
    nominal_gerilim_V: float


@dataclass
class PMICProfili:
    isim: str           # "TPS65916" gibi
    ciktilar: List[PMICCikisi]


@dataclass
class RayIhtiyaci:
    ray_isim: str                # "VD_MPU", "3V3_FPGA" gibi
    gerilim_V: float
    tahmini_akim_mA: float
    kaynak: str = ""              # atanan PMIC çıkışı veya "TAHSIS_EDILMEDI"


# Gerilim eşleştirmesi için izin verilen bağıl tolerans — bir PMIC çıkışı
# bu bandın DIŞINDAysa aday bile SAYILMAZ (ör. 3.3V rayı için 1.8V çıkışı
# "en yakın" diye zorla eşleştirilmez).
_GERILIM_TOLERANSI_ORAN = 0.05  # %5

# Ek (supplementary) regülatör termal tahmini için varsayılan verim —
# TİPİK bir buck converter değeri (kaynak: genel endüstri pratiği, ~85-92%
# aralığı) — GERÇEK bir parça seçildiğinde o parçanın datasheet'inden
# doğrulanmalı, bu sadece İLK TAHMİN içindir (bkz. `pcb_stackup_planner.py`
# IPC-2221 iz genişliği hesabındaki AYNI "ilk tahmin" disiplini).
_VARSAYILAN_SUPPLEMENTARY_VERIM = 0.85


def _gerilim_uyumlu_mu(hedef_V: float, aday_V: float) -> bool:
    if hedef_V <= 0:
        return False
    return abs(aday_V - hedef_V) / hedef_V <= _GERILIM_TOLERANSI_ORAN


def _supplementary_isi_yayilimi_W(gerilim_V: float, akim_mA: float,
                                   verim: float = _VARSAYILAN_SUPPLEMENTARY_VERIM) -> float:
    """Ek regülatörün TAHMİNİ güç kaybı (W) — `P_out * (1/verim - 1)`.
    Buck-tipi bir converter varsayımı; gerçek parça seçilince datasheet'in
    KENDİ verim eğrisiyle DOĞRULANMALI, bu sadece ilk tahmindir."""
    p_out_W = gerilim_V * (akim_mA / 1000.0)
    return round(p_out_W * (1.0 / verim - 1.0), 4)


def ray_tahsisi_kontrol_et(
    pmic: PMICProfili,
    ihtiyaclar: List[RayIhtiyaci],
    termal_kisitlar: Optional[MekanikVeTermalKisitlar] = None,
) -> Bulgu:
    """Her `RayIhtiyaci`yı greedy olarak bir `PMICCikisi`na atamaya
    çalışır (en yakın nominal gerilim + yeterli kalan akım kapasitesi).

    İHLAL TÜRLERİ (ayrı ayrı):
      - `ray_tahsis_edilemedi`: hiçbir PMIC çıkışı bu rayı (gerilim
        toleransı + kalan akım) karşılayamıyor -> ek regülatör gerekli.
      - `cikis_asiri_yuklendi`: bir çıkışa atanan raylerin TOPLAM akımı
        o çıkışın `maks_akim_mA`'sını aşıyor (greedy atama sırasında
        önceden engellenmesi beklenir, ama önceden `kaynak` ALANI
        elle/dışarıdan doldurulmuş girdiler için AYRICA kontrol edilir).

    `termal_kisitlar` verilirse, tahsis edilemeyen HER ray için gereken
    ek regülatörün TAHMİNİ ısı katkısı hesaplanır ve toplamı
    `maks_isi_yayilimi_W` bütçesiyle karşılaştırılıp raporlanır (aşarsa
    detayda AÇIKÇA belirtilir, ayrı bir ihlal türü olarak DEĞİL — termal
    bütçe aşımı `ecad_mcad_termal_kopru.py`'nin kendi kontrolünün konusu,
    burada sadece BİLGİLENDİRME/raporlama amaçlıdır).
    """
    taranan = len(ihtiyaclar)
    if taranan == 0:
        return bulgu_uret("pmic_ray_tahsisi", 0, detay="Değerlendirilecek ray ihtiyacı yok")

    kalan_akim: Dict[str, float] = {c.isim: c.maks_akim_mA for c in pmic.ciktilar}
    cikis_haritasi = {c.isim: c for c in pmic.ciktilar}
    atanmis: Dict[str, str] = {}  # ray_isim -> cikis_isim

    ihlaller: List[Dict[str, Any]] = []
    tahsis_edilemeyen_toplam_isi_W = 0.0

    for ihtiyac in ihtiyaclar:
        adaylar = [
            c for c in pmic.ciktilar
            if _gerilim_uyumlu_mu(ihtiyac.gerilim_V, c.nominal_gerilim_V)
            and kalan_akim[c.isim] >= ihtiyac.tahmini_akim_mA
        ]
        if not adaylar:
            ihtiyac.kaynak = "TAHSIS_EDILMEDI"
            isi_W = _supplementary_isi_yayilimi_W(ihtiyac.gerilim_V, ihtiyac.tahmini_akim_mA)
            tahsis_edilemeyen_toplam_isi_W += isi_W
            ihlaller.append({
                "tur": "ray_tahsis_edilemedi",
                "ray": ihtiyac.ray_isim,
                "gerilim_V": ihtiyac.gerilim_V,
                "tahmini_akim_mA": ihtiyac.tahmini_akim_mA,
                "detay": f"PMIC {pmic.isim} bu rayı karşılayamıyor, ek (supplementary) "
                         f"regülatör gerekli.",
                "ek_regulator_tahmini_isi_W": isi_W,
            })
            continue

        # En yakın nominal gerilime sahip aday seçilir (eşitlikte en çok
        # kalan akım kapasitesine sahip olan tercih edilir — deterministik).
        secilen = min(
            adaylar,
            key=lambda c: (abs(c.nominal_gerilim_V - ihtiyac.gerilim_V), -kalan_akim[c.isim]),
        )
        kalan_akim[secilen.isim] -= ihtiyac.tahmini_akim_mA
        ihtiyac.kaynak = secilen.isim
        atanmis[ihtiyac.ray_isim] = secilen.isim

    # Aşırı yükleme ikinci-geçiş kontrolü: `kaynak` alanı DIŞARIDAN
    # (elle) önceden doldurulmuş girdiler de bu fonksiyona verilebilir —
    # bu durumda greedy atama YUKARIDA zaten "TAHSIS_EDILMEDI" ile
    # değiştirmiş olabilir; burada sadece GERÇEKTEN bu tahsisin (yukarıda
    # atanan) ürettiği toplam akımı çıkış bazında topluyoruz.
    cikis_toplam_akim: Dict[str, float] = {c.isim: 0.0 for c in pmic.ciktilar}
    for ihtiyac in ihtiyaclar:
        if ihtiyac.kaynak in cikis_haritasi:
            cikis_toplam_akim[ihtiyac.kaynak] += ihtiyac.tahmini_akim_mA
    for cikis_isim, toplam in cikis_toplam_akim.items():
        sinir = cikis_haritasi[cikis_isim].maks_akim_mA
        if toplam > sinir:
            ihlaller.append({
                "tur": "cikis_asiri_yuklendi",
                "cikis": cikis_isim,
                "toplam_akim_mA": round(toplam, 3),
                "maks_akim_mA": sinir,
                "detay": f"PMIC {pmic.isim} çıkışı {cikis_isim} toplamda "
                         f"{toplam:.1f}mA istiyor ama sınır {sinir:.1f}mA.",
            })

    detay_parcalari = [f"PMIC {pmic.isim}: {len(ihtiyaclar)} ray değerlendirildi, "
                        f"{len(atanmis)} tahsis edildi."]
    if tahsis_edilemeyen_toplam_isi_W > 0:
        detay_parcalari.append(
            f"Tahsis edilemeyen raylerin toplam TAHMİNİ ek regülatör ısı katkısı: "
            f"{round(tahsis_edilemeyen_toplam_isi_W, 4)}W (verim varsayımı "
            f"{_VARSAYILAN_SUPPLEMENTARY_VERIM*100:.0f}%, GERÇEK parça seçilince "
            "datasheet'ten doğrulanmalı)."
        )
        if termal_kisitlar is not None:
            yeni_toplam = tahsis_edilemeyen_toplam_isi_W  # mevcut ısı bütçesi board'un GERİ KALANINI zaten kapsıyor varsayımı
            if yeni_toplam > termal_kisitlar.maks_isi_yayilimi_W:
                detay_parcalari.append(
                    f"UYARI: bu ek ısı TEK BAŞINA ({round(yeni_toplam,4)}W) mevcut termal "
                    f"bütçeyi ({termal_kisitlar.maks_isi_yayilimi_W}W) AŞIYOR — ısı yönetimi "
                    "(soğutucu/kasa temas yüzeyi) revize edilmeli."
                )
            else:
                detay_parcalari.append(
                    f"Termal bütçe ({termal_kisitlar.maks_isi_yayilimi_W}W) içinde kalıyor "
                    "(sadece bu ek regülatör için — board'un GERİ KALAN ısı kaynaklarıyla "
                    "TOPLAMDA ayrıca değerlendirilmeli)."
                )

    return bulgu_uret("pmic_ray_tahsisi", taranan, ihlaller, " ".join(detay_parcalari))
