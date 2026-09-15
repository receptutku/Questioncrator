from __future__ import annotations

import collections.abc as _abc
import contextlib as _contextlib
import itertools as _it
import pathlib
import signal as _signal
import subprocess
import sys
import time
import types
import unicodedata as _unicodedata
import warnings as _warnings

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
# test tembel yüklenen sympy modüllerini çoktan içe aktarmış olabilir. Ayrıca
# içerik tabanlı muhafız (F1) yalnız taze süreçte doğru sınanır: bir reçete bir
# kez çalıştıktan sonra sympy'nin arama tabloları kurulur ve ikinci çalıştırma
# hiçbir iç dizge ayrıştırmaz — hata kendini maskeler.
TAZE_CALISMALI = [
    # F1: körlemesine reddin kırdığı, tembel kurulan tablolara dayanan aile.
    "integrate(exp(-x**2), (x, -oo, oo))",
    "integrate(1/(x**2+1), (x, -oo, oo))",
    "integrate(x*exp(-x), (x, 0, oo))",
    "integrate(exp(-x)*sin(x), (x, 0, oo))",
    "integrate(sin(x)/x, (x, 0, oo))",
    "Integral(1/(x**2+1), (x, 0, oo)).doit()",
    "summation(exp(-k), (k, 0, oo))",
    "hyperexpand(hyper([], [1], x))",
    "mellin_transform(exp(-x), x, s)",
    "fourier_transform(exp(-x**2), x, k)",
    # Günlük reçeteler.
    "simplify((x**2-1)/(x-1))",
    "diff(3*x**2+5*x-2, x)",
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
    "factorint(60).keys()",  # F5a: dict_keys (Iterable ama Iterator değil)
    "factorint(60).items()",  # F5a: dict_items
    "şık + 1",  # Türkçe tanımlayıcı
    "μ + 1",  # Yunanca tanımlayıcı
    # R5 sonrası tam sayı/nitelik yollarına dokunan meşru reçeteler bozulmamalı:
    "Poly(x**2-1, x).degree()",
    "Float(1.5) + 1",
]

# Bunlar taze süreçte de mutlaka `UnsafeExpression` ile reddedilmeli.
_UZUN_RECETE = "x" * 2001
TAZE_ENGELLENMELI = [
    'sympify("x")',
    'S("x")',
    '"abc"',
    "f'{x}'",
    _RCE_PAYLOAD,  # round-1 birleştirme yükü
    "nsolve(sin(x)-1, x, 1)",
    "lambdify(x, x)",
    "Function(x)",
    "Symbol(x)",
    "symbols(x)",
    "x.\uff46unc(x.\uff4eame)",  # NFKC: ｆunc/ｎame
    "\uff33ymbol(x)",  # NFKC: Ｓymbol
    "\uff29f",  # NFKC: Ｉf
    "\U0001d412ymbol(x)",  # matematiksel kalın S
    "lambda: 1",
    "[i for i in range(3)]",
    "x.__class__",
    "_x + 1",
    "(y := 3)",
    _UZUN_RECETE,
    "1" + "0" * 12,  # 13 haneli
    "continued_fraction_iterator(sqrt(2))",  # F4: temiz UnsafeExpression
    "primerange(1, 100000)",  # üst sınır
    # F2: str üreten adlar reddedilmeli.
    "default_sort_key(x)",
    "filldedent(x)",
    "FU",
    "capture(x)",
    "poly_from_expr(x)",
    "list2numpy(Matrix([[1]]))",
    "TableForm(Matrix([[1]]))",
    "Abs.lseries().gi_code",
    "x.sort_key()",
    "Eq(x, 1).rel_op",
    # R1/R2: bellek kaldıracı ve nitelik yolu str/bytes sızıntıları.
    "Matrix([[1,2],[3,4]]).rows.to_bytes(50000000)",
    "Matrix([[1,2],[3,4]]).rows.from_bytes(b)",
    "Dict(x.assumptions0)",
    "Float(1.5).default_assumptions",
    "Eq(x, 1).ValidRelationOperator",
]


