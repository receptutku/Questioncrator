from __future__ import annotations

import pytest
import sympy

from questioncrator import mathenv
from questioncrator.models import Parameter, SourceQuestion, Template
from questioncrator.templating import extract, render


def kaynak(text: str, recipe: str) -> SourceQuestion:
    return SourceQuestion(id="s1", text=text, recipe=recipe, objective="k")


def test_katsayilar_parametrelesir():
    s = kaynak(
        "f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz.",
        "diff(3*x**2 + 5*x - 2, x)",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "diff({p0}*x**2 + {p1}*x - {p2}, x)"
    assert t.skeleton == "f(x) = {p0}x^2 + {p1}x - {p2} fonksiyonunun türevini bulunuz."
    assert [p.name for p in t.parameters] == ["p0", "p1", "p2"]
    assert t.seed_bindings == {"p0": 3, "p1": 5, "p2": 2}


def test_us_parametrelesmez():
    s = kaynak("x^2 ifadesi", "diff(x**2, x)")
    with pytest.raises(extract.NoParametersFound):
        extract.extract_template(s, "t1")


def test_ayni_deger_ayni_parametreye_baglanir():
    s = kaynak("3 ve 3 sayıları", "3 + 3*x")
    t = extract.extract_template(s, "t1")
    assert t.recipe == "{p0} + {p0}*x"
    assert len(t.parameters) == 1


def test_konu_bagimsiz_limit_recetesi():
    s = kaynak(
        "$\\lim_{x \\to 0} \\frac{\\sin(3x)}{x}$ limitini hesaplayınız.",
        "limit(sin(3*x)/x, x, 0)",
    )
    t = extract.extract_template(s, "t1")
    # 0 yapısaldır: parametreleşmez. Yalnız 3 parametre olur.
    assert t.recipe == "limit(sin({p0}*x)/x, x, 0)"
    assert len(t.parameters) == 1


def test_konu_bagimsiz_matris_recetesi():
    s = kaynak(
        "A = [[2, 1], [4, 3]] matrisinin determinantını bulunuz.",
        "Matrix([[2, 1], [4, 3]]).det()",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "Matrix([[{p0}, {p1}], [{p2}, {p3}]]).det()"
    assert t.seed_bindings == {"p0": 2, "p1": 1, "p2": 4, "p3": 3}


def test_recetesiz_kaynak_reddedilir():
    with pytest.raises(ValueError):
        extract.extract_template(SourceQuestion(id="s1", text="metin", recipe=None), "t1")


def test_tohum_islem_sayisi_kaydedilir():
    s = kaynak("f(x) = 3x^2 + 5x", "diff(3*x**2 + 5*x, x)")
    t = extract.extract_template(s, "t1")
    # diff(3x^2+5x) = 6x+5 -> Add(Mul(6,x), 5) : 2 işlem
    assert t.seed_answer_ops == sympy.sympify("6*x + 5").count_ops()


def test_render_metin_ve_recete():
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="f(x) = {p0}x^2 + {p1}x",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
    )
    assert render.render_text(t, {"p0": 4, "p1": -2}) == "f(x) = 4x^2 - 2x"
    assert render.render_recipe(t, {"p0": 4, "p1": -2}) == "diff((4)*x**2 + (-2)*x, x)"


def test_yildiz_us_gosterimi_metinde_korunur():
    """`**2` üs gösterimi metinde de yapısaldır; başka bir yerdeki aynı
    değerli katsayı parametreleşirken üs değişmemelidir."""
    s = kaynak(
        "f(x) = x**2 + 2y ifadesidir.",
        "x**2 + 2*y",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "x**2 + {p0}*y"
    assert t.skeleton == "f(x) = x**2 + {p0}y ifadesidir."
    assert t.seed_bindings == {"p0": 2}


def test_coklu_satir_recete_dogru_degistirilir():
    """İki satırlı reçetede her satırdaki jetonlar doğru konumdan değişmeli."""
    s = kaynak(
        "A = [[3, 1], [4, 5]] matrisinin determinantını bulunuz.",
        "Matrix([[3, 1],\n[4, 5]]).det()",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "Matrix([[{p0}, {p1}],\n[{p2}, {p3}]]).det()"
    assert t.seed_bindings == {"p0": 3, "p1": 1, "p2": 4, "p3": 5}


def test_render_recete_negatif_degeri_parantezler():
    """Parantezsiz `-3**2` = -9 olurdu; parantezli `(-3)**2` = 9. Kritik."""
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}",
        recipe="{p0}**2",
        parameters=(Parameter("p0", -9, 9, (0,)),),
        seed_bindings={"p0": 3},
        seed_answer_ops=1,
    )
    assert mathenv.parse(render.render_recipe(t, {"p0": -3})) == 9
