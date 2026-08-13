"""Yapılandırılmış Markdown havuzunu SourceQuestion listesine çevirir (A1).

Faz 1'in tek alım biçimi budur. Serbest format (Word/PDF/OCR) Faz 3'te
bu modülün yanına kardeş modüller olarak eklenir; arayüz aynı kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

from questioncrator.models import SourceQuestion

_BASLIK = re.compile(r"^###\s+(Soru|Cevap|Kazanım)\s*$", re.MULTILINE)


def _parse_block(block: str) -> dict[str, str]:
    """Tek bir soru bloğunu {başlık: gövde} sözlüğüne çevirir."""
    parcalar = _BASLIK.split(block)
    # split sonucu: [önsöz, başlık1, gövde1, başlık2, gövde2, ...]
    alanlar: dict[str, str] = {}
    for i in range(1, len(parcalar) - 1, 2):
        alanlar[parcalar[i]] = parcalar[i + 1].strip()
    return alanlar


def parse_pool(content: str) -> list[SourceQuestion]:
    sorular: list[SourceQuestion] = []
    for block in re.split(r"^---\s*$", content, flags=re.MULTILINE):
        alanlar = _parse_block(block)
        metin = alanlar.get("Soru", "").strip()
        if not metin:
            continue
        recete = alanlar.get("Cevap") or None
        sorular.append(
            SourceQuestion(
                id=f"s{len(sorular) + 1}",
                text=metin,
                recipe=recete,
                objective=alanlar.get("Kazanım") or None,
                needs_review=recete is None,
            )
        )
    return sorular


def load_pool(path: str | Path) -> list[SourceQuestion]:
    return parse_pool(Path(path).read_text(encoding="utf-8"))