def _taze_parse(recete: str) -> subprocess.CompletedProcess:
    kod = (
        "from questioncrator.mathenv import parse, UnsafeExpression\n"
        "try:\n"
        "    r = parse(" + repr(recete) + ")\n"
        "    print('OK', repr(r))\n"
        "except UnsafeExpression as e:\n"
        "    print('BLOCKED', str(e))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", kod],
        capture_output=True,
        text=True,
        cwd=str(_KOK),
    )


@pytest.mark.parametrize("recete", TAZE_CALISMALI)
def test_mesru_recete_taze_yorumlayicida_calisir(recete):
    """Her meşru reçete KENDİ taze yorumlayıcısında çalışmalı (returncode 0, OK)."""
    sonuc = _taze_parse(recete)
    assert sonuc.returncode == 0, f"{recete!r} taze süreçte çöktü:\n{sonuc.stderr}"
    assert sonuc.stdout.startswith("OK"), (
        f"{recete!r} taze süreçte engellendi:\n{sonuc.stdout}{sonuc.stderr}"
    )


@pytest.mark.parametrize("recete", TAZE_ENGELLENMELI)
def test_tehlikeli_recete_taze_yorumlayicida_engellenir(recete):
    """Her tehlikeli reçete KENDİ taze yorumlayıcısında `UnsafeExpression` almalı.

    Beklenen sonuç sütunu (BLOCKED) açıkça sınanır: yalnız "çökmedi" yetmez,
    kaçış gerçekten reddedilmiş olmalı.
    """
    sonuc = _taze_parse(recete)
    assert sonuc.returncode == 0, f"{recete!r} beklenmedik biçimde çöktü:\n{sonuc.stderr}"
    assert sonuc.stdout.startswith("BLOCKED"), (
        f"{recete!r} engellenmedi (SIZINTI):\n{sonuc.stdout}{sonuc.stderr}"
    )


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


def test_dict_keys_ve_items_normallesir():
    # F5a: `dict_keys`/`dict_items` `Iterable` ama `Iterator` değildir; yine de
    # 1000 öğe sınırı altında kabul edilmeli.
    anahtarlar = mathenv.parse("factorint(60).keys()")
    assert isinstance(anahtarlar, sympy.Basic)
    assert set(anahtarlar) == {2, 3, 5}
    ogeler = mathenv.parse("factorint(60).items()")
    assert isinstance(ogeler, sympy.Basic)


# --- F1: içerik tabanlı ayrıştırma muhafızı --------------------------------


def test_icerik_muhafizi_sympy_ic_sabitini_gecirir():
    # sympy'nin kendi derleme-anı sabitleri (ör. '3/2') `check_recipe`ten geçer;
    # bayrak açıkken bile ayrıştırılabilmeli. (Körlemesine red F1'i bozuyordu.)
    jeton = mathenv._evaluating_recipe.set(True)
    try:
        assert mathenv._original_parse_expr("3/2") == sympy.Rational(3, 2)
        # Muhafızlı takma ad üzerinden de:
        assert sympy.parsing.sympy_parser.parse_expr("3/2") == sympy.Rational(3, 2)
    finally:
        mathenv._evaluating_recipe.reset(jeton)


def test_icerik_muhafizi_guvensiz_dizgeyi_reddeder():
    # Bayrak açıkken güvensiz bir dizgenin ikinci ayrıştırması reddedilmeli.
    jeton = mathenv._evaluating_recipe.set(True)
    try:
        with pytest.raises(mathenv.UnsafeExpression):
            sympy.sympify("__import__('os').getcwd()")
        with pytest.raises(mathenv.UnsafeExpression):
            sympy.sympify("srepr(x)")  # yasaklı ad
    finally:
        mathenv._evaluating_recipe.reset(jeton)


def test_icerik_muhafizi_bayrak_disinda_calismaz():
    # Bayrak kapalıyken uygulamanın kendi çağrıları normal ayrıştırır (muhafız
    # hiç devreye girmez).
    assert not mathenv._evaluating_recipe.get()
    assert sympy.sympify("x + 1") == sympy.Symbol("x") + 1


