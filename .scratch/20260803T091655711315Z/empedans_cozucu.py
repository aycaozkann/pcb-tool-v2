#!/usr/bin/env python3
"""
empedans_cozucu.py
====================
`pcb_stackup_planner.py::empedans_hedefi_getir()` sadece bir HEDEF sayı
döndürüyordu (ör. USB3 için 90Ω) — o hedefi FİZİKSEL OLARAK karşılayacak
(W, S) iz genişliği/aralığını hesaplayan bir çözücü YOKTU. Bu dosya o
boşluğu doldurur.

Arkadaşının `zdiff_solver.py`'sinden esinlenildi (IPC-2141/Wadell kapalı
form yaklaşımı) — aynı fizik, aynı doğrulama disiplini (self-test +
fault-injection), proje konvansiyonuna göre Türkçe isimlendirilmiş ve
`empedans_hedefi_getir()` ile birlikte çalışacak şekilde uyarlanmış.

ÖNEMLİ — DÜRÜSTLÜK NOTU:
Bu kapalı-form formüller ERKEN TASARIM (trade study) içindir. Üretim
sign-off'u için gerçek laminate verisi + 2D/3D alan çözücü (field solver)
ve fab'ın impedance test coupon + TDR raporu ŞARTTIR
([[SKILL-empedans-stackup]] §a ile aynı disiplin) — bu dosya o adımın
YERİNE GEÇMEZ, sadece stackup keşfi/erken karar aşamasını hızlandırır.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

H_ADAY_DEGERLERI_MM = (0.1, 0.15, 0.2, 0.3, 0.5, 0.8, 1.6)


def _pozitif_olmali(**degerler: float) -> None:
    for isim, deger in degerler.items():
        if not math.isfinite(deger) or deger <= 0:
            raise ValueError(f"{isim} pozitif sonlu bir sayı olmalı, gelen: {deger!r}")


def z0_mikroserit(w: float, t: float, h: float, er: float) -> float:
    """Tek-uçlu mikroşerit empedansı (IPC-2141/Wadell yaklaşımı), ohm.

    Z0 = 87/sqrt(er+1.41) * ln(5.98*h/(0.8*w+t))
    """
    _pozitif_olmali(w=w, t=t, h=h, er=er)
    log_argumani = 5.98 * h / (0.8 * w + t)
    if log_argumani <= 1.0:
        raise ValueError(
            "geometri bu yaklaşımın pozitif-empedans bölgesinin dışında"
        )
    return 87.0 / math.sqrt(er + 1.41) * math.log(log_argumani)


def zdiff_mikroserit(w: float, s: float, t: float, h: float, er: float) -> float:
    """Kenar-kuplajlı (edge-coupled) mikroşerit diferansiyel empedansı, ohm."""
    _pozitif_olmali(s=s)
    z0 = z0_mikroserit(w, t, h, er)
    z_odd = z0 * (1.0 - 0.347 * math.exp(-2.9 * s / h))
    return 2.0 * z_odd


def zdiff_stripline(w: float, s: float, t: float, h: float, er: float) -> float:
    """Simetrik kenar-kuplajlı stripline Zdiff, ohm.

    Kaynak: IPC-2141 simetrik stripline kapalı-form yaklaşımı:
    Z0 = 60/sqrt(er) * ln(4h/(0.67*pi*(0.8w+t)))
    ardından IPC-2141 kenar-kuplajlı stripline yaklaşımı:
    Zdiff = 2*Z0*(1 - 0.374*exp(-2.9*s/h))

    Burada `h`, iki referans düzlemi arasındaki TOPLAM mesafedir; iz bu
    iki düzlem arasında ortalanmış kabul edilir.
    """
    _pozitif_olmali(w=w, s=s, t=t, h=h, er=er)
    log_argumani = 4.0 * h / (0.67 * math.pi * (0.8 * w + t))
    if log_argumani <= 1.0:
        raise ValueError(
            "geometri bu yaklaşımın pozitif-empedans bölgesinin dışında"
        )
    z0 = 60.0 / math.sqrt(er) * math.log(log_argumani)
    return 2.0 * z0 * (1.0 - 0.374 * math.exp(-2.9 * s / h))


def _grid_degerleri(sinirlar: Sequence[float], minimum: float, isim: str) -> list[float]:
    """(baslangic, bitis[, adim]) demetini, fab-sınırlı, kapsayıcı bir grid'e açar."""
    if len(sinirlar) not in (2, 3):
        raise ValueError(f"{isim} (baslangic, bitis) ya da (baslangic, bitis, adim) olmalı")
    baslangic, bitis = float(sinirlar[0]), float(sinirlar[1])
    adim = float(sinirlar[2]) if len(sinirlar) == 3 else 0.005
    _pozitif_olmali(baslangic=baslangic, bitis=bitis, adim=adim, minimum=minimum)
    baslangic = max(baslangic, minimum)
    if baslangic > bitis:
        return []

    sayi = int(math.floor((bitis - baslangic) / adim + 1e-12))
    degerler = [baslangic + i * adim for i in range(sayi + 1)]
    if not math.isclose(degerler[-1], bitis, rel_tol=0.0, abs_tol=1e-12):
        degerler.append(bitis)
    return degerler


