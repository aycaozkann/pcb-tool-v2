---
type: pcb-dashboard
project_status: taslak
release_status: blocked
tags:
  - pcb/dashboard
---

# PCB Tasarım Dashboard

**Faz durumu:** #faz/0-gereksinim

> [!info] Faz etiketleri
> Bu satırdaki etiket, CLAUDE.md'nin otonom akışındaki adımlardan hangisinde
> olunduğunu gösterir — sonraki fazın adı gelince BURADAKİ etiket elle
> güncellenir (`#faz/0-gereksinim` → `#faz/2-sematik` → `#faz/3-simulasyon`
> → `#faz/4-yerlesim` → `#faz/5-drc-temiz` → `#faz/6-checker` →
> `#faz/7-uretim`). Dataview kuruluysa aşağıdaki sorgu tüm `#faz/*`
> etiketlerini tek yerde listeler.

> [!warning] Üretim durumu: BLOKE
>
> Bu proje için gerçek KiCad tasarım varlıkları ve onaylı üretim kanıtları henüz bulunmuyor. Bu not, kontrol merkezidir; üretim onayı değildir.

## Hızlı durum

| Alan | Durum | Kaynak / sonraki adım |
|---|---|---|
| Gereksinimler | 🔴 TASLAK | [[01_Design_Requirements]] dosyasını doldur ve onayla |
| Stackup / empedans | 🔴 TASLAK | [[02_Stackup_and_Impedance]] |
| DRC kuralları | 🔴 TASLAK | [[03_Design_Rules]] + fab parametreleri |
| IPC standartları | ✅ EKLENDİ | IPC-2221 clearance, IPC-2152 iz genişliği, IPC-6012 DFM, IPC-DRU dönüşümü |
| DFM / DFA | 🟡 Bekliyor | [[04_DFM_and_DFA]] + `ipc6012_dfm_motoru.py` |
| Release | 🔴 BLOKE | [[05_Release_Checklist]] |

## Tasarım akışı

```mermaid
flowchart LR
    R[Gereksinimler] --> S[Şematik ve BOM]
    S --> H["HANDOVER.md (Devir Teslim)"]
    H --> P[Stackup ve yerleşim]
    P --> V[DRC / ERC / DFM]
    V --> Q[Bağımsız kontrol]
    Q --> U[Üretim paketi]
```

[[../TASARIM_AKISI|Ayrıntılı tasarım akışı]] · [[../MASTER_RULEBOOK|Bağlayıcı kural kitabı]]

## Otomatik doğrulama raporları (araç çıktıları — kaynak gerçeklik)

> [!note] Bu bağlantılar dosya henüz üretilmediyse KIRIK görünür — bu
> Obsidian'ın normal davranışıdır, bir hata değildir. Kırık bir bağlantı
> "bu adım henüz koşmadı" anlamına gelir; sessizce yeşile boyanmaz.

| Rapor | Üreten | Durum |
|-------|--------|-------|
| [[../HANDOVER|Devir Teslim (Handover)]] | `schematic-design` skill Faz 5 | ⏳ bekliyor |
| [[../TEST/routing_plan|Topoloji planı]] | `topolojik_router_koprusu.py` | ⏳ bekliyor |
| [[../TEST/simulasyon_raporu|SPICE simülasyon]] | `ngspice_koprusu.py` | ⏳ bekliyor |
| [[../TEST/pin_karsilastirma|Pin uyumu]] | `cad_api_koprusu.py` | ⏳ bekliyor |
| [[../TEST/checker_raporu|Design-checker]] | kural motoru | ⏳ bekliyor |
| [[../TEST/bringup_checklist|Bring-up listesi]] | `kicad_koprusu.py` | ⏳ bekliyor |
| [[../TEST/gerber_dfm_raporu|Gerber DFM]] | `gerber_dfm_gorsel_koprusu.py` | ⏳ bekliyor |
| [[../TEST/mcad_carpisma_raporu|3D çarpışma]] | `mcad_carpisma_koprusu.py` | ⏳ bekliyor |

Her rapor elle onaylandıktan sonra `[[07_Dogrulama/README|Doğrulama kanıtları]]` klasörüne taşınır.
Tam liste: [[../TEST/README|TEST/ dizini]].

## Hafıza ve günlük

