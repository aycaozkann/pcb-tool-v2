---
type: pcb-index
tags:
  - pcb/test
---

# Test / Doğrulama Raporları

Bu klasör, araç tarafından **otomatik üretilen** doğrulama raporlarını içerir.

| Rapor | Üreten | Açıklama |
|-------|--------|----------|
| `routing_plan.md` | `topolojik_router_koprusu.py` | Routing öncesi topoloji planı |
| `simulasyon_raporu.md` | `ngspice_koprusu.py` | SPICE simülasyon sonuçları |
| `pin_karsilastirma.md` | `cad_api_koprusu.py` | Sembol-footprint pin uyumu |
| `checker_raporu.md` | Design-checker | Bağımsız tasarım denetimi |
| `bringup_checklist.md` | `kicad_koprusu.py::generate_bringup_checklist` | Laboratuvar ölçüm listesi |
| `gerber_dfm_raporu.md` | `gerber_dfm_gorsel_koprusu.py` | Gerber DFM görsel denetim |
| `mcad_carpisma_raporu.md` | `mcad_carpisma_koprusu.py` | 3D çarpışma testi |

Her rapor, elle onaylandıktan sonra kanıt olarak `DOCS/07_Dogrulama/` klasörüne taşınır.
