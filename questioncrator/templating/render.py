"""Şablon + bağlamadan soru metni ve çalıştırılabilir reçete üretir."""

from __future__ import annotations

import re

from questioncrator.models import Template

_PLACEHOLDER = re.compile(r"\{(p\d+)\}")
_COMMAND_END = re.compile(r"\\([A-Za-z]+)$")
_COMMAND_START = re.compile(r"\\([A-Za-z]+)")

# Yer tutucudan hemen sonra bunlar geliyorsa negatif değer her zaman
# parantezlenir: `-3^2` -9 okunur, kastedilen (-3)^2'dir.
_POWER_AFTER = frozenset("^²³!")
# Bunlardan sonra negatif sayı çıplak (`-n`) yazılır.
_OPENER_CHARS = frozenset("=([{,;$<>|")
_OPENER_COMMANDS = frozenset({"le", "ge", "leq", "geq"})
# Tekli eksi bunlardan sonra geliyorsa `-(-n)` yerine `n` yazılır.
_UNARY_MINUS_OPENERS = frozenset("=([{,$")
# Değişken gibi davranan, işlenen sayılan LaTeX komutları.
_SYMBOL_COMMANDS = frozenset({"pi", "theta", "alpha", "beta", "gamma"})
# 1 katsayısı yalnız bunların önünde yazılmaz.
_COEFFICIENT_COMMANDS = _SYMBOL_COMMANDS | {
    "sqrt", "frac", "dfrac", "tfrac", "sin", "cos", "tan", "cot", "sec", "csc",
    "log", "ln", "exp",
}


def _binding(bindings: dict[str, int], name: str) -> int:
    """Bağlama değerini döndürür; int olmayan (bool dahil) değeri reddeder.

    Değer metne ve güvenilmeyen reçeteye gömüldüğü için yalnız tam sayı
    kabul edilir; aksi halde bağlama üzerinden metin enjekte edilebilirdi.
    """
    value = bindings[name]
    if type(value) is not int:
        raise TypeError(f"{name}: bağlama değeri int olmalı, {type(value).__name__} verildi")
    return value


def _last_token(stripped: str) -> str:
    """Boşluksuz biten satır parçasının son karakteri ya da LaTeX komutu."""
    if not stripped:
        return ""
    command = _COMMAND_END.search(stripped)
    return command.group(0) if command else stripped[-1]


def _ends_with_operand(head: str) -> bool:
    stripped = head.rstrip()
    if not stripped:
        return False
    command = _COMMAND_END.search(stripped)
    if command:
        return command.group(1) in _SYMBOL_COMMANDS
    return stripped[-1].isalnum() or stripped[-1] in ")]}"


def _is_opener(token: str) -> bool:
    if token.startswith("\\"):
        return token[1:] in _OPENER_COMMANDS
    return token in _OPENER_CHARS


def _drops_unit_coefficient(rest: str) -> bool:
    """1 katsayısı yazılmadan önündeki şeye yapışabilir mi."""
    first = rest[:1]
    if first == "(":
        return True
    if first.isalpha():
        return not rest[1:2].isalpha()
    command = _COMMAND_START.match(rest)
    if command is None:
        return False
    if command.group(1) == "left":
        return rest[command.end():command.end() + 1] == "("
    return command.group(1) in _COEFFICIENT_COMMANDS


def _append_number(text: str, value: int, rest: str) -> str:
    magnitude = abs(value)
    digits = "" if magnitude == 1 and _drops_unit_coefficient(rest) else str(magnitude)
    bare = digits if value >= 0 else "-" + digits
    parenthesized = f"(-{magnitude})"

    cut = text.rfind("\n") + 1
    prefix, line = text[:cut], text[cut:]
    stripped = line.rstrip()
    gap = line[len(stripped):]
    last = _last_token(stripped)
    head = stripped[:-1] if last in ("+", "-") else ""

    # Baştaki `+` atılır: metin başında ya da bir açıcıdan sonra.
    if last == "+" and not _ends_with_operand(head):
        at_start = cut == 0 and not head.strip()
        if at_start or _is_opener(_last_token(head.rstrip())):
            if value < 0 and rest[:1] in _POWER_AFTER:
                return prefix + head + parenthesized
            return prefix + head + bare

    if value >= 0:
        return text + digits
    if rest[:1] in _POWER_AFTER:
        return text + parenthesized
    if last in ("+", "-"):
        if _ends_with_operand(head):
            sign = "-" if last == "+" else "+"
            return prefix + head + sign + gap + digits
        if last == "-" and _last_token(head.rstrip()) in _UNARY_MINUS_OPENERS:
            return prefix + head + digits
        return text + parenthesized
    if last in ("^", "_"):
        return text + "{-" + str(magnitude) + "}"
    if not stripped or _is_opener(last):
        return text + bare
    return text + parenthesized


def render_text(template: Template, bindings: dict[str, int]) -> str:
    """Hocaya ve öğrenciye görünecek soru metni.

    Yalnız `{pN}` yer tutucuları değiştirilir; metindeki diğer süslü
    parantezler (LaTeX) olduğu gibi kalır. Metin, reçeteyle matematiksel
    olarak hiçbir zaman çelişmemelidir; sadelik ikinci plandadır:

    - Negatif değer kuvvet/faktöriyel önünde (`^ ² ³ !`) parantezlenir.
    - İkili `+`/`-` sonrası işaret sadeleşir (`a + -3` -> `a - 3`,
      `a - -3` -> `a + 3`); işlenensiz tekli eksi ve madde işareti
      korunur (`- (-3)`), açıcı sonrası tekli eksi düşer (`= -{p0}` -> `= 3`).
    - Metin başındaki ya da açıcı sonrasındaki `+` atılır.
    - `^`/`_` sonrası `{-n}`; açıcılar (`= ( [ { , ; $ < > |`, `\\le`,
      `\\ge`) sonrası çıplak `-n`; diğer her yerde `(-n)`.
    - 1 katsayısı yalnız tek harfli değişken, `(` ve izinli LaTeX
      komutları önünde yazılmaz (`1x` -> `x`, `-1\\sqrt` -> `-\\sqrt`).
    """
    skeleton = template.skeleton
    text = ""
    position = 0
    for match in _PLACEHOLDER.finditer(skeleton):
        text += skeleton[position:match.start()]
        position = match.end()
        value = _binding(bindings, match.group(1))
        text = _append_number(text, value, skeleton[position:])
    return text + skeleton[position:]


def render_recipe(template: Template, bindings: dict[str, int]) -> str:
    """SymPy'ye verilecek reçete.

    Yalnız `{pN}` yer tutucuları değiştirilir. Değerler parantezlenir:
    parantezsiz `-3**2` Python'da -9 verir, oysa kastedilen (-3)^2 = 9'dur.
    """
    return _PLACEHOLDER.sub(lambda m: f"({_binding(bindings, m.group(1))})", template.recipe)
