---
name: pcb-layout
description: Bir donanım projesinin şematik onayından sonraki PCB yerleşim (placement), hesaplama ve yönlendirme (routing) fazını yönetir. Mekanik kısıtlamaları, mm bazlı kümeleme kurallarını ve katı routing önceliklerini zorunlu kılar. Şematik fazı bitmeden çalıştırılamaz.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - mcp__kicad__*
---

# /pcb-layout — PCB Yerleşim ve Yönlendirme Süreci

Bu skill, donanım projelerinin fiziksel karta (PCB) dönüştürülme sürecini uçtan uca yönetir. Claude Code bu kurallara harfiyen uymak zorundadır.

---

## Devir Teslim (Handover) Önceliği — ZORUNLU, Faz 1'den ÖNCE

PCB ajanı, yerleşim (placement) veya hesaplama yapmadan ÖNCE mutlaka
`HANDOVER.md` dosyasını okumak zorundadır (`schematic-design` skill'inin
Faz 5'inde üretilir — bkz. o skill'in ilgili maddesi). Yerleşim planı
(Placement), şematik ajanının belirlediği "Komponent Kümeleri"ne harfiyen
uygun yapılmalı; dekuplaj kondansatörleri ilgili çipin pinlerine makine
kısıtlarının izin verdiği en yakın noktaya konmalıdır. Yönlendirme
(Routing) sırasında Gürültülü (SW, Clock) hatlar ile Hassas (Analog)
hatlar birbirlerinden fiziksel olarak izole edilmelidir. `HANDOVER.md`
yoksa veya içindeki bir kısıta uyulamıyorsa durum kullanıcıya
(`NEEDS_HUMAN`) raporlanır — sessizce atlanmaz (bkz. `MASTER_RULEBOOK.md`
— HANDOVER.md Zorunluluğu).

---

## Faz 1 — Çizim Öncesi Hesaplamalar ve Raporlama

Fiziksel çizime geçmeden önce devrenin ihtiyaç duyduğu tüm elektriksel kısıtlamalar hesaplanmalıdır.
1. **Yol Kalınlığı ve Akım Kapasitesi:** Sinyal ve güç yolları için IPC-2221 standartlarında kalınlık hesaplanır.
2. **Empedans Hesaplamaları:** MIPI CSI-2 hatları için diferansiyel empedans (100Ω ±%10) hedefleri belirlenir (0.12mm trace / 0.2mm gap).
3. **Excel Raporu:** Hesaplamalar `pcb_hesaplamalar.csv` dosyasına kaydedilir ve onay alınır.

---

## Faz 2 — Katman (Layer) Stratejisi ve Stackup

1. **Stackup:** 4-Layer 1.6mm standart dizilim kullanılır.
2. **İşlev Atamaları:**
   * **F.Cu (Üst):** Kritik yüksek hızlı sinyaller ve komponentler.
   * **In1.Cu (İç 1):** Kesintisiz Toprak Düzlemi (GND Plane / Faraday Kalkanı).
   * **In2.Cu (İç 2):** Bölünmüş Güç Düzlemleri (Split Power Planes).
   * **B.Cu (Alt):** Düşük hızlı dijital sinyaller ve atlama yolları.

---

## Faz 3 — Mekanik Kısıtlamalar ve Komponent Yerleşimi (Placement Constraints)

Yapay zekanın rastgele yerleşim yapmasını engellemek için şu katı kurallar uygulanacaktır:

