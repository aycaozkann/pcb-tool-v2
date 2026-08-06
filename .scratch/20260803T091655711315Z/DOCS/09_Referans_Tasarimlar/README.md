---
type: pcb-index
tags:
  - pcb/referans
---

# Referans Tasarımlar

Bu klasör, `pcb-designer-tool`'un eski sürümleriyle tasarlanmış gerçek PCB projelerini belgeler. Her sayfa, ilgili projenin KiCad dosyalarına, pin tablosuna ve doğrulama raporlarına bağlanır.

| Tasarım | Açıklama | KiCad Dosyaları | Durum |
|---------|----------|-----------------|-------|
| [[09_Referans_Tasarimlar/SHT35_Breakout\|SHT35 Breakout]] | Sensirion SHT35 sıcaklık/nem sensör breakout kartı (I2C, 5V, 1×6 header) | `.kicad_sch` ✅ `.kicad_pcb` ✅ `.kicad_pro` ✅ | 🟡 Şematik tamam, ERC 0 hata — PCB yerleşim/routing bekliyor |
| [[09_Referans_Tasarimlar/ESP32C3_SmartBand\|ESP32-C3 SmartBand]] | ESP32-C3FH4X tabanlı giyilebilir akıllı bileklik (LiPo, IMU, yuvarlak LCD, USB-C) | `.kicad_sch` ✅ `.kicad_pcb` ✅ `.kicad_pro` ✅ | 🟡 Routing kısmen tamam, 6 bağlanmamış net kaldı |

> Bu tasarımlar, mevcut `pcb-tool-v2`'nin güncel modülleri (IPC standartları, sch_wire, fail-closed gates) **olmadan** tasarlanmıştır. Güncel tool ile tekrar doğrulama yapılabilir.
