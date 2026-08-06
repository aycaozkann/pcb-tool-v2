# PCB Tasarım Akışı — Adım 1 - 11 (Gereksinimden Üretim Çıktısına)

> Bu doküman, projenin genel tasarım metodolojisini tanımlar. `pcb_stackup_planner.py`
> dosyası bu akışın **Adım 8: Katman Seçimi ve Katmanların Görevlerinin Belirlenmesi**
> kısmını kod haline getirir (bkz. Faz 1-4: iz genişliği/DFM, differential pair/length
> matching/via stub, RF/anten/kristal, güç elektroniği). **Adım 9: Empedans Kontrolü ve
> Diferansiyel Çift Routing** ve **Adım 10: Bakır Alanı (Zone) Tanımlama ve GND Dökümü**,
> KiCad'de Adım 8'in çıktısını (stackup) kullanarak fiziksel çizime ve dökümüne geçişi
> anlatır — bu iki adım kod değil, KiCad içinde elle/araçla izlenecek iş akışlarıdır.
> `kicad_koprusu.py` ise Adım 8-9'daki hesaplanan değerleri (net class, empedans hedefi)
> gerçek KiCad proje dosyalarına aktarmayı deneyen (KiCad kurulu bir makinede
> doğrulanması gereken) bir köprü modülüdür. **Adım 11**, Adım 9-10'un ürettiği fiziksel
> tasarımı — DRC'nin yakalamadığı üç ek riski (maske barajı, referans düzlemi
> sürekliliği, gereksiz menderes) — kod tabanlı ölçümle kapatıp DFT + CPL/panelizasyon
> ile üretim çıktısına bağlar; bkz. `pcb_highspeed_escape.py`, `check_reference_plane_continuity()`,
> `dft-testpoints` skill'i, `uretim_zinciri_koprusu.py` BÖLÜM 4.

## Adım 1: Gereksinim ve Referans Analizi (Girdi Döngüsü)
- **Kullanıcı Girdisi:** Projenin amacı ve ne için kullanılacağı alınır.
- **Referans Kontrolü:** "Örnek veya referans aldığınız bir proje var mı?" sorusu sorulur.
  Var ise mimari şablon olarak hafızaya alınır.

## Adım 2: Ana Entegre (MCU) Karar Düğümü
- **IF** (Spesifik MCU Talebi == TRUE): Kullanıcının istediği işlemci doğrudan ana entegre
  olarak atanır.
- **ELSE:** Projenin amacına uygun, I/O pinleri ve haberleşme yetenekleri yeterli bir
  işlemci veri tabanından seçilir.
- **Atama:** Seçilen MCU'nun çalışma voltajı ve desteklediği donanımsal haberleşme
  portları (I2C, SPI, UART vb.) bir değişkene atanır.
- **Pin Multiplexing ve Alternatif Görev Kontrolü:** Seçilen MCU'nun pinlerinin sadece
  protokolle (I2C/SPI) uyumlu olması yetmez; seçilen pinlerin donanımsal kısıtları
  (örn. sadece giriş alabilen "input-only" pinler) veya yazılım tarafında çakışabilecek
  alternatif görev matrisleri (Alternate Functions) bu aşamada kontrol edilir.
- **Power Sequencing (Açılış Sıralaması) Denetimi:** Sistemde birden fazla voltaj rayı
  varsa (örn. 3.3V ve hassas analog kısımlar için 1.8V), regülatörlerin hangi sırayla
  ayağa kalkacağı şematik aşamasında belirlenir. Çekirdek ve I/O voltajlarının yanlış
  sırayla çakışarak latch-up (kilitlenme) yaratması engellenir.

## Adım 3: Sensör ve Haberleşme Uyum Döngüsü
- Hedef sensör seçilir ve protokol kontrolüne girer:
  - **IF** (Sensör Protokolü != MCU Protokolü): Hata verir, uyumlu yeni bir sensör
    seçimine dönülür.
  - **IF** (Sensör Protokolü == MCU Protokolü): Donanımsal uyum onaylanır, voltaj
    kontrolüne geçilir.
