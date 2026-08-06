#!/usr/bin/env python3
"""pcb-tool-v2 otonom akışının tek-komut yürütücüsü.

    python main.py run --project-dir "yol/proje" [--produce] [--kicad-cli ...]
    python main.py promote --project-dir "yol/proje" [--scratch-id ID] [--kicad-cli ...]

`CLAUDE.md`'deki "Otonom akış (sırayla)" listesinin adım 1 (ortam), adım 3
(şematik + ERC) ve adım 5 (DRC kapısı) bölümlerini TEK bir komuta bağlar.
Adım 4 (yerleşim/routing) ve adım 6-7 (checker/üretim) BİLİNÇLİ OLARAK bu
komuta dahil EDİLMEDİ: onlar `pcbnew` + insan onayı (routing_plan.md) veya
ayrı bir skill (design-checker) gerektiriyor, tek bir CLI komutunun arkasına
sessizce gizlenemezler (bkz. MASTER_RULEBOOK "Ne zaman dur"). Bu script,
DRC/ERC temiz olmadan `uretim_ciktilari_cli.py`'nin çağrılamayacağını
GERÇEKTEN uygular — "fail-closed" davranışı elle tekrarlamak yerine mevcut
modülleri sırayla çağırır.

**Governance katmanı (2026-08-03, GÖREV 1-7):** `run` artık kanonik proje
dosyalarına DİREKT yazmaz — önce `.scratch/<id>/` altına kopyalar, TÜM
fazlar scratch kopya üzerinde çalışır. Kanonik dosyaya geçiş SADECE
`promote` komutuyla, SADECE (a) taze DRC/ERC temiz VE (b) proje-özel
kontratı ölçen bağımsız verifier (`bagimsiz_dogrulama.py`) temiz VE (c)
tüm `karar_birimleri.json` kayıtları `KABUL_EDILDI` olduğunda olur —
bkz. `cmd_promote`. Bu, MASTER_RULEBOOK BÖLÜM 0 "Rapor-Veri Tutarlılığı"
maddesinin YAPTIRIM MEKANİZMASIDIR: bir rapor "temiz"/"güvenli" diyebilmesi
için artık GERÇEKTEN bu kapılardan geçmiş olması gerekir, iddia tek başına
yetmez.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from arac_yollari import tum_araclari_kontrol_et
from bagimsiz_dogrulama import (
    bagimsiz_dogrulama_calistir,
    dogrulama_temiz_mi,
    kapsam_yok_maddeleri,
)
from karar_birimleri import kabul_edilmemis_kararlari_bul, kararlari_yukle
from kicad_koprusu import (
    drc_calistir,
    drc_raporunu_ozetle,
    drc_temiz_mi,
    erc_calistir,
)
from scratch_yonetimi import (
    kanonige_yukselt,
    scratch_kok_dizini,
    scratch_listele,
    scratch_olustur,
)


def _konsol_utf8_ayarla() -> None:
    """Windows konsolunda Türkçe karakterlerin bozuk görünmesini (mojibake,
    `TEM�Z` gibi) önler: `sys.stdout`/`sys.stderr` UTF-8'e çevrilir. Eski
    Python/ortamlarda `reconfigure` yoksa sessizce atlanır."""
    for akim in (sys.stdout, sys.stderr):
        if akim is not None and hasattr(akim, "reconfigure"):
            try:
                akim.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _erc_ihlallerini_topla(rapor: dict) -> list[dict]:
    """`erc_calistir()` şeması `sheets[].violations` altında gelir (DRC'den
    farklı) — bkz. `kicad_koprusu.erc_calistir` docstring'i."""
    ihlaller: list[dict] = []
    for sayfa in rapor.get("sheets", []):
        ihlaller.extend(sayfa.get("violations", []))
    return ihlaller


def _erc_temiz_mi(rapor: dict) -> bool:
    return not any(v.get("severity") == "error" for v in _erc_ihlallerini_topla(rapor))


def _drc_baglantisiz_netler(rapor: dict) -> list[str]:
    """`unconnected_items` girdilerinden NET ADLARINI çıkarır.

    KiCad 10 DRC şemasında `unconnected_items[].items[].description`
    `"5 için [IMU_INT1] U1 ayak F.Cu"` biçimindedir — köşeli parantez
    içindeki değer net adıdır. Sıralı ve tekilleştirilmiş liste döner;
    parse edilemeyen girdiler (net adı yoksa) atlanır. Bu, kullanıcıya
    "HANGİ net yarım kalmış" bilgisini verir — `[error] Missing connection`
    satırı tek başına hangi net olduğunu söylemez."""
    netler: list[str] = []
    for ihlal in rapor.get("unconnected_items", []):
        for madde in ihlal.get("items", []):
            eslesme = re.search(r"\[([^\]]+)\]", madde.get("description", ""))
            if eslesme and eslesme.group(1) not in netler:
                netler.append(eslesme.group(1))
    return netler


