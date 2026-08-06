# 11 — Full Otonom Dönüşüm Talimatı (Claude Code İçin)

> Tarih: 2026-07-31
> Amaç: `pcb-tool-v2`'yi "istekten üretime-hazır pakete" giden **tam donanımlı, full otonom PCB ajanı**na dönüştürmek için yapılması gerekenlerin uygulanabilir talimat listesi.
> Ön koşul: `DOCS/10_Otonomluk_Engel_Raporu.md`'deki sınıflandırmayı (D1/D2/D3) oku.
> Kullanım: Her maddeyi birer birer Claude Code'a görev olarak ver. Bir madde **kabul kriteri**ni sağlamadan bir sonrakine geçme.

---

## Genel kural (hepsinin üstünde)

> Full otonomluk = **hiçbir durma noktası sessizce geçilmez; ama hiçbiri için insan beklemez.** Her durma noktası ya (a) otomatik çözülür, ya (b) **belgeli otonom karar** olarak `TEST/`'e kayıtlı bir gerekçeyle geçilir. `NEEDS_HUMAN` yalnızca "iki bağımsız otonom strateji de başarısız oldu" kanıtıyla, o da sadece `TEST/needs_human_*.json` dosyasına yazarak döner — akışı kullanıcıya sorarak durdurmaz.

---

## GÖREV 1 — pcbnew altyapısını KiCad 10 Python'una bağla (D1.4)

Bu, diğer birçok maddenin ön koşuludur: DFM/EMC, gerçek-board doğrulama, yerleşim radarı ve KAPSAM_YOK kaynakları pcbnew'siz çalışamaz.

- **Yapılacaklar:**
  1. `arac_yollari.py`'ye KiCad'in bundled Python'unu bulan fonksiyon ekle (Windows: `C:\Program Files\KiCad\10.0\bin\python.exe`; Linux: `kicad-cli` yanındaki python). `.kicad_pro`'dan sürüm oku.
  2. `dfm_emc_check.py:30` ve `via_stub.py:51`'deki modül-seviyesi `import pcbnew`'i kaldır; `kicad_koprusu.py`'deki desen gibi **lazy/opsiyonel import** yap. Import başarısızsa modül "pcbnew yok" modunda çalışsın (soyut dataclass testleri çalışmaya devam etsin), gerçek board kontrolleri için net hata mesajı: "KiCad Python'uyla çalıştır: `& \"C:\Program Files\KiCad\10.0\bin\python.exe\" <script>`".
  3. `pcbnew_koprusu.py` içindeki 8 `import pcbnew` noktasını tek bir module-level yardımcıya (`pcbnew_oturumu()` context manager) topla; her çağrı `board.Save()` sonrası `.bak` kuralına uysun.
  4. Test: KiCad Python'uyla `python -c "import pcbnew, kipy"` → başarılı. `dfm_emc_check.py` venv'de "pcbnew yok" modunda temiz import olsun.

- **Kabul kriteri:** `test_*` tümü venv'de yeşil; `dfm_emc_check.py` gerçek ESP32-C3 board'unda KiCad Python'uyla koşup bulgu üretiyor.

## GÖREV 2 — routing_plan.md onayını "otomatik onay + audit log" modeline çevir (D3.1/5, D3.2)

- **Yapılacaklar:**
  1. `main.py` ve `.claude/skills/pcb-layout/SKILL.md` Aşama 3.7'yi değiştir: `TEST/routing_plan.md` + `TEST/routing_plan.json` üretilir, **onay beklenmez**. Bunun yerine `TEST/kararlar_logu.md`'ye "topoloji kararı OTOMATİK alındı" satırı + her net için gerekçe yazılır.
  2. Topoloji değişikliği raporlama kuralını koru: her katman/via/topoloji sapması `routing_plan.json`'a satır olarak eklenir (sessiz sapma yasağı değişmez, sadece insan-onayı yerine log).
  3. `CLAUDE.md` "Ne zaman dur" maddesi 5'i şu hale getir: "routing_plan üretilir ve `TEST/kararlar_logu.md`'ye kaydedilir; akış durmaz."
