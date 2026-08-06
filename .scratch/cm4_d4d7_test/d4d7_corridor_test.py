"""
d4d7_corridor_test.py
======================
DOCS/karar_birimleri.json -> j1-esd-cluster-corridor-darligi kararına göre
test: kuvvet_yonelimli_yerlesim.py'yi (main.py Faz 4'ün ZATEN kullandığı
motor) SADECE cm4-io-test'in D4-D7 ESD kümesine ve komşu çevresine
(J1/J6 sabit çapa olarak) uygulayıp D6-D7 arası mesafenin gerçekten
büyüyüp büyümediğini ölçer. Board'a HİÇBİR ŞEY YAZMAZ (motorun kendi
tasarım sınırı zaten budur — bkz. modül docstring'i).

Gerçek koordinatlar 2026-08-04 oturumunda MCP get_component_pads /
get_component_list ile ölçüldü (cm4-io-test/cm4_io_test.kicad_pcb).
"""
import sys
sys.path.insert(0, r"C:\Users\Dell\Desktop\pcb-designer-tool\pcb-tool-v2")

import math
from kuvvet_yonelimli_yerlesim import (
    Komponent, Net, MesafeKisiti, YerlesimKategorisi,
    yerlesim_coz, cakisma_kontrolu, kisitlari_dogrula,
)

# --- Gerçek board verisi (2026-08-04 MCP ölçümü) ---
# D4/D5/D6/D7: USBLC6-2SC6, SOT-23-6, courtyard bbox ~11.107 x 5.148mm
KOMPONENTLER = [
    Komponent(ref="D4", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=31.0),
    Komponent(ref="D5", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=31.0),
    Komponent(ref="D6", genislik_mm=11.107, yukseklik_mm=5.148, x=78.0, y=35.0),
    Komponent(ref="D7", genislik_mm=11.107, yukseklik_mm=5.148, x=83.0, y=35.0),
    # J1 (CM4 B2B konnektörü, TRD kaynağı) ve J6 (RJ45 MagJack, TRD hedefi)
    # SABİT çapa olarak eklendi (gerçek footprint merkezleri).
    Komponent(ref="J1", genislik_mm=25.345, yukseklik_mm=7.477, x=45.0, y=40.0, sabit=True),
    Komponent(ref="J6", genislik_mm=34.07, yukseklik_mm=23.897, x=95.0, y=17.0, sabit=True),
]

# ETH_TRD0..3 P/N -> D4=TRD0, D5=TRD1, D6=TRD2, D7=TRD3, her biri J1'den
# girip J6'ya çıkıyor (flow-through). Ratsnest modeli için: J1-Dn ve
# Dn-J6 iki ayrı 2-pinli net (P/N ayrımı bu basitleştirilmiş testte
# önemli değil, tek bir "kanal" net'i yeterli — force-directed motor
# zaten pin sayısına değil net ağırlığına bakıyor).
NETLER = [
    Net(isim="TRD0_kanal_a", baglantilar=["J1", "D4"], agirlik=1.0),
    Net(isim="TRD0_kanal_b", baglantilar=["D4", "J6"], agirlik=1.0),
    Net(isim="TRD1_kanal_a", baglantilar=["J1", "D5"], agirlik=1.0),
    Net(isim="TRD1_kanal_b", baglantilar=["D5", "J6"], agirlik=1.0),
    Net(isim="TRD2_kanal_a", baglantilar=["J1", "D6"], agirlik=1.0),
    Net(isim="TRD2_kanal_b", baglantilar=["D6", "J6"], agirlik=1.0),
    Net(isim="TRD3_kanal_a", baglantilar=["J1", "D7"], agirlik=1.0),
    Net(isim="TRD3_kanal_b", baglantilar=["D7", "J6"], agirlik=1.0),
]

# Board sınırları (cm4-io-test gerçek board boyutu, mm)
KART_GENISLIK = 120.0
KART_YUKSEKLIK = 80.0


def mesafe(koordinatlar, a, b):
    ax, ay = koordinatlar[a]
    bx, by = koordinatlar[b]
    return math.hypot(ax - bx, ay - by)