- **Boot ve Reset Devre Standardı:** MCU'nun güvenli şekilde çalışabilmesi ve
  programlanabilmesi (Flash/Run modu) için EN, GPIO0, GPIO2 gibi kritik pinlerin harici
  pull-up/pull-down dirençleri ile beslenme standartları eksiksiz şemaya eklenir.
- **Voltaj Çatışması Kontrolü:**
  - **IF** (MCU voltajı == Sensör voltajı): Sorunsuz doğrudan bağlantı rotası çizilir.
  - **IF** (MCU voltajı != Sensör voltajı): Araya iletişim protokolüne tam uyumlu bir
    Seviye Dönüştürücü (Level Shifter) eklenir (örn. I2C için açık-drenaj uyumlu TXS
    serisi bir entegre otomatik olarak malzeme listesine eklenir).

## Adım 4: Güç Topolojisi Karar Motoru (Kararlılık, Gürültü ve Regülasyon)
- Toplam güç ihtiyacı toplanır.
- **Güç Topolojisi Kriteri:**
  - **IF** (Sistem = Pil Beslemeli): AMS1117 gibi klasik LDO'lar reddedilir. Yalnızca
    Ultra Low-Dropout (ULDO) veya %90+ verimli Buck Converter seçilir.
  - **ELSE:** Standart LDO kabul edilebilir.
- **Datasheet Tetikleyicisi:** Güç entegresi seçilir ve datasheet'i klasöre kaydedilir.
- **Dropout Kontrolü:** Giriş-çıkış voltaj farkının LDO'nun dropout değerini karşıladığı
  kanıtlanır.
- **Gürültü ve PSRR Kontrolü:** Hassas bir "AVDD" pini varsa, bu hattı besleyecek
  LDO'nun PSRR (Gürültü Reddetme) değerinin yüksek olduğu teyit edilir.
  - Dijital besleme pini (VDD_CORE, VDD_IO) ise PSRR kritik değildir (~40 dB yeterli).
  - Hassas analog pin ise (ADC, DAC, Mikrofon, RF Anten, AVDD) yüksek PSRR zorunludur.
  - Datasheet'teki "PSRR vs. Frequency" grafiğine bakılır; anahtarlama frekansında
    (100 kHz - 1 MHz) 60-80 dB arası PSRR şartı aranır. Sağlamıyorsa reddedilir.
- **Geri Besleme (Feedback) Direnç Hesabı:** Ayarlanabilir LDO/Buck seçildiyse:
  1. Datasheet'ten referans voltajı (Vref) okunur.
  2. Standart formülle (Vout = Vref × (1 + R1/R2)) hesaplama yapılır.
  3. R2 için standart bir değer atanır, R1 hesaplanır.
  4. Sonuç, piyasada satılan %1 toleranslı E96 serisi standart dirençlere yuvarlanır.
  5. Gerçek dirençlerle formül tekrar çalıştırılır; hata payı %2'yi aşarsa yeniden hesaplanır.
  6. Hesaplanan R1/R2 BOM'a işlenir.

## Adım 5: Pasif Elemanların Örülmesi (Kapasite, ESR ve Inrush)
- **Giriş/Çıkış Kapasitör Kontrolü:** LDO datasheet'inde zorunlu kılınan minimum çıkış
  kapasitörü (örn. 2.2µF) değeri okunur ve şematiğe işlenir.
- **ESR ve Dielektrik Seçimi:** Osilasyonu (kararsızlığı) önlemek için kapasitörlerin
  dielektrik yapısı zorunlu olarak X5R veya X7R seramik seçilir.
- **Inrush (Kalkış) Akımı Kontrolü:** Devredeki toplam kapasitenin ilk açılışta çekeceği
  anlık akımın, güç kaynağı/USB portu limitlerini aşıp aşmadığı kontrol edilir.