- **Kabul kriteri:** ESP32-C3'te routing fazı kullanıcı sorusu sormadan başlıyor; `kararlar_logu.md` tüm net kararlarını içeriyor.

## GÖREV 3 — 3-kez-tekrar kuralını "belgeli otonom karar"a çevir (D2.4, D2.6, CLAUDE.md:682-688)

- **Yapılacaklar:**
  1. `hata_hafizasi.py`'ye `Sonuc.OTONOM_KARAR` enum değeri ekle (NEEDS_HUMAN'ın yerine geçen kayıt türü) — "denendi, başarısız, gerekçe kaydedildi, akış alternatifle devam etti".
  2. `otonom_kurtarma_motoru.py:285`'i değiştir: üç katman da tükendiğinde `needs_human=True` döndürmek yerine, `MerdivenSonucu`'na `otesi_strateji` alanı ekle ve **üst katmanda** şunu dene: (a) itip-kaydırma (`topolojik_router_koprusu.py` push-and-shove) → (b) mikro-yerleşim (aynı netin komşu pads arası) → (c) via+katman değişimi → (d) fanout/şematik revizyonu önerisi. Bunlar da olmazsa `OTONOM_KARAR` kaydı + `TEST/needs_human_<net>.json` yaz ve net'i "bilinçli açık" işaretle, akışı sonraki net'e geçir.
  3. Feedback döngüsü sayacı (BOM→stackup, escape→routing, DFM→stackup) 3'e ulaştığında da aynı: döngüyü `OTONOM_KARAR` gerekçesiyle durdur, rapora işle, en kötü kabul edilebilir konfigürasyona ilerle.
- **Kabul kriteri:** IMU_INT1/DISPLAY_RESET gibi zor netler artık kullanıcıya soru sormadan "OTONOM_KARAR + bilinçli açık" kaydıyla geçiyor; `TEST/`'te gerekçe dosyası var.

## GÖREV 4 — FreeRouting'i ya canlandır ya resmen kapat (D1.1)

- **Yapılacaklar:**
  1. Önce 30 dakika araştırma: güncel FreeRouting (Java) `.kicad_pcb`'yi doğrudan okuyabiliyor mu? (FreeRouting 2.x/3.x release notları.) Okuyorsa `uretim_zinciri_koprusu.py::freerouting_calistir()`'ı `.kicad_pcb` girdisiyle çalışacak şekilde güncelle, `FreeRoutingDesteklenmiyorHatasi` kaldır.
  2. Okuyamıyorsa KESİN KARAR: `router=freerouting` seçeneğini `.claude/skills/pcb-layout/SKILL.md:177`'den sil; `main.py`'de `--router` parametresi sadece `python` (otonom router) kabul etsin. `uretim_zinciri_koprusu.py` FreeRouting fonksiyonlarını "deprecated, KULLANMA" notuyla dondur (silme — referans testleri var).
  3. Her iki durumda: `otonom_kurtarma_motoru.py` + `otonom_python_router.py` tek routing motoru olarak ilan edilir; CLI `--router` argümanı kaldırılırsa docs'taki referansları güncelle.
- **Kabul kriteri:** `test_uretim_zinciri_freerouting.py` ya gerçek FreeRouting çalıştırmasıyla ya da "devre dışı" durumuyla yeşil; hiçbir doküman kullanılamaz `freerouting` seçeneği önermiyor.

## GÖREV 5 — Parça tedarik verisini otonomlaştır (D1.3)

