"""İşçi→ebeveyn yanıtları için tür etiketli JSON kodeği (işçi baytı güvenilmez).

Taşınan: None, bool, int (≤4300 hane), sonlu float, str, list, tuple (`$t`),
metin anahtarlı dict (`$d`) ve `models` veri sınıfları (`$m`, alanlar tür
ipucuna göre denetlenir; desteklenmeyen ipucu içe aktarmada hata verir).
İstisnalar ad + mesaj (≤4000 karakter) olarak açık bir kayıttan kurulur.
Ebeveyn: düz `json.loads` (ortamdan bağımsız hane sınırı, sonlu sayı, tekil
anahtar) + derinlik/öğe bütçeli yürüyüş + sıra numarası eşleşmesi. Boyut
sınırını çerçeve okuyucu uygular.
"""

from __future__ import annotations

import dataclasses
import json
import math
import types
import typing
from collections.abc import Callable
from typing import Any

from questioncrator import models
from questioncrator.mathenv import EvaluationTimeout, UnsafeExpression
from questioncrator.templating.extract import NoParametersFound

MAX_DEPTH = 64
MAX_ITEMS = 200_000
MAX_INT_DIGITS = 4300
MAX_MESSAGE = 4000


class WireError(ValueError):
    """Değer kodlanamadı ya da yanıt reddedildi."""


def _qualified(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


# --- Veri sınıfı kaydı ve alan tipi denetimi ----------------------------

_MODELS: dict[str, type] = {
    name: obj
    for name, obj in vars(models).items()
    if isinstance(obj, type) and dataclasses.is_dataclass(obj) and obj.__module__ == models.__name__
}
_MODEL_NAMES: dict[type, str] = {cls: name for name, cls in _MODELS.items()}
_MODEL_FIELDS: dict[type, tuple[str, ...]] = {
    cls: tuple(f.name for f in dataclasses.fields(cls) if f.init) for cls in _MODELS.values()
}

_Check = Callable[[Any], bool]


def _hint_check(hint: Any) -> _Check:
    """Alan ipucunu ucuz bir tür denetleyicisine çevirir (`object`: her tel değeri)."""
    if hint is object:
        return lambda value: True
    if hint is None or hint is type(None):
        return lambda value: value is None
    if hint in (bool, int, str):
        return lambda value: type(value) is hint
    if hint is float:
        return lambda value: type(value) in (int, float)
    if hint in _MODEL_NAMES:
        return lambda value: type(value) is hint
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (types.UnionType, typing.Union):
        options = [_hint_check(arg) for arg in args]
        return lambda value: any(check(value) for check in options)
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        item = _hint_check(args[0])
        return lambda value: type(value) is tuple and all(item(v) for v in value)
    if origin is tuple and args:
        items = [_hint_check(arg) for arg in args]
        return lambda value: (
            type(value) is tuple
            and len(value) == len(items)
            and all(check(v) for check, v in zip(items, value, strict=True))
        )
    if origin is list and len(args) == 1:
        item = _hint_check(args[0])
        return lambda value: type(value) is list and all(item(v) for v in value)
    if origin is dict and len(args) == 2 and args[0] is str:
        item = _hint_check(args[1])
        return lambda value: type(value) is dict and all(item(v) for v in value.values())
    raise TypeError(f"desteklenmeyen alan ipucu: {hint!r}")


_MODEL_CHECKS: dict[type, dict[str, _Check]] = {}
for _cls in _MODELS.values():
    _hints = typing.get_type_hints(_cls)
    _MODEL_CHECKS[_cls] = {f.name: _hint_check(_hints[f.name]) for f in dataclasses.fields(_cls)}


def model_names() -> list[str]:
    return sorted(_MODELS)


# --- İstisna kaydı -------------------------------------------------------

_Builder = Callable[[str], BaseException]
_EXCEPTIONS: dict[str, tuple[type, _Builder | None]] = {}


def register_exception(cls: type, from_message: _Builder | None = None) -> None:
    """Ebeveynde yeniden yükseltilebilecek bir istisna sınıfı ekler.

    Kurucusu tek metin argüman almayan sınıflar için `from_message` verilir.
    """
    if not (isinstance(cls, type) and issubclass(cls, Exception)):
        raise TypeError("yalnız Exception alt sınıfları kaydedilebilir")
    if issubclass(cls, (StopIteration, StopAsyncIteration)):
        raise TypeError("yineleme durdurma istisnaları kaydedilemez")
    _EXCEPTIONS[_qualified(cls)] = (cls, from_message)


def unregister_exception(cls: type) -> None:
    _EXCEPTIONS.pop(_qualified(cls), None)


for _exc in (
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
    SyntaxError,
    AttributeError,
    UnsafeExpression,
    EvaluationTimeout,
    NoParametersFound,
):
    register_exception(_exc)


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
        # 4300 hane ≈ 14 284 bit; kesin sınırı ebeveynin `parse_int`i uygular.
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
        text = json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return text.encode("utf-8")
    except (ValueError, UnicodeEncodeError) as exc:  # int hane sınırı, eşsiz vekil vb.
        raise WireError(f"sonuç kodlanamadı: {type(exc).__name__}") from None


def dumps_ok(value: Any, *, retire: bool, seq: int) -> bytes:
    encoded = _encode(value, 0, _Budget())
    return _dump({"status": "ok", "value": encoded, "retire": retire, "seq": seq})


def dumps_error(exc: BaseException, *, retire: bool, seq: int) -> bytes:
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
        "message": message[:MAX_MESSAGE],
        "retire": retire,
        "seq": seq,
    }
    return _dump(document)