### Aşama 3.0 — Yerleşim Stratejisi Temel İlkesi (Ratsnest Bazlı Gruplama)
Dil modellerinin uzamsal zekası (2 boyutlu düzlemde çarpışmasız, mantıklı
yerleşim yapma yeteneği) zayıftır — bu yüzden koordinatlar asla "göze
uygun görünen" bir sezgiyle serbestçe atanmaz. KiCad'in Python API'si
(pcbnew) üzerinden yerleşim hesaplanırken, komponentler ÖNCE elektriksel
bağlarına (ratsnest / netlist connectivity) göre gruplara ayrılmalı, koordinat
ataması bu gruplar üzerinden yapılmalıdır:
1. Her komponent için bağlı olduğu netler (`pad.GetNet()`) çıkarılır.
2. Aynı net'i (veya aynı VDD/AVDD/CLK hattını) paylaşan komponentler tek bir
   mantıksal küme (cluster) olarak ele alınır — örn. bir IC ve onu besleyen
   decoupling kapasitörü aynı kümedir, aralarındaki mesafe optimize edilecek
   ilk parametre olmalıdır.
3. Kümeler kendi içinde yerleştirildikten SONRA kümeler arası mesafe
   (örn. Power Group ile dijital hatlar arası 10mm) ayarlanır — asla tersi
   sırayla (önce rastgele global yerleşim, sonra tek tek düzeltme) yapılmaz.
4. Aşağıdaki 3.1-3.5'teki mm bazlı kurallar bu ratsnest-gruplama işleminin
   SOMUT çıktılarıdır — 3.1-3.5 "ne" olduğunu, bu madde "nasıl hesaplandığını"
   tanımlar.

### Aşama 3.0b — Yerleşim/Routing Doğruluğunu Test Etme Kuralı (JSON Çarpışma Radarı ZORUNLU)
**Yerleşim (placement) veya routing sırasında bir koordinatın/izin
DOĞRU olup olmadığını test ederken `pcb_gorsel_kesit.py` ile PNG/SVG
üretip GÖRSEL olarak "bakmak" YASAKTIR.** Bunun yerine
`pcb_carpisma_radari.py::carpisma_json_uret()` (veya saf-geometri
katmanı: `komponent_sinir_kutularini_al` + `carpisan_ciftleri_bul` +
`kart_disina_tasmayi_bul`) ile üretilen DETERMİNİSTİK JSON kullanılır:
```json
[{"hata_tipi": "CARPISMA", "parca_1": "U1", "parca_2": "C3",
  "ic_ice_gecme_X_mm": 1.2, "ic_ice_gecme_Y_mm": 0.5,
  "tavsiye_edilen_kacis_X_mm": 1.5, "tavsiye_edilen_kacis_Y_mm": 0.5}]
```
Boş liste dönerse çakışma/taşma YOK demektir; boş DEĞİLSE, dönen
`tavsiye_edilen_kacis_X_mm`/`_Y_mm` değerine göre koordinat güncellenip
radar TEKRAR çalıştırılır (aynı `Sonsuz Döngü Kaçış Kuralı` — Faz 5 —
burada da geçerlidir: aynı çift 3 kez üst üste çakışırsa küçük kaydırma
YERİNE farklı bir yerleşim stratejisi denenir).

**Neden:** `pcb_gorsel_kesit.py`'nin kendi "DÜRÜSTLÜK SINIRI" notu SVG↔board
koordinat eşlemesinde ~0.06mm'lik bir yay-örnekleme farkı olduğunu
söylüyor — görsel bir araçla "çakışmıyor gibi görünüyor" demek, sayısal
bir DRC/placement kararı için YETERSİZ ve tekrarlanamaz bir doğrulamadır.
JSON Çarpışma Radarı `pcbnew.FOOTPRINT.GetBoundingBox(False, False)`'tan
okunan GERÇEK mm koordinatlarıyla çalışır — sonuç her koşumda birebir
aynıdır, bir sonraki ajan/oturum da AYNI sayıyı üretir.

**`pcb_gorsel_kesit.py` NE ZAMAN hâlâ kullanılır:** SADECE Faz 5'in
sonundaki "Görsel Denetim (Vision Review)" adımında (aşağıya bakınız) —
üretim öncesi HOLİSTİK/nitel bir son-bakış için (silkscreen'in pad
üzerine binmesi, RF bölgesi etrafında beklenmedik bakır, ısı-hassas
parçaların "gözle" yakın durması gibi bounding-box'la YAKALANAMAYAN
şeyler). Placement/routing'in kendisini doğrulamak için DEĞİL.

