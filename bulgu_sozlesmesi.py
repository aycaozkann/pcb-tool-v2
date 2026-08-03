"""
bulgu_sozlesmesi.py
====================
Tüm kontrol fonksiyonları için ORTAK sonuç sözleşmesi.

NEDEN BU DOSYA VAR (arkadaşın Otonom-PCB-Ajani sisteminden alınan ders):
--------------------------------------------------------------------------
Projedeki eski kontrol fonksiyonları (`maske_baraji_kontrolu`,
`z_kontrolu_yap`, `check_reference_plane_continuity` vb.) hep `List[str]`
döndürüyordu: boş liste = "temiz". Ama boş liste İKİ FARKLI durumu da temsil
edebiliyor ve bu ikisi ayırt edilemiyordu:

  1) Gerçekten kontrol edildi ve hiçbir ihlal yok (GERÇEK PASS)
  2) Kontrol edilecek hiçbir öğe bulunamadı — ör. board'da hiç via yok,
     regex hiçbir net'e uymadı, dosya boş geldi (SESSİZ SAHTE PASS)

İkinci durum, "kontrolü çalıştırdım ve 0 sorun buldum" ile "kontrolü hiç
gerçek anlamda çalıştıramadım" arasındaki farkı gizler — bu da rapor
okuyan birine yanlış güven verir.

Bu modül, `taranan` (kaç öğe incelendi) sayısını HER ZAMAN rapora dahil eden
bir `Bulgu` sözleşmesi tanımlar: `taranan == 0` ise durum otomatik olarak
`KAPSAM_YOK` olur, asla sessizce `PASS` sayılmaz.

Yeni kontrol fonksiyonları bu sözleşmeyi kullanmalı. Eski `List[str]` dönen
fonksiyonlar (`pcb_highspeed_escape.py`, `mekanik_dxf_koprusu.py`,
`kicad_koprusu.py` içindekiler) GERİYE DÖNÜK UYUMLULUK için değiştirilmedi
— ama yeni eklenen `pcbnew_koprusu.py` ve `empedans_cozucu.py` gibi
modüller doğrudan bu sözleşmeyi kullanıyor. `bulgu_uret()` ile eski
`List[str]` çıktısını da bu sözleşmeye SARABILIRSIN (bkz. altta).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BulguDurumu(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    KAPSAM_YOK = "KAPSAM_YOK"  # taranan == 0


@dataclass
class Bulgu:
    """Tek bir kontrolün sonucu. `taranan == 0` iken `durum` asla PASS OLAMAZ."""

    kontrol: str
    durum: BulguDurumu
    taranan: int
    ihlaller: List[Dict[str, Any]] = field(default_factory=list)
    detay: str = ""

    def __post_init__(self) -> None:
        if self.taranan == 0 and self.durum != BulguDurumu.KAPSAM_YOK:
            raise ValueError(
                f"{self.kontrol}: taranan=0 iken durum={self.durum} olamaz — "
                "kapsam yoksa durum otomatik KAPSAM_YOK olmalı (bulgu_uret kullan)."
            )

    @property
    def gecti_mi(self) -> bool:
        """Sadece GERÇEKTEN taranıp temiz çıkan kontroller True döner.
        KAPSAM_YOK bilerek False'tur — "kontrol edilmedi" bir başarı değildir."""
        return self.durum == BulguDurumu.PASS


def bulgu_uret(
    kontrol: str,
    taranan: int,
    ihlaller: Optional[List[Dict[str, Any]]] = None,
    detay: str = "",
) -> Bulgu:
    """Standart kurucu: taranan=0 ise otomatik KAPSAM_YOK, aksi halde
    ihlal var mı yok mu bakılarak FAIL/PASS seçilir. Kontrol fonksiyonları
    kendi Bulgu'sunu elle inşa etmek yerine BUNU çağırmalı — `__post_init__`
    denetimini atlamanın tek güvenli yolu budur."""
    ihlaller = ihlaller or []
    if taranan == 0:
        return Bulgu(kontrol, BulguDurumu.KAPSAM_YOK, 0, [], detay or "incelenecek öğe yok")
    durum = BulguDurumu.FAIL if ihlaller else BulguDurumu.PASS
    return Bulgu(kontrol, durum, taranan, ihlaller, detay)


def liste_sonucundan_bulgu_uret(
    kontrol: str,
    eski_liste_sonucu: List[str],
    taranan: int,
    detay: str = "",
) -> Bulgu:
    """Eski `List[str]` dönen kontrol fonksiyonlarının çıktısını bu
    sözleşmeye SARMAK için köprü. `taranan` çağıran tarafından verilmeli
    (eski fonksiyonlar kapsam sayısını raporlamıyordu — bu, geçiş
    döneminde en zayıf halka; taranan'ı doğru vermek çağıranın
    sorumluluğundadır)."""
    ihlaller = [{"mesaj": m} for m in eski_liste_sonucu]
    return bulgu_uret(kontrol, taranan, ihlaller, detay)


def ozet_rapor(bulgular: List[Bulgu]) -> Dict[str, Any]:
    """Birden fazla Bulgu'yu tek bir özet sözlüğe indirger (JSON'a hazır)."""
    return {
        "kontroller": [
            {
                "kontrol": b.kontrol,
                "durum": b.durum.value,
                "taranan": b.taranan,
                "ihlal_sayisi": len(b.ihlaller),
                "ihlaller": b.ihlaller,
                "detay": b.detay,
            }
            for b in bulgular
        ],
        "ozet": {
            durum.value: sum(1 for b in bulgular if b.durum == durum)
            for durum in BulguDurumu
        },
    }