def dumps_crash(message: str, *, retire: bool, seq: int) -> bytes:
    return _dump(
        {"status": "crash", "message": str(message)[:MAX_MESSAGE], "retire": retire, "seq": seq}
    )


# --- Ebeveyn tarafı: çözme -----------------------------------------------


def _parse_int(text: str) -> int:
    # `sys.set_int_max_str_digits` ayarından bağımsız: sınırı burada uygularız.
    if len(text) - text.startswith("-") > MAX_INT_DIGITS:
        raise WireError(f"yanıtta {MAX_INT_DIGITS} haneden uzun sayı var")
    return int(text)


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise WireError("sonlu olmayan sayı")
    return value


def _reject_constant(name: str) -> Any:
    raise WireError(f"sonlu olmayan sayı: {name}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WireError(f"yinelenen anahtar: {key[:80]!r}")
        result[key] = value
    return result


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
    raise WireError(f"bilinmeyen etiket: {tag[:80]!r}")


def _decode_model(payload: Any, level: int, budget: _Budget) -> Any:
    if type(payload) is not list or len(payload) != 2 or type(payload[0]) is not str:
        raise WireError("bozuk veri sınıfı")
    name, wrapped = payload
    cls = _MODELS.get(name)
    if cls is None:
        raise WireError(f"bilinmeyen veri sınıfı: {name[:80]!r}")
    if type(wrapped) is not dict or set(wrapped) != {"$d"} or type(wrapped["$d"]) is not dict:
        raise WireError("bozuk veri sınıfı alanları")
    raw_fields = wrapped["$d"]
    expected = _MODEL_FIELDS[cls]
    if set(raw_fields) != set(expected):
        raise WireError(f"{name} alanları uyuşmuyor")
    values = {key: _decode(raw_fields[key], level + 4, budget) for key in expected}
    checks = _MODEL_CHECKS[cls]
    for key, value in values.items():
        if not checks[key](value):
            raise WireError(f"{name}.{key} alan tipi uyuşmuyor")
    try:
        return cls(**values)
    except Exception as exc:  # noqa: BLE001
        raise WireError(f"{name} kurulamadı: {type(exc).__name__}") from None


def _build_exception(name: str, message: str) -> BaseException | None:
    entry = _EXCEPTIONS.get(name)
    if entry is None:
        return None
    cls, from_message = entry
    try:
        exc = from_message(message) if from_message is not None else cls(message)
    except Exception:  # noqa: BLE001 — kurulamayan istisna çöküşe düşer
        return None
    return exc if type(exc) is cls else None


_ENVELOPE_KEYS = {
    "ok": {"status", "value", "retire", "seq"},
    "err": {"status", "exc", "message", "retire", "seq"},
    "crash": {"status", "message", "retire", "seq"},
}


def loads_reply(raw: bytes, *, seq: int) -> tuple[str, Any, bool]:
    """Yanıtı çözer: `("ok", değer, retire)`, `("err", istisna, retire)` ya da
    `("crash", mesaj, retire)`. Reddedilen yanıt `WireError` yükseltir."""
    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_int=_parse_int,
            parse_float=_finite_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_no_duplicates,
        )
    except WireError:
        raise
    except (ValueError, RecursionError) as exc:  # UnicodeDecodeError dahil
        raise WireError(f"yanıt çözülemedi: {type(exc).__name__}") from None

    status = document.get("status") if type(document) is dict else None
    if status not in _ENVELOPE_KEYS or set(document) != _ENVELOPE_KEYS[status]:
        raise WireError("yanıt zarfı geçersiz")
    if type(document["seq"]) is not int or document["seq"] != seq:
        raise WireError("yanıt sıra numarası uyuşmuyor")
    retire = document["retire"]
    if type(retire) is not bool:
        raise WireError("yanıt zarfı geçersiz")
    if status == "ok":
        return "ok", _decode(document["value"], 0, _Budget()), retire
    message = document["message"]
    if type(message) is not str:
        raise WireError("yanıt zarfı geçersiz")
    message = message[:MAX_MESSAGE]
    if status == "crash":
        return "crash", message, retire
    name = document["exc"]
    if type(name) is not str:
        raise WireError("yanıt zarfı geçersiz")
    exc = _build_exception(name, message)
    if exc is None:
        return "crash", f"{name[:200]}: {message}"[:MAX_MESSAGE], retire
    return "err", exc, retire