- [[../HAFIZA/Hafiza_Defteri|Hafıza Defteri]] — proje-ötesi mühendislik dersleri, YENİ bir tasarıma başlamadan ÖNCE okunur
- [[../HAFIZA/Hata_Hafizasi|Hata Hafızası]] — DRC/ERC hata imzası eşleşmeli otomatik öğrenme (`hata_hafizasi.py`)
- [[../Changelog|Değişiklik Günlüğü]] — `degisiklik_gunlugu_uret.py` ile git geçmişinden üretilir

## Çalışma alanları

| Alan | Bağlantı | Modül/Kaynak |
|------|----------|-------------|
| 📋 Gereksinimler | [[01_Design_Requirements\|Design Requirements]] | `DOCS/01_Design_Requirements.md` |
| 📐 Stackup & Empedans | [[02_Stackup_and_Impedance\|Stackup & Impedance]] | `pcb_stackup_planner.py`, `empedans_cozucu.py` |
| 📏 DRC Kuralları | [[03_Design_Rules\|Design Rules]] | `kicad_koprusu.py`, `ipc_dru_koprusu.py` |
| 🔍 DFM & DFA | [[04_DFM_and_DFA\|DFM and DFA]] | `ipc6012_dfm_motoru.py`, `ipc2221_clearance_hesaplayici.py` |
| ✅ Release | [[05_Release_Checklist\|Release Checklist]] | `uretim_ciktilari_cli.py` |
| 📝 Kararlar | [[06_Kararlar/README\|Karar günlüğü]] | karar kayıtları |
| 🧪 Doğrulama | [[07_Dogrulama/README\|Doğrulama kanıtları]] | test/doğrulama raporları |
| 🏭 Üretim | [[08_Uretim/README\|Üretim paketleri]] | Gerber/BOM/CPL |
| 🔬 Otomatik raporlar | [[../TEST/README\|TEST/ raporları]] | routing, simülasyon, DFM, çarpışma |

## Modül durumu

