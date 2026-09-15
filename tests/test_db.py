from __future__ import annotations

import multiprocessing
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


# --- eşzamanlı göç ----------------------------------------------------------


def _eszamanli_baglan(yol: str, bariyer) -> None:
    bariyer.wait(timeout=60)
    db.connect(yol).close()


def test_eszamanli_baglantilar_gocu_bir_kez_uygular(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    for tur in range(4):
        yol = str(tmp_path / f"es-{tur}.db")
        bariyer = ctx.Barrier(4)
        surecler = [
            ctx.Process(target=_eszamanli_baglan, args=(yol, bariyer)) for _ in range(4)
        ]
        for s in surecler:
            s.start()
        for s in surecler:
            s.join(timeout=120)
        assert [s.exitcode for s in surecler] == [0, 0, 0, 0], f"tur {tur}"
        kontrol = db.connect(yol)
        assert kontrol.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        kontrol.close()


# --- hata sonrası işlem kapanır ---------------------------------------------


def _hazir_dosya(tmp_path):
    yol = tmp_path / "yazma.db"
    c = db.connect(yol)
    db.save_source(c, SourceQuestion(id="s1", text="t", recipe="2*x"))
    db.save_template(c, _sablon())
    db.save_question(c, _soru("q1"))
    db.save_review(c, Review("q1", True, 5, 8, "2026-09-15T10:00:00+00:00"))
    db.save_student(c, Student(id="st1", alias="A", created_at="x"))
    db.save_exam(c, Exam(id="ex1", title="S", created_at="x"))
    for tablo in ("source_questions", "reviews", "exams"):
        c.execute(
            f"CREATE TRIGGER engel_{tablo} BEFORE DELETE ON {tablo} "
            "BEGIN SELECT RAISE(ABORT, 'engel'); END"
        )
    c.commit()
    return yol, c


_BOZUK_YAZMALAR = {
    "save_source": lambda c: db.save_source(c, SourceQuestion(id="s2", text=None)),
    "delete_source": lambda c: db.delete_source(c, "s1"),
    "save_template": lambda c: db.save_template(c, replace(_sablon(), status="bogus")),
    "set_template_status": lambda c: db.set_template_status(c, "t1", "bogus"),
    "save_question": lambda c: db.save_question(c, _soru("q9", tid="olmayan")),
    "set_question_archived": lambda c: db.set_question_archived(c, "q1", 2),
    "save_review": lambda c: db.save_review(c, Review("q1", True, 0, 8, "x")),
    "delete_review": lambda c: db.delete_review(c, "q1"),
    "save_student": lambda c: db.save_student(c, Student(id="st2", alias="B", level=11)),
    "assign_questions": lambda c: db.assign_questions(c, "st1", ["olmayan"], "x"),
    "save_exam": lambda c: db.save_exam(c, Exam(id="ex2", title="S", kind="bogus")),
    "delete_exam": lambda c: db.delete_exam(c, "ex1"),
}


def test_tum_yazma_fonksiyonlari_kapsaniyor():
    yazanlar = {
        ad for ad in vars(db)
        if ad.startswith(("save_", "delete_", "set_", "assign_")) and callable(getattr(db, ad))
    }
    assert yazanlar == set(_BOZUK_YAZMALAR)


@pytest.mark.parametrize("ad", sorted(_BOZUK_YAZMALAR))
def test_yazma_hatasi_islemi_acik_birakmaz(tmp_path, ad):
    yol, c1 = _hazir_dosya(tmp_path)
    with pytest.raises(sqlite3.DatabaseError):
        _BOZUK_YAZMALAR[ad](c1)
    assert not c1.in_transaction
    c2 = db.connect(yol)
    c2.execute("PRAGMA busy_timeout = 200")
    db.save_source(c2, SourceQuestion(id="s3", text="ikinci"))
    assert db.get_source(c1, "s3") is not None
    if ad == "delete_source":
        assert db.get_template(c1, "t1").status == "trial"
    c2.close()
    c1.close()


# --- sıralama ve bayrak kısıtları -------------------------------------------


def test_ayni_zamanli_kaynaklar_ekleme_sirasiyla_doner(conn):
    for sid in ("s_f", "s_a", "s_c"):
        db.save_source(conn, SourceQuestion(id=sid, text=sid, created_at="2026-09-15"))
    assert [s.id for s in db.load_sources(conn)] == ["s_f", "s_a", "s_c"]


def test_ayni_zamanli_sablon_soru_sinav_ekleme_sirasini_korur(conn):
    for tid in ("t_z", "t_a"):
        db.save_template(conn, _sablon(tid))
    assert [t.id for t in db.load_templates(conn)] == ["t_z", "t_a"]
    assert [t.id for t in db.load_templates_for_source(conn, "s1")] == ["t_z", "t_a"]
    for qid in ("q_z", "q_a"):
        db.save_question(conn, _soru(qid, tid="t_z"))
    assert [q.id for q in db.load_questions(conn)] == ["q_z", "q_a"]
    for qid in ("q_z", "q_a"):
        db.save_review(conn, Review(qid, True, 5, 5, "2026-09-15"))
    assert [r.question_id for r in db.load_reviews(conn)] == ["q_z", "q_a"]
    for eid in ("ex_a", "ex_z"):
        db.save_exam(conn, Exam(id=eid, title="S", created_at="2026-09-15"))
    assert [e.id for e in db.load_exams(conn)] == ["ex_z", "ex_a"]
    for sid in ("st_z", "st_a"):
        db.save_student(conn, Student(id=sid, alias="Ayni", created_at="x"))
    assert [s.id for s in db.load_students(conn)] == ["st_z", "st_a"]


@pytest.mark.parametrize("alan", ["archived", "similar_given"])
def test_soru_bayraklari_0_1_disi_yazilamaz(conn, alan):
    db.save_template(conn, _sablon())
    with pytest.raises(sqlite3.IntegrityError):
        db.save_question(conn, _soru(**{alan: 2}))
