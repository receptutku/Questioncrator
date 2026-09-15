"""SymPy ifadelerini kısıtlı ad alanında, zaman aşımlı biçimde değerlendirir.

Reçeteler hocanın dosyalarından gelir. Yine de düz `eval` kullanmayız:
sympy'nin kendi ayrıştırıcısını, yalnız sympy adlarını içeren bir küresel
sözlükle çalıştırırız. Böylece reçete dili "herhangi bir SymPy ifadesi"
kadar geniş kalır ama Python'un geri kalanına erişemez.
"""

from __future__ import annotations

import collections.abc
import contextvars
import functools
import importlib
import io
import itertools
import keyword
import re
import sys
import tokenize
import types
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import sympy
import sympy.parsing.sympy_parser as _sympy_parser
from sympy.parsing.sympy_parser import standard_transformations

# `parse_expr`in özgün (sarmalanmamış) başvurusu: kendi değerlendirmemizi
# bununla yaparız. Modül düzeyindeki `_sympy_parser.parse_expr` ise aşağıda
# bir muhafızla değiştirilir; sympy'nin kendi `sympify`i çağrı anında o
# modül niteliğini içe aktardığından, ikinci bir eval açan her dolaylı yol
# muhafıza takılır.
_original_parse_expr = _sympy_parser.parse_expr


class UnsafeExpression(ValueError):
    """Reçete, ayrıştırılmadan önce sözdizimsel bir güvenlik kuralına takıldı."""


class EvaluationTimeout(Exception):
    """Reçete verilen süre içinde değerlendirilemedi."""


MAX_RECIPE_LENGTH = 2000
MAX_NUMBER_DIGITS = 12
# Üreteç döndüren çağrılar için üst sınır: sonsuz bir üreteci tüketerek
# bitirmeye asla çalışmayız.
MAX_RESULT_ITEMS = 1000

# İkincil koruma: yan etkili ya da ikinci bir eval açan sympy adları.
# Birincil koruma dizge yasağı + alt çizgi yasağıdır (bkz. check_recipe).
DENIED_NAMES = frozenset(
    {
        "sympify", "S", "parse_expr", "lambdify", "preview", "init_printing",
        "init_session", "var", "pprint", "pretty_print", "pager_print",
        "interactive_traversal", "textplot", "dotprint", "test", "doctest",
        "exec", "eval", "open", "compile", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "input", "help", "breakpoint", "exit", "quit",
        # Dizge üreten yazıcılar/işlevler: çıktıları çalışma anında birleşip
        # ikinci bir eval'a beslenebilir, bu yüzden reçetede kullanılamaz.
        "srepr", "sstr", "sstrrepr", "latex", "multiline_latex", "mathml",
        "pretty", "python", "pycode", "ccode", "cxxcode", "fcode", "jscode",
        "julia_code", "maple_code", "mathematica_code", "octave_code", "rcode",
        "rust_code", "glsl_code", "smtlib_code", "print_tree",
        # `.name` gibi dizge döndüren nitelikler reçetede gereksizdir.
        "name",
        # Dizgeden adlı sembol/işlev kurup kod üretimi (lambdify/exec) ya da
        # derleme (autowrap/codegen -> subprocess) sinklerine ulaşan adlar.
        # Reçeteler sembolleri `auto_symbol` ile (çıplak `x`) alır; dizgeden
        # adlı bir Function/Symbol kurmaya asla ihtiyaç duymaz.
        "Function", "Symbol", "Dummy", "Wild", "symbols", "nsolve",
        "autowrap", "ufuncify", "binary_function", "codegen",
        "implemented_function",
        # F2 (ek önlem): reçete ad alanı taranarak (bkz.
        # tests/test_mathenv.py::test_recete_ad_alani_metin_uretmez) çalışma
        # anında Python `str`/`bytes` döndüren adların tümü bulundu ve buraya
        # eklendi. `_normalize`in str/bytes kapısı yine de son emniyet kemeri;
        # bu liste dizgenin ilk elde edilmesini de engeller.
        # (1) Doğrudan ya da kap içinde str döndüren üst düzey adlar:
        "FU", "capture", "timed", "default_sort_key", "filldedent",
        "poly_from_expr", "parallel_poly_from_expr",
        # (2) str taşıyan yabancı nesneleri (numpy dizisi, yazıcı, tablo)
        # üreten üst düzey adlar — alt ağacı kökten keser:
        "list2numpy", "matrix2numpy", "TableForm", "StrPrinter",
        # (3) str döndüren nitelik zinciri jetonları (chokepoint):
        # üreteç kod nesnesi, mpmath bağlamı, tanım nesnesi iç gösterimi,
        # sıralama/karşılaştırma anahtarları, yazıcı/tablo yöntemleri.
        "gi_code", "context", "rep", "alias", "fmt", "default_order",
        "rel_op", "sort_key", "class_key", "cache_parameters", "rules",
        "as_latex", "as_str", "table", "doprint", "emptyPrinter",
        "printmethod",
    }
)  # fmt: skip
DENIED_PREFIXES = ("_", "plot", "print_", "pprint")
_ALLOWED_KEYWORDS = frozenset({"True", "False", "None", "and", "or", "not", "in", "is"})