### Aşama 3.1 — Sabit Kısıtlamalar (Absolute Constraints)
* **Board Outline:** Kartın dış sınırları belirlenmeli, tüm komponentlerin merkezi kartın içinde kalmalıdır.
* **Konnektörler (J1, J2):** Kasa tasarımına göre koordinatları (X, Y) sabitlenmeli ve yönleri dışarı bakacak şekilde kilitlenmelidir (Lock).
* **Montaj Delikleri:** Sabitlenmeli ve etraflarına en az **3-5 mm'lik "Keep-out zone"** (komponent yerleştirilemez bölgesi) tanımlanmalıdır.

### Aşama 3.2 — Merkez Entegreler (Core IC Placement)
* **Optik Hizalama:** Kameraların (U1, U2) optik merkezleri, mekanik tasarımdaki lens deliklerine göre hizalanmalıdır.
* **Sanal Düz Hat:** Sensörler ile konnektörler arasında "sanal bir düz çizgi" (line of sight) çekilmeli, bu iki bileşen birbirine en yakın ve yüz yüze bakacak şekilde konumlandırılmalıdır.

### Aşama 3.3 — Sıkı Bağlı Alt Gruplar (Tightly Coupled Clusters)
* **Decoupling Kuralı:** Şematikteki her VDD/AVDD pinine bağlı olan 100nF kapasitör, ilgili pine **maksimum 1.5 mm** uzaklıkta konumlandırılmalıdır.
* **Osilatör Kuralı:** OSC komponenti, sensörün XTAL/CLK pinine **maksimum 5 mm** uzaklıkta olmalı ve arasına başka hiçbir komponent girmemelidir. Bu parçalar ana entegreyle birlikte hareket eden bir küme (cluster) olmalıdır.

### Aşama 3.4 — Yüksek Hızlı Sinyal Otoyolları (High-Speed Clearances)
* Sensörün MIPI çıkış pinleri ile konnektörün giriş pinleri arasında kalan dikdörtgen alan **"Yüksek Hızlı Bölge"** ilan edilir.
* **Kural:** Bu bölgenin içine kapasitör, direnç veya LDO gibi hiçbir pasif/aktif komponent yerleştirilemez. Yollar için temiz bir otoban bırakılır.

### Aşama 3.5 — Güç ve İzolasyon (Power & Isolation)
* **Power Group:** LDO'lar (U5, U6, U7) bir araya toplanmalı, ancak dijital gürültüden uzak tutulmak için I2C hatlarından veya osilatör sinyallerinden **en az 10 mm uzağa** yerleştirilmelidir.

### Aşama 3.6 — Custom DRC Kilidi (Guardrail) — Routing'den ÖNCE
Standart KiCad DRC'si sadece kısa devre/clearance gibi basit hataları
yakalar; elektriksel MANTIK hatasını (örn. yüksek akımlı bir motor hattının
ince bir yolla çizilmesi) yakalamaz. Bu yüzden routing (Faz 4) başlamadan
ÖNCE, KiCad'in `.kicad_dru` Custom Rules diliyle fiziksel bir koridor
kilitlenir — AI (veya FreeRouting) hata yapsa bile DRC bunu anında yakalar:
1. `kicad_koprusu.py::custom_dru_yaz()` çağrılır — her net class için
   (özellikle `HIGH_CURRENT`, diferansiyel çiftler) minimum iz genişliği/
   boşluk kısıtı `.kicad_dru` dosyasına yazılır. Değerler kafadan
   uydurulmaz — Faz 1'de `pcb_stackup_planner.py::iz_genisligi_hesapla_mm()`
   ile hesaplanan değerler kullanılır.
