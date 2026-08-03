# PCB Tasarım Otonom Ajanı — Proje Talimatları

## 🆕 YENİ MODÜLLER (arkadaşın Otonom-PCB-Ajani sistemiyle karşılaştırma sonrası eklendi)

Bu bölüm, projede eksikliği tespit edilip kapatılan 4 mimari boşluğu özetler.
Claude Code bu projeye ilk girdiğinde bu bölümü okumalı — aşağıdaki modüller
akışın (adım 2-5) İÇİNE entegre edilmeyi bekliyor, henüz `main.py`/akışın
kendisi bunları otomatik çağırmıyor.

1. **`bulgu_sozlesmesi.py`** — Tüm kontrol fonksiyonları için ortak
   `Bulgu(kontrol, durum, taranan, ihlaller, detay)` sözleşmesi.
   `taranan == 0` iken durum asla PASS olamaz (KAPSAM_YOK zorunlu) — "hiç
   kontrol edilmedi" ile "kontrol edildi, temiz çıktı" artık ayırt edilebiliyor.
   Eski `List[str]` dönen fonksiyonlar (`pcb_highspeed_escape.py`,
   `mekanik_dxf_koprusu.py`, `kicad_koprusu.py`) GERİYE DÖNÜK UYUMLULUK için
   değiştirilmedi; `liste_sonucundan_bulgu_uret()` ile bu sözleşmeye sarılabilirler.

2. **`empedans_cozucu.py`** — `pcb_stackup_planner.py::empedans_hedefi_getir()`
   sadece bir HEDEF sayı (ör. USB3 için 90Ω) döndürüyordu; o hedefi
   FİZİKSEL OLARAK karşılayacak (W, S) iz genişliği/aralığını hesaplayan bir
   çözücü yoktu. Bu modül IPC-2141/Wadell kapalı-form formülünü uygular,
   W/S/H grid taraması yapar, ulaşılamayan hedefleri `ULASILAMAZ` diye
   işaretler, kendi kendini test eder (`oz_testleri_calistir()` — referans
   ölçüm + monotonluk + **fault-injection**: bilerek yanlış katsayı koyup
   testin gerçekten kırıldığını kanıtlar). **ENTEGRE EDİLDİ:**
   `pcb_stackup_planner.py::empedans_geometrisi_coz(cift, h_mm, er, ...)` —
   `empedans_hedefi_getir()`'i çağırıp sonucu doğrudan bu çözücüye besliyor.

3. **`pcbnew_koprusu.py`** — PROJENİN EN BÜYÜK BOŞLUĞUNU KAPATIYOR: şimdiye
   kadar `pcb_highspeed_escape.py`/`pcb_stackup_planner.py`/
   `mekanik_dxf_koprusu.py` hep SOYUT dataclass'lar üzerinde çalışıyordu,
   hiçbir modül gerçek `.kicad_pcb`'yi `pcbnew` ile AÇMIYORDU. Bu modül
   gerçek board'dan `PinArasiKanal`'ı otomatik üretir (`kanal_ciftlerini_bul`)
   ve gerçek-board DFM kontrolleri ekler (via-in-pad, annular ring, kenar
   keepout). **AĞ/ARAÇ UYARISI:** bu ortamda gerçek KiCad/`pcbnew` yok —
   dosyanın `import pcbnew` satırına kadarki mantık doğru yazıldı ama SENİN
   makinende gerçek bir `.kicad_pcb` ile ÇALIŞTIRILIP doğrulanmadı. **ENTEGRE
   EDİLDİ:** `kicad_koprusu.py::gercek_board_dogrulama_kapisi(board_path)` —
   `.claude/skills/pcb-layout/SKILL.md` Faz 5'e "standart DRC yetmez, bu da
   ZORUNLU" olarak eklendi.

4. **`sch_wire.py`** (eski adı `sematik_wire_motoru.py`, artık
   `sematik_wire_motoru_old.py` — DEPRECATED, sadece referans/regresyon
   testi için tutuluyor) — İKİNCİ BÜYÜK BOŞLUK: şematik üretimi tamamen
   `mcp__kicad__*` araçlarına bırakılmıştı, ama bu MCP'nin bilinen hataları
   var (bkz. `kicad_koprusu.py` Ek-A notu) ve YERİNE GEÇECEK kod yoktu. Bu
   modül gerçek `(wire)`/`(junction)`/`(label)`/güç sembolü üreten,
   `kicad-cli` netlist'iyle KANITLANAN bağımsız bir kütüphanedir (harici
   bağımlılık yok). **ENTEGRE EDİLDİ:** `.claude/skills/schematic-design/
   SKILL.md`'nin "Şematik Tasarım Kuralları" bölümüne madde 6 olarak eklendi
   — wire çizimi için BİRİNCİL yöntem bu modül, MCP ikincil/GUI-kolaylık.
   AĞ/ARAÇ UYARISI: bu ortamda `kicad-cli` yok — sadece S-Expr üretim/geometri
   tarafı test edildi; `netlist_nets`/`verify_nets`/`run_erc` senin
   makinende doğrulanmalı.
   **2026-07-30 GÜNCELLEMESİ:** `Otonom-PCB-Ajani` projesinden alınan
   İngilizce isimli `sch_wire.py`, projenin kendi (Türkçe isimli)
   `sematik_wire_motoru.py`'sinin YERİNE geçti — API'si (S-Expr üretimi,
   rotasyon/mirror geometrisi) neredeyse birebir aynıydı ama İKİ P0
   düzeltmeyi İÇERMİYORDU; entegrasyon sırasında ikisi de `sch_wire.py`'ye
   taşındı: (1) `assert_kicad_closed()` koşulsuz `pgrep` çağırıyordu —
   Windows'ta `pgrep` yok, `FileNotFoundError` ile yazma işlemini
   TAMAMEN kesiyordu; artık platform algılanıyor (Windows: `tasklist`).
   (2) `netlist_nets`/`run_erc` düz `"kicad-cli"` stringi çağırıyordu;
   artık `arac_yollari.kicad_cli_yolunu_bul()` ile çözülüyor. Eski dosya
   `sematik_wire_motoru_old.py` olarak korunuyor (silinmedi) — kod
   tabanında ona `import` eden BAŞKA modül yoktu, sadece DOCS/yorum
   referansları vardı, hepsi `sch_wire.py`'ye güncellendi.

