from __future__ import annotations

import time
import types

import pytest
import sympy

from questioncrator import mathenv


def test_basit_ifade_ayristirilir():
    assert mathenv.parse("3*x**2 + 5*x - 2") == sympy.sympify("3*x**2 + 5*x - 2")


def test_sympy_fonksiyonlari_calisir():
    x = sympy.Symbol("x")
    assert mathenv.parse("diff(3*x**2 + 5*x - 2, x)") == 6 * x + 5


def test_farkli_konudan_recete_de_calisir():
    # Konu bağımsızlığı: ayrıştırıcı hiçbir konuyu ayrıcalıklı görmez.
    assert mathenv.parse("Matrix([[2, 1], [4, 3]]).det()") == 2
    assert mathenv.parse("limit(sin(3*x)/x, x, 0)") == 3


def test_liste_donen_recete_normallesir():
    """`solve` düz Python listesi döndürür; boru hattı her yerde Basic bekler."""
    sonuc = mathenv.parse("solve(2*y + 6, y)")
    assert isinstance(sonuc, sympy.Basic)
    assert list(sonuc) == [-3]


def test_degisebilir_matris_normallesir():
    sonuc = mathenv.parse("Matrix([[1, 2], [3, 4]]) * 2")
    assert isinstance(sonuc, sympy.Basic)


def test_cift_alt_cizgi_reddedilir():
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("(1).__class__")


def test_allowed_namespace_builtinlari_kapali():
    """`_allowed_namespace()` sözlüğünde `__builtins__` boş kalmalı.

    Bu, `parse_expr`'in ad-dönüşüm hattından bağımsız, doğrudan sözlük
    düzeyinde bir garanti; ek önlem (defense-in-depth) olarak tutulur.
    """
    ns = mathenv._allowed_namespace()
    assert ns["__builtins__"] == {}


def test_bilinmeyen_ad_gercek_pythona_ulasmadan_sembolik_kalir():
    """Ad alanında olmayan bir çağrı, gerçek bir Python nesnesine değil,
    sembolik bir sympy `Function`'a bağlanır.

    `parse_expr`'in `auto_symbol` dönüşümü, ad alanında bulunmayan her adı
    -- güvenli ya da tehlikeli fark etmeksizin -- eval'e ulaşmadan önce
    sembolik bir `Function` çağrısına çevirir. Gerçekten çağrılmış olsaydı
    sonuç sembolik bir çağrı olmazdı.
    Not: `open` artık yasak ad listesinde (bkz. `DENIED_NAMES`); bu yüzden
    burada yasaklı olmayan, ad alanında da bulunmayan bir ad kullanılır.
    """
    sonuc = mathenv.parse("bilinmeyen(1)")
    assert isinstance(sonuc, sympy.Basic)
    assert str(sonuc) == "bilinmeyen(1)"


def test_zaman_asimi_yukselir(monkeypatch):
    # Gerçekten pahalı bir SymPy ifadesi kullanmıyoruz: iş parçacığı zorla
    # sonlandırılamadığı için test bitiminde arkada takılı kalırdı.
    def yavas(recipe: str) -> sympy.Basic:
        time.sleep(0.5)
        return sympy.Integer(1)

    monkeypatch.setattr(mathenv, "parse", yavas)
    with pytest.raises(mathenv.EvaluationTimeout):
        mathenv.parse_with_timeout("1", seconds=0.05)


@pytest.mark.parametrize(
    "recete",
    [
        'sympify("_"+"_imp"+"ort_"+"_(\'os\').getcwd()")',
        'S("x")',
        '"abc"',
        "f'{x}'",
        "x.__class__",
        "_x + 1",
        "lambda: 1",
        "[i for i in range(3)]",
        "preview(x)",
        "plot(x)",
        "print_latex(x)",
        "lambdify(x, x)",
        "var(x)",
        "init_session()",
        "exec(x)",
        "open(x)",
        "getattr(x, x)",
        "(y := 3)",
        "1" + "0" * 12,
        "x + " * 600 + "x",
    ],
)
def test_tehlikeli_recete_reddedilir(recete):
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(recete)


