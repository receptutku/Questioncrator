"""SQLite şeması ve kaydet/yükle fonksiyonları.

Veri hocanın makinesinde, tek bir dosyada durur. Karmaşık alanlar
(parametreler, bağlamalar, kısıtlar) JSON metin sütunlarında saklanır —
Faz 1 için sorgu ihtiyacı yok, sadeliği tercih ediyoruz.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from questioncrator.models import (
    GeneratedQuestion,
    Parameter,
    Review,
    SourceQuestion,
    Template,
)

SCHEMA = """
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


def connect(
    path: str | Path = "questioncrator.db", *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Bağlantı açar ve şemayı garantiler.

    `check_same_thread=False` yalnız Streamlit için gereklidir: Streamlit
    betiği her yeniden çiziminde farklı bir iş parçacığında çalıştırabilir.
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # PRAGMA'yı executescript içinde vermek işe yaramaz (işlem içinde yok sayılır).
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --- kaynak sorular ---------------------------------------------------------


def save_source(conn: sqlite3.Connection, source: SourceQuestion) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO source_questions VALUES (?, ?, ?, ?, ?)",
        (source.id, source.text, source.recipe, source.objective, int(source.needs_review)),
    )
    conn.commit()


def load_sources(conn: sqlite3.Connection) -> list[SourceQuestion]:
    rows = conn.execute("SELECT * FROM source_questions ORDER BY id").fetchall()
    return [
        SourceQuestion(
            id=r["id"],
            text=r["text"],
            recipe=r["recipe"],
            objective=r["objective"],
            needs_review=bool(r["needs_review"]),
        )
        for r in rows
    ]


# --- şablonlar --------------------------------------------------------------


def save_template(conn: sqlite3.Connection, template: Template) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO templates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            template.id,
            template.source_id,
            template.skeleton,
            template.recipe,
            json.dumps([asdict(p) for p in template.parameters]),
            json.dumps(list(template.constraints)),
            json.dumps(template.seed_bindings),
            template.seed_answer_ops,
            template.objective,
            template.status,
        ),
    )
    conn.commit()


def load_templates(conn: sqlite3.Connection) -> list[Template]:
    rows = conn.execute("SELECT * FROM templates ORDER BY id").fetchall()
    return [
        Template(
            id=r["id"],
            source_id=r["source_id"],
            skeleton=r["skeleton"],
            recipe=r["recipe"],
            parameters=tuple(
                Parameter(
                    name=p["name"],
                    low=p["low"],
                    high=p["high"],
                    exclude=tuple(p["exclude"]),
                )
                for p in json.loads(r["parameters"])
            ),
            constraints=tuple(json.loads(r["constraints"])),
            seed_bindings=json.loads(r["seed_bindings"]),
            seed_answer_ops=r["seed_answer_ops"],
            objective=r["objective"],
            status=r["status"],
        )
        for r in rows
    ]


def set_template_status(conn: sqlite3.Connection, template_id: str, status: str) -> None:
    conn.execute("UPDATE templates SET status = ? WHERE id = ?", (status, template_id))
    conn.commit()


# --- üretilen sorular -------------------------------------------------------


def save_question(conn: sqlite3.Connection, question: GeneratedQuestion) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO generated_questions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            question.id,
            question.template_id,
            json.dumps(question.bindings),
            question.text,
            question.answer_latex,
            question.answer_key,
            question.created_at,
        ),
    )
    conn.commit()


def load_questions(conn: sqlite3.Connection) -> list[GeneratedQuestion]:
    rows = conn.execute("SELECT * FROM generated_questions ORDER BY created_at, id").fetchall()
    return [
        GeneratedQuestion(
            id=r["id"],
            template_id=r["template_id"],
            bindings=json.loads(r["bindings"]),
            text=r["text"],
            answer_latex=r["answer_latex"],
            answer_key=r["answer_key"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def load_answer_keys(conn: sqlite3.Connection) -> set[str]:
    """Şimdiye kadar üretilmiş tüm cevap anahtarları — kopya filtresinin girdisi."""
    rows = conn.execute("SELECT answer_key FROM generated_questions").fetchall()
    return {r["answer_key"] for r in rows}


# --- değerlendirmeler -------------------------------------------------------


def save_review(conn: sqlite3.Connection, review: Review) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?, ?)",
        (
            review.question_id,
            int(review.approved),
            review.difficulty,
            review.quality,
            review.created_at,
        ),
    )
    conn.commit()


def load_reviews(conn: sqlite3.Connection) -> list[Review]:
    rows = conn.execute("SELECT * FROM reviews ORDER BY created_at, question_id").fetchall()
    return [
        Review(
            question_id=r["question_id"],
            approved=bool(r["approved"]),
            difficulty=r["difficulty"],
            quality=r["quality"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
