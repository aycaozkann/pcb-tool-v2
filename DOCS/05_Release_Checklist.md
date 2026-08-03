# 05 — Release Checklist

Durum: `TASLAK`

> Bu, üretime göndermeden HEMEN ÖNCE koşulan son kapıdır.
> `MASTER_RULEBOOK.md`'nin "EK: Hızlı Kontrol Listesi"ni proje-özel kanıtla
> (ekran görüntüsü/rapor dosya yolu/sayı) doldurarak tekilleştirir. Bu
> dosyadaki HERHANGİ bir kutu işaretsizse üretime gönderilmez.

## 1. Elektriksel Doğrulama

- [ ] DRC: 0 hata (`kicad_koprusu.py::drc_temiz_mi()` → rapor yolu: ______)
- [ ] ERC: 0 hata (`erc_temiz_mi()` → rapor yolu: ______)
- [ ] `gercek_board_dogrulama_kapisi()`: `temiz_mi = True` (→ `04_DFM_and_DFA.md` §1)
- [ ] Netlist parity (şematik ↔ PCB) doğrulandı, fark = 0.
- [ ] Tekrarlanan ihlal sayacı (`tekrarlanan_ihlal_tespit_et`) hiçbir noktada
  eşiği (3) aşmadı — aştıysa `NEEDS_HUMAN` olarak çözüldü, sessizce geçilmedi.

## 2. Görsel / Fiziksel Denetim

- [ ] **Silkscreen (ipek baskı) okunaklı mı?** Pad/via üzerine taşan metin
  yok, referans designatorlar (R1, C1, ...) montaj sonrası okunabilir
  konumda. `pcb_gorseli_disa_aktar()` SVG'si üzerinden vision review yapıldı.
- [ ] **3D model çakışması yok mu?** Yüksek komponentler (konnektör,
  elektrolitik, ısı emici) kasa/komşu parça ile çakışmıyor —
  `mekanik_dxf_koprusu.py::z_kontrolu_yap()` PASS VE ayrıca KiCad 3D
  viewer'da (veya STEP export'unda) gözle son kontrol yapıldı.
  > `z_kontrolu_yap()` 2D poligon + yükseklik haritasıyla çalışır; gerçek
  > STEP-STEP boolean çakışma testi bu projede henüz YOK (`TBD` — cadquery/
  > python-occ gerektirir, bu ortamda kurulu değil). Bu yüzden 3D görsel
  > kontrol otomatik testin YERİNE değil YANINA eklenmiştir.
- [ ] Pin-1/kutup işaretleri konnektörün ALTINDA kalmıyor (montajda okunabilir).
- [ ] Fiducial marker'lar 3 asimetrik köşede.

## 3. IPC-A-600 — Çıplak Kart Kabul Kriterleri (üretici raporuyla çapraz kontrol)

> IPC-A-600, üretilmiş (henüz komponent monte edilmemiş) çıplak PCB'nin kabul
> edilebilirlik sınıflarını (Class 1/2/3) tanımlar. Bu bölüm fab'ın kendi
> kalite raporuyla (varsa) çapraz kontrol edilir — bu proje IPC-A-600'ü
> DENETLEMEZ, sadece hangi sınıfın hedeflendiğini ve fab raporunda
> neyin karşılığı olduğunu kayıt altına alır.

| Alan | Hedef sınıf/kriter | Fab raporunda karşılığı |
|---|---|---|
| Hedef IPC sınıfı (Class 1/2/3) | | |
| Bakır/mask ayrılma (delaminasyon) | Yok | |
| Plating void / annular ring bütünlüğü | | `pcbnew_koprusu.py::annular_ring_kontrolu` ile tasarım tarafı zaten kontrol edildi — bu, ÜRETİM sonrası fiziksel kontroldür |
| Solder mask kayması/hizası | | |
| Silkscreen keskinliği/konumu | | |
| Kenar/routing pürüzsüzlüğü (V-score/mouse-bite artığı) | | |

- [ ] Hedef IPC sınıfı `01_Design_Requirements.md` §3 (güvenilirlik
  gereksinimi) ile TUTARLI (ör. endüstriyel/titreşimli ortam → Class 3).

## 4. Tedarik / BOM Son Kontrol

- [ ] Lifecycle risk skoru her satırda ≤0.5 VEYA yüksek riskli her satır
  için karar (alternatif/NEEDS_HUMAN) belgeli (`bom_lifecycle_koprusu.py`).
- [ ] MSL (nem hassasiyeti) + floor life kritik parçalarda kontrol edildi.
- [ ] DNP satırları BOM + CPL'de TUTARLI.

## 5. Çıktı Paketi

- [ ] Gerber + Drill + BOM + CPL/POS `kibot_calistir()` ile TEK ZIP'te üretildi.
- [ ] Fab-rotasyon-map versiyonlu (hash kayıtlı).
- [ ] **CPL/Centroid ve Polarite Kontrolü:** Pick & Place (CPL) dosyaları
  dışa aktarılırken; diyot, IC ve polariteli kapasitörlerin Kütüphane
  0-derece yönleri ile Tape&Reel dizgi yönleri kontrol edildi. Her
  polariteli komponentin "Pin 1" veya "Katot" işaretinin serigrafide
  (Silkscreen) lehimleme sonrası dışarıdan net okunacak şekilde
  yerleştirildiği teyit edildi.
- [ ] `uretim/` dizini git'e commit'lendi (scratch tek kopya değil).

## 6. Nihai Onay

- [ ] Yukarıdaki 5 bölümün TAMAMI işaretli.
- [ ] `DOCS/01`...`DOCS/04` hepsi `ONAYLANDI` durumunda.
- [ ] Bu dosya `ONAYLANDI` olarak imzalandı — rev/tarih: ______