- **Yerleşim Kısıtı:** Tüm decoupling kondansatörleri güç pinlerine maksimum 1.5 mm
  mesafeye kilitlenir.
- **Yeni Kontrol Modülü (`derating_calculator`):** Bileşen seçimi sırasında BOM
  listesini matematiksel olarak denetleyecek bir mantık eklenmelidir. Bu mantık,
  hat üzerindeki maksimum voltaj ve akımı alarak dirençler için güç (P=V²/R),
  kondansatörler için voltaj toleransı, bobinler için Doyma Akımı (Isat)
  güvenlik payı (Derating) hesaplamalarını otomatik yapıp uygunsuz bileşenleri
  reddetmelidir (bkz. `MASTER_RULEBOOK.md` FAZ 1.5 — EE Derating Filtresi).

## Adım 6: Üretim Öncesi Kesin Onay ve Tedarik Döngüsü (Son Filtre)
Taslak BOM listesi onaylanır; eksik varsa şematik çizilmeden parçalar değiştirilir.

**Tedarik Zinciri ve Parça Bilgisi Kontrolleri:**
- [ ] Küresel stok durumu (Mouser/DigiKey vb.) kontrol edildi mi?
- [ ] Üretim statüsü "Active" mi? (NRND / Obsolete olanlar elendi mi?)
- [ ] Tüm komponentlerin MPN'si eksiksiz mi?
- [ ] Parametre sınırları netleştirildi mi? ("10µF" değil "10µF / 16V" gibi)

**Kılıf (Footprint) ve Sembol Eşleşmesi Kontrolleri:**
- [ ] Şematik sembolündeki pin sayıları datasheet ile birebir eşleşiyor mu?
- [ ] CAD kütüphanesindeki lib_id ile MPN tutarlı mı?
- [ ] Yönlü elemanların (LED, diyot, polariteli kapasitör) artı/eksi bacakları şematik ile
      fiziksel kılıfta aynı mı?
- [ ] SMD pasif kılıfları (0402/0603 vb.) seçilen dizgi fabrikasının minimum kapasitesiyle
      uyumlu mu?
- [ ] Kullanılmayan/boş pinlere "X" (Not Connected) işareti kondu mu?

**Karar Motoru (IF-ELSE):**
- **IF** (Durum == "Active" VE Stok > İhtiyaç VE Kılıf == Doğru): Tüm parçalar onaylanır
  (PASS), BOM kilitlenir, fiziksel tasarıma geçilir.
- **IF** (Stok Yok VEYA Durum == "Obsolete"): Parça reddedilir (FAIL), kurtarma döngüsü:
  - Drop-in replacement (aynı kılıf/pin dizilimi) var mı? Varsa MPN güncellenir, onaya gider.
  - Yoksa, parça türüne göre ilgili adıma geri dönülür:
    - LDO/güç entegresi yoksa → Adım 4'e dön.
    - Sensör yoksa → Adım 3'e dön.
    - MCU yoksa → Adım 2'ye dön.
- **Kod karşılığı (`bom_lifecycle_koprusu.py`):** yukarıdaki IF-ELSE, `risk_skoru_hesapla()`'nın
  ürettiği tek bir sayısal eşiğe (skor > 0.5) indirgenir — "Active" durumu tek başına yeterli
  değildir, düşük stok/single-source/uzun lead-time de skoru yükseltip alternatif aramayı
  tetikleyebilir. `find_pin_compatible()` adaylar arasından SADECE `ayni_pinout AND
  elektriksel_param_eslesiyor` olanları döndürür ("aynı paket" tek başına PASS saydırmaz).
  Uygun aday yoksa bu döngü 3 kez denenip sonuç değişmezse NEEDS_HUMAN'a düşer (körü körüne
  4. bir MPN denenmez).

## Adım 7: Şematik Çizim Kuralları ve Üçlü Doğrulama Mekanizması

