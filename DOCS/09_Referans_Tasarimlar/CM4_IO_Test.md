---
type: pcb-reference
tags:
  - pcb/referans
  - pcb/cm4-io-test
---

# CM4 I/O Test Kartı (cm4-io-test)

**Klasör:** `cm4-io-test\` (ayrı proje, ayrı git deposu — bu vault'a
`[[karar_birimleri]]`/`[[bagimsiz_dogrulama]]` gibi bağlanan pcb-tool-v2'nin
DIŞINDA yaşıyor, bkz. `OBSIDIAN_VAULT.md`'deki "Proje-Araç Köprüsü Kuralı").

| Alan | Değer |
|------|-------|
| Durum | Şematik/ERC tamam. PCB: yüksek hızlı arayüzlerin çoğu (PCIe, HDMI0, HDMI1) DRC-temiz; J1 Gigabit Ethernet 8 net'i **unrouted airwire** (Görev 2 "pair twist" + Görev E FreeRouting/DSN diff-pair veri kaybı — İKİ bağımsız sebeple çözülemedi); 259 düşük hızlı net'ten **37/103 escape+cap ile denendi** (board'a YAZILMADI, eşik altı) VE **gerçek FreeRouting denendi ama yakınsamadı** (board'a hiç YAZILMADI). *(GÜNCEL DEĞİL — bkz. 2026-08-04 oturumu aşağıda: `unconnected_items` gerçekte 269 çıktı, bu satırın "37/103" ve "PCIe/HDMI0/HDMI1 DRC-temiz" iddiaları HDMI0/HDMI1 için YANLIŞ bulundu — pad var, aynı-adlı track var ama ARADAKİ BAĞLANTI hiç yok.)* |
| Bu oturumdaki en son DRC | `drc_after_freerouting_attempt.json` (2026-08-03, Görev E sonrası) — 27 ihlal (21 via_dangling + 4 lib_footprint_mismatch + 2 silk_over_copper, HEPSİ önceki oturumdan/PCIe ile ilgili), 269 unconnected_items. `shorting_items=0`, `tracks_crossing=0` — board hâlâ TEMİZ; bu oturumun HİÇBİR routing denemesi (escape+cap, gerçek FreeRouting) board'a YAZILMADI. |
| Kart | 4 katman (F.Cu/In1.Cu=GND/In2.Cu/B.Cu), CM4 taşıyıcı kart, DF40 B2B (J1/J2), USB-C (J3), GbE MDI (J1→ESD), PCIe, dual HDMI, MIPI CSI/DSI |

## Önceki oturumun bıraktığı durum (2026-08-02) — RAPOR-VERİ UYUMSUZLUĞU BULGUSU

Önceki oturumun `AI_HANDOVER_REPORT.md`'si Ethernet netlerinin "ripped up to
clean, unrouted airwires" olduğunu ve board'un "safe, DRC-stable state"te
olduğunu iddia ediyordu. Bu oturum başında **programatik olarak doğrulanınca**
(raporun kendi verdiği 47 violation rakamıyla eşleşen `drc_truly_final.json`
okunarak), bu netler üzerinde **5 gerçek `shorting_items`** (biri
`CARRIER_3V3` güç hattına kısa devre) ve **3 `tracks_crossing`** bulundu —
board hiç "stable" değildi. Bu somut olay, `MASTER_RULEBOOK.md` BÖLÜM 0'a
eklenen "Rapor-Veri Tutarlılığı" maddesinin GEREKÇESİ oldu (bkz. o madde).
**Ders:** bir raporun "temiz"/"stable" iddiası, o oturumun ürettiği EN SON
ham DRC JSON'u okunmadan asla yazılmamalı — bu doküman da dahil, aşağıdaki
her rakam `drc_task2_final.json`'dan doğrudan okunmuştur.

## 2026-08-03 oturumu — ne yapıldı

### Görev 1 — ETH_TRD0-3 rip-up (TAMAMLANDI, doğrulandı)
F.Cu'daki 8 çapraz iz (J1→ESD hop2) `pcbnew` ile tamamen silindi. Taze DRC
(`drc_task1_ripup.json`): `shorting_items=0`, `tracks_crossing=0` — GERÇEKTEN
sıfır, sayılarak doğrulandı.

### Görev 2 — J1 escape yeniden çizimi (KISMEN TAMAMLANDI — DRC temiz DEĞİL)
`TEST/coupled_astar_router.py` + `coupled_astar_search.py` +
`build_astar_tracks.py` (proje-özel, custom A* coupled-pair router) 3 kez
yeniden tasarlandı, her seferinde GERÇEK DRC ile ölçülüp bir sonraki hatanın
kök nedeni bulundu:

1. **Düz (aynı-Y) kaçış** — J1'in 0.4mm pitch'li satırında komşu net'lerin
   kaçışlarıyla ÇAKIŞTI (`tracks_crossing` gerçek DRC'de doğrulandı).
2. **Küçük satır-içi Y fanı** (±0.15/±0.45mm) — J1'in AYNI satırında hedef
   8 pinin YANINDA 15+ ilgisiz GPIO/LED/GND pini daha olduğu keşfedildi
   (gerçek `board.GetFootprints()` sorgusuyla); küçük fan bunların çoğunu
   hâlâ ihlal etti (`solder_mask_bridge` 124 örnek).
3. **Dik (perpendicular) kaçış** (native X sabit, 1.0mm dik) — ✅ bu ikisini
   ÇÖZDÜ, `solder_mask_bridge` 124→17'ye düştü.

Ayrıca 2 ALTYAPI hatası bulunup düzeltildi:
- **Via B.Cu sızıntısı:** `PCB_VIA` varsayılan `VIATYPE_THROUGH` — sadece
  `SetLayerPair()` çağırmak F.Cu→B.Cu'ya fiziksel yayılmayı ENGELLEMEZ; via'lar
  In1.Cu (GND) + B.Cu'daki ilgisiz bakırla kısa devre yapıyordu. Fix:
  `SetViaType(VIATYPE_BLIND)`.
- **Koridor genişliği marjı eksikti:** `CORRIDOR_HALF` sadece merkez-hat-offset'i
  (0.35mm) hesaba katıyordu, iz genişliğinin yarısını (0.1mm) DEĞİL — gerçek
  bakır kenarı merkez hattan 0.45mm uzanıyordu ama şişirme sadece 0.40mm+0.20mm
  clearance = 0.60mm varsayıyordu (0.05mm açık). Fix: `CORRIDOR_HALF = OFFSET
  + TRACK_W/2`.
- **`refill_zones.py` unutulması:** script'le eklenen izler GND zone'unun eski
  dolgusuyla örtüştü (`Bölge [GND]` ile onlarca sahte-gerçek çakışma) — her
  build'den sonra zorunlu refill ile 302→242 ihlale düştü (bu bulgu zaten
  bilinen bir ders olarak kayıtlıydı, `AI_HANDOVER_REPORT.md`'de de vardı,
  BU OTURUMDA yine unutulup tekrar keşfedildi — `refill_zones.py`'nin
  pipeline'a otomatik ZORUNLU adım olarak bağlanması gerektiği doğrulandı).

**3. deneme (kullanıcı talimatıyla, kökten farklı strateji):**
`TEST/independent_net_router.py` — coupled-offset modeli TAMAMEN terk edilip
8 net bağımsız A* hedefleri olarak yeniden yazıldı (paylaşılan merkez hat
yok, her net önceki TÜM netleri gerçek engel sayar). `tracks_crossing` 5→0,
`shorting_items` 14→7 (7'si de sinyal-sinyal, HİÇBİRİ bir güç rayına
dokunmuyor — doğrulandı). Kalan 7, 0.4mm J1 pitch'inde komşu netin
elle-çizilen (A*-doğrulanmamış) dik kaçış kütüğüyle marjinal çakışma. Bir
düzeltme (tüm kaçışları toplu ön-işaretleme) denendi, 4/8 net'i routesuz
bıraktığı için GERİ ALINDI. **Bu 7 ihlal board'da BIRAKILMADI** — oturum
sonunda kullanıcı talimatıyla J1'in 8 net'i Görev 1 disipliniyle tekrar
söküldü (`drc_session_truly_final.json`: `shorting_items=0`,
`tracks_crossing=0`). 3. denemenin kodu/verisi TEST/'te referans olarak
duruyor, board'a UYGULANMIYOR. Sonuç: `DOCS/karar_birimleri.json`'da
`j1-pair-twist-cozumu` (`durum: ACIK`) olarak kayıtlı — detay:
`DOCS/10_Otonomluk_Engel_Raporu.md` D1.5.

**Çözülemeyen kök sorun ("pair twist"):** rota, kaçıştan hedef diyot pedine
giderken ~30-45°+ döndüğünde, P/N'in rota boyunca SABİT bir tarafta kalması
(kendi kendine kesişmeyen) kuralı hedef pedin GERÇEK N/P dikey diziliminiyle
UYUŞMUYOR — son adım (offset polyline DEĞİL, sabit ped koordinatına çekilen
düz stub) kendi kendini kesiyor. Referans ucunu (kaçış↔hedef) değiştirmek
DENENDİ, ÇÖZMEDİ (90→91, anlamlı fark yok — gerçek DRC ile doğrulandı).
Detaylı analiz + önerilen genel çözüm (staggered pair-twist In2.Cu'da):
`DOCS/10_Otonomluk_Engel_Raporu.md` **D1.5**.

### Görev 3 — 259 düşük hızlı net — DENENDİ, BAŞARILI DEĞİL (board temiz bırakıldı)
`TEST/bulk_lowspeed_router.py` — 103 basit (2 pedli) net için, J1'de
kanıtlanmış "bağımsız A*" mimarisi tüm karta genellendi. 3 iterasyon:
1. İlk deneme: **58/58 routelanan net'te shorting_items** — kök neden:
   `build_base_obstacles()` GND ve `<no net>` pedlerini "zone her yeri
   bloklar" korkusuyla engel saymıyordu (ama zone/pour HİÇ ayrıştırılmıyordu
   — istisna sadece gerçek GND pinlerini görünmez yaptı). Board'dan hemen
   söküldü, düzeltildi.
2. Performans sorunu (ayrı bulgu): net sayısı arttıkça paylaşılan engel
   haritası yoğunlaşıyor, "yol yok" durumları O(kart-boyutu) tam-tarama
   gerektiriyor — 20/103 net'te 433sn, 21. net (`DSI0_D0_N`) 300sn+ sonra
   bile dönmedi. **J1'in "bağımsız A*" mimarisiyle AYNI ölçeklenme sorunu**
   (paylaşılan mutable engel durumu, 8 net'te yönetilebilir, 103'te değil).
   Sabit adım/süre sınırı (15000 düğüm, 4sn) + bounding-box (+10mm) eklendi.
3. Düzeltmelerle yeniden çalıştırma: **14/27 routelanan net'te YİNE
   shorting_items** — kök neden: J1/J2'nin 0.4mm pitch satırlarına hiç
   dik-kaçış uygulanmadı (Görev 2'nin "flat escape" hatasının aynısı, ham
   pinden direkt A* başlatıldığı için). Board'dan söküldü.

**Sonuç: gerçek net başarı oranı ~13/103.** Board TEMİZ bırakıldı
(`drc_task3_final_clean.json`: `shorting_items=0`, `tracks_crossing=0`, 27
kalan ihlalin tamamı önceki oturumdan). Açık karar:
`karar_birimleri.json: bulk-lowspeed-router-cozumu` (durum: ACIK) — gereken
düzeltme: Görev 2'deki dik-kaçış mantığının J1/J2 pinlerine genellenmesi.

### Görev 3 devamı (2026-08-03, aynı gün 2. müdahale) — escape+cap kalıcılaştırma, HÂLÂ eşik altında
Görev 2'nin dik-kaçış mantığı `TEST/connector_escape.py`'ye genelleştirildi
(`kacis_gerekiyor_mu`/`kacis_noktasi_hesapla`, J1/J2'nin gerçek pcbnew-ölçülü
satırları: Y=38.645/41.355) ve **kalıcı olarak** `bulk_lowspeed_router.py`'nin
`main()`'ine bağlandı (önceden sadece ad-hoc bir test script'inde
denenmişti). Aynı oturumda `bounded_astar.py`'nin genel `MAX_EXPANSIONS=2000`
güvenlik sınırının bu router için TEK BAŞINA yetersiz kaldığı ölçüldü:
2000'lik sınır, J1/J2 dışındaki birçok net için de meşru uzun-mesafe rotaları
(gerçek board'da ~15000 genişletmede 0.37sn'de biten bir net doğrulandı)
erken kesiyordu. Router'a özel `ESCAPE_MAX_EXPANSIONS=50000` override'ı
eklendi — kafadan seçilmedi, GERÇEK ölçümle doğrulandı (20000→22/103,
50000→37/103, 100000→43/103; 100000'de bile via-locked-island patolojisi
TETİKLENMEDİ, sadece 1 net "time" sınırına takıldı). 50000 seçildi: 100000'e
göre ~2x hızlı, kazancın çoğunu koruyor.

**Kalıcı entegrasyonla tekrar çalıştırıldı (board'a YAZILMADAN):**
`python bulk_lowspeed_router.py` → **37/103 routelandı, 66 başarısız**
(46 "expansions", 20 "exhausted"), 167sn, hiç hang/crash yok — ad-hoc
deneyle BİREBİR aynı sonuç (tutarlılık kanıtı). **Kullanıcının 50+/103
eşiği KARŞILANMADI** — bu yüzden board'a HİÇBİR ŞEY YAZILMADI. Taze DRC
(`drc_final_D_group.json`) board'un DEĞİŞMEDİĞİNİ doğruladı:
`shorting_items=0`, `tracks_crossing=0`, 27 ihlal (aynı, önceki oturumdan).

Yeni kalıcı testler: `TEST/test_connector_escape.py` (12 test, gerçek J1/J2
koordinatlarıyla), `TEST/test_bulk_lowspeed_router.py` (6 test, gerçek
board'daki bir J1 neti — `NRPIBOOT_JMP` — ile uçtan uca escape+cap kanıtı
dahil). Açık karar `karar_birimleri.json: bulk-lowspeed-router-cozumu`
GÜNCEL veriyle (20k/50k/100k cap sonuçları) hâlâ AÇIK — kalan 66 net'in
çoğu ("expansions") muhtemelen gerçekten daha yüksek cap gerektiriyor
(diminishing returns: cap 2x artışı ~+6-13 net kazandırıyor), "exhausted"
olanlar (20 net) muhtemelen gerçekten ulaşılamaz/topoloji kısıtlı — ikisi
ayrı ayrı teşhis edilmeli.

### Görev E (2026-08-03, aynı gün 3. müdahale) — gerçek FreeRouting zinciri denendi, İKİ AYRI SEBEPLE elverişsiz bulundu
Kendi yazılan A*/escape mimarisi diminishing-returns'e çarptığı için, `pcb-tool-v2`'nin
zaten Madde 3'te doğrulanmış (`dsn_disa_aktar`/`freerouting_calistir`/
`ses_iceri_aktar`) gerçek FreeRouting zincirinin bu boarda hiç uygulanmamış
olduğu fark edildi ve denendi — **canlı dosyaya DOKUNULMADAN**, `TEST/
freerouting_scratch/scratch_board.kicad_pcb` kopyası üzerinde.

**Bulgu 1 (J1 diferansiyel çift — ayrı FreeRouting çalıştırmasına GEREK
KALMADAN kanıtlandı):** `pcbnew.ExportSpecctraDSN()`'in ürettiği DSN
incelendiğinde, board'daki TÜM netlerin (ETH_TRD0-3 dahil, hatta HDMI/DSI/
CAM diferansiyel çiftleri de) tek bir düz `(class kicad_default ...)`
bloğunda listelendiği, HİÇBİR diferansiyel-çift eşleştirme/coupling
bilgisinin DSN'e yazılmadığı doğrulandı (`grep -c "(class "` → 1). Bu,
FreeRouting yakınsasa BİLE J1'in 8 ETH_TRD netini birbirinden bağımsız
tek-uçlu sinyaller olarak routelayacağı, eşit-uzunluk/paralel-eşleşme
garantisi OLMAYACAĞI anlamına gelir — J1 için bu araç zincirinin
kullanılamayacağı, ALGORİTMA kalitesinden BAĞIMSIZ, VERİ KAYBINA dayalı
kesin bir sonuçtur. `karar_birimleri.json: j1-pair-twist-cozumu`'na bu
bulgu yeni bir `seçenek` olarak eklendi.

**Bulgu 2 (259 düşük hızlı net — gerçek deneme, YAKINSAMADI):** Aynı scratch
board'un tam DSN'i (103KB) başarıyla export edildi, `freerouting_calistir()`
240sn dahili zaman aşımıyla çağrıldı. Gerçek boyutlu bu kartta (~267
unrouted net + halihazırda routed PCIe/HDMI/USB) FreeRouting ~285sn+ boyunca
YAKINSAMADI — DAHA ÖNEMLİSİ, dahili zaman-aşımı mekanizması KENDİSİ de
zamanında TETİKLENMEDİ: `freerouting_calistir()`'in zaman kontrolü
`proc.stdout.readline()`'ın (BLOCKING) her dönüşünde çalışıyor; FreeRouting
uzun bir süre stdout'a hiçbir satır yazmayınca kontrol hiç ÇALIŞMA FIRSATI
bulamadı. Süreç elle (`Stop-Process`) sonlandırıldı. **SES dosyası hiç
üretilmedi, `ses_iceri_aktar()` hiç ÇAĞRILAMADI, board'a HİÇBİR ŞEY
YAZILMADI** — taze DRC (`drc_after_freerouting_attempt.json`) ile board'un
DEĞİŞMEDİĞİ doğrulandı (`shorting_items=0`, `tracks_crossing=0`, 27 ihlal,
aynı). Bu, DOCS/12'nin (pcb-tool-v2) E1 bulgusunu ("gerçek boyutlu kartlarda
FreeRouting yavaş") DOĞRULAYIP GENİŞLETİYOR: sadece yavaş değil, zaman
aşımı mekanizmasının kendisi de bu senaryoda (uzun sessiz stdout aralığı)
güvenilmez. Bu, `uretim_zinciri_koprusu.py`'de ayrı bir düzeltme konusu
(bu görevin kapsamı DIŞINDA bırakıldı, DOKUNULMADI) —
`karar_birimleri.json: bulk-lowspeed-router-cozumu`'na yeni kısıt/seçenek
olarak eklendi.

**Sonuç:** Board'a HİÇBİR yazma işlemi yapılmadı (kullanıcı onayı
gerektiren adıma hiç gelinmedi — gerçek sonuç zaten üretilemedi). Her iki
açık karar (`j1-pair-twist-cozumu`, `bulk-lowspeed-router-cozumu`) GÜNCEL
kanıtla `ACIK` kalmaya devam ediyor; J1 için artık "hangi algoritma"dan
öte "bu araç zinciri temelden uygun değil" sonucu netleşti.

### Görev 4 (bitirme kapısı) — BAŞLANMADI
Görev 2-3 DRC-temiz olmadan bu adıma geçilmedi (kasıtlı — MASTER_RULEBOOK
fail-closed disiplini).

## Sonraki oturum için not
- `TEST/build_astar_tracks.py`'deki `p_side`/`n_side` belirleme mantığı,
  "pair twist" olmadan TAMAMLANAMAZ — bkz. yukarıdaki D1.5 referansı.
- `refill_zones.py`'yi HER `build_astar_tracks.py` çalıştırmasından SONRA,
  DRC'den ÖNCE çalıştırmayı unutma (bu oturumda bir kez unutuldu, 60 sahte
  ihlale mal oldu).
- Kalan 21 `via_dangling` + 4 `lib_footprint_mismatch` bu oturumun
  ÖNCESİNDEN kalma, bu oturumda dokunulmadı (PCIe ile ilgili, handover
  raporunda zaten "leftover cleanup" olarak not edilmişti).

---

## 2026-08-04 oturumu — pcb-tool-v2 KULLANILMADAN başladı, sonradan bağlandı

**ÖNEMLİ İTİRAF:** Bu oturum cm4-io-test üzerinde saatlerce çalıştıktan
SONRA `pcb-tool-v2`'nin varlığını fark etti (kullanıcının ayrı bir görev
için proje klasörü ararken tesadüfen bulundu) — o ana kadar tüm işler ham
`pcbnew`/`kicad-cli` script'leriyle, bu dokümandaki geçmiş bulgulardan
HABERSİZ yapıldı. Sonuç: session'ın ilk yarısında "board 0 DRC ihlaliyle
tamamlandı" gibi hatalı bir ara-sonuç rapor edildi (aşağıda düzeltildi) —
tam olarak BÖLÜM 0 "Rapor-Veri Tutarlılığı" maddesinin uyardığı hata.
**Ders (zaten MASTER_RULEBOOK'ta ama tekrar somutlaştı):** cm4-io-test
ayrı repo olsa da, bu vault'un bilgisi (özellikle FreeRouting/DSN
diff-pair kısıtı ve "37/103" bulgusu) her zaman ÖNCE okunmalı.

### Session-başı gerçek durum (kanıt: `kicad-cli pcb drc --format report --severity-all`)
Önceki oturumdan kalan DRC checker'lar (`mcp__kicad__run_drc`, proje
içi custom script) `unconnected_items` kontrolünü HİÇ YAPMIYORDU — sadece
clearance/via/footprint/silk tipi kuralları kontrol ediyordu, bu yüzden
"0 hata" görünüyordu. `kicad-cli`'nin TAM metin raporunda ayrıca basılan
`unconnected_items` sayısı ise **269** çıktı (149 net) — bu sayı aslında
zaten 2026-08-03'te bu dokümanda kayıtlıydı, sadece bu oturum başında
tekrar "keşfedildi". Doğrulanan gerçek: PCIe REFCLK/RX/TX GERÇEKTEN
routed (08-02 iddiası doğru); **HDMI0/HDMI1 İSE DEĞİL** — pad var, aynı
adlı bir track stub'ı board'un başka bir yerinde var ama ikisi arasında
FİZİKSEL BAĞLANTI YOK (08-02 raporunun "HDMI0/HDMI1 DRC-temiz" iddiası
yanlıştı, muhtemelen zone-fill sonrası bir ripup/deneme unutulmuştu).

### Bu oturumda yapılanlar (hepsi `kicad-cli pcb drc --format report --severity-all` ile adım adım doğrulandı)

1. **Kozmetik temizlik (27→0 uyarı):** 21 orphan `via_dangling` silindi
   (her biri F.Cu/B.Cu'da hiçbir track/pad'e dokunmadığı doğrulanduktan
   sonra), 4 `MountingHole_3.2mm_M3` footprint güncel kütüphaneden
   resenkronize edildi, 1 `silk_over_copper` (C3 referans yazısı) gizlendi.
2. **GND (26→0 unconnected):** `pcb-layout` skill'inin stackup tanımına
   göre (In1.Cu = kesintisiz GND) In1.Cu + B.Cu'ya GND zone eklendi (daha
   önce SADECE F.Cu'da vardı — bu, projenin KENDİ kuralına aykırı eksik
   bir stackup'tı), + 20 stitching via.
3. **CHASSIS_GND:** zone denemesi GND'yi "boğdu" (zone-öncelik çakışması,
   geri alındı); trace denemesi J7/J8'in aslında HDMI0/HDMI1'in FİZİKSEL
   konnektörleri olduğunu ortaya çıkardı ve onların sinyal pinlerine kısa
   devre yaptı (geri alındı) — hâlâ unrouted, HDMI fazına ertelendi.
4. **Güç düzlemleri (CARRIER_3V3/CM4_5V/CM4_3V3, 116→75 unconnected-pad):**
   `pcb-layout` skill'inin "In2.Cu = Bölünmüş Güç Düzlemleri" kuralına göre
   üç net için In2.Cu'da ayrı zone'lar (öncelik: en küçük/lokal net en
   yüksek öncelik) + her SMD pad için escape via (F.Cu/B.Cu → In2.Cu).
   61 pad'den 38'i ilk denemede güvenli bulundu, 19'u fine-pitch/PCIe
   coupled-gap ihlaline girdiği için silindi (kalan 23 pad zaten
   yerleştirilemedi) — net kazanç 38-19=19 escape via.
5. **`bulk_lowspeed_router.py` (proje-özel, önceden yazılmış) tekrar
   denendi:** taze board durumuyla 100/103 net işlendi, son 3 net'te
   `bounded_astar.py`'de bir `MemoryError`/olası döngü bulundu (script'e
   try/except + 10-net'te-bir ara-kayıt eklendi, kalıcı hale getirilmedi —
   sadece bu çalıştırma için). Kurtarılan JSON'da 36 net "çözülmüş"
   görünüyordu ama board'a yazılıp GERÇEK DRC ile kontrol edilince
   **31/36'sında gerçek `shorting_items`/`clearance` ihlali çıktı**
   (çoğu HDMI0/1 `_SCL_CONN`/`_SDA_CONN` ve GPIO net'leri) — router'ın
   kendi "başarılı" etiketi YANLIŞ pozitifti, muhtemelen In2.Cu'daki YENİ
   güç zone'ları obstacle grid'e yansımamıştı. Sadece gerçekten temiz
   çıkan 5 net (`Q1_BASE_NODE`, `LED1_ANODE_NODE`, `SW_NODE`,
   `LED2_ANODE_NODE`, `R11_Q1_NODE`) board'a yazıldı, kalan 31 geri alındı.

### Session-sonu doğrulanmış durum
`kicad-cli pcb drc --format report --severity-all`: **0 violation, 226
unconnected_items** (başlangıç: 269, gün toplamı: 43 net çözüldü). Güç
düzlemleri neredeyse bitti: CARRIER_3V3 15, CM4_5V 13, CM4_3V3 3
pad-mention kaldı (başlangıç 70/38/8) — kalanlar J1/J3 gibi yoğun
konnektör bölgelerinde, otomatik offset-arama ile escape via yerleştirmek
tekrar tekrar başarısız oluyor, muhtemelen elle/interaktif routing
gerekiyor. HDMI0, HDMI1, GbE J1, MIPI CAM0/CAM1, DSI0/DSI1, USB, I2C, geri
kalan GPIO/misc HÂLÂ routelanmamış — bu, TEK oturumda bitecek bir iş
değil (08-02/08-03 oturumlarının da doğruladığı gibi).

### Sonraki oturum için ders
- `bulk_lowspeed_router.py`'nin "N/103 routed" ilerleme çıktısı YANILTICI
  — aslında "N/103 DENENDİ" demek, başarı sayısı değil. Kod bu haliyle
  bırakıldı, DEĞİŞTİRİLMEDİ (net etiketi düzeltmesi kapsam dışı).
- Bu router'ın "çözüldü" dediği HİÇBİR net, board'a yazılmadan/GERÇEK DRC
  ile TEK TEK doğrulanmadan GÜVENİLMEMELİ — obstacle grid, aynı session
  içinde board'a eklenen yeni zone/via'ları (özellikle In2.Cu güç
  düzlemleri) doğru yansıtmıyor olabilir.
- CHASSIS_GND'yi çözmek HDMI0/HDMI1 fazının bir parçası olarak ele
  alınmalı (J7=HDMI0, J8=HDMI1 fiziksel konnektörleri, shield pinleri
  0.4mm mesafede sinyal pinlerine çok yakın).
