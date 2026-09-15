"""Çalışma alanı veritabanı: şema göçleri ve kaydet/yükle fonksiyonları.

Her çalışma alanı (dershane) kendi SQLite dosyasındadır; bu modül kiracı
kavramını bilmez. Karmaşık alanlar JSON metin sütunlarında saklanır.
Şema `PRAGMA user_version` ile sürümlenir; `MIGRATIONS` yalnız sona
eklenerek büyür, var olan bir göç asla değiştirilmez.

İşlem kuralı: her yazma fonksiyonu kendi işlemini açar ve commit eder;
hata olursa geri alıp istisnayı yeniden yükseltir. Bu yüzden yazma
fonksiyonları dış bir işlemin içinde çağrılmamalıdır. `migrate` de
başlamadan önce bekleyen işlemi commit eder.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from questioncrator.models import (
    Exam,
    GeneratedQuestion,
    Parameter,
    Review,
    SourceQuestion,
    Student,
    Template,
)

_V1 = """
CREATE TABLE IF NOT EXISTS source_questions (
    id           TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    recipe       TEXT,
    objective    TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS templates (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    skeleton        TEXT NOT NULL,
    recipe          TEXT NOT NULL,
    parameters      TEXT NOT NULL,
    constraints     TEXT NOT NULL,
    seed_bindings   TEXT NOT NULL,
    seed_answer_ops INTEGER NOT NULL,
    objective       TEXT,
    status          TEXT NOT NULL DEFAULT 'trial'
                    CHECK (status IN ('trial', 'active', 'disabled'))
);

CREATE TABLE IF NOT EXISTS generated_questions (
    id           TEXT PRIMARY KEY,
    template_id  TEXT NOT NULL REFERENCES templates(id),
    bindings     TEXT NOT NULL,
    text         TEXT NOT NULL,
    answer_latex TEXT NOT NULL,
    answer_key   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    question_id TEXT PRIMARY KEY REFERENCES generated_questions(id),
    approved    INTEGER NOT NULL CHECK (approved IN (0, 1)),
    difficulty  INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 10),
    quality     INTEGER NOT NULL CHECK (quality BETWEEN 1 AND 10),
    created_at  TEXT NOT NULL
);
"""

_V2 = """
CREATE TABLE students (
    id              TEXT PRIMARY KEY,
    alias           TEXT NOT NULL,
    weak_objectives TEXT NOT NULL DEFAULT '[]',
    level           INTEGER CHECK (level IS NULL OR level BETWEEN 1 AND 10),
    created_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
);

ALTER TABLE source_questions ADD COLUMN answer_text TEXT;
ALTER TABLE source_questions ADD COLUMN origin TEXT NOT NULL DEFAULT 'markdown';
ALTER TABLE source_questions ADD COLUMN review_note TEXT;
ALTER TABLE source_questions ADD COLUMN created_at TEXT NOT NULL DEFAULT '';

ALTER TABLE templates ADD COLUMN difficulty_estimate REAL NOT NULL DEFAULT 5.0;

ALTER TABLE generated_questions ADD COLUMN choices TEXT NOT NULL DEFAULT '[]';
ALTER TABLE generated_questions ADD COLUMN correct_index INTEGER;
ALTER TABLE generated_questions ADD COLUMN difficulty_estimate REAL NOT NULL DEFAULT 5.0;
ALTER TABLE generated_questions ADD COLUMN student_id TEXT REFERENCES students(id);
ALTER TABLE generated_questions ADD COLUMN created_by TEXT;
ALTER TABLE generated_questions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0
    CHECK (archived IN (0, 1));
ALTER TABLE generated_questions ADD COLUMN similar_given INTEGER NOT NULL DEFAULT 0
    CHECK (similar_given IN (0, 1));

ALTER TABLE reviews ADD COLUMN reviewer_id TEXT;

CREATE TABLE student_questions (
    student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES generated_questions(id) ON DELETE CASCADE,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (student_id, question_id)
);

CREATE TABLE exams (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('exam', 'worksheet')),
    student_id   TEXT REFERENCES students(id) ON DELETE SET NULL,
    question_ids TEXT NOT NULL,
    settings     TEXT NOT NULL,
    created_by   TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX idx_generated_template ON generated_questions(template_id);