### A. Şematik Tasarım ve Temizlik Kuralları
- **Net İsimlendirme Standardı:** Güç yollarında tek bir kanonik isim kilitlenir
  (örn. "+3.3V" belirlendiyse "+3V3" kullanılamaz).
- **Kablo Çizim Geometrisi:** Çapraz (diagonal) kablo çizimi yasaktır; tüm bağlantılar
  sadece 90 derece açılarla çizilir.
- **Bileşen Konumlandırması:** Sinyal akışı soldan sağa, güç akışı yukarıdan aşağıya.
- **Decoupling Gösterimi:** Adım 5'teki bypass kapasitörleri, besledikleri ana entegrenin
  güç pinlerinin hemen yanına çizilir.
- **Kritik Pin Atamaları:** SOT-223 gibi metal tab'lı regülatörlerin soğutucu pad'i
  ezbere GND'ye bağlanmaz; datasheet onayıyla doğru hedefe (genelde VOUT) yönlendirilir.
- **Designator Atamaları:** Tüm komponentlerin R1/C5/U2 gibi atamaları eksiksiz yapılır.
- **Açık Pin Koruması:** Kullanılmayan pinlere "X" (No-Connect) konur — **ancak** projenin
  mantıksal çalışması için gereken aktif pinler (I2C/SPI/UART, güç, harici konnektör)
  kesinlikle No-Connect ile kapatılamaz; ya bir net'e ya da bir header çıkışına
  yönlendirilmek zorundadır.

### B. Üçlü Doğrulama Mekanizması (Triple Validation)
1. **ERC Doğrulaması:** Elektriksel Kural Kontrolü çalıştırılır, tüm "Fatal"/"Logic"
   hatalar sıfırlanana kadar düzeltilir. Güç çatışması hatası almamak için ilgili
   pinlere PWR_FLAG sembolleri eklenir.
2. **Netlist Doğrulaması:** Çizimden çekilen netlist satır sayısı ile hedeflenen
   matematiksel bağlantı sayısı birebir eşleşmelidir.
3. **Simülasyon Doğrulaması:** Kritik kısımlar (güç ağacı, regülatör çıkışları,
   kararlılık sınırları) KiCad'in ngspice motoruyla simüle edilir.

### C. Şematik - Datasheet Çapraz Doğrulama Raporu (Excel Çıktısı)
- Çizim/doğrulama bitince sistem otomatik bir Excel/CSV raporu
  (`TEST/Pin_Dogrulama_Raporu.xlsx`) oluşturur.
- Datasheet'teki beklenen pin görevleri ile şematikteki fiili bağlantılar satır satır
  karşılaştırılır.
- Datasheet'te aktif görevi olan bir pin, şematikte yanlışlıkla No-Connect bırakılmışsa
  "WARNING/FAIL" fırlatılır ve sistem durdurulur.

## Adım 8: Katman Seçimi ve Katmanların Görevlerinin Belirlenmesi
> Bu adımın tam kodu `pcb_stackup_planner.py` dosyasındadır (Faz 1-4 ile genişletilmiş).
> Özet mantık:
- **Veri yapıları:** `Net` (isim, tür, empedans kontrolü gerekli mi, maks akım) ve
  `Komponent` (isim, kılıf türü, pin sayısı).
- **Sinyalleri gruplama:** Tüm netler Güç, GND, Kritik (hızlı dijital/RF), Analog,
  Standart I/O kategorilerine ayrılır.
- **Katman sayısı hesaplama:** 2 katmandan başlanır; Fine-Pitch BGA, kritik sinyal
  varlığı, RF varlığı, çoklu voltaj + çok sayıda kritik sinyal, yüksek akım gibi
  kurallar sayıyı yukarı iter.
- **Stackup ataması:** "Hiçbir hızlı/analog sinyal referanssız kalamaz" temel kuralıyla
  katmanlara SİNYAL/GND/GÜÇ rolleri atanır.