def _proje_dosyalarini_bul(project_dir: Path) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """`project_dir` içinde tek bir `.kicad_pro` bulur, aynı gövde adıyla
    `.kicad_sch`/`.kicad_pcb` eşleştirir. Birden fazla/hiç bulunamazsa None
    döner — uydurma bir varsayılan İSİM SEÇİLMEZ."""
    adaylar = sorted(project_dir.glob("*.kicad_pro"))
    if len(adaylar) != 1:
        return None, None, None
    pro = adaylar[0]
    govde = pro.with_suffix("")
    sch = govde.with_suffix(".kicad_sch")
    pcb = govde.with_suffix(".kicad_pcb")
    return pro, (sch if sch.exists() else None), (pcb if pcb.exists() else None)


def _wire_label_sayilarini_oku(sch_path: Path) -> tuple[int, int]:
    """`.kicad_sch` içindeki üst-seviye `(wire ...)` ve `(label ...)` /
    `(global_label ...)` bloklarını sayar — `sch_wire.py`'nin "0-wire
    defekti" tespitiyle AYNI ölçüt (bkz. Changelog 2026-07-31 P0 notu)."""
    metin = sch_path.read_text(encoding="utf-8")
    wire_sayisi = metin.count("(wire ")
    label_sayisi = metin.count("(label ") + metin.count("(global_label ") + metin.count("(hierarchical_label ")
    return wire_sayisi, label_sayisi