# --- F2: ad alanı str üretmez ----------------------------------------------


def _kap_icinde_str(v, derinlik=0):
    if isinstance(v, (str, bytes, bytearray)):
        return True
    if derinlik > 4 or isinstance(v, (sympy.Basic, sympy.matrices.MatrixBase)):
        return False
    if isinstance(v, _abc.Mapping):
        return any(
            _kap_icinde_str(a, derinlik + 1) or _kap_icinde_str(b, derinlik + 1)
            for a, b in list(v.items())[:100]
        )
    if isinstance(v, (list, tuple, set, frozenset)):
        return any(_kap_icinde_str(w, derinlik + 1) for w in list(v)[:100])
    if isinstance(v, _abc.Iterator):
        try:
            return any(_kap_icinde_str(w, derinlik + 1) for w in _it.islice(v, 50))
        except Exception:
            return False
    return False


@_contextlib.contextmanager
def _sigalrm_zaman_asimi():
    """Çağrı-başı zaman aşımı için SIGALRM kurar ve çıkışta ESKİSİNİ geri yükler.

    R5b: `setitimer` süreç-globaldir ve işleyici geri yüklenmezse sonraki
    testlere sızar. Bu bağlam yöneticisi hem zamanlayıcıyı sıfırlar hem de
    önceki işleyiciyi geri kor. Ana iş parçacığı dışında `signal` kullanılamaz;
    o durumda zaman aşımı olmadan (doğrudan çağırarak) çalışır.
    """
    try:
        eski = _signal.getsignal(_signal.SIGALRM)
    except (ValueError, AttributeError):
        yield lambda fn, *a, **k: fn(*a)
        return

    def _alarm(*_):
        raise TimeoutError

    _signal.signal(_signal.SIGALRM, _alarm)

    def guarded(fn, *a, limit=1.0):
        _signal.setitimer(_signal.ITIMER_REAL, limit)
        try:
            return fn(*a)
        finally:
            _signal.setitimer(_signal.ITIMER_REAL, 0)

    try:
        yield guarded
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, eski)


def _ornek_argumanlar():
    x, y, k = sympy.symbols("x y k")
    M = sympy.Matrix([[1, 2], [3, 4]])
    return [
        (), (x,), (x, x), (x, y), (1,), (2, 3), (x, 1), (1, x), (M,), (M, M),
        (x**2 + 1, x), ([x, y],), ((x, y),), (sympy.Rational(1, 2),),
        (x, (x, 0, 1)), (sympy.Poly(x**2 - 1, x),), ([1, 2, 3],),
        (sympy.Eq(x, 1), x), (sympy.sin(x),), (sympy.pi,), (sympy.Float(1.5),),
        (x, x, x), (1, 2, 3), (sympy.Interval(0, 1),), (sympy.FiniteSet(1, 2),),
        (sympy.Tuple(1, 2),), (sympy.Dict({1: 2}),), (sympy.Function("f")(x), x),
        (sympy.Function("f")(x),), (2,), (0,), (-1,), (sympy.oo,), (sympy.I,),
        (sympy.E,), (k, (k, 1, 10)),
    ]  # fmt: skip


def _str_ureten_adlar():
    """Ad alanındaki her adı zararsız argümanlarla çağırıp str/bytes döndüreni bulur."""
    argumanlar = _ornek_argumanlar()
    bulunan = set()
    with _warnings.catch_warnings(), _sigalrm_zaman_asimi() as guarded:
        _warnings.simplefilter("ignore")
        for ad, nesne in mathenv._base_namespace().items():
            if _kap_icinde_str(nesne):
                bulunan.add(ad)
                continue
            if callable(nesne):
                for a in argumanlar:
                    try:
                        r = guarded(nesne, *a)
                    except BaseException:
                        continue
                    if _kap_icinde_str(r):
                        bulunan.add(ad)
                        break
    return bulunan