def hedefe_gore_coz(
    hedef_ohm: float,
    h: float,
    er: float,
    t: float,
    w_araligi: Sequence[float],
    s_araligi: Sequence[float],
    fab_min_w: float,
    fab_min_s: float,
) -> list[dict[str, float]]:
    """`hedef_ohm`'a en yakın 5 mikroşerit (w, s) grid noktasını döndürür."""
    _pozitif_olmali(
        hedef_ohm=hedef_ohm, h=h, er=er, t=t, fab_min_w=fab_min_w, fab_min_s=fab_min_s,
    )
    genislikler = _grid_degerleri(w_araligi, fab_min_w, "w_araligi")
    araliklar = _grid_degerleri(s_araligi, fab_min_s, "s_araligi")
    if not genislikler or not araliklar:
        return []

    adaylar: list[dict[str, float]] = []
    for w in genislikler:
        for s in araliklar:
            try:
                empedans = zdiff_mikroserit(w, s, t, h, er)
            except ValueError:
                continue
            hata_ohm = empedans - hedef_ohm
            adaylar.append({
                "w_mm": round(w, 9),
                "s_mm": round(s, 9),
                "zdiff_ohm": empedans,
                "hata_ohm": hata_ohm,
                "hata_yuzde": abs(hata_ohm) / hedef_ohm * 100.0,
            })

    adaylar.sort(key=lambda x: (x["hata_yuzde"], x["w_mm"], x["s_mm"]))
    return adaylar[:5]


def _ulasilabilir_empedans_siniri(
    h: float, er: float, t: float,
    w_araligi: Sequence[float], s_araligi: Sequence[float],
    fab_min_w: float, fab_min_s: float,
) -> tuple[float, float] | None:
    genislikler = _grid_degerleri(w_araligi, fab_min_w, "w_araligi")
    araliklar = _grid_degerleri(s_araligi, fab_min_s, "s_araligi")
    empedanslar: list[float] = []
    for w in genislikler:
        for s in araliklar:
            try:
                empedanslar.append(zdiff_mikroserit(w, s, t, h, er))
            except ValueError:
                pass
    if not empedanslar:
        return None
    return min(empedanslar), max(empedanslar)