# `parse_expr`in standart dönüşümleri (auto_symbol/auto_number) üretilen kodun
# içine bu adları enjekte eder (çıplak `x` -> `Symbol('x')`, bilinmeyen çağrı
# `f(x)` -> `Function('f')(x)`). Bu yüzden yasaklı olsalar bile ad alanında
# kalmalıdırlar.
#
# Güvenli olmalarının nedeni iki ayrı olgudur:
#   1. Enjeksiyon her zaman derleme anındaki bir metin sabitiyle (kullanıcının
#      yazdığı adın kendisi) olur, çalışma anında kurulmuş bir değerle değil.
#   2. Kullanıcının bu adlara doğrudan ulaşması `check_recipe`te kesilir. Bu
#      yalnızca ad jetonları NFKC ile normalleştirildiği için doğrudur: Python
#      tanımlayıcıları derleme anında NFKC'ye çevirir, dolayısıyla ham jeton
#      metnine bakan bir denetim `ｆunc` / `Ｓymbol` gibi yazımlarla atlatılırdı.
#      `check_recipe` hem normalleştirir hem de normalleşmiş biçim ham metinden
#      farklıysa jetonu tümden reddeder.
_PARSER_REQUIRED_NAMES = frozenset({"Symbol", "Function"})


def check_recipe(recipe: str) -> None:
    """Reçeteyi değerlendirmeden önce jeton düzeyinde denetler.

    Reçete dili yalnız sayı, ad, işlem ve parantezden oluşur: dizge,
    alt çizgiyle başlayan ad, anahtar sözcük (mantıksal olanlar hariç)
    ve atama ifadesi yasaktır.
    """
    if len(recipe) > MAX_RECIPE_LENGTH:
        raise UnsafeExpression(f"reçete {MAX_RECIPE_LENGTH} karakterden uzun")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(recipe).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise UnsafeExpression("reçete jetonlara ayrılamadı") from exc
    for token in tokens:
        kind = tokenize.tok_name.get(token.type, "")
        if token.type == tokenize.STRING or kind.startswith("FSTRING"):
            raise UnsafeExpression("dizge içeren reçete reddedildi")
        if token.type == tokenize.OP and token.string == ":=":
            raise UnsafeExpression("atama içeren reçete reddedildi")
        if token.type == tokenize.NUMBER:
            if len(re.sub(r"[^0-9]", "", token.string)) > MAX_NUMBER_DIGITS:
                raise UnsafeExpression("çok büyük sayı literali reddedildi")
        if token.type == tokenize.NAME:
            # Python tanımlayıcıları derleme anında NFKC'ye çevirir; ham jeton
            # metnine bakmak `ｆunc` gibi yazımların yasakları atlatmasına yol
            # açardı. Önce normalleştirir, sonra farklıysa tümden reddederiz.
            raw = token.string
            name = unicodedata.normalize("NFKC", raw)
            if name != raw:
                raise UnsafeExpression("NFKC dışı yazımlı ad içeren reçete reddedildi")
            if keyword.iskeyword(name) and name not in _ALLOWED_KEYWORDS:
                raise UnsafeExpression(f"`{name}` içeren reçete reddedildi")
            if name in DENIED_NAMES or name.startswith(DENIED_PREFIXES):
                raise UnsafeExpression(f"`{name}` adı reçetede kullanılamaz")