- **Yapılacaklar:**
  1. Offline parça veritabanı şeması ekle: `parts_db/parts.csv` — `mpn, lifecycle, stok_0, lead_time_hafta, single_source, pinout_ozeti, elektriksel_param` kolonları. `bom_lifecycle_koprusu.py::nexar_sorgula()`'yı şöyle değiştir: `api_key=None` iken önce `parts_db/parts.csv`'de ara; bulunursa `kaynak="offline_db"` döndür; bulunmazsa `kaynak="TBD"` (CONFIRM raporu) — ama artık TBD parçalar için `parts_db/pending.md`'ye "arama görevi" satırı yaz.
  2. `cad_api_koprusu.py::varlik_sorgula()` için de aynı offline yol: footprint/pinout `parts_db`'den doğrulanır, yoksa CONFIRM.
  3. Nexar gerçek entegrasyonu opsiyonel kalsın; API key gelirse online sorgu offline sonucu ezer.
- **Kabul kriteri:** BOM akışı ESP32-C3'te hiçbir parça için insan beklemeden risk skoru üretiyor; `pending.md` TBD'leri listeliyor.

## GÖREV 6 — KAPSAM_YOK → otomatik ölçüm kaynağı (D2.2)

- **Yapılacaklar:**
  1. `ipc6012_dfm_motoru.py`, `ipc_a_610_dfa_motoru.py`, `emi_emc_kural_motoru.py`'nin KAPSAM_YOK döndüğü her kontrolü listele (test'lerdeki örneklerden).
  2. Her KAPSAM_YOK kaynağı için otomatik ölçüm zincirini bağla: DRC/ERC verisi → `kicad_koprusu.py::gercek_board_dogrulama_kapisi` (GÖREV 1'den sonra çalışır); ölçüm verisi yoksa bile artık `NEEDS_HUMAN` değil, `OTONOM_KARAR` + "ölçüm aracı çalışmadı, kontrol atlandı, raporda FAIL-olarak-işaretlendi" dönsün.
  3. `uretim_ciktilari_cli.py:121,132,148` — gerçek-board kontrolü artık varsayılan olarak ÇALIŞSIN (GÖREV 1 çözüldüyse); `--gercek-board-kontrolu-atla` bayrağının "NEEDS_HUMAN işaretle" davranışını "OTONOM_KARAR + raporda UYARI" olarak değiştir.
- **Kabul kriteri:** Üç motorun genel_sonuc'u hiçbir girdi kombinasyonunda "insan bekle" mesajı üretmiyor; tümü `OTONOM_KARAR` sözleşmesine uyuyor. Test'ler güncelleniyor.

## GÖREV 7 — main.py'yi tam orkestratör yap (D3.3 + eksik otomasyon)

- **Yapılacaklar:**
  1. `main.py run`'ı tek komutla tüm zinciri yönetir hale getir: `ön-kontrol → şematik (sch_wire) → ERC → stackup/empedans → BOM/parça (GÖREV 5) → yerleşim (kuvvet_yonelimli_yerlesim) → routing (otonom router) → DRC → gerçek-board DFM/EMC (GÖREV 1) → üretim çıktısı (GÖREV 8)`. Fazlar arası `uretim_zinciri_koprusu.py` BÖLÜM 5 kontrat kapılarını (drc.json, parts.json) zorunlu kılsın.
  2. Her faz bitiminde `MASTER_RULEBOOK.md` FAZ -0.5 otonom git commit kuralını uygula (kullanıcı sormadan; GÖREV 0'daki kilit kuralı + `sleep 3` + retry ile).
  3. `--produce` bayrağını gerçek üretim paketi üretecek şekilde tamamla (GÖREV 8).
- **Kabul kriteri:** `python main.py run --project-dir <ESP32C3>` tek komutla istekten üretim paketine kadar kullanıcıya sormadan ilerliyor; her faz `TEST/`'e doğrulanabilir rapor bırakıyor.

## GÖREV 8 — Üretim paketi ve KiBot (üretim zinciri)

- **Yapılacaklar:**
  1. KiBot'u kur (`pip install kibot` veya KiCad eklentisi); `KURULUM.md`'ye ekle.
  2. `uretim_ciktilari_cli.py`'yi çalışır hale getir: `kibot_config_yaz()` gerçek bir `.kibot.yaml` üretsin (gerber+drill+bom+cpl, JLCPCB iki-panel). KiBot yoksa net hata mesajı, sessiz geçiş yok.
  3. `main.py --produce` → KiBot ile `uretim/` klasörüne gerber.zip + bom.csv + cpl.csv + gerber görseli üretsin; öncesinde GÖREV 6'nın DRC/DFM kapısını zorunlu kılsın.
- **Kabul kriteri:** `--produce` ESP32-C3 için gerçek gerber/bom/cpl üretiyor; `uretim/` klasörü oluşuyor; üretim paketi `git`'e işleniyor.

## GÖREV 9 — Kanıt disiplinini aiplanlama modeline taşı (uzun vadeli kalite)

- **Yapılacaklar:**
  1. Her doğrulama çalıştırması `TEST/<kontrol>_<tarih>.json` + `TEST/evidence/` altında **yeniden çalıştırılabilir** kayıt üretsin (usb-hs-breakout'taki `evidence/00_RAPOR.md` deseni). Raporlarda "ölçüldü / hesaplandı / TBD" etiketi zorunlu.
  2. `uretim_ciktilari_cli.py` ve `main.py` tüm sayıları o çalıştırmada ölçsün (önceki çalıştırmanın sonucunu kopyalama — ProjectE CLAUDE.md "measure yourself" kuralı).
  3. Her board için `verify.md` benzeri tek sayfalık sonuç özeti üret (PASS/FAIL tablolu).
- **Kabul kriteri:** `TEST/evidence/` geriye dönük her iddianın nasıl ölçüldüğünü gösteriyor.

---

## GÖREV 10 — FreeRouting DSN/SES zincirini pcbnew üzerinden canlandır + hibrit zaman aşımı (GÖREV 4'ün operasyonelleştirilmesi, DOCS/12 bulgusu)

> **Durum: TAMAMLANDI (2026-07-31).** `uretim_zinciri_koprusu.py` BÖLÜM 1
> yeniden yazıldı. GERÇEKTEN bu makinede doğrulandı: `dsn_disa_aktar()`
> KiCad'in `ecc83-pp.kicad_pcb` demo board'unda gerçek DSN üretti;
> `freerouting_calistir()` GERÇEK bir FreeRouting 2.2.4 çalıştırmasında
> `java.lang.StackOverflowError`'ı (`PolylineTrace.combine` sonsuz
> özyinelemesi) 240sn'lik timeout'u BEKLEMEDEN, ~7 saniyede yakalayıp
> `java_hatasi_mi=True` ile döndü (Eylem 2/3 kullanıcı tarafından ek
> olarak istenen `-Xss8m`/`-Djava.awt.headless=true`/fail-fast satır
> taraması ile). `test_uretim_zinciri_freerouting.py` (20 test) ve tüm
> proje paketi (830 test) yeşil. **SENİN makinende hâlâ doğrulanmamış:**
> `freerouting_zaman_asiminda_otonom_devam_et()`'in gerçek bir proje
> board'unda (bu demo board'lar değil) uçtan uca çalışması — bu ortamda
> sadece mock'larla test edildi (pcbnew footprint/DRC extraction gerçek
> board'a karşı henüz koşulmadı).

> Bu görev GÖREV 4'ü TEKRARLAMAZ — onu SOMUTLAŞTIRIR. `DOCS/12_FreeRouting_Fizibilite.md`
> bu makinede DOĞRULADI: `kicad-cli`'nin DSN/SES desteklememesi doğru tespit
> edilmişti, ama kod tabanındaki "pcbnew de kurulu değil" varsayımı YANLIŞTI —
> `pcbnew.ExportSpecctraDSN`/`pcbnew.ImportSpecctraSES` KiCad 10.0.4'ün gömülü
> Python'unda ÇALIŞIYOR (sentetik + 2 gerçek KiCad demo board'unda kanıtlandı).
> Karar: GÖREV 4'ün "resmen kapat" seçeneği YERİNE "canlandır" seçeneği.

