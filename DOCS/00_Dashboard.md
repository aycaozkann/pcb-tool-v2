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
| IPC standartları | ✅ EKLENDİ | IPC-2221 clearance, IPC-2152 iz genişliği, IPC-6012 DFM, IPC-DRU dönüşümü, IPC-2221 via delik çapı (`via_capi_hesaplayici.py`, `python main.py via-capi`) |
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
| `kuvvet_yonelimli_yerlesim.py` | ✅ Hazır — artık `main.py` Faz 4'e bağlı (`hiyerarsik_yerlesim_coz`: güç/dekuplaj → kritik HS → düşük hızlı I/O ZORUNLU sırası; `termal_kisitlarini_uret` ile Faz 4b termal keepout GERÇEK yerleşim girdisi; `.kicad_pcb`'ye YAZMAZ, `TEST/yerlesim_raporu.md` üretir — 2026-08-03). **HighSpeedRuleManager (2026-08-05, Bölüm 6):** `yuksek_hizli_net_mi()` ile otomatik HS/diferansiyel tespiti + otomatik ağırlık yükseltme; `YuksekHizKeepout`/`yuksek_hiz_keepout_hesapla()` (3W kuralı) + `keepout_cakismasi_kontrolu()`/`yuksek_hiz_keepout_kontrolu()` (yeni `yuksek_hiz_keepout_ihlali` Bulgu tipi, mevcut `courtyard_cakismasi`'nın YANINA); `yerlesim_coz()`'e `keepoutlar` ile SONSUZ itme (adım reddi) eklendi. cm4-io-test'in gerçek D4-D7 verisiyle doğrulandı: keepout ihlalleri `['D4','D7']`→`[]`, D4-D6 koridoru +5.59mm (`.scratch/cm4_d4d7_test/d4d7_corridor_test_v2_keepout.py`). | `test_kuvvet_yonelimli_yerlesim.py` |
| `pcb_stackup_planner.py` | ✅ Hazır — `via_tipi_aspect_ratio_kontrolu()` eklendi: her via'yı KENDİ `ViaTipiDetay`'ine göre (BOYDAN_BOYA 8:1, KOR/GOMULU/MIKROVIA 1:1) değerlendirir, board-genel `ViaTipi` politika bayrağının (KONTROL 3) YANINA eklendi, YERİNE değil — 2026-08-04 | `test_pcb_stackup_planner.py`, `test_via_siniflandirma.py` |
| `via_siniflandirma.py` | ✅ Hazır — HDI via sınıflandırması: `ViaTipiDetay` (BOYDAN_BOYA/KOR/GOMULU/MIKROVIA), `Via` dataclass + `aspect_oran`, `select_via_type_for_bga()` proaktif karar (pitch≥0.8→BOYDAN_BOYA, 0.5-0.8+yüzeysel→KOR, <0.5 veya derin→MİKROVIA+via-in-pad+IPC-4761 Type VII otomatik) — 2026-08-04 | `test_via_siniflandirma.py` |
| `pcbnew_koprusu.py::via_in_pad_kontrolu` | ✅ Hazır — opsiyonel `via_siniflandirma_haritasi` parametresi eklendi: bilinçli dolgu+kapaklı (IPC-4761 Type VII) via-in-pad'ler artık ihlal SAYILMAZ; harita verilmezse (varsayılan) eski davranış BİREBİR korunur — 2026-08-04 | `test_pcbnew_koprusu.py::TestViaInPadGenisletme` |
| `pcbnew_koprusu.py::dekuplaj_mesafe_kontrolu` | ✅ Hazır — her IC güç pini için en yakın uygun (47-220nF) kapasitörün GERÇEK board mesafesini ölçer (varsayılan sınır 3mm); `pcb_stackup_planner.py::dekuplaj_kontrolu()`'nun (şematik-seviyesi SAYI kontrolü) YANINA eklendi; "kapasitör yok" / "kapasitör var ama uzak" AYRI ihlal türleri; cm4-io-test'te gerçek çalıştırıldı (19 güç pini tarandı, 19 ihlal — board'da sadece 1 uygun 100nF aday var) — 2026-08-04 | `test_pcbnew_koprusu.py::TestDekuplajMesafeKontrolu` |
| `pmic_ray_tahsisi.py` | ✅ Hazır — `PMICProfili`/`RayIhtiyaci` greedy tahsis: her rayı gerilim+kalan akıma göre bir PMIC çıkışına atar; `ray_tahsis_edilemedi`/`cikis_asiri_yuklendi` AYRI ihlal türleri; `MekanikVeTermalKisitlar.maks_isi_yayilimi_W` ile entegre (ek regülatörün TAHMİNİ ısı katkısı raporlanır) — 2026-08-04 | `test_pmic_ray_tahsisi.py` |
| `karar_birimleri.py::kritik_pin_teyit_karari_olustur` | ✅ Hazır — BOOT/SYSBOOT/MODE_SEL/NC_RESERVED/NDA net deseni tespit edilirse otomatik `durum=ACIK` karar birimi açar (`kritik_pin_karalarini_tespit_ve_kaydet()` diske yazar) — mevcut DAG/geçersizleme mantığı DEĞİŞTİRİLMEDİ, sadece yeni üretici fonksiyon eklendi; `kabul_edilmemis_kararlari_bul()` bu kararları OTOMATİK yakalayıp promotion'ı durdurur — 2026-08-04 | `test_karar_birimleri.py::TestKritikPinTeyitKapisi` |
| `empedans_cozucu.py` | ✅ Hazır | `test_empedans_cozucu.py` |
| `ngspice_koprusu.py` | ✅ Hazır | `test_ngspice_koprusu.py` |
| `gerber_dfm_gorsel_koprusu.py` | ✅ Hazır | `test_gerber_dfm_gorsel_koprusu.py` |
| `uretim_ciktilari_cli.py` | ✅ Hazır | `test_uretim_ciktilari_cli.py` |
| `uretim_zinciri_koprusu.py` | ✅ Hazır — DSN/SES `pcbnew` tabanlı (GÖREV 10) + JLCPCB DFM artık gerçek fail-closed ağ kodu (2026-08-03; endpoint/şema hâlâ doğrulanmadı, bkz. DOCS/10 D1.2) | `test_uretim_zinciri_freerouting.py`, `test_jlcpcb_dfm.py` |
| `ipc7351_footprint.py` | ✅ Hazır — 2-terminal + gullwing/QFP + QFN + BGA land pattern (2026-08-03) | `test_ipc7351_footprint.py` |
| `ecad_mcad_termal_kopru.py` | ✅ Hazır — artık `main.py` Faz 4b'ye bağlı (`termal_mekanik_taramasi_calistir`, `bulgu_sozlesmesi` uyumlu, 2026-08-03) | `test_ecad_mcad_termal_kopru.py` |
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
| `main.py` | ✅ Yeni — tek-komut orkestratör (`python main.py run --project-dir ...`): ortam ön kontrolü + şematik 0-wire tespiti + ERC + DRC kapısı + **Faz 4 Hiyerarşik Yerleşim Planlaması** + **Faz 4b Mekanik-Termal Entegrasyon** (2026-08-03, ikisi bağlı: termal keepout yerleşime GİRDİ) + opsiyonel `--produce`; ayrıca scratch/promote governance katmanı (`python main.py promote`); gerçek `ESP32C3_SmartBand` ve `SHT35_Breakout` projelerine karşı doğrulandı | `test_main.py`, `test_cmd_promote.py` |
| `otonom_python_router.py` | ✅ Yeni — son çare ızgara A* router (saf Python, `pcbnew` gerekmez); yazma katmanı SENİN makinende doğrulanmalı | `test_otonom_python_router.py` |

### Opsiyonel/ek araçlar (otonom akışa BAĞLANMADI — bkz. CLAUDE.md 4. Tur)

| Modül | Durum | Test |
|-------|-------|------|
| `sch_route.py` | ✅ Hazır (A* algoritması test edildi) | `test_sch_route.py` |
| `rewire.py` / `wireify.py` | ⚠️ Uçtan uca gerçek KiCad gerektirir | `test_rewire.py` (sınırlı) |
| `via_stub.py` | ✅ Hazır (2026-08-03: modül-seviyeli `import pcbnew` kaldırıldı, lazy import + pcbnew yokken `NO_COVERAGE` fail-closed — artık test edilebilir) | `test_via_stub.py` |
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
- [x] GitHub Actions CI pipeline'ı oluştur (`.github/workflows/ci.yml` — 2026-08-03). #pcb/acik

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
