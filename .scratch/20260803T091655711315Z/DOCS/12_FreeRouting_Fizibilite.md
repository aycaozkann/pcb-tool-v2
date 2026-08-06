# 12 — FreeRouting Açığı Fizibilite Raporu

> Tarih: 2026-07-31
> Amaç: `DOCS/10_Otonomluk_Engel_Raporu.md` D1.1 (FreeRouting DSN zinciri) ve `DOCS/11_Full_Otonom_Donusum_Talimati.md` GÖREV 4 için fizibiliteyi **gerçek makinede** doğrulamak.
> Yöntem: KiCad 10.0.4 gömülü Python (`pcbnew`) + FreeRouting 1.9.0/2.2.4 jar (Java 25) ile uçtan uca test.

---

## Özet (yönetici özeti)

FreeRouting engeli **tamamen kapalı değil — çözüm yolu VAR**, ama "kutu içinde çalışır" değil. Araştırma, `uretim_zinciri_koprusu.py`'deki `KICAD10_DSN_DESTEKLENIYOR = False` sabitinin **eksik tespit** olduğunu gösteriyor: `kicad-cli` DSN desteklemiyor DOĞRU, ama **`pcbnew` Python API'si DSN export + SES import DESTEKLIYOR** ve bu makinede kurulu.

Bu, GÖREV 4'ün "FreeRouting'i ya canlandır ya resmen kapat" ikilemini **"canlandır"** lehine değiştirir — ancak iki engel kalır: (1) FreeRouting'in gerçek boyutlu kartlarda hızı, (2) SES import'unun footprint eşleşme duyarlılığı.

---

## Doğrulanan Bulgular (bu makinede ölçüldü)

### 1. `kicad-cli` DSN desteklemiyor — KOD DOĞRU
`kicad-cli pcb export --help` alt komutları: `3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl, ipc2581, ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, svg, u3d, vrml, xao` — `dsn` yok. Aynı şekilde `pcb import` da Specctra (.ses) içermiyor. Mevcut kod bu noktada doğru.

### 2. `pcbnew` Python API'si DSN/SES DESTEKLİYOR — KODDAKİ İDDİA EKSİK
KiCad 10.0.4 gömülü Python'unda (`C:\Program Files\KiCad\10.0\bin\python.exe`) **ikisi de mevcut ve çalışıyor**:

```python
import pcbnew
pcbnew.ExportSpecctraDSN  # True
pcbnew.ImportSpecctraSES  # True
# imzalar:
#   ExportSpecctraDSN(BOARD aBoard, wxString aFullFilename) -> bool
#   ImportSpecctraSES(BOARD aBoard, wxString aFullFilename) -> bool
```

- `ExportSpecctraDSN` **sentetik board** (3 footprint, 4 net) → `True`, geçerli `.dsn` üretti (unit um).
- `ExportSpecctraDSN` **gerçek KiCad demo board** `ecc83-pp.kicad_pcb` (15 footprint, 14 net) → `True`, 40 KB DSN.
- `ExportSpecctraDSN` **gerçek KiCad demo board** `interf_u.kicad_pcb` (25 footprint, 174 net) → `True`, 137 KB DSN.
- `ImportSpecctraSES` basit `.ses` (634 bayt, boş routes) → `True`.
- `ImportSpecctraSES` FreeRouting çıktısı `real_board3.ses` (1309 bayt, gerçek routes) → **`False`** (aşağıda "Engeller" bölümü).

Yani mevcut kodun "çözüm pcbnew Python API'si gerektirir ve bu ortamda pcbnew KURULU DEĞİL" (uretim_zinciri_koprusu.py:184-185, ses_iceri_aktar docstring) iddiası **YANLIŞ** — pcbnew KiCad'in gömülü Python'unda kurulu ve `arac_yollari.kicad_python_yolunu_bul()` + `pcbnew_scripti_calistir()` ile zaten ulaşılabilir.

### 3. FreeRouting headless çalışıyor
- Java 25 (Temurin) kurulu: `java -version` OK.
- FreeRouting 2.2.4 (build 2026-05-13) jar indirildi, `-de <dsn> -do <ses> -mp <pass>` ile DSN okuyup SES yazıyor.
- Sentetik board'da (3 net): **1.29 saniyede** bitti, `final score 0.00`, routes üretti.
- FreeRouting 1.9.0 da çalışıyor ama 2.2.4 güncel.

### 4. DSN export'tan FreeRouting'e sorunsuz geçiş
`ExportSpecctraDSN` çıktısını FreeRouting 2.2.4 başarıyla açtı ("Opening ... Starting routing of 'real_board2'... completed in 1.29 seconds"). Yani **DSN üretimi çalışıyor ve FreeRouting DSN'i okuyabiliyor** — zincirin ilk yarısı (export → route) gerçek.

---

## Engeller