- **Bağlam:** `uretim_zinciri_koprusu.py::dsn_disa_aktar()` (satır 100) ve
  `ses_iceri_aktar()` (satır 167) şu an bilinçli olarak `FreeRoutingDesteklenmiyorHatasi`
  fırlatıyor; `KICAD10_DSN_DESTEKLENIYOR = False` (satır 89) bunu ikinci bir
  savunma katmanıyla tekrar engelliyor. DOCS/12 E1 bulgusu: FreeRouting 2.2.4
  gerçek boyutlu kartlarda (14-174 net) 120-240 saniyede bitmiyor (timeout).
  E2 bulgusu: `ImportSpecctraSES` gerçek routes'lu `.ses`'i sentetik board'a
  import ederken `False` döndü (padstack eşleşme duyarlılığı) — bu yüzden
  import'un HER ZAMAN `GetTracks()` sayısıyla doğrulanması gerekir, dönüş
  değerine körü körüne güvenilemez.

- **Eylem 1 — `pcbnew` tabanlı gerçek DSN/SES zinciri:**
  1. `arac_yollari.py`'ye yeni bir yardımcı ekle (gerekirse):
     `pcbnew_dsn_disa_aktar(board_path, dsn_path)` ve
     `pcbnew_ses_iceri_aktar(board_path, ses_path)` — ikisi de
     `pcbnew_scripti_calistir()` ÜZERİNDEN, geçici bir `.py` script dosyası
     yazıp KiCad'in gömülü Python'unda çalıştırarak
     `pcbnew.LoadBoard()` → `pcbnew.ExportSpecctraDSN(board, dsn_path)` /
     `pcbnew.ImportSpecctraSES(board, ses_path)` → (import ise)
     `board.Save(board_path)` yapsın. Proje venv'inin kendi Python'u
     ASLA `import pcbnew` DENEMEMELİ (`arac_yollari.py`'nin kendi
     docstring kuralı — bkz. `kicad_python_yolunu_bul`).
  2. `uretim_zinciri_koprusu.py::dsn_disa_aktar()` ve `ses_iceri_aktar()`'ı,
     hâlâ `FreeRoutingDesteklenmiyorHatasi` fırlatmak YERİNE bu yeni
     `arac_yollari` fonksiyonlarını çağıracak şekilde YENİDEN YAZ.
     `KICAD10_DSN_DESTEKLENIYOR` sabitini `True` yap VE adını/yorumunu
     güncelle (artık "kicad-cli DSN destekliyor mu" değil "pcbnew DSN/SES
     zinciri kullanılabilir mi" anlamına geldiğini belirt).
  3. `ses_iceri_aktar()` sonrasında MUTLAKA `pcbnew` script'i içinde
     `board.GetTracks()` sayısını (import öncesi/sonrası) karşılaştırıp
     sonuca `izler_degisti: bool` alanı ekle — DOCS/12 E2'nin "dönüş
     değerine güvenme" uyarısının kod karşılığı budur.
  4. `FreeRoutingDesteklenmiyorHatasi` sınıfını SİLME — `pcbnew`
     bulunamazsa (KiCad Python yolu çözülemezse) fonksiyonlar YİNE bu
     istisnayı fırlatmalı (fail-closed, sessiz geçiş yok).

- **Eylem 2 — 240 saniyelik timeout politikası:**
  1. `freerouting_calistir()`'in `zaman_asimi_sn` varsayılanını 1800'den
     **240**'a düşür (DOCS/12 E1: gerçek kartlarda 120-240sn'de bitmiyor —
     daha uzun beklemek otonom zinciri dakikalarca kilitler). Parametre
     olarak override edilebilir kalsın (küçük/basit kartlar için).
  2. `subprocess.TimeoutExpired` yakalandığında (zaten yapılıyor) sonuç
     nesnesine `zaman_asimi_mi: bool = True` alanı ekle ki çağıran taraf
     "gerçekten başarısız" ile "zaman aşımına uğradı" ayrımını yapabilsin.

