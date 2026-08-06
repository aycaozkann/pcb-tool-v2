---
type: pcb-reference
tags:
  - pcb/referans
  - pcb/esp32c3
---

# ESP32-C3 SmartBand

**Klasör:** `ESP32-C3 Smart Board (Li-Ion/LiPo + MPU6050 + GC9A01 yuvarlak ekran + USB-C)\pcb-designer-tool`

| Alan | Değer |
|------|-------|
| Durum | Şematik tamamlandı, routing neredeyse tamam — **2026-07-31 (2. tur):** USB_DP/USB_DN 90° köşeler 45°'ye çevrildi (0 yeni ihlal), gerçek-board DFM taraması koştu (via-in-pad/kenar-keepout/stitching bulguları var, aşağıya bkz.). DRC'de sadece 2 unconnected (IMU_INT1, DISPLAY_RESET — **NEEDS_HUMAN, doğrulandı**: otomatik router tüm katmanları/via adaylarını tükendi, gerçek yerleşim yoğunluğu sorunu) + 1 zararsız D2 footprint uyarısı kaldı |
| Tool sürümü | Eski (semarik_wire_motoru, IPC modülleri, fail-closed gates OLMADAN) |
| Form faktör | Bilek tipi giyilebilir |

---

## Sistem Mimarisi

```mermaid
flowchart LR
    P[LiPo 3.7V 200mAh] --> R[TP4056 Charger]
    R --> B[ME6206A33M 3.3V LDO]
    B --> C3[ESP32-C3FH4X]
    B --> I[ICM-42688-P IMU]
    B --> D[GC9A01 LCD]
    C3 --> U[USB-C (native USB)]
    C3 --> I
    C3 --> D
```

## Elektriksel Özet

| Özellik | Değer |
|---------|-------|
| Besleme | Li-Po 3.7V → ME6206A33M (3.3V LDO) + TP4056 Li-Po charger |
| Ana MCU | ESP32-C3FH4X (QFN32 5×5mm, 16 GPIO bonded) |
| IMU | ICM-42688-P (LGA-14 2.5×3mm) — MPU-6050 Obsolete nedeniyle değişti |
| Ekran | GC9A01 yuvarlak LCD, 12-pin FPC (Hirose FH12-12S-0.5SH) |
| USB | USB-C (native USB Serial/JTAG), USB4085 konnektör |
| Radyo | 40MHz kristal (Epson TSX-3225), Pi-ağı RF eşleştirme |
| Pil koruma | DW01A + FS8205 Li-Po koruma kırmızı |

## Önemli Bileşenler

| Ref | Parça | Açıklama |
|-----|-------|----------|
| U1 | ESP32-C3FH4X | Ana MCU, QFN32, 16 GPIO |
| U2 | ICM-42688-P | 6-eksen IMU, LGA-14 |
| U3 | ME6206A33M | 3.3V LDO |
| U4 | TP4056 | Li-Po şarj yongası |
| U5 | DW01A | Pil koruma IC |
| U6 | FS8205 | Pil koruma MOSFET |
| D1 | USBLC6-2SC6 | USB ESD koruma |
| D2 | — | Ek besleme koruma diyotu (footprint kaydırıldı) |
| Y1 | Epson TSX-3225 40MHz | Ana kristal |

## Kapatılmış/Çözülmüş Sorunlar

| # | Sorun | Çözüm |
|---|-------|-------|
| 1 | FreeRouting JDK uyumsuzluğu | FreeRouting v2.2.4 başarıyla çalıştı: 112 net → 16 bağlanmamış |
| 2 | `.kicad_dru` sessizce yok sayılıyordu | `(version 1)` başlığı + `;` yerine `#` yorum + `priority` token kaldırıldı |
| 3 | DRC'de 26 kısa devre → 0 | FreeRouting + DRU düzeltmesi sonrası |
| 4 | Silkscreen ihlali 51 → 0 | Düzeltildi |
| 5 | Starved thermal 4 → 0 | Düzeltildi |
| 6 | Düzlemde yabancı sinyal 115.65mm → 0mm | Düzeltildi |
| 7 | MPU-6050 Obsolete → ICM-42688-P | Datasheet doğrulandı, pinout farkları tabloda işaretlendi |
| 8 | `hole_to_hole` ihlali | Yinelenen via kaldırıldı |
| 9 | U2 pin5/pin12 (+3V3) — 3 clearance hatası | Elle S-expr ile yeniden yönlendirildi (MCP backend çökmüştü); dik-mesafe hesabıyla pin11 pad'i + I2C_SCL 45° çapraz izi aynı anda temizlendi — bkz. `HAFIZA/Hafiza_Defteri.md` 2026-07-31 kaydı |

