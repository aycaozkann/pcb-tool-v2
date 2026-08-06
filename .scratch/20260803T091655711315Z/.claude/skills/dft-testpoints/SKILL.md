---
name: dft-testpoints
description: Güç rayı + debug (SWD/UART) + kritik sinyallere test noktası (TP) ekler, kapsamı doğrular ve bring-up checklist üretir. İki fazda koşar — TP'ler şematik fazında (schematic-design Faz 2'den sonra) doğar, yerleşim sonrası (pcb-layout Faz 5'ten sonra) erişilebilirlik doğrulanır. Kullanıcı "test noktaları ekle", "DFT" veya "bring-up checklist" dediğinde, ya da schematic-design/pcb-layout akışının kendisi bu skill'i tetiklediğinde kullan.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - mcp__kicad__*
---

# /dft-testpoints — Test Edilebilirlik (DFT) Süreci

Bu skill, `schematic-design` ve `pcb-layout` skill'lerinden BAĞIMSIZ ama
onlarla iki noktada kesişen dar kapsamlı bir süreçtir: test noktası (TP)
kararını üretir, kapsamı doğrular, bring-up checklist yazar. Board'un
kendisini çizmez/routing yapmaz — o iş Maker skill'lerinin işidir.

---

## Ne zaman, hangi fazda çalışır

**Faz A — Erken (şematikte doğar):** `schematic-design` skill'inin Faz 2
(Şematik Çizimi) tamamlanıp Faz 2.5 (footprint atama) başlamadan önce/
sırasında çağrılır. Bu fazda üretilen TP'ler AYNI `.kicad_sch`'e yazılır —
bu yüzden `schematic-design` ile SERİDİR (aynı dosyaya paralel iki ajan
yazamaz; proje kilidi kuralı burada da geçerlidir).

**Faz B — Geç (yerleşim sonrası):** `pcb-layout` skill'inin Faz 5 (DRC/DFM)
"temiz" raporladıktan SONRA, ama `design-checker`/üretim çıktılarından ÖNCE
çağrılır. Bu fazda TP'lerin mekanik erişilebilirliği (stub yaratmıyor, prob
açısı uygun) doğrulanır ve `bringup_checklist.md` yayınlanır.

---

## Faz A — Adımlar (Erken)

1. `kicad_koprusu.py::insert_test_points(rail_tree, debug_netleri)` çağrılır.
   Girdi: `pcb_stackup_planner.py::stackup_planla()`'nın ürettiği rail bilgisi
   (`rail_tree`) + proje-özel debug net listesi (varsayılan: SWDIO, SWCLK,
   nRST, UART_TX, UART_RX — proje farklı bir debug arayüzü kullanıyorsa
   bu liste açıkça override edilmeli).
2. **Zorunlu kapsam** (kapsam hedefi güç+debug %100):
   - Her güç rayının **çıkışı** (regülatör girişi değil).
   - SWD (SWDIO/SWCLK/nRST), UART (TX/RX).
   - Boot-strap pinleri, PMIC enable/PG.
3. `kicad_koprusu.py::tp_kapsam_kontrolu(tps, beklenen_guc_rayi_sayisi, beklenen_debug_net_listesi)`
   ile eksik kalan rail/net raporlanır — eksik varsa Faz A tamamlanmış
   sayılmaz.
4. TP'lerin şematiğe fiziksel eklenmesi (`mcp__kicad__*` araçları ile
   sembol yerleştirme + wire) `schematic-design` skill'inin Faz 2 kablo
   çizim kurallarına (sadece dik açı, pin ankrajıyla birebir aynı koordinat)
   TABİDİR — bu skill kendi kablo çizim kuralı icat etmez, ödünç alır.
5. Kullanılmayan/opsiyonel bir debug hattı varsa `(no_connect ...)` ile
   niyet belgelenir — sessizce atlanmaz.

## Faz B — Adımlar (Geç, yerleşim sonrası)

1. Yerleşim sonrası her TP'nin koordinatını (`pcb-layout` Faz 3 placement
   çıktısından) al; şu kontrolleri yap:
   - **Erişilebilirlik:** TP, courtyard-temiz bir alanda mı (komşu parça
     probe ucuna engel olmuyor mu)?
   - **Yüksek hız hattı stub yasağı:** MIPI/USB gibi hatlara TP stub'ı
     KONULMAZ (empedans süreksizliği) — `pcb_highspeed_escape.py`'nin
     escape geometrisiyle çakışan bir TP varsa bu bir hatadır, TP'yi kaldır
     veya mikro-TP/prob-pad'e çevir.
   - **GND yakınlığı:** Osiloskop kullanımı için TP'ye birkaç mm mesafede
     bir GND TP olmalı.
   - **ICT (In-Circuit Test) Fiziksel Kısıtları:** "Bed of Nails" pogo
     pinlerinin birbirine temas etmemesi için yerleştirilen Test Noktaları
     (TP) arasında merkezden merkeze minimum 1.27 mm (tercihen 2.54 mm)
     mesafe bırakılmalıdır. Fikstür maliyetini düşürmek için, zorunlu
     kalınmadıkça tüm test noktaları kartın SADECE TEK BİR katmanına
     (tercihen `B.Cu` / Alt katman) yerleştirilmelidir.
2. `kicad_koprusu.py::generate_bringup_checklist(tps, rail_enable_sirasi)`
   çağrılır. `rail_enable_sirasi` **rastgele değildir** —
   `pcb_stackup_planner.py`'nin ürettiği güç bütçesi/sıralama bilgisinden
   (veya PMIC datasheet'inin gerektirdiği enable sırasından) türetilir; rail
   sıralama hatası core'a kalıcı hasar verebileceği için bu sıra
   checklist'te ZORLANIR (numaralı adımlar, sıra dışına çıkılamaz).
3. Çıktı: `bringup_checklist.md` (proje kökünde) — beklenen voltaj sırası +
   debug erişilebilirlik listesi + yüksek hız hatlarında TP olmadığı notu.

---

## Kabul kriterleri

- [ ] `tp_kapsam_kontrolu()` boş liste döndü (güç+debug %100).
- [ ] Yüksek hızlı hatlarda (MIPI/USB/CSI) TP stub'ı sayısı = 0.
- [ ] `bringup_checklist.md` üretildi ve rail sırası proje kararına (keyfi
      değil) dayanıyor.
- [ ] Kullanılmayan debug pinleri `(no_connect ...)` ile belgelendi.
- [ ] TP'ler arası merkez-merkez mesafe ≥1.27mm (tercihen 2.54mm) ve tüm
      TP'ler zorunlu kalınmadıkça tek katmanda (tercihen `B.Cu`).

## Sınır

Bu skill board'u çizmez/yerleştirmez/routing yapmaz — sadece TP kararını,
kapsam doğrulamasını ve bring-up dokümantasyonunu üretir. Fiziksel
ekleme/routing `schematic-design`/`pcb-layout` skill'lerinin sorumluluğunda
kalır; bu skill onlara bir girdi (`testpoint_map` — `insert_test_points()`
dönüş değeri) ve bir çıktı (`bringup_checklist.md`) sağlar.
