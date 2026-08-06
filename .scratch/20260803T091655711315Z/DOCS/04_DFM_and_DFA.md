# 04 — DFM and DFA (Üretilebilirlik ve Montajlanabilirlik)

Durum: `TASLAK`

> Kaynak: `pcbnew_koprusu.py` (gerçek-board DFM ölçümleri), `ipc_a_610_dfa_motoru.py`
> (IPC-A-610 dizgi/reflow komponent clearance'ı — bkz. §1b),
> `emi_emc_kural_motoru.py` (3W/20H/via-stitching — bkz. §5),
> `.claude/skills/dft-testpoints/SKILL.md`, `.claude/skills/emi-emc/SKILL.md`,
> `uretim_zinciri_koprusu.py` BÖLÜM 4 (CPL/panelizasyon) + BÖLÜM 5 (kontrat
> kapıları — `parts.json`/`drc.json`).

## 1. Gerçek-Board DFM Kontrolleri (`pcbnew_koprusu.py`)

`kicad_koprusu.py::gercek_board_dogrulama_kapisi(board_path)` çalıştırıldıktan
sonra buraya SONUÇ yapıştırılır (JSON özetinden):

| Kontrol | Durum | Taranan | İhlal sayısı |
|---|---|---|---|
| `gercek_maske_baraji` | | | |
| `via_in_pad` | | | |
| `annular_ring` | | | |
| `kenar_keepout_seramik` | | | |
| `stitch_yogunlugu` | | | |

- [ ] `KAPSAM_YOK` çıkan bir kontrol varsa (ör. board'da hiç via yok), bu
  sessizce PASS sayılmadı, ayrıca not düşüldü.
- [ ] Via-in-pad bulunduysa: fab notunda **IPC-4761 Type VII** (dolgu+kapak)
  olarak belirtildi.

## 1b. DFA — Dizgi/Reflow Komponent Clearance (`ipc_a_610_dfa_motoru.py`)

`IpcA610DfaMotoru.tum_kontrolleri_calistir()` çıktısı (montaj sınıfı: Class 1/2/3):

| Kontrol | Durum | Taranan (çift) | İhlal sayısı |
|---|---|---|---|
| `ipc_a_610_komponent_clearance` (SMD-SMD / SMD-THT / THT-THT) | | | |
| `ipc_a_610_kenar_clearance` (komponent ↔ kart kenarı) | | | |

- [ ] Reflow ısıl gölgeleme riski (`golgeleme_riski_mi=True`, gövde
  yükseklik farkı > 2.0mm) işaretli komponent çiftleri elle gözden
  geçirildi — kısa komponente sıcak hava/IR erişimi yeterli mi?
- [ ] Konnektörler (mekanik keepout, `_KONNEKTOR_TABAN_MM`) mating/aktüatör
  hacmiyle çakışmıyor (bkz. `mekanik_dxf_koprusu.py::z_kontrolu_yap()` ile
  BİRLİKTE değerlendirilir, biri diğerinin yerine geçmez).
- [ ] SINIR: bounding-box yaklaşıklığı kullanır (rastgele açılarda gerçek
  courtyard'dan sapabilir) — kritik çiftler `mcp__kicad__check_courtyard_overlaps`
  / `check_clearance` ile çapraz doğrulandı.
- [ ] DÜRÜSTLÜK: bu modülün sayıları IPC-A-610'un KENDİSİNİN yayınladığı
  bir mesafe tablosu DEĞİL, TEMSİLİ/sektör-pratiği değerlerdir (bkz. modül
  başlığı) — seçilen dizgi hattının GÜNCEL yetenek verisiyle doğrulanmalı.

## 2. Test Noktaları (DFT)

`dft-testpoints` skill'i çıktısı:

- [ ] Güç rayı kapsamı: %100 (`tp_kapsam_kontrolu()`).
- [ ] Debug (SWD/UART) kapsamı: %100.
- [ ] Yüksek hızlı hatlarda (MIPI/USB) TP stub'ı YOK.
- [ ] `bringup_checklist.md` üretildi, rail enable sırası doğru.

## 3. Panelizasyon Stratejisi

`uretim_zinciri_koprusu.py::panelizasyon_kontrolu()` girdisi/çıktısı:

| Alan | Değer |
|---|---|
| Panel gerekiyor mu | *(hacme göre — bkz. `01_Design_Requirements.md` §4)* |
| Global fiducial sayısı | *(≥3 şart)* |
| BGA local fiducial | *(varsa)* |
| Rail genişliği (mm) | *(≥5mm)* |
| Hassas parça — depanel mesafesi (mm) | *(≥5mm, MLCC flex-crack riski)* |
| V-score / mouse-bite kararı | |

- [ ] Seramik (2-uçlu) parçaların kırma hattına göre YÖNÜ kontrol edildi
  (uzun eksen kırma çizgisine PARALEL olmalı — `kenar_keepout_seramik_kontrolu`
  çıktısındaki `yon_derece` ile).
- [ ] **Optik Hizalama (Fiducial Marks):** Kartın (veya panelin) en az 3
  köşesine Global Fiducial eklendi. BGA, QFN ve 0.5mm'den küçük pin
  aralığına sahip fine-pitch çiplerin çapraz köşelerine Local Fiducial
  eklendi mi?
- [ ] **Panelizasyon ve Mekanik Stres (Konveyör):** Konveyör bantlarının
  kartı tutabilmesi için kart kenarlarında (Edge Clearance) uygun boşluk
  bırakıldı VEYA panele kılavuz delikli (Tooling Holes) kenar çıtaları
  (Breakaway Rails) eklendi.
- [ ] **V-Cut/Mouse-Bite Komponent Keepout:** V-Cut (V-Kesim) veya Mouse
  Bites (Route) ayrım hatlarına 2mm'den daha yakın mesafede seramik
  kondansatör (MLCC) gibi mekanik strese duyarlı komponent YOK.

## 4. Assembly / CPL

- [ ] `generate_cpl_file()` → centroid = **courtyard merkezi**, footprint
  origin DEĞİL.
- [ ] `rotasyon_duzeltmesi_uygula()` + `check_orientation()` — kutuplu parça
  (diyot/LED/elektrolitik) yönü ↔ CPL açısı çapraz kontrolü PASS.
- [ ] Fab-rotasyon-map **versiyonlandı** (`rotation_map_versiyonla()` hash'i
  kayıtlı) — versiyonsuz map ile devam ETMEK YASAK (tüm parti ters lehim).
- [ ] DNP listesi hem BOM hem CPL'de aynı anda işaretli.

## 4b. Serigrafi ve Maske (Silkscreen vs Mask)

- [ ] Serigrafi (Silkscreen) yazıları, çizgileri veya Pin 1 işaretleyicileri
  KESİNLİKLE çıplak bakırın veya pad'lerin (Solder Mask Clearance alanı)
  üzerine denk gelmiyor — bu durum SMT dizgide lehim hatalarına yol açar.

## 5. EMI/EMC Kesişimi (`emi-emc` skill + `emi_emc_kural_motoru.py`)

- [ ] Dekuplaj yerleşimi ≤1.5mm doğrulandı.
- [ ] Termal ve gürültüye-hassas parçalar zıt köşelerde.
- [ ] Stitching via yoğunluğu (`stitch_yogunlugu_kontrolu` GERÇEK board üzerinde
  + `emi_emc_kural_motoru.stitching_max_araligi_mm()`/`via_araligi_kontrolu()`
  hedef/denetim çifti) λ/20 hedefte.
- [ ] **3W kuralı** (`emi_emc_kural_motoru.uc_w_kontrolu`): yüksek hızlı sinyal
  çiftleri (SPI/I2C/USB/diferansiyel) arası merkez-merkez mesafe ≥ iz
  genişliği × 3. `ipc_dru_koprusu.uc_w_kuraline_cevir()` ile `.kicad_dru`
  clearance kuralına yazıldı mı? (kenar-kenar değeri kullanılır, bkz. fonksiyon notu).
- [ ] **20H kuralı** (`emi_emc_kural_motoru.yirmi_h_kontrolu`): güç düzlemi
  GND düzleminden kart kenarında ≥ dielektrik kalınlığı × 20 İÇERİDE.
  (`.kicad_dru`'ya YAZILAMAZ — KiCad custom rule dilinde "plane setback"
  constraint tipi yok; bu kontrol Python tarafında kalıcı olarak koşmalı.)
- [ ] DÜRÜSTLÜK: 3W/20H/λ-20 FCC/CISPR'ın kendisinin verdiği sabit sayılar
  DEĞİL, EMC pratiğinde yaygın tasarım sezgiselleridir — gerçek uyumluluk
  yalnızca akredite lab ölçümüyle (D seviyesi, bkz. Otonom-PCB-Ajani
  `SKILL-dogrulama-matrisi.md` taksonomisi) kanıtlanır.

## 6. Onay

- [ ] Tüm kutular işaretli veya `AÇIK MADDE` olarak gerekçesiyle not edildi.
- [ ] Durum `ONAYLANDI` — rev/tarih.