## 2026-07-31 güncellemesi (main.py + rewire.py gerçek doğrulaması)

- `main.py run --project-dir "..."` bu proje için ERC=temiz (7 uyarı,
  0 hata), DRC=HATA (2 unconnected + 1 lib_footprint_mismatch uyarısı)
  raporluyor — otomatik akışın gerçek çıktısı, bkz. aşağıdaki "Açık
  Maddeler".
- `rewire.py` bu şematikte (157 label) DENENDİ: 31 net'in 30'u tam
  yol buldu, sadece `STAT_K: D1-1 -> U3-1` kenarı `sch_route.py` A*
  router'ında çözülemedi → netlist-eşitlik farkı yakalandı, dosya
  OTOMATİK geri yüklendi (koruma çalıştı). Aynı sınırlama
  `SHT35_Breakout` referansında da görüldü (PWR_FLAG/leftover-MST-kenarı
  deseni) — `sch_route.py`'ye bir fallback eklenmeden bu proje de
  tam wire'a çevrilemiyor.
- IMU_INT1 (U1 pin5 → U2 pin4) net'i için otomatik escape-router denemesi
  (via + iç katman) yapıldı: pin5'in F.Cu pedi, 0.2mm clearance ile
  komşu pinlerin (pin4/pin6) kaçış izleri + U1'in büyük termal ped'i
  (pad 33) tarafından TOPOLOJİK OLARAK çevrelenmiş durumda (0.02mm
  ızgara çözünürlüğünde doğrulandı — gerçek bir "araç çökmesi" değil,
  gerçek bir yerleşim/tıkanıklık sorunu). Otomatik merdivenin üç
  katmanı da (DOGRUDAN/L/U, bölümlü, ızgara A*) tükendi →
  `NEEDS_HUMAN`: ya komşu bir izin (GPIO2_PULLUP) elle kaydırılması ya
  da GUI'de görsel push&shove gerekiyor.

- `escape_raporu_olustur()` yerine gerçek board'dan `USB_DP`/`USB_DN`
  F.Cu segmentleri çıkarılıp `dik_acili_koseleri_bul()` ile denetlendi:
  **USB_DP'de 4, USB_DN'de 7 adet 90° köşe bulundu** (KRİTİK — 45°/yay
  ile değiştirilmeli, standart DRC bunu YAKALAMAZ). Skew 0.48mm (~2.86ps)
  — USB2.0 bütçesi için önemsiz, sorun DEĞİL.