def _izinli_jeton(ad: str) -> bool:
    """Bir niteliğin adı `check_recipe`ten geçer mi (reçete o jetonu yazabilir mi)?"""
    if _unicodedata.normalize("NFKC", ad) != ad:
        return False
    return not (ad in mathenv.DENIED_NAMES or ad.startswith(mathenv.DENIED_PREFIXES))


def _ornek_nesneler(marker: str):
    """Reçetelerden erişilebilen türleri temsil eden nesneler + marker sembolü."""
    x, y = sympy.Symbol("x"), sympy.Symbol("y")
    mk = sympy.Symbol(marker)
    fmk = sympy.Function(marker)(x)
    return [
        mk,
        fmk,
        mk + 1,
        mk * x,
        mk**2,
        sympy.sin(mk),
        sympy.Integer(5),
        sympy.Rational(3, 4),
        sympy.Float(1.5),
        sympy.pi,
        sympy.oo,
        sympy.I,
        sympy.E,
        sympy.S.Half,
        sympy.Integer(-7),
        sympy.Matrix([[1, mk], [3, 4]]),
        sympy.Poly(x**2 - 1, x),
        sympy.Eq(mk, 1),
        x < 3,
        sympy.Interval(0, 1),
        sympy.FiniteSet(1, mk),
        sympy.Tuple(1, mk),
        sympy.Dict({1: mk}),
        x + y,
        x * y,
        x**y,
        sympy.Symbol(marker, positive=True),
    ]


def _nitelik_str_sizintilari(marker: str, max_derinlik: int = 3):
    """`check_recipe`ten geçen nitelik adlarını izleyen `getattr`-yalnız BFS.

    R2c: taramayı üst düzey adların ötesine nitelik yollarına taşır. İki şey
    döndürür: str/bytes sızdıran yaprak jetonların kümesi ve saldırganın SEÇTİĞİ
    adı (marker) sızdıran yolların kümesi. Anlamlı ve KARARLI güvenlik değişmezi
    ikincisidir: saldırgan-seçimi hiçbir dizge elde edilememeli — ve saldırganın
    seçtiği ad (bir Sembol/İşlev adı) ancak `getattr` yollarından (ör. `.name`)
    sızabilir, bu yüzden `getattr`-yalnız tarama bu değişmezi tümüyle kapsar.

    `getattr`-yalnız olmasının nedeni: rasgele YÖNTEM çağırmak (SIGALRM olmadan)
    sonsuz bir hesaba takılıp asılabilir; nitelik (özellik) erişimi ise ucuzdur
    ve gözden geçirenin tüm nitelik örneklerini (`assumptions0`,
    `default_assumptions`, `ValidRelationOperator`, `rel_op`, `.name` ailesi)
    yakalar. Yönteme dayalı str sızıntıları (ör. `to_bytes`, `sort_key`) jeton
    düzeyinde ayrıca yasaklıdır. Tip başına bir kez genişler (dedup).
    """
    sizinti: set[str] = set()
    saldirgan: set[str] = set()
    gorulen: set = set()

    def _str_bul(v, d=0):
        if isinstance(v, (str, bytes, bytearray)):
            return v
        if d > 3 or isinstance(v, (sympy.Basic, sympy.matrices.MatrixBase)):
            return None
        try:
            if isinstance(v, _abc.Mapping):
                for a, b in list(v.items())[:40]:
                    r = _str_bul(a, d + 1) or _str_bul(b, d + 1)
                    if r is not None:
                        return r
            elif isinstance(v, (list, tuple, set, frozenset)):
                for w in list(v)[:40]:
                    r = _str_bul(w, d + 1)
                    if r is not None:
                        return r
            elif isinstance(v, _abc.Iterator):
                for w in _it.islice(v, 20):
                    r = _str_bul(w, d + 1)
                    if r is not None:
                        return r
        except Exception:
            return None
        return None

    def _kaydet(jeton, deger):
        sizinti.add(jeton)
        try:
            if marker in str(deger):
                saldirgan.add(jeton)
        except Exception:
            pass

    def gez(nesne, derinlik):
        if derinlik > max_derinlik:
            return
        tip = nesne if isinstance(nesne, type) else type(nesne)
        if tip in gorulen:
            return
        gorulen.add(tip)
        try:
            adlar = [n for n in dir(nesne) if _izinli_jeton(n)]
        except Exception:
            return
        for n in adlar:
            try:
                v = getattr(nesne, n)
            except BaseException:
                continue
            r = _str_bul(v)
            if r is not None:
                _kaydet(n, r)
                continue
            if (
                derinlik < max_derinlik
                and v is not None
                and not callable(v)
                and not isinstance(v, (int, float, bool, complex))
            ):
                gez(v, derinlik + 1)

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        # (1) Ad alanının sınıf/işlev değerleri (marker içeren adlar dahil).
        for ad, nesne in mathenv._base_namespace().items():
            if _str_bul(nesne) is not None:
                _kaydet(ad, nesne)
            gez(nesne, 0)
        # (2) Reçetelerden erişilebilen türleri temsil eden nesneler.
        for nesne in _ornek_nesneler(marker):
            gez(nesne, 0)

    return sizinti, saldirgan