- **Eylem 3 — Zaman aşımında çökmeyen fallback:**
  1. `freerouting_zinciri_calistir()`'i güncelle: `freerouting_calistir()`
     `zaman_asimi_mi=True` ile dönerse, zinciri `NEEDS_HUMAN`/hata ile
     KESMEK yerine `otonom_kurtarma_motoru.otonom_routing_merdiveni()`'ni
     (zaten var olan 3 katmanlı merdiven + push-and-shove) DEVAM
     STRATEJİSİ olarak çağır. Bu, GÖREV 3'ün "belgeli otonom karar" ilkesiyle
     tutarlıdır — FreeRouting başarısız/zaman aşımına uğrarsa akış DURMAZ,
     kendi router'ıyla devam eder ve `TEST/kararlar_logu.md`'ye "FreeRouting
     240sn'de bitmedi, otonom_kurtarma_motoru'na geçildi" satırı yazar.
  2. Bu fallback çağrısı da başarısız olursa (otonom merdiven de tükenirse),
     ANCAK O ZAMAN GÖREV 3'teki `OTONOM_KARAR` + `TEST/needs_human_<net>.json`
     kaydı yoluna düşülür — iki bağımsız router'ın İKİSİ DE başarısız olması
     gerekir, sessiz "başarılı" varsayımı YOK.