2. Örnek üretilen kural:
   ```
   (rule "Yüksek Akım Yolları"
     (condition "A.NetClass == 'HIGH_CURRENT'")
     (constraint track_width (min 1.5mm)))
   ```
3. Bu dosya routing başlamadan ÖNCE yazılmış ve DRC'ye yüklenmiş olmalı —
   sonradan eklenen bir kural, o kurala aykırı çizilmiş yolları geriye
   dönük yakalamaz, sadece yeni ihlalleri.
4. Faz 5'teki her DRC çalıştırmasında bu özel kurallar da otomatik olarak
   kontrol edilir (`kicad-cli` `.kicad_dru` dosyasını okur) — ayrı bir
   çalıştırma gerekmez.

### Aşama 3.7 — Routing Öncesi Topoloji Raporu (ZORUNLU KAPI)
FreeRouting veya Python çizim motorunu başlatmadan önce, tüm netleri analiz
et. Hangi sinyalin hangi katmandan gideceğini, maksimum via sayısını ve
hedeflenen akım/empedans değerini gösteren `TEST/routing_plan.json` ve
insanın okuyabileceği `TEST/routing_plan.md` dosyalarını KESİNLİKLE üret.
Kullanıcı `.md` dosyasını görüp onaylamadan çizime ASLA başlama.

Neden ayrı bir kapı: Faz 3.6'nın `.kicad_dru` kilidi bir izin
FİZİKSEL sınırlarını (min genişlik/boşluk) zorlar ama "bu net hangi
katmandan, kaç via ile gidecek" TOPOLOJİ kararını hiç görmez — o karar
şimdiye kadar routing sırasında örtük olarak alınıyordu, yani onaylanmamış
bir kararla bakır dökülüyordu. Bu rapor o kararı çizimden ÖNCE yazılı ve
onaylanabilir hale getirir.