- **Çapraz doğrulama (DRC):** Dönüş yolu, güç düzlemi parçalanması, crosstalk, RF
  izolasyonu kontrol edilir; hata varsa katman sayısı 2 artırılıp yeniden denenir.
- **Fiziksel/üretim doğrulama (DFM):** Mekanik kalınlık, bakır dengesi (warping), via
  aspect ratio kontrol edilir.
- **Faz 1-4 ile eklenenler:** İz genişliği/akım hesabı (IPC-2221), fabrika DFM
  profilleri (JLCPCB/PCBWay), decoupling kapasitör kuralı, differential pair empedans
  hedefi, length matching, via stub/back-drilling analizi, anten keep-out, kristal
  yerleşimi, RF stitching via, creepage/clearance yalıtım mesafesi, yüksek akım bakır
  kalınlığı, termal via hesabı.
- **`pcb_stackup_planner.py` (Güç ve Isı Güncellemesi):** Betik artık sadece SI
  (Empedans) değil, güç hatları için **IPC-2152** standardına göre akım taşıma
  kapasitesi ve sıcaklık artışı (Temperature Rise - ΔT) hesaplaması yapmalıdır.
  Yüksek akım yolları (Power Nets) için minimum iz kalınlığı (Trace Width) ve
  bakır kesit alanı (A), P=I²R ısı kayıplarını ve voltaj düşümünü (IR Drop)
  önleyecek şekilde algoritmik olarak belirlenmelidir.
- **`mekanik_dxf_koprusu.py` (Termal Keepout Güncellemesi):** Çarpışma kontrol
  algoritmasına "Mekanik Bounding Box" haricinde "Termal Keepout Zone" (Isı
  İzolasyon Alanı) mantığı eklenmelidir. Güç tüketen ve ısınan çiplerin
  çevresinde sanal bir termal yarıçap oluşturulmalı ve hassas/analog
  komponentlerin (Osilatör, Referans Entegreleri) bu yarıçapın içine
  yerleştirilmesi engellenmelidir.

## Adım 9: Empedans Kontrolü ve Diferansiyel Çift Routing (KiCad İş Akışı)
> Bu adım kod değildir — Adım 8'in ürettiği stackup çıktısını temel alarak KiCad
> içinde izlenecek MANUEL bir iş akışıdır. Amaç, `pcb_stackup_planner.py`'nin
> `empedans_hedefi_getir`, `length_matching_kontrolu` ve `via_stub_analizi`
> fonksiyonlarında (Faz 2) hesaplanan/doğrulanan hedeflerin gerçek PCB çizimine
> nasıl aktarılacağını tanımlar.

### 1. Üretici Parametrelerini Topla
Empedans hesabı matematiktir ve varsayımsal değerlerle yapılamaz. Kartı ürettireceğin
fabrikanın (JLCPCB, PCBWay vb.) web sitesindeki "Impedance Calculator"/"Stackup"
sayfalarından şu değerler not edilir:
- **Er (Dielektrik Sabiti):** FR4/prepreg malzemenin yalıtkanlık sabiti (genelde 4.2-4.6).
- **H (Yalıtkan Kalınlığı):** Sinyal katmanı ile referans GND katmanı arasındaki mesafe
  (örn. 0.1mm).
- **T (Bakır Kalınlığı):** Dış katmanlar için genelde 1 oz (35 µm) veya 0.5 oz (18 µm).

### 2. KiCad Hesaplayıcısını (TransLine) Kullan
Üretici parametreleri alındıktan sonra KiCad'in Calculator Tools > TransLine sekmesi
kullanılır:
- **Tür seçimi:** Differential sinyal için (USB D+/D- gibi) "Coupled Microstrip Line"
  (dış katman) veya "Edge-Coupled Stripline" (iç katman) seçilir.