- **Kabul kriteri:** Gerçek bir `.kicad_pcb` üzerinde (a) `pcbnew` ile DSN
  export edilip FreeRouting ile route edildikten sonra SES import sonrası
  pad/net bağlantı sayısı (`GetTracks()`/netlist) import ÖNCESİYLE
  karşılaştırılıp KOPMADIĞI doğrulanıyor; (b) 240sn aşan bir çalıştırmada
  zincir çökmeden `otonom_kurtarma_motoru`'na düşüyor ve bu geçiş
  `TEST/kararlar_logu.md`'de görünüyor; (c) `test_uretim_zinciri_freerouting.py`
  güncellenip yeşil.

## GÖREV 11 — DRC raporlarını bölgesel kümeleme (clustering) ile özetle

> **Durum: TAMAMLANDI (2026-07-31).** Yeni modül `drc_ozetleyici.py`
> yazıldı: grid/centroid tabanlı `ihlalleri_kumele()`, opsiyonel pcbnew
> tabanlı `en_yakin_footprint_bul()`, `bulgu_sozlesmesi` entegrasyonlu
> `drc_kumeleri_bulgu_uret()`. `test_drc_ozetleyici.py` (19 test, fault-injection
> dahil — küçük hücre boyutuyla kümelerin gerçekten ayrıştığı kanıtlandı)
> yeşil. `kicad_koprusu.py::drc_raporunu_ozetle()` DEĞİŞMEDİ (geriye dönük
> uyumluluk korundu). **SENİN makinende doğrulanmamış:** `en_yakin_footprint_bul()`
> gerçek bir `.kicad_pcb` ile (bu ortamda sadece mock'lu pcbnew script
> çıktısıyla test edildi).

