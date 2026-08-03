# 10 — Tam Otonomluk Engel Raporu

> Tarih: 2026-07-31
> Kapsam: `pcb-tool-v2` kod tabanı (tüm `*.py`), `CLAUDE.md`, `.claude/skills/*`, `MASTER_RULEBOOK.md`
> Amaç: Kullanıcının "bütün dosyada full otonomluğu engelleyen neler mevcut" sorusuna satır satır cevap.
> Yöntem: `NEEDS_HUMAN` (64 eşleşme), `NotImplementedError` (22 eşleşme), `import pcbnew` (24 eşleşme), doküman onay noktaları tarandı ve her bulgu üç sınıfa ayrıldı.

## Sınıflandırma

| Sınıf | Anlam | Otonomluğa etkisi | Kaldırılabilir mi |
|-------|-------|-------------------|-------------------|
| **D1** | Gerçek kod engeli (placeholder / eksik entegrasyon) | Akışı HARD-STOP yapar | Evet, kod yazarak |
| **D2** | İşaretli durma noktası (`NEEDS_HUMAN` döndüren mantık) | Koşullu durma | Evet, karar mantığını "belgeli otonom karar"a çevirerek |
| **D3** | Politika durağı (doküman seviyesinde onay beklentisi) | Koşullu durma | Kural değişikliğiyle, AMA bazıları bilinçli güvenlik kapısı |

---

## D1 — Gerçek kod engelleri (NotImplementedError / eksik altyapı)

### D1.1 FreeRouting zinciri — KiCad 10'da kullanılamaz
- **`uretim_zinciri_koprusu.py:128`** — `dsn_disa_aktar()` `FreeRoutingDesteklenmiyorHatasi` fırlatıyor.
- **Doğrulanmış gerekçe (kod içi dokümantasyon, satır 103-112):** KiCad 10 `kicad-cli pcb export` alt komutları `3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl, ipc2581, ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, svg, u3d, vrml, xao` — **`dsn` yok**.
- Aynı engel zinciri: `freerouting_calistir()` (satır 192), `ses_iceri_aktar()` (satır 229) — hepsi `FreeRoutingDesteklenmiyorHatasi`.
- **Sonuç:** `router=freerouting` seçeneği fiilen ölü; `pcb-layout SKILL.md:177` bunu açıkça NEEDS_HUMAN işaretliyor.
- **Otonom çözüm seçenekleri:**
  1. DSN'i kendimiz üret (KiCad 6/7 Specctra DSN formatını `.kicad_pcb`'den üreten yerli bir exporter yaz).
  2. FreeRouting'i tamamen devre dışı bırak ve otonom Python router'ı (zaten var: `otonom_kurtarma_motoru.py` + `otonom_python_router.py`) tek doğrulama kaynağı yap.
  3. Güncel FreeRouting'in `.kicad_pcb`'yi doğrudan okumasını doğrula (kod içi not satır 120-122: DOĞRULANMADI).

### D1.2 JLCPCB DFM API — placeholder
- **`uretim_zinciri_koprusu.py:443`** — `jlcpcb_dfm_kontrolu()` (üretim zinciri Faz 8 ek kontrolü) `NotImplementedError`.
- **Etki:** Üretim öncesi ek DFM API katmanı planlandı ama yok; yerel `fabrika_dfm_kontrolu()` (pcb_stackup_planner.py) yedekte kalıyor. Kısmi engel.

### D1.3 Nexar/Octopart API — placeholder
- **`cad_api_koprusu.py:200`** — `varlik_sorgula()` (footprint/parça doğrulama) gerçek `api_token` verilirse `NotImplementedError`. `api_token=None` ise `kaynak="TBD"` ile boş sonuç döner (satır 189-199).
- **`bom_lifecycle_koprusu.py:90`** — `nexar_sorgula()` `api_key` verilirse `NotImplementedError`; `None` ise `kaynak="TBD"` döner (satır 88-89).
- **Etki:** Gerçek stok/lifecycle/footprint verisi alınamıyor. `kaynak="TBD"` yolu sessizce devam ettiği için BOM akışı çalışıyor ama risk puanlaması gerçek dünya verisine dayanmıyor.
- **Otonom çözüm:** API entegrasyonu yazılmalı VEYA offline bir parça veritabanı (kullanıcı tarafından doldurulan MPN+lifecycle+stok CSV) altyapıya bağlanmalı.

