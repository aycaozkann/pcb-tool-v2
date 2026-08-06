# 03 — Design Rules (DRC Parametreleri)

Durum: `TASLAK`

> Kaynak: `pcb_stackup_planner.py::FABRIKA_PROFILLERI` (JLCPCB Standart/
> Gelişmiş, PCBWay Standart) + `kicad_koprusu.py::custom_dru_yaz()` +
> `ipc2152_hesaplayici.py` / `ipc2221_clearance_hesaplayici.py` /
> `ipc6012_dfm_motoru.py` / `ipc_dru_koprusu.py` (bölüm 4-4d — IPC
> standartlarından `.kicad_dru`'ya uçtan uca zincir).
> Bu dosya HANGİ profilin bu proje için SEÇİLDİĞİNİ ve fab'ın gerçek
> kabul limitleriyle karşılaştırmasını kaydeder.

## 1. Seçilen Üretici Profili

| Alan | Değer |
|---|---|
| Seçilen fab | *(JLCPCB / PCBWay / Würth / ...)* |
| Profil anahtarı (`FABRIKA_PROFILLERI` içinde) | *(ör. "JLCPCB_STANDART")* |
| Seçim gerekçesi | *(maliyet / min iz-aralık ihtiyacı / hızlı teslimat)* |

## 2. DRC Parametreleri (fab profilinden — uydurma değil, fab web sitesinden TARİHLİ doğrulanmalı)

| Parametre | Bu projede kullanılan | Fab minimumu | Kaynak/tarih |
|---|---|---|---|
| Min iz genişliği (mm) | | | |
| Min iz aralığı (mm) | | | |
| Min delik çapı (mm) | | | |
| Min annular ring (mm) | | | |
| Maks aspect ratio | | | |
| Min solder mask barajı (mm) | | | `pcb_highspeed_escape.py::FAB_MIN_MASKE_BARAJI_MM` ile aynı sayı olmalı |

> **Uyarı:** `fabrika_dfm_kontrolu()` çağrısı bu tabloya göre yapılandırılmalı,
> tabloyla senkron değilse fonksiyon yanlış eşiklerle çalışır — güncelleme
> ikisinde birden yapılmalı.

## 3. `.kicad_dru` Kural Enjeksiyonu

> [!danger] DÜZELTME (bu makinede gerçek `kicad-cli` ile AMPİRİK olarak doğrulandı)
> Bu maddenin önceki hali TERSİNİ söylüyordu ("genel kurallar başta,
> spesifik SONDA, sonra gelen kural kazanır") — bu YANLIŞTIR. Gerçek KiCad
> 10 davranışı: **İLK EŞLEŞEN KURAL KAZANIR.** İstisna/spesifik kurallar
> GENEL kurallardan ÖNCE yazılmalı, aksi halde istisna hiç uygulanmaz ve
> DRC genel kuralla "temiz" der (istisna sessizce yok sayılır). Ayrıca
> `(version 1)` başlığı ZORUNLU (yoksa TÜM dosya yok sayılır) ve yorum
> karakteri `#`'dir, `;` DEĞİL (`;` parse'ı sessizce çökertir). Bu üç kural
> artık `ipc_dru_koprusu.py`'de YAPISAL OLARAK zorlanıyor — bkz. bölüm 4d.

- [ ] `custom_dru_yaz()` / `ipc_dru_koprusu.py::kural_dosyasi_olustur()` ile
  üretilen kurallar `routing'den ÖNCE` yazıldı.
- [ ] Kural sırası doğru: **istisna/spesifik kurallar BAŞTA, genel kurallar
  SONDA** (ilk eşleşen kural kazanır — bkz. yukarıdaki düzeltme notu).
- [ ] Enjekte edilen her kural fault-injection ile kanıtlandı (kuralı ihlal
  eden bilinçli bir geometri koy, DRC KIRILMALI — kırılmıyorsa kural boştur).
- [ ] `(version 1)` başlığı dosyanın İLK satırı, hiçbir yerde `;` yorum
  karakteri olarak KULLANILMADI.

## 4. IPC-2221 / IPC-2152 — İletken Genişliği / Akım Taşıma

Bu proje varsayılan olarak **IPC-2221** ile boyutlandırır
(`pcb_stackup_planner.py::iz_genisligi_hesapla_mm()` — muhafazakâr, hızlı,
kapalı-form). Bir iz IPC-2221'e göre sığmıyorsa veya iç katman/yüksek
akımlı kritik bir ray söz konusuysa, tasarımı bloke etmeden önce
**`ipc2152_hesaplayici.py::ipc2152_min_iz_genisligi_mm()`** ile yeniden
değerlendir — bu modül aynı IPC-2221 çekirdek formülünü kullanır (tek
kaynak gerçeklik, sessiz sapma yok) ama iç katmanlar için AYRICA
belgelenen bir derating katsayısı (`varsayılan 1.25`, `ic_katman_derating_katsayisi`
parametresiyle override edilebilir) uygular.

> [!warning] Dürüstlük notu
> `ipc2152_hesaplayici.py` IPC-2152'nin resmi eğri ailesini
> SAYISALLAŞTIRMAZ (bu ortamda erişim yoktu) — kritik/güvenlik ilişkili
> raylarda üretim imzasından ÖNCE Saturn PCB Toolkit veya satın alınmış
> IPC-2152 standardıyla çapraz doğrulanmalı. Modülün kendi docstring'i
> tam gerekçeyi içerir.

| Rail | Worst-case akım (A) | Katman | IPC-2221 (mm) | IPC-2152 (mm, iç-katman derating dahil) | Kullanılan standart | CONFIRM gerekli mi |
|---|---|---|---|---|---|---|
| | | | | | | |

## 4b. IPC-2221B Table 6-1 — Clearance / Creepage (Elektriksel İzolasyon)

`ipc2221_clearance_hesaplayici.py::clearance_hesapla_mm()` — voltaj farkı +
katman tipi (iç/dış) + kaplama durumuna (kaplamasız/conformal coating) göre
minimum clearance + creepage hesaplar; `pcb_stackup_planner.py`'nin mevcut
dış/kaplamasız tablosunu TEK KAYNAK olarak miras alır (sessiz sapma yok —
öz-testler bunu doğrular).

> [!warning] Dürüstlük notu — kritik
> Bu modülün tablosu resmi, satın alınmış IPC-2221B PDF'inden DEĞİL,
> ikincil kaynaklardan derlendi. Her değer kendi güven seviyesini taşır
> (`Guven.MEVCUT_KOD_ILE_TUTARLI` / `IKINCIL_KAYNAK_TAHMINI` /
> `MUHAFAZAKAR_VARSAYIM`). **Güvenlik-kritik veya >50V içeren HER
> tasarımda**, üretim imzasından ÖNCE değerler resmi standarttan TEK TEK
> doğrulanmalı ve bir uyumluluk uzmanına onaylatılmalıdır — bu modül
> compliance KANITI DEĞİLDİR, sadece ilk tarama aracıdır.

| Net çifti | Maks. gerilim farkı (V) | Katman | Kaplama | Clearance (mm) | Creepage (mm) | Güven seviyesi | Resmi standartla doğrulandı mı |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

- [ ] **High-Voltage (HV) Net Class:** Yüksek voltajlı ağlar için özel bir
  `HV_NetClass` oluşturulmuş ve bu sınıfın Clearance (boşluk) değeri
  otomatik IPC hesaplamasına (min 2.0mm - 2.5mm) göre ayarlanmış mıdır?

## 4c. IPC-6012 — Class 2 / Class 3 Üretilebilirlik Sınıfı

`ipc6012_dfm_motoru.py::Ipc6012DfmMotoru` — annular ring, solder mask
barajı, aspect ratio limitlerini seçilen sınıfa (Class 2/3) göre denetler,
`bulgu_sozlesmesi.Bulgu` ile PASS/FAIL/**KAPSAM_YOK** raporlar (ölçüm
verilmeyen bir kontrol asla sessizce PASS sayılmaz).

| Alan | Değer |
|---|---|
| Seçilen IPC-6012 sınıfı | *(Class 2 / Class 3)* |
| Seçim gerekçesi | *(tüketici elektroniği → Class 2; havacılık/tıbbi/askeri → Class 3)* |
| Min annular ring (mm) | *(`SINIF_LIMITLERI[sinif].min_annular_ring_mm`)* |
| Min solder mask barajı (mm) | *(= `pcb_highspeed_escape.FAB_MIN_MASKE_BARAJI_MM`, IPC-6012'nin kendi sayısı DEĞİL)* |
| Maks aspect ratio | *(`SINIF_LIMITLERI[sinif].maks_aspect_ratio`)* |
| `Ipc6012DfmMotoru.genel_sonuc()` çıktısı | *(PASS / FAIL / NEEDS_HUMAN)* |

> [!warning] Dürüstlük notu
> Limitler TEMSİLİDİR (ikincil kaynak) — solder mask barajı IPC-6012'nin
> KENDİSİNİN hard bir sayı verdiği bir alan değildir, bu proje kendi kabul
> ettiği fab minimumunu (0.20mm) miras alır. Seçilen fabrikanın GÜNCEL
> "IPC Class 2/3 certified" beyanından çapraz doğrulanmalı.

## 4d. `.kicad_dru` Entegrasyonu — `ipc_dru_koprusu.py`

Yukarıdaki üç modülün (4/4b/4c) sonuçları `ipc_dru_koprusu.py::kural_dosyasi_olustur()`
ile GERÇEK bir `.kicad_dru` dosyasına yazılır. Bu köprü, bu projede daha
önce (ESP32-C3 Smart Band revizyonunda) AMPİRİK OLARAK keşfedilen ÜÇ
sessiz KiCad 10 tuzağını YAPISAL OLARAK imkânsız kılar:

1. **`(version 1)` başlığı ZORUNLU** — yoksa dosyanın TAMAMI sessizce yok sayılır.
2. **`(priority N)` GEÇERSİZ bir token** — kural sırası dosya SIRASIYLA
   belirlenir (ilk eşleşen kazanır); istisnalar genel kurallardan ÖNCE yazılır.
3. **Yorum karakteri `#`'dir, `;` DEĞİL** — `;` parse'ı sessizce çökertir.

Bu üç kural + `track_width`/`clearance`/`annular_width` constraint'lerinin
GERÇEKTEN uygulandığı (parse değil, gerçek DRC ihlali ürettiği), bu
makinede `ESP32C3_SmartBand.kicad_pcb`'ye karşı **doğrulandı** (temel 3
ihlalden clearance probuyla 503'e, annular_width probuyla 187 ihlale
çıktı — bkz. `ipc_dru_koprusu.py` modül başlığı).

- [ ] `.kicad_dru` bu üç modülden `kural_dosyasi_olustur()` ile üretildi
      (kafadan yazılmadı).
- [ ] İstisna kuralları (`istisna_kurali_uret()`) genel kurallardan ÖNCE
      geldi (`KuralOnceligi.ISTISNA`).
- [ ] Üretilen dosyada `(version 1)` başlığı ve `#` yorumları var, `priority`/`;` YOK.

## 5. IPC-7351 — Pad/Footprint Boyutlandırma

`ipc7351_footprint.py` ile hesaplanan (veya datasheet'ten alınan) land
pattern'ler:

| Footprint | Yoğunluk seviyesi (A/B/C) | Pad uzunluk × genişlik (mm) | Kaynak (hesaplandı mı / datasheet mi) |
|---|---|---|---|
| | | | |

> Not: `ipc7351_footprint.py` yalnızca 2-terminalli çip paketleri (R/C/L)
> kapsar; QFN/BGA/gullwing gibi çok-pinli paketlerde datasheet land
> pattern'i esastır (`TBD` — bu modülde henüz yok).

## 6. Onay

- [ ] Fab profili ve DRC parametreleri fab'ın GÜNCEL web sitesinden
  tarihli doğrulandı (tablo eski/statik değil).
- [ ] Durum `ONAYLANDI` — rev/tarih.
