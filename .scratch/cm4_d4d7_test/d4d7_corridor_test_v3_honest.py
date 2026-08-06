"""
d4d7_corridor_test_v3_honest.py
=================================
Kullanıcının haklı itirazı üzerine v2'nin düzeltmesi: v2, "eski_motor"
(keepout'suz) karşılaştırmasında bile net isimlerinin (_P/_N kuyruğu)
OTOMATİK ağırlık yükseltmesinden (Bölüm 6, agirlik 1.0->3.0) fayda
görüyordu - bu yüzden "keepout D6-D7'yi açtı" sonucu YANLIŞ ATFEDİLMİŞTİ
(gerçekte D6-D7 zaten SADECE otomatik-ağırlık yükseltmesiyle, keepout
hiç devrede olmadan, aynı mesafeye geliyordu - Δ keepout = -0.105mm,
yani NEGATİF).

Bu script ÜÇ ayrı koşulu ayırır:
  1. GERÇEK ESKİ DAVRANIŞ (agirlik=1.0 sabit, keepout yok) - 2026-08-04
     testinin birebir tekrarı.
  2. SADECE otomatik ağırlık yükseltmesi (Bölüm 6 A kısmı), keepout yok.
  3. Otomatik ağırlık + keepout (Bölüm 6 A+B+C, tam HighSpeedRuleManager).

Ayrıca D6-D7 için rapor edilen mesafe artık ÖKLİD merkez mesafesi
DEĞİL, karar_birimleri.json'ın "j1-esd-cluster-corridor-darligi"
kararının GERÇEKTEN kullandığı metrik: D6 sağ ped kenarı (x=79.8) ile
D7 sol ped kenarı (x=81.2) arası yatay boşluk - komponentler KATI
CİSİM olarak hareket ettiği için bu boşluk, komponent merkezlerinin
SADECE X eksenindeki delta'sı kadar değişir (Y ekseni deltası pad
kenarı boşluğunu ETKİLEMEZ, sadece X önemli).

Gerçek pad koordinatları bu oturumda `cm4_io_test.kicad_pcb`'den TAZE
ölçüldü (inspect_nets.py): D4/D6 X sütunu = 76.8625/79.1375,
D5/D7 X sütunu = 81.8625/84.1375, D4/D5 Y = 30.05/31.95,
D6/D7 Y = 34.05/35.95. D6 sağ ped kenarı = 79.1375+0.6625=79.8,
D7 sol ped kenarı = 81.8625-0.6625=81.2 -> başlangıç boşluk = 1.4mm
(karar_birimleri.json'daki rakamla BİREBİR eşleşiyor).
"""
import sys
sys.path.insert(0, r"C:\Users\Dell\Desktop\pcb-designer-tool\pcb-tool-v2")

import math
from kuvvet_yonelimli_yerlesim import (
    Komponent, Net, yerlesim_coz, keepout_cakismasi_kontrolu,
    yuksek_hiz_keepout_hesapla,
)

# Component merkezleri (gerçek pad koordinatlarından türetildi, bu oturumda
# pcbnew ile taze ölçüldü - bkz. docstring).
KOMPONENTLER = [
    Komponent(ref="D4", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=31.0),
    Komponent(ref="D5", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=31.0),
    Komponent(ref="D6", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=35.0),
    Komponent(ref="D7", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=35.0),
    Komponent(ref="J1", genislik_mm=25.345, yukseklik_mm=7.477, x=45.0, y=40.0, sabit=True),
    Komponent(ref="J6", genislik_mm=34.07, yukseklik_mm=23.897, x=95.0, y=17.0, sabit=True),
]

D6_PED_KENAR_OFSET = 79.8 - 78.0   # D6 merkezinden sağ ped kenarına: +1.8mm
D7_PED_KENAR_OFSET = 81.2 - 83.0   # D7 merkezinden sol ped kenarına: -1.8mm
BASLANGIC_PED_BOSLUGU = 1.4        # 79.8 -> 81.2, doğrulama için

KART_GENISLIK, KART_YUKSEKLIK = 120.0, 80.0
IZ_GENISLIGI_MM = 0.18


def ped_kenar_boslugu(koordinatlar):
    """D6 sağ ped kenarı ile D7 sol ped kenarı arası GERÇEK X boşluğu -
    katı cisim varsayımıyla: komponent merkezi nereye giderse, kendi
    sabit ofsetiyle pad kenarı da oraya gider."""
    d6_x = koordinatlar["D6"][0] + D6_PED_KENAR_OFSET
    d7_x = koordinatlar["D7"][0] + D7_PED_KENAR_OFSET
    return d7_x - d6_x


def calistir(netler, keepoutlar=(), etiket=""):
    sonuc = yerlesim_coz(
        KOMPONENTLER, netler, KART_GENISLIK, KART_YUKSEKLIK,
        maks_iterasyon=400, keepoutlar=keepoutlar,
    )
    bosluk = ped_kenar_boslugu(sonuc.koordinatlar)
    komponent_haritasi = {k.ref: k for k in KOMPONENTLER}
    ihlaller = keepout_cakismasi_kontrolu(sonuc.koordinatlar, komponent_haritasi, list(keepoutlar)) if keepoutlar else []
    print(f"--- {etiket} ---")
    print(f"  D6-D7 ped kenar boşluğu: {BASLANGIC_PED_BOSLUGU:.3f}mm -> {bosluk:.3f}mm  (Δ={bosluk - BASLANGIC_PED_BOSLUGU:+.3f}mm)")
    print(f"  keepout ihlalleri: {ihlaller}")
    for ref in ("D4", "D5", "D6", "D7"):
        print(f"  {ref}: {sonuc.koordinatlar[ref]}")
    return sonuc, bosluk


