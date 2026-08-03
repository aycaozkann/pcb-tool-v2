# KURULUM.md — Bu Projeyi Yeni Bir Makinede Ayağa Kaldırma

Bu dosya, bu proje BAŞKA BİRİNE/BAŞKA BİR MAKİNEYE taşındığında gereken tüm
kurulumları içerir. `CLAUDE.md`, Faz -1'de (ortam hazırlığı) burada listelenen
her aracı kontrol eder; eksik olanı bulursa aşağıdaki komutu **kullanıcıya
gösterip** kurmasını ister — sessizce atlamaz, sessizce "kurulu varsayıp"
devam da etmez.

> Sıra önemli değil, ama KiCad 10 olmadan hiçbiri (kicad-cli, MCP, kicad-happy)
> çalışmaz — önce onu kur.

---

## 1. KiCad 10
`kicad-cli` (DRC/ERC/netlist için kanonik yöntem) ve `pcbnew`/`kipy` Python
modülü KiCad kurulumuyla gelir.
- **İndir:** https://www.kicad.org/download/
- **Doğrula:**
  ```bash
  kicad-cli --version
  python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"
  ```
- Windows'ta `kicad-cli.exe` PATH'te olmayabilir — tipik konum:
  `C:\Program Files\KiCad\<sürüm>\bin\kicad-cli.exe` (bkz. `kicad_koprusu.py`
  ve `.claude/skills/schematic-design/SKILL.md` Ek-A notu).

## 2. kicad-python (kipy) — canlı KiCad oturumu IPC API'si
```bash
pip install kicad-python
```
KiCad'de: Preferences > Plugins > "Enable API" işaretli olmalı. (KiCad
ekibinin kendi notu: "unstable API" — bkz. `kicad_koprusu.py` bölüm 3.)

## 3. mixelpixx/KiCAD-MCP-Server — GUI-benzeri MCP araçları (`mcp__kicad__*`)
Gereksinimler: Node.js 18+, Python 3.10+ (KiCad'in kendi python'u dahil).
```bash
git clone https://github.com/mixelpixx/KiCAD-MCP-Server.git
cd KiCAD-MCP-Server
npm install
pip3 install -r requirements.txt
npm run build
python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"   # doğrulama
```
Sonra Claude Code/Desktop config dosyana ekle (macOS/Linux:
`~/.config/claude/claude_desktop_config.json`, Windows:
`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "kicad": {
      "command": "node",
      "args": ["/tam/yol/KiCAD-MCP-Server/dist/index.js"],
      "env": { "PYTHONPATH": "/usr/lib/kicad/lib/python3/dist-packages" }
    }
  }
}
```
Detaylı platform notları için repodaki `docs/PLATFORM_GUIDE.md`'ye bak.
**Unutma:** Bu MCP'nin bilinen bazı hataları var (`sync_schematic_to_board`,
`get_net_connections`, `get_schematic_pin_locations`) — kritik netleri her
zaman `kicad-cli` ile bağımsız doğrula (bkz. `kicad_koprusu.py` üst notu).

## 4. kicad-happy — şematik/PCB/Gerber analiz skill paketi (Claude Code plugin)
```
/plugin marketplace add aklofas/kicad-happy
/plugin install kicad-happy@kicad-happy
```
Bağımlılık yok (saf Python 3.10+, KiCad kurulumu bile gerektirmez). Bu repo
onu yeniden tanımlamaz/vendor etmez — plugin marketplace üzerinden
kurulduğunda global olarak (tüm projelerde) kullanılabilir hale gelir.
Sorun yaşarsan repodaki `install-guidance.md`'yi oku (platforma özgü
tuzaklar ve workaround'lar için).

