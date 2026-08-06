---
name: schematic-design
description: Bir elektronik donanım projesinde şematik tasarım fazını baştan sona yönetir — gereksinim belirlemeden datasheet analizine, pin tablosuna, şematik çizimine, footprint atamasına ve 4 aşamalı doğrulamaya (pin karşılaştırma, ERC, netlist, simülasyon) kadar. PCB yerleşim/routing bu skill'in kapsamı dışındadır. Kullanıcı yeni bir PCB/donanım projesine şematikten başlamak istediğinde, veya "şematik tasarımına başlayalım" dediğinde kullan.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - WebSearch
  - WebFetch
  - AskUserQuestion
  - ToolSearch
  - mcp__kicad__*
---

# /schematic-design — Şematik Tasarım Süreci

Bu skill bir donanım projesinin **şematik tasarım fazını** uçtan uca yönetir. PCB yerleşimi/routing'i kapsamaz — o ayrı bir aşamadır, şematik onaylanıp Faz 3-4 doğrulamaları geçmeden başlamaz.

Fazları sırayla uygula. Bir faz onaylanmadan/tamamlanmadan bir sonrakine geçme. Her fazın sonunda kullanıcıya net bir özet ver ve devam onayı al (Faz -1 hariç — o sessizce çalışır).

---

## Faz -1 — Otomatik Ortam Hazırlığı

Skill çağrıldığı anda, kullanıcıya sormadan çalıştır:

1. KiCad MCP araçlarının yüklü olup olmadığını kontrol et. **Bu araçlar deferred (tembel yüklenen) olabilir** — doğrudan çağırmadan önce `ToolSearch` ile `"select:mcp__kicad__..."` sorgusuyla şemalarını yükle, yoksa `InputValidationError` alırsın.
2. Proje dizininde `.kicad_pro` var mı kontrol et (`Glob`). Yoksa `mcp__kicad__create_project` ile oluştur; varsa `mcp__kicad__open_project`.
3. `sym-lib-table` / `fp-lib-table` dosyalarının mevcut olduğunu doğrula.
4. `kicad-cli` tam yolunu doğrula (bash PATH'inde olmayabilir — Windows'ta tipik olarak `/c/Program Files/KiCad/<sürüm>/bin/kicad-cli.exe`; `where`/`Get-Command` ile teyit et, bulunca hatırla).
5. pcbnew tabanlı bir python script çalıştırman gerekirse **sistem python'u değil, KiCad'in kendi bundled python.exe'sini** kullan.

---

## Faz 0 — Gereksinim Belirleme

1. Kullanıcının proje fikrini dinle; varsa referans/örnek proje dosyasını incele.
2. `AskUserQuestion` ile eksik gereksinimleri ve teknik detayları netleştir (hedef kullanım senaryosu, güç kaynağı tipi, boyut/form-faktör kısıtı, hedef host/platform varsa hangisi, vb.).
3. Kullanıcının net bir fikri yoksa, **piyasaya uygun ve endüstriyel tasarım standartlarına uygun** somut seçenekler sun (örnek IC'ler, mimari yaklaşımlar) — soyut değil, karşılaştırılabilir öneriler.
4. Hedef bir host/platform belirlendiyse (örn. Jetson, RPi, özel bir SoC kartı) bunu not al — Faz 1'de pinout uyumluluğu kontrolü için gerekecek.
5. Bu faz gereksinimler netleşince biter; kullanıcıya kısa bir özet sun ve onay al.

---

## Faz 1 — Datasheet Analizi ve Pin Bağlama Tablosu

1. Kullanılacak her entegrenin datasheet'ini bul (`WebSearch`/`WebFetch`) ve oku.
2. Her entegrenin bağlanması gereken **tüm** pinlerini çıkar.
3. Her entegre için **sebep-sonuçlu bir pin bağlama tablosu** oluştur — her pin için: fonksiyonu, nereye bağlanacağı, ve **neden** (datasheet referansıyla). Bunu kullanıcının inceleyebileceği bir dosya olarak yaz (proje kökünde, örn. `pin_baglanti_tablosu.md`).
4. **Host platformu pinout uyumu:** Faz 0'da bir hedef platform belirlendiyse, o platformun resmi referans/carrier board pinout spesifikasyonunu bul ve konnektör pin atamasını buna hizala. Rastgele/keyfi pin sırası verme.
5. **Strapping/adres pin kontrolü:** aynı bus'ı (I2C/SPI vb.) paylaşan birden fazla aynı entegre varsa, adres/strapping çakışması olup olmadığını doğrula. Doğrulanamıyorsa (örn. ayrı konnektörler/host'a çıkıyorlar) bunu açıkça not düş, sessizce geçme.
6. **Eksik/"TBD" datasheet parametreleri:** üretici bir değeri yayınlamamışsa, kullanacağın varsayımın kaynağını ve mantığını (örn. "toplam güçten sektör-tipik oranla bölündü, X kaynağına dayanarak") pin tablosunda veya ayrı bir notta açıkça belgele. Sessizce tahmin etme.
7. Pin tablosunu kullanıcıya sun, onay al.

