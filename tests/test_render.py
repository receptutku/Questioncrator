from __future__ import annotations

import pytest

from questioncrator.models import Parameter, Template
from questioncrator.templating.render import render_recipe, render_text


def sablon(iskelet: str, adet: int = 3, recete: str = "{p0}") -> Template:
    return Template(
        id="t1", source_id="s1", skeleton=iskelet, recipe=recete,
        parameters=tuple(Parameter(f"p{i}", -9, 9, (0,)) for i in range(adet)),
    )


def test_latex_suslu_parantezleri_bozulmaz():
    t = sablon(r"$\lim_{x \to 0} \frac{\sin({p0}x)}{x}$ limitini hesaplayınız.", 1)
    beklenen = r"$\lim_{x \to 0} \frac{\sin(4x)}{x}$ limitini hesaplayınız."
    assert render_text(t, {"p0": 4}) == beklenen


def test_cift_suslu_icinde_yer_tutucu():
    t = sablon(r"$\frac{{p0}}{x}$", 1)
    assert render_text(t, {"p0": 7}) == r"$\frac{7}{x}$"


@pytest.mark.parametrize(
    ("degerler", "beklenen"),
    [
        ((3, 5, 2), "f(x) = 3x^2 + 5x - 2"),
        ((-4, -4, -4), "f(x) = -4x^2 - 4x + 4"),
        ((1, -1, 5), "f(x) = x^2 - x - 5"),
        ((-1, 1, -1), "f(x) = -x^2 + x + 1"),
    ],
)
def test_isaret_ve_katsayi_sadelesir(degerler, beklenen):
    t = sablon("f(x) = {p0}x^2 + {p1}x - {p2}")
    assert render_text(t, dict(zip(["p0", "p1", "p2"], degerler, strict=True))) == beklenen


def test_esittir_sonrasi_eksi_eksi_arti_yazilmaz():
    t = sablon("y = -{p0}x", 1)
    assert render_text(t, {"p0": -3}) == "y = 3x"


def test_carpma_sonrasi_negatif_parantezlenir():
    t = sablon(r"2 \cdot {p0} ve 5 * {p1}", 2)
    assert render_text(t, {"p0": -3, "p1": -1}) == r"2 \cdot (-3) ve 5 * (-1)"


def test_liste_icinde_negatif_ve_bir_korunur():
    t = sablon("A = [[{p0}, {p1}], [{p2}, 2]]")
    assert render_text(t, {"p0": -4, "p1": 1, "p2": -1}) == "A = [[-4, 1], [-1, 2]]"


def test_eksik_baglama_hata_verir():
    with pytest.raises(KeyError):
        render_text(sablon("{p0}", 1), {})


# --- uç durumlar ---


def test_basta_negatif_deger():
    assert render_text(sablon("{p0}x + 1", 1), {"p0": -5}) == "-5x + 1"
    assert render_text(sablon("{p0}x + 1", 1), {"p0": -1}) == "-x + 1"


def test_eksi_sonrasi_sifir_oldugu_gibi_yazilir():
    assert render_text(sablon("x - {p0}", 1), {"p0": 0}) == "x - 0"


def test_latex_frac_iki_yer_tutucu():
    t = sablon(r"\frac{{p0}}{{p1}}", 2)
    assert render_text(t, {"p0": -3, "p1": 1}) == r"\frac{-3}{1}"


# --- bağlama türü sertleştirmesi ---


@pytest.mark.parametrize("deger", ["3", "x)+(y", 2.0, True, False, None])
def test_render_text_int_olmayan_baglamayi_reddeder(deger):
    with pytest.raises(TypeError):
        render_text(sablon("{p0}x", 1), {"p0": deger})


@pytest.mark.parametrize("deger", ["3", "__import__('os')", 2.0, True, False, None])
def test_render_recipe_int_olmayan_baglamayi_reddeder(deger):
    with pytest.raises(TypeError):
        render_recipe(sablon("{p0}", 1), {"p0": deger})


# --- render_recipe ---


def test_render_recipe_yalniz_yer_tutucuyu_degistirir():
    t = sablon("x", 2, recete="{p0} + {q} + {} + {{p1}} + {p1}**2")
    assert render_recipe(t, {"p0": 3, "p1": -2}) == "(3) + {q} + {} + {(-2)} + (-2)**2"


def test_render_recipe_eksik_baglama_hata_verir():
    with pytest.raises(KeyError):
        render_recipe(sablon("x", 1, recete="{p0}"), {})