@functools.cache
def _base_namespace() -> dict[str, object]:
    namespace: dict[str, object] = {}
    for name in sympy.__all__:
        denied = name in DENIED_NAMES or name.startswith(DENIED_PREFIXES)
        if denied and name not in _PARSER_REQUIRED_NAMES:
            continue
        value = getattr(sympy, name)
        if isinstance(value, types.ModuleType):
            continue
        namespace[name] = value
    return namespace


def _allowed_namespace() -> dict[str, object]:
    # Temel sözlük önbellekte tutulur; her çağrıda kopyalanır ki
    # değerlendirme sırasında yapılan değişiklikler sonrakilere sızmasın.
    ns = dict(_base_namespace())
    # Ek önlem (defense-in-depth): ad alanında olmayan adlar `auto_symbol`
    # dönüşümüyle sembole düşer; bu satır o yolun dışında kalabilecek
    # bir çağrı yoluna karşı ek bir kapaktır.
    ns["__builtins__"] = {}
    return ns


# Bir reçete değerlendirilirken (yalnız kendi iş parçacığında) True olur.
# `parse` bunu ayarlar; muhafız buna bakar.
_evaluating_recipe: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "qc_evaluating_recipe", default=False
)


def _in_module_import() -> bool:
    """Yığında bir modül içe aktarma işlemi var mı?

    `simplify` gibi sympy işlevleri değerlendirme sırasında tembel içe aktarma
    yapar; içe aktarılan modülün gövdesi kendi sabit metinlerini sympy'ye
    ayrıştırtabilir. Bu, saldırganın kurduğu bir dizge değil, sympy'nin kendi
    derleme-anı sabitidir: bir içe aktarma sırasında saldırgan dizgesi asla
    ortaya çıkmaz. Bu yüzden muafiyet kesindir, saldırı yüzeyini genişletmez.
    """
    frame = sys._getframe(1)
    while frame is not None:
        module_name = frame.f_globals.get("__name__", "")
        if isinstance(module_name, str) and module_name.startswith("importlib._bootstrap"):
            return True
        frame = frame.f_back
    return False


@functools.lru_cache(maxsize=4096)
def _recipe_content_ok(text: str) -> bool:
    """İçerik muhafızı için: dizge, reçete dilinin kurallarına uyuyor mu?

    `check_recipe` ile aynı kuralları uygular (dizge/f-string yok, alt çizgi
    yok, yasaklı ad yok, `__`/`import` alt dizgesi yok). Sonuç önbelleğe alınır:
    değerlendirme sırasında aynı iç sabit birçok kez ayrıştırılabilir; kural
    kümesi çalışma anında sabit olduğundan önbellek güvenlidir.
    """
    if "__" in text or "import" in text:
        return False
    try:
        check_recipe(text)
    except UnsafeExpression:
        return False
    return True