### D1.4 pcbnew altyapı bağımlılığı
- **`dfm_emc_check.py:30`** — modül seviyesinde `import pcbnew`; venv'de pcbnew yok → modül hiç yüklenemiyor, DFM/EMC taraması koşulamıyor.
- **`via_stub.py:51`** — `import pcbnew`.
- **`pcb_carpisma_radari.py:152,318`** — fonksiyon içinde koşullu/lazy `import pcbnew` (mock ile test edilebilir kalmış).
- **`pcbnew_koprusu.py`** (satır 27, 85, 142, 180, 220, 255, 283, 349) — `import pcbnew`; modül kendisi "pcbnew yok" senaryosu için yazılmış.
- **`topolojik_router_koprusu.py:593`** — lazy `import pcbnew`.
- **Çözüm:** KiCad 10'un Python'unu kullanmak (`C:\Program Files\KiCad\10.0\bin\python.exe`) veya pcbnew bağımlılığını lazy/opsiyonel yapıp `.kicad_pcb` metin ayrıştırma yoluna düşmek.

---

## D2 — İşaretli durma noktaları (`NEEDS_HUMAN` döndüren mantık)

### D2.1 BOM risk skoru → pin-uyumlu yedek yok
- **`bom_lifecycle_koprusu.py:199,215`** — `risk_skoru_hesapla()` > 0.5 ve `find_pin_compatible()` aday bulamazsa `NEEDS_HUMAN`. (MASTER_RULEBOOK.md:50 aynı kural.)
- **Otonom çözüm:** "bulunamadı" kararını **belgeli otonom karar** haline getir: parçayı `TBD/uyarı` etiketiyle ilerlet, riski rapora işle, akışı durdurma.

### D2.2 DFM/DFA KAPSAM_YOK → genel_sonuc NEEDS_HUMAN
- **`ipc6012_dfm_motoru.py:259-271`** — bir kontrol hiç veri almadıysa (`KAPSAM_YOK`) sonuç `NEEDS_HUMAN` (sessiz PASS yasağı).
- **`ipc_a_610_dfa_motoru.py:346-351`** — aynı disiplin (satır 350).
- **`emi_emc_kural_motoru.py:319-323`** — `genel_sonuc`: `FAIL > NEEDS_HUMAN(KAPSAM_YOK) > PASS`.
- **Etki:** Veri eksikliği = durma. Bu bilinçli bir güvenlik özelliği (testlerle doğrulanmış: test_ipc6012_dfm_motoru.py:175-184).
- **Otonom çözüm:** KAPSAM_YOK kaynaklarını (ölçüm verisi kimden geliyor) otomatik üretebilmek → veri üretim zincirini tamamlamak. Örn. DRC/ERC verisini pcbnew üzerinden otomatik çekip motora beslemek.

### D2.3 Termal bariyer çözülemezse
- **`ecad_mcad_termal_kopru.py:382`** — web genişliği `MIN_WEB_GENISLIGI_MM` altındaysa `-> NEEDS_HUMAN`. Ayrıca satır 277, 279, 325, 344 yorum düzeyinde.
- **Otonom çözüm:** alternatif termal stratejiler zinciri (farklı katman, termal vias, parça yerleşimi) denendikten sonra ancak durma.

### D2.4 Topolojik router kararsız kaldığında
- **`topolojik_router_koprusu.py:323,455,506`** — katman verisi yoksa / eğik iz yönü belirsizse / itip-kaydırma önerilemezse `None` döner → çağıran `NEEDS_HUMAN` raporlar.
- **Otonom çözüm:** `otonom_kurtarma_motoru.py` zaten 3 katmanlı merdiveni sunuyor; ama en sonda (satır 280-285) hepsi tükenirse `needs_human=True`.

### D2.5 Üretim çıktıları kontrolü bilinçli atlama
- **`uretim_ciktilari_cli.py:121,132,148`** — gerçek-board DFM kontrolü `--gercek-board-kontrolu-atla` ile atlansa bile sonuç `NEEDS_HUMAN` işaretlenir (PASS sayılmaz).
- **`test_uretim_ciktilari_cli.py:130-147`** — bu davranış test edilmiş.
- **Otonom çözüm:** gerçek-board kontrolünü pcbnew ile çalıştırılabilir kılmak (bkz. D1.4) — böylece atlama yoluna hiç gerek kalmaz.

