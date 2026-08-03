"""rewire.py için sınırlı test suite (pytest).

DÜRÜSTLÜK NOTU: `rewire.py`'nin asıl işlevi (`rewire()`) gerçek KiCad sembol
kütüphanelerine (`/usr/share/kicad/symbols/...`, Linux yolu, KURULUM.md
madde 1) ve `kicad-cli`'ye ihtiyaç duyar — `test_sch_wire.py` ile AYNI
disiplinle, bu ortamda uçtan uca ÇALIŞTIRILAMAZ. Bu dosya SADECE saf/
KiCad-bağımsız kısımları (`_u` deterministik UUID üretimi, modülün
sorunsuz import edilmesi) kilitler. Gerçek `rewire(sch, write=True)`
akışı SENİN makinende, gerçek KiCad kapalıyken doğrulanmalıdır.
"""

from __future__ import annotations

from rewire import _u


def test_u_deterministik():
    a = _u("board.kicad_sch", "wire/1")
    b = _u("board.kicad_sch", "wire/1")
    assert a == b


def test_u_farkli_tag_farkli_uuid():
    a = _u("board.kicad_sch", "wire/1")
    b = _u("board.kicad_sch", "wire/2")
    assert a != b
