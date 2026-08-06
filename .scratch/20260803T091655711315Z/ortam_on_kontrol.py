#!/usr/bin/env python3
"""PCB araç zinciri için ortam ön kontrol komutu.

Kullanım:
    uv run python ortam_on_kontrol.py                    # sadece KiCad CLI
    uv run python ortam_on_kontrol.py --tam               # TÜM araçlar (KURULUM.md "Hızlı toplu doğrulama")
    uv run python ortam_on_kontrol.py --kicad-cli "C:\\Program Files\\KiCad\\10.0\\bin\\kicad-cli.exe"

`--tam`, bash'in `A && B && C` zincirleme sözdiziminin YERİNE geçer —
Windows PowerShell 5.1 `&&`yi desteklemez, bu yüzden bu tek komut hem
bash'te hem PowerShell'de AYNI şekilde çalışır (`KURULUM.md` "Hızlı toplu
doğrulama" bölümüne bakınız). Bash zincirinden farklı olarak tek bir eksik
araç DİĞERLERİNİN kontrol edilmesini ENGELLEMEZ — tek çağrıda TAM tablo
elde edilir, çıkış kodu (0/1) yalnızca TÜMÜ PASS ise 0'dır.
"""

from __future__ import annotations

import argparse

from arac_yollari import ortam_on_kontrolu, tum_araclari_kontrol_et


def main(argv: list[str] | None = None) -> int:
    ayrac = argparse.ArgumentParser(description=__doc__)
    ayrac.add_argument("--kicad-cli", help="kicad-cli(.exe) için tam yol; KICAD_CLI'yi ezer")
    ayrac.add_argument(
        "--tam", action="store_true",
        help="Sadece KiCad CLI değil, KURULUM.md'deki TÜM araçları kontrol et "
             "(pcbnew/kipy, node, java, JLC2KiCadLib, kibot, uv, pytest, git)",
    )
    args = ayrac.parse_args(argv)

    if args.tam:
        sonuclar = tum_araclari_kontrol_et(args.kicad_cli)
        for durum in sonuclar:
            print(durum.satir())
        return 0 if all(d.gecti_mi for d in sonuclar) else 1

    try:
        for satir in ortam_on_kontrolu(args.kicad_cli):
            print(satir)
    except (FileNotFoundError, RuntimeError) as hata:
        print(f"FAIL KiCad CLI: {hata}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
