---
name: emi-emc
description: EMI/EMC (elektromanyetik paraziti azaltma) ve termal yönetim kararlarını yönetir — topraklama stratejisi, dekuplaj yerleşimi, ekranlama (shielding), stitching via yoğunluğu, termal via/poligon soğutma. Şematik topoloji + PCB yerleşim/routing arasında köprü kurar. Kullanıcı "EMI/EMC kontrolü yap", "topraklama stratejisi", "gürültü azaltma" veya "termal tasarım" dediğinde kullan.
tags: [skill, emi-emc, termal]
---

# SKILL: EMI/EMC ve Termal Yönetim

Önceki durum: EMI/EMC ile ilgili kod (`pcb_stackup_planner.py`'deki RF
stitching aralığı, guard-ring, yalıtım mesafesi kontrolleri;
`pcbnew_koprusu.py::stitch_yogunlugu_kontrolu`) VARDI ama dağınıktı — ne bir
skill dosyası ne de tek bir "EMI/EMC kararları burada verilir" akış noktası
vardı. Bu dosya o boşluğu kapatır: **EMI bir "son kontrol" değil, stackup +
yerleşim KARARIDIR** — Faz 4'te (`pcb-layout`) keşfedilen bir EMI problemi
kart dönüşü demektir; bu skill Faz 2-3'te (stackup + şematik) koşmalı.

## 1. Topraklama Stratejisi (önce topoloji, sonra yerleşim)

1. **Tek-nokta vs çoklu-nokta toprak:** Karışık analog/dijital devrelerde
   analog ve dijital GND'yi TEK bir noktada (genelde ADC/dönüştürücü altında)
   birleştir; birden fazla birleşim noktası ground loop yaratır. Karar
   `sematik_riskler.md`'ye yazılmalı (bilinçli tercih, tesadüf değil).
2. **Düzlem sürekliliği:** Yüksek hızlı hat, referans düzleminde split/void
   üzerinden GEÇEMEZ — `kicad_koprusu.py::check_reference_plane_continuity()`
   ile ölçülerek kanıtlanır (gözle bakmak yeterli değil, MASTER_RULEBOOK
   Faz 6 kontrol listesi bunu zaten şart koşuyor).
3. **Katman geçişinde dönüş yolu:** GND→GND yakın stitching via; GND→PWR
   geçişinde dönüş yolu via değil **bitişik 100nF kapasitördür**.
4. **Kart-dışına çıkan her arayüz** (konnektör, kablo) potansiyel bir
   anten/CM (ortak-mod) kaynağıdır — ışıyan emisyonların çoğu kablo
   rezonansından gelir, karttan değil. Filtre/choke ayak izini konnektör
   TARAFINDA, baştan ayır (kullanılmasa bile DNP).

## 2. Dekuplaj Kapasitörü Yerleşimi

- **Değer değil, döngü endüktansı belirler.** Aynı değerden çok sayıda,
  mümkün olan en düşük döngü endüktansıyla (kısa iz + yakın via) yerleştir.
  `pcb_stackup_planner.py::dekuplaj_kontrolu()` şu an SADECE SAYIYI kontrol
  ediyor (her güç pinine ≥1 kapasitör) — gerçek mesafe/döngü alanı kontrolü
  henüz `pcbnew_koprusu.py` seviyesinde otomatikleştirilmedi (`TBD`:
  gerçek board üzerinde pad→via→düzlem döngü alanı ölçümü).
- MASTER_RULEBOOK Faz 4 kuralı: bypass kapasitörü VCC/VDD pinine **≤1.5mm**.
- Yüksek-CV MLCC'lerde DC-bias derating'i unutma (`guc_isil` §b ile aynı
  konu) — nominal değer PDN hesabında YANILTICIDIR.

## 3. Ekranlama (Shielding) ve ESD

1. Kullanıcının eriştiği her konnektör bir ESD giriş noktasıdır. Zincir:
   **konnektör → TVS/koruma elemanı → (çok kısa) GND → seri eleman → IC.**
   TVS her zaman IC'den ÖNCE, konnektör tarafında.
2. Kablo ekranı (shield) topraklama üç okuldan biriyle yapılır (doğrudan
   GND / kapasitör+paralel direnç / ferrit) — kesin doğru cevap yok, kasa/
   kablo mimarisine bağlı. **Uygulanabilir karar:** yerleşimde üçünü de
   destekleyen bir ayak izi bırak (aynı pad çiftine 0Ω/kapasitör/ferrit
   takılabilsin), birini monte et, kalanları DNP.
3. Ferrit boncuk seçiminde DC-bias altında empedansın çöktüğünü unutma —
   sıfır-bias `Z@100MHz` ile seçim yapma.

## 4. Stitching Via Yoğunluğu — ÖLÇÜLEBİLİR kontrol

`pcbnew_koprusu.py::stitch_yogunlugu_kontrolu(board_path, f_diz_ghz, er_eff)`
gerçek karttan iki şeyi ölçer:
- Kart kenarı boyunca örneklenen noktalarda en yakın GND via mesafesi,
- Her katman-geçişi (via) etrafında en yakın GND via mesafesi (dönüş yolu).

Hedef aralık λ/20'den türetilir; **frekansı saat hızından değil kenar
hızından (`f_knee ≈ 0.35/t_r`) al** — 100MHz saat 500ps kenarla 700MHz'e
kadar enerji taşır. `f_diz_ghz` parametresine saat frekansını DEĞİL, f_knee
tahminini ver. GND via yoksa fonksiyon `KAPSAM_YOK` döner — "via yok, o
yüzden ihlal de yok" sahte bir PASS olurdu, bu yüzden ayrı durumla işaretli.

