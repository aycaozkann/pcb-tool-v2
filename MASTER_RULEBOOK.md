# ⚡ Donanım Tasarımı ve Mühendislik Ana Anayasası (Master Rulebook)

---

## BÖLÜM 0: ZORUNLU RAPORLAMA VE DATASHEET PROTOKOLÜ

* **Zorunlu CSV Raporlama:** Şematik ve PCB hesaplamaları kafadan yapılamaz. Formüller kullanılarak elde edilen her sonuç `TEST/` dizinine standart CSV dosyası olarak kaydedilecektir. İlgili CSV'de "PASS" alınmadan bir sonraki işleme geçilmeyecektir.
* **Datasheet Arşivi (İstisnasız, Şematik Çiziminden ÖNCE):** Seçilen her entegrenin — ilk BOM'da olsun veya tasarım sırasında/sonradan eklensin (örn. bir yük anahtarı veya koruma IC'si gibi Faz 2 ortasında karara bağlanan bir parça) — resmi datasheet dosyası, o parça şematiğe işlenmeden ÖNCE `DATASHEETS/` klasörüne kaydedilmek zorundadır. WebFetch/WebSearch ile canlı kaynaktan okunan bir datasheet dahi olsa, sadece bellekte/konuşma geçmişinde tutulup dosyaya kaydedilmemesi bu kuralın ihlalidir. Bulunamazsa işlem durdurulup kullanıcıdan talep edilecektir. *(Gerekçe: Faz 2.5'te TPS22910A datasheet'i WebFetch ile okunup kullanılmış ama dosyaya kaydedilmemişti — sonradan fark edilip düzeltildi; bu tekrarlanmamalı.)*
* **Güç Topolojisi Kriteri:** Pil beslemeli sistemlerde klasik LDO (örn. AMS1117) kullanılamaz; Ultra Low-Dropout (ULDO) veya %90+ verimli Buck Converter kullanımı zorunludur. **Karar kaydı (2026-08-03):** bu seçim yapılır yapılmaz `karar_birimleri.karar_ekle_veya_guncelle()` ile bir karar birimi (`karar_id` örn. `"guc-topolojisi"`) açılır/güncellenir — `gereken_kanit` alanına dropout/verim hesabının hangi CSV'de kanıtlandığı yazılır, `durum` sadece hesap+kullanıcı onayı sonrası `KABUL_EDILDI` olur (bkz. `main.py promote`'un bu kayıtları kontrol ettiği kapı).
* **Giyilebilir/Kompakt Form Faktör İstisnası (Güç Topolojisi):** Form faktör "Giyilebilir" (Wearable) veya "Kompakt" olarak belirlendiyse, Buck-Boost/Buck yerine **Low-IQ (düşük sükunet akımlı) ULDO** (örn. ME6211, RT9013 veya dengi) tercih edilir — gerekçe: buck/buck-boost'un anahtarlama bobini hem yer kaplar hem de EMI/akustik gürültü kaynağıdır, küçük giyilebilir kartlarda bu maliyete değmez. **Bilinçli ödün:** Low-IQ LDO, pil gerilimi LDO dropout'unun altına düşünce (tipik ~3.0-3.4V bandı) regülasyonu keser — pilin en son diliminin bir kısmı kullanılamaz; bu, buck-boost'un tam pil aralığını (3.0-4.2V) kullanabilme avantajından bilinçli olarak vazgeçilmesidir, kullanıcı onayıyla kabul edilir. Ayrıca bu tür projelerde pili tamamen kesmek için sisteme fiziksel bir **sürgülü anahtar (Slide Switch)** eklenecektir (derin deşarj/depolama sızıntı akımını sıfırlamak için). *(Gerekçe: ESP32-C3 Smart Band projesinde başlangıçta önerilen buck-boost, kullanıcı tarafından giyilebilir form faktörde gürültü/boyut kaygısıyla Low-IQ LDO + slide switch lehine değiştirildi.)*
* **Anten Kuralı (Giyilebilir/Kompakt Form Faktör):** Form faktör "Giyilebilir" (Wearable) veya "Kompakt" olduğunda, yer kaplayan **PCB Meander (iz) anten KULLANILMAZ**. Bunun yerine **2.4 GHz Seramik Çip Anten (SMD Chip Antenna)** + gerekli **empedans eşleştirme (Pi-matching) devresi** kullanılır. Çip antenin datasheet'indeki keep-out/yerleştirme kılavuzu (genelde kart kenarına yakın, altında/çevresinde bakır dökümü olmayan bir bölge) harfiyen uygulanır; Pi-match ağının (genelde 2-3 pasif: seri L + paralel C, ya da benzeri topoloji) değerleri anten üreticisinin uygulama notundan alınır, kafadan seçilmez.
* **BOM Kuralı (Kalıcı, İstisnasız):** Lifecycle durumu **NRND, Obsolete veya EOL** çıkan hiçbir parça seçilmez — **prototip/hobi amaçlı olsa bile** bu kural gevşetilmez, daima Active ve güncel bir alternatife geçilir. Sadece "hâlâ LCSC/AliExpress'ten bulunabiliyor" gerekçesiyle NRND/Obsolete bir parça BOM'a kilitlenmez; bulunabilirlik ayrı bir konu, üretim durumu ayrı bir konudur. *(Gerekçe: Aynı projede önce ESP32-C3FN4'ün EOL, ardından MPU-6050'nin Obsolete olduğu tespit edildi; MPU-6050 durumunda kullanıcı ilk anda "yine de devam" seçeneğini reddedip ICM-42688-P'ye geçmeyi tercih etti — bu kuralın neden istisnasız olması gerektiğinin somut kanıtı.)*
* **Rapor-Veri Tutarlılığı (Zorunlu Çapraz Doğrulama, İstisnasız):** Oturum sonunda üretilen her özet/handover raporundaki ("temiz", "güvenli", "X artık yok", "Y sökülüp airwire'a çevrildi" gibi) HER durum iddiası, o oturumun ürettiği EN SON ham DRC/ERC JSON çıktısı programatik olarak okunup sayılmadan yazılamaz. Özellikle bir sorunun YOKLUĞUNU iddia eden cümleler (örn. "artık kısa devre yok", "board DRC-stable durumda") yasak — bunun yerine ilgili violation tiplerinin (`shorting_items`, `tracks_crossing`, vb.) en son DRC dosyasındaki sayısı açıkça 0 olarak doğrulanıp raporda o sayı gösterilir. "Muhtemelen", "olması gerekir", "sökülmüştü" gibi hafızaya/niyete dayalı ifadelerle son durum tahmin edilerek yazılamaz. Rapor, kendi verdiği özet rakamlarla (toplam violation/unrouted sayısı) hangi DRC dosyasının eşleştiğini dosya adıyla açıkça belirtir. *(Gerekçe: cm4_io_test projesinde AI_HANDOVER_REPORT.md, Ethernet netlerinin "ripped up to clean, unrouted airwires" olduğunu ve board'un "safe, DRC-stable state"te olduğunu iddia etti; ama raporun kendi verdiği rakamlarla (47 violation) birebir eşleşen drc_truly_final.json içinde bu netler üzerinde 5 gerçek shorting_items — biri CARRIER_3V3 güç hattına kısa devre dahil — ve 3 tracks_crossing bulundu. Rapor, kullanıcıya olduğundan daha güvenli bir durum bildirmişti; bu programatik doğrulama yapılmadan bir daha tekrarlanmamalı.)*
  > **Yaptırım mekanizması (2026-08-03):** Bu madde artık sadece bir üslup
  > kuralı değil — `python main.py promote` komutu, kanonik dosyaya
  > yazmadan ÖNCE taze DRC/ERC'yi + proje-özel kontratı ölçen bağımsız
  > verifier'ı (`bagimsiz_dogrulama.py`) + tüm `karar_birimleri.json`
  > kayıtlarının `KABUL_EDILDI` olduğunu GERÇEKTEN çalıştırıp doğrular;
  > biri bile FAIL ise kanonik dosyaya HİÇBİR ŞEY yazılmaz ("PROMOTION
  > RED"). Bkz. `scratch_yonetimi.py`/`bagimsiz_dogrulama.py`/
  > `karar_birimleri.py` ve `main.py::cmd_promote`.

---

## FAZ -0: ORTAM HAZIRLIĞI

* KiCad MCP araçlarının (`mixelpixx/KiCAD-MCP-Server`) yüklü olduğu doğrulanacaktır.
* Proje dizininde `.kicad_pro`, `TEST/` ve `DATASHEETS/` klasörlerinin varlığı denetlenecektir.
* Python betikleri için sistemdeki değil, KiCad'in dahili python ortamı kullanılacaktır.

---

### FAZ -0.5: OTONOM VERSİYON KONTROL (GIT) VE GERİ DÖNÜŞ (ROLLBACK) NOKTALARI

Yapay zeka (Claude/Ajan), tasarım sürecinde bir felaket (routing çıkmazı, DRC
patlaması) yaşanması ihtimaline karşı sistemi Git ile güvence altına almalıdır.

* **Otonom Commit Zorunluluğu:** Aşağıdaki 4 kritik dönüm noktasından
  herhangi birinde "PASS (Sıfır Hata)" alındığında, yapay zeka kullanıcıya
  sormadan arka planda terminalden `git add .` ve uygun bir mesajla
  `git commit -m "FAZ X: [Açıklama] tamamlandı"` komutlarını çalıştırmak
  zorundadır:
  1. Şematik çizimi ve ERC kontrolleri sıfır hata ile bittiğinde (Faz 2 sonu).
  2. Komponent yerleşimi (Placement) onaylandığında (Faz 4 sonu).
  3. Yönlendirme (Routing) ve DRC kontrolleri sıfır hata ile bittiğinde (Faz 7 sonu).
  4. Fabrika çıktıları (Gerber, BOM, CPL) üretildiğinde (Faz 8 sonu).
* **Rollback Stratejisi:** Eğer yapay zeka routing veya yerleşim sırasında
  içinden çıkılmaz bir döngüye girerse veya sistemi bozarsa, manuel düzeltme
  denemek yerine `git checkout` veya `git reset --hard` komutları ile bir
  önceki temiz commit'e dönerek B planı uygulamalıdır.

---

## FAZ 1: BOM, TEDARİK VE KILIF DOĞRULAMASI

* **Malzeme Seçiminde Anlık Yaşam Döngüsü Bildirimi (zorunlu, erken aşama):** Bir komponent aday olarak değerlendirilir değerlendirilmez (BOM'a kilitlenmeden ÖNCE, ilk seçim anında) üretim/yaşam döngüsü durumu (Active / NRND / Obsolete / EOL / Last Time Buy) kontrol edilip **kullanıcıya doğrudan raporlanacaktır** — sadece kafadan filtrelenip sessizce elenmeyecek, "şu parça X olduğu için elendi/seçildi" şeklinde açıkça belirtilecektir. Amaç: tasarım tamamlandıktan sonra tedarik sorunuyla karşılaşıp sıfırdan yeniden tasarım yapmak zorunda kalmamak — bu kontrol baştan, seçim aşamasında yapılır.
* **Referans/Yardımcı Parça ile Asıl BOM Parçası Ayrımı:** Footprint/sembol/3D model kaynağı olarak (SnapEDA, Ultra Librarian, datasheet vb.) başka bir MPN veya varyant (örn. farklı renk/paket kodu) incelenirse ve o kaynakta yaşam döngüsü bilgisi (özellikle Obsolete/EOL) görülürse, bu bilgi **hangi parçaya ait olduğu açıkça belirtilerek** (asıl seçilen BOM parçası mı, yoksa sadece referans/kaynak parça mı) kullanıcıya bildirilecektir — araştırma sırasında yan bilgi olarak edinilse bile sessizce geçilmeyecektir.
* Aktif komponentlerin küresel stok durumu kontrol edilecek, üretim durumu "Active" olmayanlar (NRND/Obsolete) elenecektir.
* **Kod karşılığı (`bom_lifecycle_koprusu.py`):** her satır `risk_skoru_hesapla()` ile puanlanır — `lifecycle_agirlik (Active=0/NRND=0.6/EOL=1.0) + dusuk_stok(+0.3) + single_source(+0.3) + uzun_lead_time(+0.2)`. Skor **>0.5** ise `find_pin_compatible()` çağrılır — aday listesi **paket + pinout + elektriksel parametre** üçünün de eşleştiği (`ayni_pinout AND elektriksel_param_eslesiyor`) adaylarla sınırlanır; "aynı paket" TEK BAŞINA yeterli sayılmaz. Uygun aday yoksa `NEEDS_HUMAN`; aday footprint değiştiriyorsa (`footprint_degisiyor=True`) stackup/routing'e feedback açılır.
* Ağ erişimi/API key yoksa (`nexar_sorgula(api_key=None)`) sonuç `kaynak="TBD"` döner — hayali stok/fiyat/MPN **asla** üretilmez, kullanıcıya CONFIRM olarak raporlanır.
* LDO, Level Shifter gibi kritik komponentlerin pin dizilimine sahip yedek (Drop-in replacement) modeli belirlenecektir.
* Şematik sembolündeki pin sayıları ile datasheet pin sayıları eşleştirilecektir (Soğutucu pad'in GND'ye bağlanması dahil).
* Kütüphane adı (lib_id) ile Üretici Parça Numarası (MPN) tamamen tutarlı olacaktır.
* Pasif eleman boyutları (0402, 0603) dizgi fabrikasının kapasitesine göre seçilecektir.

---

### FAZ 1.5: BİLEŞEN SEÇİMİ VE GÜVENLİK PAYI (EE DERATING FİLTRESİ)

Yapay zeka veya tasarımcı, BOM (Malzeme Listesi) oluştururken aşağıdaki Elektrik/Elektronik (EE) fiziksel kısıtlarına uymak zorundadır:

* **Kapasitör Voltaj ve Dielektrik Kuralı (DC Bias):** MLCC seramik kondansatörlerin voltaj değeri (Voltage Rating), çalışacağı hattın nominal voltajının EN AZ 2 KATI olmalıdır (Örn: 5V hat için minimum 10V veya 16V kondansatör). Güç dekuplajı için sadece X7R veya X5R dielektrik kullanılabilir. Hassas analog, RF ve osilatör devreleri için sadece C0G/NP0 kullanılabilir. Y5V ve Z5U kullanımı kesinlikle yasaktır.
* **Direnç Güç Düşümü (Power Derating):** Seçilen tüm SMD/TH dirençlerin anma gücü (Power Rating), üzerinden geçecek hesaplanmış maksimum gücün en az 2 katı olmalıdır (%50 Derating kuralı). Güç hattı veya voltaj bölücü dirençleri ısınma kaynaklı değer değişimini önlemek için asla sınırda çalıştırılamaz.
* **Bobin Doyma Akımı (Inductor Saturation):** Anahtarlamalı güç kaynakları (SMPS) için seçilen bobinlerin Doyma Akımı (Isat), regülatörün anlık tepe akımından (Peak Current) EN AZ %30 daha yüksek olmalıdır. İndüktör manyetik doyuma ulaşmamalıdır.
* **Tolerans Öncelikleri:** Analog sensör geri beslemeleri, voltaj bölücüler ve ADC girişlerindeki dirençler en fazla %1 toleranslı seçilmelidir. Sadece dijital Pull-up/Pull-down dirençleri %5 toleranslı olabilir.

---

## FAZ 2: ŞEMATİK, MATEMATİKSEL KONTROL VE ELEKTRİKSEL KURALLAR

* **Güç Voltajı:** Voltaj sınırları datasheet "Recommended Operating Conditions" tablosundan çekilecektir.
* **Akım Geçidi ($I_{max}$):** Hedef entegrelerin çekeceği maksimum anlık akımlar toplanacak ve regülatörün verebileceği akım %25-%30 oranında daha fazla tutulacaktır. Bu durum CSV olarak raporlanacaktır.
* **Dropout Kontrolü:** Regülatör giriş-çıkış farkı, datasheet'teki değerden büyük olmalıdır: $V_{in} - V_{out} > V_{dropout}$. Bu denklik CSV raporuyla kanıtlanacaktır.
* **Tolerans Zinciri ve Worst-Case Analizi (zorunlu):** Kademeli güç rayları (örn. Buck→LDO1→LDO2) arasındaki marj hesapları **asla sadece nominal değerlerle** yapılmayacaktır. Bir üst kademenin datasheet'teki çıkış toleransı (örn. ±%1.5 veya ±40mV gibi ΔVOUT spesifikasyonu) bir alt kademenin worst-case giriş gerilimine mutlaka yansıtılacak, marj bu worst-case değer üzerinden hesaplanacaktır (Vin_worst = Vin_nominal − |ΔVOUT_üst_kademe|). Kullanılan MIN/MAX datasheet değerlerinin tüm çalışma sıcaklığı aralığında mı (örn. "at operating temperature range TJ=-40 to +125") yoksa sadece 25°C'de mi (TYP) geçerli olduğu tabloyla teyit edilip raporda açıkça belirtilecektir — sıcaklık ayrıca bir marj daralmasına yol açıyorsa bu da hesaba katılacaktır. *(Gerekçe: LDO2 dropout marjı ilk hesapta nominal Vin ile %69 çıkmıştı; LDO1'in kendi ±40mV toleransı eklenince gerçek worst-case marj %57.7 olarak düzeltildi — hâlâ PASS ama ilk sayı yanıltıcıydı.)*
* **Haberleşme:** I2C hatları (SDA, SCL) "Open-Drain" yapısına uygun 2.2kΩ - 4.7kΩ pull-up dirençleri ile VCC'ye bağlanacaktır.
* **Seviye Dönüştürücü:** Farklı voltaj aralıkları arasında (örn. 1.8V ve 3.3V) level shifter zorunludur ve açık drenaj uyumlu seçilmelidir.
* **Kararlılık:** Entegre pinlerine minimum decoupling kapasitörleri eklenecektir.
* **Güç Net İsimlendirmesi:** Aynı rayı görünüşte farklı iki isimle (örn. `+3.3V` ve `+3V3`) isimlendirmek yasaktır. Tek bir kanonik sembol kullanılacaktır.
* **Kablo Çizimi:** Çapraz (diagonal) kablo asla çizilmez; yalnızca yatay ve dikey (90 derece) dik hatlar kullanılır.
* **Bağlantısız Pinler:** Tasarıma dahil olmayacak ve fiziksel olarak boş kalacak yedek pinlere mutlaka X (No-Connect) işareti konacaktır.
* **Açık Pin Koruması / Akıllı No-Connect Kuralı (Adım 7):** Projenin mantıksal çalışması için gereken aktif pinler (sensör haberleşme hatları, I2C, SPI, UART, güç veya harici konnektöre/header'a taşınacak hatlar) **kesinlikle** No-Connect ile kapatılamaz. ERC hatasını susturmak için aktif bir pin körleştirilemez; bu pinler ya bir net adına (kabloya) ya da gelecekteki genişleme/programlama için bir pin header çıkışına yönlendirilmek zorundadır.
* **Doğru Pin Atamaları (Dedicated Clock Pins):** Kartta bir FPGA veya gelişmiş bir mikrodenetleyici varsa, saat sinyalleri rastgele pinlere bağlanamaz. Çiplerin veri sayfasındaki (datasheet) "Dedicated Clock Pins" (Özel Saat Pinleri) üzerinden giriş yapılması zorunludur. Çip içindeki CDC mekanizmaları sadece bu pinlere bağlıdır.
* **Sinyal Bütünlüğü ve Seri Sonlandırma:** Saat sinyali yollarında kenar yuvarlanmalarını ve yansımaları (reflection) önlemek için empedans uyumu yapılmalı ve kaynağa yakın seri sonlandırma dirençleri (series termination resistors) eklenmelidir. Bozulmuş bir saat sinyali meta-stabilite tetikleyicisidir.

---

## FAZ 3: ŞEMATİK DOĞRULAMASI

* Şematik bağlantısı datasheet pini ile uyumlu mu diye çapraz kontrol edilecektir (örn. kazara NC bırakılmış fonksiyonel pinler kontrol edilecektir).
* **MIPI ve Yüksek Hızlı Diferansiyel Çift Polarite Doğrulaması (zorunlu, ayrı adım):** Net listesinin topolojik tutarlılığı ("aynı net ismi → aynı pinler", ERC'nin "bağlı mı" kontrolü) **diferansiyel çiftlerin (P/N) doğru polarite/lane ile bağlandığını KANITLAMAZ** — ERC ters bağlanmış bir P/N çiftini yakalayamaz. Bu yüzden host (örn. Jetson J20) ve sensör/IC'nin resmi pin tabloları **yan yana, birincil kaynaktan (datasheet PDF'i doğrudan açılarak, önceki oturumun özetine güvenilmeden) her diferansiyel çift için tek tek** karşılaştırılacak ve sonuç ilgili doğrulama raporunda (`TEST/pin_karsilastirma.md` veya `TEST/simulasyon_raporu.md`) tablo halinde belgelenecektir. Bu adım, genel "pin ↔ datasheet karşılaştırması" maddesinden ayrı, MIPI/USB/Ethernet gibi tüm yüksek hızlı diferansiyel arayüzler için tekrarlanmalıdır.
* ERC testi çalıştırılacak ve fatal/logic hatalar "0" olana kadar düzeltilecektir. PWR_FLAG yalnızca kök neden bulunduktan sonra eklenecektir.
* Bağımsız olarak netlist dışa aktarılıp doğrulanacaktır.
* Üretici modelleri veya temel parametrelere dayalı davranışsal simülasyon raporu `TEST/simulasyon_raporu.md` olarak kaydedilecektir.
* **HANDOVER.md Zorunluluğu (Şematikten PCB'ye Geçiş):** Şematik fazından PCB fazına geçilirken ajanın "Niyet ve Kısıt" aktarımı yapması zorunludur. `HANDOVER.md` dosyası üretilmeden PCB aşamasına geçilemez. PCB ajanı, şematik ajanının bu dosyada belirttiği elektriksel kısıtlara (akım değerleri, gürültü izolasyonu, kümeleme) uymak zorundadır; uyamıyorsa durumu kullanıcıya (`NEEDS_HUMAN`) raporlamalıdır.

---

## FAZ 4: MEKANİK SINIRLAR VE YERLEŞİM (PLACEMENT)

* Edge.Cuts (Kart Sınırları) kasanın iç mekaniğine göre DXF/STEP dosyasıyla milimetrik eşlenecektir.
* **Kod karşılığı (`mekanik_dxf_koprusu.py`):** `import_board_outline()` birim (mm/mil) çevirimi + **çapa kontrolü** yapar — bilinen bir delik koordinatıyla outline'daki en yakın delik arası sapma >0.5mm ise birim/orijin hatası şüphesiyle `ValueError` fırlatır (otomatik "toleransla düzeltme" YAPILMAZ, insan onayı gerekir). Kutu tavanı düz değilse `derive_keepouts()` STEP'ten türetilmiş bölge-bazlı `TavanHaritasiBolgesi` kullanır; `z_kontrolu_yap()` her parçanın body-height'ının bölge `max_allowed_height_mm`'ini (CLEARANCE payı düşülmüş) aşmadığını doğrular — bu, placement bariyerinin SABİT girdisidir.
* Stereo/optik tasarımlarda IPD tolerans zinciri `ipd_tolerans_zinciri_hesapla()` ile worst-case (toplam) veya RSS (kare-kök-toplamı) yöntemiyle hesaplanır; optik merkez ofseti `optik_merkez_ofseti_uygula()` ile footprint origin'inden ayrıştırılır (optik merkez ≠ footprint origin).
* Montaj deliklerinin etrafına pul/vida ezilme riskine karşı en az 3-5 mm Keep-Out (Yasaklı Bölge) çizilecektir.
* **Mekanik Stres ve Lehim Güvenliği:** Titreşimli endüstriyel ortamlar göz önüne alınarak, kart esnemesinden (flexure) kaynaklı mikroskobik lehim çatlamalarını (micro-cracks) önlemek adına montaj deliklerinin etrafına mekanik keep-out bölgeleri bırakılacak ve kritik pasifler (özellikle büyük seramik kondansatörler ve BGA/CSP paketler) bükülme bölgelerinden uzak tutulacaktır.
* Z-Ekseni yüksekliği kontrol edilecek, konnektörler kart kenarından tak-çıkar işlemine uygun hizalanacaktır.
* Lens tutucu gibi aparatların iz düşümleri "Keep-Out" olarak çizilecek, altına pasif bileşen konmayacaktır.
* **Decoupling Kuralı:** Bypass kapasitörleri VCC/VDD pinine en fazla 1.5 mm mesafeye konumlandırılacaktır.
* **Osilatör Kuralı:** Kristaller ana entegreye simetrik olarak en fazla 5 mm mesafede olacaktır.
* **Termal Sürgün:** Isı üreten (LDO vb.) parçalar ile ısıya hassas (Osilatör, sensör) parçalar kartın zıt köşelerine yerleştirilecektir.
* **Termal Yönetim ve Isı İzolasyonu (Thermal Drift):** Yüksek akım çeken ve ısınan komponentler (PMIC, LDO, Motor Sürücüler, Güç MOSFET'leri), sıcaklığa duyarlı komponentlerden (Osilatörler/Kristaller, Referans Voltajı entegreleri) uzağa yerleştirilmelidir. Çok ısınan çiplerin termal pad'leri altına ısıyı alt katmanlara dağıtmak için termal via matrisi (örneğin 0.3mm delik, 1.2mm aralıklarla) yerleştirilmesi zorunludur.
* Sensör ile konnektör arasında optik merkez hizalaması ve sanal düz hat kurulacaktır.
* **Komponent Gölgelemesi (Shadowing) ve Dalga Lehimi Kuralı:** Uzun veya yüksek komponentlerin (örneğin konnektörler, elektrolitik kondansatörler), küçük SMD pasifleri (0402/0603) "rüzgar gölgesinde" bırakarak soğuk lehime sebep olmasını engelle. Lehim akış/fırın yönü dikkate alınarak, küçük komponentler büyük komponentlerin hemen arkasına veya bitişiğine gizlenmeyecek şekilde yerleştirilmelidir.

---

## FAZ 4b: MEKANİK-TERMAL ENTEGRASYON

Faz 4'e kadar kasa (mekanik STEP/DXF) SADECE bir 3D keepout TEHDİDİ olarak
ele alındı (`z_kontrolu_yap()` — "buraya parça yükselemez"). Bu faz, kasayı
AYRICA bir ısıl TEMAS HEDEFİ olarak da ele alır — mekanikçinin bıraktığı bir
"heatsink boss" (termal çıkıntı) yüzeyi, ısı kaynağı bir komponentin ısısını
kasaya aktarabileceği bir FIRSATTIR, sadece bir engel değildir. **Kod
karşılığı: `ecad_mcad_termal_kopru.py`.**

* **Kasa Temas Yüzeyi Tespiti:** `soguturucu_yuzey_bul(x, y, yuzeyler)`,
  verilen bir komponent koordinatının kasadaki bir `TermalTemasBolgesi`
  (STEP'ten türetilmiş metal temas yüzeyi) içine düşüp düşmediğini ve o
  yüzeyin `z_boslugu_mm` değerini döndürür. Kasa STEP verisi paylaşılmadıysa
  sessizce `None` döner — hata FIRLATMAZ, bu faz tamamen ATLANIR.
* **B.Mask Açıklığı Zorunluluğu:** Bir komponentin `guc_yayilimi_W`'si
  kritik eşiği aşıyorsa VE altında bir kasa temas yüzeyi varsa,
  `termal_yonetim_ve_mask_kontrolu()` (mevcut `pcb_stackup_planner.
  termal_yonetim_kontrolu()`'nu ÇAĞIRARAK genişletir, YENİDEN YAZMAZ) artık
  sadece termal via eksikliğini değil, **B.Mask açıklığı eksikliğini de**
  hata olarak döndürür — component altı çıplak bakıra çıkamıyorsa kasaya
  ısıl temas kuramaz. Gerçek B.Mask poligonu `b_mask_poligonu_pcb_ye_yaz()`
  ile PCB'ye yazılır.
* **Yüzey Kaplaması Zorunluluğu (ENIG):** B.Mask açıklığı TEK BAŞINA
  yetmez — o bölgenin yüzey kaplaması BOM/fabrikasyon notunda **ENIG**
  olarak zorunlu kılınmalı (HASL DEĞİL). Aksi halde çıplak bakır zamanla
  oksitlenir ve termal ped/kasa temasının performansı zamanla düşer.
  `termal_yonetim_ve_mask_kontrolu()` bunu ayrı bir uyarı olarak döndürür.
* **Termal Ped Kalınlığı:** `termal_ped_kalinligi_hesapla(kasa_z_boslugu_mm,
  sikisma_orani=0.25)` — ped, `kasa_z_boslugu_mm / (1 - sikisma_orani)`
  kalınlığında olmalı ki vidalandığında %20-30 ezilip boşluğu TAM
  doldursun (ne ince kalıp boşluk bırakmalı, ne kalın kalıp PCB'ye aşırı
  mekanik gerilim bindirmeli). Sonuç `termal_ped_bom_notu_uret()` ile
  `"Thermal Pad — {kalınlık}mm"` formatında BOM'a yazılır.
* **Termal Bariyer (Edge.Cuts Frezeleme Yarığı) — Mekanik/Isıl Çelişki:**
  Isı kaynağı ile hassas parça arasındaki mesafe "zıt köşe" kuralını
  (yukarıdaki Faz 4 maddesi) sağlasa BİLE, ikisi de aynı kalın bakır
  katmanına (örn. 2oz GND) bağlıysa ısıl olarak yeterince ayrışmıyor
  demektir — `termal_bariyer_gerekli_mi()` bunu tespit eder.
  `edge_cuts_yarigi_oner()` bir frezeleme yarığı (milling slot) önerir —
  **AMA SADECE** slot ile kart kenarı arasında Faz 4'ün "Mekanik Stres ve
  Lehim Güvenliği" kuralına uygun minimum bir "web" (kalan malzeme)
  genişliği (`MIN_WEB_GENISLIGI_MM`) bırakılabiliyorsa. Bu çelişki
  çözülemiyorsa (web yetersizse) fonksiyon KASITLI olarak `None` döner —
  `termal_bariyer_ozetle()` bunu `NEEDS_HUMAN` olarak raporlar. Termal
  izolasyon KAZANIP mekanik dayanım KAYBETMEK yasaktır; sessizce bu ödün
  verilmez.
* **Kasa Verisi Yoksa:** Mekanik STEP paylaşılmadıysa `ecad_mcad_termal_kopru.py`
  tamamen atlanır — hiçbir fonksiyonu hata fırlatmaz, sadece boş/`None`
  sonuç döner (Faz -0'ın "veri yoksa dur, hata fırlatma" disiplini).

---

## FAZ 5: GÜÇ BÜTÜNLÜĞÜ (PI) VE TERMAL TAHLİYE

* Ana besleme yolları IPC-2221 standartlarına göre çekeceği akıma ve %20 güvenlik payına göre boyutlandırılacaktır.
* Yol kalınlığı ve akım kapasiteleri hesaplanıp `TEST/Faz5_Voltaj_Dusumu.csv` içerisine kaydedilecektir.
* Yüksek akım hatlarında tek via değil, akım paylaştırıcı (dikiş) via'lar kullanılacaktır (0.3mm via = ~1A taşır kuralı).
* Parazitik direnci düşürmek için kapasitörlerin GND/VCC pedleri düzleme "Double Via" ile inecektir.
* Isınan entegrelerin (LDO) altına çok sayıda "Termal Via" eklenecektir.
* Yüksek akım pedleri "Thermal Relief" yerine doğrudan "Solid" (tamamen bakırla kaplı) şekilde bağlanacaktır.

---

## FAZ 6: SİNYAL BÜTÜNLÜĞÜ (SI) VE EMI/EMC KORUMA

* Diferansiyel hatlar üretici empedans hedeflerine göre çizilecektir (örn. 100Ω diferansiyel empedans için 0.12mm iz, 0.2mm boşluk).
* **Kesintisiz (Solid) Dönüş Yolu:** Yüksek hızlı sinyal katmanının altında yarık (split) olmayan bütün bir GND düzlemi zorunludur. **Kod karşılığı:** `kicad_koprusu.py::check_reference_plane_continuity()` her yüksek hız iz segmentinin iki ucunu + orta noktasını referans düzlem poligonuyla point-in-polygon testinden geçirir — standart clearance/width DRC'si bu ihlali YAKALAMAZ (o bakır-bakır mesafesine bakar, düzlem sürekliliğine değil), bu yüzden ayrı bir kapı olarak zorunludur.
* Sinyal katman değiştiriyorsa hemen yanına (~12mm yakınına) dönüş akımı için GND via'sı konulacaktır.
* **3W Kuralı:** Paralel yüksek hızlı hatlar arasında, yol genişliğinin en az 3 katı (3W) boşluk bırakılacaktır.
* **5W Kuralı:** Saat (Clock) sinyalleri diğer hatlardan izole edilecek, gerekirse Guard Trace ile korunacaktır.
* Dış dünyayla temas eden sinyal konnektörlerine anında koruma sağlaması için mümkün olan en yakın mesafeye TVS Diyotları ve EMI şok bobinleri (CMC) yerleştirilecektir.
* **ESD (Statik Elektrik) Koruması:** Jetson FFC konnektörü (J20) ve dış dünyaya açılan tüm güç/veri hatlarının girişine, entegreleri korumak için düşük kapasitanslı MIPI uyumlu ESD koruma diyot dizileri (TVS Array) en yakın mesafeye eklenecektir. Genel amaçlı TVS diyotları yerine bu diyot dizilerinin tercih edilme sebebi, yüksek kapasitanslarının MIPI D-PHY gibi yüksek hızlı diferansiyel hatlarda sinyal bütünlüğünü bozmasıdır.
* **Ortak Mod Gürültü ve İzolasyon:** Endüstriyel ortam koşullarında ground loop (toprak döngüsü) ve ortak mod gürültülerini engellemek için gerekli filtreleme (örn. ortak mod choke) ve topraklama stratejileri (tek noktalı analog/dijital GND birleşimi vb.) uygulanacaktır.
* **Çapraz Karışmayı (Crosstalk) Önleme ve CDC İzolasyonu:** Farklı saat alanlarına (örneğin 50 MHz ve 125 MHz gibi farklı clock domain'ler) ait saat yolları (clock traces) PCB üzerinde asla yan yana veya alt alta (farklı katmanlarda) paralel yürütülemez. Aksi halde birbirlerinin üzerine gürültü (jitter) bindirirler.
* **Güç Bütünlüğü (PI) ve Parazitik İndüktans Minimizasyonu:** Dekuplaj (bypass) kondansatörlerini sadece çipe yakın yerleştirmek yetmez; parazitik indüktansı (ESL) önlemek için VDD ve GND via'ları kondansatör pedlerine olabildiğince bitişik (mümkünse via-in-pad veya çok kısa kalın yollarla) atılmalıdır. Hedef, akım dönüş döngü alanını (Loop Area) minimuma indirmektir.
* **Analog/Dijital İzolasyon (Mixed-Signal Design):** ADC, DAC veya Op-Amp gibi hassas analog devreler ile MCU/FPGA gibi gürültülü dijital devreler aynı PCB üzerindeyse, Analog GND (AGND) ve Dijital GND (DGND) alanları birbirinden izole edilmeli (moating) ve sadece güç kaynağı girişinde tek bir noktadan (Star Grounding / Net Tie) birleştirilmelidir. Dijital dönüş akımları ASLA analog alanın altından geçemez.
* **Esnek Kablo (FFC/FPC) Sınırları:** Yüksek hızlı MIPI CSI-2 hatlarını taşıyan FFC kablolarının sinyal bütünlüğünü bozmaması için prototip aşamasında kısa tutulması ve empedans kontrollü seçilmesi şart koşulacaktır.

---

## FAZ 7: YIĞIN (STACKUP) VE KATI YÖNLENDİRME (ROUTING)

* **4 Katman Stackup:** L1 (F.Cu - Yüksek Hızlı Sinyal), L2 (In1.Cu - Kesintisiz GND Düzlemi), L3 (In2.Cu - Güç Dağıtımı), L4 (B.Cu - Düşük Hızlı Sinyal) standart olarak kullanılacaktır.
* **Routing Önceliği:** İlk önce GND düzlemi dökülür, sonra kritik sinyaller (F.Cu), sonra güç hatları (In2.Cu), en son dijital sinyaller (I2C, GPIO) çizilir.
* **Geometri Kuralı:** Asla 90 derece dik açı çizilmez; tüm dönüşler 45 derece veya kavisli (arc) olacaktır.
* Gözyaşı Damlası (Teardrop) via ve yol birleşim noktalarına mutlaka eklenecektir.
* Havada asılı kalan "Ada" (Dead Copper) bakır dökümleri temizlenecektir.
* Büyük GND dökümleri düzenli aralıklarla Via Stitching kullanılarak zımbalanacaktır.
* Asit tuzaklarını önlemek için yolların pedlere bağlandığı dar (V şekilli) açılar düzeltilecektir.
* **Bakır Dengesi ve Eğilme (Warping) Önlemi:** Reflow fırınında kartın bükülmesini (Bow & Twist) önlemek için üst ve alt katmanlardaki bakır yoğunluğu simetrik olmalıdır. Yönlendirme ve poligon dökümleri bittikten sonra, geniş boşluk kalan dış katmanlara mekanik dengeyi sağlamak amacıyla (elektriksel işlevi olmasa bile) "Copper Thieving" (Dengeleme Bakırı) veya taralı (hatched) bakır dökümü uygulanmalıdır.
* **Diferansiyel Faz Uyumu (Phase/In-Pair Skew Matching):** Yüksek hızlı diferansiyel çiftlerin (MIPI, USB, PCIe) uzunluk eşlemesi, sadece hattın sonunda genel toplam uzunluk üzerinden yapılamaz. Köşe dönüşlerinde (corner) dış izde oluşan uzunluk farkı, asimetrinin başladığı köşeye maksimum 15mm mesafe içinde, ilgili köşe yakınına "Bump (Küçük menderes)" eklenerek düzeltilmelidir (Uncoupled length minimizasyonu).
* **Via Stub (Kör Uç) Minimizasyonu:** 1 GHz ve üzeri yüksek hızlı hatlar (MIPI, Gigabit Ethernet vb.) iç katmanlara yönlendirilirken Via Stub (kullanılmayan via uzantısı) etkisi hesaba katılmalıdır. Tasarımcı, empedans yansımasını önlemek için ya sinyali tüm katmanları geçecek şekilde (Örn: Top'tan Bottom'a) yönlendirmeli ya da üreticiye (Fab) "Backdrilling" (Fazlalık via kısmını matkapla temizleme) kuralı tanımlamalıdır.
* **Yüksek Voltaj İzolasyonu (Creepage & Clearance):** 50V ve üzeri gerilim taşıyan hatlar (Şebeke/Röle/Motor hatları) ile düşük voltajlı dijital devrelere ait netler arasında IPC-2221 standartlarına uygun Yüzey Atlama (Creepage) mesafesi bırakılmalıdır (Örn: 220V için min. 2.5mm). Eğer fiziksel yer darlığından bu mesafe sağlanamıyorsa, iki bölge arasına PCB kesim (Edge.Cuts/Milling) katmanında fiziksel "İzolasyon Yarığı (Isolation Slot)" açılması zorunludur.

---

## FAZ 8: DFM, DFT VE ÇIKTILAR (RELEASE TO FAB)

* Her voltaj rayına ve GND'ye çıplak bakır "Test Point (TP)" konulacaktır (MIPI veya Clock gibi hatlara kesinlikle konulmaz). **Kod karşılığı (`kicad_koprusu.py`):** `insert_test_points(rail_tree, debug_netleri)` her güç rayı + zorunlu debug netlerini (SWDIO/SWCLK/nRST/UART_TX/UART_RX) kapsar; `tp_kapsam_kontrolu()` güç+debug %100 hedefini doğrular; `generate_bringup_checklist()` rail enable sırasını ZORLAYARAK (sıra hatası core'a hasar verebilir) `bringup_checklist.md` üretir. TP'ler şematik fazında (Faz 2/3) doğar, burada sadece mekanik erişilebilirliği + kapsamı doğrulanır.
* Dizgi makineleri için kartın asimetrik 3 köşesine 1mm çıplak bakır "Fiducial Marks" (Optik Hizalama) yerleştirilecektir. Panel varsa (`uretim_zinciri_koprusu.py::panelizasyon_kontrolu()`): ≥3 global fiducial + BGA varsa local fiducial + ≥5mm rail genişliği + de-panel hattı hassas parçalardan (kristal, BGA köşesi) ≥5mm uzak.
* Serigrafideki referans yazıları açık pedlerin veya via deliklerinin üzerinde olmayacak şekilde boş alanlara kaydırılacaktır.
* **Solder mask barajı (mask dam) — clearance DRC'sinden AYRI kontrol:** `baraj = pad_arasi_bosluk − 2×mask_expansion`. Özellikle ESD dizisi/konnektör gibi pin-arası kanaldan geçen izlerde kritik (5V ile veri hattı birleşirse host portu yanar). **Kod karşılığı (`pcb_highspeed_escape.py`):** `maske_baraji_kontrolu(kanal, iz_genisligi_mm, fab_min_baraj_mm)` — fab minimumunun (tipik 0.20-0.25mm) altına düşen her ihlali raporlar; standart clearance DRC'si bunu YAKALAMAZ. İz genişliğini burada AKIM değil BARAJ belirler — `maksimum_iz_genisligi_icin_baraj_mm()` ile geri çözülür, sonra IPC-2221 ile akımın hâlâ yettiği ayrıca doğrulanır.
* Fab rotasyon-map'i VERSİYONLANMALIDIR (yoksa tüm parti ters lehim). **Kod karşılığı:** `rotation_map_versiyonla()` içerik hash'i üretir; `rotasyon_duzeltmesi_uygula()` eşleşmeyen her footprint için sessiz 0-ofset varsaymak yerine UYARI döner. `check_orientation()` kutuplu parça (diyot/IC pin-1/LED/elektrolitik) yönü ile üretilen CPL açısını çapraz kontrol eder — DRC yön bilmez, bu adım olmadan tüm kutuplu parti ters monte edilebilir.
* DRC ve ERC sıfır hata verene kadar tamamlanacaktır.
* **Çıktılar:** Gerber, Drill (.drl), tam eksiksiz BOM ve Pick & Place için merkez dosyası (CPL/POS) üretim formatında dışa aktarılacaktır. Pick-point = gövde/courtyard centroid, footprint origin DEĞİL (`generate_cpl_file()`).

---

## EK: Hızlı Kontrol Listesi (Checkbox)

> Bu ek, önceden ayrı bir dosya (`Aşamalı_Kontrol_Listesi.docx`) olarak
> tutulan checkbox formatını yukarıdaki fazların GÜNCEL haliyle tek dosyada
> toplar. O eski dosya, MASTER_RULEBOOK'a sonradan eklenen bazı maddeleri
> (worst-case tolerans zinciri, MIPI/diferansiyel polarite doğrulaması,
> referans/asıl-parça ayrımı, anlık yaşam-döngüsü bildirimi) içermiyordu —
> bu yüzden ayrı tutulmadı, buraya güncel haliyle taşındı. Detaylı gerekçe
> ve formüller için ilgili fazın yukarıdaki tam metnine bakılmalı; burası
> sadece hızlı işaretleme içindir.

### Bölüm 0 — Raporlama ve Datasheet
- [ ] Her hesaplama sonucu `TEST/` içine CSV olarak kaydedildi, "PASS" alındı mı?
- [ ] Her entegrenin datasheet'i (BOM'a ilk girişte de, sonradan eklenen bir parça için de) şematiğe işlenmeden ÖNCE `DATASHEETS/` klasörüne kaydedildi mi?
- [ ] Pil beslemeli sistemde klasik LDO (AMS1117 vb.) değil, ULDO veya %90+ verimli Buck kullanıldı mı? Giyilebilir/Kompakt form faktörde bu, Low-IQ ULDO + fiziksel slide switch olarak mı uygulandı?

### Faz -0 — Ortam Hazırlığı
- [ ] KiCad MCP araçları yüklü mü kontrol edildi mi?
- [ ] `.kicad_pro`, `TEST/`, `DATASHEETS/` klasörleri var mı?
- [ ] Python betikleri için KiCad'in dahili python ortamı kullanılıyor mu?

### Faz 1 — BOM, Tedarik, Kılıf
- [ ] Her aday parça, BOM'a kilitlenmeden ÖNCE yaşam döngüsü/stok durumu (Active/NRND/Obsolete/EOL/LTB) kontrol edilip kullanıcıya açıkça raporlandı mı?
- [ ] Risk skoru >0.5 çıkan parçalar için pin-uyumlu alternatif (paket+pinout+elektriksel eşleşme) arandı mı; bulunamazsa NEEDS_HUMAN mi işaretlendi?
- [ ] Referans/yardımcı kaynaklarda (SnapEDA vb.) görülen bir Obsolete/EOL bilgisi varsa, hangi parçaya ait olduğu (asıl BOM parçası mı, kaynak parça mı) netleştirilerek bildirildi mi?
- [ ] Aktif olmayan (NRND/Obsolete/EOL) parçalar **istisnasız** (prototip dahil) elendi mi, Active bir alternatife geçildi mi?
- [ ] Kritik parçalar (LDO, Level Shifter) için pin-uyumlu yedek (drop-in) belirlendi mi?
- [ ] Şematik pin sayısı datasheet ile eşleşiyor mu (soğutucu pad/GND dahil)?
- [ ] lib_id ile MPN tutarlı mı?
- [ ] Pasif boyutları (0402/0603) dizgi fabrikasının kapasitesine uygun mu?

### Faz 2 — Şematik, Matematik, Elektriksel Kurallar
- [ ] Voltaj sınırları datasheet "Recommended Operating Conditions"tan mı alındı?
- [ ] Akım toplamı yapılıp regülatör kapasitesi %25-30 payla mı seçildi (CSV'de)?
- [ ] Dropout kontrolü ($V_{in}-V_{out} > V_{dropout}$) CSV ile kanıtlandı mı?
- [ ] Kademeli raylarda worst-case marj, bir üst kademenin ΔVOUT toleransı düşülerek mi hesaplandı (sadece nominal değil)? Kullanılan MIN/MAX değerlerin sıcaklık aralığı mı yoksa 25°C mi olduğu belirtildi mi?
- [ ] I2C pull-up (2.2k-4.7kΩ) open-drain uyumlu mu?
- [ ] Farklı voltaj seviyeleri arasında open-drain uyumlu level shifter var mı?
- [ ] Decoupling kapasitörleri eklendi mi?
- [ ] Güç rayı tek kanonik isimle mi anıldı (+3.3V vs +3V3 karışıklığı yok mu)?
- [ ] Kablolar sadece dik açı (90°) ile mi çizildi?
- [ ] Boş pinlere X (NC) kondu mu — **ama** aktif/fonksiyonel pinler (I2C/SPI/UART, güç, harici konnektör) yanlışlıkla NC ile kapatılmadı mı?

### Faz 3 — Şematik Doğrulaması
- [ ] Her pin datasheet ile çapraz kontrol edildi mi (özellikle çoklu-instance/simetrik tasarımlarda kopyala-yapıştır kaynaklı kazara NC var mı)?
- [ ] Yüksek hızlı diferansiyel çiftlerin (MIPI/USB/Ethernet) P/N polaritesi, host ve sensörün resmi pin tabloları birincil kaynaktan yan yana karşılaştırılarak doğrulandı ve `TEST/pin_karsilastirma.md`'ye tablo halinde işlendi mi? (ERC bunu YAKALAMAZ.)
- [ ] ERC çalıştırıldı, fatal/logic hata "0" mı? PWR_FLAG sadece kök neden bulunduktan sonra mı eklendi?
- [ ] Netlist bağımsız olarak dışa aktarılıp doğrulandı mı?
- [ ] Simülasyon raporu `TEST/simulasyon_raporu.md`'ye yazıldı mı; kullanılan modelin (gerçek üretici modeli mi, davranışsal mi) türü ve davranışsal ise neyi yansıtmadığı belirtildi mi?

### Faz 4 — Mekanik ve Yerleşim
- [ ] Edge.Cuts kasa DXF/STEP ile milimetrik örtüşüyor mu? Birim(mm/mil)/orijin çapa kontrolü yapıldı mı (bilinen delik koordinatıyla)?
- [ ] Montaj delikleri etrafında 3-5mm keep-out var mı; kutu tavanı düz değilse bölge-bazlı 3D yükseklik haritası (max_allowed_height_mm) çıkarıldı mı?
- [ ] Stereo/optik tasarımda IPD tolerans zinciri (worst-case veya RSS, hangisi seçildiği belirtilerek) hesaplandı mı; optik merkez ofseti footprint origin'inden ayrı mı ele alındı?
- [ ] Kritik pasifler ve BGA/CSP paketler kart bükülme bölgelerinden uzak mı (mekanik stres/lehim çatlağı riski)?
- [ ] Z-ekseni yüksekliği ve konnektör hizası kasaya uygun mu?
- [ ] Decoupling ≤1.5mm, osilatör ≤5mm mesafede mi?
- [ ] Isı üreten ve ısıya hassas parçalar zıt köşelerde mi?
- [ ] Sensör-konnektör arasında optik hizalama/sanal düz hat var mı?

### Faz 4b — Mekanik-Termal Entegrasyon
- [ ] Kasa STEP verisi varsa, kritik güçlü komponentler için `soguturucu_yuzey_bul()` ile temas yüzeyi kontrolü yapıldı mı?
- [ ] Kasa temas bölgesindeki güçlü komponentlerde B.Mask açıklığı tanımlandı mı (`termal_yonetim_ve_mask_kontrolu()` temiz mi)?
- [ ] B.Mask açıklığı olan bölgeler için yüzey kaplaması BOM/fabrikasyon notunda ENIG olarak zorunlu kılındı mı (HASL değil)?
- [ ] Termal ped kalınlığı `termal_ped_kalinligi_hesapla()` ile hesaplanıp BOM'a yazıldı mı?
- [ ] Ortak kalın bakır katmanı üzerinden ısıl ayrışmayan ısı-kaynağı/hassas-parça çiftleri için termal bariyer gerekliliği kontrol edildi mi; gerekiyorsa yeterli web genişliğiyle mi önerildi, yoksa NEEDS_HUMAN mi işaretlendi?

### Faz 5 — Güç Bütünlüğü ve Termal
- [ ] Ana yollar IPC-2221 + %20 pay ile boyutlandırılıp `TEST/Faz5_Voltaj_Dusumu.csv`'ye kaydedildi mi?
- [ ] Yüksek akımda tek via değil, akım paylaştırıcı via'lar mı kullanıldı (0.3mm≈1A kuralı)?
- [ ] Kapasitör GND/VCC pedleri Double Via ile mi indi?
- [ ] LDO altına termal via kondu mu, yüksek akım pedleri Solid (Thermal Relief değil) mi bağlandı?

### Faz 6 — Sinyal Bütünlüğü ve EMI/EMC
- [ ] Diferansiyel hatlar hedef empedansa (örn. 100Ω) göre mi çizildi?
- [ ] Yüksek hızlı katman altında kesintisiz GND düzlemi var mı — `check_reference_plane_continuity()` ile ölçülerek (nokta-poligon testiyle) kanıtlandı mı, sadece gözle mi bakıldı?
- [ ] Katman geçişlerinde ~12mm yakınına dönüş GND via'sı kondu mu?
- [ ] 3W (paralel hat boşluğu) ve 5W (clock izolasyonu) kuralına uyuldu mu?
- [ ] Dış dünya girişlerine TVS/EMI şok bobini, MIPI hatlarına düşük kapasitanslı ESD dizisi kondu mu?
- [ ] Ortak mod gürültüsü/ground loop için filtreleme ve tek-nokta topraklama uygulandı mı?
- [ ] FFC/FPC kabloları empedans kontrollü ve kısa mı?
- [ ] Giyilebilir/Kompakt form faktörde PCB meander anten yerine seramik çip anten + Pi-matching kullanıldı mı; anten üreticisinin keep-out kılavuzu uygulandı mı?

### Faz 7 — Stackup ve Routing
- [ ] 4 katman (L1 sinyal / L2 GND / L3 güç / L4 düşük hız) standardına uyuldu mu?
- [ ] Routing sırası (GND → kritik sinyal → güç → dijital I/O) izlendi mi?
- [ ] Dönüşler 45° veya arc mi (90° yok mu)?
- [ ] Teardrop eklendi, dead copper temizlendi, GND via stitching yapıldı, asit tuzakları düzeltildi mi?

### Faz 8 — DFM/DFT ve Çıktılar
- [ ] Her rayda ve GND'de Test Point var mı (MIPI/Clock hatlarında YOK mu)? `tp_kapsam_kontrolu()` güç+debug %100 mü döndü?
- [ ] `generate_bringup_checklist()` rail enable sırasına göre mi üretildi (sıra hatası core'a hasar verebilir)?
- [ ] 3 asimetrik köşede fiducial mark var mı; panel varsa `panelizasyon_kontrolu()` (≥3 global fiducial, BGA local fiducial, ≥5mm rail, ≥5mm de-panel mesafesi) temiz mi?
- [ ] Serigrafi pad/via üzerine taşmıyor mu?
- [ ] Pin-arası kanaldan geçen izlerde maske barajı hesaplandı mı (`maske_baraji_kontrolu()`, fab min tipik 0.20-0.25mm) — sadece "solder mask köprüsü riski yok" diye gözle mi geçildi?
- [ ] Fab-rotasyon-map versiyonlandı mı (hash ile); `check_orientation()` kutuplu parça yönünü CPL açısıyla çapraz doğruladı mı?
- [ ] DRC ve ERC sıfır hata mı?
- [ ] Gerber, Drill, tam BOM, CPL/POS (centroid = courtyard merkezi, footprint origin değil) dışa aktarıldı mı?
