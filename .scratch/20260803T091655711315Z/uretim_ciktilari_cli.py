#!/usr/bin/env python3
"""
uretim_ciktilari_cli.py
=========================
Tek komutla üretim çıktısı üretimi: `uretim_zinciri_koprusu.py::
kibot_config_yaz()` + `kibot_calistir()`'i sarar, ama ÖNCE `kicad_koprusu.py`
doğrulama kapısını (DRC + ERC + gerçek-board kontrolleri) ZORUNLU kılar —
"tek tıkla Gerber" isteğinin "DRC'yi atlayarak tek tıkla Gerber"e
dönüşmemesi için.

Kullanım:
    python3 uretim_ciktilari_cli.py board.kicad_pcb sch.kicad_sch \\
        --cikti-dizini uretim/ [--force-atla-dogrulama]

`--force-atla-dogrulama` SADECE hata ayıklama içindir — DRC/ERC dahil HER
ŞEYİ atlar, normal akışta KULLANILMAMALI (MASTER_RULEBOOK'un "DRC sıfır
hata olmadan bir sonraki işleme geçilmez" ilkesini bilerek delen tek
bayrak, bu yüzden isim bilinçli olarak kullanışsız/uzun tutuldu).
`--gercek-board-kontrolu-atla` ondan AYRI ve daha DAR bir bayraktır —
SADECE `pcbnew` yokluğunda maske barajı/via-in-pad/annular-ring
kontrollerini atlar, DRC/ERC yine ZORUNLU kalır; sonuç PASS değil
NEEDS_HUMAN olarak işaretlenir.

FAIL-CLOSED DAVRANIŞ (dış incelemede bulunan iki P0 düzeltildi):
`dogrulama_kapisini_calistir()` artık (1) `pcbnew` yoksa VARSAYILAN olarak
FAIL döner (önceki sürüm sessizce PASS sayıyordu) ve (2) DRC/ERC raporunun
şeması tanınmıyorsa (`sema_taninmadi_mi()`) yine FAIL döner (önceki sürüm
bu kapıyı hiç çağırmıyordu). Ayrıntı için `dogrulama_kapisini_calistir()`
docstring'i.

AĞ/ARAÇ UYARISI: Bu ortamda `kibot`/`pcbnew` yok — o kısımların mantığı
doğru yazıldı ama uçtan uca SENİN makinende doğrulanmalı. `kicad-cli` ise
`arac_yollari.py::kicad_cli_yolunu_bul()` ile bu makinede GERÇEKTEN
bulunup doğrulandı (PATH'te olmasa bile Windows standart kurulum dizininde
otomatik aranıyor).
"""

from __future__ import annotations

import argparse
import sys

from kicad_koprusu import drc_calistir, drc_temiz_mi, erc_calistir, erc_temiz_mi, sema_taninmadi_mi
from uretim_zinciri_koprusu import kibot_calistir, kibot_config_yaz


