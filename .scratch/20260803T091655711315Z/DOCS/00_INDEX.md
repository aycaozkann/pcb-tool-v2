# 🧭 DOCS — Proje Dokümantasyon Haritası

Bu klasör, projeyi "dağınık not defteri"nden kurumsal bir donanım tasarım
şablonuna taşımak için var. **İçerik burada TEKRAR YAZILMADI** — her dosya,
zaten var olan `MASTER_RULEBOOK.md` / `TASARIM_AKISI.md` / `.claude/skills/`
içeriğine referans veren, PROJE-ÖZEL doldurulacak bir şablondur. Amaç: bir
donanım mühendisinin/müşterinin/üreticinin ilk baktığında "bu profesyonel bir
tasarım paketi" diyeceği bir dosya sırası + her adımın kanıtının nerede
olduğunun açık olması.

## Okuma/doldurma sırası

| # | Dosya | Ne zaman doldurulur | Kaynak (proje içi) |
|---|-------|----------------------|---------------------|
| 01 | [Design Requirements](01_Design_Requirements.md) | Faz 0 (proje başında) | `MASTER_RULEBOOK.md` Faz 0-1 |
| 02 | [Stackup & Impedance](02_Stackup_and_Impedance.md) | Faz 2 | `pcb_stackup_planner.py`, `empedans_cozucu.py` |
| 03 | [Design Rules](03_Design_Rules.md) | Faz 2 (routing'den önce) | `pcb_stackup_planner.py::FABRIKA_PROFILLERI`, `kicad_koprusu.py::custom_dru_yaz` |
| 04 | [DFM & DFA](04_DFM_and_DFA.md) | Faz 4-8 | `pcbnew_koprusu.py`, `dft-testpoints`/`emi-emc` skill'leri, `uretim_zinciri_koprusu.py` |
| 05 | [Release Checklist](05_Release_Checklist.md) | Üretime göndermeden hemen önce | `MASTER_RULEBOOK.md` Ek: Hızlı Kontrol Listesi + IPC-A-600 |

## İlke: Bu dosyalar KARAR KAYDIDIR, tekrar kural seti DEĞİL

`MASTER_RULEBOOK.md` ve skill dosyaları "genel olarak ne yapılır"ı tanımlar
(proje bağımsız kural seti). `DOCS/` altındaki dosyalar ise **bu projenin
belirli bir revizyonu için** hangi kararın verildiğini, hangi sayının
seçildiğini, hangi kontrolün ne zaman/nasıl çalıştırıldığını kaydeder. Yani:
Rulebook "decoupling ≤1.5mm olmalı" der; `DOCS/02_...md` "bu kartta C14
decoupling'i 1.2mm'de, ölçüldü" der.

Her `DOCS/*.md` dosyasının başında bir `Durum:` satırı olmalı:
`TASLAK` / `İNCELEMEDE` / `ONAYLANDI (rev X, tarih)`. Onaylanmamış bir
dosyaya dayanarak üretime geçilmez (bkz. `05_Release_Checklist.md`).