Ayrıca: `test_pcb_highspeed_escape.py`, `test_mekanik_dxf_koprusu.py`,
`test_kicad_koprusu.py` dosyalarına birer **fault-injection testi** eklendi
(önce temiz senaryo → PASS, sonra bilerek bozma → FAIL — testin gerçekten
bir şey kontrol ettiğinin kanıtı, `zdiff_solver.py`'deki desenden alındı).

## 🆕 2. TUR — Profesyonelleşme (dokümantasyon, IPC standartları, EMI/EMC, Git)

5. **`DOCS/`** — `00_INDEX.md`'den `05_Release_Checklist.md`'ye kurumsal
   şablon hiyerarşisi. **Bunlar `MASTER_RULEBOOK.md`'nin YERİNE geçmez** —
   Rulebook "genel kural"ı, `DOCS/*.md` "bu projenin bu revizyonu için
   verilen KARARI" kaydeder (bkz. `DOCS/00_INDEX.md` ilke bölümü). Her
   dosyanın başında `Durum: TASLAK/İNCELEMEDE/ONAYLANDI` satırı var —
   onaylanmamış dosyaya dayanarak üretime geçilmez.

6. **`ipc7351_footprint.py`** — İki-terminalli çip komponentler (0402/0603/
   0805/1206 R/C/L) için IPC-7351B land pattern (pad boyutu) hesaplayıcısı,
   3 yoğunluk seviyesi (A/B/C) + kendi kendini test eden (`test_ipc7351_footprint.py`)
   bir modül. **SINIR:** QFN/BGA/gullwing gibi çok-pinli paketleri kapsamaz
   (`TBD`) — datasheet land pattern'i onlarda hâlâ esastır.

7. **`.claude/skills/emi-emc/SKILL.md`** — Önceden dağınık duran EMI/EMC
   kodunu (`pcb_stackup_planner.py` RF stitching/guard-ring, `kicad_koprusu.py::
   check_reference_plane_continuity`) TEK bir skill altında topluyor + YENİ
   bir gerçek-board ölçümü ekliyor: `pcbnew_koprusu.py::stitch_yogunlugu_kontrolu()`
   (λ/20 hedefine göre GND stitching via yoğunluğu — arkadaşının
   `stitch_density.py`'sinin karşılığı). **ENTEGRE EDİLDİ:**
   `tum_gercek_board_kontrollerini_calistir()`'e otomatik dahil; `pcb-layout`
   Faz 5 ve CLAUDE.md tool listesine referans eklendi.

8. **`uretim_ciktilari_cli.py`** — Tek komutla Gerber/Drill/BOM/CPL üretimi
   (`kibot_config_yaz`/`kibot_calistir`'i sarar) AMA önce DRC+ERC+gerçek-board
   doğrulama kapısını ZORUNLU kılar — "tek tıkla üretim çıktısı" isteğinin
   "DRC'yi atlayarak tek tıkla" olmaması için. `--force-atla-dogrulama`
   SADECE hata ayıklama içindir, isim bilinçli olarak uzun/kullanışsız.

9. **Git/versiyon kontrolü:** `.gitattributes` eklendi (KiCad S-Expr dosyaları
   metin/LF, üretim çıktıları binary — diff gürültüsünü önler).
   `KURULUM.md` madde 9-10: commit disiplini + görsel diff (`kicad-diff`,
   `pcb_gorseli_disa_aktar()` SVG'sinin iki revizyon arasında karşılaştırılması).

   **Windows dosya kilidi kuralı (2026-07-31 eklendi):** Otonom akış çok
   hızlı art arda script çalıştırdığında (özellikle bir `.kicad_pcb`/
   `.kicad_sch` dosyasını KiCad'in kendi python'uyla `board.Save()` ile
   yazdıktan HEMEN SONRA `git add`/`git commit` çağrıldığında), Windows
   dosya tanıtıcısını henüz serbest bırakmamış olabilir ve `git add .`
   "Permission denied" ile başarısız olur — bu bir mantık hatası DEĞİL,
   geçici bir işletim sistemi kilididir. İki kural ZORUNLU:
   1. **Gecikme:** bir dosyayı güncelleyen/kaydeden bir script'ten
      (özellikle `pcbnew`/`kicad-cli` çağıran) HEMEN SONRA `git add`
      ÇAĞIRMA — araya 2-3 saniyelik bir bekleme koy (`sleep 3` veya
      Python'da `time.sleep(3)`).
   2. **Yeniden deneme:** `git add`/`git commit` "Permission denied" ile
      başarısız olursa PES ETME — 5 saniye bekleyip TEKRAR dene. Sorun
      devam ederse, arka planda asılı kalmış olabilecek `python.exe`/
      `kicad-cli.exe`/`pcbnew` süreçlerini `taskkill` ile sonlandırmayı
      dene, sonra tekrar dene.

## 🆕 3. TUR — Otonom-PCB-Ajani birleştirmesi + DFA/EMI-EMC kural motorları (2026-07-30)

10. **`sch_wire.py` devralması** — bkz. yukarıdaki madde 4'ün 2026-07-30
    güncellemesi: `Otonom-PCB-Ajani`'den alınan İngilizce isimli
    `sch_wire.py`, iki P0 düzeltmesiyle (Windows süreç algılama,
    `kicad_cli_yolunu_bul` yol çözümü) birlikte projenin BİRİNCİL şematik
    wire motoru oldu; eski `sematik_wire_motoru.py` →
    `sematik_wire_motoru_old.py` (DEPRECATED, silinmedi).

11. **`uretim_zinciri_koprusu.py` BÖLÜM 5 — Kontrat (artifact) kapıları:**
    `Otonom-PCB-Ajani`'nin "adımlar arası JSON artifact üzerinden bağlan"
    mimari dersi bu projeye taşındı: `drc.json`/`parts.json` şemaları
    (`DrcKontrati`/`PartsKontrati`) + kapı fonksiyonları (`drc_kapisi_gecti_mi`,
    `parts_kapisi_gecti_mi`) HER ZAMAN DİSKTEN okur, bellekteki `dict`'ten
    DEĞİL; dosya yoksa/bozuksa `KontratKapisiHatasi` (fail-open YOK).
    `uretim_zincirini_kontratla_yurut()` bu iki kapıyı `kibot_calistir()`'den
    ÖNCE zorunlu kılar. Bu arada bulunan bir regresyon da düzeltildi:
    `KiBotSonucu` sınıfının `@dataclass class` başlığı eksikti (çağrılınca
    `NameError` fırlatırdı, hiç test edilmediği için yakalanmamıştı).

12. **`ipc_a_610_dfa_motoru.py`** — IPC-A-610 ruhuna uygun (bkz. dosya
    başlığındaki dürüstlük notu: IPC-A-610'un kendisi çoğunlukla NİTEL
    kabul kriteri tanımlar, sabit mesafe tablosu değil) Pick-and-Place/
    Reflow komponent-komponent (SMD-SMD/SMD-THT/THT-THT) + komponent-kart
    kenarı minimum boşluk hesaplayıcı ve `bulgu_sozlesmesi.Bulgu`
    sözleşmesiyle GERÇEK yerleşimi denetleyen `IpcA610DfaMotoru`. Reflow
    ısıl gölgeleme (shadowing) riski, gövde yükseklik farkına göre ek
    boşluk ister. **ENTEGRE EDİLDİ:** `DOCS/04_DFM_and_DFA.md` §1b,
    `ipc_dru_koprusu.py::dfa_courtyard_kuraline_cevir()` (`.kicad_dru`
    `courtyard_clearance` kuralı — DOĞRULANMADI, bkz. fonksiyon notu).

13. **`emi_emc_kural_motoru.py`** — 3W (crosstalk), 20H (kenar ışıması/
    fringing) ve via-stitching (`λ/dizi_carpani`, `pcbnew_koprusu.C_MPS`
    ile tek kaynak gerçeklik) kurallarını hesaplayan + `Bulgu`
    sözleşmesiyle denetleyen motor. **ENTEGRE EDİLDİ:**
    `.claude/skills/emi-emc/SKILL.md` §4b, `DOCS/04_DFM_and_DFA.md` §5,
    `ipc_dru_koprusu.py::uc_w_kuraline_cevir()` (3W'nin `.kicad_dru`
    clearance kuralı — DOĞRULANMADI, SENİN makinende kicad-cli DRC ile
    teyit edilmeli, tıpkı `ipc2221_kuraline_cevir`'in iki-net-class
    koşulu gibi). 20H kuralı `.kicad_dru`'ya YAZILAMAZ (KiCad custom
    rule dilinde "plane setback" constraint tipi yok) — Python tarafında
    denetime devam eder.

14. **DÜRÜSTLÜK NOTU (10-13'ün ortak noktası):** `Otonom-PCB-Ajani`de
    `parts.json`/`drc.json` diye somut bir şema/örnek dosya YOKTU —
    yalnızca kavramsal isim geçiyordu (`SKILL-orchestrator.md`). Bu
    projenin kontrat şemaları BURADA, bu projenin gerçek araçlarına göre
    YENİDEN tanımlandı; "arkadaşın projesinden birebir kopyalandı" DEĞİL.

## 🆕 4. TUR — Opsiyonel/ek araçlar (2026-07-30, `ProjectE-main` karşılaştırması)

Bu 4 dosya **hiçbir mevcut akışı/fonksiyonu DEĞİŞTİRMEDEN** eklendi —
otonom akışın (madde "Otonom akış (sırayla)") hiçbir adımı bunları
ÇAĞIRMIYOR, tamamen opsiyonel/elle-çağrılan araçlardır. "Güvenli yol"
bilinçli tercih edildi: mevcut `sch_wire.py`/kontrat kapıları BİRİNCİL
yöntem olmaya devam eder, aşağıdakiler bunların YANINDA durur.

15. **`sch_route.py` + `rewire.py` + `wireify.py`** — `sch_wire.py`'nin
    (elle L/Z rota çizen) tek tek wire API'sinin ÜSTÜNE, sembol gövdelerinden
    kaçan gerçek bir A* pin-pine router ekler (`sch_route.Router`, MST ile
    net ağaçlama, yabancı net'e kısa devreyi YAPISAL olarak engelleme).
    `rewire.py` bunu kullanarak "label ile uçan bağlı" bir şematiği baştan
    tek komutla pin-pine telli hale getirir — ama netlist'in İŞLEM ÖNCESİ/
    SONRASI **birebir aynı** kaldığını kanıtlamadan yazmaz, farklıysa
    `.bak`'tan otomatik geri alır (`--write` olmadan varsayılan dry-run).
    **Ne zaman kullanılır:** çok pinli/karmaşık bir şematikte elle
    `sch_wire.py` çağrıları yazmak yerine, mevcut netlist'i koruyarak
    OTOMATİK telleme isteniyorsa. `test_sch_route.py`/`test_rewire.py` bu
    ortamda test edildi (A*/MST/junction saf mantığı); `rewire()`'ın uçtan
    uca akışı GERÇEK KiCad sembol kütüphanesi + kicad-cli gerektirir,
    `test_sch_wire.py` ile AYNI disiplinle SENİN makinende doğrulanmalı.

16. **`via_stub.py`** — projenin kendi `SKILL-dogrulama-matrisi.md`
    envanterinde "yazılması gereken, henüz yok" diye işaretli olan via-stub
    rezonans kontrolünü doldurur (`f_res = c/(4·L_stub·√Dk_eff)`, kanal
    bant genişliğine göre kapı). `dfm_emc_check.py` ile AYNI desende
    (`import pcbnew` modül seviyesinde) — bu ortamda test EDİLEMEDİ,
    SENİN makinende gerçek `pcbnew` + `.kicad_pcb` ile çalıştırılmalı.
    `pcb-layout`/`emi-emc` skill'lerine HENÜZ ZORUNLU adım olarak
    BAĞLANMADI — yüksek hızlı diferansiyel çiftli (USB/MIPI/RGMII) bir
    tasarımda elle çağrılması önerilir.

17. **`gate_receipt.py`** — `uretim_zinciri_koprusu.py` BÖLÜM 5'teki
    (madde 11) `parts.json`/`drc.json` kapılarından ÇOK DAHA SIKI, genel
    amaçlı bir "kapı makbuzu" sözleşmesi: SHA-256'ya bağlı input/tool/config
    kimliği, metric semantiği + kapsam (coverage) doğrulaması, zorunlu
    fault-injection kanıtı (A-seviyesi kapılarda), çocuk-kapı (child gate)
    indirgeme, promotion (scratch→canonical) atomiklik kanıtı, retention
    politikası. **Mevcut BÖLÜM 5'in YERİNE GEÇMEDİ** — tamamen bağımsız,
    stdlib-only bir CLI (`python gate_receipt.py RECEIPT.json`). Kendi
    kaynak test paketiyle (42 test, `test_gate_receipt.py` +
    `test_fixtures/gate_receipt/`) BU ORTAMDA GERÇEKTEN koşturulup PASS
    verdi. İleride BÖLÜM 5'in yerini almasına karar verilirse bu KASITLI,
    ayrı bir görev olmalı — otomatik/sessiz bir geçiş YAPILMADI.

18. **DÜRÜSTLÜK NOTU:** Bu 4 dosya `ProjectE-main`'deki `Otonom-PCB-Ajani`
    kopyasından (madde 1-14'ü ürettiğimiz kopyanın GÜNCELLENMİŞ hali)
    alındı. `sch_wire.py`/`dfm_emc_check.py` bu kopyada BİREBİR AYNIYDI
    (diff ile doğrulandı, yeni düzeltme yok) — sadece bu 4 dosya YENİYDİ.

## 🆕 5. TUR — `pcb_gorsel_kesit.py`: ajanın GERÇEK görme yeteneği (2026-07-30, ESP32-C3 Smart Band oturumu)

19. **`pcb_gorsel_kesit.py`** — U2 (ICM-42688-P, LGA-14, 0.5mm pitch)
    çevresinde koordinat-bazlı "kör" via/iz yerleştirme 4 kez üst üste
    önceden bilinmeyen bir engelle (F.Cu/In2.Cu izleri, "net'siz" pinlerin
    gerçek bakırı, dar koridorlar) başarısız olunca doğdu (bkz.
    `HAFIZA/Hafiza_Defteri.md`, "U2 ... GUI'ye bırakılmalı" kaydı) —
    bu modül o sorunu KÖKTEN çözer: board'un istenen bir mm bölgesini
    GERÇEK bir PNG'ye çevirir, Claude Code `Read` aracıyla bunu
    DOĞRUDAN görür (kelimenin tam anlamıyla — piksel görüntüsü, koordinat
    listesi DEĞİL). Zincir: `kicad-cli pcb export svg --page-size-mode 2
    --fit-page-to-board` (SVG (0,0) = board'un Edge.Cuts bbox min köşesi,
    1 birim = 1mm) → `svglib`+`reportlab` (SVG→PDF, saf Python, native
    bağımlılık yok) → `pdftocairo`/poppler (PDF→yüksek çözünürlüklü PNG)
    → `Pillow` (bilinen mm→piksel oranıyla kırpma+büyütme). Edge.Cuts
    sınırlarını kendi derinlik-sayan S-Expr ayrıştırıcısıyla bulur
    (`pcbnew` GEREKTİRMEZ — `sch_wire.py`'nin felsefesiyle aynı, ama
    BAĞIMSIZ bir kopya, şematiğe özgü modüle bağımlı olmasın diye).
    **DOĞRULANDI:** gerçek `ESP32C3_SmartBand.kicad_pcb`'ye (yuvarlak
    kenarlı, `gr_circle` ile tanımlı board outline) karşı çalıştırıldı —
    ilk deneme naif regex'in İÇ İÇE parantezlerde (`gr_circle` içindeki
    `(stroke (width..) (type..))`) yanlış blok sınırı bulduğunu ortaya
    çıkardı, derinlik-sayan ayrıştırıcıyla düzeltildi, `oz_testleri_calistir()`'e
    bu regresyonu kilitleyen bir test eklendi. **DÜRÜSTLÜK SINIRI:** bu
    modül SADECE görsel yönlendirme içindir — ölçüm/DRC/üretim kararı
    için KULLANILMAMALI, o kararlar `kicad_koprusu.py`/`pcbnew_koprusu.py`'ye
    aittir (SVG↔board koordinat eşlemesinde ~0.06mm'lik yay-örnekleme
    farkı ölçülmüştür, göz kontrolü için önemsiz).
    Kurulum: `KURULUM.md` madde 11.

## 🆕 6. TUR — `pcb_carpisma_radari.py`: JSON Çarpışma Radarı (2026-07-31)

20. **`pcb_carpisma_radari.py`** — Placement/routing DOĞRULUĞUNU test
    ederken madde 19'daki `pcb_gorsel_kesit.py`'ye ("bak, gözle karar ver")
    bağımlı kalmayı SONLANDIRAN deterministik JSON API. Karttaki her
    footprint'in gerçek sınır kutusunu (`pcbnew.FOOTPRINT.GetBoundingBox
    (False, False)` — TUZAK: `False, False` silkscreen'i HARİÇ tutar)
    okuyup (a) komponent-komponent çakışmasını (b) komponent-Edge.Cuts
    taşmasını X/Y mm örtüşme + önerilen kaçış mesafesiyle raporlar:
    ```json
    [{"hata_tipi": "CARPISMA", "parca_1": "U1", "parca_2": "C3",
      "ic_ice_gecme_X_mm": 1.2, "ic_ice_gecme_Y_mm": 0.5,
      "tavsiye_edilen_kacis_X_mm": 1.5, "tavsiye_edilen_kacis_Y_mm": 0.5}]
    ```
    **Mimari ayrım (önemli):** saf geometri fonksiyonları
    (`kutular_carpisiyor_mu`, `carpisan_ciftleri_bul`,
    `kart_disina_tasmayi_bul`) `pcbnew`'e HİÇ dokunmaz — düz
    `SinirKutusu` dataclass'ları üzerinde çalışır, bu yüzden bu ortamda
    (gerçek `pcbnew` OLMADAN) 18 pytest testiyle GERÇEKTEN doğrulandı
    (`test_pcb_carpisma_radari.py`, mock `SahteBoard`/`SahteFootprint`/
    `SahteBBox` ile). Sadece `komponent_sinir_kutularini_al()` (duck-typing,
    `import pcbnew` bile YAPMAZ) ve CLI sarmalayıcısı `carpisma_json_uret()`
    (`import pcbnew` yapar) gerçek board'a dokunur — ikincisi bu ortamda
    ÇALIŞTIRILAMADI, SENİN makinende gerçek bir `.kicad_pcb` ile
    doğrulanmalı (aynı disiplin: `pcbnew_koprusu.py` AĞ/ARAÇ UYARISI).
    **ENTEGRE EDİLDİ:** `.claude/skills/pcb-layout/SKILL.md` Aşama 3.0b
    (yeni) — yerleşim/routing doğruluğu test edilirken `pcb_gorsel_kesit.py`
    ile bakmak ARTIK YASAK, bu radar ZORUNLU; Faz 5'in "Görsel Denetim"
    adımı SADECE bounding-box'la yakalanamayan nitel/holistik son-bakışla
    (silkscreen/pad çakışması, RF bölgesi, ısı-hassas yakınlık) sınırlandı.
    `DOCS/00_Dashboard.md`'nin Modül durumu tablosuna eklendi.

## 🆕 7. TUR — Tam Otonom Kurtarma Mekanizması (2026-07-31)

21. **`otonom_kurtarma_motoru.py`** — Görev 1+2'nin kod karşılığı:
    `izole_calistir()` HER `pcbnew`-dokunan yazma çağrısını (segfault/hang
    riski taşıyan) kısa ömürlü bir `subprocess.run()` alt sürecinde
    izole eder — timeout/çökme/geçersiz-çıktı ÜÇÜ de yapılandırılmış
    `IzoleSonuc` olarak döner, ana süreç ASLA düşmez. `bolumlu_yol_dene()`
    uzun (12-14mm) bir rotayı ~5mm'lik parçalara bölüp her parçayı ayrı
    `akilli_yol_bul()` ile çözer — tek parça bile çözülemezse TÜM sonuç
    `BULUNAMADI` (kısmi yol asla yazılmaz). `otonom_routing_merdiveni()`
    bu ikisini + madde 22'yi TEK bir çağrıda sırayla dener. 15 pytest
    testiyle (gerçek subprocess sandboxing dahil, `pcbnew` GEREKMEDEN)
    doğrulandı.
22. **`otonom_python_router.py`** — Görev 3: `akilli_yol_bul()`'un dört
    basamağı da tükenirse devreye giren SON ÇARE, ızgara (grid) tabanlı
    8-yönlü A* arama motoru (`izgara_a_yildiz_ara()`) — saf Python,
    `pcbnew`'e HİÇ dokunmaz, `pcb_carpisma_radari.SinirKutusu`-uyumlu
    herhangi bir engel listesini kabul eder. Bulunan yol SADECE
    `duz_izleri_pcbnew_ile_yaz()` ile düz `pcbnew.PCB_TRACK` segmentleri
    olarak yazılır — KiCad'in `route_trace`/PNS router çekirdeği
    KULLANILMAZ (kullanıcının açık isteği). 13 pytest testiyle (arama
    motoru `pcbnew` GEREKMEDEN) doğrulandı.
    **DÜRÜSTLÜK NOTU:** `duz_izleri_pcbnew_ile_yaz()`/`otonom_routing_
    merdiveni()`'nin gerçek `.kicad_pcb` YAZMA adımı bu ortamda (gerçek
    `pcbnew` KURULU DEĞİL — doğrulandı: `import pcbnew` → `ModuleNotFoundError`)
    ÇALIŞTIRILAMADI; SENİN makinende (gerçek `pcbnew` + gerçek bir board
    ile) doğrulanmalı — aynı disiplin `pcbnew_koprusu.py`/`mcad_carpisma_
    koprusu.py`'de zaten var. Sandboxing/segmentasyon/A*-arama katmanları
    (`pcbnew`'e dokunmayan kısımlar) BU ortamda GERÇEKTEN test edildi.

---


Bu repo, insan müdahalesi olmadan uçtan uca donanım/PCB tasarımı yapan bir
Claude Code kurulumudur. Kullanıcı bir donanım/devre/PCB tasarım isteği
getirdiğinde ("bana ... özellikli bir devre tasarla" gibi), **hangi
aracı/skill'i kullanacağını sorma** — aşağıdaki zinciri kendiliğinden,
sırayla uygula. Onay noktaları (bkz. "Ne zaman dur") dışında durma.

## Bağlayıcı kurallar (her adımda geçerli, istisnasız)
- `MASTER_RULEBOOK.md` — tüm fazların bağlayıcı anayasası + sonundaki
  `EK: Hızlı Kontrol Listesi` (checkbox özeti). Her fazda buna uy.
- `TASARIM_AKISI.md` — aynı sürecin IF/ELSE karar-akışı görünümü;
  `pcb_stackup_planner.py`'nin hangi adıma karşılık geldiğini gösterir.

Bu iki dosya birbirinin YERİNE geçmez, ikisi birlikte okunmalı: biri "ne
yapılacağını" (Rulebook), diğeri "hangi sırayla/hangi koşulda"yı (Akış)
tanımlar.

## Otonom akış (sırayla — kullanıcı adım adım yönlendirmez)

1. **Ortam hazırlığı (yeni bir makinede/kişide İLK ÇALIŞTIRMA dahil)** —
   `schematic-design` skill'inin Faz -1'i çalıştırılır (proje klasörleri,
   kicad-cli yolu) VE ek olarak `uv run python ortam_on_kontrol.py --tam`
   sessizce çalıştırılır (`KURULUM.md`'nin "Hızlı toplu doğrulama" bölümü —
   kabuktan bağımsız, bash'te de PowerShell'de de aynı şekilde çalışır ve
   tek bir eksik araç diğerlerinin kontrolünü ENGELLEMEZ). Eksik çıkan her
   araç için kullanıcıya **KURULUM.md'deki o maddenin tam kurulum
   komutunu** göster — "kurulu olduğunu varsay" veya "sessizce atla"
   YASAK; bu proje başka bir kişiye/makineye taşındığında otomatik olarak
   neyin eksik olduğunu söylemesi gerekir. Hepsi PASS ise bunu tek
   satırla doğrula ve akışa devam et.
   Ardından **`HAFIZA/Hafiza_Defteri.md`'yi baştan sona oku** — bu dosya,
   önceki tasarımlarda alınan ve GELECEKTEKİ bir tasarımı da etkileyebilecek
   kararların/hataların serbest-metin günlüğüdür (bkz. dosyanın kendi
   şablonu). Buradaki bir ders şu anki tasarımın şartlarıyla (form faktör,
   güç kaynağı tipi, hedef fabrika) örtüşüyorsa, aynı hata/tartışma
   sıfırdan tekrarlanmadan doğrudan `MASTER_RULEBOOK.md`/
   `DOCS/01_Design_Requirements.md`'ye karar olarak taşınır.
2. **Devre tanımı (Circuit-Synth)** — `main.py`, `circuit-synth`
   kütüphanesiyle devrenin Python tanımını yapar; şematik buradan
   üretilir/senkronize edilir.
3. **Şematik + doğrulama** — `schematic-design` skill'i Faz 0-4
   (gereksinim, datasheet analizi, **known-good `SNIPPETS/` blok kontrolü**,
   çizim, footprint, 4 aşamalı doğrulama: pin karşılaştırma / ERC / netlist
   / simülasyon). Eksik bir footprint çıkarsa
   `uretim_zinciri_koprusu.py::jlc_parcasi_indir()` ile LCSC koduyla
   otomatik indir — **ama önce** `bom_lifecycle_koprusu.py::validate_bom_lifecycle()`
   + `lifecycle_raporu_olustur()` ile MASTER_RULEBOOK Faz 1 yaşam-döngüsü/stok
   kontrolü yapılıp kullanıcıya raporlanmış olmalı. Risk skoru >0.5 çıkan
   parçalar için `find_pin_compatible()` ile alternatif aranır; uygun aday
   yoksa `NEEDS_HUMAN`, aday footprint değiştiriyorsa bu adıma (3) veya
   Faz 2/stackup'a feedback açılır — sessizce geçilmez.
   Mekanik tarafta board outline/keepout gerekiyorsa (kasa/enclosure varsa)
   `mekanik_dxf_koprusu.py::import_board_outline()` + `derive_keepouts()`
   bu adımda veya paralelinde çalışır ve `keepout_zones.json`'u üretir.
4. **PCB yerleşim ve routing** — `pcb-layout` skill'i Faz 1-5 (hesap,
   stackup, ratsnest-bazlı yerleşim, **routing'den önce `custom_dru_yaz()`
   ile net-class bazlı fiziksel DRC kilidi** + **Aşama 3.7: `TEST/routing_plan.json`
   / `.md` topoloji raporu ve KULLANICI ONAYI — onaysız çizime başlanmaz**,
   routing önceliği, DRC).
   Yerleşim, `mekanik_dxf_koprusu.py::z_kontrolu_yap()`'ın ürettiği 3D
   keepout ihlallerini SIFIRLAMADAN bir sonraki adıma geçemez.
   Yerleşim onaylandıktan sonra, kasa STEP verisi VARSA MASTER_RULEBOOK
   **Faz 4b** koşar: `ecad_mcad_termal_kopru.py` ile kasa temas yüzeyi
   (`soguturucu_yuzey_bul`), B.Mask açıklığı + ENIG zorunluluğu
   (`termal_yonetim_ve_mask_kontrolu`), termal ped kalınlığı ve termal
   bariyer (`edge_cuts_yarigi_oner` → web yetmezse `NEEDS_HUMAN`)
   değerlendirilir. Kasa STEP'i paylaşılmadıysa bu faz sessizce ATLANIR. Düşük hızlı
   dijital I/O routing'i için `uretim_zinciri_koprusu.py::freerouting_zinciri_calistir()`
   **DÜŞÜNÜLMÜŞTÜ ama KiCad 10 + kicad-cli ile KULLANILAMAZ** — gerçek
   `kicad-cli pcb export --help` çıktısında DSN dışa aktarımı YOK
   (doğrulandı, bkz. `dsn_disa_aktar()` docstring'i); bu fonksiyon çağrılırsa
   `NotImplementedError` fırlatır. Bu yüzden **düşük hızlı I/O routing'i de
   şimdilik `topolojik_router_koprusu.py::akilli_yol_bul()` (Pathfinding
   merdiveni) veya `pcb-layout` Faz 4'ün manuel yöntemleriyle** yapılır;
   FreeRouting zinciri sadece kicad-cli DSN desteği geri gelirse ya da
   `pcbnew` Python API'siyle (bu ortamda kurulu değil) yeniden inşa
   edilirse devreye alınmalı. USB/MIPI gibi yüksek hızlı diferansiyel
   çiftler ZATEN FreeRouting'e bırakılmadan elle/`Route Differential Pair`
   ile ayrı çizilir — pad'den çıkış geometrisi (maske barajı, açılma, 90°
   köşe, ps-skew) `pcb_highspeed_escape.py::escape_raporu_olustur()` ile
   değerlendirilir.
5. **Doğrulama kapısı** — `kicad_koprusu.py::drc_calistir()` ve
   `erc_calistir()` ikisi de temiz dönmeden bir sonraki adıma geçilmez.
   İlk DRC/ERC çalıştırmasından ÖNCE `hata_hafizasi.py::onceki_cozumleri_rapora_dok()`
   ile hafıza taranır — "geçen sefer bu sınıf hatayı nasıl çözmüştük" (veya
   "bunu denedik, olmadı") özeti okunur; her DRC/ERC turu sonunda
   `hafizaya_ogret()` ile yeni ihlaller (ve varsa çözümleri) hafızaya
   işlenir, böylece bir sonraki proje aynı hatada sıfırdan başlamaz.
   Ayrıca `check_reference_plane_continuity()` (yüksek hız hattı split/void
   üzerinden geçmemeli — standart DRC bunu YAKALAMAZ) ve
   `maske_baraji_kontrolu()` (pin-arası kanaldan geçen izlerde, ayrı bir
   üretim riski) burada koşar — DRC "temiz" dese bile bu ikisi ayrıca
   sıfır bulgu vermeli. Aynı ihlal art arda 3 kez çıkarsa
   `tekrarlanan_ihlal_tespit_et()` bunu yakalar; o noktada `pcb-layout`
   skill'indeki "Sonsuz Döngü Kaçış Kuralı" uygulanır (küçük düzeltme
   değil, tamamen farklı geometriden yeniden çizim). Bu genel kural sadece
   DRC'ye özel değildir — **her feedback kenarında** (BOM→stackup, DFM→stackup,
   escape→routing) aynı sayaç/eşik (3) uygulanır, aşılırsa `NEEDS_HUMAN`.
   DRC temiz olunca `pcb_gorseli_disa_aktar()` ile SVG üretilip **görsel
   (vision) denetim** yapılır — metin tabanlı DRC'nin yakalayamayacağı
   yerleşim/görünüm sorunları için.
5b. **DFT (test noktaları)** — `dft-testpoints` skill'i çağrılır: Faz A
   (erken) `insert_test_points()` ile şematik fazında (adım 3) TP'ler
   şematiğe girer; Faz B (geç) burada, yerleşim sonrası erişilebilirlik +
   `generate_bringup_checklist()` çıktısıyla tamamlanır.
6. **Bağımsız denetim (Checker)** — `design-checker` skill'i çağrılır.
   Bu skill Maker'ın (adım 3-5) raporlarına güvenmeden netlist/BOM/DRC'yi
   kendi başına yeniden değerlendirir ve `TEST/checker_raporu.md`'ye
   PASS/CONDITIONAL PASS/FAIL yazar. **FAIL ise adım 7'ye geçilmez**,
   ilgili faza geri dönülür. **PASS/CONDITIONAL PASS verince**, bu oturumda
   GELECEKTEKİ bir tasarımı da etkileyebilecek her karar/hata (form faktör
   ödünü, tedarik sürprizi, düzeltilen yanlış bir varsayım — bkz.
   `HAFIZA/Hafiza_Defteri.md`'nin kendi eşiği: "bu dersi bilmeseydim başka
   bir projede de aynı hatayı yapar mıydım?") o dosyaya kayıt şablonuyla
   eklenir. Sıradan/tek seferlik düzeltmeler buraya GİRMEZ — her oturumda
   otomatik bir madde eklenmesi ZORUNLU DEĞİLDİR.
7. **Üretim çıktıları** — Checker PASS/CONDITIONAL PASS verince önce
   `uretim_zinciri_koprusu.py::rotation_map_versiyonla()` ile fab-rotasyon
   map'i damgalanır (VERSİYONSUZ map ile devam etmek YASAK — tüm parti ters
   lehim riski), `generate_cpl_file()` + `rotasyon_duzeltmesi_uygula()` +
   `check_orientation()` (kutuplu parça yönü ↔ CPL açısı çapraz kontrolü)
   koşar, panel varsa `panelizasyon_kontrolu()` (fiducial/rail/de-panel
   mesafesi) doğrulanır. Sonra `kibot_config_yaz()` + `kibot_calistir()`
   ile Gerber/BOM/CPL tek ZIP'te otomatik üretilir. JLCPCB DFM API
   entegrasyonu (`jlcpcb_dfm_kontrolu_gonder()`) **doğrulanmadı** (bkz.
   dosyanın içindeki not) — gerçek API erişimi olmadan bu adım atlanır,
   MASTER_RULEBOOK Faz 8'in yerel DFM kontrolü tek güvenilir kapı olarak
   kalır. Gerber üretildikten SONRA, ZIP'lenmeden ÖNCE
   `gerber_dfm_gorsel_koprusu.py::maske_baraji_taramasi()` +
   `bakir_bosluk_taramasi()` GERÇEK export edilmiş `.gtl`/`.gts`
   dosyalarına karşı koşar — kicad-cli DRC'nin sembolik modelinden
   BAĞIMSIZ, gerçek üretim koordinatından ikinci bir kanıt. Kasa STEP
   verisi varsa (Faz 4b'nin `KasaEngelHacmi` girdisiyle aynı kaynak)
   `mcad_carpisma_koprusu.py::carpisma_tara()` da bu adımda koşar — kasa
   verisi yoksa (Faz 4b ile aynı disiplin) sessizce atlanır.

## Kurulum
Bu proje başka bir makineye/kişiye taşındığında **önce `KURULUM.md`**
okunmalı — KiCad 10, kicad-python (kipy), mixelpixx/KiCAD-MCP-Server,
kicad-happy (Claude Code plugin), Circuit-Synth (`uv sync`), FreeRouting,
JLC2KiCadLib, KiBot için tam kurulum komutlarını içerir. Faz -1 bunu
otomatik kontrol eder (yukarıya bak); bu bölüm sadece hangi aracın NEREDE
tanımlı olduğunu gösterir.

## Kullanılabilir araçlar (kurulumu `KURULUM.md`'de — burada tekrar anlatılmaz)
- **Circuit-Synth** (`main.py`, `pyproject.toml` bağımlılığı) — devrenin
  Python'da tanımlanması.
- **kicad-happy skill** — Claude Code plugin marketplace üzerinden kurulur
  (`KURULUM.md` madde 4); bu repo onu yeniden tanımlamaz/vendor etmez, kurulu
  haliyle kullanılır.
- **kicad-python (kipy) / MCP (`mcp__kicad__*`)** — GUI-benzeri KiCad
  işlemleri. `kicad_koprusu.py`'nin başındaki Ek-A bilinen MCP
  hatalarını listeler (`sync_schematic_to_board`, `get_net_connections`,
  `get_schematic_pin_locations`) — kritik/güç netlerini HER ZAMAN
  `kicad-cli` ile bağımsız doğrula, MCP sonucuna körü körüne güvenme.
- **kicad-cli** — kanonik/öncelikli doğrulama yöntemi
  (`kicad_koprusu.py`: `drc_calistir`, `erc_calistir`,
  `net_classleri_projeye_yaz`, `tekrarlanan_ihlal_tespit_et`,
  `custom_dru_yaz`, `pcb_gorseli_disa_aktar`).
- **FreeRouting (KiCad 10'da KULLANILAMAZ — bkz. yukarıdaki not) /
  JLC2KiCadLib / KiBot / JLCPCB DFM API (doğrulanmadı) + CPL/panelizasyon
  (rotasyon-map versiyonlama, oryantasyon çapraz kontrolü, panel/fiducial/
  rail kuralları)** — `uretim_zinciri_koprusu.py` (BÖLÜM 1-3 dış araçlar,
  BÖLÜM 4 CPL/panelizasyon — BÖLÜM 4 CPL/panelizasyon fonksiyonları
  BÖLÜM 1'den bağımsızdır ve etkilenmez).
- **emi-emc skill** — topraklama stratejisi, dekuplaj yerleşimi, ekranlama,
  stitching via yoğunluğu (`pcbnew_koprusu.py::stitch_yogunlugu_kontrolu`) ve
  termal/EMI kesişen kararlar. Faz 2-3'te (stackup + şematik) koşmalı — Faz
  4'te keşfedilen EMI problemi kart dönüşü demektir. Kabul kriterleri
  `pcb-layout` Faz 5 doğrulama kapısına dahildir.
- **design-checker skill** — Maker'dan (schematic-design/pcb-layout) ayrı,
  bağımsız denetmen rolü; üretime geçmeden önceki son kapı.
- **dft-testpoints skill** — güç+debug TP kapsamı (iki fazlı: şematikte erken,
  yerleşim sonrası geç) + `bringup_checklist.md`; `kicad_koprusu.py`'deki
  `insert_test_points`/`tp_kapsam_kontrolu`/`generate_bringup_checklist`
  fonksiyonlarını kullanır.
- **pcb_highspeed_escape.py** — pad'den çıkış (escape) geometrisi: maske
  barajı (solder mask dam) hesabı, çiftin pad sütununa girmeden açılması,
  90° köşe tespiti, skew'in ps cinsinden değerlendirilmesi (gereksiz meander
  eklememe). `pcb-layout` Faz 4-5 (routing + DRC) bunu tüketir.
- **bom_lifecycle_koprusu.py** — Nexar/Octopart tipi lifecycle/stok/fiyat
  sorgusu (AĞ GEREKİR, bu ortamda placeholder), risk skoru
  (lifecycle+stok+single-source+lead-time), pin-uyumlu alternatif filtreleme
  (aynı paket YETMEZ — pinout + elektriksel param datasheet'ten doğrulanmalı).
  MASTER_RULEBOOK Faz 1'in kod karşılığı.
- **mekanik_dxf_koprusu.py** — DXF/STEP board outline + birim/orijin çapa
  kontrolü, 3D keepout (bölge-bazlı `max_allowed_height_mm`, düz olmayan kutu
  tavanı için STEP tavan haritası), stereo/optik IPD tolerans zinciri
  (worst-case veya RSS). `pcb-layout` Faz 3 placement bariyerinin girdisi.
  **Görev tanımına eklenen (`TASARIM_AKISI.md` Adım 8):** mekanik Bounding Box
  çarpışma kontrolünün YANINA bir "Termal Keepout Zone" mantığı — ısınan
  çiplerin çevresinde sanal bir termal yarıçap, hassas/analog komponentlerin
  (osilatör, referans IC) bu yarıçapa girmesini engeller. **HENÜZ
  UYGULANMADI** — bu sadece görev tanımıdır, kod bu oturumda yazılmadı.
- **ecad_mcad_termal_kopru.py** — MASTER_RULEBOOK **Faz 4b**'nin kod karşılığı:
  kasayı sadece 3D keepout TEHDİDİ değil, ısıl TEMAS HEDEFİ olarak da ele alır.
  `soguturucu_yuzey_bul()` (STEP'ten türetilmiş heatsink boss),
  `termal_yonetim_ve_mask_kontrolu()` (mevcut `pcb_stackup_planner.
  termal_yonetim_kontrolu()`'nu ÇAĞIRIP genişletir — B.Mask açıklığı + ENIG
  zorunluluğu), `termal_ped_kalinligi_hesapla()`,
  `termal_bariyer_gerekli_mi()`/`edge_cuts_yarigi_oner()` (mekanik web
  yetmiyorsa KASITLI `None` → `NEEDS_HUMAN`). **Kasa STEP verisi yoksa bu
  modül tamamen atlanır — hiçbir fonksiyonu hata fırlatmaz.**
- **kuvvet_yonelimli_yerlesim.py** — `pcb-layout` **Aşama 3.0**'ın (ratsnest
  bazlı gruplama) kod karşılığı: netlist'ten ağırlıklı graf (`netlistten_graf_kur`
  — GND/güç netleri DÜZLEM oldukları için grafiğe GİRMEZ), deterministik
  başlangıç (altın-açı spirali, `random` YOK), çekim/itme + `_cakismalari_ayir()`
  ayırma geçişi, `kumeleri_bul()`. Çıktı bir **TOHUM** yerleşimdir:
  `cakisma_kontrolu()` ve `kisitlari_dogrula()` (Aşama 3.3/3.5 mm kuralları)
  sert kapı olarak ayrıca koşar, `z_kontrolu_yap()` yine ZORUNLU.
- **ngspice_koprusu.py** — MASTER_RULEBOOK Faz 3'ün `TEST/simulasyon_raporu.md`
  zorunluluğunun arkasına gerçek çözücü koyar: `spice_netlist_uret()` (kicad-cli),
  `ngspice_calistir()`, `cikti_ayristir()`, `voltaj_dususu_dogrula()`,
  `ac_bant_dogrula()`, `simulasyon_raporu_yaz()` (model türü DAVRANISSAL ise
  "neyi yansıtmadığı" notu ZORUNLU). **Windows:** `ngspice.exe` interaktif yapı
  olduğu için donar — `ngspice_con.exe` kullanılır (`NGSPICE_ADAYLARI`).
  ngspice yoksa sonuç UYDURULMAZ, `KAPSAM_YOK` döner.
- **topolojik_router_koprusu.py** — CLAUDE.md'nin "Otonom Yol Bulma"
  merdiveninin kod karşılığı: `akilli_yol_bul()` DOGRUDAN -> L_DONUSU ->
  U_DONUSU (waypoint) -> KATMAN_DEGISIMI sırasını dener; yüksek hızlı netlerde
  via basamağını ATLAR (Faz 4 Öncelik 2) ve alt katman engel listesi
  verilmemişse "boş" VARSAYMAZ. `koseleri_45_dereceye_cevir()` (Faz 7),
  `itip_kaydir_oner()` (tek adım Push&Shove; kilitli iz/kaskad shove YOK ->
  `NEEDS_HUMAN`), `routing_plan_satiri_uret()` Aşama 3.7 raporunu besler.
  KiCad'in kendi PNS router'ı Python'a dışa AKTARILMAMIŞTIR — `TopolojikRouter`
  onu çağırmaz, üretilen geometriyi `pcbnew` ile yazar (bu ortamda pcbnew yok).
- **cad_api_koprusu.py** — LCSC'de OLMAYAN parçalar için SnapEDA/Nexar'dan
  `.kicad_sym`/`.kicad_mod`/`.step` edinme köprüsü. Asıl değeri iki SERT KAPI:
  `indirmeden_once_lifecycle_kapisi()` (Bölüm 0: NRND/EOL/Obsolete indirilemez,
  prototip dahil) ve `pin_sayisi_dogrula()` (Faz 1: sembol↔datasheet VE
  footprint↔sembol pad sayısı — exposed pad dahil). `kutuphaneye_kaydet()`
  pin kapısı geçilmeden çalışmaz; lib-table kaydı idempotenttir. Token yoksa
  URL/dosya UYDURULMAZ (`kaynak="TBD"`), indirme host beyaz listesiyle sınırlı.
- **hata_hafizasi.py** — ERC/DRC/DFM hataları için kalıcı, Obsidian uyumlu
  Markdown öğrenme hafızası (`HAFIZA/Hata_Hafizasi.md`). İmza (koordinat/
  refdes/sayı normalize edilmiş hash) + Jaccard sözcüksel benzerlikle
  arama yapar — vektör-gömme RAG DEĞİLDİR, öyle sunulmaz.
  `hafizaya_ogret()` DRC/ERC JSON raporundan otomatik kayıt üretir (aynı
  sınıf ihlal TEKİLLEŞTİRİLİR); **BAŞARISIZ denemeler de kaydedilir** ve
  `cozum_oner()` bunları ASLA öneri olarak sunmaz, "denemeyin" listesi
  olarak döner. `onceki_cozumleri_rapora_dok()` yeni bir DRC raporunu
  hafızayla eşleştirip "geçen sefer nasıl çözmüştük" özetini üretir —
  `pcb-layout` Faz 5 döngüsüne girmeden ÖNCE okunmalı.
- **gerber_dfm_gorsel_koprusu.py** — GERÇEK export edilmiş Gerber
  (`.gtl`/`.gts`, RS-274X) dosyalarını ayrıştırıp (aperture + flash +
  çizim) vektörel bir DFM ön-denetimi yapar: `maske_baraji_taramasi()`
  (solder mask dam — farklı netlere ait maske açıklıkları arası boşluk)
  ve `bakir_bosluk_taramasi()`. `pcb_highspeed_escape.py::maske_baraji_kontrolu()`
  ile AYNI riski, SOYUT kanal listesi yerine GERÇEK export koordinatından
  doğrular. Bu makinede gerçek `ESP32C3_SmartBand` Gerber çıktısına karşı
  test edildi (63 maske + 17 bakır boşluk ihlali bulundu — gerçek bulgu).
- **mcad_carpisma_koprusu.py** — `mekanik_dxf_koprusu.py::z_kontrolu_yap()`nin
  TEK düzlem eşiğinin ötesinde, her komponentin GERÇEK 3D kutusunu (yerleşim +
  rotasyon + katman, `.kicad_pcb`'den `kicad_pcb_yerlesimlerini_cikar()` ile
  — gerçek 43 footprint'lik dosyada doğrulandı) kasanın gerçek engel
  hacimleriyle (`KasaEngelHacmi`) 3D AABB çakışması olarak test eder —
  "J1 konnektörü kapağa çarpıyor" tarzı isimlendirilmiş rapor üretir.
  `step_disa_aktar()` (`kicad-cli pcb export step`) bu makinede GERÇEKTEN
  koşturuldu (25s, 2.58MB STEP). **Sınır:** STEP B-rep içeriği (gerçek
  komponent gövde geometrisi) bu ortamda `cadquery` olmadığı için
  ayrıştırılmıyor — `KomponentGovdesi3D` dışarıdan sağlanmalı.
- **kicad_koprusu.py içindeki DFT + referans düzlemi eklentileri** —
  `check_reference_plane_continuity()` (yüksek hız hattı split/void
  üzerinden geçmemeli — standart DRC bunu yakalamaz), `insert_test_points()` +
  `generate_bringup_checklist()` (güç+debug TP kapsamı, rail enable sırası;
  çıktı artık checkbox + "Ölçülen" hücreli bir TABLO — Obsidian'da
  laboratuvarda doldurulup `DOCS/07_Dogrulama/`'ya bağlanan CANLI bir test
  kaydına dönüşür, bkz. `OBSIDIAN_VAULT.md`).
- **degisiklik_gunlugu_uret.py** — `git log`'dan Obsidian uyumlu
  `Changelog.md` üretir (idempotent — her koşuda git geçmişinden BAŞTAN
  üretilir, elle append edilmez). `yol_filtresi` ile bu repodaki tek bir
  proje klasörünün günlüğü diğerlerinden ayrılabilir. Gerçek bu repoya
  karşı test edildi. Otomatik bir git hook'una BAĞLANMADI — commit
  disiplininin bir parçası olarak elle/komutla çalıştırılması önerilir.
- **HAFIZA/Hafiza_Defteri.md** — proje-ötesi, serbest-metin mühendislik
  dersleri günlüğü (CLAUDE.md otonom akış adım 1'de okunur, adım 6'da
  güncellenir). `HAFIZA/Hata_Hafizasi.md` (`hata_hafizasi.py`'nin
  yapılandırılmış DRC/ERC imza veritabanı) ile KARIŞTIRILMAMALI — ikisi
  farklı amaçlara hizmet eder, dosyaların kendi başlıklarındaki bilgi
  kutusuna bakın.
- **IPC standart zinciri (`ipc2152_hesaplayici.py` → `ipc2221_clearance_hesaplayici.py`
  → `ipc6012_dfm_motoru.py` → `ipc_dru_koprusu.py`)** — `DOCS/03_Design_Rules.md`
  bölüm 4-4d'nin kod karşılığı:
  - `ipc2152_hesaplayici.py`: `pcb_stackup_planner.iz_genisligi_hesapla_mm()`'i
    ÇEKİRDEK olarak kullanır (tek kaynak gerçeklik), iç katman için
    belgelenen bir derating katsayısı (`>= 1.0` zorunlu) uygular.
  - `ipc2221_clearance_hesaplayici.py`: iç/dış katman × kaplamalı/kaplamasız
    clearance+creepage, her tablo noktası kendi güven seviyesini
    (`Guven` enum'u) taşır — mevcut `pcb_stackup_planner.IPC2221_HARICI_MESAFE_TABLOSU_MM`
    ile ortak noktalarda BİREBİR aynı (sessiz sapma yok, öz-test kanıtlı).
  - `ipc6012_dfm_motoru.py`: annular ring/solder mask barajı/aspect ratio,
    `bulgu_sozlesmesi.Bulgu` ile PASS/FAIL/**KAPSAM_YOK**.
  - `ipc_dru_koprusu.py`: `kural_dosyasi_olustur()` — bu projede
    AMPİRİK OLARAK keşfedilmiş üç sessiz KiCad 10 `.kicad_dru` tuzağını
    (zorunlu `(version 1)` başlığı, geçersiz `(priority)` token'ı, `#`
    vs `;` yorum karakteri) YAPISAL OLARAK imkânsız kılar; `track_width`/
    `clearance`/`annular_width` constraint'lerinin GERÇEKTEN uygulandığı
    (parse değil, gerçek DRC ihlali ürettiği) bu makinede
    `ESP32C3_SmartBand.kicad_pcb`'ye karşı doğrulandı (dosya sahibinin
    orijinal `.kicad_dru`'su yedeklenip bit-bit aynı geri yüklendi).

## Otonom Yol Bulma (Pathfinding) — pes etmeden ÖNCE denenecekler
İki pin arasındaki Manhattan mesafesi çok uzunsa veya arada engel varsa hemen
DRC hatası verip pes etme. Önce engelin etrafından dolanacak (waypoints) veya
uygunsa alt katmana via ile inip geçecek ara koordinatlar (L veya U dönüşleri)
hesapla. Akıllı yollar dene.

Bu, aşağıdaki "Ne zaman dur" listesinin ÖNKOŞULUdur: "çizilemedi" diyerek
kullanıcıya dönmek ya da bir ihlali kabullenmek, ancak şu üç denemenin
hepsi tükendikten sonra meşrudur:
1. **Doğrudan / L dönüşü** — tek 90°(→45° fillet) kırılmayla aynı katmanda.
2. **Waypoint'li dolanma (U dönüşü)** — engelin (pad, keepout, mevcut iz,
   yüksek hızlı bölge) bounding box'ı etrafından hesaplanmış ara
   koordinatlarla; `pcb-layout` Faz 3.4'teki "Yüksek Hızlı Bölge" ve
   `mekanik_dxf_koprusu.py` keepout'ları engel listesine DAHİL edilir.
3. **Katman değişimi** — via ile alt/uygun katmana inip geçmek; ama
   MASTER_RULEBOOK Faz 6 gereği yüksek hızlı/kritik sinyallerde via
   YASAK (Faz 4 Öncelik 2), o netlerde bu üçüncü seçenek atlanır ve
   bunun yerine yerleşime (Faz 3) geri dönülür.

Üçü de tükenirse sorun routing değil YERLEŞİMDİR — `pcb-layout` Faz 5'in
"Sonsuz Döngü Kaçış Kuralı"na göre Faz 3'e dönülür; ancak o da 3 kez aynı
sonucu verirse `NEEDS_HUMAN`.

## 🚨 TAM OTONOM KURTARMA MEKANİZMASI — araç çökmesi bir "dur" nedeni DEĞİLDİR

**Bu proje "Karanlık Fabrika" (tam otonom) hedefiyle çalışır: canlı bir
routing aracının (MCP/`pcbnew`) çökmesi (segfault, timeout, "Python process
for KiCAD scripting is not running" — bu proje bunu GERÇEKTEN yaşadı, bkz.
`HAFIZA/Hafiza_Defteri.md` 2026-07-31 kaydı) kullanıcıdan "sen çiz" diye
BEKLEMEK İÇİN bir gerekçe DEĞİLDİR.** Bir araç çöktüğünde, elle S-expr
düzenlemeye geçmeden ÖNCE `otonom_kurtarma_motoru.py::
otonom_routing_merdiveni()` çağrılır — bu, ÜÇ otomatik kurtarma katmanını
sırayla dener, HER katmanın board'a yazma adımını da `izole_calistir()`
(subprocess sandboxing) ile İZOLE eder (bir alt süreç segfault/hang olsa
bile ana oturum/ajan AYAKTA kalır):
1. `topolojik_router_koprusu.py::akilli_yol_bul()` (DOGRUDAN/L/U/KATMAN_DEGISIMI).
2. `otonom_kurtarma_motoru.py::bolumlu_yol_dene()` — uzun rota ~5mm'lik
   parçalara bölünüp HER PARÇA ayrı çözülür (tek parça çözülemezse TÜM
   sonuç BULUNAMADI — kısmi yol YAZILMAZ).
3. `otonom_python_router.py::izgara_a_yildiz_ara()` — SON ÇARE, kapsamlı
   ızgara tabanlı A* arama (YAVAŞ ama İNATÇI); bulunan yol SADECE düz
   `pcbnew.PCB_TRACK` segmentleri olarak yazılır (KiCad'in `route_trace`/
   PNS router çekirdeği KULLANILMAZ).

**Elle `.kicad_pcb` S-expr düzenleme** (bu oturumda U2 pin5/pin12 için
yapıldığı gibi) ARTIK sadece şu İKİ durumda meşrudur: (a) yukarıdaki üç
katman da (`MerdivenSonucu.basarili=False`) tükendiyse, (b) düzeltme zaten
MEVCUT bir izin küçük bir clearance ayarı ise (yeni bir uzun-mesafe rota
DEĞİL) — büyük/yeni bir routing görevi için İLK tercih HER ZAMAN
`otonom_routing_merdiveni()`'dir.

**"Araç çöktü" (yukarıdaki mekanizma devreye girer, otomatik) ile "aynı
DRC ihlali 3 kez tekrarlıyor" (aşağıdaki `NEEDS_HUMAN` — gerçek mühendislik
kararı gerektirir) AYRI kavramlardır** — biri ARAÇ GÜVENİLİRLİĞİ sorunu
(kod kendi kendine çözer), diğeri YERLEŞİM/TASARIM sorunu (insan kararı
gerektirir). Sadece ikincisi aşağıdaki "Ne zaman dur" listesine girer.

## Ne zaman dur ve kullanıcıya sor
- Faz 0'da gereksinim gerçekten belirsizse (hedef kullanım senaryosu,
  güç kaynağı tipi, form-faktör/kasa kısıtı hiç verilmemişse).
- Bir parça hem stoksuz/Obsolete hem de pin-uyumlu bir yedeği yoksa.
- Aynı DRC hatası, kaçış stratejisinden (adım 5) sonra da 2 kez daha
  tekrarlıyorsa — bu muhtemelen mimari/yerleşim kaynaklı bir sorundur,
  körü körüne üçüncü bir routing denemesi yapılmaz.
- **Genel feedback-döngü sayacı (sadece DRC değil):** BOM→stackup (alternatif
  footprint değiştiriyor), escape→routing (maske barajı ihlali), DFM→stackup
  (empedans izi fab min altında) gibi HERHANGİ bir feedback kenarı 3 kez
  aynı sonucu verirse `NEEDS_HUMAN` — döngü kör körüne sürdürülmez.
- **Routing öncesi topoloji raporu (`pcb-layout` Aşama 3.7):**
  `TEST/routing_plan.md` üretildikten sonra kullanıcı onayı BEKLENİR —
  onaysız tek bir iz bile çizilmez.
- `design-checker` skill'i FAIL raporu verirse — kullanıcıya bulguları
  özetleyip ilgili faza dönmeden önce onay alınır.
- `DATASHEETS/` klasöründe resmi datasheet hiçbir kaynakta bulunamıyorsa.

Bunların dışında onay beklemeden, kullanıcıya her fazın sonunda kısa bir
özet vererek zinciri kendiliğinden ilerlet.

## Durum Çözücü Kalıcı Kuralları (2026-07-31, `DOCS/PROMPT_DURUM_COZUCU.md`)

Bir araç/ajan bir durumu ("takıldı", "dondu", "sessizce geçti") yanlış/eksik
raporladığında `DOCS/PROMPT_DURUM_COZUCU.md`'deki 5 adımı UYGULA. İlk
uygulamadan (FreeRouting StackOverflowError/GUI-popup olayı, bkz.
`DOCS/13_Durum_Cozucu_FreeRouting_Olayi.md`) çıkan, HER YENİ subprocess
entegrasyonunda geçerli kalıcı kurallar:

- HER harici Java/JVM subprocess çağrısı `-Djava.awt.headless=true`
  İÇERMEK ZORUNDADIR.
- HER uzun-çalışan subprocess çağrısı gerçek zamanlı çıktı taraması + hata
  deseninde fail-fast `kill()` YAPMALI — SADECE `subprocess.run(timeout=...)`'a
  güvenip sonucun kendiliğinden bitmesini beklemek YETERSİZDİR (çocuk süreç/
  pencere SIGTERM'e dirençli olabilir, bkz. DOCS/13 ADIM 1 ölçümü).
- Zaman aşımı ile "araç gerçekten çöktü" (crash/exception) İKİ AYRI sonuç
  alanı olarak raporlanmalı (`zaman_asimi_mi` / `java_hatasi_mi` gibi) —
  ikisini TEK bir "başarısız" bayrağında birleştirmek kök neden analizini
  gizler.
- HER hata/FAIL çıktısı üç öğe içermeli: NE oldu (seviye+kapı+nesne), NEDEN
  (kök neden tek cümle), NASIL ÇÖZÜLÜR (1-2 somut adım) — "anlaşılmaz hata
  mesajı" tek başına kabul edilebilir bir çıktı DEĞİLDİR.
- Konsol çıktısı Windows'ta bozuk görünüyorsa (encoding) bunu "takılma" SANMA
  — önce `sys.stdout`/log encoding'ini kontrol et.
- **`PCB_VIA.GetWidth()` HİÇBİR ZAMAN katman argümanı olmadan çağrılmaz**
  (2026-08-03, bkz. `DOCS/10_Otonomluk_Engel_Raporu.md` D1.6) — KiCad 10'da
  bu bir debug assert (GUI pop-up, headless süreci kilitler) fırlatır.
  `board.GetTracks()` üzerinde gezinen HER yeni kod, `.GetWidth()` çağırmadan
  önce ya listeyi `GetClass() == "PCB_TRACK"` ile via'lardan ARINDIRMALI, ya
  da via'lar için `item.GetWidth(item.TopLayer())` (veya bağlama uygun başka
  bir katman) kullanmalı.
