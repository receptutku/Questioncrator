"""Şablon + bağlamadan soru metni ve çalıştırılabilir reçete üretir."""

from __future__ import annotations

import re

from questioncrator.models import Template

_PLACEHOLDER = re.compile(r"\{(p\d+)\}")
# Eksi işareti bunlardan sonra geliyorsa işaret değil, ifadenin başıdır.
_OPENERS = frozenset("=([{,;:$")
# Bunlardan sonra gelen negatif sayı parantez içine alınır.
_MULTIPLIERS = ("*", "/", "×", "·", "^", "\\cdot", "\\times")


def _binding(bindings: dict[str, int], name: str) -> int:
    """Bağlama değerini döndürür; int olmayan (bool dahil) değeri reddeder.

    Değer metne ve güvenilmeyen reçeteye gömüldüğü için yalnız tam sayı
    kabul edilir; aksi halde bağlama üzerinden metin enjekte edilebilirdi.
    """
    value = bindings[name]
    if type(value) is not int:
        raise TypeError(f"{name}: bağlama değeri int olmalı, {type(value).__name__} verildi")
    return value


def _append_number(text: str, value: int, is_coefficient: bool) -> str:
    magnitude = abs(value)
    body = "" if is_coefficient and magnitude == 1 else str(magnitude)
    if value >= 0:
        return text + body

    stripped = text.rstrip()
    gap = text[len(stripped):]
    if stripped.endswith("+"):
        return stripped[:-1] + "-" + gap + body
    if stripped.endswith("-"):
        before = stripped[:-1].rstrip()
        if not before or before[-1] in _OPENERS:
            return stripped[:-1] + body
        return stripped[:-1] + "+" + gap + body
    if stripped.endswith(_MULTIPLIERS):
        return text + f"(-{magnitude})"
    return text + "-" + body


def render_text(template: Template, bindings: dict[str, int]) -> str:
    """Hocaya ve öğrenciye görünecek soru metni.

    Yalnız `{pN}` yer tutucuları değiştirilir; metindeki diğer süslü
    parantezler (LaTeX) olduğu gibi kalır. Negatif değerlerde önceki
    işaret sadeleştirilir (`+ -4` -> `- 4`), bir harf ya da parantez
    önündeki 1 katsayısı yazılmaz (`1x` -> `x`).
    """
    skeleton = template.skeleton
    text = ""
    position = 0
    for match in _PLACEHOLDER.finditer(skeleton):
        text += skeleton[position:match.start()]
        position = match.end()
        following = skeleton[position:position + 1]
        is_coefficient = following.isalpha() or following in ("\\", "(")
        text = _append_number(text, _binding(bindings, match.group(1)), is_coefficient)
    return text + skeleton[position:]


def render_recipe(template: Template, bindings: dict[str, int]) -> str:
    """SymPy'ye verilecek reçete.

    Yalnız `{pN}` yer tutucuları değiştirilir. Değerler parantezlenir:
    parantezsiz `-3**2` Python'da -9 verir, oysa kastedilen (-3)^2 = 9'dur.
    """
    return _PLACEHOLDER.sub(lambda m: f"({_binding(bindings, m.group(1))})", template.recipe)