def dogrulama_kapisini_calistir(
    board_path: str,
    sch_path: str,
    kicad_cli: str | None = None,
    gercek_board_kontrolu_atla: bool = False,
) -> tuple[bool, list[str]]:
    """DRC + ERC + (varsa) gerçek-board kontrollerini çalıştırır.
    Dönen: (hepsi_temiz_mi, sorun_mesajlari).

    İKİ REGRESYON DÜZELTİLDİ (dış incelemede bulundu, gerçek kodla doğrulandı):

    1. **Bilinmeyen DRC/ERC şeması artık PASS SAYILMAZ.** `drc_temiz_mi()`/
       `erc_temiz_mi()` beklenmeyen bir rapor yapısında (ne `violations`
       ne `sheets` var) sessizce `True` döner — bu fonksiyonların KENDİ
       sorumluluğu değil, `sema_taninmadi_mi()` KAPISI zaten bunun için
       yazılmıştı (bkz. `kicad_koprusu.py`) ama bu release CLI'si onu HİÇ
       ÇAĞIRMIYORDU. Artık her iki rapor da önce şema kontrolünden geçer.
    2. **`pcbnew` yokluğu artık varsayılan olarak FAIL'dır, sessiz PASS
       DEĞİL.** Önceki sürüm `ModuleNotFoundError`ı yakalayıp "UYARI:" ön
       ekli bir mesaj ekliyordu, sonra dönüş değeri "UYARI" ile başlayan
       mesajları FİLTRELEYEREK hesaplanıyordu — yani gerçek-board
       kontrolleri (maske barajı, via-in-pad, annular-ring, stitch
       yoğunluğu) HİÇ ÇALIŞMASA BİLE `temiz_mi=True` dönüyordu. Artık
       `gercek_board_kontrolu_atla=True` AÇIKÇA verilmediği sürece bu bir
       FAIL'dır; açıkça verilirse dahi PASS DENMEZ, mesaj NEEDS_HUMAN
       olarak işaretlenir (kullanıcı bunu kendi sorumluluğunda kabul etmiş
       olur, sessiz varsayılan hiçbir zaman yoktur).
    """
    sorunlar: list[str] = []
    basarili = True

    drc_rapor = (
        drc_calistir(board_path, kicad_cli=kicad_cli)
        if kicad_cli is not None
        else drc_calistir(board_path)
    )
    if sema_taninmadi_mi(drc_rapor):
        basarili = False
        sorunlar.append(
            "DRC raporunun şeması TANINMADI (ne 'violations' ne 'sheets' var) "
            "— fail-closed: üretim çıktısı ÜRETİLMEYECEK. kicad-cli sürümü "
            "değişmiş olabilir, rapor formatı yeniden doğrulanmalı."
        )
    elif not drc_temiz_mi(drc_rapor):
        basarili = False
        sorunlar.append("DRC temiz değil — üretim çıktısı ÜRETİLMEYECEK.")

    erc_rapor = (
        erc_calistir(sch_path, kicad_cli=kicad_cli)
        if kicad_cli is not None
        else erc_calistir(sch_path)
    )
    if sema_taninmadi_mi(erc_rapor):
        basarili = False
        sorunlar.append(
            "ERC raporunun şeması TANINMADI (ne 'violations' ne 'sheets' var) "
            "— fail-closed: üretim çıktısı ÜRETİLMEYECEK."
        )
    elif not erc_temiz_mi(erc_rapor):
        basarili = False
        sorunlar.append("ERC temiz değil — üretim çıktısı ÜRETİLMEYECEK.")

    try:
        from kicad_koprusu import gercek_board_dogrulama_kapisi
        gb_temiz_mi, _rapor = gercek_board_dogrulama_kapisi(board_path)
        if not gb_temiz_mi:
            basarili = False
            sorunlar.append(
                "gercek_board_dogrulama_kapisi() FAIL — maske barajı/via-in-pad/"
                "annular-ring/stitch-yoğunluğu kontrollerinden biri temiz değil."
            )
    except ModuleNotFoundError:
        if gercek_board_kontrolu_atla:
            sorunlar.append(
                "NEEDS_HUMAN (bilinçli atlandı, --gercek-board-kontrolu-atla): "
                "pcbnew yok, gerçek-board kontrolleri (maske barajı/via-in-pad/"
                "annular-ring/stitch-yoğunluğu) HİÇ ÇALIŞMADI. Bu PASS DEĞİLDİR "
                "— senin makinende pcbnew ile ayrıca doğrulanmalı."
            )
        else:
            basarili = False
            sorunlar.append(
                "pcbnew bu ortamda yok — gerçek-board kontrolleri ÇALIŞTIRILAMADI. "
                "Varsayılan davranış: üretim çıktısı ÜRETİLMEYECEK (fail-closed). "
                "pcbnew kur VEYA bilinçli olarak --gercek-board-kontrolu-atla kullan "
                "(bu durumda dahi sonuç NEEDS_HUMAN'dır, PASS değildir)."
            )

    return basarili, sorunlar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("board", help="path/to/board.kicad_pcb")
    ap.add_argument("schematic", help="path/to/schematic.kicad_sch")
    ap.add_argument("--kibot-config", default="kibot.yaml")
    ap.add_argument("--cikti-dizini", default="uretim")
    ap.add_argument("--kicad-cli", help="kicad-cli(.exe) tam yolu; KICAD_CLI'yi ezer")
    ap.add_argument(
        "--gercek-board-kontrolu-atla", action="store_true",
        help="pcbnew yoksa maske barajı/via-in-pad/annular-ring kontrollerini "
             "bilinçli olarak atla (SONUÇ YİNE DE NEEDS_HUMAN'dır, PASS DEĞİL) "
             "— DRC/ERC hâlâ ZORUNLUDUR, bu bayrak SADECE gerçek-board kısmını atlar",
    )
    ap.add_argument("--force-atla-dogrulama", action="store_true",
                    help="SADECE hata ayıklama — DRC/ERC dahil HER ŞEYİ atlar, normal akışta KULLANMA")
    args = ap.parse_args(argv)

    if not args.force_atla_dogrulama:
        temiz_mi, sorunlar = dogrulama_kapisini_calistir(
            args.board, args.schematic,
            kicad_cli=args.kicad_cli,
            gercek_board_kontrolu_atla=args.gercek_board_kontrolu_atla,
        )
        for s in sorunlar:
            print(s, file=sys.stderr)
        if not temiz_mi:
            print("\nDurduruldu: doğrulama kapısı geçilmeden üretim çıktısı üretilmez.",
                  file=sys.stderr)
            return 1
    else:
        print("UYARI: --force-atla-dogrulama ile doğrulama kapısı BİLEREK atlandı.",
              file=sys.stderr)

    if not __import__("os").path.exists(args.kibot_config):
        kibot_config_yaz(args.kibot_config)
        print(f"Örnek KiBot config'i yazıldı: {args.kibot_config} "
              "(stackup'a göre ELLE düzenlenmeli).")

    sonuc = kibot_calistir(args.board, args.kibot_config, args.cikti_dizini)
    print(sonuc.stdout)
    if not sonuc.basarili:
        print(sonuc.stderr, file=sys.stderr)
        return 1
    print(f"\nÜretim çıktıları hazır: {sonuc.cikti_dizini}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
