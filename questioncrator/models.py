"""Sistemin tek gerçeklik kaynağı olan değişmez veri sınıfları.

Hiçbiri konuya özel alan içermez: bir "soru" burada metin + reçetedir,
o kadar.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Parameter:
    """Bir şablon parametresinin örnekleme alanı."""

    name: str
    low: int
    high: int
    exclude: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class SourceQuestion:
    """Havuza yüklenmiş, henüz şablona çevrilmemiş bir soru."""

    id: str
    text: str
    recipe: str | None = None
    objective: str | None = None
    needs_review: bool = False
    answer_text: str | None = None
    origin: str = "markdown"
    review_note: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class Template:
    """Bir kaynak sorusundan otomatik çıkarılmış parametrik iskelet."""

    id: str
    source_id: str
    skeleton: str
    recipe: str
    parameters: tuple[Parameter, ...]
    constraints: tuple[str, ...] = ()
    seed_bindings: dict[str, int] = field(default_factory=dict)
    seed_answer_ops: int = 0
    objective: str | None = None
    status: str = "trial"  # trial | active | disabled
    difficulty_estimate: float = 5.0


@dataclass(frozen=True)
class GeneratedQuestion:
    """Şablon + bağlamadan üretilmiş, doğrulamadan geçmiş bir soru."""

    id: str
    template_id: str
    bindings: dict[str, int]
    text: str
    answer_latex: str
    answer_key: str
    created_at: str
    choices: tuple[str, ...] = ()
    correct_index: int | None = None
    difficulty_estimate: float = 5.0
    student_id: str | None = None
    created_by: str | None = None
    archived: bool = False
    similar_given: bool = False


@dataclass(frozen=True)
class Review:
    """Hocanın bir kart için verdiği karar + çift puan."""

    question_id: str
    approved: bool
    difficulty: int  # 1-10
    quality: int  # 1-10 (kurgu)
    created_at: str
    reviewer_id: str | None = None


@dataclass(frozen=True)
class Student:
    """Hocanın rumuzla eklediği öğrenci. Not/sonuç tutulmaz (gizlilik kararı)."""

    id: str
    alias: str
    weak_objectives: tuple[str, ...] = ()
    level: int | None = None
    created_at: str = ""
    archived: bool = False


@dataclass(frozen=True)
class Exam:
    """Onaylı sorulardan oluşturulmuş sınav ya da öğrenciye özel çalışma kağıdı."""

    id: str
    title: str
    kind: str = "exam"  # exam | worksheet
    question_ids: tuple[str, ...] = ()
    settings: dict[str, object] = field(default_factory=dict)
    student_id: str | None = None
    created_by: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class FewShotExample:
    """LLM istemine eklenecek örnek: hocanın yüksek kurgu puanı verdiği onaylı soru."""

    question_text: str
    answer_latex: str
    quality: int
    objective: str | None = None