### D2.6 Diğer NEEDS_HUMAN referansları (mekanizma/kayıt)
- **`hata_hafizasi.py:88`** — `Sonuc.NEEDS_HUMAN` enum değeri (mekanizma, kendi başına engel değil).
- **`kicad_koprusu.py:615,647`** — doğrulama kaydı şablonunda "Ölçülen" hücresi elle yazılır; sonuç PASS/FAIL/NEEDS_HUMAN.
- **`pcb_carpisma_radari.py`** — yerleşim çakışma radarı; pcbnew gerektirir (D1.4).

---

## D3 — Politika durakları (doküman seviyesi, bilinçli)

### D3.1 CLAUDE.md "Ne zaman dur ve kullanıcıya sor" (satır 678-697)
Onay beklenen 7 durum:
1. **Faz 0'da gereksinim belirsiz** (hedef kullanım, güç tipi, form-faktör verilmemiş).
2. **Parça stoksuz/Obsolete + pin-uyumlu yedek yok** (D2.1 ile aynı kapı).
3. **Aynı DRC hatası, kaçış stratejisinden sonra 2 kez daha tekrarlıyor** (3. kez = NEEDS_HUMAN).
4. **Herhangi bir feedback döngüsü 3 kez aynı sonucu verirse** (BOM→stackup, escape→routing, DFM→stackup).
5. **`TEST/routing_plan.md` üretildikten sonra kullanıcı onayı BEKLENİR — "onaysız tek iz çizilmez"** (satır 689-691).
6. **design-checker skill'i FAIL verirse** → bulgular özetlenip onay alınır.
7. **`DATASHEETS/`'te resmi datasheet bulunamazsa.**

### D3.2 `pcb-layout SKILL.md:182-184,195-196`
- routing_plan.md onayı, CLAUDE.md'nin "onay noktaları dışında durma" kuralının **bilinçli istisnası** olarak tanımlı.
- Faz 4 ön koşulu: Aşama 3.6 (`.kicad_dru` kilidi) + Aşama 3.7 (`TEST/routing_plan.md` onayı) tamamlanmadan routing başlamaz.

### D3.3 `main.py:9-11`
- Şematik/wire çizimi ve freerouting komutları bilinçli olarak CLI'ye dahil edilmemiş — `pcbnew` + insan onayı (routing_plan.md) gerektirdikleri için. "Sessizce gizlenemezler (bkz. MASTER_RULEBOOK 'Ne zaman dur')."

### D3.4 MASTER_RULEBOOK.md onay notları
- satır 10 (ULDO güç topolojisi tercihi "kullanıcı onayıyla kabul edilir"),
- satır 102 (`mekanik_dxf_koprusu.py` çapa hatası >0.5mm → "otomatik toleransla düzeltme YAPILMAZ, insan onayı gerekir"),
- satır 95 (HANDOVER.md — şematik→PCB geçişinde Niyet/Kısıt aktarımı zorunlu; uyulamazsa NEEDS_HUMAN).

### D1.5 — Fine-pitch konnektörden çıkan sıkı-eşleşmeli (coupled) diferansiyel çift: "pair twist" eksikliği
> **Kaynak oturum:** `cm4-io-test` (CM4 taşıyıcı kart), 2026-08-03, Gigabit Ethernet
> J1→ESD (TPD-benzeri diyot dizisi) escape'i. Kod: `cm4-io-test/TEST/build_astar_tracks.py`
> + `coupled_astar_search.py` + `coupled_astar_router.py` (pcb-tool-v2'nin GENEL bir
> modülü DEĞİL, proje-özel bir script seti — ama altta yatan algoritmik boşluk
> `pcb_highspeed_escape.py`/`topolojik_router_koprusu.py`'nin kapsadığı problem
> sınıfının TAM ORTASINDA, bu yüzden buraya kaydediliyor).

Bir A*-tabanlı "coupled corridor" router (merkez hat + sabit ±OFFSET ile P/N
ayrımı), P/N kimliğinin (`side = +1/-1`) rotanın BAŞINDA (konnektör pininden
kaçış) belirlenip TÜM rota boyunca SABİT tutulması yaklaşımıyla yazıldığında,
şu üç bağımsız (ayrı ayrı ölçülüp doğrulanmış) hata sınıfıyla karşılaşıldı:

