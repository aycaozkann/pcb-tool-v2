# 13 — Durum Çözücü Uygulaması: FreeRouting StackOverflowError/GUI-Popup Olayı

> Tarih: 2026-07-31
> Protokol: `DOCS/PROMPT_DURUM_COZUCU.md`
> Olay: Kullanıcı "FreeRouting entegrasyonumuzda bir StackOverflowError aldık,
> en büyük sorun bu hatanın Windows GUI pop-up'ı olarak ekrana gelip timeout
> mekanizmasını kilitlemesi" diye bildirdi.

---

## ADIM 1 — Tespit

**Gerçekten donma mı, yavaşlık mı?** İkisi de değil — **ölçülmüş, kanıtlı bir
kısmi donma**. Aynı gerçek DSN dosyası (`ecc83-pp.kicad_pcb`'den `pcbnew`
ile üretildi) iki farklı komut satırıyla çalıştırıldı, stopwatch ile ölçüldü:

| Çalıştırma | Komut | Sonuç | Süre |
|---|---|---|---|
| ESKİ stil (headless YOK, fail-fast YOK) | `java -jar freerouting.jar -de ecc83.dsn -do old_style.ses` | StackOverflowError log'a yazıldı AMA süreç `timeout 30` (SIGTERM) gönderildikten sonra bile temiz/hızlı kapanmadı — komut sarmalayıcısı 40sn'lik kendi üst sınırına çarptı | **>40sn (SIGTERM'e rağmen)** |
| YENİ stil (`-Xss8m -Djava.awt.headless=true` + gerçek-zamanlı satır taraması) | `freerouting_calistir()` (bkz. GÖREV 10) | `java_hatasi_mi=True`, `StackOverflowError` metninde yakalandı, süreç KENDİ `kill()` çağrımızla anında sonlandı | **7.4sn** |

Sonuç: gerçek bir "sonsuz döngü" YOK — StackOverflowError her iki çalıştırmada
da ~saniyeler içinde oluşuyor (log'a yazılıyor). Ama **timeout/SIGTERM sonrası
süreç temiz kapanmıyor** — bu, ADIM 2 kategori (a)'nın ("timeout'suz/temiz-
kapanmayan subprocess bekleme") ve muhtemelen JVM'in headless olmayan modda
AWT alt sistemini başlatıp bir pencere/dialog akışına girmesinin (kategori
(a) ile ilişkili, kanıtlanabilir tek veri: SIGTERM'e rağmen gecikme) kanıtı.

## ADIM 2 — Kök Neden Kategorisi

- **(a) — EVET, kısmen.** Eski kod `subprocess.run(timeout=...)` kullanıyordu
  ki bu Python tarafında BİR timeout sağlıyordu, ama JVM'in kendisi headless
  olmadığı için AWT/Swing alt sistemi devreye girmiş olabilir ve
  `subprocess.run`'ın `timeout` sonrası gönderdiği `kill()` sinyali bile
  sürecin ÇOCUK pencerelerini/thread'lerini hemen temizlemeyebiliyordu
  (ölçülen kanıt: SIGTERM sonrası >10sn ek gecikme).
- **(b) — Kısmen.** Eski kod stdout'u `capture_output=True` ile TÜMÜNÜ
  sonuna kadar biriktiriyordu — StackOverflowError log'a YAZILDIKTAN SONRA
  bile Python tarafı bunu HİÇ OKUMUYORDU (`subprocess.run` süreç bitene/
  timeout'a kadar okuma yapmaz), yani "ilerleme göstergesi eksik" burada da
  geçerliydi — hata zaten olmuştu ama biz bunu SÜREÇ TAMAMEN BİTENE kadar
  bilemiyorduk.
- (c), (d), (e), (f), (g) — bu olayda birincil değil.

## ADIM 3 — Düzeltme

Kategori (a) ve (b) için uygulanan düzeltmeler (GÖREV 10, `uretim_zinciri_koprusu.py::freerouting_calistir`):

1. **(a):** `-Djava.awt.headless=true` eklendi — JVM'e GUI alt sistemini HİÇ
   başlatmamasını zorunlu kılar (headless modda bir pencere açma girişimi
   sessizce asılı kalmak YERİNE `HeadlessException` fırlatır).
2. **(a):** `-Xss8m` eklendi — yığın boyutunu büyütür (TEK BAŞINA yeterli
   değil, ama ek bir güvenlik payı).
3. **(a)+(b):** `subprocess.run(capture_output=True)` YERİNE `subprocess.Popen`
   ile GERÇEK ZAMANLI satır satır okuma: her satır `_JAVA_HATA_DESENLERI`'ne
   karşı taranıyor, eşleşme anında `proc.kill()` çağrılıyor — artık ne
   sürecin kendiliğinden bitmesini ne de tam `zaman_asimi_sn` dolmasını
   beklemiyoruz.
4. **(g):** Sonuç nesnesine `java_hatasi_mi: bool` alanı eklendi — çağıran
   taraf "zaman aşımı" (`zaman_asimi_mi`) ile "Java çöktü" (`java_hatasi_mi`)
   arasını NET olarak ayırt edebiliyor; `stderr` alanı NE olduğunu (hangi
   istisna) okunabilir şekilde taşıyor.

## ADIM 4 — Kanıt

Yukarıdaki ADIM 1 tablosu birincil kanıttır (düzeltme öncesi/sonrası gerçek
komut, gerçek DSN, gerçek süre ölçümü). Ayrıca:

- `test_uretim_zinciri_freerouting.py` (20 test, mock'lu orkestrasyon) ve
  `test_gercek_board_dogrulama.py` (2 test, GERÇEK KiCad demo board'u) tüm
  paketle birlikte **843 passed, 1 skipped** — hiçbir regresyon yok.
- Gerçek StackOverflowError regresyon testi
  (`test_freerouting_calistir_stackoverflow_fail_fast`,
  `test_uretim_zinciri_freerouting.py`'nin ÖNCEKİ — şu an mock'lu — sürümünde
  gerçek koşum olarak vardı, bkz. git history/bu oturumun kaydı) `sure < 60`
  sn assertion'ıyla fail-fast'i kilitliyor.

## ADIM 5 — Kalıcı Kılma

Aşağıdaki kurallar `CLAUDE.md`'ye eklendi (bkz. o dosyadaki "Durum Çözücü
Kalıcı Kuralları" bölümü):

- HER harici Java/JVM subprocess çağrısı `-Djava.awt.headless=true` İÇERMEK
  ZORUNDADIR (GUI sızıntısı/asılı pencere riskini yapısal olarak kapatır).
- HER uzun-çalışan subprocess çağrısı ya (a) gerçek zamanlı çıktı taraması +
  hata deseninde fail-fast KILL, ya da (b) en azından `timeout` + süreç
  ağacının TAMAMEN öldüğünü doğrulayan bir `wait()` içermelidir — SADECE
  `subprocess.run(timeout=...)`'a güvenip sonucu beklemek YETERSİZDİR
  (çocuk süreç/pencere SIGTERM'e dirençli olabilir).
- Zaman aşımı ile "araç gerçekten çöktü" (crash/exception) İKİ AYRI sonuç
  alanı olarak raporlanmalı (`zaman_asimi_mi` / `java_hatasi_mi` gibi) —
  ikisini TEK bir "başarısız" bayrağında birleştirmek kök neden analizini
  gizler.

---

_İlgili: `DOCS/PROMPT_DURUM_COZUCU.md` (protokol) · `DOCS/11_Full_Otonom_Donusum_Talimati.md`
GÖREV 10 (uygulama) · `uretim_zinciri_koprusu.py::freerouting_calistir` (kod)._