def main():
    once = {k.ref: (k.x, k.y) for k in KOMPONENTLER}
    print(f"BAŞLANGIÇ D6-D7 ped kenar boşluğu (doğrulama, karar_birimleri.json'daki 1.4mm ile eşleşmeli): "
          f"{ped_kenar_boslugu(once):.3f}mm\n")

    # --- 1. GERÇEK ESKİ DAVRANIŞ: agirlik=1.0 SABİT (isim HS olsa bile
    # elle agirlik verilerek otomatik yükseltme DEVRE DIŞI bırakılıyor -
    # bu, 2026-08-04 testinin/mevcut main koddaki eski davranışın
    # birebir eşdeğeri).
    netler_eski = [
        Net(isim="TRD0_a", baglantilar=["J1", "D4"], agirlik=1.0),
        Net(isim="TRD0_b", baglantilar=["D4", "J6"], agirlik=1.0),
        Net(isim="TRD1_a", baglantilar=["J1", "D5"], agirlik=1.0),
        Net(isim="TRD1_b", baglantilar=["D5", "J6"], agirlik=1.0),
        Net(isim="TRD2_a", baglantilar=["J1", "D6"], agirlik=1.0),
        Net(isim="TRD2_b", baglantilar=["D6", "J6"], agirlik=1.0),
        Net(isim="TRD3_a", baglantilar=["J1", "D7"], agirlik=1.0),
        Net(isim="TRD3_b", baglantilar=["D7", "J6"], agirlik=1.0),
    ]
    calistir(netler_eski, etiket="1) GERÇEK ESKİ DAVRANIŞ (agirlik=1.0, keepout yok)")

    # --- 2. Gerçek net isimleri (_P kuyruğu) -> otomatik ağırlık
    # yükseltmesi devrede, ama keepout HENÜZ YOK.
    netler_hs_isim = [
        Net(isim="ETH_TRD0_P", baglantilar=["J1", "D4"]),
        Net(isim="ETH_TRD0_P_hop2", baglantilar=["D4", "J6"]),
        Net(isim="ETH_TRD1_P", baglantilar=["J1", "D5"]),
        Net(isim="ETH_TRD1_P_hop2", baglantilar=["D5", "J6"]),
        Net(isim="ETH_TRD2_P", baglantilar=["J1", "D6"]),
        Net(isim="ETH_TRD2_P_hop2", baglantilar=["D6", "J6"]),
        Net(isim="ETH_TRD3_P", baglantilar=["J1", "D7"]),
        Net(isim="ETH_TRD3_P_hop2", baglantilar=["D7", "J6"]),
    ]
    # NOT: "_hop2" son eki KASITLI OLARAK yuksek_hizli_net_mi()'yi
    # TETİKLEMEZ (isim _P/_N ile bitmiyor) - bu, J1-Dn hop'unun HS
    # sayılıp Dn-J6 hop'unun sayılmamasının aynısı (v2'deki durum), YİNE
    # KASITLI: gerçek board'da da her iki hop ayrı net segment kimliğine
    # sahip olabilir; burada amaç sadece "otomatik ağırlık" etkisini
    # izole etmek.
    sonuc2, bosluk2 = calistir(netler_hs_isim, etiket="2) SADECE otomatik ağırlık yükseltmesi (keepout yok)")

    # --- 3. Aynı net isimleri + keepout (tam HighSpeedRuleManager) ---
    keepoutlar = []
    for net in netler_hs_isim:
        keepoutlar += yuksek_hiz_keepout_hesapla(net, once, IZ_GENISLIGI_MM)
    sonuc3, bosluk3 = calistir(netler_hs_isim, keepoutlar=keepoutlar, etiket="3) Otomatik ağırlık + KEEPOUT (tam HighSpeedRuleManager)")

    print("\n=== KEEPOUT'UN KENDİ NEDEN-SONUÇ KATKISI (2 ile 3 arası fark) ===")
    print(f"  D6-D7 ped kenar boşluğu: {bosluk2:.3f}mm (ağırlık-only) -> {bosluk3:.3f}mm (ağırlık+keepout)  "
          f"Δ(keepout'un KENDİ katkısı)={bosluk3 - bosluk2:+.3f}mm")

    hedef = 2.4
    print(f"\n=== SONUÇ (karar_birimleri.json hedefi: >= {hedef}mm) ===")
    print(f"  Koşul 3 (tam sistem) sonucu: {bosluk3:.3f}mm -> {'HEDEF KARŞILANDI' if bosluk3 >= hedef else 'HEDEF KARŞILANMADI'}")
    print(f"  Bu genişlemenin keepout'a mı yoksa otomatik-ağırlığa mı ait olduğu: "
          f"{'keepout NET katkı sağladı' if abs(bosluk3 - bosluk2) > 0.05 else 'keepout NET bir katkı sağlamadı (fark gürültü seviyesinde)'}")


if __name__ == "__main__":
    main()
