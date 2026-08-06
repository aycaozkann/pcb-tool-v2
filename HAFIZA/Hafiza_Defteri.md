---
tags: [pcb, hafiza-defteri, mühendislik-dersleri]
type: pcb-hafiza-defteri
---

# Hafıza Defteri

> [!info] Bu dosya ile [[Hata_Hafizasi]] arasındaki fark
> [[Hata_Hafizasi]] (`hata_hafizasi.py` tarafından yönetilir) **yapılandırılmış**
> bir veritabanıdır: her kayıt bir DRC/ERC mesaj **imzasına** bağlıdır, otomatik
> aranır, otomatik öğretilir. Bu dosya ise **serbest metin**, insan/Claude
> tarafından elle küratörlüğü yapılan bir günlüktür — "şu board'da şu kararı
> aldık, sebebi buydu" tarzı, tek bir hata mesajına indirgenemeyen daha geniş
> mühendislik dersleri için (topoloji seçimi, form faktör ödünleri, tedarik
> kararları). İkisi birbirinin YERİNE geçmez.

## Nasıl kullanılır

**Yeni bir tasarıma başlamadan önce** (CLAUDE.md Faz -1'in bir parçası):
bu dosyayı baştan sona oku. Burada kayıtlı bir ders, şu anki tasarımın
şartlarıyla (form faktör, güç kaynağı tipi, hedef fabrika) örtüşüyorsa
`MASTER_RULEBOOK.md`/`DOCS/01_Design_Requirements.md`'ye karar olarak
taşınmalı — bu dosya kural KİTABI değil, kural kitabının NEREDEN geldiğinin
kaydıdır.

**Bir tasarım oturumu bittiğinde** (`design-checker` PASS/CONDITIONAL PASS
verdiğinde, veya kullanıcı "bunu hafızaya not et" dediğinde): o oturumda
alınan, GELECEKTEKİ bir tasarımı da etkileyebilecek her karar/hata için
aşağıdaki şablonla yeni bir madde eklenir. **Her koşulda not edilmez** —
sıradan/tek seferlik bir düzeltme (ör. bir yazım hatası) buraya girmez;
eşik: "bu dersi bilmeseydim aynı hatayı BAŞKA bir projede de yapardım mı?"

## Kayıt şablonu

```markdown
### <YYYY-MM-DD> — <proje adı> — <kısa başlık>
- **Bağlam:** <form faktör, güç kaynağı, hedef fabrika vb.>
- **Ne oldu:** <sorun/karar>
- **Neden önemli:** <bir sonraki projede tekrar etmemesi gereken şey>
- **Kaynak:** <MASTER_RULEBOOK maddesi / commit / TEST raporu bağlantısı>
```

---

## Kayıtlar

### 2026-07-xx — ESP32-C3 Smart Band — Datasheet arşivi ihmal edildi, sonradan düzeltildi
- **Bağlam:** Faz 2.5'te bir yük anahtarı (TPS22910A) sonradan karara bağlandı.
- **Ne oldu:** Datasheet WebFetch ile okunup şematikte kullanıldı ama
  `DATASHEETS/` klasörüne KAYDEDİLMEDİ — sadece konuşma geçmişinde kaldı.
  Sonradan fark edilip düzeltildi.
- **Neden önemli:** "Sonradan eklenen" bir parça (Faz 2 ortasında karara
  bağlanan bir yük anahtarı/koruma IC'si gibi), ilk BOM'daki bir parça
  kadar dikkat çekmiyor ve disiplin gözden kaçabiliyor. Bu yüzden
  MASTER_RULEBOOK Bölüm 0'a "ilk BOM'da olsun veya sonradan eklensin,
  İSTİSNASIZ" ibaresi eklendi.
- **Kaynak:** [[../MASTER_RULEBOOK#BÖLÜM 0|MASTER_RULEBOOK Bölüm 0]], madde 2.

### 2026-07-xx — ESP32-C3 Smart Band — Buck-boost yerine Low-IQ LDO + slide switch
- **Bağlam:** Giyilebilir (wearable) form faktör, Li-Ion/LiPo pil beslemesi.
- **Ne oldu:** Başlangıçta önerilen buck-boost, kullanıcı tarafından
  gürültü/boyut kaygısıyla reddedildi. Low-IQ ULDO (ME6211/RT9013 sınıfı)
  + fiziksel sürgülü anahtar (derin deşarj/sızıntı akımını sıfırlamak için)
  lehine değiştirildi. Bilinçli ödün: pil aralığının (3.0-4.2V) en son
  dilimi (LDO dropout altı, ~3.0-3.4V bandı) kullanılamaz hale geldi —
  kullanıcı onayıyla kabul edildi.
- **Neden önemli:** "Daha verimli/daha geniş aralıklı" topoloji HER ZAMAN
  doğru cevap değildir — küçük giyilebilir bir kartta anahtarlama bobininin
  yer kaplaması ve EMI/akustik gürültüsü, buck-boost'un teorik avantajını
  gölgede bırakabilir. Form faktör "Giyilebilir/Kompakt" ise bu artık
  MASTER_RULEBOOK'ta İSTİSNA olarak kural haline getirildi — bir sonraki
  giyilebilir projede aynı tartışma sıfırdan yapılmayacak.
- **Kaynak:** [[../MASTER_RULEBOOK#BÖLÜM 0|MASTER_RULEBOOK Bölüm 0]], madde 3.

### 2026-07-xx — ESP32-C3 Smart Band — İki ayrı lifecycle sürprizi (EOL + Obsolete)
- **Bağlam:** Aynı proje, BOM seçimi sırasında.
- **Ne oldu:** Önce `ESP32-C3FN4`'ün EOL olduğu, ardından `MPU-6050`'nin
  Obsolete olduğu tespit edildi. MPU-6050 durumunda kullanıcıya "yine de
  devam edilsin mi (hâlâ LCSC/AliExpress'te bulunuyor)" seçeneği sunuldu —
  kullanıcı bunu REDDEDİP `ICM-42688-P`'ye geçmeyi tercih etti.
- **Neden önemli:** "Hâlâ bulunabiliyor" ile "üretim durumu Active" AYRI
  şeylerdir — bulunabilirlik geçicidir, bir kere daha stoklar tükenince
  yeniden tasarım gerekir. Bu somut vaka, MASTER_RULEBOOK'un BOM kuralını
  "prototip/hobi amaçlı olsa bile İSTİSNASIZ" diye sertleştirmesinin
  doğrudan gerekçesidir — bir sonraki projede "sadece prototip, olur"
  diye gevşetilmeye ÇALIŞILMAMALI.
- **Kaynak:** [[../MASTER_RULEBOOK#BÖLÜM 0|MASTER_RULEBOOK Bölüm 0]], madde 4.

### 2026-07-xx — ESP32-C3 Smart Band — Nominal değerle hesaplanan marj yanıltıcıydı
- **Bağlam:** Kademeli güç rayı (Buck→LDO1→LDO2) worst-case dropout marjı.
- **Ne oldu:** İlk hesapta LDO2 dropout marjı, LDO1'in çıkışını NOMİNAL
  kabul ederek %69 çıkmıştı. LDO1'in kendi ±40mV toleransı worst-case giriş
  gerilimine yansıtılınca gerçek marj %57.7'ye düştü — hâlâ PASS ama ilk
  sayı yanıltıcıydı (marj göründüğünden ~%11 daha dardı).
- **Neden önemli:** Kademeli raylarda "üst kademe her zaman tam nominal
  verir" varsayımı, marjı SİSTEMATİK OLARAK ŞİŞİRİR — kademe sayısı arttıkça
  hata büyür. Bu proje artık worst-case zincirleme toleransı Faz 2'de
  ZORUNLU kılıyor; bir sonraki çok-kademeli tasarımda bu hesap nominal
  değerle YAPILMAMALI.
- **Kaynak:** [[../MASTER_RULEBOOK#FAZ 2|MASTER_RULEBOOK Faz 2]], "Tolerans
  Zinciri ve Worst-Case Analizi" maddesi.

### 2026-07-30 — pcb-tool-v2 — ERC/DRC JSON şeması varsayımı yanlıştı, sessiz sahte-PASS üretiyordu
- **Bağlam:** `kicad_koprusu.py`'nin `erc_calistir`/`erc_temiz_mi` fonksiyonları,
  dış bir kod incelemesinde "şeması doğrulanmadı" olarak işaretlenmişti.
- **Ne oldu:** Gerçek `kicad-cli sch erc --format json` (KiCad 10.0.4) bu
  makinede gerçek bir şematiğe (ESP32C3_SmartBand) karşı koşturulunca, ERC
  raporunun ihlalleri üst seviye `violations` altında DEĞİL,
  `sheets[].violations` altında tuttuğu görüldü. Eski kod her zaman boş
  liste bulup SESSİZCE PASS diyordu — 7 gerçek uyarı varken. Aynı koşum,
  DRC tarafında da `unconnected_items` alanının (6 tane `error` seviyeli
  eksik bağlantı) hiç okunmadığını ortaya çıkardı — raporun kendisi bile
  bunu fark etmemişti.
- **Neden önemli:** "Doğrulanmadı" diye bırakılan bir varsayım, gerçek
  veriyle test edilene kadar KESİN OLARAK YANLIŞ ya da EKSİK olabilir —
  ve yanlış olduğunda sonuç kör bir hata değil, SESSİZ SAHTE PASS'tır
  (en tehlikeli tür). Bir dış inceleme "bu doğrulanmamış" dediğinde, cevap
  "zaten böyle olduğunu biliyorduk" değil, gerçek araçla BİR KEZ koşturup
  kanıtlamaktır.
- **Kaynak:** `kicad_koprusu.py::erc_calistir`/`_drc_tum_ihlaller` docstring'leri,
  `test_kicad_koprusu.py`'deki `GERCEK_KICAD10_ERC_YAPISI` testleri.

### 2026-07-30 — pcb-tool-v2 — DOCS/03_Design_Rules.md'deki kural sırası açıklaması TAM TERSİYDİ
- **Bağlam:** `.kicad_dru` Custom Rules kural önceliği hakkındaki mevcut
  checklist maddesi.
- **Ne oldu:** `DOCS/03_Design_Rules.md` "genel kurallar başta, spesifik
  kurallar SONDA (KiCad'de sonra gelen kural kazanır)" diyordu. Bu proje
  daha önce (ESP32-C3 Smart Band revizyonunda) GERÇEK `kicad-cli` ile
  ampirik olarak TAM TERSİNİ keşfetmişti: KiCad'de **İLK EŞLEŞEN KURAL
  KAZANIR** — istisnalar genel kurallardan ÖNCE yazılmalı. O keşif
  `.kicad_dru` dosyasının kendi başlık yorumuna not düşülmüştü ama
  `DOCS/03_Design_Rules.md`'ye hiç YANSITILMAMIŞTI — iki dosya birbirinden
  SESSİZCE SAPMIŞTI. `ipc_dru_koprusu.py` yazılırken bu eski `.kicad_dru`
  dosyası okunup gerçek davranış doğrulanınca fark edildi ve düzeltildi.
- **Neden önemli:** Bir gerçek-dünya keşfi (ampirik olarak doğrulanmış bir
  araç davranışı) SADECE üretilen bir dosyanın (`.kicad_dru`) yorumuna
  yazılırsa, o dosya silinip yeniden üretildiğinde (`kural_dosyasi_olustur()`
  her seferinde BAŞTAN üretir) bilgi KAYBOLUR. Kalıcı, insan tarafından
  yazılan dokümanlar (`DOCS/`, `HAFIZA/`) ile OTOMATİK ÜRETİLEN dosyalar
  (`.kicad_dru`, `Changelog.md`) arasındaki ayrım net tutulmalı: gerçek
  bir keşif HER İKİSİNE de (üretilen dosyanın yorumuna VE kalıcı belgeye)
  yazılmalı, sadece birine değil.
- **Kaynak:** `DOCS/03_Design_Rules.md` bölüm 3, `ipc_dru_koprusu.py`
  modül başlığı.

### 2026-07-30 — pcb-tool-v2 — Kendi yazdığım öz-test, kendi tasarım hatamı iki kez yakaladı
- **Bağlam:** `ipc2221_clearance_hesaplayici.py` yazılırken.
- **Ne oldu:** İki ayrı gerçek hata, modülün KENDİ `oz_testleri_calistir()`
  fonksiyonu tarafından yazılırken hemen yakalandı: (1) "kaplama HER ZAMAN
  mesafeyi azaltır" varsayımı düşük voltajda (15V) yanlış çıktı — kaplı
  tabanı (0.13mm) kaplamasızın zaten çok dar elektriksel minimumundan
  (0.05mm) büyük olabiliyordu; (2) interpolasyon fonksiyonu iki farklı
  güven seviyeli nokta arasında `min()`/rank karışıklığı yüzünden YANLIŞ
  (daha yüksek/daha iyimser) güven seviyesini miras alıyordu.
- **Neden önemli:** Bu proje genelinde tekrarlanan bir desen: bir modülün
  kendi öz-testini/fault-injection'ını YAZMAK, sadece "kod çalışıyor mu"
  değil "varsayımlarım TUTARLI mı" sorusunu da sınar. İki hata da modül
  BİTTİKTEN sonra ayrı bir inceleme turunda değil, YAZILIRKEN, ilk
  `--oztest` çalıştırmasında ortaya çıktı — bu, "önce testi yaz, hemen
  çalıştır" disiplininin (TDD) bu projede neden ısrarla sürdürüldüğünün
  somut kanıtıdır.
- **Kaynak:** `ipc2221_clearance_hesaplayici.py` — `_KAPLI_TABAN_MM` notu,
  `_dogrusal_interpolasyon()`'daki `_guven_siralamasi` düzeltmesi.

### 2026-07-30 — pcb-tool-v2 — "UYARI" ön-ekiyle mesaj filtrelemek fail-closed kapıyı sessizce fail-open yapmıştı
- **Bağlam:** `uretim_ciktilari_cli.py::dogrulama_kapisini_calistir()`, üretim
  öncesi son doğrulama kapısı.
- **Ne oldu:** `pcbnew` kurulu değilken gerçek-board kontrolleri (maske
  barajı/via-in-pad/annular-ring) hiç çalışmıyordu; kod bunu yakalayıp
  `sorunlar` listesine `"UYARI: ..."` diye ekliyordu, sonra nihai
  `temiz_mi` hesabı "UYARI" ile başlayan mesajları FİLTRELEYEREK
  hesaplanıyordu. Sonuç: gerçek-board kontrolleri HİÇ ÇALIŞMASA BİLE
  kapı sessizce PASS dönüyordu. Aynı desenin ikinci kurbanı: bu CLI,
  `kicad_koprusu.py`'de zaten var olan `sema_taninmadi_mi()` fail-closed
  kapısını hiç ÇAĞIRMIYORDU — bilinmeyen bir DRC/ERC şeması da sessizce
  PASS sayılıyordu.
- **Neden önemli:** "Bir mesajı sadece metin öneki (`UYARI:`) ile
  kategorize edip nihai karara dahil etme/etmeme" deseni KIRILGANDIR —
  yeni bir kod yolu o öneki unutursa (veya doğru önekle eklerse ama
  aslında BLOKE ETMESİ gerekiyorsa) karar sessizce yanlış tarafa düşer.
  Artık başarı/başarısızlık AYRI bir boolean değişkenle (`basarili`)
  açıkça takip ediliyor, string içeriğinden TÜRETİLMİYOR. Bu proje
  gelecekte benzer bir "kapı" yazarken bu deseni (string-prefix filtreleme)
  KULLANMAMALI.
- **Kaynak:** `uretim_ciktilari_cli.py::dogrulama_kapisini_calistir`
  docstring'i, `test_uretim_ciktilari_cli.py`'deki regresyon testleri.

### 2026-07-30 — pcb-tool-v2 — Bash `&&` zinciri Windows PowerShell'de sessizce işe yaramıyordu
- **Bağlam:** `KURULUM.md`'nin "Hızlı toplu doğrulama" bölümü, tüm dış
  araçları `kicad-cli --version && python3 -c "..." && ... && git --version`
  şeklinde tek bir bash zinciriyle kontrol ediyordu.
- **Ne oldu:** Bu proje Windows'ta (PowerShell) geliştiriliyor ve
  PowerShell 5.1 `&&` operatörünü DESTEKLEMİYOR — komut olduğu gibi
  kopyalanıp çalıştırılınca parser hatası veriyordu. Ayrıca bash zincirinin
  kendisi de bir tasarım kusuru taşıyordu: İLK başarısız komutta durur,
  kalan araçlar hiç denenmez — kullanıcı "hangi araçların eksik olduğunu"
  değil sadece "en erken eksik olanı" görür. Çözüm: kontrolü bash'e/
  PowerShell'e değil, `arac_yollari.py::tum_araclari_kontrol_et()` + `ortam_on_kontrol.py --tam`
  ile TEK bir Python betiğine taşımak — hem kabuktan bağımsız hem de her
  aracı BAĞIMSIZ deneyip tam tabloyu tek seferde veriyor.
- **Neden önemli:** Bir kurulum/doğrulama komutu YAZARKEN hedef platformun
  kabuğu (bash mi, PowerShell mi, hangi sürüm) baştan düşünülmeli — "bende
  çalışıyor" bash sözdizimi başka bir işletim sisteminde sessizce
  kullanılamaz hale gelebilir. Kabuk-bağımlı zincirleme (`&&`, `|`, `head`)
  gerektiren her kontrol/otomasyon adımı için, mümkünse bu projenin
  yaptığı gibi kabuktan bağımsız (Python) bir sarmalayıcı tercih edilmeli.
- **Kaynak:** `KURULUM.md` "Hızlı toplu doğrulama" bölümü,
  `arac_yollari.py::tum_araclari_kontrol_et`, `test_arac_yollari.py`.

### 2026-07-30 — pcb-tool-v2 — FreeRouting zinciri kicad-cli 10'da hiç çalışmıyordu
- **Bağlam:** `uretim_zinciri_koprusu.py::freerouting_zinciri_calistir()` DSN
  export + FreeRouting + SES import zincirini "kullanılabilir" gibi
  belgeliyordu, `.ses` import'u için sadece "tespit et" notu vardı.
- **Ne oldu:** Gerçek `kicad-cli pcb export --help` çıktısı (KiCad 10.0.4)
  kontrol edilince alt komut listesinde `dsn`in HİÇ olmadığı görüldü —
  yani zincirin İLK adımı bile KiCad 10'da mevcut değil. `pcb import --help`
  de Specctra Session'ı desteklemediğini doğruladı.
- **Neden önemli:** Bir entegrasyonun "yer tutucu/doğrulanmadı" olarak
  işaretlenmesi ile "bu araç bunu ARTIK/HİÇ sunmuyor" AYRI durumlardır —
  ilki "sonra doldur" der, ikincisi "bu yolu TERK ET, alternatif ara" der.
  Bir sonraki KiCad sürüm yükseltmesinde bu iki kontrol (dsn/ses) yeniden
  çalıştırılıp güncellenmeli; sessizce "hâlâ yok" varsayılmamalı.
- **Kaynak:** `uretim_zinciri_koprusu.py::dsn_disa_aktar`/`ses_iceri_aktar`
  docstring'leri, `test_uretim_zinciri_freerouting.py`.

### 2026-07-30 — ESP32-C3 Smart Band — MCP ile canlı routing: 3 ayrı sınıf hata, GERÇEK kartta yakalandı
- **Bağlam:** Yarım kalan kartta 6 eksik bağlantıyı (`unconnected_items`)
  `mcp__kicad__route_trace`/`route_pad_to_pad` ile tamamlama denemesi.
  Kart 4 katmanlı (F.Cu/B.Cu dış, In1.Cu+In4.Cu GND düzlemi, In3.Cu +3V3
  düzlemi) ve yoğun (0.5mm pitch LGA-14 IMU, 0.5mm pitch pin sırası).
- **Ne oldu (3 AYRI hata sınıfı, üçü de kartı GERÇEKTEN bozmadan yakalandı):**
  1. **MCP'nin `route_trace`/`route_pad_to_pad`'i engelden KAÇMIYOR** — iki
     nokta arası düz çizgi çekiyor. İlk denemede 6 bağlantının 4'ü komşu
     pinlerin/pad'lerin ÜZERİNDEN geçip gerçek kısa devre yarattı (44 yeni
     DRC hatası, 13'ü `shorting_items`). `save_project` ÇAĞRILMADAN önce
     gerçek `kicad-cli` DRC ile bağımsız doğrulandığı için yakalandı;
     `close_project(save=false)` + `git checkout` ile dosya hiç
     bozulmadan geri alındı.
  2. **`delete_trace`'in `position` (en yakın izi sil) modu YOĞUN bölgede
     GÜVENİLMEZ** — silinmek istenen YENİ iz ile önceden var olan BAŞKA
     bir iz aynı noktaya yakınsa, "en yakın" olan YANLIŞ (önceden var
     olan, meşru) izi silebiliyor. `git diff` ile fark edilip geri
     alındı. **Ders:** yoğun bölgede SİLERKEN önce `query_traces` ile
     UUID bulunmalı, `traceUuid` ile silinmeli — `position` modu sadece
     seyrek/izole alanlarda güvenli.
  3. **`query_traces` VİALARI LİSTELEMİYOR** (sadece iz segmentlerini) —
     bu yüzden board'da önceden var olan via'lar (bu kartta U1'in pin
     sütunu çevresinde 9 tane yoğun via kümesi) MCP üzerinden GÖRÜNMEZ,
     sadece bir rota onlara çarpınca DRC hatası olarak ortaya çıkar. Ham
     `.kicad_pcb` dosyasını `(via ...)` için regex ile taramak (bkz.
     yukarıdaki örnek script) TEK güvenilir yöntemdi.
- **Neden önemli:** Bu üç ders `topolojik_router_koprusu.py::akilli_yol_bul()`
  gibi otomatik pathfinding araçlarının GİRDİSİNİN eksik/yanlış olursa
  (özellikle #3 — via'lar görünmüyor) çıktının da GÜVENİLMEZ olacağını
  kanıtlıyor — "algoritma doğru" ile "algoritmaya doğru engel listesi
  verildi" AYRI şeylerdir. Bir sonraki yoğun/çok katmanlı kartta:
  (a) routing'e başlamadan önce ham `.kicad_pcb`'den TÜM via'ları regex
  ile çıkar, (b) her DRC-temiz iddiasını `save_project`'ten ÖNCE gerçek
  `kicad-cli` ile doğrula, (c) yoğun bölgede silme işlemini UUID ile yap.
  Nihai çözüm (GND via-via bağlantısı) `akilli_yol_bul()`'e TAM via listesi
  verildiğinde ilk denemede temiz çıktı — araç doğruydu, eksik olan girdiydi.
- **Kaynak:** commit `69acd64` (GND bağlantısı, temiz), bu oturumun
  `TEST/drc_adim*.json`/`TEST/drc_gnd_final*.json` raporları,
  `topolojik_router_koprusu.py::akilli_yol_bul`.

### 2026-07-30 — ESP32-C3 Smart Band — `mcp__kicad__refill_zones`: belgelenen "segfault riski" bu makinede GERÇEKLEŞMEDİ, ama aracın kendi "kaydedildi mi" raporu YANLIŞ çıktı
- **Bağlam:** Kartın 4 katmanlı olduğu (In1/In4 GND, In3 +3V3 düzlemi)
  keşfedildikten sonra, yeni eklenen her via'nın düzlemlere GERÇEKTEN
  bağlanabilmesi için zone refill gerekiyordu (bkz. yukarıdaki "3 ayrı
  hata sınıfı" kaydı). Aracın kendi açıklaması "SWIG path has known
  segfault risk" diyordu; kullanıcı riski BİLE BİLE denemeyi onayladı —
  amaç aracın GERÇEKTEN çökebilirliğini/çökmediğini bu makinede
  kaydetmekti.
- **Ne oldu:** `refill_zones()` ÇÖKMEDİ, 3 zone'u başarıyla yeniden
  doldurdu. AMA yanıtı `"success": true` ile birlikte
  `"autoSave": {"saved": false, "warning": "Auto-save refused: the
  on-disk PCB file's contents changed externally..."}` döndürdü — yani
  "hesapladım ama diske YAZAMADIM" diyordu. Bağımsız `git diff` ile
  kontrol edilince dosyanın GERÇEKTEN değiştiği (161 satırlık zone
  poligon farkı) ve `kicad-cli` DRC'nin GERÇEKTEN iyileştiği (1 via_dangling
  uyarısı + 1 eksik bağlantı daha çözülmüş) görüldü — yani **yazma
  aslında BAŞARILIYDI, ama aracın kendi "saved: false" raporu YANLIŞTI**.
  Hemen ardından çağrılan `save_project()` de AYNI "dışarıdan değişti"
  gerekçesiyle reddetti (oysa o "dışarıdan değişikliği" YAPAN da kendisiydi
  — kendi önceki yazmasını "dışarıdan" sanıyor, mtime/hash defterini
  güncellemiyor). `open_project()` ile projeyi yeniden açmak (bir nevi
  "durumu MCP'nin kendi diskle senkronize etmesi") sorunu çözdü.
- **Neden önemli:** Bu, projenin "MCP sonucuna körü körüne güvenme, kritik
  şeyi bağımsız doğrula" ilkesinin (`CLAUDE.md`, `kicad_koprusu.py` Ek-A)
  BİREBİR somut kanıtı — burada MCP "başarısız" dedi ama aslında
  BAŞARILIYDI (tersi de olabilirdi: "başarılı" deyip aslında yazmamış
  olabilirdi, önceki `sync_schematic_to_board` hatası gibi). **Kural:**
  `refill_zones`/`save_project` çağrısından SONRA her zaman `git diff`
  veya `kicad-cli` DRC ile bağımsız doğrula — aracın `success`/`saved`
  alanlarına GÜVENME. Ayrıca: bu MCP sunucusunun "diskte harici değişiklik"
  koruması (`diskChangedExternally`) kendi önceki başarılı yazmasını bile
  "harici" sayabiliyor — takıldığında `open_project()` ile yeniden
  yüklemek (state resync) güvenli bir kurtarma adımı.
- **Kaynak:** Bu oturum, commit `950c5d9`, `TEST/drc_refill_check.json` /
  `TEST/drc_refill_verify2.json`.

### 2026-07-30 — ESP32-C3 Smart Band — U2 (LGA-14, 0.5mm pitch) elle/MCP ile via yerleştirmek için PRATİKTE çok zor; GUI'ye bırakılmalı
- **Bağlam:** U2'nün (ICM-42688-P) 3 ayrı +3V3 pinini (5, 8, 12) düzleme
  bağlamak için her biri civarında yeni via yeri arandı.
- **Ne oldu:** 4 farklı deneme, her seferinde ÖNCEDEN BİLİNMEYEN bir engel
  çıkardı: (1) F.Cu'da I2C_SCL/I2C_SDA yatay iz (y=1.3869 ve y=-2.2551),
  (2) In2.Cu'da AYRICA bir I2C_SCL dikey izi (x=8.9814) — yani kart en az
  6 bakır katmanlı (F/In1/In2/In3/In4/B), sadece 4 değil, (3) U2'nün
  "net'i olmayan" (NC) pinleri (2,3,10,11) da GERÇEK bakır kaplıyor ve
  clearance kuralına tabi — sadece isimli net'li pin'lere bakmak YETMEZ,
  (4) pin5'in kendi komşuları (pin2/3/6) arasındaki kullanılabilir koridor
  sadece ~0.5-0.7mm — 0.6mm çaplı standart bir via (varsayılan boyut,
  MCP'de KÜÇÜLTME seçeneği yok) bu koridora sığmıyor, sadece İNCE bir iz
  (0.25mm) sığabiliyor.
- **Neden önemli:** Bu IC'nin etrafı o kadar yoğun ki, koordinat-bazlı
  "önce hesapla sonra dene" yöntemi (bu oturumda GND bağlantısı için işe
  yaradı) burada 4 denemede de EN AZ bir öngörülmemiş engelle karşılaştı —
  her biri güvenle geri alındı (`git checkout`), karta kalıcı zarar
  gelmedi, ama net bir çözüme ulaşılamadı. **Ders:** LGA/QFN gibi ≤0.5mm
  pitch'li parçaların İÇ pinlerini bağlamak (özellikle çok katmanlı bir
  kartta) otomatik/kör routing için UYGUN DEĞİL — bu sınıf bağlantılar
  için ya (a) KiCad GUI'sinde görsel yerleşim (ratsnest'i görerek), ya da
  (b) parçanın kendi footprint'ine ÖZEL, küçük çaplı (ör. 0.3mm) via
  tanımlı bir "via-in-pad" stratejisi baştan tasarıma dahil edilmeli —
  sonradan eklemeye çalışmak (bu oturumda olduğu gibi) çok zaman alıyor
  ve düşük başarı oranı veriyor.
- **Kaynak:** Bu oturum, `TEST/drc_u2_pins*.json` (4 deneme raporu),
  commit `950c5d9`'un ötesine geçilemedi (pin5/pin12 hâlâ eksik bağlantı
  listesinde).

### 2026-07-30 — pcb-tool-v2 — Ajana GERÇEK "görme" yeteneği kazandırıldı: `pcb_gorsel_kesit.py`
- **Bağlam:** Yukarıdaki U2 kaydında "koordinatla kör routing" 4 kez
  başarısız olunca kullanıcı sordu: "sana görme yetisi nasıl
  kazandırabiliriz?" Cevap bu oturumda bulundu ve kalıcı bir araca
  (`pcb_gorsel_kesit.py`) dönüştürüldü.
- **Ne oldu:** Denenen/elenen yollar — `mcp__kicad__get_board_2d_view`
  (inline): büyük görüntüde MCP mesaj sınırını aşıyor. Aynı araç (file
  modu, PNG): bu makinede PNG dönüştürücü (pymupdf/inkscape/imagemagick)
  YOK, sessizce SVG'ye düşüyor. SVG'yi `Read` ile "okumak": `Read` SVG'yi
  XML METNİ olarak açar, RENDER ETMEZ — görsel değil, zaten elimizdeki
  koordinat listesi sorununun ta kendisi. **Çözüm:** `kicad-cli pcb
  export svg --page-size-mode 2 --fit-page-to-board` (SVG (0,0) = board
  Edge.Cuts bbox min köşesi, 1 birim=1mm, KiCad'in kendi garantisi) →
  `svglib`+`reportlab` (SVG→PDF, saf Python, native bağımlılık yok) →
  bu makinede ZATEN kurulu `poppler`/`pdftocairo` (PDF→yüksek çözünürlüklü
  PNG) → `Pillow` (bilinen mm→piksel oranıyla kırpma+büyütme) →
  `Read` ile GERÇEKTEN görüldü. İlk board denemesinde (ESP32C3_SmartBand,
  yuvarlak kenarlı) Edge.Cuts sınır ayrıştırıcının naif regex'i
  `gr_circle` içindeki iç içe `(stroke (width..) (type..))` bloğunda
  YANLIŞ kapanışta durup "Edge.Cuts'ta nokta yok" hatası verdi — derinlik
  sayan bir parantez ayrıştırıcıyla (`sch_wire.py::_block()` ile AYNI
  desen, ama bağımsız kopya) düzeltildi ve regresyonu kilitleyen bir
  fault-injection testi eklendi.
- **Neden önemli:** Bu artık pcb-tool-v2'nin GENEL bir yeteneği —
  gelecekteki HER projede, yoğun pinli parçalar (LGA/QFN/BGA) etrafında
  via/iz yerleştirmeden ÖNCE `bolge_goruntule()` ile o bölgeyi GÖREREK
  planlama yapılabilir; kör koordinat tahminine artık gerek yok. Sadece
  bir "güzel-olsun" özelliği değil — bu oturumda 4 başarısız denemeye mal
  olan sınıf bir sorunu kökten çözüyor.
- **DÜRÜSTLÜK SINIRI:** SVG↔board koordinat eşlemesinde ~0.06mm'lik bir
  yay-örnekleme farkı ölçüldü (`mcp__kicad__get_board_extents()` ile
  karşılaştırıldı) — bu SADECE görsel yönlendirme için kabul edilebilir,
  ölçüm/DRC/üretim kararı için BU ARACA GÜVENİLMEMELİ.
- **Kaynak:** `pcb_gorsel_kesit.py`, `test_pcb_gorsel_kesit.py`,
  `arac_yollari.py::pdftocairo_yolunu_bul`, `KURULUM.md` madde 11,
  `CLAUDE.md` "🆕 5. TUR".

### 2026-07-31 — ESP32-C3 Smart Band — U2 pin5/pin12 clearance hataları çözüldü: MCP tamamen çökünce elle S-expr düzenleme MEŞRU bir kurtarma yolu, çapraz ize dik mesafe SEZGİYLE değil DENKLEMLE hesaplanmalı
- **Bağlam:** Önceki oturumdan kalan 3 `clearance` hatası (U2 pin5/pin12'nin
  +3V3 stub'ları, bkz. yukarıdaki "U2 ... GUI'ye bırakılmalı" kaydı).
- **Ne oldu (İKİ ayrı ders):**
  1. **MCP çöktü, `open_project` bile kurtaramadı:** `route_trace` 30 saniye
     timeout verdi; sonrasında TÜM MCP çağrıları (`query_traces`,
     `get_backend_state`, `open_project`) "Python process for KiCAD
     scripting is not running" hatası verdi — önceki oturumlardaki
     "dehydrated" veya "diskChangedExternally" durumlarından FARKLI, bu
     kez backend'in kendisi öldü ve `open_project` onu YENİDEN
     BAŞLATAMADI. Yarım kalan işi (2 segment silinmiş, yenisi eklenmemiş)
     `.kicad_pcb` dosyasını doğrudan `Edit` aracıyla düzenleyerek
     (komşu `(segment ...)` bloğunun BİÇİMİNİ birebir kopyalayıp yeni
     `uuid4()` atayarak) tamamladık, her adımda bağımsız `kicad_koprusu.
     drc_calistir()` ile doğruladık. **Ders:** MCP backend'i tamamen
     ölürse (sadece "dehydrated" değil, süreç kaybı), bu bir ÇIKMAZ
     DEĞİL — S-expr formatını bilmek (bkz. `sch_wire.py`'nin şematik
     tarafındaki AYNI felsefe) PCB tarafında da geçerli bir kurtarma
     yoludur, MCP'nin yeniden başlatılmasını beklemeye gerek yok.
  2. **45° çapraz bir ize olan mesafe, kenar-hizalı sezgiyle YANILTICI
     hesaplanır:** pin12'nin yolu hem pin11 (no-net) pad köşesine hem de
     I2C_SCL'nin 45° çapraz bir izine aynı anda yakındı. İlk 3 deneme
     (basit L-dönüşleri) hep TEK bir kısıtı çözüp DİĞERİNİ ihlal etti —
     "pin11'den uzaklaş" dediğimde I2C çapraz izine yaklaşıyordum, ve
     tam tersi. Çözüm: çapraz izin doğru denklemini çıkarıp (bu izin iki
     ucu için `x+y=sabit` bulunuyor, çünkü yön vektörü (-1,1)) dik mesafe
     formülünü (`|x+y-sabit|/√2 ≥ gereken_boşluk + iz_yarı_genişlik +
     hedef_iz_yarı_genişlik`) KULLANMAK — bu, hem pin11 hem I2C_SCL
     kısıtını AYNI ANDA sağlayan dar bir (x,y) koridorunu (~0.03mm
     marjla) matematiksel olarak buldu, deneme-yanılma değil.
- **Neden önemli:** Bu iki ders BİRLİKTE genellenebilir: (a) MCP'nin
  "backend öldü" sınıfı hatası bu projenin önceki "dehydrated"/"diskChanged
  Externally" kayıtlarından AYRI bir hata sınıfıdır ve AYNI kurtarma
  yolunu (elle S-expr düzenleme + bağımsız kicad-cli doğrulama) kullanır;
  (b) 0.5mm pitch bir IC'nin İÇ pinleri gibi çok kısıtlı köşelerde, İKİ
  veya daha fazla engel varsa (pad + çapraz iz gibi FARKLI GEOMETRİLİ
  engeller), sezgisel/görsel yaklaşım yetersiz kalabilir — çapraz izin
  doğrusal denklemini çıkarıp dik mesafe formülüyle çözüm bölgesini
  analitik olarak daraltmak, bir sonraki yoğun köşede de (LGA/QFN/BGA)
  uygulanmalı, sadece `bolge_goruntule()` ile "bakıp tahmin etmek" değil.
- **Kaynak:** commit `8763fb0`, `TEST/KALDIGIMIZ_YER.md` (2026-07-31
  bölümü), `TEST/drc_u2_pins_clearance_fixed.json`,
  `TEST/pin5_after.png`/`pin12_after.png`.

### 2026-08-03 — cm4-io-test — KiCad DSN export diferansiyel çift bilgisini TAŞIMIYOR; FreeRouting J1 için hiç uygun değil
- **Bağlam:** J1'in 8 net'lik Gigabit Ethernet diferansiyel çifti (ETH_TRD0-3)
  kendi yazılan A* mimarisiyle 3 denemede de "pair twist" problemine takılınca,
  pcb-tool-v2'nin zaten doğrulanmış (GÖREV 10) gerçek FreeRouting zinciri
  (`dsn_disa_aktar`/`freerouting_calistir`/`ses_iceri_aktar`) alternatif olarak
  denendi.
- **Ne oldu:** `pcbnew.ExportSpecctraDSN()` ile üretilen gerçek `.dsn` dosyası
  incelenince, board'daki TÜM netlerin (ETH_TRD dahil, HDMI/DSI/CAM
  diferansiyel çiftleri de dahil) TEK bir düz `(class kicad_default ...)`
  bloğunda listelendiği, hiçbir P/N eşleştirme/coupling bilgisinin DSN'e
  yazılmadığı görüldü (`grep -c "(class "` → 1). Bu, FreeRouting'in kendisi
  mükemmel yakınsasa BİLE J1'i bağımsız tek-uçlu netler gibi routeleyeceği,
  eşit-uzunluk/paralel-eşleşme garantisi VERMEYECEĞİ anlamına geliyor.
- **Neden önemli:** Bu, "algoritma yetersiz" ile "araç zinciri temelden veri
  kaybediyor" arasındaki AYRIMIN somut kanıtı — daha iyi bir router/daha
  yüksek arama sınırı bu sorunu ÇÖZMEZ, çünkü sorun hesaplama değil, DSN
  formatının kendisinin diferansiyel çift kavramını hiç TAŞIMAMASI. Bir
  sonraki projede herhangi bir diferansiyel çift (USB/PCIe/MIPI/Ethernet)
  FreeRouting'e gönderilmeden ÖNCE bu sınır hatırlanmalı — diferansiyel
  çiftler ya `pcbnew` API'siyle doğrudan (ve `LOCKED` işaretlenerek) elle/
  yarı-otonom çözülmeli, ya da FreeRouting'e vermeden önce net listesinden
  ÇIKARILIP ayrı ele alınmalı.
- **Kaynak:** `MASTER_RULEBOOK.md` FAZ 7 "FreeRouting/DSN Diferansiyel Çift
  Sınırı", `DOCS/10_Otonomluk_Engel_Raporu.md` D1.1/D1.5,
  `karar_birimleri.json: j1-pair-twist-cozumu` (cm4-io-test).

### 2026-08-03 — cm4-io-test — `freerouting_calistir()`'in zaman-aşımı kontrolü, uzun sessiz stdout aralığında GECİKTİ
- **Bağlam:** Aynı FreeRouting denemesinde, 259 düşük hızlı net için tam
  board DSN'i (103KB) export edilip `freerouting_calistir(zaman_asimi_sn=240)`
  çağrıldı.
- **Ne oldu:** Gerçek boyutlu bu kartta (267 unrouted net + zaten routed
  PCIe/HDMI/USB) FreeRouting 240sn içinde yakınsamadı — ama daha önemlisi,
  fonksiyonun kendi zaman-aşımı kontrolü de zamanında TETİKLENMEDİ. Kontrol,
  `proc.stdout.readline()`'ın (BLOCKING) her dönüşünde çalışıyor; FreeRouting
  uzun bir süre stdout'a hiç satır yazmayınca kontrol hiç çalışma fırsatı
  bulamadı, süreç ~285sn+ sonra elle (`Stop-Process`) sonlandırılmak zorunda
  kaldı.
- **Neden önemli:** "Zaman aşımı X saniye" diye belgelenen bir kontrolün
  GERÇEKTEN o sürede tetiklendiğini varsaymak yanlış olabilir — kontrol
  mekanizması BLOCKING bir I/O çağrısıyla aynı döngüdeyse, o I/O uzun süre
  veri üretmediğinde kontrol de gecikir. Bir sonraki subprocess-tabanlı
  zaman-aşımı tasarımında (özellikle uzun süre sessiz kalabilen harici
  araçlarla) kontrol döngüsü ayrı bir thread/timer'da ya da non-blocking
  bir okuma modeliyle kurulmalı, `readline()` gibi blocking bir çağrıya
  GÖMÜLMEMELİ.
- **Kaynak:** `uretim_zinciri_koprusu.py::freerouting_calistir()`,
  `karar_birimleri.json: bulk-lowspeed-router-cozumu` (cm4-io-test), bu
  oturumun `TEST/freerouting_scratch/` denemesi.
