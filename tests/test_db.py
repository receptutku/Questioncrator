from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from questioncrator import db
from questioncrator.models import (
    Exam,
    GeneratedQuestion,
    Parameter,
    Review,
    SourceQuestion,
    Student,
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


def test_zorluk_ust_sinir_veritabaninda_zorunlu(conn: sqlite3.Connection):
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
                difficulty=11,  # geçersiz: 1-10 dışı (üst sınır)
                quality=8,
                created_at="2026-08-13T10:01:00+00:00",
            ),
        )


def test_kalite_alt_sinir_veritabaninda_zorunlu(conn: sqlite3.Connection):
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
                difficulty=5,
                quality=0,  # geçersiz: 1-10 dışı (alt sınır)
                created_at="2026-08-13T10:01:00+00:00",
            ),
        )


def test_kalite_ust_sinir_veritabaninda_zorunlu(conn: sqlite3.Connection):
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
                difficulty=5,
                quality=11,  # geçersiz: 1-10 dışı (üst sınır)
                created_at="2026-08-13T10:01:00+00:00",
            ),
        )


def test_onay_araligi_veritabaninda_zorunlu(conn: sqlite3.Connection):
    # Review.approved tip ipucu bool'dur, ama Python çalışma zamanında
    # dataclass alanlarını tip denetiminden geçirmez — bu yüzden genel API
    # üzerinden (Review + save_review) 0/1 dışı bir değer üretmek mümkündür.
    # CHECK (approved IN (0, 1)) bu durumda gerçek bir güvenlik ağıdır.
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
                approved=2,  # geçersiz: tip ipucunu ihlal eden 0/1 dışı değer
                difficulty=5,
                quality=5,
                created_at="2026-08-13T10:01:00+00:00",
            ),
        )


def test_kaynak_soru_needs_review_true_gidis_donus(conn: sqlite3.Connection):
    kaynak = SourceQuestion(
        id="s1",
        text="f(x) = 3x^2 + 5x fonksiyonunun türevi nedir?",
        recipe="diff(3*x**2 + 5*x, x)",
        objective="turev.polinom",
        needs_review=True,
    )
    db.save_source(conn, kaynak)
    assert db.load_sources(conn) == [kaynak]
    assert db.load_sources(conn)[0].needs_review is True


def test_degerlendirme_approved_false_gidis_donus(conn: sqlite3.Connection):
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
        approved=False,
        difficulty=6,
        quality=8,
        created_at="2026-08-13T10:01:00+00:00",
    )
    db.save_review(conn, degerlendirme)
    assert db.load_reviews(conn) == [degerlendirme]
    assert db.load_reviews(conn)[0].approved is False


def test_sablon_kisitlar_gercek_icerikle_gidis_donus(conn: sqlite3.Connection):
    sablon = replace(ornek_sablon(), constraints=("{p0} > {p1}", "{p0} != {p1}"))
    db.save_template(conn, sablon)
    yuklenen = db.load_templates(conn)
    assert yuklenen == [sablon]
    assert yuklenen[0].constraints == ("{p0} > {p1}", "{p0} != {p1}")


# --- şema v2 ----------------------------------------------------------------


def test_yeni_veritabani_son_surumde(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tablolar = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"students", "student_questions", "exams"} <= tablolar


def test_v1_dosyasi_veri_kaybetmeden_goc_eder(tmp_path):
    yol = tmp_path / "eski.db"
    ham = sqlite3.connect(yol)
    ham.executescript(db.MIGRATIONS[0])
    ham.execute(
        "INSERT INTO source_questions (id, text, recipe, objective, needs_review) "
        "VALUES ('s1', 'metin', '2*x', 'k', 0)"
    )
    ham.commit()
    ham.close()

    yeni = db.connect(yol)
    (kaynak,) = db.load_sources(yeni)
    assert kaynak.id == "s1" and kaynak.origin == "markdown" and kaynak.answer_text is None
    assert yeni.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    yeni.close()


def _sablon(tid="t1", source_id="s1"):
    return Template(
        id=tid, source_id=source_id, skeleton="{p0}x", recipe="{p0}*x",
        parameters=(Parameter("p0", -9, 9, (0,)),), seed_bindings={"p0": 3},
        seed_answer_ops=1, objective="k", difficulty_estimate=3.5,
    )


