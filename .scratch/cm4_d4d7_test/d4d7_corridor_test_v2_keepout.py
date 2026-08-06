"""
d4d7_corridor_test_v2_keepout.py
==================================
d4d7_corridor_test.py'nin (2026-08-04) DEVAMI: aynı senaryoya artık
HighSpeedRuleManager keepout'unu (Bölüm 6) da ekleyip D6-D7 mesafesinin
GERÇEKTEN büyüyüp büyümediğini yeniden ölçer. Board'a HİÇBİR ŞEY YAZMAZ.
"""
import sys
sys.path.insert(0, r"C:\Users\Dell\Desktop\pcb-designer-tool\pcb-tool-v2")

import math
from kuvvet_yonelimli_yerlesim import (
    Komponent, Net, YerlesimKategorisi,
    yerlesim_coz, cakisma_kontrolu, kisitlari_dogrula,
    yuksek_hiz_keepout_hesapla, keepout_cakismasi_kontrolu,
)

KOMPONENTLER = [
    Komponent(ref="D4", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=31.0),
    Komponent(ref="D5", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=31.0),
    Komponent(ref="D6", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=35.0),
    Komponent(ref="D7", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=35.0),
    Komponent(ref="J1", genislik_mm=25.345, yukseklik_mm=7.477, x=45.0, y=40.0, sabit=True),
    Komponent(ref="J6", genislik_mm=34.07, yukseklik_mm=23.897, x=95.0, y=17.0, sabit=True),
]

# Gerçek net isimleri kullanılıyor (_P/_N kuyruğu) - yuksek_hizli_net_mi
# bunları otomatik HS tanıyıp hem agirlik'i yükseltsin hem keepout üretsin.
NETLER = [
    Net(isim="ETH_TRD0_P", baglantilar=["J1", "D4"]),
    Net(isim="ETH_TRD0_P_out", baglantilar=["D4", "J6"]),
    Net(isim="ETH_TRD1_P", baglantilar=["J1", "D5"]),
    Net(isim="ETH_TRD1_P_out", baglantilar=["D5", "J6"]),
    Net(isim="ETH_TRD2_P", baglantilar=["J1", "D6"]),
    Net(isim="ETH_TRD2_P_out", baglantilar=["D6", "J6"]),
    Net(isim="ETH_TRD3_P", baglantilar=["J1", "D7"]),
    Net(isim="ETH_TRD3_P_out", baglantilar=["D7", "J6"]),
]

KART_GENISLIK, KART_YUKSEKLIK = 120.0, 80.0
IZ_GENISLIGI_MM = 0.18  # HS_GBE_100 netclass (cm4-io-test .kicad_pro)


def mesafe(koordinatlar, a, b):
    ax, ay = koordinatlar[a]
    bx, by = koordinatlar[b]
    return math.hypot(ax - bx, ay - by)


def main():
    once = {k.ref: (k.x, k.y) for k in KOMPONENTLER}

    # Başlangıç koordinatlarına göre (henüz çözülmemiş) keepout'ları hesapla
    # -- iteratif olarak her adımda yeniden hesaplamak daha doğru olurdu ama
    # bu motor .kicad_pcb'ye yazmayan bir TOHUM/tanı aracı; tek-geçiş yeterli
    # kanıt (spec de "henüz routed değilse uçtan uca" diyor, statik girdi).
    keepoutlar = []
    for net in NETLER:
        keepoutlar += yuksek_hiz_keepout_hesapla(net, once, IZ_GENISLIGI_MM)
    print(f"üretilen keepout sayısı: {len(keepoutlar)}")
    for kp in keepoutlar:
        print(f"  {kp.net_ismi}: merkez=({kp.merkez_x_mm:.2f},{kp.merkez_y_mm:.2f}) "
              f"yarıçap={kp.yaricap_mm:.3f}mm  ({kp.kaynak_ref}-{kp.hedef_ref})")

    sonuc_eski = yerlesim_coz(KOMPONENTLER, NETLER, KART_GENISLIK, KART_YUKSEKLIK, maks_iterasyon=400)
    sonuc_yeni = yerlesim_coz(
        KOMPONENTLER, NETLER, KART_GENISLIK, KART_YUKSEKLIK, maks_iterasyon=400,
        keepoutlar=keepoutlar,
    )

    print("\n=== KARŞILAŞTIRMA: eski (keepout'suz) vs yeni (HighSpeedRuleManager) ===")
    for pair in (("D4", "D6"), ("D5", "D7"), ("D6", "D7"), ("D4", "D5")):
        d_once = mesafe(once, *pair)
        d_eski = mesafe(sonuc_eski.koordinatlar, *pair)
        d_yeni = mesafe(sonuc_yeni.koordinatlar, *pair)
        print(f"  {pair[0]}-{pair[1]}: başlangıç={d_once:.3f}mm  "
              f"eski_motor={d_eski:.3f}mm  yeni_motor(keepout)={d_yeni:.3f}mm  "
              f"Δ(yeni-eski)={d_yeni - d_eski:+.3f}mm")

    komponent_haritasi = {k.ref: k for k in KOMPONENTLER}
    ihlaller_eski = keepout_cakismasi_kontrolu(sonuc_eski.koordinatlar, komponent_haritasi, keepoutlar)
    ihlaller_yeni = keepout_cakismasi_kontrolu(sonuc_yeni.koordinatlar, komponent_haritasi, keepoutlar)
    print(f"\nkeepout ihlalleri (eski motor): {ihlaller_eski}")
    print(f"keepout ihlalleri (yeni motor):  {ihlaller_yeni}")

    cakisma = cakisma_kontrolu(KOMPONENTLER, sonuc_yeni.koordinatlar)
    print(f"\ncourtyard çakışma kontrolü (yeni motor): {cakisma.durum.value} ({len(cakisma.ihlaller)} ihlal)")

    gerekli_min = 2.4 + 5.148  # DOCS/karar_birimleri.json j1-esd-cluster-corridor-darligi hedefi
    d6_d7_yeni = mesafe(sonuc_yeni.koordinatlar, "D6", "D7")
    d6_d7_once = mesafe(once, "D6", "D7")
    print(f"\n=== SONUÇ ===")
    print(f"D6-D7: {d6_d7_once:.3f}mm -> {d6_d7_yeni:.3f}mm (hedef >= {gerekli_min:.3f}mm)")
    if d6_d7_yeni >= gerekli_min:
        print("HEDEF KARŞILANDI: keepout, D6-D7 arası fiziksel koridoru gerçekten açtı.")
    else:
        print("Hedefe hâlâ ulaşılmadı - ek ağırlık/iterasyon veya keepout yarıçapı gerekebilir.")


if __name__ == "__main__":
    main()
