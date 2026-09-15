"""Yapılandırılmış Markdown havuzunu SourceQuestion listesine çevirir (A1).

Faz 1'in tek alım biçimi budur. Serbest format (Word/PDF/OCR) Faz 3'te
bu modülün yanına kardeş modüller olarak eklenir; arayüz aynı kalır.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from questioncrator.models import SourceQuestion

# Büyük/küçük harf duyarsız; aksanlı ya da ASCII yazım, sonda isteğe bağlı `:`.
_HEADING = re.compile(
    r"^###[ \t]+(Soru|Cevap|[CÇ][oö]z[uü]m|Kazan[ıiIİ]m)[ \t]*:?[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_CANONICAL = {"soru": "Soru", "cevap": "Cevap", "cozum": "Çözüm", "kazanim": "Kazanım"}


def _canonical(heading: str) -> str:
    """Başlığı aksansız küçük harfe katlayıp standart adına çevirir."""
    # Türkçe İ/ı casefold ile i'ye inmez; önce elle ASCII'ye katlanır.
    ascii_i = heading.replace("İ", "i").replace("I", "i").replace("ı", "i")
    decomposed = unicodedata.normalize("NFD", ascii_i)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return _CANONICAL[folded]


def _parse_block(block: str) -> dict[str, str]:
    """Tek bir soru bloğunu {başlık: gövde} sözlüğüne çevirir."""
    parts = _HEADING.split(block)
    # split sonucu: [önsöz, başlık1, gövde1, başlık2, gövde2, ...]
    fields: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        fields[_canonical(parts[i])] = parts[i + 1].strip()
    return fields


def parse_pool(content: str) -> list[SourceQuestion]:
    """Markdown havuz içeriğini SourceQuestion listesine çevirir.

    Sorular `---` satırıyla ayrılır. Her blok `### Soru`, `### Cevap`,
    `### Çözüm` ve `### Kazanım` başlıklarını taşıyabilir. `### Soru`
    yoksa blok atlanır. `### Cevap` yoksa soru `needs_review=True` ile
    kaydedilir (elle kontrol listesine düşer). `### Çözüm` gövdesi
    (varsa) insan tarafından okunacak çözüm metni olarak `answer_text`'e
    yazılır; reçete yerine geçmez. Başlıklar büyük/küçük harf ve aksandan
    bağımsızdır (`### cozum:` da olur); içerik önce NFC'ye normalleştirilir.
    """
    content = unicodedata.normalize("NFC", content)
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
                answer_text=fields.get("Çözüm") or None,
                origin="markdown",
            )
        )
    return questions


def load_pool(path: str | Path) -> list[SourceQuestion]:
    """Dosyadan Markdown havuzu yükler ve SourceQuestion listesine çevirir.

    `path` mutlak veya bağıl bir yol olabilir. UTF-8 kodlamasıyla okur.
    Ayrıntılar için `parse_pool()` bkz.
    """
    return parse_pool(Path(path).read_text(encoding="utf-8"))
