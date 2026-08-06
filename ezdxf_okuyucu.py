#!/usr/bin/env python3
"""
ezdxf_okuyucu.py
==================
`mekanik_dxf_koprusu.py`'deki MEVCUT `DxfOutline` / `import_board_outline()`
yapısını GERÇEK `ezdxf.readfile()` çağrısıyla doldurur. Bu dosya o modülün
YERİNE geçmez — onu besleyen ayrı bir adımdır (tıpkı dosya başındaki
"AĞ/ARAÇ UYARISI" notunun öngördüğü gibi).

DÜZELTİLEN 3 SORUN (orijinal MechanicalDXFBridge taslağına göre):
--------------------------------------------------------------------------
1. **Paralel veri yapısı kurmuyoruz** — orijinal taslak kendi sınıfını
   (`MechanicalDXFBridge`) kurup mevcut `DxfOutline` dataclass'ını hiç
   kullanmıyordu. Bu modül `ezdxf_dosyasindan_outline_oku()` ile DOĞRUDAN
   `DxfOutline` üretir, sonra `import_board_outline()`'a (mevcut, DEĞİŞMEDİ)
   verilir — tek veri yolu.
2. **Sadece LINE aranıyordu** — gerçek mekanik DXF'lerde board outline
   neredeyse hep `LWPOLYLINE` (kapalı çokgen) olarak gelir, köşelerde
   `ARC` içerebilir. Bu modül LWPOLYLINE + LINE + ARC'ı birlikte tarar;
   sadece LINE arayan sorgu gerçek bir dosyada muhtemelen 0 sonuç dönerdi.
3. **Birim tespiti yoktu** — `import_board_outline()` zaten "mm" | "mil"
   ayrımı yapıyor ama orijinal taslak DXF'ten hangi birimde geldiğini hiç
   okumuyordu. Bu modül DXF header'ındaki `$INSUNITS` değerinden birimi
   OKUR, varsaymaz; tanınmayan bir INSUNITS değeri gelirse (örn. 0 =
   "birimsiz") CONFIRM gerektiren bir hata fırlatır — sessizce mm
   varsaymak yanlış outline'a yol açabilir.

ÇÖZÜLEN inch->mil ÖLÇEK SORUNU (bu görevde ayrıca istendi):
--------------------------------------------------------------------------
`$INSUNITS=1` (Inches) olduğunda ezdxf'ten gelen ham koordinatlar
İNÇ cinsindendir — MİL DEĞİL. `mekanik_dxf_koprusu.py::import_board_
outline()`'ın `birim=="mil"` yolu `_mil_den_mm_e()` (`x * 0.0254`, yani
"1 mil = 0.0254mm") çarpanını kullanır; bu çarpan İNÇ değerine DOĞRUDAN
uygulanırsa (1 inch = 25.4mm olması gerekirken 0.0254mm çıkar) sonuç
**1000 KAT KÜÇÜK** bir outline üretirdi. Çözüm: `_INSUNITS_INCH` tespit
edildiğinde ham koordinatlar BURADA (bu dosyada, `import_board_outline()`
çağrılmadan ÖNCE) `x1000` ile ÖNCE mil'e çevrilir, `birim="mil"` olarak
işaretlenir — `import_board_outline()`'ın mil->mm çarpanı böylece doğru
büyüklükte bir mm sonucu üretir (`inch * 1000 * 0.0254 = inch * 25.4`,
matematiksel olarak doğru inch->mm dönüşümüyle BİREBİR aynı).

DOĞRULAMA DURUMU (GERÇEK koşumla güncellenmiştir):
--------------------------------------------------------------------------
  - **ezdxf kurulu değilken KAPSAM_YOK yolu: DOĞRULANDI** (bu makinede
    `ezdxf` GERÇEKTEN kurulu değil, `test_ezdxf_okuyucu.py` bu dalı
    ölçtü).
  - **$INSUNITS ayrıştırma + inch->mil ölçek düzeltmesi + LWPOLYLINE/
    LINE/ARC tarama + poligon kapalılık kontrolü: sahte `ezdxf.readfile()`
    dönen bir taklit modülle (gerçek ezdxf KURULU DEĞİL) GERÇEKTEN test
    edildi** (`test_ezdxf_okuyucu.py`) — 1000x ölçek hatasının GERÇEKTEN
    düzeldiği (inç->mm sonucunun `x*25.4` ile birebir eşleştiği) sayısal
    olarak doğrulandı.
  - **kicad_edge_cuts_a_yaz(): pcbnew mock'uyla GERÇEKTEN test edildi**
    (`topolojik_router_koprusu.py::TopolojikRouter.iz_yaz()` ile AYNI
    yazma deseni: `LoadBoard` -> `PCB_SHAPE`/`board.Add()` -> `board.
    Save()`) — GERÇEK bir `.kicad_pcb` + gerçek `pcbnew` ile HENÜZ
    doğrulanmadı (bu ortamda pcbnew yok, aynı proje-genelindeki AĞ/ARAÇ
    UYARISI geçerli).
  - **HÂLÂ DOĞRULANMADI:** ARC'ların poligon yaklaşıklamasının (segment
    sayısı/toleransı) gerçek bir mekanik DXF'te yeterli olup olmadığı —
    `_arc_to_polyline_puanlari`'daki sabit 16-segment TODO'su AYNEN
    KALDI (bu görevin kapsamı dışındaydı).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

from bulgu_sozlesmesi import Bulgu, bulgu_uret
from mekanik_dxf_koprusu import DxfOutline, import_board_outline, poligon_kapali_mi

# ezdxf'in $INSUNITS kod tablosundan ilgili olanlar (DXF grup kodu 70, header $INSUNITS)
_INSUNITS_MM = {4}  # 4 = Millimeters
_INSUNITS_INCH = {1}  # 1 = Inches — ham koordinatlar İNÇ'tir, mil DEĞİL (bkz. dosya başlığı)


def _arc_to_polyline_puanlari(
    merkez: Tuple[float, float], yaricap: float, baslangic_aci_derece: float,
    bitis_aci_derece: float, segment_sayisi: int = 16
) -> List[Tuple[float, float]]:
    """Bir ARC varlığını düz çizgi segmentlerine yaklaşıklar.

    TODO (çözülmedi, kapsam dışı bırakıldı): segment_sayisi'ni yay
    uzunluğuna/yarıçapa göre ADAPTIF yap (büyük yarıçapta sabit 16 segment
    görünür fasetleşme yaratır) — gerçek DXF ile test edilip kalibre
    edilmeli.
    """
    cx, cy = merkez
    a0 = math.radians(baslangic_aci_derece)
    a1 = math.radians(bitis_aci_derece)
    if a1 < a0:
        a1 += 2 * math.pi
    return [
        (
            cx + yaricap * math.cos(a0 + (a1 - a0) * i / segment_sayisi),
            cy + yaricap * math.sin(a0 + (a1 - a0) * i / segment_sayisi),
        )
        for i in range(segment_sayisi + 1)
    ]


def ezdxf_dosyasindan_outline_oku(
    dxf_yolu: Path, outline_katman_adi: str = "Board_Outline"
) -> Tuple[Bulgu, Optional[DxfOutline]]:
    """Gerçek DXF dosyasını okuyup `DxfOutline`'ı doldurur.

    Dönüş: `(Bulgu, DxfOutline|None)` — DXF açılamazsa veya
    `outline_katman_adi` üzerinde HİÇBİR geometri yoksa
    `Bulgu.durum=KAPSAM_YOK`, `DxfOutline=None`.
    """
    kontrol = "ezdxf_dosyasindan_outline_oku"
    try:
        import ezdxf
    except ImportError:
        return bulgu_uret(
            kontrol, taranan=0, detay="ezdxf kütüphanesi kurulu değil — DXF okuma KOŞULMADI.",
        ), None

    try:
        doc = ezdxf.readfile(str(dxf_yolu))
    except (IOError, ezdxf.DXFStructureError) as e:
        return bulgu_uret(kontrol, taranan=0, detay=f"DXF açılamadı: {e}"), None

    insunits = doc.header.get("$INSUNITS", 0)
    if insunits in _INSUNITS_MM:
        olcek = 1.0
        birim = "mm"
    elif insunits in _INSUNITS_INCH:
        # inch -> mil (x1000); import_board_outline()'ın mil->mm (x0.0254)
        # çarpanı bu şekilde DOĞRU büyüklükte bir mm sonucu üretir
        # (bkz. dosya başlığı "ÇÖZÜLEN inch->mil ÖLÇEK SORUNU").
        olcek = 1000.0
        birim = "mil"
    else:
        return bulgu_uret(
            kontrol, taranan=1,
            ihlaller=[{"sebep": "tanınmayan/birimsiz $INSUNITS", "insunits_kodu": insunits}],
            detay="DXF header'ında birim belirsiz — sessizce mm varsayılmadı, CONFIRM gerekli.",
        ), None

    msp = doc.modelspace()
    noktalar: List[Tuple[float, float]] = []

    for varlik in msp.query(f'LWPOLYLINE[layer=="{outline_katman_adi}"]'):
        noktalar.extend([(p[0], p[1]) for p in varlik.get_points()])

    for varlik in msp.query(f'LINE[layer=="{outline_katman_adi}"]'):
        noktalar.append((varlik.dxf.start.x, varlik.dxf.start.y))
        noktalar.append((varlik.dxf.end.x, varlik.dxf.end.y))

    for varlik in msp.query(f'ARC[layer=="{outline_katman_adi}"]'):
        noktalar.extend(
            _arc_to_polyline_puanlari(
                (varlik.dxf.center.x, varlik.dxf.center.y),
                varlik.dxf.radius,
                varlik.dxf.start_angle,
                varlik.dxf.end_angle,
            )
        )

    if not noktalar:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"'{outline_katman_adi}' katmanında LWPOLYLINE/LINE/ARC bulunamadı.",
        ), None

    delik_katman_adi = f"{outline_katman_adi}_Deliği"
    delikler_ham: List[Tuple[float, float, float]] = [
        (v.dxf.center.x, v.dxf.center.y, v.dxf.radius * 2)
        for v in msp.query(f'CIRCLE[layer=="{delik_katman_adi}"]')
    ]

    # DXF-native (mm veya inch) değerler burada TEK bir noktada ölçeklenir
    # (`olcek`=1.0 mm için, 1000.0 inch->mil için) — LWPOLYLINE/LINE/ARC/
    # CIRCLE kaynağından BAĞIMSIZ, tek bir çevrim noktası.
    noktalar = [(x * olcek, y * olcek) for x, y in noktalar]
    delikler = [(cx * olcek, cy * olcek, cap * olcek) for cx, cy, cap in delikler_ham]

    outline = DxfOutline(nokta_listesi=noktalar, birim=birim, delik_listesi=delikler)

    kapali = poligon_kapali_mi(outline.nokta_listesi)
    bulgu = bulgu_uret(
        kontrol, taranan=len(noktalar),
        ihlaller=[] if kapali else [{"sebep": "outline poligonu KAPALI DEĞİL"}],
        detay=f"{len(noktalar)} nokta, {len(delikler)} delik okundu (insunits={insunits}, birim={birim}). Kapalı: {kapali}.",
    )
    return bulgu, outline


def kicad_edge_cuts_a_yaz(board_path: Path, outline: DxfOutline, cizgi_kalinligi_mm: float = 0.1) -> Bulgu:
    """`import_board_outline()`'dan geçmiş, DOĞRULANMIŞ bir outline'ı
    KiCad Edge.Cuts katmanına `PCB_SHAPE` (SEGMENT) parçaları olarak
    çizer.

    `topolojik_router_koprusu.py::TopolojikRouter.iz_yaz()` ile AYNI
    yazma deseni: `pcbnew.LoadBoard()` -> her segment için bir pcbnew
    nesnesi oluştur + `board.Add()` -> döngü bitince TEK `board.Save()`
    (segment başına kaydetmek YAVAŞ/riskli olurdu, o dosyadaki desenle
    tutarlı tek seferlik kaydetme kullanıldı).

    ÖNEMLİ: bu fonksiyona DOĞRUDAN ezdxf çıktısı VERİLMEMELİ — önce
    `import_board_outline(outline)` ile birim/orijin doğrulamasından
    geçirilmiş olmalı (`outline.birim == "mm"` zorunlu, aksi halde
    `ValueError`).
    """
    kontrol = "kicad_edge_cuts_a_yaz"
    if outline.birim != "mm":
        raise ValueError(
            "kicad_edge_cuts_a_yaz: outline import_board_outline()'dan "
            "geçmemiş görünüyor (birim hâlâ 'mil') — önce doğrulamadan geçir."
        )

    noktalar = outline.nokta_listesi
    if len(noktalar) < 2:
        return bulgu_uret(
            kontrol, taranan=0,
            detay=f"outline'da {len(noktalar)} nokta var — poligon dejenere, yazılacak bir şey yok.",
        )

    if not poligon_kapali_mi(noktalar):
        return bulgu_uret(
            kontrol, taranan=len(noktalar),
            ihlaller=[{"sebep": "outline poligonu KAPALI DEĞİL — Edge.Cuts'a yazılmadı"}],
            detay="Açık bir outline board'a yazılırsa dolgu/DRC bozulur; CONFIRM gerekli.",
        )

    try:
        import pcbnew
    except ImportError:
        return bulgu_uret(
            kontrol, taranan=0,
            detay="pcbnew modülü import edilemedi — KiCad'in dahili python ortamında çalıştırılmalı.",
        )

    # poligon zaten kapalıysa (ilk nokta ~= son nokta) son->ilk segmenti
    # TEKRAR eklenmez; açık listeyse kapanış segmenti BURADA eklenir —
    # kaynak fark etmeksizin tek, tutarlı bir segment üretimi.
    segmentler = list(zip(noktalar[:-1], noktalar[1:]))
    ilk, son = noktalar[0], noktalar[-1]
    if math.hypot(ilk[0] - son[0], ilk[1] - son[1]) > 0.01:
        segmentler.append((son, ilk))

    board = pcbnew.LoadBoard(str(board_path))
    edge_katmani = pcbnew.Edge_Cuts
    eklenen = 0
    for a, b in segmentler:
        sekil = pcbnew.PCB_SHAPE(board)
        sekil.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sekil.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
        sekil.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
        sekil.SetLayer(edge_katmani)
        sekil.SetWidth(pcbnew.FromMM(cizgi_kalinligi_mm))
        board.Add(sekil)
        eklenen += 1
    board.Save(str(board_path))

    return bulgu_uret(
        kontrol, taranan=len(segmentler), detay=f"{eklenen} Edge.Cuts segmenti board'a yazıldı ve kaydedildi.",
    )