- **Malzeme değerleri:** Substrate Parameters kısmına Er, H, T girilir.
- **Hedef empedans:** Örn. USB için 90 ohm, MIPI/Ethernet için 100 ohm girilir.
- **Hesapla:** Geriye W (yol genişliği) ve S (yollar arası boşluk) kalır; hedef
  empedansı yakalayana kadar bu iki değer ayarlanır ve not edilir.

### 3. Net Sınıflarını (Net Classes) Oluştur
Hesaplanan W/S değerleri KiCad'e fiziksel kural olarak tanımlanır:
1. File > Board Setup.
2. Design Rules > Net Classes.
3. `+` ile yeni sınıf oluştur (örn. `USB_DIFF`, `MIPI_CSI`).
4. Hesaplanan W değeri "Track Width", S değeri "DP Gap" (Differential Pair Gap) alanına
   girilir.
5. İlgili netler (örn. `USB_D+`, `USB_D-`) bu sınıfa atanır.

### 4. Çizime (Routing) Başla
Kurallar tanımlandıktan sonra "Route Differential Pair" aracı (kısayol: 6) ile
+ veya - pinlerinden birine tıklanır; KiCad her iki yolu aynı anda, hesaplanan
kalınlık/aralıkla, empedansı koruyarak GND düzlemi üzerinde paralel çizer.

### 5. Via Geçişlerinde Sinyal Bütünlüğü Kuralları
Veri yoğunluklu/yüksek frekanslı (MIPI, USB vb.) donanımlarda via geçişlerinde
sinyalin bozulmaması için:
- **Via sayısını minimumda tut:** En iyi via, hiç var olmayan via'dır. Kritik
  diferansiyel çiftler mümkünse aynı katmanda (tercihen üst katman) çizilir.
- **Dönüş yolu (return path) viası ekle:** Sinyal bir katmandan diğerine
  (örn. L1'den L4'e) indiğinde referans GND düzlemi de değişir. Dönüş akımının
  ana sinyali kesintisiz takip edebilmesi için sinyal via'sının hemen yanına
  (maks. 1-2mm uzağa) bir GND stitching via'sı konur.
- **"Via stub" (kör uç) etkisinden kaçın:** L1'den L2'ye gibi kısa bir geçişte,
  standart boydan-boya via'nın kartın en altına kadar inen kısmı boşta ("stub")
  kalır; yüksek hızlı sinyaller bu kör uca çarpıp yansır (reflection). Çözüm:
  kritik sinyalleri L1'den doğrudan en alt katmana (Bottom) indirerek via'nın
  tamamını yol olarak kullanmak — böylece yansıtıcı kör uç oluşmaz.
  *(Bu, `pcb_stackup_planner.py` içindeki Faz 2 `via_stub_analizi` fonksiyonunun
  koddaki karşılığıdır.)*
- **Diferansiyel çiftlerde mutlak simetri:** D+ ve D- yollarına via atmak
  gerekiyorsa, her iki yola da aynı anda, yan yana ve milimetrik simetrik via
  atılmalıdır. Biri via ile alt katmana inip diğeri üstte devam edemez.

### 6. Uzunluk Eşitleme (Length Tuning / Menderes) Kuralları
Kısa kalan yolu uzatıp diğerine eşitlemek için çizilen kıvrımlara **Menderes
(Meander)** denir. KiCad'de adımlar:

1. **Tolerans belirleme:** File > Board Setup > Design Rules > Net Classes (veya
   Custom Rules) içinde diferansiyel çiftler için maksimum uzunluk farkı (Skew)
   tanımlanır. MIPI/USB için tipik tolerans 0.1-0.15 mm arasıdır.
   *(Kod karşılığı: Faz 2'deki `ARAYUZ_UZUNLUK_TOLERANSI_MM` tablosu ve
   `length_matching_kontrolu` fonksiyonu.)*