---

## Faz 2 — Şematik Çizimi

Pin tablosu onaylandıktan sonra çizime geç.

**0. Known-Good Blok Kontrolü (sıfırdan çizmeden ÖNCE, zorunlu ilk adım):**
Her devre parçasını sıfırdan çizmek zaman kaybettirir ve hata riskini artırır.
Çizime başlamadan önce proje kökündeki `SNIPPETS/` klasörü kontrol edilir
(`Glob`). Bu klasör, daha önce üretilmiş ve **doğruluğu kanıtlanmış** (ERC/DRC
temiz geçmiş, gerçek bir kartta denenmiş) şematik/PCB bloklarını
(`.kicad_sch` alt sayfaları veya KiCad 8+ "Snippet" formatı) MPN veya
işlev adıyla tutar (örn. `SNIPPETS/LDO_3V3_AP2114.kicad_sch`,
`SNIPPETS/ESP32C3_Anten_Decoupling.kicad_sch`).
- Kullanılacak entegre/blok için eşleşen bir snippet varsa, onu sıfırdan
  çizmek YERİNE hiyerarşik alt sayfa olarak içe aktar/birleştir; sadece
  proje-özel pin bağlantılarını (net isimleri) uyarla.
- Eşleşen snippet yoksa normal şekilde sıfırdan çiz — VE eğer bu blok
  Faz 3 doğrulamasını (ERC + netlist + gerekirse simülasyon) sıfır hatayla
  geçerse, kullanıcıya bunu `SNIPPETS/` altına yeni bir known-good blok
  olarak kaydetmeyi teklif et (otomatik kaydetme — kullanıcı onayı olmadan
  proje dışı bir "kütüphane" oluşturma).
- Bir snippet'in halihazırda `SNIPPETS/` içinde olması onu ASLA sorgusuz
  kabul etme nedeni değildir — yine de Faz 3'ün 4 aşamalı doğrulamasından
  (aşağıda) geçmesi gerekir; farklı bir proje bağlamında (farklı voltaj
  rayı, farklı komşu bileşen) aynı blok farklı davranabilir.

**Şematik Tasarım Kuralları (bağlayıcı):**