1. **Düz kaçış konnektörün kendi pinleriyle çakışır:** 0.4mm pitch'li bir
   konnektörden (örn. DF40 B2B) her pini kendi Y'sinde düz çizmek, komşu pinin
   kaçış hattının İÇİNDEN geçer (matematiksel ispat zaten `AI_HANDOVER_REPORT.md`'de
   vardı, bu oturum onu GERÇEK DRC ile de kanıtladı: `tracks_crossing`/`shorting_items`).
2. **Küçük satır-içi Y fanı yetersiz:** konnektör sadece hedef 8 pin değil,
   AYNI satırda onlarca ilgisiz pin (GPIO/LED/GND) daha barındırıyorsa (gerçek
   `board.GetFootprints()` sorgusuyla doğrulandı: J1 tek satırda 0.4mm pitch'te
   15+ ilgisiz pin daha içeriyordu), küçük bir Y fanı (±0.15/±0.45mm) bu
   pinlerin ÇOĞUNU hâlâ ihlal ediyor (`solder_mask_bridge` 124 örnek). **Çözüm
   (bu oturumda uygulandı, işe yaradı):** konnektöre DİK (perpendicular) kaçış
   — satırın tamamen DIŞINA (native X sabit, sadece Y'de 1.0mm) — pitch'ten
   bağımsız, satırda kaç pin olursa olsun genellenebilir.
3. **ÇÖZÜLEMEDİ — "pair twist" eksikliği:** rota, kaçıştan hedefe giderken
   yeterince (~30-45°+) yön değiştirirse, "P/N'nin rotayı boyunca hep aynı
   tarafta kalması" (kendi kendine kesişmeyen, topolojik olarak tutarlı) kuralı
   ARTIK hedef pad'in GERÇEK N/P dikey diziliminiyle UYUŞMAYABİLİR — çünkü sabit
   sağ/sol kuralı rotanın rotasyonuna göre hangi fiziksel üst/alt düzenin
   ortaya çıkacağını BELİRLER, seçilemez. Sonuç: son adımın (offset polyline
   DEĞİL, doğrudan sabit pad koordinatına çekilen düz "stub") kendi kendini
   kesmesi (`tracks_crossing`/`shorting_items`, gerçek DRC'de doğrulandı, referans
   ucunu kaçıştan hedefe çevirmek de ÇÖZMEDİ — ayrıca doğrulandı, 90→91 ihlal,
   anlamlı fark yok). **Doğru çözüm (bilinen ama BU OTURUMDA UYGULANMADI):**
   P ve N'in In2.Cu (ara katman) geçişi sırasında KADEMELİ (staggered, AYNI ANDA
   DEĞİL — P rotanın başında, N rotanın sonunda kendi "twist"ini yapar ki uzayda
   çakışmasınlar) bir taraf değişimi (`side` işaretinin path ORTASINDA bir kez
   tersine çevrilmesi, ama P ve N'in twist NOKTALARI birbirinden UZAK tutularak).
   **Otonom çözüm önerisi:** `coupled_astar_router.py`/`_search.py` tarzı bir
   modül, `side` kararını tek bir global sabit yerine PATH BOYUNCA rotasyon
   birikimini (cumulative turn angle) izleyip, kaçış-ucu ile hedef-ucu arasında
   uyuşmazlık tespit edildiğinde OTOMATİK bir staggered-twist segmenti
   ekleyecek şekilde genişletilmeli — bu, pcb-tool-v2'nin GENEL bir modülü
   (örn. yeni bir `coupled_pair_router.py`) olarak yazılırsa, sadece bu proje
   değil HERHANGİ bir "keskin açılı fine-pitch konnektör → hedef" diferansiyel
   escape senaryosunda tekrar keşfedilmek zorunda kalınmaz.
   *(Ölçülen sonuç: `cm4-io-test` J1→ESD escape'i 47 (rip-up öncesi başlangıç,
   AI_HANDOVER_REPORT.md) → 302 (ilk coupled-router denemesi, tespit edilen 3
   alt-hatanın hiçbiri düzeltilmeden) → 90 (yukarıdaki 1-2 düzeltildikten
   sonra) DRC ihlaline geldi — kalan ~90'ın büyük kısmı bu "pair twist"
   sorununun DOĞRUDAN sonucu, 14 `shorting_items` + 5 `tracks_crossing`.)*

   **3. deneme (aynı oturum, kökten farklı strateji — KISMEN başarılı):**
   coupled-offset + sabit-taraf modelini TAMAMEN terk edip, 8 net'i BAĞIMSIZ
   A* hedefleri olarak (paylaşılan merkez hat/offset formülü YOK, her net
   kendi kopyasını arar, ÖNCEKİ yerleştirilmiş HER net — kendi P/N eşi dahil
   — kendisi için GERÇEK bir engel) yeniden yazan `independent_net_router.py`
   ile denendi. Sonuç: **`tracks_crossing` 5→0'a düştü** (yöntemin kendi
   iddiasını doğrular: bağımsız engel-kaçınma, "pair twist" sınıfı hatayı
   YAPISAL olarak imkansız kılıyor) ve **`shorting_items` 14→6'ya düştü**
   ama **sıfıra inmedi**. Kalan 6'nın kök nedeni FARKLI bir sınıf: J1'in
   0.4mm pitch'i, her net'in KENDİ (diğer netlerden bağımsız olarak çizilen,
   A*-doğrulanmadan elle eklenen) dik kaçış kütüğünün, KOMŞU net'in (aynı
   çiftin P/N eşi, sadece 0.4mm ötede) A*-bulduğu rotasıyla marjinal
   çakışmasıdır — `INFLATE` payı (0.3mm) 0.4mm pitch'e göre yeterli
   MARJ bırakmıyor. **Bir düzeltme DENENDİ, GERİ ALINDI:** tüm 8 kaçış
   kütüğünü ARAMA BAŞLAMADAN ÖNCE toplu işaretlemek mantıklı görünüyordu
   ama GERÇEK ölçümde 4/8 net'i "NO PATH FOUND"a düşürdü (bir net'in kendi
   başlangıç hücresinin TÜM komşuları, 0.4mm ötedeki eş net'in kütüğü
   tarafından bloklandı) — düzeltme sorunu ÇÖZMEK yerine BAŞKA (daha kötü)
   bir sorun yarattığı için geri alındı, kod tabanında GERİ ALINDIĞI
   YORUMLA birlikte duruyor (bkz. `independent_net_router.py::main()`).
   **Sonuç kaydı:** `cm4-io-test/DOCS/karar_birimleri.json`'a
   `karar_id="j1-pair-twist-cozumu"`, `durum=ACIK` olarak açık bırakıldı —
   3 farklı strateji denenip hiçbiri sıfır ihlale ulaşmadı, insana
   devredilmeden (elle çizim ÖNERİLMEDİ) açıkça tanımlı, gelecekte
   otomatik/algoritmik çözülmesi beklenen bir problem olarak kayıtlı.
   **Board disiplini:** 3. denemenin kalan 7 `shorting_items`'ı (hepsi
   sinyal-sinyal, hiçbiri güç rayına dokunmuyor) board dosyasında
   BIRAKILMADI — oturum sonunda J1'in 8 net'i Görev 1 rip-up disipliniyle
   tekrar temiz/unrouted airwire durumuna döndürüldü
   (`drc_session_truly_final.json`: `shorting_items=0`,
   `tracks_crossing=0`, 27 kalan ihlalin TAMAMI önceki oturumdan/PCIe ile
   ilgili). 3. denemenin kodu/verisi `TEST/` içinde referans için
   duruyor, board'a UYGULANMIYOR.