- `check_reference_plane_continuity()` (In1.Cu GND düzlemi F.Cu'nun
  referansı, 6 katmanlı stackup'ta bir sonraki katman) USB segmentlerine
  karşı TEMİZ çıktı (zone SINIRI ile — dolgu sonrası pad/via boşlukları
  dahil DEĞİL, ilk-derece kontrol).
- `pcbnew_koprusu.tum_gercek_board_kontrollerini_calistir()` GERÇEKTEN
  koşturuldu — **`gercek_boarddan_maske_baraji_kontrolu()`'nda CİDDİ bir
  BUG bulundu:** `kanal_ciftlerini_bul()`, aynı footprint'in SIRADAN
  2-pedli pasif parçalarını (ör. C18'in kendi 2 pedi) "pin-arası kanal"
  adayı sanıyor (bu senaryo sadece 3+ pinli paketlerde — SOT-23-6 gibi —
  anlamlı) VE sonucu kanal-başına değil kanal×iz (1131×375) çarpımı kadar
  tekrarlıyor — **52MB'lık, 175.815 birebir aynı satırlık bir rapor**
  üretti (`kanal=0.9600000000000009mm <= pad=1.12mm` gibi anlamsız
  "kısa devre" uyarıları C18 için sonsuz tekrar). Bu dosya SİLİNDİ (kanıt
  olarak saklamaya değmez) — **`kanal_ciftlerini_bul()` üretime güvenilir
  koşulmadan ÖNCE aynı-footprint 2-pedli pasifleri filtrelemeli ve
  kanal başına TEK KEZ raporlamalı.** Diğer 4 kontrol TEMİZ/anlamlı
  çalıştı:
  - `via_in_pad`: **1 bulgu** — U1'in QFN termal ped'i (pad 33, GND)
    içinde bir via var, fab notuna IPC-4761 Type VII (dolgu+kapak)
    eklenmeli.
  - `annular_ring`: **PASS** (0 ihlal, 109 delik tarandı).
  - `kenar_keepout_seramik`: **2 bulgu** — C16 (1.564mm) ve C17 (1.445mm)
    kart kenarından 2.0mm kuralının altında, kırılma/çatlama riski.
  - `stitch_yogunlugu`: **89 bulgu** — λ/20 hedefine göre GND stitching
    via yoğunluğu birçok kenar/iç noktada yetersiz.
  - Maske barajı kontrolünün NOISE'u içinde gerçek bir bulgu da vardı:
    `U4.5` (BL_SW net) için baraj -0.020mm < 0.2mm fab minimumu — bu,
    algoritma düzeltilip yeniden koşturulduğunda ayrıca doğrulanmalı.
- **USB_DP/USB_DN 90° köşeler DÜZELTİLDİ:** gerçek board'dan net+katman
  bazlı zincirleme (via'larla ayrılan alt-parçalar doğru tespit edildi)
  + `koseleri_45_dereceye_cevir()` ile 8 gerçek dik açı (F.Cu/B.Cu/In2.Cu
  toplamında) 45° pah'a çevrildi, DRC'de YENİ ihlal YOK (aynı 2
  unconnected + 1 lib_footprint_mismatch kaldı). Not: ilk (katmansız)
  taramada "4 DP + 7 DN" bulunmuştu — bu YANLIŞTI (farklı katmanlardaki
  segmentleri art arda sayıyordu); doğru/katman-ayrımlı sayım 8'dir.
- **D2 footprint "düzeltmesi" GERİ ALINDI:** `pcbnew.FootprintLoad()`
  ile taze kütüphane kopyası pedleri BİREBİR eşleşti (konum/boyut/net
  hepsi doğru) ama referans etiketi kütüphanenin VARSAYILAN konumuna
  döndü ve bu, R11 ile 2 YENİ silkscreen ihlali (`silk_overlap` +
  `silk_over_copper`) yarattı — orijinal board'da bu etiket BİLEREK
  kaydırılmış (R11'den kaçınmak için). Net-negatif olduğu için board
  ESKİ haline geri yüklendi; kalan `lib_footprint_mismatch` uyarısı
  (sadece grafik/silkscreen farkı, pedler zaten doğru) BİLİNÇLİ olarak
  bırakıldı.
- **IMU_INT1 ve DISPLAY_RESET — `NEEDS_HUMAN` (doğrulandı, araç
  tükenmedi):** her iki net için de via-escape router'ı GENİŞLETİLMİŞ
  aramayla (0.05mm ızgara A*, hem F.Cu stub hem iç katman rotası için,
  komşu pinlerin GERÇEK ped/iz/via geometrisine karşı) yeniden denendi.
  IMU_INT1 (U1 pin5): pedin 5mm yarıçapa kadar HİÇBİR yönde F.Cu'dan
  çıkışı yok (komşu pin4/pin6 kaçış izleri + U1'in büyük termal ped'i
  ile çevrelenmiş). DISPLAY_RESET (J1 pin11): 99 aday via konumunun
  HİÇBİRİNDEN ped'e geri dönen bir F.Cu stub bulunamadı (komşu
  DISPLAY_MOSI/CS/SCLK via'ları çok yakın). İkisi de gerçek bir
  yerleşim/yoğunluk sorunu — GUI'de görsel push&shove veya QFN/header
  çevresinde küçük bir yeniden-yerleşim gerekiyor, kod bunu güvenle
  otomatik çözemiyor.

## Açık Maddeler

- [ ] 2 bağlanmamış net'i (IMU_INT1: U1.5↔U2.4, DISPLAY_RESET: J1.11↔U1.10 — her ikisi de 12-14mm, muhtemelen 2-3 via gerekir) routing'den geçir — henüz denenmedi
- [ ] ERC uyarılarını incele (`multiple_net_names: CHIP_EN/+3V3`)
- [ ] `lib_footprint_mismatch: 1` (D2) — onay işareti
- [ ] `escape_raporu_olustur()` USB geometrisi üzerinde çalıştır
- [ ] Reference plane continuity kontrolü
- [ ] Maske barajı kontrolü
- [ ] Design-checker bağımsız denetimi
- [ ] Güncel tool ile IPC standartlarına uygunluk doğrulaması

## Dosyalar

| Dosya | Yol |
|-------|-----|
| Şematik | `ESP32C3_SmartBand.kicad_sch` |
| PCB | `ESP32C3_SmartBand.kicad_pcb` |
| Proje | `ESP32C3_SmartBand.kicad_pro` |
| DRC kuralları | `ESP32C3_SmartBand.kicad_dru` |
| Pin tablosu | `pin_baglanti_tablosu.md` (326 satır) |
| Layout raporu | `pcb_layout_raporu.md` (315 satır) |
| KiCad sembolleri | `project_symbols.kicad_sym` |
| ERC raporu | `CM5-erc.rpt` |
| Datasheet'ler | `DATASHEETS/` |
| Routing yedekleri | `.mcp-backups/`, çok sayıda `.bak` |