def main():
    once = {k.ref: (k.x, k.y) for k in KOMPONENTLER}
    print("=== ÖNCESİ (gerçek board koordinatları) ===")
    for pair in (("D4", "D6"), ("D5", "D7"), ("D6", "D7"), ("D4", "D5")):
        print(f"  {pair[0]}-{pair[1]}: {mesafe(once, *pair):.4f} mm")

    sonuc = yerlesim_coz(
        KOMPONENTLER, NETLER, KART_GENISLIK, KART_YUKSEKLIK,
        kisitlar=[],
        maks_iterasyon=400,
    )

    print(f"\nyakınsadı_mı={sonuc.yakinsadi_mi}  iterasyon={sonuc.iterasyon}  "
          f"ratsnest {sonuc.baslangic_ratsnest_mm}mm -> {sonuc.son_ratsnest_mm}mm  "
          f"iyileşme={sonuc.iyilesme_orani:.1%}")

    print("\n=== SONRASI (force-directed çözüm) ===")
    for ref in ("D4", "D5", "D6", "D7"):
        print(f"  {ref}: {sonuc.koordinatlar[ref]}")
    for pair in (("D4", "D6"), ("D5", "D7"), ("D6", "D7"), ("D4", "D5")):
        d_once = mesafe(once, *pair)
        d_sonra = mesafe(sonuc.koordinatlar, *pair)
        delta = d_sonra - d_once
        print(f"  {pair[0]}-{pair[1]}: {d_once:.4f}mm -> {d_sonra:.4f}mm  (Δ={delta:+.4f}mm)")

    cakisma = cakisma_kontrolu(KOMPONENTLER, sonuc.koordinatlar)
    print(f"\nÇakışma kontrolü: {cakisma.durum.value} ({len(cakisma.ihlaller)} ihlal)")
    for ihlal in cakisma.ihlaller:
        print(f"   - {ihlal}")

    print("\n=== SONUÇ / KARAR ===")
    d6_d7_once = mesafe(once, "D6", "D7")
    d6_d7_sonra = mesafe(sonuc.koordinatlar, "D6", "D7")
    gerekli_min = 2.4  # DOCS/karar_birimleri.json j1-esd-cluster-corridor-darligi hedefi
    if d6_d7_sonra > d6_d7_once + 0.05:
        print(f"D6-D7 mesafesi GENİŞLEDİ: {d6_d7_once:.3f}mm -> {d6_d7_sonra:.3f}mm "
              f"(Δ={d6_d7_sonra - d6_d7_once:+.3f}mm). "
              f"{'Hedef (>=2.4mm koridor) KARŞILANDI.' if d6_d7_sonra >= gerekli_min + 5.148 else 'Hedefe hâlâ ulaşılmadı, ek iterasyon/ağırlık gerekebilir.'}")
        print("ONAY GEREKİR: board'a yazmadan önce kullanıcı onayı bekleniyor (bu script board'a yazmaz).")
    else:
        print(f"D6-D7 mesafesi GENİŞLEMEDİ (Δ={d6_d7_sonra - d6_d7_once:+.3f}mm) — "
              "somut teşhis: force-directed motor ratsnest'i minimize ediyor, ve D4-D7'nin "
              "tümü AYNI iki sabit çapaya (J1, J6) bağlı olduğundan motorun doğal eğilimi "
              "TÜMÜNÜ J1-J6 hattı üzerinde ÜST ÜSTE/YAKIN toplamaktır (ratsnest için optimal) "
              "— itme kuvveti sadece courtyard ÇAKIŞMASI durumunda devreye giriyor, ve D4-D7 "
              "arası (5mm merkez, courtyard yarıçapı ~6.1mm) zaten ÇAKIŞIYOR durumda, bu yüzden "
              "itme kuvveti çalışıyor OLABİLİR ama çekim kuvveti bunu dengeliyor/aşıyor olabilir. "
              "Kesin sebep: itme kuvveti sadece courtyard örtüşmesini gidermeye yeter kadar iter, "
              "'routing için via-pair'e yer aç' gibi bir ek hedefi YOKTUR — bu motor courtyard "
              "çakışmasını çözer ama ROUTING KORİDORU GENİŞLİĞİNİ bir optimizasyon hedefi olarak "
              "BİLMEZ (bkz. modülün kendi 'SINIRLARI' notu).")


if __name__ == "__main__":
    main()
