from __future__ import annotations

import sqlite3

import pytest

from questioncrator import db
from questioncrator.models import (
    GeneratedQuestion,
    Parameter,
    Review,
    SourceQuestion,
    Template,
)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def ornek_sablon() -> Template:
    return Template(
        id="t1",
        source_id="s1",
        skeleton="f(x) = {p0}x^2 + {p1}x fonksiyonunun türevi nedir?",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(
            Parameter(name="p0", low=-9, high=9, exclude=(0,)),
            Parameter(name="p1", low=-9, high=9, exclude=(0,)),
        ),
        constraints=(),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=3,
        objective="turev.polinom",
        status="trial",
    )


def test_kaynak_soru_gidis_donus(conn: sqlite3.Connection):
    kaynak = SourceQuestion(
        id="s1",
        text="f(x) = 3x^2 + 5x fonksiyonunun türevi nedir?",
        recipe="diff(3*x**2 + 5*x, x)",
        objective="turev.polinom",
        needs_review=False,
    )
    db.save_source(conn, kaynak)
    assert db.load_sources(conn) == [kaynak]


def test_sablon_gidis_donus(conn: sqlite3.Connection):
    sablon = ornek_sablon()
    db.save_template(conn, sablon)
    yuklenen = db.load_templates(conn)
    assert yuklenen == [sablon]
    assert yuklenen[0].parameters[0].exclude == (0,)


def test_sablon_durumu_guncellenir(conn: sqlite3.Connection):
    db.save_template(conn, ornek_sablon())
    db.set_template_status(conn, "t1", "active")
    assert db.load_templates(conn)[0].status == "active"


def test_uretilen_soru_ve_cevap_anahtarlari(conn: sqlite3.Connection):
    db.save_template(conn, ornek_sablon())
    soru = GeneratedQuestion(
        id="q1",
        template_id="t1",
        bindings={"p0": 4, "p1": -2},
        text="f(x) = 4x^2 + -2x fonksiyonunun türevi nedir?",
        answer_latex="8 x - 2",
        answer_key="Add(Integer(-2), Mul(Integer(8), Symbol('x')))",
        created_at="2026-08-13T10:00:00+00:00",
    )
    db.save_question(conn, soru)
    assert db.load_questions(conn) == [soru]
    assert db.load_answer_keys(conn) == {soru.answer_key}


def test_degerlendirme_gidis_donus(conn: sqlite3.Connection):
    db.save_template(conn, ornek_sablon())
    db.save_question(
        conn,
        GeneratedQuestion(
            id="q1",
            template_id="t1",
            bindings={"p0": 4, "p1": -2},
            text="metin",
            answer_latex="8 x - 2",
            answer_key="anahtar",
            created_at="2026-08-13T10:00:00+00:00",
        ),
    )
    degerlendirme = Review(
        question_id="q1",
        approved=True,
        difficulty=6,
        quality=8,
        created_at="2026-08-13T10:01:00+00:00",
    )
    db.save_review(conn, degerlendirme)
    assert db.load_reviews(conn) == [degerlendirme]


def test_puan_araligi_veritabaninda_zorunlu(conn: sqlite3.Connection):
    db.save_template(conn, ornek_sablon())
    db.save_question(
        conn,
        GeneratedQuestion(
            id="q1",
            template_id="t1",
            bindings={},
            text="metin",
            answer_latex="x",
            answer_key="anahtar",
            created_at="2026-08-13T10:00:00+00:00",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.save_review(
            conn,
            Review(
                question_id="q1",
                approved=True,
                difficulty=0,  # geçersiz: 1-10 dışı
                quality=8,
                created_at="2026-08-13T10:01:00+00:00",
            ),
        )
