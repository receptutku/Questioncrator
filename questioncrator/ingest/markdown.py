"""Yapılandırılmış Markdown havuzunu SourceQuestion listesine çevirir (A1).

Faz 1'in tek alım biçimi budur. Serbest format (Word/PDF/OCR) Faz 3'te
bu modülün yanına kardeş modüller olarak eklenir; arayüz aynı kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

from questioncrator.models import SourceQuestion

_HEADING = re.compile(r"^###\s+(Soru|Cevap|Kazanım)\s*$", re.MULTILINE)


def _parse_block(block: str) -> dict[str, str]:
    """Tek bir soru bloğunu {başlık: gövde} sözlüğüne çevirir."""
    parts = _HEADING.split(block)
    # split sonucu: [önsöz, başlık1, gövde1, başlık2, gövde2, ...]
    fields: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        fields[parts[i]] = parts[i + 1].strip()
    return fields


def parse_pool(content: str) -> list[SourceQuestion]:
    """Markdown havuz içeriğini SourceQuestion listesine çevirir.

    Sorular `---` satırıyla ayrılır. Her blok `### Soru`, `### Cevap`,
    ve `### Kazanım` başlıklarını taşıyabilir. `### Soru` yoksa blok
    atlanır. `### Cevap` yoksa soru `needs_review=True` ile kaydedilir
    (elle kontrol listesine düşer).
    """
    questions: list[SourceQuestion] = []
    for block in re.split(r"^---\s*$", content, flags=re.MULTILINE):
        fields = _parse_block(block)
        text = fields.get("Soru", "").strip()
        if not text:
            continue
        recipe = fields.get("Cevap") or None
        questions.append(
            SourceQuestion(
                id=f"s{len(questions) + 1}",
                text=text,
                recipe=recipe,
                objective=fields.get("Kazanım") or None,
                needs_review=recipe is None,
            )
        )
    return questions


def load_pool(path: str | Path) -> list[SourceQuestion]:
    """Dosyadan Markdown havuzu yükler ve SourceQuestion listesine çevirir.

    `path` mutlak veya bağıl bir yol olabilir. UTF-8 kodlamasıyla okur.
    Ayrıntılar için `parse_pool()` bkz.
    """
    return parse_pool(Path(path).read_text(encoding="utf-8"))