### D1.6 — `PCB_VIA.GetWidth()` katman argümanı olmadan çağrılırsa GUI assert pop-up'ı
> **Kaynak:** Kullanıcı raporu, 2026-08-03 — KiCad 10'da gerçek bir debug
> assert pop-up'ı ("GetWidth called without a layer argument") headless bir
> pcbnew script'i çalışırken çıktı ve süreci bloke etti (bkz. `DOCS/13_Durum_Cozucu_FreeRouting_Olayi.md`'deki
> "GUI pop-up otonom akışı kilitler" deseniyle AYNI risk sınıfı, farklı kök neden).

KiCad 10'un `PCB_VIA` sınıfı artık katman-başına farklı genişlik
destekleyebiliyor (blind/buried/microvia stack'leri için); bu yüzden
`PCB_VIA.GetWidth()` PARAMETRESİZ çağrılırsa bir debug assert (GUI pop-up,
headless bir sürecin sonsuza dek asılı kalmasına yol açabilir) fırlatıyor.
Kod tabanında GERÇEK (test edilmemiş, sadece `board.GetTracks()`'i FİLTRESİZ
gezip her elemana `.GetWidth()` çağıran) iki örnek bulundu ve düzeltildi:
`pcbnew_koprusu.py::annular_ring_kontrolu()` ve `dfm_emc_check.py::check_annular()`
— ikisi de `v.GetWidth()` → `v.GetWidth(v.TopLayer())` oldu. Üçüncü bir
örnek (`pcbnew_koprusu.py:188`) İNCELENDİ ve GÜVENLİ bulundu — `en_yakin`
değişkeni `GetClass() == "PCB_TRACK"` ile ÖNCEDEN filtrelenmiş, asla bir via
olamaz. **Otonom çözüm:** `pcbnew`'e dokunan HER yeni modül, `board.GetTracks()`
üzerinde gezinirken `item.Type() == pcbnew.PCB_VIA_T` kontrolü OLMADAN
`.GetWidth()` çağırmamalı — bu artık bir kod-inceleme kontrol maddesi olarak
`CLAUDE.md`'nin "Durum Çözücü Kalıcı Kuralları" bölümüne eklenmeli (henüz
eklenmedi, bu D1.6 kaydı o eklemenin YERİNE geçmiyor, sadece bulguyu tutuyor).

