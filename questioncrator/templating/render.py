"""Şablon + bağlamadan soru metni ve çalıştırılabilir reçete üretir."""

from __future__ import annotations

from questioncrator.models import Template


def render_text(template: Template, bindings: dict[str, int]) -> str:
    """Hocaya ve öğrenciye görünecek soru metni."""
    return template.skeleton.format(**bindings)


def render_recipe(template: Template, bindings: dict[str, int]) -> str:
    """SymPy'ye verilecek reçete.

    Değerler parantezlenir: parantezsiz `-3**2` Python'da -9 verir, oysa
    kastedilen (-3)^2 = 9'dur.
    """
    return template.recipe.format(**{name: f"({value})" for name, value in bindings.items()})
