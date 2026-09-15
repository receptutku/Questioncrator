"""Kaynak sorudan otomatik parametrik şablon çıkarır (A3).

Deterministiktir ve konudan bağımsızdır: reçetenin ne anlama geldiğini
bilmez, yalnız içindeki sayısal literalleri parametreye çevirir. Bu yüzden
kaynak sorunun hangi konudan geldiğinin bir önemi yoktur; bugün havuzda
olmayan bir konu da aynı yoldan geçer.
"""

from __future__ import annotations

import io
import re
import tokenize

from questioncrator.mathenv import parse_with_timeout
from questioncrator.models import Parameter, SourceQuestion, Template

# Varsayılan örnekleme aralığı. Şablon başına özelleştirme Faz 2'nin işi.
DEFAULT_LOW = -9
DEFAULT_HIGH = 9


class NoParametersFound(Exception):
    """Reçetede parametreleştirilebilir hiçbir sayısal literal yok."""


def _significant_tokens(recipe: str) -> list[tokenize.TokenInfo]:
    return [
        t
        for t in tokenize.generate_tokens(io.StringIO(recipe).readline)
        if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.ENDMARKER)
    ]


def _parametrizable_tokens(recipe: str) -> list[tokenize.TokenInfo]:
    """Parametreye çevrilebilecek NUMBER jetonlarını sırayla döndürür.

    Elenenler: üs konumundakiler (yapısal), sıfır (yapısal), tam sayı
    olmayanlar (Faz 1 kapsamı dışı).
    """
    tokens = _significant_tokens(recipe)
    selected: list[tokenize.TokenInfo] = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NUMBER:
            continue
        if i > 0 and tokens[i - 1].string == "**":
            continue
        try:
            value = int(tok.string)
        except ValueError:
            continue
        if value == 0:
            continue
        selected.append(tok)
    return selected


def _replace_token_spans(
    recipe: str, replacements: list[tuple[tokenize.TokenInfo, str]]
) -> str:
    """Jeton aralıklarını sondan başa doğru değiştirir (konumlar kaymasın diye)."""
    lines = recipe.splitlines(keepends=True) or [""]
    for tok, new_text in sorted(replacements, key=lambda r: r[0].start, reverse=True):
        line_no = tok.start[0] - 1
        start, end = tok.start[1], tok.end[1]
        line = lines[line_no]
        lines[line_no] = line[:start] + new_text + line[end:]
    return "".join(lines)


def _parametrize_text(text: str, value_to_param: dict[int, str]) -> str:
    """Metindeki sayıları yer tutucuya çevirir.

    Uzun değerden kısaya gidilir ki `12` varken `1` önce eşleşmesin.
    Lookbehind üs (`^2`, `**2`, `^{2}`) ve kelime içi rakamları korur —
    sınıfa hem `^` hem `*` dahildir, ikisi de üs gösterimlerinde önceki
    karakter olabilir; `^{` ayrıca dışlanır, yalın `{` ise dışlanmaz ki
    `\\frac{3}{x}` gibi paydalar parametreleşmeye devam etsin. Lookahead
    yalnız bir sonraki karakterin rakam ya da nokta olmasını engeller;
    bir değişken harfinin (`3x` içindeki
    `x` gibi) hemen ardından gelmesine izin verir, aksi halde
    katsayılar hiç eşleşmezdi.
    """
    for value in sorted(value_to_param, key=lambda v: -len(str(v))):
        pattern = rf"(?<![\w.*^])(?<!\^\{{){re.escape(str(value))}(?![\d.])"
        text = re.sub(pattern, "{" + value_to_param[value] + "}", text)
    return text


def extract_template(source: SourceQuestion, template_id: str) -> Template:
    if not source.recipe:
        raise ValueError(f"{source.id}: reçetesi olmayan kaynaktan şablon çıkarılamaz")

    tokens = _parametrizable_tokens(source.recipe)
    if not tokens:
        raise NoParametersFound(f"{source.id}: parametreleştirilecek sayısal literal yok")

    value_to_param: dict[int, str] = {}
    replacements: list[tuple[tokenize.TokenInfo, str]] = []
    for tok in tokens:
        value = int(tok.string)
        if value not in value_to_param:
            value_to_param[value] = f"p{len(value_to_param)}"
        replacements.append((tok, "{" + value_to_param[value] + "}"))

    skeleton_recipe = _replace_token_spans(source.recipe, replacements)
    skeleton_text = _parametrize_text(source.text, value_to_param)

    seed_bindings = {name: value for value, name in value_to_param.items()}
    seed_answer = parse_with_timeout(source.recipe)

    return Template(
        id=template_id,
        source_id=source.id,
        skeleton=skeleton_text,
        recipe=skeleton_recipe,
        parameters=tuple(
            Parameter(name=name, low=DEFAULT_LOW, high=DEFAULT_HIGH, exclude=(0,))
            for name in value_to_param.values()
        ),
        constraints=(),
        seed_bindings=seed_bindings,
        seed_answer_ops=int(seed_answer.count_ops()),
        objective=source.objective,
        status="trial",
    )