def test_recete_ad_alani_metin_uretmez():
    """F2: reçete ad alanındaki hiçbir ÜST DÜZEY ad çalışma anında str/bytes
    üretememeli.

    Bu tarama mekaniktir: 842 adın her biri zararsız argümanlarla çağrılır ve
    dönüşü (kap içinde de olsa) str/bytes içeriyorsa hata verir. Bulunan tüm
    adlar `DENIED_NAMES`e eklendiği için küme boş olmalı. (SIGALRM ana iş
    parçacığı gerektirir; pytest testleri ana iş parçacığında koşar.)
    """
    kalan = _str_ureten_adlar()
    assert kalan == set(), f"str üreten erişilebilir üst düzey adlar kaldı: {sorted(kalan)}"


def test_nitelik_yollari_saldirgan_secimi_dizge_sizdirmaz():
    """R2c: nitelik yolları taranır. DÜRÜST GARANTİ: saldırganın SEÇTİĞİ hiçbir
    dizge (marker) elde edilememeli.

    Sabit sympy sözcüğü dizgeleri (bir niteliğin adı gibi) bazı derin yollardan
    hâlâ elde edilebilir; bunların arkasında içerik muhafızı ile `_normalize`in
    str/bytes kapısı durur. Bu test, GÜÇLÜ ve KARARLI değişmezi sabitler:
    reçetelerden erişilebilen str'ler yalnız sabit sözcüktür, saldırgan-seçimi
    ad asla sızmaz.
    """
    sizinti, saldirgan = _nitelik_str_sizintilari("zqxjkmarker")
    # (1) GÜÇLÜ değişmez: saldırgan-seçimi hiçbir ad sızmaz.
    assert saldirgan == set(), (
        f"saldırgan-seçimi ad sızdıran nitelik yolları var: {sorted(saldirgan)}"
    )
    # (2) `getattr` yüzeyinde str/bytes sızdıran yaprak jeton da kalmamalı
    # (bulunanların hepsi `DENIED_NAMES`e eklendi).
    assert sizinti == set(), f"getattr yoluyla str/bytes sızdıran jetonlar kaldı: {sorted(sizinti)}"


def test_pretty_yasakli_ve_metin_dondurur():
    # Brief'in özellikle işaret ettiği ad: `pretty` gerçekten str döndürür ve
    # yasak listesinde olmalı.
    assert "pretty" in mathenv.DENIED_NAMES
    assert isinstance(sympy.pretty(sympy.Symbol("x")), str)


