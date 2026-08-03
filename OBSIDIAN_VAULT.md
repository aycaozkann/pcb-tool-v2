# Obsidian Vault Kullanımı

Bu proje klasörünü Obsidian'da **Open folder as vault** ile aç. Ayrı bir vault klasörü oluşturma: teknik dokümanlar, kod ve üretim kanıtları aynı proje kökünde kalır.

Başlangıç notu: [[DOCS/00_Dashboard|PCB Tasarım Dashboard]]

## Kaynak gerçeklik

- KiCad dosyaları, DRC/ERC çıktıları, Gerber/BOM/CPL ve kod teknik kaynak gerçekliktir.
- `DOCS/` notları karar, durum ve kanıt indeksidir; araç çıktısının yerine geçmez.
- `MASTER_RULEBOOK.md` ve `TASARIM_AKISI.md` bağlayıcı süreç ve kurallardır.
- `HAFIZA/Hata_Hafizasi.md` ve `HAFIZA/Hafiza_Defteri.md` **yapılandırılmış
  değil, birikimli** kaynaklardır — bir tasarım kararının/kuralının GERÇEK
  gerekçesi hâlâ `MASTER_RULEBOOK.md`'de olmalı; hafıza dosyaları o kararın
  NEREDEN geldiğini anlatır.

## Obsidian workspace ayarları

Projede `.obsidian/` klasörü altında vault ayarları tanımlıdır:

- **app.json** — çizgi numarası, otomatik link güncelleme, Markdown link kullanımı
- **core-plugins.json** — aktif çekirdek eklentiler (Graf, Backlink, Command Palette vb.)
- **community-plugins.json** — önerilen Obsidian Git eklentisi (isteğe bağlı)
- **graph.json** — grafik görünümü ayarları (varsayılan daraltılmış)