def stackup_tara(
    hedef_ohm: float,
    er: float,
    t: float,
    w_araligi: Sequence[float] = (0.05, 2.0, 0.005),
    s_araligi: Sequence[float] = (0.05, 2.0, 0.005),
    fab_min_w: float = 0.127,
    fab_min_s: float = 0.127,
    h_adaylari: Iterable[float] = H_ADAY_DEGERLERI_MM,
) -> dict[str, object]:
    """Dielektrik yüksekliklerini tarar, hedefe ULAŞILAMAYAN H değerlerini
    AÇIKÇA işaretler.

    "Ulaşılabilir" demek, hedefin fab-sınırlı W/S arama sınırlarının
    empedans aralığı İÇİNDE olması demektir; bu ÜRETİM SIGN-OFF'U anlamına
    GELMEZ — bkz. dosya başındaki dürüstlük notu.
    """
    _pozitif_olmali(hedef_ohm=hedef_ohm, er=er, t=t)
    satirlar: list[dict[str, object]] = []
    ulasilamayan_h_mm: list[float] = []

    for h_deger in h_adaylari:
        h = float(h_deger)
        _pozitif_olmali(h=h)
        cozumler = hedefe_gore_coz(hedef_ohm, h, er, t, w_araligi, s_araligi, fab_min_w, fab_min_s)
        sinir = _ulasilabilir_empedans_siniri(h, er, t, w_araligi, s_araligi, fab_min_w, fab_min_s)
        ulasilabilir = bool(sinir is not None and sinir[0] <= hedef_ohm <= sinir[1])
        if not ulasilabilir:
            ulasilamayan_h_mm.append(h)
        satirlar.append({
            "h_mm": h,
            "ulasilabilir": ulasilabilir,
            "durum": "ULASILABILIR" if ulasilabilir else "ULASILAMAZ",
            "ulasilabilir_min_ohm": sinir[0] if sinir else None,
            "ulasilabilir_max_ohm": sinir[1] if sinir else None,
            "en_iyi": cozumler[0] if cozumler else None,
            "ilk_5": cozumler,
        })

    return {
        "model": "IPC-2141/Wadell yaklaşık kenar-kuplajlı mikroşerit",
        "hedef_ohm": hedef_ohm,
        "er": er,
        "t_mm": t,
        "fab_min_w_mm": fab_min_w,
        "fab_min_s_mm": fab_min_s,
        "w_araligi_mm": list(w_araligi),
        "s_araligi_mm": list(s_araligi),
        "stackuplar": satirlar,
        "ulasilamayan_h_mm": ulasilamayan_h_mm,
    }


# ------------------------------------------------------------------
# ÖZ-TEST + FAULT-INJECTION (CLAUDE.md honesty §6 ile aynı disiplin:
# "test yazdıysan boş olmadığını fault-injection ile kanıtla")
# ------------------------------------------------------------------

def _referans_yuzde10_icinde_mi(hesaplayici=zdiff_mikroserit) -> None:
    olculen_ohm = 184.0
    hesaplanan_ohm = hesaplayici(0.4, 0.4, 0.035, 1.6, 4.5)
    sapma = abs(hesaplanan_ohm - olculen_ohm) / olculen_ohm
    assert sapma <= 0.10, (
        "1.6 mm FR4 referans uyuşmazlığı: "
        f"hesaplanan={hesaplanan_ohm:.2f} ohm, ölçülen={olculen_ohm:.2f} ohm, "
        f"sapma={sapma * 100:.2f}%"
    )


def _testin_bos_olmadigini_kanitla() -> bool:
    """Bilerek YANLIŞ bir katsayı (60/87 karışıklığı) koyup referans testin
    bunu GERÇEKTEN reddettiğini kanıtlar — test_sch_wire.py'deki
    break_wire=True deseninin empedans-solver karşılığı."""

    def bilerek_yanlis(w: float, s: float, t: float, h: float, er: float) -> float:
        _pozitif_olmali(w=w, s=s, t=t, h=h, er=er)
        yanlis_z0 = 60.0 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
        return 2.0 * yanlis_z0 * (1.0 - 0.347 * math.exp(-2.9 * s / h))

    try:
        _referans_yuzde10_icinde_mi(bilerek_yanlis)
    except AssertionError:
        print(
            "FAULT-INJECTION: gözlenen=FAIL, kanıt=PASS "
            "(bilerek yanlış 60/87 katsayısı reddedildi)"
        )
        return True
    print(
        "FAULT-INJECTION: gözlenen=PASS, kanıt=FAIL "
        "(referans test yanlış katsayıyı reddetmedi — TEST BOŞ)"
    )
    return False