# Not: `functools.wraps` kullanmıyoruz — sarmalanan özgün işleve `__wrapped__`
# üzerinden muhafızsız bir tutamak bırakırdı.
def _guarded_parse_expr(*args: object, **kwargs: object) -> object:
    """`sympy.parsing.sympy_parser.parse_expr` yerine geçen içerik muhafızı.

    Reçete değerlendirilirken sympy'nin herhangi bir dolaylı yolu (örn.
    `sympify(<dizge>)` ya da `simplify(<dizge>)`) bir dizgeyi yeniden
    ayrıştırmaya kalkarsa, o dizge REÇETE DİLİNİN KENDİ kurallarından
    (`check_recipe`) geçirilir: geçerse özgün ayrıştırıcı devreder, geçmezse
    `UnsafeExpression` yükselir.

    Gerekçe: sympy kendi arama tablolarını çalışma anında tembel kurarken
    KENDİ derleme-anı metin sabitlerini (ör. `'3/2'`, `'x'`, `'Number'`) sympify
    eder; bunlar düz matematiktir ve `check_recipe`ten geçer. Bir saldırgan yükü
    ise tırnak, `__`, alt çizgiyle başlayan ad ya da yasaklı ad içermeden
    tehlikeli bir sink'e ulaşamaz; bunların hepsi `check_recipe`te reddedilir.
    Böylece eski körlemesine reddin kırdığı meşru reçete ailesi (tembel kurulan
    arama tablolarına dayanan hesaplar) yeniden çalışırken ikinci-eval kapısı
    kapalı kalır.

    Ek muafiyet: sürmekte olan bir modül içe aktarma (bkz. `_in_module_import`).
    Kendi `parse`imiz özgün başvuruyu (`_original_parse_expr`) doğrudan çağırdığı
    için üst düzey reçetenin kendisi bu muhafızdan geçmez (çift tokenizasyon yok).
    """
    if _evaluating_recipe.get():
        text = args[0] if args else kwargs.get("s")
        if isinstance(text, str) and not _recipe_content_ok(text) and not _in_module_import():
            raise UnsafeExpression("reçete değerlendirilirken güvensiz dizge ayrıştırma reddedildi")
    return _original_parse_expr(*args, **kwargs)


_guarded_parse_expr._qc_guard = True  # type: ignore[attr-defined]
_guarded_parse_expr._qc_original = _original_parse_expr  # type: ignore[attr-defined]


def _install_parse_guard() -> None:
    """`parse_expr`in tüm sympy bağlarını kimlik üzerinden muhafızla değiştirir.

    `lambdify` kurucusuyla aynı yöntem: sabit bir ad listesi yerine yüklü tüm
    sympy modüllerinde nesne kimliği (`is _original_parse_expr`) eşleşen her adı
    değiştiririz. Böylece `sympy.parse_expr` ve `sympy.parsing.parse_expr` gibi
    takma adlar da muhafızlanır; yalnız `sympy_parser.parse_expr` niteliğini
    değiştirmek bu iki takma adı muhafızsız bırakıyordu (F5b).
    """
    if getattr(_sympy_parser.parse_expr, "_qc_guard", False):
        return
    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__name__", "").startswith("sympy"):
            continue
        try:
            members = list(vars(module).items())
        except TypeError:
            continue
        for attribute, value in members:
            if value is _original_parse_expr:
                try:
                    setattr(module, attribute, _guarded_parse_expr)
                except (AttributeError, TypeError):
                    pass


_install_parse_guard()


# `lambdify` üretilmiş Python kaynağını `exec`ler; `nsolve` gibi çağrılar buna
# dayanır. `Function(<dizge>)` tırnaksız kurulan bir adı sympify etmeden kabul
# ettiğinden, çalışma anında kurulmuş bir ad `lambdify`in `exec`ine sızabilir.
# Bu sink `parse_expr` ya da `_normalize` yolundan geçmez; bu yüzden ayrı bir
# muhafızla kapatılır.
_original_lambdify = getattr(sympy.lambdify, "_qc_original", sympy.lambdify)


# `functools.wraps` yok: `__wrapped__` muhafızsız bir tutamak bırakırdı.
# Muafiyet de yok — dinamik tarama içe aktarma anında lambdify çağıran hiçbir
# sympy modülü bulamadı, bu yüzden bu muhafız koşulsuz kalır.
def _guarded_lambdify(*args: object, **kwargs: object) -> object:
    """`sympy.lambdify` yerine geçen muhafız (tüm bağlarında).

    Reçete değerlendirilirken lambdify tabanlı her yol (örn. `nsolve`) kod
    üretimini burada durdurur. Bayrak kapalıyken sympy'nin kendi lambdify
    çağrıları özgün davranışla sürer.
    """
    if _evaluating_recipe.get():
        raise UnsafeExpression("reçete değerlendirilirken kod üretimi reddedildi")
    return _original_lambdify(*args, **kwargs)