- **Bağlam:** `kicad_koprusu.py::drc_raporunu_ozetle()` (satır 169) şu an
  `_drc_tum_ihlaller()`'daki (violations + unconnected_items) her ihlali
  tekilleştirmeden, ham `[severity] description` satırı olarak döndürüyor.
  Gerçek KiCad DRC JSON şeması her ihlalin koordinatını üst seviyede DEĞİL,
  `ihlal["items"][i]["pos"] = {"x":.., "y":..}` altında (ihlale dahil HER
  pad/track için ayrı) taşır — bu proje şu an bu koordinatları hiç okumuyor,
  ihlalleri konumdan bağımsız düz bir liste olarak sunuyor. Yoğun bir bölgede
  (ör. bir IC'nin altındaki 12 kısa devre) bu, 12 ayrı satır olarak dökülüyor
  ve konum bağlamını (context) şişiriyor.

- **Eylem 1 — Grid/merkez tabanlı coğrafi kümeleme:**
  1. Yeni bir modül oluştur: `drc_ozetleyici.py` (bulgu_sozlesmesi.py'nin
     `Bulgu`/`bulgu_uret` sözleşmesini KULLANIR, onu DEĞİŞTİRMEZ).
  2. `ihlalden_temsili_konum(ihlal: Dict) -> tuple[float, float] | None` —
     `ihlal["items"]` listesindeki `pos` alanlarının merkez noktasını
     (centroid) hesaplar; `items`/`pos` yoksa `None` döner (KAPSAM_YOK'a
     düşecek, uydurma koordinat YOK).
  3. `ihlalleri_kumele(ihlaller, hucre_boyutu_mm=2.0) -> list[Kume]` — basit
     bir grid yaklaşımı: her ihlalin temsili konumunu `hucre_boyutu_mm`
     büyüklüğünde bir ızgara hücresine yuvarlayıp aynı hücredeki ihlalleri
     tek bir `Kume` nesnesinde toplar (`merkez: (x,y)`, `sayi: int`,
     `severity_dagilimi: dict`, `ornek_aciklamalar: list[str]`).
     Konumsuz ihlaller (adım 2'de `None` dönenler) ayrı bir "konumsuz"
     grubunda kalır, sessizce atılmaz.
  4. `en_yakin_footprint_bul(merkez, board_path) -> str | None` — OPSİYONEL
     zenginleştirme: `arac_yollari.pcbnew_scripti_calistir()` ile board'daki
     footprint referans-konum listesini çekip merkeze en yakın refdes'i
     döndürür; `pcbnew` yoksa veya `board_path` verilmezse `None` (fonksiyon
     çökmez, sadece footprint ismi rapora eklenmez).
  5. `kume_ozeti_uret(kume) -> str` — kabul kriterindeki formatı üretir:
     `"Özet: {refdes veya 'X,Y civarı'} etrafında {sayi} adet {severity}
     ihlali kümelendi. Öneri: {refdes} bölgesindeki yerleşimi genişletin."`
     (refdes yoksa konum aralığıyla ifade eder, "öneri" cümlesi hâlâ üretilir.)

- **Eylem 2 — `bulgu_sozlesmesi.py` üzerine entegrasyon:**
  1. `drc_ozetleyici.py::drc_kumeleri_bulgu_uret(rapor: Dict) -> Bulgu` —
     `bulgu_sozlesmesi.bulgu_uret()`'i çağırıp `taranan=len(_drc_tum_ihlaller(rapor))`,
     `ihlaller=[kume özet sözlükleri]` ile bir `Bulgu` döndürür — `taranan=0`
     iken otomatik `KAPSAM_YOK` (mevcut sözleşme kuralı korunur).
  2. `kicad_koprusu.py::drc_raporunu_ozetle()` DEĞİŞTİRİLMEZ (geriye dönük
     uyumluluk — `test_kicad_koprusu.py:75` bu fonksiyonun ham liste
     davranışına bağlı). Bunun yerine `drc_calistir()`'i çağıran akışlar
     (ör. `main.py` orkestratörü, `pcb-layout` Faz 5) artık ham
     `drc_raporunu_ozetle()` YERİNE `drc_ozetleyici.drc_kumeleri_bulgu_uret()`'i
     tercih etmeli — iki fonksiyon da kalır, biri "eski/ham", diğeri
     "yeni/kümelenmiş özet".

- **Eylem 3 — Testler:**
  1. `test_drc_ozetleyici.py` — sentetik bir DRC raporu (ör. bir IC'nin
     4 pad'i etrafında yakın koordinatlı 12 sahte "short" ihlali + 2 uzak
     tekil ihlal) ile: (a) 12'sinin TEK bir kümede toplandığını, (b) 2 uzak
     ihlalin AYRI kümelerde kaldığını, (c) konumsuz bir ihlalin "konumsuz"
     grubuna düştüğünü doğrula. Projenin kendi fault-injection disiplinine
     uy: önce doğru kümeleme (PASS), sonra `hucre_boyutu_mm` bilerek çok
     küçük yapılıp kümelerin AYRIŞTIĞININ (yani testin gerçekten bir şey
     ölçtüğünün) kanıtlanması.
  2. `en_yakin_footprint_bul()` gerçek `pcbnew` gerektirdiği için (D1.4
     deseniyle AYNI) bu ortamda mock'lanmış board ile test edilir; gerçek
     `.kicad_pcb` ile doğrulama SENİN makinende yapılmalı (`pcbnew_koprusu.py`
     ile AYNI "AĞ/ARAÇ UYARISI" disiplini).

- **Kabul kriteri:** Gerçek/sentetik bir DRC raporu ekrana basılırken ham
  liste yerine `"Özet: U1 etrafında 12 adet VCC/GND kısa devresi kümelendi.
  Öneri: U1 bölgesindeki yerleşimi genişletin."` formatında (ya da footprint
  bulunamazsa konum-bazlı eşdeğerinde) satırlar üretiyor; `test_drc_ozetleyici.py`
  fault-injection testi dahil yeşil; `kicad_koprusu.drc_raporunu_ozetle()`
  davranışı ve mevcut testi DEĞİŞMEDİ.

---

## Öncelik sırası ve bağımlılık özeti

| Sıra | Görev | Bağımlılık | Beklenen etki |
|---|---|---|---|
| 1 | GÖREV 1 (pcbnew) | yok | DFM/EMC + gerçek-board + KAPSAM_YOK kaynağı açılır |
| 2 | GÖREV 2 (routing onayı) | yok | İlk insan-onayı kalkar |
| 3 | GÖREV 3 (3-kez kuralı) | GÖREV 2 | İkinci büyük durma kalkar |
| 4 | GÖREV 4 (FreeRouting) | yok | Router seçimi netleşir |
| 5 | GÖREV 5 (parça DB) | yok | BOM insan-beklemesiz |
| 6 | GÖREV 6 (KAPSAM_YOK) | GÖREV 1 | Motorlar otonom karar verir |
| 7 | GÖREV 7 (main.py orkestratör) | 2,3,4,5,6 | Tek komut zinciri |
| 8 | GÖREV 8 (üretim paketi) | 6,7 | Üretime-hazır paket |
| 9 | GÖREV 9 (kanıt) | hepsi | Sürekli kalite |
| 10 | GÖREV 10 (FreeRouting pcbnew canlandırma) | GÖREV 4'ü somutlaştırır (DOCS/12) | Router seçimi netleşir, hibrit timeout+fallback ile akış kilitlenmez |
| 11 | GÖREV 11 (DRC kümeleme) | yok (GÖREV 6/7 ile birlikte kullanılabilir) | DRC raporu context şişirmeden okunur, bölgesel öneri üretir |

## Saklanması gerekenler (BİLİNÇLİ, kaldırma)
- Faz 0 belirsiz gereksinim → kullanıcıya sor **kalır** (sensör çözümlenmeden tasarım üretilmez). Bu, "otonom karar" kapsamı DIŞINDADIR.
- design-checker FAIL → bulgular raporda kaydedilir; ilgili faza otonom dönülür ama "sessizce geçildi" işareti asla konmaz.
- Datasheet bulunamazsa → parça `TBD` olarak işaretlenir ve `parts_db/pending.md`'ye yazılır; tasarım durur AMA istenirse kullanıcı onayıyla geçilebilir (açık belge).

---

_İlgili: `DOCS/10_Otonomluk_Engel_Raporu.md` (teşhis) · `MASTER_RULEBOOK.md` (kurallar) · `.claude/skills/*` (faz prosedürleri) · `TASARIM_AKISI.md` (akış)_
