"""İşçi→ebeveyn yanıtları için tür etiketli JSON kodeği.

İşçiden gelen bayt güvenilmez kabul edilir. Pickle bu yönde kullanılmaz:
açma sırasında sınıf kurar, nitelik yazar ve bellek ayırır; beyaz listeyle
kapatılamayacak kadar geniş bir yüzeydir. Burada yalnız veri taşınır.

İzinli değerler: `None`, `bool`, `int` (en çok 4300 hane), sonlu `float`,
`str`, `list`, `tuple` (`{"$t": [...]}`), yalnız metin anahtarlı `dict`
(`{"$d": {...}}`) ve `questioncrator.models` veri sınıfları
(`{"$m": [ad, {"$d": alanlar}]}`; kurulum `cls(**alanlar)`, eksik ya da
bilinmeyen alan reddedilir). Tür birebir eşleşmelidir; alt sınıflar
kodlanmaz. İstisnalar yalnız ad ve mesaj olarak taşınır ve ebeveynde açık
bir kayıttan kurulur; kayıtta olmayanlar çöküş mesajına dönüşür.

Ebeveyn çözmeden önce metni kaba sınırlarla tarar (sayı hanesi, jeton
sayısı), çözerken yinelenen anahtarı ve sonlu olmayan sayıyı reddeder,
ardından derinliği ve öğe sayısını tam olarak denetler. Boyut sınırı
çerçeve düzeyinde, çağıranda uygulanır.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import math
import re
from collections.abc import Callable
from typing import Any

from questioncrator import models

MAX_DEPTH = 64
MAX_ITEMS = 200_000
MAX_INT_DIGITS = 4300
# Etiketler (`$t`, `$d`, `$m`) JSON jetonu ekler; kaba ön tarama bu payı tanır.
_MAX_TOKENS = 4 * MAX_ITEMS + 64


class WireError(ValueError):
    """Değer kodlanamadı ya da yanıt reddedildi."""


# --- Kayıtlar ------------------------------------------------------------

_MODELS: dict[str, type] = {
    name: obj
    for name, obj in vars(models).items()
    if isinstance(obj, type) and dataclasses.is_dataclass(obj) and obj.__module__ == models.__name__
}
_MODEL_NAMES: dict[type, str] = {cls: name for name, cls in _MODELS.items()}
_MODEL_FIELDS: dict[type, tuple[str, ...]] = {
    cls: tuple(f.name for f in dataclasses.fields(cls) if f.init) for cls in _MODELS.values()
}


def model_names() -> list[str]:
    return sorted(_MODELS)


_Builder = Callable[[str], BaseException]
# Anahtar `modül.nitelikli_ad`; değer (sınıfı veren çözücü, isteğe bağlı kurucu).
# Paket sınıfları tembel içe aktarılır: adlar sabittir, işçi seçemez.
_EXCEPTIONS: dict[str, tuple[Callable[[], type], _Builder | None]] = {}


def _lazy(module: str, name: str) -> Callable[[], type]:
    def resolve() -> type:
        return getattr(importlib.import_module(module), name)

    return resolve


for _cls in (
    ValueError,
    TypeError,
    ZeroDivisionError,
    ArithmeticError,
    OverflowError,
    NotImplementedError,
    KeyError,
    IndexError,
    RecursionError,
    MemoryError,
    RuntimeError,
):
    _EXCEPTIONS[f"builtins.{_cls.__qualname__}"] = (lambda c=_cls: c, None)

for _module, _name in (
    ("questioncrator.mathenv", "UnsafeExpression"),
    ("questioncrator.mathenv", "EvaluationTimeout"),
    ("questioncrator.templating.extract", "NoParametersFound"),
):
    _EXCEPTIONS[f"{_module}.{_name}"] = (_lazy(_module, _name), None)


def _qualified(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def register_exception(cls: type, from_message: _Builder | None = None) -> None:
    """Ebeveynde yeniden yükseltilebilecek bir istisna sınıfı ekler.

    Kurucusu tek metin argüman almayan sınıflar için `from_message` verilir.
    """
    if not (isinstance(cls, type) and issubclass(cls, Exception)):
        raise TypeError("yalnız Exception alt sınıfları kaydedilebilir")
    if issubclass(cls, (StopIteration, StopAsyncIteration)):
        raise TypeError("yineleme durdurma istisnaları kaydedilemez")
    _EXCEPTIONS[_qualified(cls)] = (lambda: cls, from_message)


def unregister_exception(cls: type) -> None:
    _EXCEPTIONS.pop(_qualified(cls), None)


# --- İşçi tarafı: kodlama ------------------------------------------------


def _refuse(obj: object, detail: str = "") -> WireError:
    suffix = f" ({detail})" if detail else ""
    return WireError(f"sonuç türü aktarılamaz: {_qualified(type(obj))}{suffix}")


class _Budget:
    def __init__(self) -> None:
        self.items = 0

    def take(self) -> None:
        self.items += 1
        if self.items > MAX_ITEMS:
            raise WireError(f"sonuç {MAX_ITEMS} öğe sınırını aştı")


def _check_depth(level: int) -> None:
    if level > MAX_DEPTH:
        raise WireError(f"sonuç {MAX_DEPTH} derinlik sınırını aştı")


def _encode(obj: Any, level: int, budget: _Budget) -> Any:
    """`level`: değeri çevreleyen JSON kabı sayısı (zarf hariç)."""
    budget.take()
    kind = type(obj)
    if obj is None or kind is bool or kind is str:
        return obj
    if kind is int:
        # 4300 hane ≈ 14 284 bit; kesin denetimi `json.dumps` yapar.
        if obj.bit_length() > 14_300:
            raise _refuse(obj, f"{MAX_INT_DIGITS} haneden uzun")
        return obj
    if kind is float:
        if not math.isfinite(obj):
            raise _refuse(obj, "sonlu değil")
        return obj
    if kind is list:
        _check_depth(level + 1)
        return [_encode(item, level + 1, budget) for item in obj]
    if kind is tuple:
        _check_depth(level + 2)
        return {"$t": [_encode(item, level + 2, budget) for item in obj]}
    if kind is dict:
        _check_depth(level + 2)
        encoded: dict[str, Any] = {}
        for key, value in obj.items():
            if type(key) is not str:
                raise _refuse(key, "sözlük anahtarı")
            encoded[key] = _encode(value, level + 2, budget)
        return {"$d": encoded}
    name = _MODEL_NAMES.get(kind)
    if name is not None:
        _check_depth(level + 4)
        fields = {f: _encode(getattr(obj, f), level + 4, budget) for f in _MODEL_FIELDS[kind]}
        return {"$m": [name, {"$d": fields}]}
    raise _refuse(obj)


def _dump(document: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(document, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    except ValueError as exc:  # int hane sınırı vb.
        raise WireError(f"sonuç kodlanamadı: {exc}") from None
    return text.encode("ascii")


def dumps_ok(value: Any, *, retire: bool) -> bytes:
    return _dump({"status": "ok", "value": _encode(value, 0, _Budget()), "retire": retire})


def dumps_error(exc: BaseException, *, retire: bool) -> bytes:
    try:
        # Tek metin argümanlı istisnada argümanın kendisi taşınır: `str(KeyError(x))`
        # tırnak ekler, ebeveynde yeniden kurulunca mesaj değişirdi.
        args = exc.args
        message = args[0] if len(args) == 1 and type(args[0]) is str else str(exc)
    except Exception:  # noqa: BLE001 — mesajı üretemeyen istisna
        message = "<mesaj alınamadı>"
    document = {
        "status": "err",
        "exc": _qualified(type(exc)),
        "message": message,
        "retire": retire,
    }
    return _dump(document)


def dumps_crash(message: str, *, retire: bool) -> bytes:
    return _dump({"status": "crash", "message": str(message), "retire": retire})


# --- Ebeveyn tarafı: çözme -----------------------------------------------

# Doğrusal süre şarttır (ön tarama süre sınırı dışında, ebeveynde koşar):
# - Atomik tekrarlar geri izlemeyi keser.
# - Kapanmamış dizge metin sonuna kadar eşleşir (`\Z`); aksi halde `sub` her
#   sonraki tırnaktan yeniden tarar ve `"\"\"...` yükü O(n²) olur. Bozuk JSON'u
#   zaten `json.loads` reddeder.
_STRING = re.compile(r'"[^"\\]*+(?:\\.[^"\\]*+)*+(?:"|\\?\Z)')
# Geriye bakış eşleşmeyi yalnız rakam koşusunun başında dener; yoksa 4300 hanelik
# koşuların her iç konumu yeniden sayılır ve süre O(n·4300) olur.
_LONG_NUMBER = re.compile(rf"(?<![0-9])[0-9]{{{MAX_INT_DIGITS + 1}}}")


def _prescan(text: str) -> None:
    """`json.loads` öncesi C hızında kaba sınırlar (bellek ve süre üst sınırı)."""
    bare = _STRING.sub('""', text)
    if _LONG_NUMBER.search(bare):
        raise WireError(f"yanıtta {MAX_INT_DIGITS} haneden uzun sayı var")
    tokens = bare.count("[") + bare.count("{") + bare.count(",") + bare.count(":")
    if tokens > _MAX_TOKENS:
        raise WireError("yanıt jeton sınırını aştı")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WireError(f"yinelenen anahtar: {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise WireError(f"sonlu olmayan sayı: {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise WireError("sonlu olmayan sayı")
    return value


def _decode(node: Any, level: int, budget: _Budget) -> Any:
    budget.take()
    kind = type(node)
    if node is None or kind in (bool, str, int, float):
        return node
    if kind is list:
        _check_depth(level + 1)
        return [_decode(item, level + 1, budget) for item in node]
    if kind is not dict or len(node) != 1:
        raise WireError("etiketsiz ya da bozuk nesne")
    ((tag, payload),) = node.items()
    if tag == "$t":
        _check_depth(level + 2)
        if type(payload) is not list:
            raise WireError("bozuk demet")
        return tuple(_decode(item, level + 2, budget) for item in payload)
    if tag == "$d":
        _check_depth(level + 2)
        if type(payload) is not dict:
            raise WireError("bozuk sözlük")
        return {key: _decode(value, level + 2, budget) for key, value in payload.items()}
    if tag == "$m":
        _check_depth(level + 4)
        return _decode_model(payload, level, budget)
    raise WireError(f"bilinmeyen etiket: {tag!r}")


def _decode_model(payload: Any, level: int, budget: _Budget) -> Any:
    if type(payload) is not list or len(payload) != 2 or type(payload[0]) is not str:
        raise WireError("bozuk veri sınıfı")
    name, wrapped = payload
    cls = _MODELS.get(name)
    if cls is None:
        raise WireError(f"bilinmeyen veri sınıfı: {name!r}")
    if type(wrapped) is not dict or set(wrapped) != {"$d"} or type(wrapped["$d"]) is not dict:
        raise WireError("bozuk veri sınıfı alanları")
    raw_fields = wrapped["$d"]
    expected = _MODEL_FIELDS[cls]
    if set(raw_fields) != set(expected):
        unknown = sorted(set(raw_fields) - set(expected))
        missing = sorted(set(expected) - set(raw_fields))
        raise WireError(f"{name} alanları uyuşmuyor (bilinmeyen {unknown}, eksik {missing})")
    values = {key: _decode(raw_fields[key], level + 4, budget) for key in expected}
    try:
        return cls(**values)
    except Exception as exc:  # noqa: BLE001
        raise WireError(f"{name} kurulamadı: {type(exc).__name__}") from None


def _build_exception(name: str, message: str) -> BaseException | None:
    entry = _EXCEPTIONS.get(name)
    if entry is None:
        return None
    resolve, from_message = entry
    try:
        cls = resolve()
        exc = from_message(message) if from_message is not None else cls(message)
    except Exception:  # noqa: BLE001 — kurulamayan istisna çöküşe düşer
        return None
    if type(exc) is not cls or not isinstance(exc, Exception):
        return None
    return exc


_ENVELOPE_KEYS = {
    "ok": {"status", "value", "retire"},
    "err": {"status", "exc", "message", "retire"},
    "crash": {"status", "message", "retire"},
}


def loads_reply(raw: bytes) -> tuple[str, Any, bool]:
    """Yanıtı çözer: `("ok", değer, retire)`, `("err", istisna, retire)` ya da
    `("crash", mesaj, retire)`. Reddedilen yanıt `WireError` yükseltir."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise WireError("yanıt UTF-8 değil") from None
    _prescan(text)
    try:
        document = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except WireError:
        raise
    except (ValueError, RecursionError) as exc:
        raise WireError(f"yanıt çözülemedi: {type(exc).__name__}") from None

    if type(document) is not dict:
        raise WireError("yanıt zarfı nesne değil")
    status = document.get("status")
    if status not in _ENVELOPE_KEYS or set(document) != _ENVELOPE_KEYS[status]:
        raise WireError("yanıt zarfı geçersiz")
    retire = document["retire"]
    if type(retire) is not bool:
        raise WireError("yanıt zarfı geçersiz")
    if status == "ok":
        return "ok", _decode(document["value"], 0, _Budget()), retire
    message = document["message"]
    if type(message) is not str:
        raise WireError("yanıt zarfı geçersiz")
    if status == "crash":
        return "crash", message, retire
    name = document["exc"]
    if type(name) is not str:
        raise WireError("yanıt zarfı geçersiz")
    exc = _build_exception(name, message)
    if exc is None:
        return "crash", f"{name}: {message}", retire
    return "err", exc, retire