def test_derin_nitelik_zinciri_str_yollari_kapali():
    # F2/R2 (ek): erişilebilirlik taramasında bulunan derin str yolları ve
    # bellek kaldıracı jetonları kapatıldı.
    for recete in [
        "Abs.lseries().gi_code",  # üreteç kod nesnesi -> co_*
        "list2numpy(Matrix([[1]]))",  # numpy dizisi -> dtype.char, tobytes
        "Eq(x, 1).rel_op",  # '==' dizgesi
        "x.sort_key()",  # sıralama anahtarı (iç içe str)
        "Matrix([[1,2],[3,4]]).rows.to_bytes(50000000)",  # R1: bellek kaldıracı
        "Dict(x.assumptions0)",  # R2: gerçek str anahtarlı sözlük
        "Float(1.5).default_assumptions",  # R2
        "Eq(x, 1).ValidRelationOperator",  # R2
    ]:
        with pytest.raises(mathenv.UnsafeExpression):
            mathenv.parse(recete)


def test_tehlikeli_yerlesikler_reddedilir():
    """R3: içerik muhafızının güvenliği, tehlikeli yerleşiklerin (sympy'nin iç
    ayrıştırıcısının ad alanına enjekte ettiği) yasaklı olmasına bağlıdır.

    Literal kümeye karşı sabitlenir: kaynak listeden biri "sympy adı değil" diye
    budanırsa bu test kırılır ve yüzey sessizce açılmaz.
    """
    tehlikeli = {
        "exec", "eval", "open", "compile", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "input", "breakpoint",
    }  # fmt: skip
    for ad in tehlikeli:
        with pytest.raises(mathenv.UnsafeExpression):
            mathenv.check_recipe(ad)
    # `_DANGEROUS_BUILTINS` kümesi de tam olmalı (kaynak sabiti).
    assert tehlikeli <= mathenv.DENIED_NAMES
    assert set(mathenv._DANGEROUS_BUILTINS) == tehlikeli


# --- F3: bayrak, normalleştirme bittikten SONRA sıfırlanır -------------------


def test_uretec_govdesi_bayrak_acikken_calisir():
    """F3: `_normalize` üreteç gövdesini gerçekleştirirken bayrak hâlâ açık olmalı.

    Eski kodda `parse` bayrağı `finally`de `_normalize`ten ÖNCE sıfırlıyordu;
    üreteç gövdesi (islice ile 1001 öğeye dek) her iki muhafız kapalıyken
    çalışıyordu. Tel-tuzak bir yineleyici, tüketilirken bayrağın değerini kaydeder.
    """
    kayit = []

    class TripwireIterator:
        def __init__(self):
            self._n = 0

        def __iter__(self):
            return self

        def __next__(self):
            kayit.append(mathenv._evaluating_recipe.get())
            self._n += 1
            if self._n > 3:
                raise StopIteration
            return sympy.Integer(self._n)

    # `parse`i taklit et: bayrağı ayarla, sonra `_normalize` çağır.
    jeton = mathenv._evaluating_recipe.set(True)
    try:
        sonuc = mathenv._normalize(TripwireIterator())
    finally:
        mathenv._evaluating_recipe.reset(jeton)
    assert kayit, "yineleyici hiç tüketilmedi"
    assert all(kayit), "üreteç gövdesi bayrak KAPALIYKEN çalıştı (F3 gerilemesi)"
    assert list(sonuc) == [1, 2, 3]


# --- F4: kap gerçekleştirmesinde istisna sızıntısı yok ----------------------


def test_continued_fraction_temiz_unsafe_yukseltir():
    # F4: eski davranış ~1.3 sn sonra çıplak `RecursionError` idi; artık temiz
    # `UnsafeExpression`.
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("continued_fraction_iterator(sqrt(2))")


def test_normalize_matematik_hatasi_tarafsiz_bildirilir():
    # R4: sıradan bir matematik başarısızlığı (ör. NotImplementedError/TypeError)
    # hocaya saldırı gibi değil, tarafsız biçimde bildirilmeli.
    def patlayan():
        yield sympy.Integer(1)
        raise NotImplementedError("henüz yok")

    with pytest.raises(mathenv.UnsafeExpression) as bilgi:
        mathenv._normalize(patlayan())
    mesaj = str(bilgi.value)
    assert "reçete sonucu üretilemedi" in mesaj
    assert "güvensiz" not in mesaj and "reddedildi" not in mesaj