Her net için raporda bulunması ZORUNLU alanlar:
| Alan | Kaynak (kafadan uydurulmaz) |
|---|---|
| `net` / `net_class` | `kicad_koprusu.py::net_classleri_projeye_yaz()` |
| `katmanlar` (izin verilen) | Faz 2 stackup + Faz 4 öncelik sırası |
| `max_via` | Faz 4: yüksek hızlı/kritik = **0**, güç = akım paylaştırıcı dikiş via'lar, dijital I/O = serbest |
| `hedef_akim_A` + `iz_genisligi_mm` | `pcb_stackup_planner.py::iz_genisligi_hesapla_mm()` (IPC-2221 + %20 pay) |
| `hedef_empedans_ohm` + `(W, S)` | `pcb_stackup_planner.py::empedans_geometrisi_coz()` (`ULASILAMAZ` ise NEEDS_HUMAN) |
| `router` | `freerouting` (**KiCad 10 + kicad-cli'de KULLANILAMAZ — DSN dışa aktarımı yok, doğrulandı, bkz. `uretim_zinciri_koprusu.py::dsn_disa_aktar()`; bu değer seçilirse rapor NEEDS_HUMAN işaretlemeli**) \| `manuel/diffpair` \| `python` (`topolojik_router_koprusu.py::akilli_yol_bul()`) — USB/MIPI FreeRouting'e BIRAKILMAZ |

Kurallar:
1. Rapor üretilmeden `freerouting_zinciri_calistir()` veya herhangi bir
   `route_*` çağrısı yapılamaz.
2. `.md` dosyası kullanıcıya SUNULUR ve onay beklenir — bu, CLAUDE.md'nin
   "onay noktaları dışında durma" kuralının bilinçli bir istisnasıdır
   (yanlış topoloji kararı, DRC temiz olsa bile kart dönüşü demektir).
3. Onaydan sonra topoloji değişirse (örn. Pathfinding kuralı bir netin
   katman değiştirmesini gerektirdi) rapor GÜNCELLENİR ve o net için
   değişiklik kullanıcıya tek satırla bildirilir — sessiz sapma YASAK.
4. `json` makine tarafından tüketilir (routing motoruna girdi), `md` insan
   onayı içindir; ikisi aynı veriden üretilir, elle ayrı ayrı yazılmaz.

---

## Faz 4 — Katı Routing Öncelik Sırası

**ÖNKOŞUL:** Aşama 3.6 (`.kicad_dru` kilidi) VE Aşama 3.7
(`TEST/routing_plan.md` kullanıcı onayı) tamamlanmadan bu faz başlamaz.

Çizim işlemine başlarken şu sıralama dışına çıkılamaz:

1. **Öncelik 1 (EMI Kalkanı):** İlk olarak `In1.Cu` katmanına uçtan uca kesintisiz **GND Copper Pour** yapılır.
2. **Öncelik 2 (Kritik ve Yüksek Hızlı Sinyaller):** MIPI CSI-2 arayüzleri ve osilatör saat sinyalleri; en kısa, engelsiz ve **via kullanılmadan sadece üst katmandan (`F.Cu`)** çizilir. **EK KURAL:** Sistemde birden fazla farklı saat sinyali (clock domain) varsa, bu saat yolları asla birbirine paralel veya farklı katmanlarda üst üste/alt alta yönlendirilemez (CDC Crosstalk Yasağı).
3. **Öncelik 3 (Güç Hatları):** `In2.Cu` katmanında geniş bakır düzlemlerle, decoupling kapasitörleri pinlere sıfır yanaşacak şekilde çözülür.
4. **Öncelik 4 (Hassas Analog Sinyaller):** Gürültüden uzak tutularak, dijital sinyallerle paralel ilerlemeyecek şekilde çizilir. **EE Yerleşim Önceliği:** Hassas analog yollar ile yüksek hızlı/gürültülü dijital yollar (örneğin I2C, SPI, Clock) birbirine paralel çizilemez, aynı katmanda uzun süre yan yana gidemez ve altlı-üstlü kesişmeleri gerekiyorsa sadece 90 derecelik dik açıyla kesişebilirler.
5. **Öncelik 5 (Dijital G/Ç - I/O):** I2C, GPIO ve kontrol sinyalleri en son çizilir (alt katmana inebilir, dolanabilir).

**Karar kaydı (2026-08-03):** Öncelik 2'ye başlamadan önce, seçilen yüksek
hızlı routing STRATEJİSİ (ör. "doğrudan F.Cu diagonal", "via-çifti ile
In2.Cu tünelleme", "coupled A* corridor") `karar_birimleri.
karar_ekle_veya_guncelle()` ile kaydedilir (`karar_id` örn.
`"hs-routing-stratejisi-<arayüz>"`, `bagimliliklar=["stackup-katman-sayisi"]`
— strateji katman sayısına bağlıdır). `gereken_kanit`: DRC temiz + bu
arayüz için `bagimsiz_dogrulama.py` skew/katman-sızıntısı kontrollerinin
PASS olduğu bir `main.py promote` raporu. `main.py promote`, bu karar
`KABUL_EDILDI` olmadan kanonik dosyaya geçmeyi zaten reddeder.

---

## Faz 5 — DRC ve DFM Kontrolü
KiCad DRC testi çalıştırılır; sıfır hata raporlanana kadar onay verilmez.

**Standart DRC "temiz" demesi YETMEZ.** `kicad_koprusu.py::gercek_board_dogrulama_kapisi()`
de bu fazda ZORUNLU olarak çalıştırılmalı — standart DRC bakır-bakır
clearance'a bakar, maske barajı/via-in-pad/annular-ring/kenar-keepout/
stitch-yoğunluğu gibi ayrı üretim ve EMI risklerini YAKALAMAZ (bkz.
`pcbnew_koprusu.py`, `emi-emc` skill'i). Bu fonksiyon `(temiz_mi, rapor)`
döner; `temiz_mi is False` ise standart DRC sıfır hata verse bile bir
sonraki faza (Görsel Denetim/KiBot) geçilmez.

### Sonsuz Döngü Kaçış Kuralı (Escape Rule)
DRC hatalarını tek tek düzeltirken bir hatayı düzeltip başka birini
bozmak (özellikle sıkışık/yoğun bölgelerde) yaygın bir başarısızlık
modudur. Bunu döngüye girmeden yakalamak için:
1. Her DRC çalıştırmasından sonra ihlal listesi (`drc_raporunu_ozetle`)
   bir öncekiyle karşılaştırılır — **aynı konumdaki/aynı açıklamalı ihlal
   art arda 3. kez** çıkıyorsa, o net/yol üzerinde küçük düzeltmelerle
   (yolu birkaç 0.1mm kaydırma vb.) devam ETMEK YASAKTIR.
2. Bu eşik aşıldığında strateji değiştirilir: ilgili yol/via TAMAMEN
   silinip, farklı bir katmandan veya farklı bir geometriden (örn. yan
   taraftan dolaşarak) baştan çizilir — mevcut yolun küçük varyasyonları
   denenmez.
3. 2 farklı yeniden-çizim denemesi de aynı ihlali veriyorsa, bu tekil bir
   routing hatası değil muhtemelen bir yerleşim (placement) sorunudur —
   Faz 3'e (özellikle Aşama 3.0 ratsnest gruplaması) geri dönülüp o
   bölgedeki komponent yerleşimi sorgulanır; sessizce aynı döngüde
   ısrar edilmez.
4. Her strateji değişikliği (kaçış) kullanıcıya kısaca not düşülür — hangi
   ihlal, kaç kez tekrarladı, hangi alternatif denendi.

### Görsel Denetim (Vision Review) — DRC temiz olduktan SONRA, KiBot'tan ÖNCE
**Kapsam sınırı (bkz. Aşama 3.0b):** bu adım çakışma/taşma/koordinat
DOĞRULUĞU için DEĞİLDİR — o iş `pcb_carpisma_radari.py` JSON API'sinin
işidir ve DAHA ÖNCE (Faz 3-4 sırasında) sıfır çıkmış olmalıdır. Burada
SADECE bounding-box'la yakalanamayan, nitel/holistik bir son-bakış yapılır.
DRC/ERC metin/koordinat tabanlıdır — bir bileşenin "mantıken" kötü bir yere
konduğunu (ama hiçbir clearance kuralını ihlal etmediğini) yakalayamaz.
Bunun için DRC sıfır hata verdikten sonra:
1. `kicad_koprusu.py::pcb_gorseli_disa_aktar()` ile (`kicad-cli pcb export
   svg` sarmalayıcısı) kartın üstten görünümü SVG/PNG olarak dışa aktarılır.
2. Bu görsel, Claude'un görme (vision) yeteneğiyle, "Kıdemli İnceleme
   Mühendisi" bakış açısıyla incelenir. En az şunlar kontrol edilir:
   - Anten/RF bölgesinin etrafında beklenmedik bakır döküm var mı?
   - Isı üreten parçalar (LDO, motor sürücü) ile ısıya hassas parçalar
     (osilatör, sensör) GÖRSEL olarak da birbirine çok mu yakın duruyor?
   - Faz 3.4'teki "Yüksek Hızlı Bölge"ye gözle bakıldığında gerçekten boş mu?
   - Serigrafi/referans yazıları pinlerin/padlerin üzerine mi biniyor?
3. Bu adım DRC'nin YERİNE geçmez, ONU TAMAMLAR — metin tabanlı kontrollerin
   veremeyeceği bir sezgisel/bütünsel kalite kontrolüdür. Görsel incelemede
   bir sorun bulunursa, ilgili faza (genelde Faz 3 placement) geri dönülür;
   KiBot'a (üretim çıktıları) SADECE hem DRC/ERC hem görsel denetim temiz
   olduğunda geçilir.