Tasarım AŞAMASINDA (henüz board yokken) hedef aralığı önceden hesaplamak
için `emi_emc_kural_motoru.stitching_max_araligi_mm(f_diz_ghz, er_eff)`
kullanılır — AYNI fizik (`C_MPS` sabiti `pcbnew_koprusu.py`'den ithal
edilir, tek kaynak gerçeklik), ama `pcbnew`/gerçek board GEREKTİRMEZ.
Board hazır olunca `stitch_yogunlugu_kontrolu()` GERÇEK ölçümü yapar;
ikisi BİRLİKTE kullanılır (biri tasarım hedefi, diğeri gerçek-board kanıtı).

## 4b. 3W / 20H Kuralları (`emi_emc_kural_motoru.py`)

İki ek TASARIM AŞAMASI kuralı (board olmadan, sadece stackup/routing
planından hesaplanabilir — Faz 2-3'te, routing'den ÖNCE karar verilmeli):

1. **3W (crosstalk):** iki yüksek hızlı sinyal yolu (SPI/I2C/USB/diferansiyel
   çift dışındaki tek uçlu hatlar) arası merkez-merkez mesafe ≥ iz genişliği
   × 3 (`w_3w()`/`uc_w_kontrolu()`). Netclass pattern'lerine bu hedef
   `ipc_dru_koprusu.uc_w_kuraline_cevir()` ile `.kicad_dru` clearance
   kuralı olarak yazılabilir (kenar-kenar değeri kullanılır — merkez-merkez
   İLE KARIŞTIRMA, en sık yapılan 3W hatası budur).
2. **20H (kenar ışıması):** güç düzlemi, GND düzleminden kart kenarında
   ≥ dielektrik kalınlığı × 20 İÇERİDE olmalı (`h_20h_setback_mm()`/
   `yirmi_h_kontrolu()`). Bu, `.kicad_dru`'ya YAZILAMAZ (KiCad custom rule
   dilinde "plane setback" constraint tipi yok) — copper pour/zone kenar
   ofseti olarak yerleşimde/zone tanımında elle uygulanmalı, bu fonksiyon
   sadece HEDEF sayıyı verir ve sonradan Python tarafında denetler.

Her ikisi de FCC/CISPR'ın kendisinin verdiği sabit sayı DEĞİL, EMC pratiğinde
yaygın tasarım sezgiselidir (bkz. modülün başlığındaki dürüstlük notu) —
gerçek uyumluluk yalnızca lab ölçümüyle kanıtlanır, bu kurallar SADECE
pre-compliance hazırlığıdır.

## 5. Termal Yönetim

1. `pcb_stackup_planner.py`'nin mevcut termal fonksiyonları (termal via
   sayısı, güç elektroniği bakır kontrolü) burada TÜKETİLİR — bu skill onları
   TEKRAR ÜRETMEZ, sadece EMI ile kesişen kararları (ör. termal via dizisinin
   GND stitching ile çakışıp çakışmadığı) koordine eder.
2. Termal ve gürültüye-hassas parçaları ZIT köşelere yerleştir
   (MASTER_RULEBOOK Faz 4 kontrol listesi maddesi) — ısı kaynağı + hassas
   analog girişi yan yana koyma.
3. Isı yayılımını bakır ALANI değil düzlem SÜREKLİLİĞİ belirler — iç
   katmandaki bağlantısız bakır bile θ_ja'yı düşürür, ama kazanç doyuma girer
   (nicel göstermeden "daha fazla bakır her zaman iyidir" deme).

## Kabul Kriterleri

- [ ] Topraklama stratejisi (tek-nokta / çoklu-nokta) bilinçli seçilmiş ve
      yazılmış, tesadüfen oluşmamış.
- [ ] `check_reference_plane_continuity()` ile referans düzlemi sürekliliği
      ÖLÇÜLEREK kanıtlanmış (gözle bakmak yeterli değil).
- [ ] Kart-dışına çıkan her arayüzde filtre/choke ayak izi ayrılmış (DNP
      olsa bile).
- [ ] `stitch_yogunlugu_kontrolu()` PASS (veya KAPSAM_YOK ise bu açıkça
      raporda görünüyor, sessizce PASS sayılmamış).
- [ ] 3W kuralı (`uc_w_kontrolu()`) yüksek hızlı hat çiftlerinde PASS; hedef
      `.kicad_dru`'ya yazıldıysa (`uc_w_kuraline_cevir()`) gerçek DRC ile
      SENİN makinende ayrıca doğrulandı (bkz. modülün DOĞRULAMA DURUMU notu).
- [ ] 20H kuralı (`yirmi_h_kontrolu()`) güç/GND düzlem çifti için PASS.
- [ ] ESD zinciri sırası doğru: konnektör → TVS → IC (ters değil).
- [ ] Shield/ekran topraklama kararı belgeli; üç seçenekli ayak izi bırakıldı.
- [ ] Dekuplaj yerleşimi ≤1.5mm; termal ve hassas parçalar zıt köşelerde.

İlgili modüller: `pcb_stackup_planner.py` (RF stitching/guard-ring/yalıtım),
`kicad_koprusu.py::check_reference_plane_continuity`, `pcbnew_koprusu.py::
stitch_yogunlugu_kontrolu`, `emi_emc_kural_motoru.py` (3W/20H/via-stitching
tasarım hedefleri), `ipc_dru_koprusu.py::uc_w_kuraline_cevir` (3W'nin
`.kicad_dru` karşılığı). İlgili skill'ler: `pcb-layout` (Faz 5 doğrulama
kapısına bu skill'in kabul kriterleri de dahil edilmeli), `schematic-design`
(topraklama/TVS zinciri topolojik karar Faz 2'de verilir).