_guarded_lambdify._qc_guard = True  # type: ignore[attr-defined]
_guarded_lambdify._qc_original = _original_lambdify  # type: ignore[attr-defined]


def _install_lambdify_guard() -> None:
    """`lambdify`in tüm sympy bağlarını kimlik üzerinden muhafızla değiştirir.

    Farklı sympy modülleri lambdify'ı `from ... import lambdify` ile içe
    aktarıp aynı işlev nesnesine ayrı adlar bağlar (örn. `solvers.lambdify`).
    Sabit bir ad listesi kırılgan olurdu; bunun yerine yüklü tüm sympy
    modüllerinde nesne kimliği (`is _original_lambdify`) eşleşen her adı
    değiştiririz. Kaynak modül niteliği de değiştiği için, sonradan yüklenen
    modüllerin `from ... import lambdify`i doğrudan muhafızı alır.

    Bilinen sınır: `sympy.utilities.lambdify` modülü `importlib.reload` ile
    yeniden yüklenirse muhafızsız bağ geri gelir, üstelik `_qc_guard` işareti
    de kaybolacağı için bu işlev yeniden kurulum yapmaz. Uygulama sympy'yi
    yeniden yüklemez; yine de bu durumda `_install_lambdify_guard()` elle
    çağrılmalıdır.
    """
    if getattr(sympy.lambdify, "_qc_guard", False):
        return
    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__name__", "").startswith("sympy"):
            continue
        try:
            members = list(vars(module).items())
        except TypeError:
            continue
        for attribute, value in members:
            if value is _original_lambdify:
                try:
                    setattr(module, attribute, _guarded_lambdify)
                except (AttributeError, TypeError):
                    pass


_install_lambdify_guard()


def _warm_lazy_importers() -> None:
    """İçe aktarma anında dizge ayrıştıran sympy modüllerini önceden yükler.

    Muhafız içe aktarma çerçevelerini zaten muaf tutar (bkz.
    `_in_module_import`); bu yükleme ikinci emniyet kemeridir. Dinamik tarama,
    değerlendirme sırasında tembel olarak yüklenip gövdesinde dizge ayrıştıran
    tek sıcak yolun birim/önek modülü olduğunu gösterdi.
    """
    try:
        importlib.import_module("sympy.physics.units")
    except Exception:  # pragma: no cover - ortama bağlı
        pass


_warm_lazy_importers()


def _guard_materialization(thunk):
    """Bir kap/üreteç gövdesini üretirken çıkan hatayı `UnsafeExpression`e sarar.

    Kap ya da üreteç gövdesinin gerçekleştirilmesi (öğelerin tüketilmesi) rasgele
    sympy kodu çalıştırır ve bu kod `RecursionError` gibi çıplak bir istisna
    yükseltebilir (ör. `continued_fraction_iterator(sqrt(2))`). Böyle bir hata ham
    biçimde dışarı sızmamalı; temiz bir `UnsafeExpression`e çevrilir (F4). Zaten
    `UnsafeExpression` olanlar (uzunluk sınırı, metin kapısı) olduğu gibi geçer.
    """
    try:
        return thunk()
    except UnsafeExpression:
        raise
    except Exception as exc:  # RecursionError dâhil her şey
        raise UnsafeExpression(f"reçete sonucu üretilirken hata: {exc}") from exc


