# PROMPT: Durum Çözücü (Yanlış/Eksik/Yanıltıcı Durum Raporu Protokolü)

> Kullanım: Bu dosyayı, aracın/ajanın bir durumu yanlış/eksik/yanıltıcı
> raporladığı HER durumda (örn. "takıldı", "dondu", "X yapamadı", "sessizce
> geçti", "hata mesajı anlamsız") tek bir görev tanımı olarak Claude Code'a
> ver. Ajan tüm disiplini TEK SEFERDE uygular ve sonunda kalıcı kural ekler
> — aynı hata türü bir daha sessizce oluşmaz. Adım atlamak YOK.

---

## ADIM 1 — TESPİT (takılma/donma iddiası varsa)

- Gerçekten donma mı yoksa yavaşlık mı? KANITLA: her fazı/alt süreci ayrı
  stopwatch ile ölç (başlangıç+bitiş yazdır), toplam süreyi göster.
- Sonsuz döngü/deadlock/subprocess-bekleme adaylarını listele, zaman
  aşımlarını kontrol et (timeout yoksa bu bir bulgudur).
- "Kullanıcı X saniye bekledi ama iş bitti" ile "gerçekten takıldı"yı ayır.

## ADIM 2 — KÖK NEDEN KATEGORİSİ

Şunlardan HANGİSİ olduğunu açıkça belirt (birden fazla olabilir):

a) gerçek sonsuz döngü / timeout'suz subprocess beklemek
b) yavaş koşu, dakikalarca sessiz çıktı → ilerleme göstergesi eksik
c) fail-closed kapısı sessiz kaldı / sonucunu söylemedi
d) konsol çıktısı bozuk (encoding/UTF-8) → takılma SANILDI
e) yanlış/eksik kullanıcı girdisi → anlamsız veya hiç hata mesajı yok
f) üretim zincirinde fail-open: araç yokken sessizce geçme / yanlış "PASS"
g) kullanıcı "ne yapmalıyım" diye anlamıyor → hata mesajı yetersiz

## ADIM 3 — DÜZELT (bulunan her kategori için zorunlu)

- (a): her subprocess'e belirgin timeout ver, hatayı yakala ve yazdır.
- (b): her fazın bitişini/numarasını ve harcanan süreyi çıktıya ekle.
- (d): konsol çıktısını UTF-8'e çevir (örn. `sys.stdout.reconfigure(encoding="utf-8")`).
- (e): hata mesajından ÖNCE İPUCU ekle — alt klasörde/dosyada arayıp
  bulduğunu kopyala-yapıştır yapılabilir komut olarak öner; birden fazla
  aday varsa hepsini listele, gizlice seçme.
- (c)+(f): "sessiz PASS"/"sessiz atlama" olan her kapıyı fail-closed yap —
  eksik araçta net hata + kurulum komutu (örn. `pip install ...`) +
  KURULUM.md maddesi göster.
- (g): HER HATA/FAIL çıktısı 3 öğe içersin: **NE** oldu (seviye+kapı+nesne:
  net adı, dosya adı, ayak izi), **NEDEN** (kök neden tek cümle), **NASIL
  ÇÖZÜLÜR** (1-2 somut adım).

## ADIM 4 — KANITLA

- Aracı GERÇEK girdilerle (gerçek dosyalar/dizinler) çalıştır; düzeltme
  öncesi ve sonrası çıktıyı/exit kodlarını/süreleri göster.
- Her düzeltme için test yaz (ilgili test dosyasına), mevcut testlerin
  kırılmadığından emin ol, TÜM test suite'ini koştur ve sonucu raporla.

## ADIM 5 — KALICI KIL

- Dersleri ajanın kalıcı talimatlarına işle: `MASTER_RULEBOOK.md`/
  `CLAUDE.md`/ilgili `SKILL.md` dosyasındaki ilgili faza KISA maddeler
  halinde kural ekle (tek paragraf değil), örn. "HER hata çıktısı ne+neden+
  nasıl içerir", "HER subprocess'e timeout", "araç yokken fail-open olmaz".
- İleride regresyon olmasın diye kurala test bağla.
- Sonunda: yapılan değişiklikleri, bulgu kategorilerini ve çıktı örneklerini
  özetle; git commit öner ama **kullanıcı onaylamadan COMMIT ETME**.

---

_Kaynak: kullanıcı tarafından 2026-07-31'de tanımlandı; ilk uygulama:
FreeRouting `java.lang.StackOverflowError` + headless GUI popup olayı
(bkz. `DOCS/11_Full_Otonom_Donusum_Talimati.md` GÖREV 10)._