def test_kacis_denemesi_kod_calistirmiyor(tmp_path, monkeypatch):
    # Kaçış çalışsaydı dosya oluşurdu.
    hedef = tmp_path / "izi"
    recete = 'sympify("_"+"_imp"+"ort_"+"_(\'os\').mkdir(\'' + str(hedef) + "')\")"
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(recete)
    assert not hedef.exists()


def test_ad_alaninda_modul_ve_yasakli_ad_yok():
    ad_alani = mathenv._allowed_namespace()
    assert not [ad for ad, deger in ad_alani.items() if isinstance(deger, types.ModuleType)]
    assert not (set(ad_alani) & mathenv.DENIED_NAMES)
    assert not [
        ad for ad in ad_alani if ad != "__builtins__" and ad.startswith(mathenv.DENIED_PREFIXES)
    ]


def test_modul_adi_otomatik_sembole_duser_ve_alt_modul_erisilemez():
    # `utilities` bir sympy modülüdür; ad alanında olmadığı için Symbol olur.
    # Symbol'ün `solveset` niteliği yoktur, bu yüzden gerçek Python kodu değil
    # somut bir `AttributeError` çıkar (SystemExit ya da başka bir kaçış değil).
    with pytest.raises(AttributeError):
        mathenv.parse("utilities.solveset")


@pytest.mark.parametrize(
    "recete",
    [
        "diff(3*x**2 + 5*x - 2, x)",
        "Matrix([[2, 1], [4, 3]]).det()",
        "Rational(1, 3) + 2",
        "solve(2*y + 6, y)",
        "x < 3",
        "sqrt(8) and True",
        "123456789012",
        "3.25*x",
    ],
)
def test_mesru_receteler_calismaya_devam_eder(recete):
    mathenv.parse(recete)


# Çalışma anında dizge kuran, tırnaksız kaçış: `Symbol.name` / `srepr(...)`
# Python `str` döndürür; indeksleme + birleştirme ile "__import__('os')..."
# kurulur, `parse_expr` bunu `str` olarak döndürür ve eski `_normalize`
# `sympify(str)` çağırarak sympy'nin builtins'li ikinci eval'ını açardı.
_RCE_PAYLOAD = (
    "a_b.name[1] + a_b.name[1] + imp.name + ort.name + a_b.name[1] + a_b.name[1]"
    " + srepr(x)[6] + srepr(x)[7] + os.name + srepr(x)[7] + srepr(x)[10]"
    " + srepr(Float(1.5))[8] + getcwd.name + srepr(x)[6] + srepr(x)[10]"
)


def test_calisma_aninda_dizge_kuran_kacis_reddedilir():
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(_RCE_PAYLOAD)


def test_kacis_simplify_varyanti_da_reddedilir():
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("simplify(" + _RCE_PAYLOAD + ")")


def test_normalize_dizge_uretmeyi_reddeder():
    # Katman (a): `_normalize` hiçbir koşulda bir dizgeyi sympify'a vermez.
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv._normalize("__import__('os')")
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv._normalize(b"kod")


def test_parse_asla_dizge_dondurmez():
    sonuc = mathenv.parse("x + 1")
    assert isinstance(sonuc, sympy.Basic)
    assert not isinstance(sonuc, (str, bytes))


def test_degerlendirme_bayragi_icinde_sympify_dizge_ayristiramaz(tmp_path):
    # Katman (b): reçete değerlendirme bayrağı açıkken sympy'nin kendi
    # `sympify`i bir dizgeyi yeniden ayrıştıramaz; kod çalışmadan durur.
    hedef = tmp_path / "izi_b"
    kotu = "__import__('os').mkdir('" + str(hedef) + "')"
    jeton = mathenv._evaluating_recipe.set(True)
    try:
        with pytest.raises(mathenv.UnsafeExpression):
            sympy.sympify(kotu)
    finally:
        mathenv._evaluating_recipe.reset(jeton)
    assert not hedef.exists()


def test_bayrak_disinda_sympify_normal_calisir():
    # Küresel sarmalayıcı uygulamanın kendi `sympify` çağrılarını bozmamalı.
    assert not mathenv._evaluating_recipe.get()
    assert sympy.sympify("x + 1") == sympy.Symbol("x") + 1
