from __future__ import annotations

import pathlib
import subprocess
import sys
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
    # `Symbol`/`Function` yasaklı jetonlardır ama `parse_expr` dönüşümleri
    # üretilen koda enjekte ettiği için ad alanında kalmaları gerekir; onlar
    # dışında hiçbir yasaklı ad ad alanında olmamalı.
    assert not (set(ad_alani) & (mathenv.DENIED_NAMES - mathenv._PARSER_REQUIRED_NAMES))
    assert mathenv._PARSER_REQUIRED_NAMES <= set(ad_alani)
    assert not [
        ad
        for ad in ad_alani
        if ad != "__builtins__"
        and ad not in mathenv._PARSER_REQUIRED_NAMES
        and ad.startswith(mathenv.DENIED_PREFIXES)
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


# İkinci sınıf "çalışma anında kurulan dizge" kaçışı: `nsolve` içeride
# `lambdify` çağırır, o da üretilen Python kaynağını `exec`ler; `Function(<ad>)`
# tırnaksız bir adı sympify etmeden kabul ettiği için bu adın içine kod
# gizlenip lambdify'ın exec'ine sızabilirdi. Bu sink `parse_expr`/`_normalize`
# yolundan geçmez, ayrı bir muhafızla kapatılır.
def test_nsolve_receresi_reddedilir_ve_calistirmaz(tmp_path):
    hedef = tmp_path / "izi_nsolve"
    # Reçete düzeyinde `nsolve`/`Function` yasaklıdır; check_recipe hiç
    # değerlendirmeden reddeder.
    recete = "nsolve(Function(x)(x) - 1, x, 1)"
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(recete)
    assert not hedef.exists()


def test_lambdify_sink_bayrak_icinde_kod_calistirmaz(tmp_path):
    # Katman (kod üretimi muhafızı): bayrak açıkken lambdify tabanlı yol
    # (`nsolve`) exec'e ulaşmadan durur; ad içine gizlenen os.mkdir çalışmaz.
    hedef = tmp_path / "izi_lambdify"
    x = sympy.Symbol("x")
    kotu_ad = "__import__('os').mkdir('" + str(hedef) + "')or abs"
    f = sympy.Function(kotu_ad)
    jeton = mathenv._evaluating_recipe.set(True)
    try:
        with pytest.raises(mathenv.UnsafeExpression):
            sympy.nsolve(f(x) - 1, x, 1)
        with pytest.raises(mathenv.UnsafeExpression):
            sympy.lambdify(x, x)
    finally:
        mathenv._evaluating_recipe.reset(jeton)
    assert not hedef.exists()


def test_bayrak_disinda_lambdify_normal_calisir():
    # Muhafız sympy'nin kendi lambdify çağrılarını küresel olarak bozmamalı.
    assert not mathenv._evaluating_recipe.get()
    x = sympy.Symbol("x")
    g = sympy.lambdify(x, x)
    assert g(3) == 3


_KOK = pathlib.Path(__file__).resolve().parents[1]

# Hocanın günlük olarak yazacağı reçeteler. Bunlar TAZE bir yorumlayıcıda
# çalıştırılır: aynı süreçte koşmak hatayı maskeler, çünkü daha önceki bir
# test tembel yüklenen sympy modüllerini çoktan içe aktarmış olabilir.
TAZE_SUREC_RECETELERI = [
    "simplify((x**2-1)/(x-1))",
    "diff(3*x**2+5*x-2, x)",
    "integrate(sin(x), (x, 0, pi))",
    "limit(sin(3*x)/x, x, 0)",
    "Matrix([[2,1],[4,3]]).det()",
    "solve(x**2-4, x)",
    "Sum(k, (k,1,10)).doit()",
    "binomial(5,2)",
    "gcd(12,18)",
    "Eq(2*x, 6)",
    "solveset(x**2-4, x)",
    "Abs(-3)",
    "Rational(3,4)**2",
    "floor(7/2)",
    "log(8,2)",
    "factor(x**2-1)",
    "expand((x+2)**3)",
    "series(sin(x), x, 0, 4)",
    "dsolve(Derivative(f(x),x) - x)",
    "Matrix([[1,2],[3,4]]).inv()",
    "factorint(60)",
    "primerange(1, 20)",
]


@pytest.mark.parametrize("recete", TAZE_SUREC_RECETELERI)
def test_mesru_recete_taze_yorumlayicida_calisir(recete):
    """Her meşru reçete KENDİ taze yorumlayıcısında çalışmalı.

    Bu testin alt süreç kullanması şart: `simplify` gibi işlevler
    değerlendirme sırasında tembel içe aktarma yapar ve içe aktarılan modülün
    gövdesi sympy'ye kendi sabit metinlerini ayrıştırtır. Aynı süreçte önceki
    bir test o modülü zaten yüklediyse yol hiç tetiklenmez ve kırık davranış
    görünmez olur. Üretimdeki işçi de her zaman taze bir süreçtir.
    """
    kod = f"from questioncrator.mathenv import parse; parse({recete!r})"
    sonuc = subprocess.run(
        [sys.executable, "-c", kod],
        capture_output=True,
        text=True,
        cwd=str(_KOK),
    )
    assert sonuc.returncode == 0, f"{recete!r} taze süreçte başarısız:\n{sonuc.stderr}"


def test_nfkc_yazimi_yasaklari_atlatamaz():
    # Python tanımlayıcıları derleme anında NFKC'ye çevirir; ham jeton metnine
    # bakan denetim `ｆunc`/`ｎame` gibi yazımlarla atlatılabiliyordu.
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("x.\uff46unc(x.\uff4eame)")
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("\uff33ymbol(x)")


def test_turkce_harfli_ad_calismaya_devam_eder():
    # Türkçe harfler NFKC altında değişmez; dizgesiz bağlamda eskisi gibi çalışır.
    sonuc = mathenv.parse("şık + 1")
    assert isinstance(sonuc, sympy.Basic)
    assert "şık" in str(sonuc)


def test_sozluk_donen_recete_normallesir():
    sonuc = mathenv.parse("factorint(60)")
    assert isinstance(sonuc, sympy.Basic)
    assert sonuc == sympy.Dict({2: 2, 3: 1, 5: 1})


def test_uretec_donen_recete_normallesir():
    sonuc = mathenv.parse("primerange(1, 20)")
    assert isinstance(sonuc, sympy.Basic)
    assert list(sonuc) == [2, 3, 5, 7, 11, 13, 17, 19]


def test_cok_uzun_uretec_reddedilir():
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("primerange(1, 100000)")


def test_sinirsiz_uretec_tuketilmeden_reddedilir():
    """Üst sınır olmasaydı bu test sonsuza dek asılı kalırdı."""

    def sonsuz():
        sayi = 0
        while True:
            yield sayi
            sayi += 1

    with pytest.raises(mathenv.UnsafeExpression):
        mathenv._normalize(sonsuz())