---

## Özet ve önerilen çözüm sırası

### Kritiklik tablosu

| # | Engel | Dosya:satır | Etki | Zorluk |
|---|-------|-------------|------|--------|
| 1 | pcbnew yüklenemiyor | dfm_emc_check.py:30, via_stub.py:51, pcbnew_koprusu.py | DFM/EMC, gerçek-board, yerleşim radarı çalışmıyor | Düşük (KiCad 10 Python'u) |
| 2 | routing_plan.md onayı | CLAUDE.md:689-691, pcb-layout SKILL.md:182 | Routing başlayamaz | Politika değişikliği |
| 3 | FreeRouting DSN yok | uretim_zinciri_koprusu.py:128 | Freerouting router'ı ölü | Orta (DSN exporter yaz) |
| 4 | 3-kez tekrar → NEEDS_HUMAN | CLAUDE.md:682-688, otonom_kurtarma_motoru.py:285 | Zor yerleşimde durur | Karar mantığı değişimi |
| 5 | Nexar/Octopart placeholder | cad_api_koprusu.py:200, bom_lifecycle_koprusu.py:90 | Stok/lifecycle verisi yok | Orta (offline DB + CSV) |
| 6 | KAPSAM_YOK → NEEDS_HUMAN | ipc6012_dfm_motoru.py:270, ipc_a_610_dfa_motoru.py:350, emi_emc_kural_motoru.py:323 | Veri eksikliğinde durur | D1.4 çözülürse çoğu düşer |
| 7 | JLCPCB DFM API placeholder | uretim_zinciri_koprusu.py:443 | Ek DFM katmanı yok | Düşük (yerel yedek var) |

### Önerilen uygulama sırası (bağımlılık zinciri)
1. **D1.4 → pcbnew'u KiCad 10 Python'una bağla** (DFM/EMC + gerçek-board + yerleşim radarı + KAPSAM_YOK kaynağı birden çözülür; D2.2 ve D2.5'in büyük kısmı düşer).
2. **D3.1/5 + D3.2 → routing_plan.md onayını "otomatik onay (audit log)" modeline çevir** — rapor yine üretilir, ama beklenmez; topoloji değişikliği loglanır.
3. **D2.4 + D2.6 → 3-kez tekrar kuralını "belgeli otonom karar"a çevir** — denemeler + gerekçe rapora yazılır, durmaz.
4. **D1.1 → ya DSN exporter yaz ya da FreeRouting'i resmen kapat** (SKILL.md'deki `router=freerouting` seçeneğini python/manuel-diffpair'e sabitle).
5. **D1.3 → offline parça veritabanı (CSV) altyapısı** ekle; nexar opsiyonel kalır.
6. **D2.1, D2.3, D3.1/2, D3.4 → stoksuz+bilinçli topoloji ödünlerini "uyarı + rapora işle" olarak otonomlaştır.**

> **Saklanması önerilenler:** Faz 0 belirsiz gereksinim (sensör çözümlemeden tasarım yapmak tehlikeli) ve design-checker FAIL durumu — bunlar otonom karara devredilirken bile "dokümante edilmiş karar" olmalıdır; birebir kaldırılmamalıdır.
