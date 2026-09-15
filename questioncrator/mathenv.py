"""SymPy ifadelerini kısıtlı ad alanında, zaman aşımlı biçimde değerlendirir.

Reçeteler hocanın dosyalarından gelir. Yine de düz `eval` kullanmayız:
sympy'nin kendi ayrıştırıcısını, yalnız sympy adlarını içeren bir küresel
sözlükle çalıştırırız. Böylece reçete dili "herhangi bir SymPy ifadesi"
kadar geniş kalır ama Python'un geri kalanına erişemez.
"""

from __future__ import annotations

import functools
import io
import keyword
import re
import tokenize
import types
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations


class UnsafeExpression(ValueError):
    """Reçete, ayrıştırılmadan önce sözdizimsel bir güvenlik kuralına takıldı."""


class EvaluationTimeout(Exception):
    """Reçete verilen süre içinde değerlendirilemedi."""


MAX_RECIPE_LENGTH = 2000
MAX_NUMBER_DIGITS = 12

# İkincil koruma: yan etkili ya da ikinci bir eval açan sympy adları.
# Birincil koruma dizge yasağı + alt çizgi yasağıdır (bkz. check_recipe).
DENIED_NAMES = frozenset(
    {
        "sympify", "S", "parse_expr", "lambdify", "preview", "init_printing",
        "init_session", "var", "pprint", "pretty_print", "pager_print",
        "interactive_traversal", "textplot", "dotprint", "test", "doctest",
        "exec", "eval", "open", "compile", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "input", "help", "breakpoint", "exit", "quit",
    }
)  # fmt: skip
DENIED_PREFIXES = ("_", "plot", "print_", "pprint")
_ALLOWED_KEYWORDS = frozenset({"True", "False", "None", "and", "or", "not", "in", "is"})


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
            name = token.string
            if keyword.iskeyword(name) and name not in _ALLOWED_KEYWORDS:
                raise UnsafeExpression(f"`{name}` içeren reçete reddedildi")
            if name in DENIED_NAMES or name.startswith(DENIED_PREFIXES):
                raise UnsafeExpression(f"`{name}` adı reçetede kullanılamaz")


@functools.cache
def _base_namespace() -> dict[str, object]:
    namespace: dict[str, object] = {}
    for name in sympy.__all__:
        if name in DENIED_NAMES or name.startswith(DENIED_PREFIXES):
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


def _normalize(value: object) -> sympy.Basic:
    """SymPy'nin Basic olmayan dönüşlerini Basic'e çevirir.

    Bazı sympy çağrıları düz Python listesi ya da değişebilir bir kap
    nesnesi döndürür. Boru hattının geri kalanı her yerde `Basic` bekler
    (`count_ops`, `srepr`, `latex`), bu yüzden tek noktada normalleştiririz.
    """
    if isinstance(value, sympy.matrices.MatrixBase):
        return sympy.ImmutableMatrix(value)
    if isinstance(value, (list, tuple, set)):
        return sympy.Tuple(*[_normalize(v) for v in value])
    if isinstance(value, sympy.Basic):
        return value
    return sympy.sympify(value)


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
    return _normalize(
        parse_expr(
            recipe,
            global_dict=_allowed_namespace(),
            transformations=standard_transformations,
        )
    )


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