1. **Güç net isimlendirmesi:** her ray için **tek kanonik sembol/isim** kullan. Aynı rayı görünüşte benzer ama farklı string'li iki isimle (örn. `+3.3V` vs `+3V3`) asla temsil etme — bu görünmez bir kısa devre/kopukluk yaratır ve KiCad net isimleri karakter-eşleşmesi gerektirdiği için ikisi asla birleşmez.
2. **Diferansiyel çift / yüksek hız sinyalleri:** P/N (veya +/-) son ekiyle tutarlı isimlendir; ilgili net class pattern'lerini (`.kicad_pro`) bu isimlerle senkron tut.
3. **Kablo çizim kuralı — sadece dik açı:** Kablolar yalnızca yatay ve dikey (90°) hatlarla çizilir, **çapraz (diagonal) kablo asla çizilmez**. Gerekli yerlerde yön değiştirmek için yukarı/aşağı inip çıkarak "altı açık kare" (basamak/step) şeklini alabilir. **Bileşen/pin konumlandırma hesapları buna göre yapılır** — component'ler, pinlerin dik açılı hatlarla temiz bağlanabileceği şekilde hizalanarak yerleştirilir; kablo çizildikten sonra düzeltilmeye çalışılmaz.
4. **Bileşen yerleşimi:** bileşenler birbirinin üzerine/çakışacak şekilde yerleştirilmez.
5. **Script ile üretiliyorsa** (GUI yerine MCP/python ile): iç içe parantez blokları regex ile değil, parantez derinliği sayan bir `extract_block` fonksiyonuyla çıkar; alt-birim isimlerine kütüphane öneki ekleme; `extends` kullanan kaynak sembolleri flatten et; `kicad-cli` mesajsız/sessiz bir hata koduyla çökerse hemen "ortam sorunu" varsayma — dosyayı gerçekten GUI'de açıp bozuk olup olmadığını kontrol et.
6. **Wire çizimi için BİRİNCİL yöntem `sch_wire.py`'dir (eski adı `sematik_wire_motoru.py`, artık `sematik_wire_motoru_old.py` — DEPRECATED), `mcp__kicad__*` DEĞİL.** MCP'nin bilinen hataları (Ek-A) tam olarak bu adımı — net'e doğru pin bağlama — etkiliyor. `SchBuilder` gerçek `(wire)`/`(junction)`/güç sembolü üretir ve **bağlantının tek kanıtı** `verify_nets()`'in (kicad-cli netlist export) sonucudur — görsel çizgi bağlantı kanıtı DEĞİLDİR. MCP araçları sadece GUI-benzeri kolaylık için (proje açma/component ekleme) kullanılabilir; wire/net üretimi ve doğrulaması `sch_wire.py` + kicad-cli üzerinden yapılmalı.

Çizim bitince kullanıcıya sun, onay al.

---

## Faz 2.5 — Footprint Atama

1. Şematik onaylanır onaylanmaz, her bileşene datasheet'teki gerçek pakete uygun footprint ata.
2. Paket tipi, pin sayısı, pitch, pad boyutunu datasheet'le çapraz kontrol et (yanlış footprint PCB aşamasında geri dönüşü zor bir hata olur).
3. Bu adım, Faz 3'ün netlist/PCB senkron kontrollerinden **önce** tamamlanmış olmalı.

---

## Faz 3 — Onay Sonrası 4 Aşamalı Doğrulama

Şematik ve footprint'ler kullanıcı tarafından onaylandıktan sonra sırayla uygula:

### 3.1 — Bağlantı ↔ Datasheet Pin Karşılaştırması
Her pinin fiili şematik bağlantısını datasheet'in beklediğiyle karşılaştır. Uyuşmazlık varsa (örn. "datasheet'te Input olması gereken bir pin şemada NC bırakılmış") **sebebiyle birlikte** raporla — kasıtlı bir tasarım kararı mı yoksa hata mı olduğunu belirt. **Özellikle çoklu-instance/simetrik tasarımlarda** (aynı devrenin birden fazla kopyası — örn. çoklu kamera/kanal), kopyala-yapıştır kaynaklı kazara NC bırakılmış fonksiyonel pinleri tara; bu hata sınıfı sık görülür.

### 3.2 — ERC Testi
ERC çalıştır. Hata/uyarı çıkarsa **PWR_FLAG gibi araçlarla geçiştirmeden önce kök nedeni araştır.** PWR_FLAG eklemek ilk çare olmamalı — önce neden o güç pini "sürücüsüz" görünüyor, gerçekten mi öyle yoksa net isimlendirme/bağlantı hatası mı, onu bul.

