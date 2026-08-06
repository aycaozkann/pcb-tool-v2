# 01 — Design Requirements

Durum: `TASLAK`

> Bu dosya Faz 0'da (proje başlarken) doldurulur ve tasarım boyunca yaşayan
> bir referans olarak kalır. Kaynak: `MASTER_RULEBOOK.md` Faz -0/Faz 1.
> Burada tanımlanan her sayı, aşağı akıştaki (stackup, DFM, release) kararların
> gerekçesidir — "neden 4 katman" sorusunun cevabı buradaki bir satıra
> dayanmalı, keyfi olmamalı.

## 1. Elektriksel Gereksinimler

| Alan | Değer | Kaynak/Gerekçe |
|---|---|---|
| Besleme gerilimi/kaynağı | *(ör. Li-ion 3.0-4.2V, USB-PD 5V)* | |
| Toplam güç bütçesi (worst-case) | *(W)* — `pcb_stackup_planner.py::guc_isil` hesabına girdi | |
| Kritik rayların ripple/noise toleransı | | |
| Harici arayüzler (USB/Ethernet/MIPI/...) | | Her biri için `empedans_hedefi_getir()`'de bir `AraBirimTuru` karşılığı olmalı |
| EMC hedef standardı + sınıfı | *(ör. CISPR 32 Class B)* | `emi-emc` skill §0 ile aynı disiplin — sınıfı SEN seçmezsin, pazar seçer |

## 2. Mekanik Gereksinimler

| Alan | Değer | Kaynak |
|---|---|---|
| Kart boyutu / form-faktör | | `mekanik_dxf_koprusu.py::import_board_outline` girdisi |
| Kasa/enclosure var mı, STEP dosyası | | `derive_keepouts()` girdisi |
| Konnektör tipleri + sayısı | | `SKILL-konnektor` mating-cycle/akım derating'i etkiler |
| Montaj yöntemi (vida/klips/DIN ray) | | |

## 3. Çevresel/Güvenilirlik Gereksinimleri

| Alan | Değer |
|---|---|
| Çalışma sıcaklık aralığı | *(ör. -20°C ... +85°C — `guc_isil.py`'deki `ambient_c` girdisi budur)* |
| Titreşim/şok sınıfı | *(varsa MLCC flex-crack keepout kararını etkiler)* |
| Nem/IP sınıfı | |
| Hedef ürün ömrü / MTBF | *(BOM lifecycle risk toleransını etkiler — bkz. `bom_lifecycle_koprusu.py`)* |

## 4. Tedarik/Maliyet Kısıtları

| Alan | Değer |
|---|---|
| Hedef fab (JLCPCB/PCBWay/Wurth/...) | → `03_Design_Rules.md`'deki fabrika profiline bağlanır |
| Hedef birim maliyet | |
| Üretim hacmi (proto / küçük seri / seri) | Panelizasyon kararını etkiler (`panelizasyon_kontrolu`) |
| Yasaklı/tercih edilmeyen tedarikçiler | |

## 5. Onay

- [ ] Bu dosyadaki her satır, kullanıcıyla (veya proje sahibiyle) doğrulandı.
- [ ] Belirsiz kalan alan yok, ya da `NEEDS_HUMAN` olarak işaretlendi.
- [ ] Durum `TASLAK`'tan `ONAYLANDI`'ya çekildi ve tarih/rev eklendi.