2. **Uzunluk eşitleme aracı:** Yollar `Route Differential Pair` ile çizildikten
   sonra, "Tune Differential Pair Skew/Phase" aracı seçilip çift üzerine
   tıklanır; açılan "Tuning Status" penceresi uyumsuzluğu ve hedef uzunluğu
   gösterir.
3. **Menderesleri çizme:** Kısa yolun üzerinde gezinildiğinde KiCad otomatik "U"
   şeklinde kıvrımlar ekler; hedefe ulaşınca bilgi kutusu yeşile döner, tıklayarak
   sabitlenir. '1'-'4' kısayolları kıvrım genlik/genişliğini ayarlar.

**Menderes çiziminde altın kurallar:**
- **Uyumsuzluğun olduğu yere müdahale et:** Fark nerede oluştuysa (bir pin
  çıkışı, bir via dönüşü vb.) menderes hemen o noktaya konur — hatayı yolun
  sonuna/ortasına bırakmak eşitlemeyi anlamsızlaştırır.
- **Menderes boşlukları (3W kuralı):** Kıvrımlar arası mesafe, yol genişliğinin
  en az 3-4 katı olmalıdır; aksi halde sinyal kıvrımı dolaşmak yerine yollar
  arasında atlar (crosstalk).

## Adım 10: Bakır Alanı (Zone) Tanımlama ve GND Dökümü (KiCad İş Akışı)
> Bu adım da Adım 9 gibi kod değildir — Adım 9'da çizilen sinyal yollarının
> tamamlanmasından SONRA, KiCad içinde izlenecek manuel bir iş akışıdır.
> Amaç, boş kalan kart alanlarını GND (veya güç) dökümüyle doldurup dönüş
> yolu sürekliliğini ve termal/EMI performansını sağlamaktır.

### 1. Bakır Alanı (Zone) Tanımlama
1. Sağ araç çubuğundan "Add a filled zone" aracı seçilir (kısayol:
   Ctrl+Shift+Z).
2. Kartın kenarının (Edge.Cuts) hemen dışına tıklanır; "Copper Zone
   Properties" penceresi açılır.
3. **Layer:** Dökümün yapılacağı katman seçilir (örn. F.Cu veya B.Cu).
4. **Net:** Alanın bağlanacağı sinyal seçilir — genellikle GND.
5. Pencere onaylandıktan sonra kartın etrafını saran kapalı bir çokgen
   çizilir; başlangıç noktasına çift tıklanarak çizim bitirilir.

### 2. Alanı Doldurma (Filling)
Sınır çizildiğinde alan otomatik dolmaz — sadece taralı sınır görünür.
Klavyeden **B** tuşuna basmak alanları bakırla doldurur (veya günceller).
Dökümü gizleyip sadece yolları görmek için sol araç çubuğundaki "Show
filled areas in zones" ikonu kapatılabilir.

