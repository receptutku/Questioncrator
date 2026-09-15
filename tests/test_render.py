from __future__ import annotations

import itertools
import random
import re

import pytest
import sympy

from questioncrator import mathenv
from questioncrator.generation.sampler import sample_bindings
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


# --- kural 1: kuvvet ve faktöriyelde işarete dokunulmaz ---


@pytest.mark.parametrize(
    ("iskelet", "beklenen"),
    [
        ("x - {p0}^2", "x - (-3)^2"),
        ("y = {p0}^2", "y = (-3)^2"),
        ("{p0}^2 + 1", "(-3)^2 + 1"),
        ("x + {p0}²", "x + (-3)²"),
        ("{p0}³", "(-3)³"),
        ("x - {p0}!", "x - (-3)!"),
    ],
)
def test_kuvvet_ve_faktoriyelde_negatif_parantezlenir(iskelet, beklenen):
    assert render_text(sablon(iskelet, 1), {"p0": -3}) == beklenen


# --- kural 2-4: ikili ve tekli işaretler ---


def test_madde_isaretli_liste_isareti_korur():
    t = sablon("Seçenekler:\n- {p0}\n- {p1}", 2)
    assert render_text(t, {"p0": -3, "p1": -4}) == "Seçenekler:\n- (-3)\n- (-4)"


def test_metin_basinda_tekli_eksi_parantezlenir():
    assert render_text(sablon("- {p0}", 1), {"p0": -3}) == "- (-3)"


def test_satir_basinda_ikili_eksi_sayilmaz():
    t = sablon("a - 1\n- {p0}x", 1)
    assert render_text(t, {"p0": -3}) == "a - 1\n- (-3)x"


def test_ikili_arti_ve_eksi_sadelesir():
    assert render_text(sablon("a + {p0}", 1), {"p0": -3}) == "a - 3"
    assert render_text(sablon("f(x) - {p0}", 1), {"p0": -3}) == "f(x) + 3"
    assert render_text(sablon(r"\frac{1}{2} - {p0}", 1), {"p0": -3}) == r"\frac{1}{2} + 3"


@pytest.mark.parametrize(
    ("iskelet", "beklenen"),
    [
        ("+ {p0}x", "-3x"),
        ("y = + {p0}", "y = -3"),
        ("({p0} + 1)", "(-3 + 1)"),
    ],
)
def test_bastaki_arti_atilir_negatif(iskelet, beklenen):
    assert render_text(sablon(iskelet, 1), {"p0": -3}) == beklenen


def test_bastaki_arti_atilir_pozitif():
    assert render_text(sablon("+ {p0}x", 1), {"p0": 3}) == "3x"
    assert render_text(sablon("y = +{p0}", 1), {"p0": 3}) == "y = 3"
    assert render_text(sablon("a + {p0}", 1), {"p0": 3}) == "a + 3"


# --- kural 5-7 ---


def test_us_ve_alt_indis_icinde_suslu_negatif():
    assert render_text(sablon("x^{p0}", 1), {"p0": -2}) == "x^{-2}"
    assert render_text(sablon("a_{p0}", 1), {"p0": -2}) == "a_{-2}"
    assert render_text(sablon("x^{p0}", 1), {"p0": 2}) == "x^2"


@pytest.mark.parametrize(
    "iskelet",
    ["x < {p0}", "x > {p0}", r"x \le {p0}", r"x \geq {p0}", "|{p0}|", "a; {p0}", "${p0}$"],
)
def test_acicilardan_sonra_ciplak_negatif(iskelet):
    beklenen = iskelet.replace("{p0}", "-3")
    assert render_text(sablon(iskelet, 1), {"p0": -3}) == beklenen


@pytest.mark.parametrize(
    "iskelet",
    [r"6 \div {p0}", "6 ÷ {p0}", r"2 \pm {p0}", "3 − {p0}", r"2 \times {p0}", "sayı {p0} olsun"],
)
def test_diger_her_yerde_negatif_parantezlenir(iskelet):
    beklenen = iskelet.replace("{p0}", "(-3)")
    assert render_text(sablon(iskelet, 1), {"p0": -3}) == beklenen


# --- 1 katsayısı ---


