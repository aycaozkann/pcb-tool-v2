---
name: design-checker
description: Bağımsız bir "Denetmen (Checker)" rolüyle, schematic-design ve pcb-layout skill'lerinin (Maker) tamamladığını iddia ettiği bir tasarımı şüpheci bir gözle yeniden denetler — netlist, DRC/ERC logları, BOM ve datasheet'leri Maker'ın vardığı sonuçlara güvenmeden yeniden okur. Maker "işim bitti, 0 hata" dediğinde, üretim çıktılarından (KiBot) ÖNCE çağrılır. Kendi başına bir tasarım üretmez veya düzeltmez — sadece bulgu raporu yazar.
user-invocable: true
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# /design-checker — Bağımsız Denetmen (Red Team) Süreci

## Neden bu skill ayrı
Tek bir ajan hem tasarımı çizip hem kendi çizdiğini "0 hata" diye
onaylıyorsa kör noktalar oluşur — aynı varsayımları, aynı yerde tekrar
yapma eğilimindedir. Bu skill BİLEREK `schematic-design` ve `pcb-layout`
skill'lerinden (yani "Maker") ayrı ve şüpheci bir role sahiptir: Maker'ın
raporlarını (`TEST/*.md`, DRC/ERC JSON çıktıları) veri olarak okur ama
Maker'ın vardığı SONUÇLARA güvenmez — kendi başına yeniden değerlendirir.

## Ne zaman çağrılır
`CLAUDE.md`'deki otonom akışta, `pcb-layout` Faz 5 (DRC/ERC + görsel
denetim) "temiz" raporladıktan SONRA, `uretim_zinciri_koprusu.py::kibot_calistir()`
çağrılmadan ÖNCE. Bu skill "PASS" demeden üretim adımına geçilmez.

## Denetim Adımları

### 1. Netlist ve BOM Çapraz Okuma (Maker'ın özetine değil, ham veriye bak)
- `TEST/netlist_dogrulama.md`'yi OKU ama orada yazan sonucu tekrar etme —
  `kicad-cli sch export netlist` çıktısını (varsa) veya ham `.kicad_sch`/
  `.kicad_pcb` dosyalarını bizzat aç, her gücü/kritik neti kendi başına say.
- BOM'da her satırın MPN'i, footprint'i ve voltaj/tolerans notu (örn.
  "10µF" değil "10µF/16V") dolu mu — MASTER_RULEBOOK Faz 1'in gerektirdiği
  gibi.

### 2. Şeytanın Avukatlığı (Devrik Sorular)
Aşağıdaki gibi sorguları KENDİN üret ve devre üzerinde tek tek doğrula —
Maker'ın raporunda bu sorulara cevap yoksa bunu bir bulgu olarak işaretle:
- "I2C hatlarında pull-up direnci var mı, değeri datasheet aralığında mı?"
- "Bu kapasitörün voltaj değeri, üzerine düşen gerilimin (worst-case,
  MASTER_RULEBOOK Faz 2'deki tolerans zinciri dahil) altında kalıyor mu?"
- "Regülatörün Enable/power-sequencing sırası datasheet'in istediğiyle
  uyumlu mu, yoksa Maker bunu atlamış mı?"
- "DRC/ERC raporunda 'warning' seviyesinde bırakılıp 'error' değil diye
  görmezden gelinen ama aslında önemli bir madde var mı?"

### 3. DRC/ERC/Görsel Denetim Raporlarını Yeniden Değerlendirme
- `kicad_koprusu.py::drc_calistir()` / `erc_calistir()` çıktılarını
  (varsa kaydedilmiş JSON raporlarını) yeniden oku — Maker'ın "temiz"
  dediği rapor gerçekten sıfır `error` seviyeli ihlal mi, yoksa sadece
  `warning`'ler mi göz ardı edilmiş kontrol et.
- `pcb-layout` skill'inin ürettiği `pcb_gorunumu.svg` görselini (varsa)
  bağımsız olarak incele — Maker'ın görsel denetiminde atladığı bir şey
  var mı (özellikle anten/RF bölgesi, ısı üreten/hassas parça yakınlığı).

### 4. Bulgu Raporu (`TEST/checker_raporu.md`)
Şu formatta yaz:
```
## Denetmen Raporu — <tarih>
### Doğrulanan (Maker'ın iddiasıyla uyumlu bulundu)
- ...
### Bulgular (Maker'ın gözden kaçırdığı/eksik bıraktığı)
- [CRITICAL/HIGH/MEDIUM] <bulgu> — <neden önemli>
### Sonuç: PASS | CONDITIONAL PASS | FAIL
```
- **PASS:** Kritik/yüksek önemde bulgu yok — üretim adımına (KiBot) geçilir.
- **CONDITIONAL PASS:** Sadece düşük önemde bulgular var — kullanıcıya
  bildirilir, kullanıcı isterse yine de devam edilebilir.
- **FAIL:** En az bir CRITICAL/HIGH bulgu var — Maker'a (ilgili faza)
  geri dönülür, üretim adımına GEÇİLMEZ.

## Sınır
Bu skill tasarımı DÜZELTMEZ, sadece bulgu raporu üretir. Düzeltme,
`schematic-design`/`pcb-layout` skill'lerinin işidir — Checker'ın
tarafsızlığını korumak için düzeltmeyle karıştırılmaz.
