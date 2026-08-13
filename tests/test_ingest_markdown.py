from __future__ import annotations

from pathlib import Path

from questioncrator.ingest import markdown

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"


def test_dort_soru_okunur():
    sorular = markdown.load_pool(VERI)
    assert len(sorular) == 4
    assert [s.id for s in sorular] == ["s1", "s2", "s3", "s4"]


def test_alanlar_dogru_ayrisir():
    sorular = markdown.load_pool(VERI)
    ilk = sorular[0]
    assert ilk.text == "f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz."
    assert ilk.recipe == "diff(3*x**2 + 5*x - 2, x)"
    assert ilk.objective == "turev.polinom"
    assert ilk.needs_review is False


def test_konu_bagimsiz_receteler_korunur():
    sorular = markdown.load_pool(VERI)
    assert sorular[1].recipe == "limit(sin(3*x)/x, x, 0)"
    assert sorular[2].recipe == "Matrix([[2, 1], [4, 3]]).det()"


def test_recetesiz_soru_elle_kontrol_kuyruguna_dusuyor():
    sorular = markdown.load_pool(VERI)
    assert sorular[3].recipe is None
    assert sorular[3].needs_review is True


def test_bos_icerik_bos_liste_verir():
    assert markdown.parse_pool("") == []
    assert markdown.parse_pool("\n---\n   \n") == []


def test_cok_satirli_soru_metni_korunur():
    icerik = """### Soru
Birinci satır.
İkinci satır.

### Cevap
2 + 2
"""
    (soru,) = markdown.parse_pool(icerik)
    assert soru.text == "Birinci satır.\nİkinci satır."
    assert soru.recipe == "2 + 2"
