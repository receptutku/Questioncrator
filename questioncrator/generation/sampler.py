"""Şablon parametrelerini örnekler ve kısıtlardan süzer (A4).

Rastgelelik dışarıdan verilir (`rng`) — testlerin ve tekrar üretilebilir
partilerin şartı.
"""

from __future__ import annotations

import random

import sympy

from questioncrator.mathenv import parse
from questioncrator.models import Parameter, Template


def _sample_parameter(param: Parameter, rng: random.Random) -> int:
    candidate = rng.randint(param.low, param.high)
    while candidate in param.exclude:
        candidate = rng.randint(param.low, param.high)
    return candidate


def satisfies_constraints(template: Template, bindings: dict[str, int]) -> bool:
    """Şablonun tüm kısıtları bu bağlamada doğru mu?

    Kısıt dizeleri `{p0} > {p1}` gibi yer tutuculu SymPy ifadeleridir.
    """
    for constraint in template.constraints:
        formatted = constraint.format(**{name: f"({value})" for name, value in bindings.items()})
        if parse(formatted) != sympy.true:
            return False
    return True


def sample_bindings(
    template: Template, rng: random.Random, attempts: int = 50
) -> dict[str, int] | None:
    """Kısıtları sağlayan bir bağlama üretir; `attempts` denemede bulamazsa None."""
    for _ in range(attempts):
        bindings = {p.name: _sample_parameter(p, rng) for p in template.parameters}
        if satisfies_constraints(template, bindings):
            return bindings
    return None