def _normalize(value: object) -> sympy.Basic:
    """SymPy'nin Basic olmayan dönüşlerini Basic'e çevirir.

    Bazı sympy çağrıları düz Python listesi, sözlük, üreteç ya da değişebilir
    bir kap nesnesi döndürür. Boru hattının geri kalanı her yerde `Basic`
    bekler, bu yüzden tek noktada normalleştiririz. Dizge (str/bytes) asla
    kabul edilmez — aksi halde çalışma anında kurulmuş bir dizge ikinci bir
    eval'a sızabilirdi; bu kapı taşıyıcıdır.
    """
    if isinstance(value, (str, bytes, bytearray)):
        raise UnsafeExpression("reçete metin değeri üretemez")
    if isinstance(value, sympy.matrices.MatrixBase):
        return sympy.ImmutableMatrix(value)
    if isinstance(value, sympy.Basic):
        return value
    if isinstance(value, (bool, int, float, complex)):
        return sympy.sympify(value)
    if isinstance(value, collections.abc.Mapping):
        # Çarpanlara ayırma gibi çağrılar sözlük döndürür.
        return _guard_materialization(
            lambda: sympy.Dict({_normalize(k): _normalize(v) for k, v in value.items()})
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return _guard_materialization(lambda: sympy.Tuple(*[_normalize(v) for v in value]))
    # Üreteç/menzil ve diğer yinelenebilirler (ör. `dict_keys`/`dict_items`:
    # `Iterable` ama `Iterator` değil — F5a). str/bytes yukarıda, `Basic` ve
    # `Matrix` de yukarıda ele alındığı için burada güvenle yakalanırlar.
    if isinstance(value, (range, collections.abc.Iterator)) or isinstance(
        value, collections.abc.Iterable
    ):

        def _build() -> sympy.Basic:
            # Üreteç sonsuz olabilir; asla tüketerek bitirmeye çalışmayız.
            items = list(itertools.islice(iter(value), MAX_RESULT_ITEMS + 1))
            if len(items) > MAX_RESULT_ITEMS:
                raise UnsafeExpression("reçete çok uzun bir sonuç üretti")
            return sympy.Tuple(*[_normalize(v) for v in items])

        return _guard_materialization(_build)
    raise UnsafeExpression("reçete beklenmeyen bir değer türü üretti")


def parse(recipe: str) -> sympy.Basic:
    """Reçete dizesini SymPy nesnesine çevirir.

    Konu bağımsızdır: sympy'nin genel ad alanındaki adların hepsi eşit
    derecede geçerlidir, hiçbir işlem ailesi ayrıcalıklı değildir.
    """
    if "__" in recipe:
        raise UnsafeExpression("çift alt çizgi içeren ifade reddedildi")
    if "import" in recipe:
        raise UnsafeExpression("`import` içeren ifade reddedildi")
    check_recipe(recipe)
    # Bayrağı `parse` içinde ayarlarız ki `parse_with_timeout`un işçi
    # iş parçacığında da geçerli olsun (ContextVar iş parçacığına özeldir).
    token = _evaluating_recipe.set(True)
    try:
        result = _original_parse_expr(
            recipe,
            global_dict=_allowed_namespace(),
            transformations=standard_transformations,
        )
        # Normalleştirme, bayrak HÂLÂ açıkken yapılır (F3): `_normalize` üreteç
        # ve kap gövdelerini burada gerçekleştirir ve o gövdeler çalışırken
        # hem içerik hem de kod-üretimi muhafızları etkin kalmalıdır. Bayrağı
        # normalleştirmeden önce sıfırlamak her iki muhafızı da devre dışı
        # bırakırdı.
        return _normalize(result)
    except UnsafeExpression:
        raise
    except RecursionError as exc:
        # `RecursionError` hiçbir yoldan ham biçimde dışarı sızmamalı (F4).
        raise UnsafeExpression("reçete değerlendirilirken özyineleme sınırı aşıldı") from exc
    finally:
        _evaluating_recipe.reset(token)


def parse_with_timeout(recipe: str, seconds: float = 5.0) -> sympy.Basic:
    """`parse` ile aynı, ancak verilen süreyi aşarsa `EvaluationTimeout` yükseltir.

    Not: iş parçacığı zorla sonlandırılamaz; süresi dolan hesap arka planda
    tükenene kadar devam eder. Faz 1 için kabul edilebilir — üretim partileri
    küçüktür ve süresi dolan reçete zaten doğrulamadan geçemez.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(parse, recipe).result(timeout=seconds)
    except FutureTimeout as exc:
        raise EvaluationTimeout(f"{seconds} saniyede değerlendirilemedi") from exc
    finally:
        pool.shutdown(wait=False)