## 5. Circuit-Synth — devrenin Python'da tanımlanması
Zaten `pyproject.toml`'da bağımlılık olarak tanımlı. Sadece:
```bash
uv sync
```
(`uv` kurulu değilse: https://docs.astral.sh/uv/getting-started/installation/)

## 5b. pytest — test suite'i çalıştırmak için (ZORUNLU, geliştirme ortamında)
`pytest`, `dependency-groups.dev` altında tanımlıdır — `uv sync` TEK BAŞINA
onu KURMAZ (dev grupları varsayılan olarak dahil edilmez):
```bash
uv sync --group dev
uv run pytest -q   # tüm test_*.py dosyalarını çalıştırır (20+ dosya)
```
Bu adım atlanırsa `test_*.py` dosyaları bu makinede ÇALIŞTIRILAMAZ (import
hatası) — CLAUDE.md'nin herhangi bir fazında "testler PASS" denmeden önce bu
komutun gerçekten çalıştığı doğrulanmalıdır.

## 6. FreeRouting — otonom routing (headless)
Gereksinim: Java 17+.
```bash
# FreeRouting'in son .jar'ını indir:
# https://github.com/freerouting/freerouting/releases
java -jar freerouting-<sürüm>.jar --help   # doğrulama
```
`uretim_zinciri_koprusu.py::freerouting_zinciri_calistir()` bu jar'ın yolunu
parametre olarak alır.

## 7. JLC2KiCadLib — LCSC parça kodundan otomatik footprint/sembol indirme
```bash
pip install JLC2KiCadLib
```

## 8. KiBot — üretim çıktıları (Gerber/BOM/CPL paketleme)
```bash
pip install kibot
kibot --version   # doğrulama
```

## 9. Git — versiyon kontrolü (ZORUNLU, bu bölüm olmadan proje "kurulu" sayılmaz)
Bu proje ve `.md` dosyaları Git'te (GitHub/GitLab) tutulmalı.
```bash
git init   # zaten yoksa
git lfs install   # üretim çıktıları (gerbers.zip vb.) büyükse
```
`.gitattributes` bu repoda zaten var — KiCad S-Expr dosyalarını (`.kicad_sch/
.kicad_pcb/.kicad_pro`) metin olarak, üretim çıktılarını (`.zip/.gbr/.pdf`)
binary olarak işaretler; diff gürültüsünü önler.

**Commit disiplini:** her revizyon (rev A, rev B, ...) ayrı bir commit/tag
olmalı; `uretim/` klasörü (KiBot çıktısı) scratch'te bırakılmaz, git'e
commit'lenir (`SKILL-orchestrator` "push öncesi son tarama" maddesiyle aynı
disiplin: takip edilen bayat üretilmiş dosyalar yeniden üretilmeden push
edilmemeli).

## 10. Görsel Diff Araçları (opsiyonel ama önerilir)
KiCad dosyaları metin S-Expr olsa da ham diff okunaklı DEĞİLDİR (koordinat
kayması tüm satırı değiştirir). Görsel PCB/şematik diff için:
```bash
pip install kicad-diff
# veya: https://gitlab.com/kicad/code/kicad kaynaklı `kicad-cli sch/pcb
# export svg` çıktılarını iki revizyon için üretip harici bir görsel diff
# aracıyla (ör. ImageMagick `compare`) karşılaştırma script'i kur.
```
`kicad_koprusu.py::pcb_gorseli_disa_aktar()` zaten SVG üretiyor — bu
fonksiyonu iki git revizyonunda çalıştırıp çıktıları karşılaştırmak, PR
review'lerinde "bu değişiklik layout'ta ne değiştirdi" sorusuna hızlı cevap
verir.

## 11. `pcb_gorsel_kesit.py` — Claude'un board'u GERÇEKTEN "görmesi" (ZORUNLU, ajan görme yeteneği için)
`pcb_gorsel_kesit.py` (2026-07-30, ESP32-C3 Smart Band oturumunda —
U2/LGA-14 gibi yoğun pinli parçaların çevresinde koordinat-bazlı "kör"
routing defalarca başarısız olunca eklendi) board'un istenen bir mm
bölgesini gerçek bir PNG'ye çevirir; Claude Code bunu `Read` aracıyla
DOĞRUDAN görebilir — artık sadece koordinat okumak yerine yerleşimi
GÖRSEL olarak da değerlendirebilir. İki dış araç gerekir:

```bash
# poppler (pdftocairo) — PDF'i PNG'ye çevirir
winget install oschwartz10612.Poppler      # Windows
sudo apt install poppler-utils             # Linux
brew install poppler                       # macOS

