---
type: pcb-reference
tags:
  - pcb/referans
  - pcb/sht35
---

# SHT35 Sensör Breakout Kartı

**Klasör:** `Sensirion SHT35 SıcaklıkNem Sensör Breakout Kartı\pcb-designer-tool (1)\`

| Alan | Değer |
|------|-------|
| Durum | Şematik tamamlandı, ERC 0/0, **PCB DRC 0/0** (2026-07-31: `main.py run` ile doğrulandı) |
| Tool sürümü | `main.py` + `rewire.py`/`sch_wire.py` toolchain projeye SONRADAN eklendi (2026-07-31) |
| Revizyon | 4 (final) |

## 2026-07-31 güncellemesi (gerçek KiCad 10.0.4 ile doğrulandı)

- `MountingHole:MountingHole_2.2mm` lib_id'si güncel KiCad kütüphanesinde
  artık yok (yeniden adlandırılmış: `MountingHole_2.2mm_M2`) — MH1/MH2
  `pcbnew.FootprintLoad()` ile kütüphaneden TAZE kopyalanarak değiştirildi,
  `lib_footprint_mismatch` uyarısı kapandı.
- 3 silkscreen uyarısı (board kenarı + solder mask üzerine taşma) MH1/MH2/J1
  referans etiketlerinin `hide yes` yapılmasıyla temizlendi.
- Sadece `B.Cu`'da olan GND dökümü, aynı outline ile `F.Cu`'ya da eklendi
  (2 katmanlı kart için çift-taraflı referans düzlemi) + 8 adet GND
  stitching via'sı (kenar/köşe, mevcut bakırdan güvenli mesafe kontrolüyle
  yerleştirildi). **DRC: 0 hata / 0 uyarı.**
- `rewire.py` (0-wire label→gerçek wire dönüşümü) bu şematikte DENENDİ:
  7 net'in 5'i tam, ama `+5V`/`GND` net'lerindeki PWR_FLAG kısa-kenar
  bağlantısı (`R1-1 -> FLG1-1`, `R3-2 -> FLG2-1`) A* router'ında yol
  bulunamadı → netlist-eşitlik kontrolü farkı yakaladı, dosya OTOMATİK
  `.bak`'tan geri yüklendi (KORUMA ÇALIŞTI, veri kaybı YOK). Şematik hâlâ
  label-tabanlı — `sch_route.py`'nin A* router'ına PWR_FLAG kısa-kenarlar
  için bir fallback (ör. waypoint/detour) eklenmeden tam dönüşüm mümkün
  değil; bilinen sınırlama olarak kaydedildi.
- `main.py run --project-dir "..."` bu proje için PASS veriyor (ERC+DRC
  temiz); `--produce` KiBot kurulu değilse atlanır.

---

## Elektriksel Özet

| Özellik | Değer |
|---------|-------|
| Besleme | **+5V** doğrudan (header üzerinden hosttan), LDO yok |
| Sensör | Sensirion SHT35-DIS-B2.5KS (DFN-8-EP, 2.5×2.5mm) |
| Arayüz | I2C (5V mantık seviyesi, 4.7kΩ pull-up → +5V) |
| I2C adres | **0x44** (ADDR → GND sabit pull-down, header'da değil) |
| Header | 1×6 (VCC, GND, SDA, SCL, NRESET, ALERT) |

## BOM

| Ref | Değer | MPN | Üretici | LCSC |
|-----|-------|-----|---------|------|
| U1 | SHT35-DIS-B2.5KS | SHT35-DIS-B2.5KS | Sensirion | C90161 |
| C1 | 100nF X7R 16V | CC0603KRX7R9BB104 | Yageo | C14663 |
| R1 | 4.7kΩ %1 | RC0603FR-074K7L | Yageo | C99782 |
| R2 | 4.7kΩ %1 | RC0603FR-074K7L | Yageo | C99782 |
| R3 | 10kΩ %1 | RC0603FR-0710KL | Yageo | C98220 |
| J1 | 1×6 pin header, 2.54mm | 2.54-1x6P | Generic | C37208 |

## Dosyalar

| Dosya | Yol |
|-------|-----|
| Şematik | `SHT35_Breakout.kicad_sch` |
| PCB | `SHT35_Breakout.kicad_pcb` |
| Proje | `SHT35_Breakout.kicad_pro` |
| Pin tablosu | `pin_baglanti_tablosu.md` |
| Bring-up checklist | `bringup_checklist.md` |
| SVG görsel | `SHT35_Breakout_2d_view.svg` |
| Datasheet | `DATASHEETS/Sensirion_SHT3x-DIS_Datasheet.pdf` |

## Revizyon Geçmişi

| Rev | Değişiklik |
|-----|-----------|
| Rev 1 | LDO (AP2112K-3.3TRG1) ile 3.3-5V esnek giriş — terk |
| Rev 2 | LDO'suz +5V, 7-pin header (ADDR dahil) — terk |
| Rev 3 | LDO'suz +3.3V, 4-pin header — terk |
| **Rev 4** | **+5V doğrudan, 1×6 header (NRESET/ALERT eklendi), ADDR pull-down sabit** ✅ |