| Modül | Durum | Test |
|-------|-------|------|
| `kicad_koprusu.py` | ✅ Hazır | `test_kicad_koprusu.py` |
| `sch_wire.py` | ✅ Hazır | `test_sch_wire.py` |
| `sematik_wire_motoru_old.py` | ⚠️ Deprecated (yerine `sch_wire.py`) | `test_sematik_wire_motoru_old.py` |
| `topolojik_router_koprusu.py` | ✅ Hazır | `test_topolojik_router_koprusu.py` |
| `kuvvet_yonelimli_yerlesim.py` | ✅ Hazır | `test_kuvvet_yonelimli_yerlesim.py` |
| `pcb_stackup_planner.py` | ✅ Hazır | `test_pcb_stackup_planner.py` |
| `empedans_cozucu.py` | ✅ Hazır | `test_empedans_cozucu.py` |
| `ngspice_koprusu.py` | ✅ Hazır | `test_ngspice_koprusu.py` |
| `gerber_dfm_gorsel_koprusu.py` | ✅ Hazır | `test_gerber_dfm_gorsel_koprusu.py` |
| `uretim_ciktilari_cli.py` | ✅ Hazır | `test_uretim_ciktilari_cli.py` |
| `uretim_zinciri_koprusu.py` | ✅ Hazır | `test_uretim_zinciri_freerouting.py` |
| `arac_yollari.py` | ✅ Hazır | `test_arac_yollari.py` |
| `ortam_on_kontrol.py` | ✅ Hazır | — |
| `ipc2221_clearance_hesaplayici.py` | ✅ Yeni | `test_ipc2221_clearance_hesaplayici.py` |
| `ipc2152_hesaplayici.py` | ✅ Yeni | `test_ipc2152_hesaplayici.py` |
| `ipc6012_dfm_motoru.py` | ✅ Yeni | `test_ipc6012_dfm_motoru.py` |
| `ipc_dru_koprusu.py` | ✅ Yeni | `test_ipc_dru_koprusu.py` |
| `bom_lifecycle_koprusu.py` | ✅ Hazır | `test_bom_lifecycle_koprusu.py` |
| `cad_api_koprusu.py` | ✅ Hazır | `test_cad_api_koprusu.py` |
| `hata_hafizasi.py` | ✅ Hazır | `test_hata_hafizasi.py` |
| `ipc_a_610_dfa_motoru.py` | ✅ Yeni | `test_ipc_a_610_dfa_motoru.py` |
| `emi_emc_kural_motoru.py` | ✅ Yeni | `test_emi_emc_kural_motoru.py` |
| `pcb_gorsel_kesit.py` | ✅ Yeni — ajanın "görme" yeteneği (gerçek ESP32C3_SmartBand'e karşı doğrulandı); artık SADECE Faz 5 nitel son-bakış için, bkz. `pcb_carpisma_radari.py` | `test_pcb_gorsel_kesit.py` |
| `pcb_carpisma_radari.py` | ✅ Yeni — JSON Çarpışma Radarı, placement/routing doğruluğu için `pcb_gorsel_kesit.py`'nin YERİNİ aldı (saf geometri katmanı 18 mock testle doğrulandı, `pcbnew.LoadBoard()` sarmalayıcısı SENİN makinende doğrulanmalı) | `test_pcb_carpisma_radari.py` |
| `otonom_kurtarma_motoru.py` | ✅ Yeni — Tam Otonom Kurtarma Mekanizması (subprocess sandboxing + waypoint segmentasyonu), araç çökmesinde `NEEDS_HUMAN`'a düşmeden otomatik kurtarma | `test_otonom_kurtarma_motoru.py` |
| `main.py` | ✅ Yeni — tek-komut orkestratör (`python main.py run --project-dir ...`): ortam ön kontrolü + şematik 0-wire tespiti + ERC + DRC kapısı, opsiyonel `--produce` ile `uretim_ciktilari_cli.py`'ye devir; gerçek `ESP32C3_SmartBand` ve `SHT35_Breakout` projelerine karşı doğrulandı | — |
| `otonom_python_router.py` | ✅ Yeni — son çare ızgara A* router (saf Python, `pcbnew` gerekmez); yazma katmanı SENİN makinende doğrulanmalı | `test_otonom_python_router.py` |

### Opsiyonel/ek araçlar (otonom akışa BAĞLANMADI — bkz. CLAUDE.md 4. Tur)

| Modül | Durum | Test |
|-------|-------|------|
| `sch_route.py` | ✅ Hazır (A* algoritması test edildi) | `test_sch_route.py` |
| `rewire.py` / `wireify.py` | ⚠️ Uçtan uca gerçek KiCad gerektirir | `test_rewire.py` (sınırlı) |
| `via_stub.py` | ⚠️ Gerçek `pcbnew` gerektirir, bu ortamda test edilemedi | — |
| `gate_receipt.py` | ✅ Hazır (42 test, bağımsız CLI) | `test_gate_receipt.py` |

## Referans Tasarımlar (eski tool ile tasarlanmış)

| Tasarım | KiCad Dosyaları | Durum | Detay |
|---------|----------------|-------|-------|
| [[09_Referans_Tasarimlar/SHT35_Breakout\|SHT35 Breakout]] | `.sch` ✅ `.pcb` ✅ `.pro` ✅ | Şematik tamam, ERC 0 hata | I2C sıcaklık/nem sensörü, 5V, 1×6 header |
| [[09_Referans_Tasarimlar/ESP32C3_SmartBand\|ESP32-C3 SmartBand]] | `.sch` ✅ `.pcb` ✅ `.pro` ✅ | PCB routing kısmen tamam, DRC 0 hata | ESP32-C3 + IMU + GC9A01 LCD + LiPo |

> Bu tasarımlar güncel tool modülleri (IPC-2221/2152/6012, fail-closed gates, sch_wire) olmadan yapıldı. Güncel tool ile tekrar doğrulanabilir.

## Açık maddeler

- [ ] Ürünün elektriksel ve mekanik gereksinimlerini onayla. #pcb/acik
- [ ] Hedef fabrika ve üretim profilini seç. #pcb/acik
- [ ] Gerçek KiCad şematik/PCB projesini oluştur. #pcb/acik
- [ ] KiCad CLI, pcbnew ve KiBot ortamını doğrula. #pcb/acik
- [ ] Gerçek bir kart ile uçtan uca DRC→ERC→DFM→Gerber testini çalıştır. #pcb/acik
- [ ] GitHub Actions CI pipeline'ı oluştur. #pcb/acik

## Dataview (isteğe bağlı)

```dataview
TASK
FROM "DOCS"
WHERE !completed
GROUP BY file.folder
```

```dataview
TABLE file.mtime AS "Son değişiklik"
FROM #faz
SORT file.mtime DESC
```
