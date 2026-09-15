"""Kaynak sorudan otomatik parametrik şablon çıkarır (A3).

Deterministiktir ve konudan bağımsızdır: reçetenin ne anlama geldiğini
bilmez, yalnız içindeki sayısal literalleri parametreye çevirir. Bu yüzden
kaynak sorunun hangi konudan geldiğinin bir önemi yoktur; bugün havuzda
olmayan bir konu da aynı yoldan geçer.

DEĞİŞMEZ: öğrencinin gördüğü metin sabit kalırken cevabın değişmesi (ya
da tersi) imkânsızdır. Bir değerin metindeki ve reçetedeki geçişleri
sınıflandırılır; değer yalnız sayımlar birebir eşleşiyorsa parametreleşir.
Karar tek yerdedir: `_parametrizable_values`.
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

# Metin geçiş sınıfları.
SAFE = "S"  # Ayrı, güvenli bir sayı: parametreleşebilir.
EXPONENT = "E"  # Basit üs (`^v`, `^{v}`, `**v`, üst simge): sabit kalır.
UNSAFE = "U"  # Diğer güvensiz bağlamlar: değeri tamamen dondurur.

_DIGIT_RUN = re.compile(r"[0-9]+")
_SIGNED_DIGIT_RUN = re.compile(r"-?\s*[0-9]+")
_BRACED_DIGITS = re.compile(r"\s*([0-9]+)\s*")
_SCRIPT_MARKER = re.compile(r"\^|\*\*|_")
_ROOT_INDEX = re.compile(r"\\sqrt\s*\[")
_SUPERSCRIPT_RUN = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_SUBSCRIPT_RUN = re.compile("[₀₁₂₃₄₅₆₇₈₉]+")
_SCRIPT_TO_ASCII = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
_CLOSERS = {"{": "}", "[": "]"}

Span = tuple[int, int]
# (jeton, değer, `**` sonrası mı)
RecipeLiteral = tuple[tokenize.TokenInfo, int, bool]


class NoParametersFound(Exception):
    """Reçetede parametreleştirilebilir hiçbir sayısal literal yok."""


def _significant_tokens(recipe: str) -> list[tokenize.TokenInfo]:
    return [
        t
        for t in tokenize.generate_tokens(io.StringIO(recipe).readline)
        if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.ENDMARKER)
    ]


def _recipe_literals(recipe: str) -> list[RecipeLiteral]:
    """Reçetedeki sıfır olmayan tam sayı literalleri, sırayla.

    Her biri R_E (hemen `**` sonrası, yapısal üs) ya da R_S (diğer) olarak
    işaretlenir. Tam sayı olmayanlar Faz 1 kapsamı dışıdır, sıfır yapısaldır.
    """
    tokens = _significant_tokens(recipe)
    literals: list[RecipeLiteral] = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NUMBER:
            continue
        try:
            value = int(tok.string)
        except ValueError:
            continue
        if value == 0:
            continue
        literals.append((tok, value, i > 0 and tokens[i - 1].string == "**"))
    return literals


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


def _group_end(text: str, open_index: int) -> int:
    """`{`/`[` ile açılan grubun kapanışından sonraki konum (iç içe sayılır)."""
    opener = text[open_index]
    closer = _CLOSERS[opener]
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _is_power_stars(text: str, index: int) -> bool:
    """`index`teki `**` üs mü; değilse Markdown kalın yazı sayılır.

    Üs: önünde bir işlenen (`x**2`, `)**2`) ya da iki yanında boşluk
    (`2 ** 3`) vardır. `**3**` gibi sarmalar kalın yazıdır.
    """
    before = text[index - 1:index]
    after = text[index + 2:index + 3]
    if before.isalnum() or before in (")", "}"):
        return True
    return before.isspace() and after.isspace()


def _script_regions(text: str) -> tuple[set[Span], list[Span]]:
    """Metindeki (basit üs rakam dizileri, güvensiz bölgeler).

    `^`/`**` sonrası yalnız rakamdan oluşan sayı ya da `{v}` grubu basit
    üstür. `^{2x}`, `^-2`, `^{-2}`, `_` sonrası her şey, kalın yazı `**`
    sonrası ve `\\sqrt[…]` içi güvensiz bölgedir.
    """
    exponents: set[Span] = set()
    unsafe: list[Span] = []
    for marker in _SCRIPT_MARKER.finditer(text):
        start = marker.end()
        while text[start:start + 1] in (" ", "\t") and start < len(text):
            start += 1
        is_power = marker.group() == "^" or (
            marker.group() == "**" and _is_power_stars(text, marker.start())
        )
        if text.startswith("{", start):
            end = _group_end(text, start)
            inner = _BRACED_DIGITS.fullmatch(text, start + 1, end - 1)
            if is_power and inner and text[end - 1:end] == "}":
                exponents.add(inner.span(1))
            else:
                unsafe.append((start, end))
            continue
        number = _SIGNED_DIGIT_RUN.match(text, start)
        if number is None:
            continue
        if is_power and text[start].isdigit():
            exponents.add(number.span())
        else:
            unsafe.append(number.span())
    for root in _ROOT_INDEX.finditer(text):
        unsafe.append((root.end() - 1, _group_end(text, root.end() - 1)))
    return exponents, unsafe


def _classify(text: str, span: Span, exponents: set[Span], unsafe: list[Span]) -> str:
    """Değere birebir eşit bir rakam dizisinin sınıfı: S, E ya da U."""
    start, end = span
    if any(u_start < end and start < u_end for u_start, u_end in unsafe):
        return UNSAFE
    before = text[start - 1:start]
    # Tanımlayıcı içi (`x2`, `\frac12`): sayı ayrı bir değer değildir.
    if before.isalpha() or before == "_":
        return UNSAFE
    # Ondalık ayırıcı: `2,5` ve `2.5` iki ayrı tam sayı değildir.
    if before in (",", ".") and text[start - 2:start - 1].isdigit():
        return UNSAFE
    after = text[end:end + 2]
    if after[:1] in (",", ".") and after[1:].isdigit():
        return UNSAFE
    return EXPONENT if span in exponents else SAFE


def _text_occurrences(text: str, values: set[int]) -> dict[int, dict[str, list[Span]]]:
    """Her değerin metindeki geçişleri, sınıflarına göre."""
    exponents, unsafe = _script_regions(text)
    occurrences: dict[int, dict[str, list[Span]]] = {
        value: {SAFE: [], EXPONENT: [], UNSAFE: []} for value in values
    }
    for run in _DIGIT_RUN.finditer(text):
        for value in values:
            if run.group() == str(value):
                kind = _classify(text, run.span(), exponents, unsafe)
                occurrences[value][kind].append(run.span())
            elif str(value) in run.group():
                # Başka bir rakam dizisinin içi (`12` içindeki `2`).
                occurrences[value][UNSAFE].append(run.span())
    for pattern, whole_kind in ((_SUPERSCRIPT_RUN, EXPONENT), (_SUBSCRIPT_RUN, UNSAFE)):
        for run in pattern.finditer(text):
            digits = run.group().translate(_SCRIPT_TO_ASCII)
            for value in values:
                if digits == str(value):
                    occurrences[value][whole_kind].append(run.span())
                elif str(value) in digits:
                    occurrences[value][UNSAFE].append(run.span())
    return occurrences


def _parametrizable_values(
    occurrences: dict[int, dict[str, list[Span]]], literals: list[RecipeLiteral]
) -> set[int]:
    """DEĞİŞMEZİN tek karar noktası: hangi değerler parametreleşir.

    Bir değer v yalnız şunların HEPSİ sağlanırsa parametreleşir:

    - U boş: metinde karma üs, indis, kök derecesi, ondalık, harf ya da
      rakam komşuluğu gibi hiçbir güvensiz geçiş yok;
    - |E| == |R_E|: metinde sabit kalan basit üsler, reçetede sabit kalan
      `**` üsleriyle sayıca eşleşiyor;
    - |S| == |R_S| >= 1: metinde değişecek her geçişin reçetede bir
      karşılığı var ve reçetede metinde görünmeyen bir geçiş yok (ör.
      `diff(x**2 + 2, x, 2)`deki türev derecesi ya da şıktaki `2`).

    Aksi halde v metinde de reçetede de sabit kalır. Parametreleşen
    değerde yalnız S ve R_S geçişleri değişir; E ve R_E sabit kalır.
    """
    allowed: set[int] = set()
    for value, found in occurrences.items():
        recipe_exponents = sum(1 for _, v, is_exp in literals if v == value and is_exp)
        recipe_safe = sum(1 for _, v, is_exp in literals if v == value and not is_exp)
        if found[UNSAFE] or len(found[EXPONENT]) != recipe_exponents:
            continue
        if recipe_safe >= 1 and len(found[SAFE]) == recipe_safe:
            allowed.add(value)
    return allowed


def _parametrize_text(text: str, span_to_param: dict[Span, str]) -> str:
    """Verilen S geçişlerini sondan başa doğru yer tutucuya çevirir."""
    for (start, end), name in sorted(span_to_param.items(), reverse=True):
        text = text[:start] + "{" + name + "}" + text[end:]
    return text


def extract_template(source: SourceQuestion, template_id: str) -> Template:
    if not source.recipe:
        raise ValueError(f"{source.id}: reçetesi olmayan kaynaktan şablon çıkarılamaz")

    literals = _recipe_literals(source.recipe)
    occurrences = _text_occurrences(source.text, {value for _, value, _ in literals})
    allowed = _parametrizable_values(occurrences, literals)
    tokens = [(tok, value) for tok, value, is_exp in literals if value in allowed and not is_exp]
    if not tokens:
        raise NoParametersFound(f"{source.id}: parametreleştirilecek sayısal literal yok")

    value_to_param: dict[int, str] = {}
    replacements: list[tuple[tokenize.TokenInfo, str]] = []
    for tok, value in tokens:
        if value not in value_to_param:
            value_to_param[value] = f"p{len(value_to_param)}"
        replacements.append((tok, "{" + value_to_param[value] + "}"))

    skeleton_recipe = _replace_token_spans(source.recipe, replacements)
    skeleton_text = _parametrize_text(
        source.text,
        {
            span: name
            for value, name in value_to_param.items()
            for span in occurrences[value][SAFE]
        },
    )

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
