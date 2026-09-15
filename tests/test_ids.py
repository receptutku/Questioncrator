from __future__ import annotations

import random
import re

from questioncrator.ids import new_id


def test_bicim():
    assert re.fullmatch(r"q_[0-9a-f]{12}", new_id("q"))


def test_rng_ile_deterministik():
    assert new_id("s", random.Random(1)) == new_id("s", random.Random(1))


def test_rngsiz_benzersiz():
    assert len({new_id("t") for _ in range(200)}) == 200
