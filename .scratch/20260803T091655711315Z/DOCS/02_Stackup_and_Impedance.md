# 02 — Stackup and Impedance

Durum: `TASLAK`

> Kaynak kod: `pcb_stackup_planner.py` (katman sayısı/dizilim/decoupling/
> length-matching), `empedans_cozucu.py` (IPC-2141/Wadell fiziksel çözüm).
> Bu dosya o hesapların SONUÇLARINI, bu projenin belirli revizyonu için
> kaydeder — formülleri tekrar açıklamaz.

## 1. Katman Sayısı Kararı

> **Karar kaydı (2026-08-03):** bu tablo doldurulup `capraz_dogrulama_yap()`
> PASS verdiğinde `karar_birimleri.karar_ekle_veya_guncelle()` ile
> `karar_id="stackup-katman-sayisi"` açılır — `gereken_kanit` bu tabloya +
> `capraz_dogrulama_yap()` sonucuna işaret eder. Stackup SONRADAN değişirse
> (ör. 4→6 katman) bu karara bağımlı TÜM diferansiyel çift/empedans
> kararları `karar_gecersiz_kil()` ile zincirleme `ACIK`'a döner — elle
> tek tek hatırlanmaz.

| Girdi | Değer |
|---|---|
| `katman_sayisini_hesapla()` çıktısı | *(2/4/6/8/10)* |
| Gerekçe (RF var mı, fine-pitch BGA var mı, yüksek akım var mı) | |
| `dizilimi_olustur()` ile üretilen sıra | *(ör. Sinyal / GND / Güç / Sinyal)* |
| `capraz_dogrulama_yap()` sonucu | PASS/FAIL + tarih |

## 2. Fiziksel Stackup (fab'ın PRESLENMİŞ değerleri — nominal DEĞİL)

> `empedans_cozucu.py` başındaki dürüstlük notu: "hesap ile üretilen"in
> farkı burada kayıt altına alınır. Fab'dan gelen coupon/TDR raporu
> olmadan bu tablo TASLAK sayılır.

| Katman çifti | Nominal H (mm) | Preslenmiş H (mm, fab raporundan) | Bakır ağırlığı | εr (frekans-düzeltmeli) |
|---|---|---|---|---|
| | | | | |

## 3. Empedans Kontrollü Hatlar

Her diferansiyel çift için `pcb_stackup_planner.py::empedans_hedefi_getir()`
+ `empedans_geometrisi_coz()` çıktısı:

| Net/Çift | Arayüz | Hedef Z (Ω) | Çözülen W/S (mm) | `ulasilabilir_mi` | Length-match toleransı |
|---|---|---|---|---|---|
| | | | | | |

- [ ] Her satırda `ulasilabilir_mi is False` çıkan YOK — çıktıysa stackup
  revize edildi (routing zorlanmadı, `empedans_cozucu.py` kuralı).
- [ ] Fab'a verilen değer **W değil, hedef Z + tolerans + referans katman**
  (`SKILL-empedans-stackup` §a ile aynı disiplin).
- [ ] Impedance test coupon istendi mi? Rapor eklendi mi?

## 4. Referans Düzlemi ve Dönüş Yolu

- [ ] Her hızlı katmanın kesintisiz referans düzlemi var (`stackup.json`
  eşdeğeri — `reference_net` alanı bu projede nerede tutuluyor, belirt).
- [ ] `kicad_koprusu.py::check_reference_plane_continuity()` PASS.
- [ ] Katman geçişlerinde GND→GND stitching via / GND→PWR bitişik 100nF.

## 5. Onay

- [ ] `empedans_cozucu.py::oz_testleri_calistir()` gerçek KiCad kurulumunda
  da (bu ortamda değil, senin makinende) tekrar çalıştırıldı.
- [ ] Durum `ONAYLANDI` — rev/tarih.