def test_normalize_ozyineleme_ve_bellek_ayri_bildirilir():
    # R4: kaynak/özyineleme tükenmesi ayrı (sınır ihlali) mesajıyla ayrılır.
    def ozyineli():
        yield sympy.Integer(1)
        raise RecursionError("maximum recursion depth exceeded")

    with pytest.raises(mathenv.UnsafeExpression) as bilgi:
        mathenv._normalize(ozyineli())
    assert "özyineleme sınırı" in str(bilgi.value)

    def bellek():
        yield sympy.Integer(1)
        raise MemoryError()

    with pytest.raises(mathenv.UnsafeExpression) as bilgi2:
        mathenv._normalize(bellek())
    assert "bellek sınırı" in str(bilgi2.value)


def test_parse_recursionerror_disari_sizmaz(monkeypatch):
    # F4: `RecursionError` `parse` içinde herhangi bir aşamada oluşursa ham
    # biçimde dışarı sızmamalı; `parse`ın en dış yakalayıcısı onu temiz bir
    # `UnsafeExpression`e çevirir. Burada normalleştirme aşamasını `RecursionError`
    # yükseltecek biçimde değiştiriyoruz.
    def patlayan_normalize(_value):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(mathenv, "_normalize", patlayan_normalize)
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("x + 1")


# --- F5b: parse muhafızı kimlik-eksiksiz ------------------------------------


def test_parse_muhafizi_tum_takma_adlarda_kurulu():
    # Eski kod yalnız `sympy_parser.parse_expr`i sarıyordu; `sympy.parse_expr`
    # ve `sympy.parsing.parse_expr` muhafızsız kalıyordu.
    import sympy.parsing

    assert getattr(sympy.parsing.sympy_parser.parse_expr, "_qc_guard", False)
    assert getattr(sympy.parse_expr, "_qc_guard", False)
    assert getattr(sympy.parsing.parse_expr, "_qc_guard", False)
    # Yüklü hiçbir sympy modülünde sarmalanmamış özgün başvuru kalmamalı.
    import sys as _sys

    kalan = [
        (m.__name__, ad)
        for m in list(_sys.modules.values())
        if m is not None and getattr(m, "__name__", "").startswith("sympy")
        for ad, deger in list(vars(m).items())
        if deger is mathenv._original_parse_expr
    ]
    assert kalan == [], f"muhafızsız parse_expr takma adları: {kalan}"


# --- İçerik muhafızına karşı özel olarak tasarlanmış yeni yük ----------------


def test_icerik_muhafizina_karsi_yeni_yuk_basarisiz():
    """Yeni yük: çalışma anında `check_recipe`ten geçecek bir dizge kurup yine de
    tehlikeli olmayı dener.

    Fikir: `chr`/`bin`/`ord` yasak değildir ve sympy'nin KENDİ ayrıştırma
    ad alanında gerçek yerleşiktir; `chr(95)+chr(95)+...` ile alt çizgi/dizge
    kurulup `__import__` inşa edilebilirdi. Neden başarısız:
      (1) Reçete ad alanında `__builtins__ = {}` olduğundan `chr`/`bin`/`ord`
          bu adlar arasında yoktur; `auto_symbol` onları SEMBOLİK bir çağrıya
          çevirir (gerçek dizge üretmez).
      (2) İçerik muhafızı yalnız sympy'nin KENDİ derleme-anı sabitlerini görür;
          saldırgan bir dizgeyi bir iç ayrıştırmaya enjekte edecek erişilebilir
          bir sink yoktur (str üreten adların hepsi yasak, str sonuç `_normalize`
          kapısında reddedilir).
    Sonuç: RCE yok; hiçbir dizge gerçek Python str'ine dönüşmez.
    """
    for yuk in ["chr(95)+chr(95)", "bin(3)+bin(3)", "ord(x)*chr(95)"]:
        sonuc = mathenv.parse(yuk)
        assert isinstance(sonuc, sympy.Basic)
        # Sembolik kaldı: gerçek str üretilmedi.
        assert not isinstance(sonuc, (str, bytes))