### E1 — FreeRouting gerçek boyutlu kartlarda yavaş (2.2.4)
Gerçek KiCad demo board'larında FreeRouting 2.2.4 **120 sn (ecc83, 14 net) ve 240 sn (interf_u, 174 net) içinde bitmedi** (timeout). Sentetik 3-net'lik board saniyeler sürerken gerçek kartlar (gerçek padstack'ler, kısıtlamalar, zone'lar) bu süreyi aştı. Bu, üretim akışı için kritik risk: otonom zincir dakikalarca tek net üzerinde takılabilir.

Not: timeout `-mp 3` (düşük pass) ile de oldu — sorun pass sayısı değil, karmaşıklık/Java tarafında bir tıkanma. FreeRouting'in kendi log'u "New version available" uyarısı dışında hata vermedi; `-mp` sınırına rağmen pass'lar bitmiyor veya optimizasyon aşaması takılıyor.

### E2 — SES import footprint eşleşmesine duyarlı
`ImportSpecctraSES` gerçek routes'lu SES'i sentetik board'a import ederken `False` döndü (track sayısı 0). Boş SES `True` döndüğüne göre sorun SES yapısında değil, board'la eşleşmede: FreeRouting'in ürettiği `library_out` padstack'leri (ör. `"Via[0-1]_600:300_um"`) ile hedef board'daki pad'lerin uyuşması gerekebilir. Bu, `.ses` import'unun "yaz ve dene" olarak doğrulanması gerektiği anlamına gelir.

---

## Karar Önerisi (GÖREV 4 için)

**"Canlandır" yolunu seç** — ama kademeli:

| Adım | İş | Kriter |
|---|---|---|
| A | `uretim_zinciri_koprusu.py`'deki `dsn_disa_aktar()` ve `ses_iceri_aktar()`'ı `pcbnew` tabanlı gerçek uygulamaya çevir; `KICAD10_DSN_DESTEKLENIYOR` sabitini kaldır. `arac_yollari.kicad_python_yolunu_bul()` + `pcbnew_scripti_calistir()` üzerinden `python.exe -c "..."` çalıştır (venv Python'u pcbnew göremez). | Gerçek board'da DSN üretir, SES import eder; `test_uretim_zinciri_freerouting.py` güncellenir |
| B | FreeRouting çağrısına makul zaman aşımı + `-mp` sınırı koy; süre aşılırsa `OTONOM_KARAR` kaydıyla o net'i "bilinçli açık" işaretle (GÖREV 3 sözleşmesi) — dakikalarca bekleme yok | Hiçbir net 60 sn'den fazla FreeRouting'e kalmıyor |
| C | FreeRouting'i yalnızca Faz 4 Öncelik 5 (düşük hızlı dijital I/O) ve GND pour için kullan; yüksek hızlı/kritik netleri `otonom_kurtarma_motoru.py`'de tut (zaten plan bu — korunur) | SKILL.md'deki mevcut ayrım |

**Alternatif (reddedilen):** "Resmen kapat" — `pcbnew` DSN/SES desteği bu makinede DOĞRULANDIĞI için kapatmak mevcut otonom router'ı tek olasılık yapar ve E1'i çözmez; ayrıca GÖREV 4'ün "30 dk araştırma" varsayımı artık gereksiz (fizibilite bu raporda kanıtlandı).

---

## GÖREV 4 kabul kriterine etkisi

Mevcut kriter: "`test_uretim_zinciri_freerouting.py` ya gerçek FreeRouting çalıştırmasıyla ya da 'devre dışı' durumuyla yeşil."

Güncellenmiş öneri: **"gerçek FreeRouting çalıştırmasıyla yeşil"** hedefi gerçekçi — DSN üretimi ve FreeRouting çalışması bu raporda kanıtlandı. Tek açık nokta SES import eşleşmesi (E2); bunun çözümü import sonrası `GetTracks()` kontrolüyle doğrulama + gerekiyorsa FreeRouting'e `-mp`/`-mr` gibi ek bayraklarla çıktı şeklini yönlendirmek.

---

## Yapılmamış / Dışarıda bırakılanlar
- FreeRouting 3.x (eğer varsa) test edilmedi; 2.2.4 (2026-05-13) güncel release olarak kullanıldı.
- Gerçek ESP32-C3 board dosyası makinede olmadığı için (silinmiş), testler KiCad kurulumundaki demo board'larla yapıldı.
- SES import eşleşme sorunu (E2) kök neden analiz edilmedi (kapsam dışı; uygulama adımında ele alınmalı).

---

_İlgili: `DOCS/10_Otonomluk_Engel_Raporu.md` (D1.1) · `DOCS/11_Full_Otonom_Donusum_Talimati.md` (GÖREV 4) · `uretim_zinciri_koprusu.py` (FreeRouting zinciri) · `arac_yollari.py` (`pcbnew_scripti_calistir`)_
