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
| Durum | Şematik/ERC tamam. PCB: yüksek hızlı arayüzlerin çoğu (PCIe, HDMI0, HDMI1) DRC-temiz; Gigabit Ethernet (J1→ESD escape) **DRC-temiz DEĞİL** (90 ihlal, aşağıda detay); ~259 düşük hızlı net henüz routelanmadı. |
| Bu oturumdaki en son DRC | `drc_session_truly_final.json` — 27 ihlal (21 via_dangling + 4 lib_footprint_mismatch + 2 silk_over_copper, HEPSİ önceki oturumdan/PCIe ile ilgili), 269 unconnected_items. `shorting_items=0`, `tracks_crossing=0` — 3. denemenin (bağımsız per-net A*) 7 shorting_items'ı **board'da BIRAKILMADI**, oturum sonunda J1'in 8 net'i tekrar temiz/unrouted airwire durumuna söküldü (Görev 1 disipliniyle aynı standart — "en iyi ama kirli" bir ara durum kalıcı sayılmadı). 3. denemenin kodu/verisi (`TEST/independent_net_router.py`, `write_independent_tracks.py`, `independent_paths.json`) referans için saklandı, board'a UYGULANMADI. |
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