`workspace.json` / `workspace-mobile.json` **git'e commit edilmez** — her
makinede yeniden oluşan geçici dosyalardır (`.gitignore`'da zaten dışlandı).

## Bu kasa NEDEN GitHub'a (aycaozkann/Pcb_desing) bağlı

Bu klasör (`pcb-tool-v2/`) aynı zamanda bir git deposudur (`origin`:
`https://github.com/aycaozkann/Pcb_desing`). Obsidian'ın kendisi bir senkron
mekanizması İÇERMEZ — kasadaki her not, tıpkı kod gibi, SADECE `git add` /
`git commit` / `git push` ile GitHub'a taşınır. Yani "pushladıkça oraya
eklensin" isteğinin karşılığı budur: bu klasörde yazılan her `.md` dosyası
zaten normal bir git dosyasıdır, farklı bir mekanizma gerekmez — commit
disiplinine (`KURULUM.md` madde 9) bu notlar da dahildir.

**Obsidian Git eklentisi** (community-plugins.json'da önerilen, isteğe bağlı):
El ile commit/push yapmak yerine belirli aralıklarla otomatik commit+push
yapabilir. Önerilen ayar: "Auto pull on boot" açık, "Auto commit/push"
aralığı en az birkaç dakika (KiCad dosyaları da aynı klasördeyse, çok sık
commit KiCad'in kendi `.lck` dosyalarıyla çakışabilir — bkz.
`sch_wire.py::assert_kicad_closed`).

## Proje-Araç Köprüsü Kuralı

Bu vault sadece `pcb-tool-v2` klasörünü kapsar. Test/gerçek projeler
(ör. `cm4-io-test`) genellikle ayrı bir klasörde, ayrı bir git
deposunda ve dolayısıyla **ayrı bir Obsidian vault'unda** yaşar —
Obsidian vault'lar arası backlink desteklemediği için, bir projede
öğrenilen hiçbir şey bu vault'a otomatik olarak düşmez.

Bu yüzden her proje oturumu sona erdiğinde (başarılı ya da başarısız),
proje klasörünün KENDİSİ ayrı vault'ta kalsa bile, aşağıdaki iki dosya
mutlaka bu vault'un (`pcb-tool-v2/DOCS/`) içine yazılır:

- **Proje özeti:** `DOCS/09_Referans_Tasarimlar/<proje-adi>.md` —
  mevcut `ESP32C3_SmartBand.md` / `SHT35_Breakout.md` ile aynı formatta;
  ne yapıldığı, hangi noktada durulduğu, hangi kararların alındığı.
- **Yeni otonomluk engeli varsa:** `DOCS/10_Otonomluk_Engel_Raporu.md`'ye
  mevcut D1/D2/D3 sınıflandırma formatında eklenir — proje sırasında
  aracın (kodun/kuralın/skill'in) yetersiz kaldığı HER nokta buraya
  girer, sadece proje klasöründeki bir nota değil.

Her iki dosya da `00_Dashboard.md`'den `[[wikilink]]` ile bağlı
tutulur, böylece vault içi graph view'da her proje notunun hangi
karara/engele kaynaklık ettiği görsel olarak izlenebilir.

**Gerekçe:** Aksi halde her yeni proje, bir öncekinde bulunan engelleri/
dersleri sıfırdan tekrar keşfeder — vault'un asıl amacı (kararların
kaybolmaması) proje-tool sınırında delinmiş olur.

## Değişiklik Günlüğü (Changelog.md)

`Changelog.md`, `degisiklik_gunlugu_uret.py` ile git geçmişinden ÜRETİLİR
(elle düzenlenmez — bir sonraki üretimde kaybolur):

```bash
uv run python -c "from degisiklik_gunlugu_uret import changelog_yaz; \
    changelog_yaz('Changelog.md', repo_dizini='.', yol_filtresi='pcb-tool-v2')"
```

Bu proje bunu OTOMATİK bir git hook'una BAĞLAMAZ (hook'lar kullanıcı onayı
gerektiren bir davranış değişikliğidir) — commit disiplininin bir parçası
olarak, anlamlı bir kilometre taşından (ör. bir faz tamamlandığında) sonra
elle/komutla çalıştırılıp commit'e dahil edilmesi önerilir.

## Hafıza (Hata_Hafizasi vs Hafiza_Defteri)

- **[[HAFIZA/Hata_Hafizasi|Hata_Hafizasi.md]]** — `hata_hafizasi.py`
  tarafından YÖNETİLEN, DRC/ERC mesaj imzasıyla eşleşen yapılandırılmış bir
  veritabanı. Elle yazılmaz, `hafizaya_ogret()` ile beslenir.
- **[[HAFIZA/Hafiza_Defteri|Hafiza_Defteri.md]]** — serbest metin, insan/
  Claude tarafından küratörlüğü yapılan mühendislik dersleri günlüğü. Yeni
  bir tasarıma başlamadan ÖNCE okunur; bir tasarım oturumu bitince (veya
  kullanıcı "hafızaya not et" dediğinde) yeni madde eklenir. Kendi
  şablonu dosyanın içinde.

## Bring-up / test dijitalleştirme

`kicad_koprusu.py::generate_bringup_checklist()` artık her güç rayı için
checkbox + "Ölçülen" hücreli bir Markdown TABLOSU üretir. Laboratuvarda bu
dosya doğrudan Obsidian'da (tablet/laptop) açılıp osiloskop/multimetre
ölçümleri tabloya işlenir; tamamlanınca `DOCS/Templates/Dogrulama_Kaydi.md`
şablonuyla `DOCS/07_Dogrulama/`'ya bağlanarak kalıcı test kaydına dönüşür.

## Eklentiler

Dashboard eklentisiz de çalışır. İsteğe bağlı **Dataview**, `#pcb/karar`,
`#pcb/acik` ve `#faz/*` etiketli notlardan otomatik listeler üretir.
**Obsidian Git** yukarıda anlatıldığı gibi isteğe bağlı otomatik push için
kullanılabilir.