# svglib + reportlab — SVG'yi PDF'e çevirir (saf Python, native bağımlılık yok)
uv add --dev svglib reportlab pillow
```
Doğrulama:
```bash
uv run --group dev python pcb_gorsel_kesit.py --oztest
uv run --group dev python pcb_gorsel_kesit.py board.kicad_pcb \
    --bolge 1,-5,15,4 --cikti kesit.png --buyutme 2
```
`pdftocairo` PATH'te değilse `arac_yollari.py::pdftocairo_yolunu_bul()`
Windows'ta winget'in `WinGet\Packages\...` klasörünü otomatik tarar;
gerekirse `POPPLER_BIN` ortam değişkeniyle tam yol verilebilir
(`KICAD_CLI` ile aynı desen).

---

## Hızlı toplu doğrulama

### Bash / macOS / Linux
```bash
kicad-cli --version && \
python3 -c "import pcbnew, kipy" && \
node --version && \
java -version && \
python3 -c "import JLC2KiCadLib" 2>&1 | head -1 && \
kibot --version && \
uv --version && \
uv run --group dev pytest --version && \
git --version
```
**Sınırı:** `&&` zinciri İLK başarısız komutta durur — sonraki araçlar hiç
denenmez, tek seferde sadece "en erken eksik olan" görülür.

### PowerShell (Windows) — kabuktan bağımsız, TAM tablo

Windows PowerShell 5.1 `&&` zincirlemeyi DESTEKLEMEZ (yukarıdaki bash
komutu burada çalışmaz) — bu yüzden bash'e denk gelen kontrol ayrı bir
Python betiği (`ortam_on_kontrol.py`) olarak yazıldı. Tek komutta HEM
bash'te HEM PowerShell'de AYNI şekilde çalışır ve bash zincirinin
aksine **tek bir eksik araç diğerlerinin kontrol edilmesini engellemez**
— tüm araçlar denenir, tam tablo tek seferde görünür:

```powershell
uv run python ortam_on_kontrol.py --tam
```

Örnek çıktı (bu makinede gerçekten koşturuldu):
```
PASS KiCad CLI: C:\Program Files\KiCad\10.0\bin\kicad-cli.exe (10.0.4)
FAIL pcbnew / kipy: ModuleNotFoundError: No module named 'pcbnew' (bkz. KURULUM.md madde 1-2)
PASS Node.js: v24.18.0
PASS Java: openjdk version "25.0.4" 2026-07-21 LTS
FAIL JLC2KiCadLib: ModuleNotFoundError: No module named 'JLC2KiCadLib' (bkz. KURULUM.md madde 7)
FAIL KiBot: 'kibot' bulunamadı (PATH'te değil) (bkz. KURULUM.md madde 8)
PASS uv: uv 0.11.32 (...)
PASS pytest (dev grubu): pytest 9.1.1
PASS git: git version 2.54.0.windows.1
```
Çıkış kodu yalnızca TÜMÜ PASS ise `0`'dır (`$LASTEXITCODE` ile kontrol
edilebilir) — CI/otomasyon için doğrudan kullanılabilir. Her `FAIL`
satırı, o aracın `KURULUM.md`'deki tam kurulum maddesini gösterir; "kurulu
olduğunu varsay" veya "sessizce atla" burada da YASAK.

Herhangi biri FAIL verirse, o maddeye dön ve kur — CLAUDE.md'nin Faz -1'i
bu listeyi izler ve eksik olanı sana bu dosyadaki tam komutla birlikte
söyler.

## Windows: KiCad CLI yolu yapılandırması

`kicad-cli.exe` PATH'te değilse proje onu Windows'taki standart KiCad
kurulumunda otomatik arar. Farklı bir konum veya sürüm kullanmak için kalıcı
ortam değişkeni tanımla:

```powershell
[Environment]::SetEnvironmentVariable(
  "KICAD_CLI",
  "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
  "User"
)
```

Yeni bir terminal açtıktan sonra gerçek araçla ön kontrolü çalıştır:

```powershell
uv run python ortam_on_kontrol.py
```

Geçici yol gerektiğinde `--kicad-cli` parametresi kullanılır; bu değer
`KICAD_CLI` ortam değişkeninden önceliklidir:

```powershell
uv run python ortam_on_kontrol.py --kicad-cli "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
```