def _soru(qid="q1", tid="t1", **ek):
    alanlar = dict(
        id=qid, template_id=tid, bindings={"p0": 4}, text="4x", answer_latex="4 x",
        answer_key=f"k-{qid}", created_at="2026-09-15T10:00:00+00:00",
    )
    alanlar.update(ek)
    return GeneratedQuestion(**alanlar)


def test_yeni_alanlar_gidis_donus(conn):
    db.save_source(conn, SourceQuestion(
        id="s1", text="t", recipe="2*x", answer_text="2x", origin="manual",
        review_note="not", created_at="2026-09-15T10:00:00+00:00",
    ))
    db.save_template(conn, _sablon())
    soru = _soru(choices=("4 x", "5 x", "3 x", "-4 x", "8 x"), correct_index=0,
                 difficulty_estimate=4.2, created_by="u1", similar_given=True)
    db.save_question(conn, soru)
    assert db.get_source(conn, "s1").answer_text == "2x"
    assert db.get_template(conn, "t1").difficulty_estimate == 3.5
    assert db.get_question(conn, "q1") == soru
    assert db.get_question(conn, "yok") is None


def test_upsert_satir_cogaltmaz(conn):
    db.save_template(conn, _sablon())
    db.save_question(conn, _soru())
    db.save_question(conn, _soru(text="değişti"))
    assert [q.text for q in db.load_questions(conn)] == ["değişti"]


def test_bilinmeyen_sablona_soru_yazilamaz(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_question(conn, _soru(tid="olmayan"))


def test_arsivlenen_soru_filtrelenir(conn):
    db.save_template(conn, _sablon())
    db.save_question(conn, _soru("q1"))
    db.save_question(conn, _soru("q2"))
    db.set_question_archived(conn, "q2", True)
    assert [q.id for q in db.load_questions(conn, include_archived=False)] == ["q1"]
    assert len(db.load_questions(conn)) == 2


def test_kaynak_silinince_sablonlari_kapanir(conn):
    db.save_source(conn, SourceQuestion(id="s1", text="t", recipe="2*x"))
    db.save_template(conn, _sablon())
    db.delete_source(conn, "s1")
    assert db.get_source(conn, "s1") is None
    assert db.get_template(conn, "t1").status == "disabled"


def test_degerlendirme_silinir(conn):
    db.save_template(conn, _sablon())
    db.save_question(conn, _soru())
    db.save_review(conn, Review("q1", True, 5, 8, "2026-09-15T10:00:00+00:00", reviewer_id="u1"))
    assert db.get_review(conn, "q1").reviewer_id == "u1"
    db.delete_review(conn, "q1")
    assert db.get_review(conn, "q1") is None


def test_ogrenci_ve_atamalar(conn):
    db.save_template(conn, _sablon())
    db.save_question(conn, _soru("q1"))
    ogrenci = Student(id="st1", alias="Ali", weak_objectives=("k",), level=6,
                      created_at="2026-09-15T10:00:00+00:00")
    db.save_student(conn, ogrenci)
    db.assign_questions(conn, "st1", ["q1", "q1"], "2026-09-15T10:00:00+00:00")
    assert db.get_student(conn, "st1") == ogrenci
    assert db.load_student_question_ids(conn, "st1") == {"q1"}
    assert db.load_student_template_ids(conn, "st1") == {"t1"}
    db.save_student(conn, Student(**{**ogrenci.__dict__, "archived": True}))
    assert db.load_students(conn) == []
    assert len(db.load_students(conn, include_archived=True)) == 1


def test_ogrenci_seviyesi_sinirli(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_student(conn, Student(id="st1", alias="A", level=11, created_at="x"))


def test_sinav_gidis_donus_ve_siralama(conn):
    eski = Exam(id="ex1", title="Eski", question_ids=("q1",), settings={"format": "mc"},
                created_at="2026-09-14T10:00:00+00:00")
    yeni = Exam(id="ex2", title="Yeni", kind="worksheet", created_at="2026-09-15T10:00:00+00:00")
    db.save_exam(conn, eski)
    db.save_exam(conn, yeni)
    assert [e.id for e in db.load_exams(conn)] == ["ex2", "ex1"]
    assert db.get_exam(conn, "ex1") == eski
    db.delete_exam(conn, "ex1")
    assert db.get_exam(conn, "ex1") is None