### 3.3 — Netlist
Netlist çıkar/kontrol et. **MCP araçlarının (özellikle `sync_schematic_to_board`, `get_net_connections`, `get_schematic_pin_locations`) sonucuna körü körüne güvenme** — bu araçların bazı sembol tiplerinde (örn. çok pinli/alternate-unit içeren IC'ler) yanlış net ataması yaptığı veya sahte pin sayısı döndürdüğü gözlemlendi. Kritik/güç netlerini `kicad-cli sch export netlist --format kicadxml` ile **bağımsız olarak** çapraz doğrula (bkz. Ek-A).

### 3.4 — Simülasyon
Her entegre için:
1. Üreticinin resmi sitesinde **şifresiz** bir SPICE/PSpice modeli ara.
2. Yoksa GitHub, SnapEDA, Ultra Librarian gibi üçüncü parti kaynaklarda ara.
3. Hiçbiri yoksa (veya model şifreliyse/encrypted ise, ör. Cadence-encrypted), datasheet'teki temel parametrelerden (hedef voltaj, eşik, dropout, akım limiti vb.) **davranışsal bir model** kur.
4. Ne tür bir model kullanıldığını (gerçek üretici modeli mi, davranışsal tahmin mi) ve **davranışsal model kullanıldıysa hangi gerçek davranışları YANSITMADIĞINI** (örn. "gerçek transient/PSRR/gürültü davranışını yansıtmaz, sadece DC çalışma noktası için yeterli") açıkça belgele.
5. Giriş/çıkış sinyallerini matematiksel olarak analiz et: beklenen değer neydi (datasheet'ten hesapla), simülasyon ne verdi, fark var mı ve varsa nedeni ne.

**Genel disiplin:** Her düzeltme, küçük parçalara bölünüp **izole bir kopyada** doğrulanmalı, sonra ana dosyaya uygulanmalı — özellikle çok adımlı script tabanlı düzeltmelerde.

---

## Faz 4 — Çapraz Doğrulama ve Raporlama

1. Faz 3'ün dört sonucunu (pin karşılaştırma, ERC, netlist, simülasyon) birbirine çapraz kontrol ettir — biri "temiz" derken diğeri bir tutarsızlık gösteriyorsa bunu araştır, sessizce görmezden gelme.
2. Nihai sonuca ulaş: tasarım pratikte çalışmaya hazır mı, hâlâ açık madde var mı.
3. Tüm bu raporları proje kökünde bir **`TEST/`** klasörü altında dosyalar halinde sun (örn. `TEST/pin_karsilastirma.md`, `TEST/erc_raporu.md`, `TEST/netlist_dogrulama.md`, `TEST/simulasyon_raporu.md`, `TEST/ozet.md`).

---

## Faz 5 — Devir Teslim Raporu (HANDOVER.md) Üretimi

Şematik çizimi ve ERC kontrolleri başarıyla bittikten sonra, ajan PCB
tasarımcısına (`pcb-layout` skill'ine) rehberlik etmesi için **zorunlu
olarak** ana dizine bir `HANDOVER.md` dosyası oluşturmalıdır. Bu dosya,
şematik ajanının PCB ajanına aktardığı "niyet ve kısıt" belgesidir —
`pcb-layout` skill'i placement/routing'e başlamadan ÖNCE bunu okumak
zorundadır (bkz. `pcb-layout` SKILL.md'nin ilgili maddesi). `HANDOVER.md`
üretilmeden PCB fazına geçilemez (bkz. `MASTER_RULEBOOK.md` — HANDOVER.md
Zorunluluğu).

Bu dosya şunları içermelidir:

1. **Komponent Kümeleri (Clusters):** Hangi dekuplaj kondansatörlerinin,
   dirençlerin veya kristallerin HANGİ ana entegreye (IC) fiziksel olarak
   çok yakın yerleştirilmesi gerektiği.
2. **Gürültülü ve Hassas Hatlar:** SMPS Switch (SW) düğümleri, yüksek
   frekanslı saat (Clock) sinyalleri gibi "Aggressor" hatlar ile ADC
   girişleri, analog sensör yolları gibi "Victim" hatların isimleri.
3. **Güç/Akım Gereksinimleri:** Yüksek akım (Örn: >1A) taşıyacak özel güç
   netlerinin isimleri ve tahmini taşıyacakları akım miktarları.

---

## Ek-A: Bilinen MCP Araç Hataları (referans)

| Araç | Sorun | Önlem |
|---|---|---|
| `add_schematic_component`/`batch_add_and_connect` (kütüphane `Description`'ı özel karakter — parantez, virgül, iç içe tırnak `\"` — içeren HERHANGİ bir sembolle; sadece +3V3 gibi güç sembolleriyle SINIRLI DEĞİL) | İlk kullanımda (o sembol tipi `lib_symbols`'a henüz gömülmemişken) Description property'sinin instance kopyası bozulup dosyanın geri kalanını (pin listesi, sonraki sembol) tek bir kaçak string literaline yutuyor — dosya tamamen parse edilemez hale geliyor, sadece ERC değil `list_schematic_components` bile "Failed to load schematic" veriyor. **2026-07-31 SOMUT ÖRNEKLER (cm4-io-test projesinde canlı üretildi):** `Connector_Generic:Conn_02x50_Row_Letter_First` (Description'da parantez+virgül: "...row letter first pin numbering scheme (pin number consists of...), script generated") ve `power:GND` (Description'da iç içe tırnak: `Power symbol creates a global label with name \"GND\" , ground`) — ikisi de İLK yerleştirmede dosyayı bozdu. | Mevcut/çalışan bir sembolü şablon alıp elle ekle, VEYA (daha güvenilir) `mcp__kicad__create_symbol` ile Description'ı bilerek düz-metin (parantez/virgül/tırnak YOK) tutan TEMİZ bir özel sembol oluşturup onu kullan. Bozulma olursa dosyayı elle kurtarmaya çalışma: dosyanın kendi üstündeki `(uuid ...)` başlığını koru, minimal boş bir `(kicad_sch ...)` iskeletiyle SIFIRLA, sembolleri TEK TEK (asla paralel — iki ayrı çağrı aynı dosyaya eşzamanlı yazarsa da AYRI bir bozulma deseni gözlemlendi) yeniden ekle. |
| `get_net_connections` | Bazen iki ayrı neti birleşmiş gösteriyor | `kicad-cli` ERC + `export_netlist` ile çapraz doğrula |
| `sync_schematic_to_board` | Bazı sembol tiplerinde (çok pinli/alternate-unit) pinleri yanlış nete yazabiliyor | Kritik/güç netlerini `kicad-cli sch export netlist --format kicadxml` ile bağımsız doğrula; PCB'de `grep '(net "..."'` ile şüpheli isimleri tara |
| `get_schematic_pin_locations` | Bazı sembollerde onlarca sahte/undefined koordinatlı pin döndürebiliyor | Sonucu gerçek pin sayısıyla mantık kontrolünden geçir, saçma görünüyorsa güvenme |
| `add_mounting_hole` | Yanlış lib_id üretebiliyor (PCB fazı — burada sadece not) | Manuel lib_id düzeltmesi gerekebilir |
| `batch_connect`/`batch_add_and_connect` (büyük çağrılarda) | 30sn yanıt zaman aşımı hatası dönebiliyor AMA işlem çoğu zaman ARKA PLANDA TAMAMLANIYOR (kısmi/tam) | Timeout mesajından sonra `list_schematic_components`/`list_schematic_labels` ile dosyanın sağlıklı olduğunu VE hangi pinlerin gerçekten bağlandığını kontrol et; eksik kalanları küçük bir ek çağrıyla tamamla — hemen yeniden deneme/geri alma yapma |

`kicad-cli` tipik konumu (Windows): `/c/Program Files/KiCad/<sürüm>/bin/kicad-cli.exe` — bash PATH'inde olmayabilir, tam yol kullan.

---

## Ek-B: "TBD"/Yayınlanmamış Datasheet Parametreleri veya Şifreli Simülasyon Modelleri

Bir üretici bir değeri yayınlamamışsa ya da SPICE modeli şifreliyse:

1. Resmi kaynakta şifresiz/açık alternatif ara.
2. Üçüncü parti kaynaklarda (GitHub, SnapEDA, Ultra Librarian) ara.
3. Hiçbiri yoksa datasheet'in yayınladığı **dolaylı** verilerden (örn. toplam güç, sektör-tipik oranlar) gerçekçi bir tahmin/davranışsal model kur.
4. **Bu varsayımı ASLA sessizce yapma** — raporda kaynağını, mantığını ve modelin/tahminin sınırlarını (neyi doğru yansıtıp neyi yansıtmadığını) açıkça yaz.