def oz_testleri_calistir() -> None:
    """Zorunlu sayısal-referans ve monotonluk testlerini çalıştırır."""

    def referans_testi() -> None:
        _referans_yuzde10_icinde_mi()

    def h_monotonluk_testi() -> None:
        dusuk = zdiff_mikroserit(0.4, 0.4, 0.035, 0.8, 4.5)
        yuksek = zdiff_mikroserit(0.4, 0.4, 0.035, 1.6, 4.5)
        assert yuksek > dusuk, f"Zdiff h ile artmadı: {dusuk:.3f} -> {yuksek:.3f}"

    def w_monotonluk_testi() -> None:
        dar = zdiff_mikroserit(0.3, 0.4, 0.035, 1.6, 4.5)
        genis = zdiff_mikroserit(0.5, 0.4, 0.035, 1.6, 4.5)
        assert genis < dar, f"Zdiff w ile azalmadı: {dar:.3f} -> {genis:.3f}"

    def s_monotonluk_testi() -> None:
        yakin = zdiff_mikroserit(0.4, 0.2, 0.035, 1.6, 4.5)
        uzak = zdiff_mikroserit(0.4, 0.6, 0.035, 1.6, 4.5)
        assert uzak > yakin, f"Zdiff s ile artmadı: {yakin:.3f} -> {uzak:.3f}"

    testler = (
        ("referans", referans_testi),
        ("h Zdiff'i artırır", h_monotonluk_testi),
        ("w Zdiff'i azaltır", w_monotonluk_testi),
        ("s Zdiff'i artırır", s_monotonluk_testi),
    )
    for isim, test in testler:
        try:
            test()
        except AssertionError as exc:
            print(f"ÖZ-TEST FAIL [{isim}]: {exc}", file=sys.stderr)
            raise
        else:
            print(f"ÖZ-TEST PASS [{isim}]")

    try:
        assert _testin_bos_olmadigini_kanitla(), "fault-injection kanıtının kendisi başarısız"
    except AssertionError as exc:
        print(f"ÖZ-TEST FAIL [fault-injection]: {exc}", file=sys.stderr)
        raise


def _tablo_bicimlendir(rapor: dict[str, object]) -> str:
    baslik = (
        " h (mm) | durum        | en iyi W (mm) | en iyi S (mm) | "
        "Zdiff (ohm) | hata (%) | ulaşılabilir aralık (ohm)"
    )
    satirlar = [baslik, "-" * len(baslik)]
    for satir in rapor["stackuplar"]:  # type: ignore[index]
        en_iyi = satir["en_iyi"]
        if en_iyi is None:
            en_iyi_sutunlar = "      -       |      -        |      -      |     -    "
        else:
            en_iyi_sutunlar = (
                f"{en_iyi['w_mm']:13.3f} | {en_iyi['s_mm']:13.3f} | "
                f"{en_iyi['zdiff_ohm']:11.2f} | {en_iyi['hata_yuzde']:8.3f}"
            )
        dusuk = satir["ulasilabilir_min_ohm"]
        yuksek = satir["ulasilabilir_max_ohm"]
        aralik = "-" if dusuk is None else f"{dusuk:.2f} .. {yuksek:.2f}"
        satirlar.append(
            f"{satir['h_mm']:7.3f} | {satir['durum']:12s} | "
            f"{en_iyi_sutunlar} | {aralik}"
        )
    return "\n".join(satirlar)


def _olustur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hedef", type=float, help="hedef diferansiyel empedans, ohm")
    p.add_argument("--er", type=float, default=4.5, help="bağıl dielektrik sabiti")
    p.add_argument("--t", type=float, default=0.035, help="bakır kalınlığı, mm")
    p.add_argument("--fab-min-w", type=float, default=0.127, help="minimum iz genişliği, mm")
    p.add_argument("--fab-min-s", type=float, default=0.127, help="minimum iz aralığı, mm")
    p.add_argument("--w-min", type=float, default=0.05)
    p.add_argument("--w-max", type=float, default=2.0)
    p.add_argument("--s-min", type=float, default=0.05)
    p.add_argument("--s-max", type=float, default=2.0)
    p.add_argument("--adim", type=float, default=0.005)
    p.add_argument("--json", type=Path)
    p.add_argument("--oztest", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = _olustur_parser()
    args = parser.parse_args(argv)

    try:
        oz_testleri_calistir()
    except (AssertionError, ValueError):
        return 1

    if args.oztest or args.hedef is None:
        if args.hedef is None and not args.oztest:
            print("--hedef verilmedi; öz-testler tamamlandı.")
        return 0

    try:
        rapor = stackup_tara(
            hedef_ohm=args.hedef, er=args.er, t=args.t,
            w_araligi=(args.w_min, args.w_max, args.adim),
            s_araligi=(args.s_min, args.s_max, args.adim),
            fab_min_w=args.fab_min_w, fab_min_s=args.fab_min_s,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print()
    print(_tablo_bicimlendir(rapor))
    json_metni = json.dumps(rapor, indent=2, ensure_ascii=False, sort_keys=True)
    print("\nJSON:")
    print(json_metni)
    if args.json:
        args.json.write_text(json_metni + "\n", encoding="utf-8")
        print(f"\nJSON şuraya yazıldı: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