@pytest.mark.parametrize(
    "iskelet",
    [
        r"${p0}\cdot x$",
        "{p0}cm",
        r"{p0}\,\text{cm}",
        r"{p0}\%",
        r"{p0}\le x",
        r"\left( {p0}\right)",
        r"{p0}\times 10^3",
        "{p0}er elma",
        "{p0}xy",
    ],
)
def test_bir_katsayi_olmayan_yerde_yazilir(iskelet):
    assert render_text(sablon(iskelet, 1), {"p0": 1}) == iskelet.replace("{p0}", "1")


@pytest.mark.parametrize(
    ("iskelet", "bir", "eksi_bir"),
    [
        ("{p0}x", "x", "-x"),
        ("{p0}(x+1)", "(x+1)", "-(x+1)"),
        (r"{p0}\sqrt{x}", r"\sqrt{x}", r"-\sqrt{x}"),
        (r"{p0}\sin x", r"\sin x", r"-\sin x"),
        (r"{p0}\pi", r"\pi", r"-\pi"),
        (r"{p0}\left(x\right)", r"\left(x\right)", r"-\left(x\right)"),
    ],
)
def test_bir_katsayi_degisken_ve_izinli_komut_onunde_silinir(iskelet, bir, eksi_bir):
    assert render_text(sablon(iskelet, 1), {"p0": 1}) == bir
    assert render_text(sablon(iskelet, 1), {"p0": -1}) == eksi_bir


def test_eksi_bir_birim_onunde_yazilir():
    assert render_text(sablon("{p0}cm", 1), {"p0": -1}) == "-1cm"


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


# --- tutarlılık: öğrencinin gördüğü metin reçeteyle çelişmez ---


def _ifadeye(metin: str) -> str:
    """Yalnız aşağıdaki iskelet kümesini kapsayan metin -> reçete dönüşümü."""
    s = metin.replace("$", "").replace(r"\cdot", "*")
    s = s.replace("²", "**2").replace("³", "**3").replace("^", "**")
    return re.sub(r"(\d|\))\s*([a-z(])", r"\1*\2", s)


def _liste_ifadeye(metin: str) -> str:
    satirlar = metin.split("\n")[1:]
    return "[" + ", ".join(_ifadeye(satir.removeprefix("- ")) for satir in satirlar) + "]"


TUTARLILIK_ORNEKLERI = [
    ("x - {p0}^2", "x - {p0}**2", _ifadeye),
    ("{p0}^2 + {p1}²", "{p0}**2 + {p1}**2", _ifadeye),
    ("{p0}x^2 + {p1}x - {p2}", "{p0}*x**2 + {p1}*x - {p2}", _ifadeye),
    ("x - {p0}!", "x - factorial({p0})", _ifadeye),
    (r"${p0} \cdot x - {p1}$", "{p0}*x - {p1}", _ifadeye),
    ("y - {p0}(x - {p1})", "y - {p0}*(x - {p1})", _ifadeye),
    ("Seçenekler:\n- {p0}\n- {p1}", "[{p0}, {p1}]", _liste_ifadeye),
]


def _baglamalar(t: Template) -> list[dict[str, int]]:
    adlar = [p.name for p in t.parameters]
    rastgele = [sample_bindings(t, random.Random(tohum)) for tohum in range(20)]
    uclar = [
        dict(zip(adlar, d, strict=True))
        for d in itertools.product((-1, 1, -3), repeat=len(adlar))
    ]
    return [b for b in rastgele if b is not None] + uclar


@pytest.mark.parametrize(("iskelet", "recete", "donustur"), TUTARLILIK_ORNEKLERI)
def test_metin_ve_recete_ayni_degeri_verir(iskelet, recete, donustur):
    adet = len(set(re.findall(r"\{(p\d+)\}", recete)))
    t = sablon(iskelet, adet, recete=recete)
    for baglama in _baglamalar(t):
        metin = render_text(t, baglama)
        metinden = mathenv.parse(donustur(metin))
        receteden = mathenv.parse(render_recipe(t, baglama))
        esit = metinden == receteden or (
            isinstance(receteden, sympy.Expr) and sympy.simplify(metinden - receteden) == 0
        )
        assert esit, f"{baglama}: {metin!r} -> {metinden} != {receteden}"
