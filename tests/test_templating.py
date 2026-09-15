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
    # 2 metinde üs olarak da geçtiği (`x^2`) için tamamen sabit kalır.
    assert t.recipe == "diff({p0}*x**2 + {p1}*x - 2, x)"
    assert t.skeleton == "f(x) = {p0}x^2 + {p1}x - 2 fonksiyonunun türevini bulunuz."
    assert [p.name for p in t.parameters] == ["p0", "p1"]
    assert t.seed_bindings == {"p0": 3, "p1": 5}


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
    """`**2` üs gösterimi metinde güvensiz bağlamdır; aynı değerli katsayı
    da dahil 2 hiçbir yerde parametreleşmez."""
    s = kaynak(
        "f(x) = x**2 + 2y + 3 ifadesidir.",
        "x**2 + 2*y + 3",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "x**2 + 2*y + {p0}"
    assert t.skeleton == "f(x) = x**2 + 2y + {p0} ifadesidir."
    assert t.seed_bindings == {"p0": 3}


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


def test_suslu_us_metinde_parametrelesmez():
    """`x^{2}` içindeki üs yapısaldır; reçetede `**2` parametreleşmediği gibi
    metinde de parametreleşmemelidir."""
    s = kaynak("$x^{2} + 3x$ ifadesi", "x**2 + 3*x")
    t = extract.extract_template(s, "t1")
    assert t.recipe == "x**2 + {p0}*x"
    assert t.skeleton == "$x^{2} + {p0}x$ ifadesi"


def test_ayni_sayi_hem_us_hem_katsayi():
    """Değer metinde tek bir güvensiz geçişte bile tamamen sabit kalır."""
    s = kaynak("$x^{2} + 2x + 3$", "x**2 + 2*x + 3")
    t = extract.extract_template(s, "t1")
    assert t.recipe == "x**2 + 2*x + {p0}"
    assert t.skeleton == "$x^{2} + 2x + {p0}$"


@pytest.mark.parametrize(
    ("metin", "recete"),
    [
        ("$e^{2x}$ türevini bulunuz.", "diff(exp(2*x), x)"),
        (r"$\sqrt[3]{x} + 3x$", "diff(cbrt(x) + 3*x, x)"),
        ("$x_{2} + 2$", "2"),
        ("x² + 2x", "x**2 + 2*x"),
        ("Bir kalem 2,5 TL", "Rational(5, 2)"),
        ("Bir kalem 2.5 TL", "Rational(5, 2)"),
    ],
)
def test_guvensiz_baglamdaki_deger_hicbir_yerde_parametrelesmez(metin, recete):
    with pytest.raises(extract.NoParametersFound):
        extract.extract_template(kaynak(metin, recete), "t1")


def test_baska_sayinin_icinde_gecen_deger_sabit_kalir():
    """`12` içinde `2` geçtiği için 2 sabit kalır; 12 ayrı ve güvenlidir."""
    t = extract.extract_template(kaynak("12 elmanın 2 katı", "2*12 - 12"), "t1")
    assert t.recipe == "2*{p0} - {p0}"
    assert t.skeleton == "{p0} elmanın 2 katı"


def test_metinde_gecmeyen_deger_recetede_parametrelesmez():
    s = kaynak("Bir şişe 1.5 litre ise 4 şişe kaç litre eder?", "Rational(3, 2)*4")
    t = extract.extract_template(s, "t1")
    assert t.recipe == "Rational(3, 2)*{p0}"
    assert t.skeleton == "Bir şişe 1.5 litre ise {p0} şişe kaç litre eder?"


def test_frac_icindeki_sayi_parametrelesmeye_devam_eder():
    s = kaynak(r"$\frac{3}{x^{2}}$", "3/x**2")
    t = extract.extract_template(s, "t1")
    assert t.skeleton == r"$\frac{{p0}}{x^{2}}$"