def faz_ortam(kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ -1: Ortam ön kontrolü ===")
    sonuclar = tum_araclari_kontrol_et(kicad_cli)
    for durum in sonuclar:
        print(" ", durum.satir())
    kritik = {"KiCad CLI"}
    kritik_gecti = all(d.gecti_mi for d in sonuclar if d.isim in kritik)
    if not kritik_gecti:
        print("KRİTİK ARAÇ EKSİK (KiCad CLI) — devam edilemiyor, bkz. KURULUM.md.")
        return False
    eksikler = [d.isim for d in sonuclar if not d.gecti_mi]
    if eksikler:
        print(f"Opsiyonel araçlar eksik ({', '.join(eksikler)}) — ilgili fazlar bu makinede atlanacak/sınırlı çalışacak.")
    return True


def faz_sematik(sch_path: Path, kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ 2-3: Şematik + ERC ===")
    wire_n, label_n = _wire_label_sayilarini_oku(sch_path)
    if wire_n == 0 and label_n > 0:
        print(f"  UYARI: 0-wire deseni ({wire_n} wire / {label_n} label) — "
              f"'python rewire.py \"{sch_path}\" --write' ile gerçek wire'a çevrilmesi önerilir.")
    else:
        print(f"  wire={wire_n}, label={label_n}")

    rapor = erc_calistir(str(sch_path), kicad_cli=kicad_cli)
    ihlaller = _erc_ihlallerini_topla(rapor)
    for v in ihlaller:
        print(f"  [{v.get('severity', '?')}] {v.get('type', '')}: {v.get('description', '')}")
    temiz = _erc_temiz_mi(rapor)
    print(f"  ERC: {'TEMİZ (sadece uyarı olabilir)' if temiz else 'HATA VAR'} ({len(ihlaller)} bulgu)")
    return temiz


def faz_drc(pcb_path: Path, kicad_cli: Optional[str]) -> bool:
    print("\n=== FAZ 5: DRC kapısı ===")
    rapor = drc_calistir(str(pcb_path), kicad_cli=kicad_cli)
    for satir in drc_raporunu_ozetle(rapor):
        print(" ", satir)
    temiz = drc_temiz_mi(rapor)
    if not temiz:
        baglantisiz = _drc_baglantisiz_netler(rapor)
        if baglantisiz:
            print(f"  Bağlantısız netler: {', '.join(baglantisiz)} — bu netler routelanmamış;"
                  f" pcbnew'de iz çizimi (routing) tamamlanmadan DRC temizlenemez.")
    print(f"  DRC: {'TEMİZ (sadece uyarı olabilir)' if temiz else 'HATA VAR'}")
    return temiz


def faz_uretim(pcb_path: Path, sch_path: Path, project_dir: Path) -> int:
    print("\n=== FAZ 7: Üretim çıktıları (uretim_ciktilari_cli) ===")
    import shutil
    if shutil.which("kibot") is None:
        print("  UYARI: KiBot PATH'te bulunamadı (bkz. KURULUM.md madde 8).")
        print("  Üretim çıktıları (Gerber/BOM/CPL) KiBot ile üretilir;")
        print("  kurmak için: pip install kibot")
        print("  KiBot kurulmadan üretim çıktısı ÜRETİLEMEZ — DRC/ERC temiz olsa bile.")
        return 1
    import uretim_ciktilari_cli

    return uretim_ciktilari_cli.main([
        str(pcb_path), str(sch_path),
        "--kibot-config", str(project_dir / "kibot.yaml"),
        "--cikti-dizini", str(project_dir / "uretim"),
    ])


def cmd_run(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"HATA: proje dizini bulunamadı: {project_dir}")
        return 2

    if not faz_ortam(args.kicad_cli):
        return 1

    scratch_dir = scratch_olustur(str(project_dir))
    print(f"\nScratch çalışma alanı: {scratch_dir}")
    print("  Kanonik proje dosyaları bu oturumda DEĞİŞTİRİLMEYECEK.")
    print(f"  Kanonik konuma yazmak için: python main.py promote --project-dir \"{project_dir}\" --scratch-id {scratch_dir.name}")

    pro, sch, pcb = _proje_dosyalarini_bul(scratch_dir)
    if pro is None:
        # Kullanıcıya doğru --project-dir ipucunu KANONİK ağaçtan göster —
        # scratch içi bir yol göstermek yanıltıcı olurdu (ephemeral, promote
        # edilmeden kaybolur).
        alt_adaylar = sorted(project_dir.rglob("*.kicad_pro"))
        print(f"HATA: {project_dir} içinde tam olarak 1 adet .kicad_pro bulunamadı — hangi projeyi çalıştıracağım belirsiz.")
        if len(alt_adaylar) == 1:
            print(f"  İPUCU: proje dosyası alt klasörde bulundu: {alt_adaylar[0].parent}.")
            print(f"         --project-dir \"{alt_adaylar[0].parent}\" ile çalıştırın.")
        elif len(alt_adaylar) > 1:
            print("  İPUCU: birden fazla .kicad_pro alt klasörde bulundu:")
            for aday in alt_adaylar:
                print(f"         - {aday.parent}")
            print("         Hangi projeyi çalıştıracağınızı --project-dir ile açıkça belirtin.")
        return 2
    print(f"\nProje: {pro.name}  [scratch-id={scratch_dir.name}]")

    sematik_temiz = True
    if sch is not None:
        sematik_temiz = faz_sematik(sch, args.kicad_cli)
    else:
        print("\n=== FAZ 2-3: Şematik + ERC === \n  ATLANDI: .kicad_sch bulunamadı")

    drc_temiz = True
    if pcb is not None:
        drc_temiz = faz_drc(pcb, args.kicad_cli)
    else:
        print("\n=== FAZ 5: DRC kapısı === \n  ATLANDI: .kicad_pcb bulunamadı")

    if not (sematik_temiz and drc_temiz):
        print("\nSONUÇ: FAIL — ERC/DRC hatası temizlenmeden üretime geçilmez.")
        return 1

    if args.produce:
        if sch is None or pcb is None:
            print("\nHATA: --produce için hem .kicad_sch hem .kicad_pcb gerekli.")
            return 2
        kod = faz_uretim(pcb, sch, scratch_dir)
        print(f"\nSONUÇ: {'PASS' if kod == 0 else 'FAIL'} (üretim çıktısı kodu={kod})")
        return kod

    print("\nSONUÇ: PASS (ERC/DRC temiz, scratch üzerinde). Kanonik konuma yazmak için "
          f"'python main.py promote --project-dir \"{project_dir}\" --scratch-id {scratch_dir.name}' çalıştırın.")
    return 0


# ------------------------------------------------------------------
# promote — scratch -> kanonik yükseltme kapısı (GÖREV 3 + 7)
# ------------------------------------------------------------------

def _dosya_sha256(yol: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(yol.read_bytes())
    return h.hexdigest()


def _ruleset_hash(scratch_dir: Path) -> str:
    """Bu promotion'da geçerli olan kural setinin (MASTER_RULEBOOK.md +
    varsa proje-özel `.kicad_dru`) TEK bir hash'e indirgenmesi — rapor
    hangi kural setine göre üretildiğini KANITLAR, sadece İDDİA ETMEZ."""
    import hashlib

    h = hashlib.sha256()
    rulebook = Path(__file__).resolve().parent / "MASTER_RULEBOOK.md"
    if rulebook.exists():
        h.update(rulebook.read_bytes())
    for dru in sorted(scratch_dir.glob("*.kicad_dru")):
        h.update(dru.read_bytes())
    return h.hexdigest()


def _komut_hash(argv: list) -> str:
    import hashlib

    return hashlib.sha256(" ".join(argv).encode("utf-8")).hexdigest()


def _otonom_commit_at(project_dir: Path, mesaj: str) -> bool:
    """FAZ -0.5 otonom commit kuralının promote karşılığı: `project_dir`
    bir git deposu İÇİNDEYSE `git add`/`git commit` çalıştırır. Depo
    değilse (veya git yoksa) sessizce False döner — promotion'ın BAŞARISI
    buna bağlı DEĞİLDİR, dosyalar zaten kanonik konuma kopyalanmış olur;
    commit sadece ek bir geri-alınabilirlik katmanıdır."""
    import subprocess

    try:
        kok = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if kok.returncode != 0:
            return False
        subprocess.run(["git", "-C", str(project_dir), "add", "."], check=True, timeout=30)
        subprocess.run(["git", "-C", str(project_dir), "commit", "-m", mesaj], check=True, timeout=30)
        return True
    except (OSError, ImportError):
        return False
    except Exception:
        # subprocess.SubprocessError alt sınıfları (CalledProcessError,
        # TimeoutExpired) dahil — commit'in başarısız olması promotion'ı
        # GERİ ALMAZ (dosyalar zaten kanonik konumda), sadece raporlanır.
        return False


def cmd_promote(args: argparse.Namespace) -> int:
    print("\n=== PROMOTE: scratch -> kanonik ===")
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"HATA: proje dizini bulunamadı: {project_dir}")
        return 2

    scratch_id = args.scratch_id
    if scratch_id is None:
        adaylar = scratch_listele(str(project_dir))
        if not adaylar:
            print("HATA: hiç scratch bulunamadı — önce 'python main.py run' çalıştırın.")
            return 2
        scratch_id = adaylar[0]
        print(f"  --scratch-id verilmedi, en yeni scratch kullanılıyor: {scratch_id}")

    scratch_dir = scratch_kok_dizini(str(project_dir)) / scratch_id
    if not scratch_dir.is_dir():
        print(f"HATA: scratch bulunamadı: {scratch_dir}")
        return 2

    pro, sch, pcb = _proje_dosyalarini_bul(scratch_dir)
    if pro is None or pcb is None:
        print("PROMOTION RED: scratch içinde tek bir .kicad_pro + .kicad_pcb bulunamadı.")
        return 2

    kapilar_gecti = True
    red_nedenleri: list = []

    # (1) taze DRC/ERC
    sematik_temiz = True
    if sch is not None:
        sematik_temiz = faz_sematik(sch, args.kicad_cli)
        if not sematik_temiz:
            kapilar_gecti = False
            red_nedenleri.append("ERC temiz değil")

    drc_temiz = faz_drc(pcb, args.kicad_cli)
    if not drc_temiz:
        kapilar_gecti = False
        red_nedenleri.append("DRC temiz değil")

    # (2) bağımsız verifier — proje-özel kontrat, KiCad DRC'den BAĞIMSIZ
    print("\n=== Bağımsız doğrulama (proje-özel kontrat) ===")
    dogrulama_ozeti = bagimsiz_dogrulama_calistir(str(pcb), str(scratch_dir))
    for k in dogrulama_ozeti["kontroller"]:
        print(f"  [{k['durum']}] {k['kontrol']} (taranan={k['taranan']}, ihlal={k['ihlal_sayisi']})")
    if not dogrulama_temiz_mi(dogrulama_ozeti):
        kapilar_gecti = False
        red_nedenleri.append("bağımsız verifier (proje-özel kontrat) FAIL")
    kapsam_disi = kapsam_yok_maddeleri(dogrulama_ozeti)
    if kapsam_disi:
        print(f"  UYARI (KAPSAM_YOK — kontrol EDİLEMEDİ, PASS/FAIL sayılmadı): {', '.join(kapsam_disi)}")

    # (2b) karar birimleri kapısı — GÖREV 7
    print("\n=== Karar birimleri ===")
    kararlar = kararlari_yukle(str(scratch_dir))
    acik_kararlar = kabul_edilmemis_kararlari_bul(kararlar)
    if acik_kararlar:
        kapilar_gecti = False
        red_nedenleri.append(
            "kapanmamış kararlar: " + ", ".join(f"{k.karar_id}({k.durum.value})" for k in acik_kararlar)
        )
        for k in acik_kararlar:
            print(f"  [{k.durum.value}] {k.karar_id}: {k.soru}")
    elif kararlar:
        print(f"  {len(kararlar)} karar, hepsi KABUL_EDILDI.")
    else:
        print("  (bu projede hiç karar_birimleri.json kaydı yok — bu kapı atlanıyor)")

    if not kapilar_gecti:
        print("\nSONUÇ: PROMOTION RED")
        for sebep in red_nedenleri:
            print(f"  - {sebep}")
        print(f"  Kanonik dosyaya HİÇBİR ŞEY yazılmadı. Scratch olduğu gibi bırakıldı: {scratch_dir}")
        return 1

    # (3) hash'li rapor + kanonik kopyalama + otonom commit
    board_hash = _dosya_sha256(pcb)
    ruleset_hash = _ruleset_hash(scratch_dir)
    komut_argv = ["main.py", "promote", "--project-dir", str(project_dir), "--scratch-id", scratch_id]
    komut_hash = _komut_hash(komut_argv)

    rapor_dir = project_dir / "DOCS" / "07_Dogrulama"
    rapor_dir.mkdir(parents=True, exist_ok=True)
    zaman = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rapor_yolu = rapor_dir / f"promotion_{zaman}.json"
    rapor = {
        "zaman_utc": zaman,
        "scratch_id": scratch_id,
        "board_sha256": board_hash,
        "ruleset_sha256": ruleset_hash,
        "komut_sha256": komut_hash,
        "komut": komut_argv,
        "erc_temiz": sematik_temiz,
        "drc_temiz": drc_temiz,
        "bagimsiz_dogrulama": dogrulama_ozeti,
        "karar_sayisi": len(kararlar),
        "sonuc": "PROMOTED",
    }
    rapor_yolu.write_text(json.dumps(rapor, indent=2, ensure_ascii=False), encoding="utf-8")

    kanonige_yukselt(scratch_dir, str(project_dir))

    commit_atildi = _otonom_commit_at(
        project_dir,
        f"FAZ PROMOTE: scratch {scratch_id} kanonige yukseltildi (board={board_hash[:12]})",
    )

    print(f"\nSONUÇ: PROMOTED — rapor: {rapor_yolu}")
    print(f"  board_sha256={board_hash[:16]}...  ruleset_sha256={ruleset_hash[:16]}...  komut_sha256={komut_hash[:16]}...")
    print(f"  {'git commit atıldı.' if commit_atildi else 'git deposu değil/commit atılamadı — dosyalar yine de kanonik konumda.'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="komut", required=True)

    run = sub.add_parser("run", help="ortam + şematik/ERC + DRC kapısını çalıştırır (opsiyonel: üretim çıktıları)")
    run.add_argument("--project-dir", default=".", help="proje kök dizini (.kicad_pro'nun bulunduğu yer)")
    run.add_argument("--produce", action="store_true", help="ERC/DRC temizse Gerber/BOM/CPL de üret")
    run.add_argument("--kicad-cli", help="kicad-cli(.exe) tam yolu; KICAD_CLI ortam değişkenini ezer")
    run.set_defaults(func=cmd_run)

    promote = sub.add_parser(
        "promote",
        help="scratch -> kanonik yükseltme kapısı (DRC/ERC + proje-özel kontrat + karar birimleri)",
    )
    promote.add_argument("--project-dir", required=True, help="proje kök dizini (kanonik)")
    promote.add_argument("--scratch-id", default=None, help="yükseltilecek scratch id; verilmezse en yeni scratch kullanılır")
    promote.add_argument("--kicad-cli", help="kicad-cli(.exe) tam yolu; KICAD_CLI ortam değişkenini ezer")
    promote.set_defaults(func=cmd_promote)

    return ap


def main(argv: Optional[list[str]] = None) -> int:
    _konsol_utf8_ayarla()
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