### 3. Bakır Dökümünde Kritik Mühendislik Kuralları
Zone Properties penceresindeki şu ayarların doğru olduğundan emin olunmalı:
- **Termal Yalıtım (Thermal Reliefs):** Varsayılan açık gelir ve ÖYLE
  KALMALIDIR. Kapatılırsa, bir pad (örn. kondansatör GND pad'i) doğrudan
  devasa bir bakır kütlesine bağlanır; bu kütle lehim yaparken ısının
  tamamını çeker ve soğuk lehime yol açar. Termal yalıtım, pad ile döküm
  arasına küçük köprüler atarak ısıyı pad'de tutar.
- **Ölü Bakırları Temizleme (Remove Islands):** "Always" (Her Zaman) seçili
  olmalıdır. Hiçbir yere bağlı olmayan izole bakır adaları anten gibi
  davranıp gürültü toplar ve sinyalleri bozar.
- **Clearance (Boşluk):** Döküm ile sinyal yolları arası mesafedir. Özellikle
  empedans kontrollü (Adım 9'da hesaplanan) yolların dibine kadar giren bir
  GND dökümü empedansı bozabilir. Standart değerden (örn. 0.2mm) biraz daha
  geniş (0.4-0.5mm) tutmak genellikle daha güvenlidir.

### 4. Dikiş Viaları (Stitching Vias)
Hem Top hem Bottom katmana GND dökümü yapıldıysa, bu iki bakır alanı
birbirine "zımbalanmalıdır" — aksi halde üst ve alt GND arasında voltaj
farkları oluşabilir. Boş bulunan her yere (özellikle sinyal yollarının yön
değiştirdiği köşelere ve kart kenarlarına) üstten alta inen GND via'ları
yerleştirilir. Bu işleme **via stitching** denir ve kartın elektriksel/
termal stabilitesini önemli ölçüde artırır.
*(Bu, Adım 9'daki "dönüş yolu viası" kuralının — ve dolayısıyla
`pcb_stackup_planner.py`'deki Faz 2 `via_stub_analizi` mantığının — tüm
kart yüzeyine genelleştirilmiş hâlidir: sinyal via'ları için nokta nokta
yapılan return-path via kuralı, burada GND dökümünün bütünü için tekrarlanır.)*

## Adım 11: Pad-Escape, Referans Düzlemi Kanıtı, DFT ve CPL/Panelizasyon
> Adım 9-10 hattın GÖVDESİNİ ve genel GND dökümünü kapsıyordu. Bu adım,
> DRC'nin YAKALAMADIĞI (çünkü DRC bakır-bakır clearance'a bakar, üretim
> katmanına/düzlem sürekliliğine değil) üç ayrı riski, çıktı üretiminden
> ÖNCE, kod tabanlı ölçümle kapatır.

**IF-ELSE:**
- **IF** (net, pin-arası dar bir kanaldan geçiyor — ESD dizisi/konnektör
  GND-VBUS pini gibi): `pcb_highspeed_escape.py::maske_baraji_kontrolu()`
  çalıştırılır. Baraj < fab min (tipik 0.20-0.25mm) İSE iz genişliği
  `maksimum_iz_genisligi_icin_baraj_mm()` ile geri çözülür VEYA footprint
  değiştirilir — akıma göre değil BARAJA göre karar verilir.
- **IF** (yüksek hız neti bir GND/PWR düzleminin üzerinden geçiyor):
  `kicad_koprusu.py::check_reference_plane_continuity()` her segmentin uç
  ve orta noktalarını düzlem poligonuyla test eder. Nokta düzlemin DIŞINDA
  İSE → katman geçişine GND-GND stitching via veya GND-PWR 100nF kapasitör
  eklenir; Adım 9'daki length-match temiz olsa BİLE bu ihlal SI'yı bozar,
  ayrıca kapatılmalıdır.
- **IF** (skew > 0): mm değil **ps** cinsinden değerlendirilir
  (`skew_mm_den_ps_e_cevir`, FR4 mikroşerit ~167.6 mm/ns). Bütçenin ALTINDA
  İSE menderes EKLENMEZ (`meander_gerekli_mi() == False`) — gereksiz
  menderes kuplajı/empedansı bozar.
- **DFT (paralel, `dft-testpoints` skill'i):** güç rayı + debug netleri için
  TP kapsamı `tp_kapsam_kontrolu()` ile %100'e tamamlanır;
  `generate_bringup_checklist()` rail enable sırasını ZORLAYARAK
  `bringup_checklist.md` üretir.
- **Çıktı öncesi (CPL/panelizasyon):** fab-rotasyon-map
  `rotation_map_versiyonla()` ile hash'lenir (versiyonsuz map = tüm parti
  ters lehim riski); `check_orientation()` kutuplu parça yönünü CPL açısıyla
  çapraz doğrular; panel varsa `panelizasyon_kontrolu()` (fiducial/rail/
  de-panel mesafesi) çalıştırılır. Hepsi temiz İSE Adım 7'deki
  `design-checker` denetimine, o da PASS verirse KiBot üretim çıktılarına
  geçilir.
