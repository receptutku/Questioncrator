"""Kayıt kimlikleri: `önek_12onaltılık`.

Sıra numarası yerine rastgele kimlik kullanılır: aynı çalışma alanında
iki hoca aynı anda üretim yaptığında çakışma olmaz.
"""

from __future__ import annotations

import random
import secrets


def new_id(prefix: str, rng: random.Random | None = None) -> str:
    bits = rng.getrandbits(48) if rng is not None else secrets.randbits(48)
    return f"{prefix}_{bits:012x}"
