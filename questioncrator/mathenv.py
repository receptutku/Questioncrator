"""SymPy ifadelerini kısıtlı ad alanında, zaman aşımlı biçimde değerlendirir.

Reçeteler hocanın dosyalarından gelir. Yine de düz `eval` kullanmayız:
sympy'nin kendi ayrıştırıcısını, yalnız sympy adlarını içeren bir küresel
sözlükle çalıştırırız. Böylece reçete dili "herhangi bir SymPy ifadesi"
kadar geniş kalır ama Python'un geri kalanına erişemez.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations


class UnsafeExpression(ValueError):
    """Reçete, ayrıştırılmadan önce sözdizimsel bir güvenlik kuralına takıldı."""


class EvaluationTimeout(Exception):
    """Reçete verilen süre içinde değerlendirilemedi."""


def _allowed_namespace() -> dict[str, object]:
    ns: dict[str, object] = {name: getattr(sympy, name) for name in sympy.__all__}
    # Yerleşik Python fonksiyonlarına erişimi kapat; sympy adları yeter.
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