CREATE INDEX idx_generated_student ON generated_questions(student_id);
CREATE INDEX idx_templates_source ON templates(source_id);
"""

MIGRATIONS: tuple[str, ...] = (_V1, _V2)
SCHEMA_VERSION = len(MIGRATIONS)


def _statements(script: str) -> Iterator[str]:
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer.strip()
            buffer = ""
    if buffer.strip():
        raise ValueError("göç betiğinde tamamlanmamış SQL ifadesi")


def migrate(conn: sqlite3.Connection) -> None:
    """Eksik göçleri sırayla, her birini ayrı bir `BEGIN IMMEDIATE` işleminde uygular.

    Sürüm, yazma kilidi alındıktan sonra yeniden okunur: aynı dosyaya
    eşzamanlı bağlanan süreçlerden yalnız biri bir adımı uygular, diğerleri
    kilidi bekler (busy timeout) ve adımı atlar.
    """
    if conn.in_transaction:
        conn.commit()
    for version in range(1, SCHEMA_VERSION + 1):
        if conn.execute("PRAGMA user_version").fetchone()[0] >= version:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] < version:
                for statement in _statements(MIGRATIONS[version - 1]):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            conn.rollback()
            raise
        conn.commit()


def _enable_wal(conn: sqlite3.Connection, timeout: float) -> None:
    """WAL kipine geçer; bu PRAGMA meşgul işleyiciyi çağırmadığından elle yeniden dener."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def connect(
    path: str | Path = "questioncrator.db", *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Bağlantı açar, göçleri uygular.

    `check_same_thread=False` bağlantının başka bir iş parçacığında
    kullanılacağı durumlar içindir (ör. web çerçevesinin iş havuzu).
    """
    timeout = 5.0
    conn = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=timeout)
    conn.row_factory = sqlite3.Row
    # PRAGMA'lar işlem dışında verilmelidir (journal_mode işlem içinde
    # değiştirilemez); bu yüzden göçten önce.
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        _enable_wal(conn, timeout)
    migrate(conn)
    return conn


@contextmanager
def _write(conn: sqlite3.Connection) -> Iterator[None]:
    """Başarıda commit; herhangi bir istisnada geri al ve yeniden yükselt.

    Başarısız bir ifadenin açtığı örtük işlem açık kalırsa yazma kilidi
    tutulur ve aynı dosyaya bağlanan diğer bağlantılar kilitlenir.
    """
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def _upsert(conn: sqlite3.Connection, table: str, key: str, row: dict[str, object]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    updates = ", ".join(f"{c} = excluded.{c}" for c in row if c != key)
    with _write(conn):
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT({key}) DO UPDATE SET {updates}",
            tuple(row.values()),
        )


# --- kaynak sorular ---------------------------------------------------------


def save_source(conn: sqlite3.Connection, source: SourceQuestion) -> None:
    _upsert(conn, "source_questions", "id", {
        "id": source.id,
        "text": source.text,
        "recipe": source.recipe,
        "objective": source.objective,
        "needs_review": int(source.needs_review),
        "answer_text": source.answer_text,
        "origin": source.origin,
        "review_note": source.review_note,
        "created_at": source.created_at,
    })


def _source(r: sqlite3.Row) -> SourceQuestion:
    return SourceQuestion(
        id=r["id"],
        text=r["text"],
        recipe=r["recipe"],
        objective=r["objective"],
        needs_review=bool(r["needs_review"]),
        answer_text=r["answer_text"],
        origin=r["origin"],
        review_note=r["review_note"],
        created_at=r["created_at"],
    )


def load_sources(conn: sqlite3.Connection) -> list[SourceQuestion]:
    rows = conn.execute("SELECT * FROM source_questions ORDER BY created_at, rowid").fetchall()
    return [_source(r) for r in rows]


def get_source(conn: sqlite3.Connection, source_id: str) -> SourceQuestion | None:
    r = conn.execute("SELECT * FROM source_questions WHERE id = ?", (source_id,)).fetchone()
    return _source(r) if r else None


def delete_source(conn: sqlite3.Connection, source_id: str) -> None:
    """Kaynağı siler; şablonları üretilmiş soruları korumak için silinmez, kapatılır."""
    with _write(conn):
        conn.execute(
            "UPDATE templates SET status = 'disabled' WHERE source_id = ?", (source_id,)
        )
        conn.execute("DELETE FROM source_questions WHERE id = ?", (source_id,))


# --- şablonlar --------------------------------------------------------------


def save_template(conn: sqlite3.Connection, template: Template) -> None:
    _upsert(conn, "templates", "id", {
        "id": template.id,
        "source_id": template.source_id,
        "skeleton": template.skeleton,
        "recipe": template.recipe,
        "parameters": json.dumps([asdict(p) for p in template.parameters]),
        "constraints": json.dumps(list(template.constraints)),
        "seed_bindings": json.dumps(template.seed_bindings),
        "seed_answer_ops": template.seed_answer_ops,
        "objective": template.objective,
        "status": template.status,
        "difficulty_estimate": template.difficulty_estimate,
    })


def _template(r: sqlite3.Row) -> Template:
    return Template(
        id=r["id"],
        source_id=r["source_id"],
        skeleton=r["skeleton"],
        recipe=r["recipe"],
        parameters=tuple(
            Parameter(name=p["name"], low=p["low"], high=p["high"], exclude=tuple(p["exclude"]))
            for p in json.loads(r["parameters"])
        ),
        constraints=tuple(json.loads(r["constraints"])),
        seed_bindings=json.loads(r["seed_bindings"]),
        seed_answer_ops=r["seed_answer_ops"],
        objective=r["objective"],
        status=r["status"],
        difficulty_estimate=r["difficulty_estimate"],
    )


def load_templates(conn: sqlite3.Connection) -> list[Template]:
    return [_template(r) for r in conn.execute("SELECT * FROM templates ORDER BY rowid")]


def get_template(conn: sqlite3.Connection, template_id: str) -> Template | None:
    r = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    return _template(r) if r else None


def load_templates_for_source(conn: sqlite3.Connection, source_id: str) -> list[Template]:
    rows = conn.execute("SELECT * FROM templates WHERE source_id = ? ORDER BY rowid", (source_id,))
    return [_template(r) for r in rows]


def set_template_status(conn: sqlite3.Connection, template_id: str, status: str) -> None:
    with _write(conn):
        conn.execute("UPDATE templates SET status = ? WHERE id = ?", (status, template_id))


# --- üretilen sorular -------------------------------------------------------


def save_question(conn: sqlite3.Connection, question: GeneratedQuestion) -> None:
    _upsert(conn, "generated_questions", "id", {
        "id": question.id,
        "template_id": question.template_id,
        "bindings": json.dumps(question.bindings),
        "text": question.text,
        "answer_latex": question.answer_latex,
        "answer_key": question.answer_key,
        "created_at": question.created_at,
        "choices": json.dumps(list(question.choices)),
        "correct_index": question.correct_index,
        "difficulty_estimate": question.difficulty_estimate,
        "student_id": question.student_id,
        "created_by": question.created_by,
        "archived": int(question.archived),
        "similar_given": int(question.similar_given),
    })


def _question(r: sqlite3.Row) -> GeneratedQuestion:
    return GeneratedQuestion(
        id=r["id"],
        template_id=r["template_id"],
        bindings=json.loads(r["bindings"]),
        text=r["text"],
        answer_latex=r["answer_latex"],
        answer_key=r["answer_key"],
        created_at=r["created_at"],
        choices=tuple(json.loads(r["choices"])),
        correct_index=r["correct_index"],
        difficulty_estimate=r["difficulty_estimate"],
        student_id=r["student_id"],
        created_by=r["created_by"],
        archived=bool(r["archived"]),
        similar_given=bool(r["similar_given"]),
    )


def load_questions(
    conn: sqlite3.Connection, *, include_archived: bool = True
) -> list[GeneratedQuestion]:
    where = "" if include_archived else "WHERE archived = 0"
    rows = conn.execute(f"SELECT * FROM generated_questions {where} ORDER BY created_at, rowid")
    return [_question(r) for r in rows]


def get_question(conn: sqlite3.Connection, question_id: str) -> GeneratedQuestion | None:
    r = conn.execute("SELECT * FROM generated_questions WHERE id = ?", (question_id,)).fetchone()
    return _question(r) if r else None


def set_question_archived(conn: sqlite3.Connection, question_id: str, archived: bool) -> None:
    with _write(conn):
        conn.execute(
            "UPDATE generated_questions SET archived = ? WHERE id = ?",
            (int(archived), question_id),
        )


def load_answer_keys(conn: sqlite3.Connection) -> set[str]:
    """Şimdiye kadar üretilmiş tüm cevap anahtarları — kopya filtresinin girdisi."""
    return {r["answer_key"] for r in conn.execute("SELECT answer_key FROM generated_questions")}


# --- değerlendirmeler -------------------------------------------------------


def save_review(conn: sqlite3.Connection, review: Review) -> None:
    _upsert(conn, "reviews", "question_id", {
        "question_id": review.question_id,
        "approved": int(review.approved),
        "difficulty": review.difficulty,
        "quality": review.quality,
        "created_at": review.created_at,
        "reviewer_id": review.reviewer_id,
    })


def _review(r: sqlite3.Row) -> Review:
    return Review(
        question_id=r["question_id"],
        approved=bool(r["approved"]),
        difficulty=r["difficulty"],
        quality=r["quality"],
        created_at=r["created_at"],
        reviewer_id=r["reviewer_id"],
    )


def load_reviews(conn: sqlite3.Connection) -> list[Review]:
    rows = conn.execute("SELECT * FROM reviews ORDER BY created_at, rowid")
    return [_review(r) for r in rows]


def get_review(conn: sqlite3.Connection, question_id: str) -> Review | None:
    r = conn.execute("SELECT * FROM reviews WHERE question_id = ?", (question_id,)).fetchone()
    return _review(r) if r else None


def delete_review(conn: sqlite3.Connection, question_id: str) -> None:
    with _write(conn):
        conn.execute("DELETE FROM reviews WHERE question_id = ?", (question_id,))


# --- öğrenciler -------------------------------------------------------------


def save_student(conn: sqlite3.Connection, student: Student) -> None:
    _upsert(conn, "students", "id", {
        "id": student.id,
        "alias": student.alias,
        "weak_objectives": json.dumps(list(student.weak_objectives)),
        "level": student.level,
        "created_at": student.created_at,
        "archived": int(student.archived),
    })


def _student(r: sqlite3.Row) -> Student:
    return Student(
        id=r["id"],
        alias=r["alias"],
        weak_objectives=tuple(json.loads(r["weak_objectives"])),
        level=r["level"],
        created_at=r["created_at"],
        archived=bool(r["archived"]),
    )


def load_students(conn: sqlite3.Connection, *, include_archived: bool = False) -> list[Student]:
    where = "" if include_archived else "WHERE archived = 0"
    rows = conn.execute(f"SELECT * FROM students {where} ORDER BY alias, rowid")
    return [_student(r) for r in rows]


def get_student(conn: sqlite3.Connection, student_id: str) -> Student | None:
    r = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return _student(r) if r else None


def assign_questions(
    conn: sqlite3.Connection, student_id: str, question_ids: Iterable[str], assigned_at: str
) -> None:
    with _write(conn):
        conn.executemany(
            "INSERT OR IGNORE INTO student_questions (student_id, question_id, assigned_at) "
            "VALUES (?, ?, ?)",
            [(student_id, qid, assigned_at) for qid in question_ids],
        )


def load_student_question_ids(conn: sqlite3.Connection, student_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT question_id FROM student_questions WHERE student_id = ?", (student_id,)
    )
    return {r["question_id"] for r in rows}


def load_student_template_ids(conn: sqlite3.Connection, student_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT g.template_id FROM student_questions sq "
        "JOIN generated_questions g ON g.id = sq.question_id WHERE sq.student_id = ?",
        (student_id,),
    )
    return {r["template_id"] for r in rows}


# --- sınavlar ---------------------------------------------------------------


def save_exam(conn: sqlite3.Connection, exam: Exam) -> None:
    _upsert(conn, "exams", "id", {
        "id": exam.id,
        "title": exam.title,
        "kind": exam.kind,
        "student_id": exam.student_id,
        "question_ids": json.dumps(list(exam.question_ids)),
        "settings": json.dumps(exam.settings),
        "created_by": exam.created_by,
        "created_at": exam.created_at,
    })


def _exam(r: sqlite3.Row) -> Exam:
    return Exam(
        id=r["id"],
        title=r["title"],
        kind=r["kind"],
        question_ids=tuple(json.loads(r["question_ids"])),
        settings=json.loads(r["settings"]),
        student_id=r["student_id"],
        created_by=r["created_by"],
        created_at=r["created_at"],
    )


def load_exams(conn: sqlite3.Connection, *, student_id: str | None = None) -> list[Exam]:
    if student_id is None:
        rows = conn.execute("SELECT * FROM exams ORDER BY created_at DESC, rowid DESC")
    else:
        rows = conn.execute(
            "SELECT * FROM exams WHERE student_id = ? ORDER BY created_at DESC, rowid DESC",
            (student_id,),
        )
    return [_exam(r) for r in rows]


def get_exam(conn: sqlite3.Connection, exam_id: str) -> Exam | None:
    r = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    return _exam(r) if r else None


def delete_exam(conn: sqlite3.Connection, exam_id: str) -> None:
    with _write(conn):
        conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
