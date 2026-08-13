from __future__ import annotations

import random

import pytest

from questioncrator.generation import sampler
from questioncrator.models import Parameter, Template


def sablon(constraints: tuple[str, ...] = ()) -> Template:
    return Template(
        id="t1",
        source_id="s1",
        skeleton="{p0} ve {p1}",
        recipe="{p0}*x + {p1}",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        constraints=constraints,
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
    )


def test_ornekleme_alan_icinde_kalir():
    rng = random.Random(0)
    b = sampler.sample_bindings(sablon(), rng)
    assert set(b) == {"p0", "p1"}
    assert all(-9 <= v <= 9 and v != 0 for v in b.values())


def test_ornekleme_deterministik():
    assert sampler.sample_bindings(sablon(), random.Random(7)) == sampler.sample_bindings(
        sablon(), random.Random(7)
    )


def test_kisit_uygulanir():
    t = sablon(constraints=("{p0} > {p1}",))
    for tohum in range(20):
        b = sampler.sample_bindings(t, random.Random(tohum))
        if b is not None:
            assert b["p0"] > b["p1"]


def test_saglanamayan_kisit_none_dondurur():
    t = sablon(constraints=("{p0} > 1000",))
    assert sampler.sample_bindings(t, random.Random(0), attempts=10) is None


def test_satisfies_constraints_dogrudan():
    t = sablon(constraints=("{p0} > {p1}",))
    assert sampler.satisfies_constraints(t, {"p0": 5, "p1": 2}) is True
    assert sampler.satisfies_constraints(t, {"p0": 2, "p1": 5}) is False


def test_tamamen_haric_tutulan_hata_verir():
    """Parametrenin tüm değer aralığı hariç tutulmuşsa ValueError yükseltir."""
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}",
        recipe="{p0}",
        parameters=(Parameter("p0", 0, 0, (0,)),),  # Sadece 0, fakat 0 hariç tutuluyor
        constraints=(),
        seed_bindings={},
        seed_answer_ops=0,
    )
    with pytest.raises(ValueError):
        sampler.sample_bindings(t, random.Random(0))
