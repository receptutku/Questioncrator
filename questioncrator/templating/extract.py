"""Kaynak sorudan otomatik parametrik şablon çıkarır (A3).

Deterministiktir ve konudan bağımsızdır: reçetenin ne anlama geldiğini
bilmez, yalnız içindeki sayısal literalleri parametreye çevirir. Bu yüzden
kaynak sorunun hangi konudan geldiğinin bir önemi yoktur; bugün havuzda
olmayan bir konu da aynı yoldan geçer.

DEĞİŞMEZ: bir literal değer metindeki ve reçetedeki TÜM geçişlerinde
birlikte parametreleşir ya da hiçbirinde parametreleşmez. Öğrencinin
gördüğü metin sabit kalırken cevabın değişmesi (ya da tersi) böylece
imkânsız olur. Kural tek yerdedir: `_parametrizable_values`.
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

_DIGIT_RUN = re.compile(r"[0-9]+")
_SIGNED_DIGIT_RUN = re.compile(r"-?\s*[0-9]+")
# Ardından gelen sayı ya da `{…}` grubu üs ya da indistir.
_SCRIPT_MARKER = re.compile(r"(?:\^|\*\*|_)\s*")
_ROOT_INDEX = re.compile(r"\\sqrt\s*\[")
_SCRIPT_DIGITS = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+")
_SCRIPT_TO_ASCII = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
_CLOSERS = {"{": "}", "[": "]"}


class NoParametersFound(Exception):
    """Reçetede parametreleştirilebilir hiçbir sayısal literal yok."""


def _significant_tokens(recipe: str) -> list[tokenize.TokenInfo]:
    return [
        t
        for t in tokenize.generate_tokens(io.StringIO(recipe).readline)
        if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.ENDMARKER)
    ]


def _parametrizable_tokens(recipe: str) -> list[tokenize.TokenInfo]:
    """Reçetede parametreye aday NUMBER jetonlarını sırayla döndürür.

    Elenenler: üs konumundakiler (yapısal), sıfır (yapısal), tam sayı
    olmayanlar (Faz 1 kapsamı dışı). Adaylar ayrıca metin tarafındaki
    değişmez süzgecinden geçer (`_parametrizable_values`).
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


def _unsafe_spans(text: str) -> list[tuple[int, int]]:
    """Metinde üs, indis ya da kök derecesi olan bölgeler.

    `^`, `**`, `_` sonrası sayı ya da `{…}` grubunun tamamı (`^{2x}` dahil)
    ve `\\sqrt[…]` içi.
    """
    spans: list[tuple[int, int]] = []
    for marker in _SCRIPT_MARKER.finditer(text):
        start = marker.end()
        if text.startswith("{", start):
            spans.append((start, _group_end(text, start)))
            continue
        number = _SIGNED_DIGIT_RUN.match(text, start)
        if number:
            spans.append((start, number.end()))
    for root in _ROOT_INDEX.finditer(text):
        spans.append((root.end() - 1, _group_end(text, root.end() - 1)))
    return spans


def _is_unsafe_occurrence(text: str, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    if any(span_start < end and start < span_end for span_start, span_end in spans):
        return True
    before = text[start - 1:start]
    # Tanımlayıcı içi (`x2`, `\frac12`): sayı ayrı bir değer değildir.
    if before.isalpha() or before == "_":
        return True
    # Ondalık ayırıcı: `2,5` ve `2.5` iki ayrı tam sayı değildir.
    if before in (",", ".") and text[start - 2:start - 1].isdigit():
        return True
    after = text[end:end + 2]
    return after[:1] in (",", ".") and after[1:].isdigit()


def _parametrizable_values(text: str, candidates: set[int]) -> set[int]:
    """DEĞİŞMEZİN tek uygulandığı yer: hangi değerler parametreleşebilir.

    Bir aday değer yalnız şu durumda parametreleşir: metinde en az bir
    kez ayrı bir sayı olarak geçer VE hiçbir geçişi güvensiz bağlamda
    değildir. Güvensiz bağlamlar: `^`/`**`/`_` sonrası, `^{…}`/`_{…}`
    içi, `\\sqrt[…]` içi, ondalık ayırıcı komşuluğu, harf komşuluğu, üst
    ya da alt simge rakamları ve başka bir rakam dizisinin içi (`12`
    içindeki `2`). Metinde hiç geçmeyen değer de parametreleşmez.
    """
    spans = _unsafe_spans(text)
    unsafe: set[int] = set()
    seen: set[int] = set()
    for run in _DIGIT_RUN.finditer(text):
        digits = run.group()
        for value in candidates:
            if str(value) in digits and digits != str(value):
                unsafe.add(value)
        value = int(digits)
        if value in candidates and digits == str(value):
            if _is_unsafe_occurrence(text, run.start(), run.end(), spans):
                unsafe.add(value)
            else:
                seen.add(value)
    for script in _SCRIPT_DIGITS.finditer(text):
        digits = script.group().translate(_SCRIPT_TO_ASCII)
        unsafe.update(value for value in candidates if str(value) in digits)
    return seen - unsafe


def _parametrize_text(text: str, value_to_param: dict[int, str]) -> str:
    """Metindeki ayrı sayı dizilerini yer tutucuya çevirir.

    Yalnız `_parametrizable_values` süzgecinden geçmiş değerler gelir;
    onların metindeki her geçişi güvenlidir, bu yüzden hepsi değişir.
    """
    by_digits = {str(value): name for value, name in value_to_param.items()}

    def replace(run: re.Match[str]) -> str:
        name = by_digits.get(run.group())
        return run.group() if name is None else "{" + name + "}"

    return _DIGIT_RUN.sub(replace, text)


def extract_template(source: SourceQuestion, template_id: str) -> Template:
    if not source.recipe:
        raise ValueError(f"{source.id}: reçetesi olmayan kaynaktan şablon çıkarılamaz")

    candidates = _parametrizable_tokens(source.recipe)
    allowed = _parametrizable_values(source.text, {int(tok.string) for tok in candidates})
    tokens = [tok for tok in candidates if int(tok.string) in allowed]
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
