# Questioncrator — Faz 1 (Çekirdek + Kart Akışı) Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hocanın yapılandırılmış bir soru havuzu yükleyip, sistemin otomatik çıkardığı şablonlardan doğrulanmış yeni sorular üretmesini, bunları kart akışında puanlayıp onaylamasını ve onaylılardan PDF sınav kağıdı + cevap anahtarı almasını sağlayan çalışır bir sürüm.

**Architecture:** Konudan tamamen bağımsız bir "reçete" boru hattı. Bir kaynak sorusu = *metin* + *SymPy reçetesi* (cevabı hesaplayan ifade dizesi). Şablon çıkarımı, reçetedeki sayısal literalleri tokenize ederek parametreye çevirir ve aynı değerleri metinde de yer tutucuya dönüştürür. Üretim = parametre örnekle → metni ve reçeteyi biçimlendir → SymPy ile değerlendir → jenerik doğrulayıcıdan geçir. Kodda türev/limit/integral/matris gibi hiçbir konu adı geçmez.

**Tech Stack:** Python 3.11+, SymPy, SQLite (stdlib `sqlite3`), Streamlit, Jinja2, pytest, ruff.

**Spec:** `docs/tasarim-v0.5.md`

## Global Constraints

- **Konu bağımsızlığı (ihlal edilemez).** Kaynak kodda hiçbir yerde belirli bir matematik konusuna özel dal, sabit, isim veya `if` bulunmaz. Bu kural testlerle korunur (Görev 6, Adım 9). Yeni bir konu desteği = yeni kaynak sorusu, kod değişikliği değil.
- **Python sürüm tabanı:** 3.11+. `from __future__ import annotations` her modülün ilk satırıdır.
- **Veri yereldir.** Tek bir SQLite dosyası (`questioncrator.db`), varsayılan konum çalışma dizini. Ağ çağrısı Faz 1'de yoktur.
- **Öğrenci kişisel verisi yoktur.** Faz 1 şemasında öğrenci tablosu bulunmaz (Faz 3'e ait).
- **LLM Faz 1'de kullanılmaz.** Yalnız `LLMClient` protokolü + `NullLLMClient` yazılır (Görev 11). Somut sağlayıcı Faz 2'de seçilir.
- **Arayüz dili Türkçe.** Kullanıcıya görünen tüm dizeler Türkçedir. Kod tanımlayıcıları (fonksiyon/değişken adları) İngilizce, yorumlar Türkçedir.
- **Rastgelelik enjekte edilir.** Üretim yapan hiçbir fonksiyon `random` modülünü global olarak çağırmaz; `rng: random.Random` parametresi alır. Testler `random.Random(0)` ile deterministiktir.
- **Zaman enjekte edilir.** `created_at` üreten hiçbir fonksiyon içeride `datetime.now()` çağırmaz; ISO-8601 dize parametresi alır.
- **Puanlar 1-10 tam sayıdır.** Zorluk ve kurgu ayrı ayrı. Puansız onay/red kaydı yasaktır (veri tabanı seviyesinde `CHECK` ile).
- **Test komutu:** `pytest -q`. Lint: `ruff check .`. Her görev bunlar yeşilken biter.

---

## Dosya Yapısı

Görevler bu yapıyı üretir. Her dosyanın tek bir sorumluluğu vardır.

```
questioncrator/
  __init__.py
  mathenv.py              SymPy ifadelerini kısıtlı ad alanında, zaman aşımlı ayrıştırma
  models.py               Değişmez veri sınıfları (tek gerçeklik kaynağı)
  db.py                   SQLite şeması + kaydet/yükle fonksiyonları
  ingest/
    __init__.py
    markdown.py           Yapılandırılmış Markdown -> SourceQuestion
  templating/
    __init__.py
    extract.py            Kaynak soru -> Template (sayısal literal parametreleştirme)
    render.py             Template + bağlama -> soru metni / çalıştırılabilir reçete
  generation/
    __init__.py
    sampler.py            Parametre örnekleme + kısıt süzme
    engine.py             Şablon seçimi, deneme modu, kopya filtresi, parti üretimi
  verification/
    __init__.py
    checks.py             Jenerik SymPy doğrulamaları
  scoring/
    __init__.py
    store.py              Değerlendirme kaydı + şablon skorları + durum geçişleri
  export/
    __init__.py
    latex.py              Jinja2 -> LaTeX -> PDF
    templates/
      exam.tex.j2
      answers.tex.j2
  llm/
    __init__.py
    client.py             LLMClient protokolü + NullLLMClient
  app/
    __init__.py
    state.py              Streamlit'ten bağımsız, test edilebilir uygulama mantığı
    main.py               Streamlit giriş noktası, 3 sekme
tests/
  test_mathenv.py
  test_db.py
  test_ingest_markdown.py
  test_templating.py
  test_sampler.py
  test_verification.py
  test_engine.py
  test_scoring.py
  test_export.py
  test_app_state.py
  test_llm_client.py
  test_topic_agnostic.py
  data/
    ornek_havuz.md
docs/
  tasarim-v0.5.md
  superpowers/plans/2026-08-13-faz1-cekirdek-kart-akisi.md
pyproject.toml
README.md
```

---

## Kavram Sözlüğü (uygulayıcı için)

Kod yazmadan önce bunları anlamak zorunludur.

**Reçete (recipe).** Cevabı hesaplayan, SymPy'nin anlayacağı bir ifade dizesi. Örnek: `diff(3*x**2 + 5*x - 2, x)`. Reçete *çalıştırılmaz*, ayrıştırılır — `mathenv.parse` kısıtlı bir ad alanında değerlendirir. Reçete konudan bağımsızdır: `limit(sin(3*x)/x, x, 0)`, `Matrix([[2, 1], [4, 3]]).det()`, `solve(2*y + 6, y)` hepsi geçerli reçetedir.

**Şablon (template).** Bir kaynak sorusundan otomatik çıkarılan parametrik iskelet. İki paralel dizeden oluşur:
- `skeleton`: soru metni, sayılar `{p0}` gibi yer tutucularla değiştirilmiş.
- `recipe`: aynı sayılar aynı yer tutucularla değiştirilmiş reçete.

Aynı sayısal değer her iki dizede de **aynı** parametreye eşlenir. Şablonun tutarlılığı buradan gelir: `{p0}` metinde de reçetede de aynı sayıya açılır.

**Bağlama (binding).** `{"p0": 4, "p1": -3}` gibi parametre → tam sayı eşlemesi. Bir şablon + bir bağlama = bir soru.

**Cevap anahtarı (answer_key).** Değerlendirilmiş cevabın `sympy.srepr` gösterimi. Kopya tespitinde kullanılır: aynı cevaba açılan iki soru aynı sorudur.

**Deneme modu (trial).** Yeni çıkarılan her şablon `status="trial"` başlar. Bir üretim partisinde bir deneme şablonundan en fazla 2 soru çıkabilir. İki onay alınca `active` olur, üç red + düşük kurgu puanı alınca `disabled` olur.

---

### Görev 1: Proje iskeleti + güvenli matematik ortamı

Bu görev projeyi ayağa kaldırır ve tüm sonraki görevlerin dayandığı tek temel yardımcıyı yazar: rastgele bir dizeyi SymPy nesnesine çeviren, `eval` güvenlik açığı ve sonsuz döngü riski kapatılmış bir ayrıştırıcı.

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `.gitignore`
- Create: `questioncrator/__init__.py`
- Create: `questioncrator/mathenv.py`
- Test: `tests/test_mathenv.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `questioncrator.mathenv.parse(recipe: str) -> sympy.Basic`
  - `questioncrator.mathenv.parse_with_timeout(recipe: str, seconds: float = 5.0) -> sympy.Basic`
  - `questioncrator.mathenv.UnsafeExpression(ValueError)`
  - `questioncrator.mathenv.EvaluationTimeout(Exception)`

- [ ] **Adım 1: `pyproject.toml` yaz**

```toml
[project]
name = "questioncrator"
version = "0.1.0"
description = "Havuz tabanlı otomatik soru üretim sistemi"
requires-python = ">=3.11"
dependencies = [
    "sympy>=1.12",
    "streamlit>=1.35",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.5"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["questioncrator*"]

[tool.setuptools.package-data]
"questioncrator.export" = ["templates/*.j2"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Adım 2: `.gitignore` ve `README.md` yaz**

`.gitignore`:
```
__pycache__/
*.py[cod]
.venv/
*.egg-info/
.pytest_cache/
.ruff_cache/
questioncrator.db
build/
dist/
*.pdf
*.aux
*.log
*.fls
*.fdb_latexmk
```

`README.md`:
```markdown
# Questioncrator

Havuz tabanlı otomatik soru üretim sistemi. Tasarım: `docs/tasarim-v0.5.md`.

## Kurulum

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Test

    pytest -q
    ruff check .

## Çalıştırma

    streamlit run questioncrator/app/main.py
```

- [ ] **Adım 3: Sanal ortamı kur ve bağımlılıkları yükle**

```bash
cd ~/Questioncrator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Beklenen: hatasız kurulum. `python -c "import sympy, streamlit, jinja2"` sessiz döner.

- [ ] **Adım 4: Başarısız testi yaz**

`tests/test_mathenv.py`:
```python
from __future__ import annotations

import time

import pytest
import sympy

from questioncrator import mathenv


def test_basit_ifade_ayristirilir():
    assert mathenv.parse("3*x**2 + 5*x - 2") == sympy.sympify("3*x**2 + 5*x - 2")


def test_sympy_fonksiyonlari_calisir():
    x = sympy.Symbol("x")
    assert mathenv.parse("diff(3*x**2 + 5*x - 2, x)") == 6 * x + 5


def test_farkli_konudan_recete_de_calisir():
    # Konu bağımsızlığı: ayrıştırıcı hiçbir konuyu ayrıcalıklı görmez.
    assert mathenv.parse("Matrix([[2, 1], [4, 3]]).det()") == 2
    assert mathenv.parse("limit(sin(3*x)/x, x, 0)") == 3


def test_liste_donen_recete_normallesir():
    """`solve` düz Python listesi döndürür; boru hattı her yerde Basic bekler."""
    sonuc = mathenv.parse("solve(2*y + 6, y)")
    assert isinstance(sonuc, sympy.Basic)
    assert list(sonuc) == [-3]


def test_degisebilir_matris_normallesir():
    sonuc = mathenv.parse("Matrix([[1, 2], [3, 4]]) * 2")
    assert isinstance(sonuc, sympy.Basic)


def test_cift_alt_cizgi_reddedilir():
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse("(1).__class__")


def test_builtin_erisimi_yok():
    with pytest.raises(Exception):
        mathenv.parse("open('/etc/passwd')")


def test_zaman_asimi_yukselir(monkeypatch):
    # Gerçekten pahalı bir SymPy ifadesi kullanmıyoruz: iş parçacığı zorla
    # sonlandırılamadığı için test bitiminde arkada takılı kalırdı.
    def yavas(recipe: str) -> sympy.Basic:
        time.sleep(0.5)
        return sympy.Integer(1)

    monkeypatch.setattr(mathenv, "parse", yavas)
    with pytest.raises(mathenv.EvaluationTimeout):
        mathenv.parse_with_timeout("1", seconds=0.05)
```

- [ ] **Adım 5: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_mathenv.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.mathenv'`

- [ ] **Adım 6: Asgari uygulamayı yaz**

`questioncrator/__init__.py`:
```python
"""Havuz tabanlı otomatik soru üretim sistemi."""

__version__ = "0.1.0"
```

`questioncrator/mathenv.py`:
```python
"""SymPy ifadelerini kısıtlı ad alanında, zaman aşımlı biçimde değerlendirir.

Reçeteler hocanın dosyalarından gelir. Yine de düz `eval` kullanmayız:
sympy'nin kendi ayrıştırıcısını, yalnız sympy adlarını içeren bir küresel
sözlükle çalıştırırız. Böylece reçete dili "herhangi bir SymPy ifadesi"
kadar geniş kalır ama Python'un geri kalanına erişemez.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations


class UnsafeExpression(ValueError):
    """Reçete, ayrıştırılmadan önce sözdizimsel bir güvenlik kuralına takıldı."""


class EvaluationTimeout(Exception):
    """Reçete verilen süre içinde değerlendirilemedi."""


def _allowed_namespace() -> dict[str, object]:
    ns: dict[str, object] = {name: getattr(sympy, name) for name in sympy.__all__}
    # Yerleşik Python fonksiyonlarına erişimi kapat; sympy adları yeter.
    ns["__builtins__"] = {}
    return ns


def _normalize(value: object) -> sympy.Basic:
    """SymPy'nin Basic olmayan dönüşlerini Basic'e çevirir.

    Bazı sympy çağrıları düz Python listesi ya da değişebilir bir kap
    nesnesi döndürür. Boru hattının geri kalanı her yerde `Basic` bekler
    (`count_ops`, `srepr`, `latex`), bu yüzden tek noktada normalleştiririz.
    """
    if isinstance(value, sympy.matrices.MatrixBase):
        return sympy.ImmutableMatrix(value)
    if isinstance(value, (list, tuple, set)):
        return sympy.Tuple(*[_normalize(v) for v in value])
    if isinstance(value, sympy.Basic):
        return value
    return sympy.sympify(value)


def parse(recipe: str) -> sympy.Basic:
    """Reçete dizesini SymPy nesnesine çevirir.

    Konu bağımsızdır: sympy'nin genel ad alanındaki adların hepsi eşit
    derecede geçerlidir, hiçbir işlem ailesi ayrıcalıklı değildir.
    """
    if "__" in recipe:
        raise UnsafeExpression("çift alt çizgi içeren ifade reddedildi")
    if "import" in recipe:
        raise UnsafeExpression("`import` içeren ifade reddedildi")
    return _normalize(
        parse_expr(
            recipe,
            global_dict=_allowed_namespace(),
            transformations=standard_transformations,
        )
    )


def parse_with_timeout(recipe: str, seconds: float = 5.0) -> sympy.Basic:
    """`parse` ile aynı, ancak verilen süreyi aşarsa `EvaluationTimeout` yükseltir.

    Not: iş parçacığı zorla sonlandırılamaz; süresi dolan hesap arka planda
    tükenene kadar devam eder. Faz 1 için kabul edilebilir — üretim partileri
    küçüktür ve süresi dolan reçete zaten doğrulamadan geçemez.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(parse, recipe).result(timeout=seconds)
    except FutureTimeout as exc:
        raise EvaluationTimeout(f"{seconds} saniyede değerlendirilemedi") from exc
    finally:
        pool.shutdown(wait=False)
```

- [ ] **Adım 7: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_mathenv.py -q && ruff check .`
Expected: 8 passed, ruff temiz.

Eğer `test_builtin_erisimi_yok` beklenmedik biçimde geçmezse (yani `open` çağrısı çalışırsa), `_allowed_namespace` içindeki `__builtins__` atamasının `parse_expr`'e gerçekten iletildiğini doğrula; sympy sürümüne göre `local_dict={}` de geçmek gerekebilir.

- [ ] **Adım 8: Commit**

```bash
git add pyproject.toml README.md .gitignore questioncrator tests
git commit -m "feat: proje iskeleti ve güvenli SymPy ayrıştırma ortamı"
```

---

### Görev 2: Veri modeli + SQLite deposu

Tüm sonraki görevler bu veri sınıflarını konuşur. Şema burada kilitlenir.

**Files:**
- Create: `questioncrator/models.py`
- Create: `questioncrator/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `models.Parameter(name: str, low: int, high: int, exclude: tuple[int, ...])`
  - `models.SourceQuestion(id, text, recipe, objective, needs_review)`
  - `models.Template(id, source_id, skeleton, recipe, parameters, constraints, seed_bindings, seed_answer_ops, objective, status)`
  - `models.GeneratedQuestion(id, template_id, bindings, text, answer_latex, answer_key, created_at)`
  - `models.Review(question_id, approved, difficulty, quality, created_at)`
  - `db.connect(path="questioncrator.db", *, check_same_thread=True) -> sqlite3.Connection`
  - `db.save_source(conn, source) -> None` / `db.load_sources(conn) -> list[SourceQuestion]`
  - `db.save_template(conn, template) -> None` / `db.load_templates(conn) -> list[Template]` / `db.set_template_status(conn, template_id, status) -> None`
  - `db.save_question(conn, question) -> None` / `db.load_questions(conn) -> list[GeneratedQuestion]` / `db.load_answer_keys(conn) -> set[str]`
  - `db.save_review(conn, review) -> None` / `db.load_reviews(conn) -> list[Review]`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_db.py`:
```python
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
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_db.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.models'`

- [ ] **Adım 3: `models.py` yaz**

```python
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


@dataclass(frozen=True)
class Review:
    """Hocanın bir kart için verdiği karar + çift puan."""

    question_id: str
    approved: bool
    difficulty: int  # 1-10
    quality: int  # 1-10 (kurgu)
    created_at: str
```

- [ ] **Adım 4: `db.py` yaz**

```python
"""SQLite şeması ve kaydet/yükle fonksiyonları.

Veri hocanın makinesinde, tek bir dosyada durur. Karmaşık alanlar
(parametreler, bağlamalar, kısıtlar) JSON metin sütunlarında saklanır —
Faz 1 için sorgu ihtiyacı yok, sadeliği tercih ediyoruz.
"""

from __future__ import annotations

import json
import sqlite3
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
            json.dumps([p.__dict__ for p in template.parameters]),
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
```

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_db.py -q && ruff check .`
Expected: 6 passed.

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/models.py questioncrator/db.py tests/test_db.py
git commit -m "feat: veri modeli ve SQLite deposu"
```

---

### Görev 3: Alım — yapılandırılmış Markdown

Faz 1'in havuz girdisi tek bir Markdown dosyasıdır. Serbest format (Word/PDF/OCR) Faz 3'e aittir; burada onu taklit etmiyoruz.

**Files:**
- Create: `questioncrator/ingest/__init__.py`
- Create: `questioncrator/ingest/markdown.py`
- Create: `tests/data/ornek_havuz.md`
- Test: `tests/test_ingest_markdown.py`

**Interfaces:**
- Consumes: `models.SourceQuestion`
- Produces:
  - `ingest.markdown.parse_pool(content: str) -> list[SourceQuestion]`
  - `ingest.markdown.load_pool(path: str | Path) -> list[SourceQuestion]`

**Dosya biçimi.** Sorular `---` satırıyla ayrılır. Her blok üç başlık taşıyabilir:

```markdown
### Soru
f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz.

### Cevap
diff(3*x**2 + 5*x - 2, x)

### Kazanım
turev.polinom
```

`### Cevap` yoksa soru kaydedilir ama `needs_review=True` olur — Sekme 1'deki "elle kontrol gerekli" listesine düşer. Kimlikler `s1`, `s2`, ... biçiminde dosyadaki sıraya göre verilir.

- [ ] **Adım 1: Örnek havuz dosyasını yaz**

`tests/data/ornek_havuz.md` — bilerek üç farklı konudan, konu bağımsızlığını kanıtlayacak biçimde:
```markdown
### Soru
f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz.

### Cevap
diff(3*x**2 + 5*x - 2, x)

### Kazanım
turev.polinom

---

### Soru
$\lim_{x \to 0} \frac{\sin(3x)}{x}$ limitini hesaplayınız.

### Cevap
limit(sin(3*x)/x, x, 0)

### Kazanım
limit.trigonometrik

---

### Soru
A = [[2, 1], [4, 3]] matrisinin determinantını bulunuz.

### Cevap
Matrix([[2, 1], [4, 3]]).det()

### Kazanım
matris.determinant

---

### Soru
Bu sorunun makine tarafından okunabilir bir cevabı yok.

### Kazanım
belirsiz
```

- [ ] **Adım 2: Başarısız testi yaz**

`tests/test_ingest_markdown.py`:
```python
from __future__ import annotations

from pathlib import Path

from questioncrator.ingest import markdown

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"


def test_dort_soru_okunur():
    sorular = markdown.load_pool(VERI)
    assert len(sorular) == 4
    assert [s.id for s in sorular] == ["s1", "s2", "s3", "s4"]


def test_alanlar_dogru_ayrisir():
    sorular = markdown.load_pool(VERI)
    ilk = sorular[0]
    assert ilk.text == "f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz."
    assert ilk.recipe == "diff(3*x**2 + 5*x - 2, x)"
    assert ilk.objective == "turev.polinom"
    assert ilk.needs_review is False


def test_konu_bagimsiz_receteler_korunur():
    sorular = markdown.load_pool(VERI)
    assert sorular[1].recipe == "limit(sin(3*x)/x, x, 0)"
    assert sorular[2].recipe == "Matrix([[2, 1], [4, 3]]).det()"


def test_recetesiz_soru_elle_kontrol_kuyruguna_dusuyor():
    sorular = markdown.load_pool(VERI)
    assert sorular[3].recipe is None
    assert sorular[3].needs_review is True


def test_bos_icerik_bos_liste_verir():
    assert markdown.parse_pool("") == []
    assert markdown.parse_pool("\n---\n   \n") == []


def test_cok_satirli_soru_metni_korunur():
    icerik = """### Soru
Birinci satır.
İkinci satır.

### Cevap
2 + 2
"""
    (soru,) = markdown.parse_pool(icerik)
    assert soru.text == "Birinci satır.\nİkinci satır."
    assert soru.recipe == "2 + 2"
```

- [ ] **Adım 3: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_ingest_markdown.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.ingest'`

- [ ] **Adım 4: Uygulamayı yaz**

`questioncrator/ingest/__init__.py`:
```python
"""Havuz alım katmanı (A1)."""
```

`questioncrator/ingest/markdown.py`:
```python
"""Yapılandırılmış Markdown havuzunu SourceQuestion listesine çevirir (A1).

Faz 1'in tek alım biçimi budur. Serbest format (Word/PDF/OCR) Faz 3'te
bu modülün yanına kardeş modüller olarak eklenir; arayüz aynı kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

from questioncrator.models import SourceQuestion

_BASLIK = re.compile(r"^###\s+(Soru|Cevap|Kazanım)\s*$", re.MULTILINE)


def _parse_block(block: str) -> dict[str, str]:
    """Tek bir soru bloğunu {başlık: gövde} sözlüğüne çevirir."""
    parcalar = _BASLIK.split(block)
    # split sonucu: [önsöz, başlık1, gövde1, başlık2, gövde2, ...]
    alanlar: dict[str, str] = {}
    for i in range(1, len(parcalar) - 1, 2):
        alanlar[parcalar[i]] = parcalar[i + 1].strip()
    return alanlar


def parse_pool(content: str) -> list[SourceQuestion]:
    sorular: list[SourceQuestion] = []
    for block in re.split(r"^---\s*$", content, flags=re.MULTILINE):
        alanlar = _parse_block(block)
        metin = alanlar.get("Soru", "").strip()
        if not metin:
            continue
        recete = alanlar.get("Cevap") or None
        sorular.append(
            SourceQuestion(
                id=f"s{len(sorular) + 1}",
                text=metin,
                recipe=recete,
                objective=alanlar.get("Kazanım") or None,
                needs_review=recete is None,
            )
        )
    return sorular


def load_pool(path: str | Path) -> list[SourceQuestion]:
    return parse_pool(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_ingest_markdown.py -q && ruff check .`
Expected: 6 passed.

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/ingest tests/test_ingest_markdown.py tests/data
git commit -m "feat: yapılandırılmış Markdown havuz alımı"
```

---

### Görev 4: Şablon çıkarımı + render

Sistemin kalbi. Kaynak sorudan otomatik, deterministik, konudan bağımsız şablon çıkarır. Hoca onayı yoktur (tasarım v0.5); kalite kapısı ileride soru seviyesindedir.

**Algoritma.**
1. Reçeteyi Python `tokenize` ile çöz, `NUMBER` jetonlarını bul.
2. Üs konumundaki sayıları atla (`**` jetonundan hemen sonra gelenler) — üs yapısaldır, değiştirilirse soru başka bir soruya dönüşür.
3. Sıfır ve tam sayı olmayan literalleri atla — sıfır genellikle yapısaldır, kesirli katsayı Faz 1 kapsamı dışıdır.
4. Kalan her **farklı değer** için ilk görülme sırasına göre bir parametre adı üret (`p0`, `p1`, ...). Aynı değer aynı parametreye eşlenir (deterministik, öngörülebilir politika).
5. Reçetedeki jeton aralıklarını `{pN}` ile değiştir → `Template.recipe`.
6. Aynı değerleri soru metninde de `{pN}` ile değiştir; üs konumundakileri (`^2`, `**2`) ve kelime içine gömülü rakamları koru → `Template.skeleton`.
7. Tohum bağlamasını (`seed_bindings`) ve tohum cevabının işlem sayısını (`seed_answer_ops`) kaydet — doğrulayıcı bunları "dejenere sonuç" ölçütü olarak kullanır.

**Files:**
- Create: `questioncrator/templating/__init__.py`
- Create: `questioncrator/templating/extract.py`
- Create: `questioncrator/templating/render.py`
- Test: `tests/test_templating.py`

**Interfaces:**
- Consumes: `models.SourceQuestion`, `models.Template`, `models.Parameter`, `mathenv.parse_with_timeout`
- Produces:
  - `templating.extract.extract_template(source: SourceQuestion, template_id: str) -> Template`
  - `templating.extract.NoParametersFound(Exception)`
  - `templating.render.render_text(template: Template, bindings: dict[str, int]) -> str`
  - `templating.render.render_recipe(template: Template, bindings: dict[str, int]) -> str`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_templating.py`:
```python
from __future__ import annotations

import pytest
import sympy

from questioncrator import mathenv
from questioncrator.models import Parameter, SourceQuestion, Template
from questioncrator.templating import extract, render


def kaynak(text: str, recipe: str) -> SourceQuestion:
    return SourceQuestion(id="s1", text=text, recipe=recipe, objective="k")


def test_katsayilar_parametrelesir():
    s = kaynak(
        "f(x) = 3x^2 + 5x - 2 fonksiyonunun türevini bulunuz.",
        "diff(3*x**2 + 5*x - 2, x)",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "diff({p0}*x**2 + {p1}*x - {p2}, x)"
    assert t.skeleton == "f(x) = {p0}x^2 + {p1}x - {p2} fonksiyonunun türevini bulunuz."
    assert [p.name for p in t.parameters] == ["p0", "p1", "p2"]
    assert t.seed_bindings == {"p0": 3, "p1": 5, "p2": 2}


def test_us_parametrelesmez():
    s = kaynak("x^2 ifadesi", "diff(x**2, x)")
    with pytest.raises(extract.NoParametersFound):
        extract.extract_template(s, "t1")


def test_ayni_deger_ayni_parametreye_baglanir():
    s = kaynak("3 ve 3 sayıları", "3 + 3*x")
    t = extract.extract_template(s, "t1")
    assert t.recipe == "{p0} + {p0}*x"
    assert len(t.parameters) == 1


def test_konu_bagimsiz_limit_recetesi():
    s = kaynak(
        "$\\lim_{x \\to 0} \\frac{\\sin(3x)}{x}$ limitini hesaplayınız.",
        "limit(sin(3*x)/x, x, 0)",
    )
    t = extract.extract_template(s, "t1")
    # 0 yapısaldır: parametreleşmez. Yalnız 3 parametre olur.
    assert t.recipe == "limit(sin({p0}*x)/x, x, 0)"
    assert len(t.parameters) == 1


def test_konu_bagimsiz_matris_recetesi():
    s = kaynak(
        "A = [[2, 1], [4, 3]] matrisinin determinantını bulunuz.",
        "Matrix([[2, 1], [4, 3]]).det()",
    )
    t = extract.extract_template(s, "t1")
    assert t.recipe == "Matrix([[{p0}, {p1}], [{p2}, {p3}]]).det()"
    assert t.seed_bindings == {"p0": 2, "p1": 1, "p2": 4, "p3": 3}


def test_recetesiz_kaynak_reddedilir():
    with pytest.raises(ValueError):
        extract.extract_template(SourceQuestion(id="s1", text="metin", recipe=None), "t1")


def test_tohum_islem_sayisi_kaydedilir():
    s = kaynak("f(x) = 3x^2 + 5x", "diff(3*x**2 + 5*x, x)")
    t = extract.extract_template(s, "t1")
    # diff(3x^2+5x) = 6x+5 -> Add(Mul(6,x), 5) : 2 işlem
    assert t.seed_answer_ops == sympy.sympify("6*x + 5").count_ops()


def test_render_metin_ve_recete():
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="f(x) = {p0}x^2 + {p1}x",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
    )
    assert render.render_text(t, {"p0": 4, "p1": -2}) == "f(x) = 4x^2 + -2x"
    assert render.render_recipe(t, {"p0": 4, "p1": -2}) == "diff((4)*x**2 + (-2)*x, x)"


def test_render_recete_negatif_degeri_parantezler():
    """Parantezsiz `-3**2` = -9 olurdu; parantezli `(-3)**2` = 9. Kritik."""
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}",
        recipe="{p0}**2",
        parameters=(Parameter("p0", -9, 9, (0,)),),
        seed_bindings={"p0": 3},
        seed_answer_ops=1,
    )
    assert mathenv.parse(render.render_recipe(t, {"p0": -3})) == 9
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_templating.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.templating'`

- [ ] **Adım 3: `extract.py` yaz**

`questioncrator/templating/__init__.py`:
```python
"""Şablon çıkarımı ve render katmanı (A3)."""
```

`questioncrator/templating/extract.py`:
```python
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
    secilen: list[tokenize.TokenInfo] = []
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
        secilen.append(tok)
    return secilen


def _replace_token_spans(
    recipe: str, replacements: list[tuple[tokenize.TokenInfo, str]]
) -> str:
    """Jeton aralıklarını sondan başa doğru değiştirir (konumlar kaymasın diye)."""
    lines = recipe.splitlines(keepends=True) or [""]
    for tok, yeni in sorted(replacements, key=lambda r: r[0].start, reverse=True):
        satir_no = tok.start[0] - 1
        bas, son = tok.start[1], tok.end[1]
        satir = lines[satir_no]
        lines[satir_no] = satir[:bas] + yeni + satir[son:]
    return "".join(lines)


def _parametrize_text(text: str, value_to_param: dict[int, str]) -> str:
    """Metindeki sayıları yer tutucuya çevirir.

    Uzun değerden kısaya gidilir ki `12` varken `1` önce eşleşmesin.
    Lookbehind'lar üs (`^2`, `**2`) ve kelime içi rakamları korur.
    """
    for value in sorted(value_to_param, key=lambda v: -len(str(v))):
        desen = rf"(?<![\w.^]){re.escape(str(value))}(?![\w.])"
        text = re.sub(desen, "{" + value_to_param[value] + "}", text)
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

    seed_bindings = {ad: deger for deger, ad in value_to_param.items()}
    seed_answer = parse_with_timeout(source.recipe)

    return Template(
        id=template_id,
        source_id=source.id,
        skeleton=skeleton_text,
        recipe=skeleton_recipe,
        parameters=tuple(
            Parameter(name=ad, low=DEFAULT_LOW, high=DEFAULT_HIGH, exclude=(0,))
            for ad in value_to_param.values()
        ),
        constraints=(),
        seed_bindings=seed_bindings,
        seed_answer_ops=int(seed_answer.count_ops()),
        objective=source.objective,
        status="trial",
    )
```

- [ ] **Adım 4: `render.py` yaz**

```python
"""Şablon + bağlamadan soru metni ve çalıştırılabilir reçete üretir."""

from __future__ import annotations

from questioncrator.models import Template


def render_text(template: Template, bindings: dict[str, int]) -> str:
    """Hocaya ve öğrenciye görünecek soru metni."""
    return template.skeleton.format(**bindings)


def render_recipe(template: Template, bindings: dict[str, int]) -> str:
    """SymPy'ye verilecek reçete.

    Değerler parantezlenir: parantezsiz `-3**2` Python'da -9 verir, oysa
    kastedilen (-3)^2 = 9'dur.
    """
    return template.recipe.format(**{ad: f"({deger})" for ad, deger in bindings.items()})
```

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_templating.py -q && ruff check .`
Expected: 9 passed.

`test_katsayilar_parametrelesir` ilk denemede kalabilir: `- 2` ifadesinde tokenize `2`'yi NUMBER olarak verir, eksi ayrı OP jetonudur. Beklenen çıktı bu yüzden `- {p2}`'dir; test de öyle yazılmıştır. Metinde de aynı davranış geçerlidir.

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/templating tests/test_templating.py
git commit -m "feat: otomatik şablon çıkarımı ve render"
```

---

### Görev 5: Parametre örnekleme + kısıt süzme

**Files:**
- Create: `questioncrator/generation/__init__.py`
- Create: `questioncrator/generation/sampler.py`
- Test: `tests/test_sampler.py`

**Interfaces:**
- Consumes: `models.Template`, `models.Parameter`, `mathenv.parse`, `templating.render`
- Produces:
  - `generation.sampler.sample_bindings(template, rng, attempts=50) -> dict[str, int] | None`
  - `generation.sampler.satisfies_constraints(template, bindings) -> bool`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_sampler.py`:
```python
from __future__ import annotations

import random

from questioncrator.generation import sampler
from questioncrator.models import Parameter, Template


def sablon(constraints: tuple[str, ...] = ()) -> Template:
    return Template(
        id="t1",
        source_id="s1",
        skeleton="{p0} ve {p1}",
        recipe="{p0}*x + {p1}",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        constraints=constraints,
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
    )


def test_ornekleme_alan_icinde_kalir():
    rng = random.Random(0)
    b = sampler.sample_bindings(sablon(), rng)
    assert set(b) == {"p0", "p1"}
    assert all(-9 <= v <= 9 and v != 0 for v in b.values())


def test_ornekleme_deterministik():
    assert sampler.sample_bindings(sablon(), random.Random(7)) == sampler.sample_bindings(
        sablon(), random.Random(7)
    )


def test_kisit_uygulanir():
    t = sablon(constraints=("{p0} > {p1}",))
    for tohum in range(20):
        b = sampler.sample_bindings(t, random.Random(tohum))
        if b is not None:
            assert b["p0"] > b["p1"]


def test_saglanamayan_kisit_none_dondurur():
    t = sablon(constraints=("{p0} > 1000",))
    assert sampler.sample_bindings(t, random.Random(0), attempts=10) is None


def test_satisfies_constraints_dogrudan():
    t = sablon(constraints=("{p0} > {p1}",))
    assert sampler.satisfies_constraints(t, {"p0": 5, "p1": 2}) is True
    assert sampler.satisfies_constraints(t, {"p0": 2, "p1": 5}) is False
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_sampler.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.generation'`

- [ ] **Adım 3: Uygulamayı yaz**

`questioncrator/generation/__init__.py`:
```python
"""Üretim motoru katmanı (A4)."""
```

`questioncrator/generation/sampler.py`:
```python
"""Şablon parametrelerini örnekler ve kısıtlardan süzer (A4).

Rastgelelik dışarıdan verilir (`rng`) — testlerin ve tekrar üretilebilir
partilerin şartı.
"""

from __future__ import annotations

import random

import sympy

from questioncrator.mathenv import parse
from questioncrator.models import Parameter, Template


def _sample_parameter(param: Parameter, rng: random.Random) -> int:
    aday = rng.randint(param.low, param.high)
    while aday in param.exclude:
        aday = rng.randint(param.low, param.high)
    return aday


def satisfies_constraints(template: Template, bindings: dict[str, int]) -> bool:
    """Şablonun tüm kısıtları bu bağlamada doğru mu?

    Kısıt dizeleri `{p0} > {p1}` gibi yer tutuculu SymPy ifadeleridir.
    """
    for kisit in template.constraints:
        formatli = kisit.format(**{ad: f"({v})" for ad, v in bindings.items()})
        if parse(formatli) != sympy.true:
            return False
    return True


def sample_bindings(
    template: Template, rng: random.Random, attempts: int = 50
) -> dict[str, int] | None:
    """Kısıtları sağlayan bir bağlama üretir; `attempts` denemede bulamazsa None."""
    for _ in range(attempts):
        bindings = {p.name: _sample_parameter(p, rng) for p in template.parameters}
        if satisfies_constraints(template, bindings):
            return bindings
    return None
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_sampler.py -q && ruff check .`
Expected: 5 passed.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/generation tests/test_sampler.py
git commit -m "feat: parametre örnekleme ve kısıt süzme"
```

---

### Görev 6: Doğrulayıcı (A6)

Şablon onayı kaldırıldığı için matematiksel kalite kapısı tamamen burasıdır. Kontroller jeneriktir — hiçbiri "bu bir türev sorusu" bilgisine dayanmaz.

**Kontroller.**
1. **Değerlendirilebilirlik:** reçete zaman aşımı olmadan ayrıştırılıyor mu?
2. **Tanımlılık:** sonuçta `nan`, `zoo`, `oo` var mı?
3. **Dejenere olmama:** cevabın işlem sayısı, tohum cevabınkinin yarısından az mı? (Örn. tüm katsayılar sadeleşip cevap sabite düşmüş.)
4. **Sayı estetiği:** cevaptaki rasyonel sayıların pay/paydası makul sınırlar içinde mi?
5. **Kararlılık:** aynı reçete iki kez değerlendirildiğinde aynı `srepr` çıkıyor mu?
6. **Kısıt uyumu:** şablonun kısıtları bağlamada gerçekten sağlanıyor mu?

**Files:**
- Create: `questioncrator/verification/__init__.py`
- Create: `questioncrator/verification/checks.py`
- Test: `tests/test_verification.py`
- Test: `tests/test_topic_agnostic.py`

**Interfaces:**
- Consumes: `models.Template`, `mathenv.parse_with_timeout`, `templating.render.render_recipe`, `generation.sampler.satisfies_constraints`
- Produces:
  - `verification.checks.VerificationResult(ok: bool, answer: sympy.Basic | None, notes: tuple[str, ...])`
  - `verification.checks.verify(template, bindings, *, timeout=5.0) -> VerificationResult`
  - `verification.checks.MAX_NUMERATOR`, `verification.checks.MAX_DENOMINATOR`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_verification.py`:
```python
from __future__ import annotations

from questioncrator.models import Parameter, Template
from questioncrator.verification import checks


def turev_sablonu() -> Template:
    return Template(
        id="t1",
        source_id="s1",
        skeleton="f(x) = {p0}x^2 + {p1}x",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
    )


def test_gecerli_baglama_dogrulanir():
    sonuc = checks.verify(turev_sablonu(), {"p0": 4, "p1": -2})
    assert sonuc.ok is True
    assert sonuc.answer is not None
    assert sonuc.notes == ()


def test_tanimsiz_sonuc_reddedilir():
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}/{p1}",
        recipe="{p0}/({p1} - {p1})",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=1,
    )
    sonuc = checks.verify(t, {"p0": 4, "p1": 2})
    assert sonuc.ok is False
    assert any("tanımsız" in n for n in sonuc.notes)


def test_dejenere_sadelesme_reddedilir():
    # Tohum cevabı 2 işlem; bu bağlamada cevap sabite düşerse dejeneredir.
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}x - {p0}x + {p1}",
        recipe="{p0}*x - {p0}*x + {p1}",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=4,
    )
    sonuc = checks.verify(t, {"p0": 3, "p1": 5})
    assert sonuc.ok is False
    assert any("dejenere" in n for n in sonuc.notes)


def test_cirkin_sayi_reddedilir():
    t = Template(
        id="t1",
        source_id="s1",
        skeleton="{p0}/{p1}",
        recipe="Rational({p0}, {p1}) * 10**6",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=1,
    )
    sonuc = checks.verify(t, {"p0": 7, "p1": 3})
    assert sonuc.ok is False
    assert any("sayı büyüklüğü" in n for n in sonuc.notes)


def test_kisit_ihlali_reddedilir():
    t = turev_sablonu()
    t = Template(**{**t.__dict__, "constraints": ("{p0} > {p1}",)})
    sonuc = checks.verify(t, {"p0": 1, "p1": 5})
    assert sonuc.ok is False
    assert any("kısıt" in n for n in sonuc.notes)


def test_zaman_asimi_reddedilir(monkeypatch):
    def zaman_asimi(recipe: str, seconds: float = 5.0):
        raise checks.EvaluationTimeout("test")

    monkeypatch.setattr(checks, "parse_with_timeout", zaman_asimi)
    sonuc = checks.verify(turev_sablonu(), {"p0": 4, "p1": -2})
    assert sonuc.ok is False
    assert any("zaman aşımı" in n for n in sonuc.notes)
```

`tests/test_topic_agnostic.py` — Global Constraint'i koruyan bekçi test:
```python
from __future__ import annotations

import random
from pathlib import Path

from questioncrator.generation import sampler
from questioncrator.ingest import markdown
from questioncrator.templating import extract
from questioncrator.verification import checks

KAYNAK_KOK = Path(__file__).parent.parent / "questioncrator"
VERI = Path(__file__).parent / "data" / "ornek_havuz.md"

# Kodda geçmesi yasak konu adları. Yeni konu = yeni kaynak sorusu, kod değil.
YASAK = ["turev", "türev", "limit", "integral", "matris", "determinant", "polinom"]


def test_kaynak_kodda_konu_adi_gecmiyor():
    ihlaller = []
    for yol in KAYNAK_KOK.rglob("*.py"):
        icerik = yol.read_text(encoding="utf-8").lower()
        for kelime in YASAK:
            if kelime in icerik:
                ihlaller.append(f"{yol.relative_to(KAYNAK_KOK)}: {kelime}")
    assert ihlaller == [], f"Konuya özel kod bulundu: {ihlaller}"


def test_uc_farkli_konu_ayni_boru_hattindan_geciyor():
    kaynaklar = [s for s in markdown.load_pool(VERI) if s.recipe]
    assert len(kaynaklar) == 3  # farklı üç konu
    for i, kaynak in enumerate(kaynaklar):
        sablon = extract.extract_template(kaynak, f"t{i}")
        baglama = sampler.sample_bindings(sablon, random.Random(i))
        assert baglama is not None, f"{kaynak.id}: bağlama üretilemedi"
        # Doğrulama başarısız olabilir (dejenere değer denk gelebilir), ama
        # boru hattı istisna fırlatmadan sonuna kadar gitmelidir.
        sonuc = checks.verify(sablon, baglama)
        assert isinstance(sonuc.ok, bool)
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_verification.py tests/test_topic_agnostic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.verification'`

- [ ] **Adım 3: Uygulamayı yaz**

`questioncrator/verification/__init__.py`:
```python
"""Doğrulama katmanı (A6)."""
```

`questioncrator/verification/checks.py`:
```python
"""Üretilen bir sorunun matematiksel olarak sağlam olup olmadığını denetler (A6).

Şablon onayı kaldırıldığı için otomatik kalite kapısı burasıdır. Tüm
kontroller jeneriktir: cevabın hangi işlemden geldiğini bilmez, yalnız
sonucun kendisine bakar.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy

from questioncrator.generation.sampler import satisfies_constraints
from questioncrator.mathenv import EvaluationTimeout, UnsafeExpression, parse_with_timeout
from questioncrator.models import Template
from questioncrator.templating.render import render_recipe

MAX_NUMERATOR = 9999
MAX_DENOMINATOR = 99
MIN_OPS_RATIO = 0.5  # cevap, tohum cevabının en az yarısı kadar "zengin" olmalı

_TANIMSIZ = (sympy.nan, sympy.zoo, sympy.oo, -sympy.oo)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    answer: sympy.Basic | None
    notes: tuple[str, ...]


def _tanimsiz_mi(expr: sympy.Basic) -> bool:
    return any(atom in _TANIMSIZ for atom in sympy.preorder_traversal(expr))


def _sayilar_cirkin_mi(expr: sympy.Basic) -> bool:
    for atom in expr.atoms(sympy.Rational):
        if abs(atom.p) > MAX_NUMERATOR or abs(atom.q) > MAX_DENOMINATOR:
            return True
    return False


def verify(
    template: Template, bindings: dict[str, int], *, timeout: float = 5.0
) -> VerificationResult:
    notlar: list[str] = []

    if not satisfies_constraints(template, bindings):
        return VerificationResult(False, None, ("şablon kısıtları sağlanmıyor",))

    recete = render_recipe(template, bindings)
    try:
        cevap = parse_with_timeout(recete, seconds=timeout)
    except EvaluationTimeout:
        return VerificationResult(False, None, ("değerlendirme zaman aşımına uğradı",))
    except (UnsafeExpression, SyntaxError, TypeError, ValueError, ZeroDivisionError) as exc:
        return VerificationResult(False, None, (f"değerlendirilemedi: {exc}",))

    if _tanimsiz_mi(cevap):
        notlar.append("sonuç tanımsız (nan/zoo/oo)")

    if template.seed_answer_ops and cevap.count_ops() < template.seed_answer_ops * MIN_OPS_RATIO:
        notlar.append("dejenere sadeleşme: cevap tohum cevabından çok daha basit")

    if _sayilar_cirkin_mi(cevap):
        notlar.append("sayı büyüklüğü sınırları aşıldı")

    try:
        ikinci = parse_with_timeout(recete, seconds=timeout)
    except EvaluationTimeout:
        return VerificationResult(False, None, ("değerlendirme zaman aşımına uğradı",))
    if sympy.srepr(ikinci) != sympy.srepr(cevap):
        notlar.append("kararsız sonuç: iki değerlendirme farklı çıktı")

    return VerificationResult(ok=not notlar, answer=cevap, notes=tuple(notlar))
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_verification.py tests/test_topic_agnostic.py -q`
Expected: 8 passed.

`test_kaynak_kodda_konu_adi_gecmiyor` başarısız olursa: `checks.py` veya başka bir modüle sızmış konu adını (yorum dahil) kaldır. Örnek/test verisi `tests/` altındadır ve tarama dışıdır — orada konu adı serbesttir.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/verification tests/test_verification.py tests/test_topic_agnostic.py
git commit -m "feat: jenerik SymPy doğrulayıcı ve konu bağımsızlığı bekçi testi"
```

---

### Görev 7: Üretim motoru — şablon seçimi, deneme modu, kopya filtresi

**Files:**
- Create: `questioncrator/generation/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `models.Template`, `models.GeneratedQuestion`, `sampler.sample_bindings`, `checks.verify`, `render.render_text`
- Produces:
  - `generation.engine.TRIAL_BATCH_CAP = 2`
  - `generation.engine.generate_from_template(template, *, count, rng, now, seen_answer_keys, id_prefix) -> list[GeneratedQuestion]`
  - `generation.engine.generate_batch(templates, *, total, rng, now, seen_answer_keys, objectives=None) -> list[GeneratedQuestion]`

**Kurallar.**
- `status == "disabled"` şablonlar hiç kullanılmaz.
- `status == "trial"` şablonlardan bir partide en fazla `TRIAL_BATCH_CAP` (=2) soru çıkar.
- Cevap anahtarı daha önce görülmüş bir soru üretilmez (kopya filtresi).
- `objectives` verilirse yalnız o kazanımlardaki şablonlar kullanılır (Faz 3'ün öğrenci sayfası bu parametreyi kullanacak; Faz 1'de Sekme 2 filtresi olarak da işe yarar).
- Şablonlar `rng` ile karıştırılır; parti üretimi deterministiktir.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_engine.py`:
```python
from __future__ import annotations

import random

from questioncrator.generation import engine
from questioncrator.models import Parameter, Template

SIMDI = "2026-08-13T10:00:00+00:00"


def sablon(tid: str, status: str = "active", objective: str = "k1") -> Template:
    return Template(
        id=tid,
        source_id="s1",
        skeleton="f(x) = {p0}x^2 + {p1}x fonksiyonunu inceleyiniz.",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5},
        seed_answer_ops=2,
        objective=objective,
        status=status,
    )


def test_istenen_sayida_soru_uretilir():
    sorular = engine.generate_from_template(
        sablon("t1"), count=5, rng=random.Random(0), now=SIMDI,
        seen_answer_keys=set(), id_prefix="q",
    )
    assert len(sorular) == 5
    assert all(s.template_id == "t1" for s in sorular)
    assert len({s.id for s in sorular}) == 5


def test_uretilen_metin_baglamayla_uyumlu():
    (soru,) = engine.generate_from_template(
        sablon("t1"), count=1, rng=random.Random(3), now=SIMDI,
        seen_answer_keys=set(), id_prefix="q",
    )
    assert "{p0}" not in soru.text
    assert str(soru.bindings["p0"]) in soru.text


def test_kopya_cevap_uretilmez():
    ilk = engine.generate_from_template(
        sablon("t1"), count=6, rng=random.Random(1), now=SIMDI,
        seen_answer_keys=set(), id_prefix="a",
    )
    gorulen = {s.answer_key for s in ilk}
    ikinci = engine.generate_from_template(
        sablon("t1"), count=6, rng=random.Random(1), now=SIMDI,
        seen_answer_keys=gorulen, id_prefix="b",
    )
    assert gorulen.isdisjoint({s.answer_key for s in ikinci})


def test_deneme_sablonu_partide_iki_soruyla_sinirli():
    sorular = engine.generate_batch(
        [sablon("t1", status="trial")], total=10, rng=random.Random(0),
        now=SIMDI, seen_answer_keys=set(),
    )
    assert len(sorular) == engine.TRIAL_BATCH_CAP


def test_devre_disi_sablon_kullanilmaz():
    sorular = engine.generate_batch(
        [sablon("t1", status="disabled")], total=5, rng=random.Random(0),
        now=SIMDI, seen_answer_keys=set(),
    )
    assert sorular == []


def test_kazanim_filtresi():
    sablonlar = [sablon("t1", objective="k1"), sablon("t2", objective="k2")]
    sorular = engine.generate_batch(
        sablonlar, total=6, rng=random.Random(0), now=SIMDI,
        seen_answer_keys=set(), objectives={"k2"},
    )
    assert sorular != []
    assert {s.template_id for s in sorular} == {"t2"}


def test_parti_uretimi_deterministik():
    sablonlar = [sablon("t1"), sablon("t2")]
    a = engine.generate_batch(
        sablonlar, total=6, rng=random.Random(42), now=SIMDI, seen_answer_keys=set()
    )
    b = engine.generate_batch(
        sablonlar, total=6, rng=random.Random(42), now=SIMDI, seen_answer_keys=set()
    )
    assert [s.text for s in a] == [s.text for s in b]
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_engine.py -q`
Expected: FAIL — `ImportError: cannot import name 'engine'`

- [ ] **Adım 3: Uygulamayı yaz**

`questioncrator/generation/engine.py`:
```python
"""Üretim partisini orkestre eder (A4 + A6 birleşimi).

Şablon seçer, parametre örnekler, doğrulatır, kopyaları eler. Deneme
modundaki şablonların hacmini kısarak hatalı bir şablonun tek seferde
çöp dalgası üretmesini engeller.
"""

from __future__ import annotations

import random

import sympy

from questioncrator.generation.sampler import sample_bindings
from questioncrator.models import GeneratedQuestion, Template
from questioncrator.templating.render import render_text
from questioncrator.verification.checks import verify

TRIAL_BATCH_CAP = 2
MAX_ATTEMPTS_PER_QUESTION = 20


def generate_from_template(
    template: Template,
    *,
    count: int,
    rng: random.Random,
    now: str,
    seen_answer_keys: set[str],
    id_prefix: str,
) -> list[GeneratedQuestion]:
    """Tek şablondan en fazla `count` doğrulanmış, birbirinden farklı soru üretir."""
    uretilen: list[GeneratedQuestion] = []
    yerel_gorulen = set(seen_answer_keys)

    while len(uretilen) < count:
        bulundu = False
        for _ in range(MAX_ATTEMPTS_PER_QUESTION):
            bindings = sample_bindings(template, rng)
            if bindings is None:
                continue
            sonuc = verify(template, bindings)
            if not sonuc.ok or sonuc.answer is None:
                continue
            anahtar = sympy.srepr(sonuc.answer)
            if anahtar in yerel_gorulen:
                continue
            yerel_gorulen.add(anahtar)
            uretilen.append(
                GeneratedQuestion(
                    id=f"{id_prefix}-{template.id}-{len(uretilen)}",
                    template_id=template.id,
                    bindings=bindings,
                    text=render_text(template, bindings),
                    answer_latex=sympy.latex(sonuc.answer),
                    answer_key=anahtar,
                    created_at=now,
                )
            )
            bulundu = True
            break
        if not bulundu:
            break  # bu şablon tükendi

    return uretilen


def _batch_cap(template: Template, remaining: int) -> int:
    if template.status == "trial":
        return min(TRIAL_BATCH_CAP, remaining)
    return remaining


def generate_batch(
    templates: list[Template],
    *,
    total: int,
    rng: random.Random,
    now: str,
    seen_answer_keys: set[str],
    objectives: set[str] | None = None,
) -> list[GeneratedQuestion]:
    """Şablonlar arasında dolaşarak toplam `total` soruya kadar üretir."""
    uygun = [
        t
        for t in templates
        if t.status != "disabled" and (objectives is None or t.objective in objectives)
    ]
    rng.shuffle(uygun)

    sonuc: list[GeneratedQuestion] = []
    gorulen = set(seen_answer_keys)
    # Şablon başına adil pay: toplam / şablon sayısı, en az 1.
    if not uygun:
        return []
    pay = max(1, total // len(uygun))

    for sablon in uygun:
        kalan = total - len(sonuc)
        if kalan <= 0:
            break
        kota = _batch_cap(sablon, min(pay, kalan))
        parca = generate_from_template(
            sablon,
            count=kota,
            rng=rng,
            now=now,
            seen_answer_keys=gorulen,
            id_prefix=f"q{len(sonuc)}",
        )
        gorulen.update(s.answer_key for s in parca)
        sonuc.extend(parca)

    return sonuc
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_engine.py -q && ruff check .`
Expected: 7 passed.

`test_kazanim_filtresi` başarısız olursa (boş liste dönerse) `pay` hesabını kontrol et: tek şablonda `pay = total`, doğru.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/generation/engine.py tests/test_engine.py
git commit -m "feat: üretim motoru, deneme modu ve kopya filtresi"
```

---

### Görev 8: Puan deposu + şablon skorları + durum geçişleri

Tasarımın "öğrenme sinyali" burada birikir. Faz 1'de sinyal **şablon durumu** olarak geri beslenir (deneme → etkin / devre dışı). Few-shot seçimi ve zorluk kalibrasyonu Faz 2'de aynı depodan okuyacak.

**Files:**
- Create: `questioncrator/scoring/__init__.py`
- Create: `questioncrator/scoring/store.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `db`, `models.Review`, `models.Template`
- Produces:
  - `scoring.store.TemplateScore(template_id, reviewed, approved, approval_rate, avg_quality, avg_difficulty)`
  - `scoring.store.template_scores(conn) -> dict[str, TemplateScore]`
  - `scoring.store.record_review(conn, review) -> None`
  - `scoring.store.apply_status_transitions(conn) -> dict[str, str]`
  - Eşikler: `PROMOTE_AFTER_APPROVALS = 2`, `DISABLE_AFTER_REJECTIONS = 3`, `DISABLE_QUALITY_CEILING = 4.0`

**Geçiş kuralları.**
- `trial` → `active`: şablondan en az `PROMOTE_AFTER_APPROVALS` onay geldiyse.
- `trial`/`active` → `disabled`: en az `DISABLE_AFTER_REJECTIONS` red geldiyse **ve** ortalama kurgu puanı `DISABLE_QUALITY_CEILING`'in altındaysa.
- Devre dışı bırakma önceliklidir (aynı anda iki koşul sağlanırsa şablon kapatılır).

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_scoring.py`:
```python
from __future__ import annotations

import pytest

from questioncrator import db
from questioncrator.models import GeneratedQuestion, Parameter, Review, Template
from questioncrator.scoring import store

SIMDI = "2026-08-13T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def hazirla(conn, template_id: str, adet: int, status: str = "trial") -> list[str]:
    db.save_template(
        conn,
        Template(
            id=template_id,
            source_id="s1",
            skeleton="{p0}",
            recipe="{p0}*x",
            parameters=(Parameter("p0", -9, 9, (0,)),),
            seed_bindings={"p0": 3},
            seed_answer_ops=1,
            status=status,
        ),
    )
    idler = []
    for i in range(adet):
        qid = f"{template_id}-q{i}"
        db.save_question(
            conn,
            GeneratedQuestion(
                id=qid, template_id=template_id, bindings={"p0": i + 1},
                text="metin", answer_latex="x", answer_key=f"k{template_id}{i}",
                created_at=SIMDI,
            ),
        )
        idler.append(qid)
    return idler


def test_skorlar_hesaplanir(conn):
    idler = hazirla(conn, "t1", 4)
    puanlar = [(True, 5, 8), (True, 6, 6), (False, 3, 4), (True, 7, 9)]
    for qid, (onay, zorluk, kurgu) in zip(idler, puanlar, strict=True):
        store.record_review(conn, Review(qid, onay, zorluk, kurgu, SIMDI))

    skor = store.template_scores(conn)["t1"]
    assert skor.reviewed == 4
    assert skor.approved == 3
    assert skor.approval_rate == pytest.approx(0.75)
    assert skor.avg_quality == pytest.approx((8 + 6 + 4 + 9) / 4)
    assert skor.avg_difficulty == pytest.approx((5 + 6 + 3 + 7) / 4)


def test_iki_onay_deneme_sablonunu_etkinlestirir(conn):
    idler = hazirla(conn, "t1", 2)
    for qid in idler:
        store.record_review(conn, Review(qid, True, 5, 8, SIMDI))

    gecisler = store.apply_status_transitions(conn)
    assert gecisler == {"t1": "active"}
    assert db.load_templates(conn)[0].status == "active"


def test_uc_red_ve_dusuk_kurgu_sablonu_kapatir(conn):
    idler = hazirla(conn, "t1", 3)
    for qid in idler:
        store.record_review(conn, Review(qid, False, 5, 2, SIMDI))

    assert store.apply_status_transitions(conn) == {"t1": "disabled"}
    assert db.load_templates(conn)[0].status == "disabled"


def test_uc_red_ama_yuksek_kurgu_kapatmaz(conn):
    idler = hazirla(conn, "t1", 3)
    for qid in idler:
        store.record_review(conn, Review(qid, False, 5, 9, SIMDI))

    assert store.apply_status_transitions(conn) == {}
    assert db.load_templates(conn)[0].status == "trial"


def test_kapatma_etkinlestirmeden_onceliklidir(conn):
    idler = hazirla(conn, "t1", 5)
    kararlar = [(True, 8), (True, 8), (False, 1), (False, 1), (False, 1)]
    for qid, (onay, kurgu) in zip(idler, kararlar, strict=True):
        store.record_review(conn, Review(qid, onay, 5, kurgu, SIMDI))

    assert store.apply_status_transitions(conn) == {"t1": "disabled"}


def test_degerlendirilmemis_sablon_gecis_yapmaz(conn):
    hazirla(conn, "t1", 2)
    assert store.apply_status_transitions(conn) == {}
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_scoring.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.scoring'`

- [ ] **Adım 3: Uygulamayı yaz**

`questioncrator/scoring/__init__.py`:
```python
"""Puan deposu ve öğrenme sinyali katmanı."""
```

`questioncrator/scoring/store.py`:
```python
"""Hocanın onay/red kararlarını ve çift puanını biriktirir, şablon skorlarına çevirir.

Faz 1'de sinyalin tek etkisi şablon durum geçişleridir. Faz 2'de aynı
depo few-shot örnek seçimini ve zorluk kalibrasyonunu besleyecektir —
bu yüzden ham puanlar en baştan eksiksiz saklanır.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from questioncrator import db
from questioncrator.models import Review

PROMOTE_AFTER_APPROVALS = 2
DISABLE_AFTER_REJECTIONS = 3
DISABLE_QUALITY_CEILING = 4.0


@dataclass(frozen=True)
class TemplateScore:
    template_id: str
    reviewed: int
    approved: int
    approval_rate: float
    avg_quality: float
    avg_difficulty: float


def record_review(conn: sqlite3.Connection, review: Review) -> None:
    db.save_review(conn, review)


def template_scores(conn: sqlite3.Connection) -> dict[str, TemplateScore]:
    rows = conn.execute(
        """
        SELECT g.template_id      AS template_id,
               COUNT(*)           AS reviewed,
               SUM(r.approved)    AS approved,
               AVG(r.quality)     AS avg_quality,
               AVG(r.difficulty)  AS avg_difficulty
        FROM reviews r
        JOIN generated_questions g ON g.id = r.question_id
        GROUP BY g.template_id
        """
    ).fetchall()
    return {
        r["template_id"]: TemplateScore(
            template_id=r["template_id"],
            reviewed=r["reviewed"],
            approved=r["approved"],
            approval_rate=r["approved"] / r["reviewed"],
            avg_quality=r["avg_quality"],
            avg_difficulty=r["avg_difficulty"],
        )
        for r in rows
    }


def apply_status_transitions(conn: sqlite3.Connection) -> dict[str, str]:
    """Skorlara bakıp şablon durumlarını günceller; değişenleri döndürür."""
    skorlar = template_scores(conn)
    degisenler: dict[str, str] = {}

    for sablon in db.load_templates(conn):
        skor = skorlar.get(sablon.id)
        if skor is None or sablon.status == "disabled":
            continue

        reddedilen = skor.reviewed - skor.approved
        if reddedilen >= DISABLE_AFTER_REJECTIONS and skor.avg_quality < DISABLE_QUALITY_CEILING:
            yeni = "disabled"
        elif sablon.status == "trial" and skor.approved >= PROMOTE_AFTER_APPROVALS:
            yeni = "active"
        else:
            continue

        db.set_template_status(conn, sablon.id, yeni)
        degisenler[sablon.id] = yeni

    return degisenler
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_scoring.py -q && ruff check .`
Expected: 6 passed.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/scoring tests/test_scoring.py
git commit -m "feat: puan deposu, şablon skorları ve durum geçişleri"
```

---

### Görev 9: Çıktı — LaTeX sınav kağıdı + cevap anahtarı

**Files:**
- Create: `questioncrator/export/__init__.py`
- Create: `questioncrator/export/latex.py`
- Create: `questioncrator/export/templates/exam.tex.j2`
- Create: `questioncrator/export/templates/answers.tex.j2`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `models.GeneratedQuestion`
- Produces:
  - `export.latex.render_exam_tex(questions, title) -> str`
  - `export.latex.render_answers_tex(questions, title) -> str`
  - `export.latex.build_pdf(tex: str, out_path: Path) -> Path`
  - `export.latex.LatexNotAvailable(Exception)`

**Not.** `build_pdf` sistemde `pdflatex` gerektirir. Testler yalnız `.tex` üretimini doğrular; PDF derlemesi testte atlanır (`pytest.mark.skipif`) ki CI ortamı TeX kurulumuna bağımlı olmasın.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_export.py`:
```python
from __future__ import annotations

import shutil

import pytest

from questioncrator.export import latex
from questioncrator.models import GeneratedQuestion

SIMDI = "2026-08-13T10:00:00+00:00"

SORULAR = [
    GeneratedQuestion(
        id="q1", template_id="t1", bindings={"p0": 4},
        text="f(x) = 4x^2 fonksiyonunu inceleyiniz.",
        answer_latex="8 x", answer_key="k1", created_at=SIMDI,
    ),
    GeneratedQuestion(
        id="q2", template_id="t1", bindings={"p0": 5},
        text="f(x) = 5x^2 fonksiyonunu inceleyiniz.",
        answer_latex="10 x", answer_key="k2", created_at=SIMDI,
    ),
]


def test_sinav_tex_uretilir():
    tex = latex.render_exam_tex(SORULAR, title="Ara Sınav")
    assert r"\documentclass" in tex
    assert "Ara Sınav" in tex
    assert tex.count(r"\item") == 2
    assert "f(x) = 4x^2" in tex
    # Sınav kağıdında cevap görünmemeli
    assert "8 x" not in tex


def test_cevap_anahtari_tex_uretilir():
    tex = latex.render_answers_tex(SORULAR, title="Ara Sınav")
    assert "Cevap Anahtarı" in tex
    assert "8 x" in tex
    assert "10 x" in tex


def test_bos_liste_yine_de_gecerli_tex_verir():
    tex = latex.render_exam_tex([], title="Boş")
    assert r"\begin{document}" in tex and r"\end{document}" in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex kurulu değil")
def test_pdf_derlenir(tmp_path):
    tex = latex.render_exam_tex(SORULAR, title="Ara Sınav")
    pdf = latex.build_pdf(tex, tmp_path / "sinav.pdf")
    assert pdf.exists() and pdf.stat().st_size > 0
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_export.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.export'`

- [ ] **Adım 3: Jinja şablonlarını yaz**

`questioncrator/export/templates/exam.tex.j2`:
```
\documentclass[12pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage[a4paper,margin=2.5cm]{geometry}
\pagestyle{empty}
\begin{document}
\begin{center}{\Large \textbf{\VAR{title}}}\end{center}
\vspace{1em}
\begin{enumerate}
\BLOCK{for q in questions}
  \item \VAR{q.text} \vspace{3cm}
\BLOCK{endfor}
\end{enumerate}
\end{document}
```

`questioncrator/export/templates/answers.tex.j2`:
```
\documentclass[12pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage[a4paper,margin=2.5cm]{geometry}
\pagestyle{empty}
\begin{document}
\begin{center}{\Large \textbf{\VAR{title} — Cevap Anahtarı}}\end{center}
\vspace{1em}
\begin{enumerate}
\BLOCK{for q in questions}
  \item \VAR{q.text} \\[0.3em] \textbf{Cevap:} $\VAR{q.answer_latex}$
\BLOCK{endfor}
\end{enumerate}
\end{document}
```

- [ ] **Adım 4: `latex.py` yaz**

`questioncrator/export/__init__.py`:
```python
"""Çıktı katmanı (A8)."""
```

`questioncrator/export/latex.py`:
```python
"""Onaylanmış sorulardan LaTeX sınav kağıdı ve cevap anahtarı üretir (A8).

Jinja2'nin varsayılan `{{ }}` sınırlayıcıları LaTeX'te çakıştığı için
`\\VAR{}` / `\\BLOCK{}` sınırlayıcıları kullanılır.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import jinja2

from questioncrator.models import GeneratedQuestion


class LatexNotAvailable(Exception):
    """Sistemde `pdflatex` bulunamadı."""


_ENV = jinja2.Environment(
    block_start_string=r"\BLOCK{",
    block_end_string="}",
    variable_start_string=r"\VAR{",
    variable_end_string="}",
    comment_start_string=r"\#{",
    comment_end_string="}",
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
    loader=jinja2.PackageLoader("questioncrator.export", "templates"),
)


def render_exam_tex(questions: Sequence[GeneratedQuestion], title: str) -> str:
    return _ENV.get_template("exam.tex.j2").render(questions=list(questions), title=title)


def render_answers_tex(questions: Sequence[GeneratedQuestion], title: str) -> str:
    return _ENV.get_template("answers.tex.j2").render(questions=list(questions), title=title)


def build_pdf(tex: str, out_path: str | Path) -> Path:
    if shutil.which("pdflatex") is None:
        raise LatexNotAvailable("pdflatex bulunamadı; PDF üretilemiyor")

    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        kaynak = tmp_dir / "belge.tex"
        kaynak.write_text(tex, encoding="utf-8")
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", kaynak.name],
            cwd=tmp_dir,
            check=True,
            capture_output=True,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes((tmp_dir / "belge.pdf").read_bytes())
    return out_path
```

- [ ] **Adım 5: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_export.py -q && ruff check .`
Expected: 3 passed, 1 skipped (pdflatex yoksa) veya 4 passed.

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/export tests/test_export.py
git commit -m "feat: LaTeX sınav kağıdı ve cevap anahtarı çıktısı"
```

---

### Görev 10: Streamlit uygulaması — Sekme 1 ve Sekme 2

Streamlit kodu test edilmez; test edilebilir tüm mantık `app/state.py` içine, Streamlit'ten bağımsız fonksiyonlar olarak yazılır. `main.py` yalnız çizim yapar.

**Files:**
- Create: `questioncrator/app/__init__.py`
- Create: `questioncrator/app/state.py`
- Create: `questioncrator/app/main.py`
- Test: `tests/test_app_state.py`

**Interfaces:**
- Consumes: `db`, `ingest.markdown`, `templating.extract`, `generation.engine`, `scoring.store`, `export.latex`
- Produces:
  - `app.state.PoolSummary(total, ready, needs_review, by_objective)`
  - `app.state.pool_summary(conn) -> PoolSummary`
  - `app.state.ingest_markdown_pool(conn, content) -> tuple[int, int]` → (kaydedilen kaynak, çıkarılan şablon)
  - `app.state.pending_cards(conn) -> list[GeneratedQuestion]`
  - `app.state.submit_review(conn, question_id, approved, difficulty, quality, now) -> dict[str, str]`
  - `app.state.produce_cards(conn, total, rng, now, objectives=None) -> list[GeneratedQuestion]`
  - `app.state.approved_questions(conn) -> list[GeneratedQuestion]`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_app_state.py`:
```python
from __future__ import annotations

import random
from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.app import state

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-08-13T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def test_havuz_alimi_kaynak_ve_sablon_uretir(conn):
    kaynak_sayisi, sablon_sayisi = state.ingest_markdown_pool(
        conn, VERI.read_text(encoding="utf-8")
    )
    assert kaynak_sayisi == 4
    assert sablon_sayisi == 3  # reçetesiz soru şablona çevrilmez
    assert len(db.load_templates(conn)) == 3


def test_havuz_ozeti(conn):
    state.ingest_markdown_pool(conn, VERI.read_text(encoding="utf-8"))
    ozet = state.pool_summary(conn)
    assert ozet.total == 4
    assert ozet.ready == 3
    assert ozet.needs_review == 1
    assert sum(ozet.by_objective.values()) == 4


def test_kart_uretimi_ve_bekleyenler(conn):
    state.ingest_markdown_pool(conn, VERI.read_text(encoding="utf-8"))
    kartlar = state.produce_cards(conn, total=6, rng=random.Random(0), now=SIMDI)
    assert kartlar != []
    # Deneme modunda 3 şablon x 2 = en fazla 6
    assert len(kartlar) <= 6
    assert [k.id for k in state.pending_cards(conn)] == [k.id for k in kartlar]


def test_degerlendirilen_kart_bekleyenlerden_cikar(conn):
    state.ingest_markdown_pool(conn, VERI.read_text(encoding="utf-8"))
    kartlar = state.produce_cards(conn, total=4, rng=random.Random(0), now=SIMDI)
    state.submit_review(conn, kartlar[0].id, True, 5, 8, SIMDI)
    bekleyen = state.pending_cards(conn)
    assert kartlar[0].id not in {k.id for k in bekleyen}
    assert len(bekleyen) == len(kartlar) - 1


def test_onaylanan_sorular_listelenir(conn):
    state.ingest_markdown_pool(conn, VERI.read_text(encoding="utf-8"))
    kartlar = state.produce_cards(conn, total=4, rng=random.Random(0), now=SIMDI)
    state.submit_review(conn, kartlar[0].id, True, 5, 8, SIMDI)
    state.submit_review(conn, kartlar[1].id, False, 5, 2, SIMDI)
    onayli = state.approved_questions(conn)
    assert [q.id for q in onayli] == [kartlar[0].id]


def test_iki_onay_sonrasi_sablon_etkinlesir(conn):
    state.ingest_markdown_pool(conn, VERI.read_text(encoding="utf-8"))
    kartlar = state.produce_cards(conn, total=6, rng=random.Random(0), now=SIMDI)
    hedef = kartlar[0].template_id
    ayni = [k for k in kartlar if k.template_id == hedef][:2]
    assert len(ayni) == 2
    for k in ayni[:-1]:
        state.submit_review(conn, k.id, True, 5, 8, SIMDI)
    gecisler = state.submit_review(conn, ayni[-1].id, True, 5, 8, SIMDI)
    assert gecisler == {hedef: "active"}
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_app_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.app'`

- [ ] **Adım 3: `state.py` yaz**

`questioncrator/app/__init__.py`:
```python
"""Streamlit uygulaması."""
```

`questioncrator/app/state.py`:
```python
"""Arayüzden bağımsız uygulama mantığı.

Streamlit'e hiçbir bağımlılığı yoktur; bu sayede tüm davranış düz pytest
ile doğrulanabilir. `main.py` yalnız burayı çağırır ve çizer.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter
from dataclasses import dataclass, replace

from questioncrator import db
from questioncrator.generation import engine
from questioncrator.ingest import markdown
from questioncrator.mathenv import EvaluationTimeout
from questioncrator.models import GeneratedQuestion, Review
from questioncrator.scoring import store
from questioncrator.templating import extract


@dataclass(frozen=True)
class PoolSummary:
    total: int
    ready: int
    needs_review: int
    by_objective: dict[str, int]


def ingest_markdown_pool(conn: sqlite3.Connection, content: str) -> tuple[int, int]:
    """Havuz metnini alır, kaynakları kaydeder ve şablon çıkarımını çalıştırır.

    Döndürür: (kaydedilen kaynak sayısı, çıkarılan şablon sayısı).
    """
    kaynaklar = markdown.parse_pool(content)
    mevcut = len(db.load_sources(conn))
    sablon_sayisi = 0

    for i, kaynak in enumerate(kaynaklar):
        # Var olan havuzun üstüne eklendiğinde kimlikler çakışmasın.
        kaynak = replace(kaynak, id=f"s{mevcut + i + 1}")
        db.save_source(conn, kaynak)
        if not kaynak.recipe:
            continue
        try:
            sablon = extract.extract_template(kaynak, template_id=f"t-{kaynak.id}")
        except (extract.NoParametersFound, ValueError, EvaluationTimeout):
            # Şablona çevrilemeyen kaynak havuzda kalır, sadece üretime girmez.
            continue
        db.save_template(conn, sablon)
        sablon_sayisi += 1

    return len(kaynaklar), sablon_sayisi


def pool_summary(conn: sqlite3.Connection) -> PoolSummary:
    kaynaklar = db.load_sources(conn)
    sayac = Counter((k.objective or "etiketsiz") for k in kaynaklar)
    return PoolSummary(
        total=len(kaynaklar),
        ready=sum(1 for k in kaynaklar if not k.needs_review),
        needs_review=sum(1 for k in kaynaklar if k.needs_review),
        by_objective=dict(sayac),
    )


def produce_cards(
    conn: sqlite3.Connection,
    total: int,
    rng: random.Random,
    now: str,
    objectives: set[str] | None = None,
) -> list[GeneratedQuestion]:
    kartlar = engine.generate_batch(
        db.load_templates(conn),
        total=total,
        rng=rng,
        now=now,
        seen_answer_keys=db.load_answer_keys(conn),
        objectives=objectives,
    )
    for kart in kartlar:
        db.save_question(conn, kart)
    return kartlar


def pending_cards(conn: sqlite3.Connection) -> list[GeneratedQuestion]:
    """Henüz puanlanmamış kartlar."""
    degerlendirilen = {r.question_id for r in db.load_reviews(conn)}
    return [q for q in db.load_questions(conn) if q.id not in degerlendirilen]


def submit_review(
    conn: sqlite3.Connection,
    question_id: str,
    approved: bool,
    difficulty: int,
    quality: int,
    now: str,
) -> dict[str, str]:
    """Karar + çift puanı kaydeder, şablon durum geçişlerini uygular."""
    store.record_review(
        conn,
        Review(
            question_id=question_id,
            approved=approved,
            difficulty=difficulty,
            quality=quality,
            created_at=now,
        ),
    )
    return store.apply_status_transitions(conn)


def approved_questions(conn: sqlite3.Connection) -> list[GeneratedQuestion]:
    onayli = {r.question_id for r in db.load_reviews(conn) if r.approved}
    return [q for q in db.load_questions(conn) if q.id in onayli]
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest tests/test_app_state.py -q && ruff check .`
Expected: 6 passed.

- [ ] **Adım 5: `main.py` yaz (Streamlit çizimi)**

```python
"""Streamlit giriş noktası — hocanın gördüğü üç sekme.

Çalıştırma: `streamlit run questioncrator/app/main.py`
"""

from __future__ import annotations

import random
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from questioncrator import db
from questioncrator.app import state
from questioncrator.export import latex


@st.cache_resource
def _conn():
    # Streamlit betiği farklı iş parçacıklarında çalıştırabilir.
    return db.connect("questioncrator.db", check_same_thread=False)


def _simdi() -> str:
    return datetime.now(UTC).isoformat()


def sekme_havuz(conn) -> None:
    st.header("Havuz")
    yuklenen = st.file_uploader(
        "Soru havuzu dosyası (yapılandırılmış Markdown)", type=["md", "txt"]
    )
    if yuklenen is not None and st.button("Havuza ekle"):
        kaynak_sayisi, sablon_sayisi = state.ingest_markdown_pool(
            conn, yuklenen.getvalue().decode("utf-8")
        )
        st.success(f"{kaynak_sayisi} soru okundu, {sablon_sayisi} şablon çıkarıldı.")

    ozet = state.pool_summary(conn)
    sutun1, sutun2, sutun3 = st.columns(3)
    sutun1.metric("Toplam soru", ozet.total)
    sutun2.metric("İşlenmeye hazır", ozet.ready)
    sutun3.metric("Elle kontrol gerekli", ozet.needs_review)

    if ozet.by_objective:
        st.subheader("Kazanım dağılımı")
        st.bar_chart(ozet.by_objective)


def sekme_kartlar(conn) -> None:
    st.header("Soru Önerileri")

    adet = st.number_input("Üretilecek soru sayısı", min_value=1, max_value=50, value=10)
    if st.button("Yeni öneriler üret"):
        uretilen = state.produce_cards(
            conn, total=int(adet), rng=random.Random(), now=_simdi()
        )
        st.success(f"{len(uretilen)} öneri üretildi.")

    bekleyen = state.pending_cards(conn)
    if not bekleyen:
        st.info("Bekleyen öneri yok. Yukarıdan yeni öneri üretebilirsiniz.")
    else:
        kart = bekleyen[0]
        st.caption(f"Bekleyen: {len(bekleyen)}")
        st.markdown(f"**Soru:** {kart.text}")
        st.latex(kart.answer_latex)

        zorluk = st.slider("Zorluk", 1, 10, 5, key=f"zorluk-{kart.id}")
        kurgu = st.slider("Kurgu", 1, 10, 5, key=f"kurgu-{kart.id}")

        onay_sutun, red_sutun = st.columns(2)
        if onay_sutun.button("Onayla", key=f"onay-{kart.id}"):
            gecisler = state.submit_review(conn, kart.id, True, zorluk, kurgu, _simdi())
            if gecisler:
                st.toast(f"Şablon durumu güncellendi: {gecisler}")
            st.rerun()
        if red_sutun.button("Reddet", key=f"red-{kart.id}"):
            gecisler = state.submit_review(conn, kart.id, False, zorluk, kurgu, _simdi())
            if gecisler:
                st.toast(f"Şablon durumu güncellendi: {gecisler}")
            st.rerun()

    onayli = state.approved_questions(conn)
    st.divider()
    st.subheader(f"Onaylı sorular: {len(onayli)}")
    if onayli:
        baslik = st.text_input("Sınav başlığı", value="Sınav")
        st.download_button(
            "Sınav kağıdı (.tex)",
            data=latex.render_exam_tex(onayli, baslik),
            file_name="sinav.tex",
        )
        st.download_button(
            "Cevap anahtarı (.tex)",
            data=latex.render_answers_tex(onayli, baslik),
            file_name="cevap_anahtari.tex",
        )
        try:
            hedef = Path(tempfile.gettempdir()) / "sinav.pdf"
            latex.build_pdf(latex.render_exam_tex(onayli, baslik), hedef)
            st.download_button(
                "Sınav kağıdı (.pdf)", data=hedef.read_bytes(), file_name="sinav.pdf"
            )
        except latex.LatexNotAvailable:
            st.caption("PDF için sistemde `pdflatex` kurulu olmalı; şimdilik .tex indirin.")


def sekme_ogrenciler() -> None:
    st.header("Öğrenciler")
    st.info("Öğrenci sayfaları Faz 3'te devreye girecek.")


def main() -> None:
    st.set_page_config(page_title="Questioncrator", layout="wide")
    conn = _conn()
    havuz, kartlar, ogrenciler = st.tabs(["Havuz", "Soru Önerileri", "Öğrenciler"])
    with havuz:
        sekme_havuz(conn)
    with kartlar:
        sekme_kartlar(conn)
    with ogrenciler:
        sekme_ogrenciler()


main()
```

- [ ] **Adım 6: Uygulamayı elle çalıştır ve akışı doğrula**

```bash
streamlit run questioncrator/app/main.py
```

Kontrol listesi:
1. Havuz sekmesinde `tests/data/ornek_havuz.md` dosyasını yükle → "4 soru okundu, 3 şablon çıkarıldı."
2. Soru Önerileri sekmesinde "Yeni öneriler üret" → kart görünüyor, soru metninde `{p0}` gibi yer tutucu **yok**.
3. İki kaydırıcıyı oynat, "Onayla" → sonraki karta geçiyor.
4. Aynı şablondan ikinci onaydan sonra "Şablon durumu güncellendi" bildirimi çıkıyor.
5. Onaylı sorular sayacı artıyor, `.tex` indirme düğmeleri çalışıyor.

Sorun çıkarsa `questioncrator.db` dosyasını silip tekrar dene (şema değişikliği sonrası eski dosya kalmış olabilir).

- [ ] **Adım 7: Commit**

```bash
git add questioncrator/app tests/test_app_state.py
git commit -m "feat: Streamlit uygulaması — havuz ve kart akışı sekmeleri"
```

---

### Görev 11: LLM soyutlaması (Faz 2 için sözleşme)

Faz 1'de hiçbir LLM çağrısı yapılmaz. Buradaki tek amaç, Faz 2'nin dayanacağı arayüzü şimdiden sabitlemek ve boru hattının LLM'siz de çalıştığını `NullLLMClient` ile göstermek.

**Files:**
- Create: `questioncrator/llm/__init__.py`
- Create: `questioncrator/llm/client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `llm.client.LLMClient` (Protocol) — `complete(prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str`
  - `llm.client.NullLLMClient` — her çağrıda `LLMNotConfigured` yükseltir
  - `llm.client.LLMNotConfigured(RuntimeError)`
  - `llm.client.FewShotExample(question_text, answer_latex, quality)`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_llm_client.py`:
```python
from __future__ import annotations

import pytest

from questioncrator.llm import client


def test_null_istemci_cagrilirsa_hata_verir():
    with pytest.raises(client.LLMNotConfigured):
        client.NullLLMClient().complete("merhaba")


def test_null_istemci_protokole_uyuyor():
    assert isinstance(client.NullLLMClient(), client.LLMClient)


def test_sahte_istemci_de_protokole_uyuyor():
    class Sahte:
        def complete(self, prompt, *, system=None, max_tokens=1024):
            return "cevap"

    assert isinstance(Sahte(), client.LLMClient)
    assert Sahte().complete("x") == "cevap"


def test_fewshot_ornegi_puani_tasir():
    ornek = client.FewShotExample(question_text="soru", answer_latex="x", quality=9)
    assert ornek.quality == 9
```

- [ ] **Adım 2: Testin başarısız olduğunu doğrula**

Run: `pytest tests/test_llm_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'questioncrator.llm'`

- [ ] **Adım 3: Uygulamayı yaz**

`questioncrator/llm/__init__.py`:
```python
"""LLM katmanı (A5) — Faz 1'de yalnız sözleşme."""
```

`questioncrator/llm/client.py`:
```python
"""LLM istemcisi sözleşmesi.

Faz 1 hiçbir LLM çağrısı yapmaz; boru hattı bu katman olmadan da uçtan
uca çalışır. Sağlayıcı seçimi Faz 2'ye ertelenmiştir — o zaman bu
protokolü uygulayan somut bir sınıf eklemek yeterli olacaktır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMNotConfigured(RuntimeError):
    """LLM sağlayıcısı seçilmediği hâlde bir LLM çağrısı denendi."""


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> str: ...


class NullLLMClient:
    """Faz 1 varsayılanı: çağrılırsa net bir hata verir, sessizce boş dönmez."""

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> str:
        raise LLMNotConfigured(
            "LLM sağlayıcısı yapılandırılmadı; Faz 1 boru hattı LLM'siz çalışır"
        )


@dataclass(frozen=True)
class FewShotExample:
    """Faz 2'de isteme eklenecek örnek: hocanın yüksek kurgu puanı verdiği onaylı soru."""

    question_text: str
    answer_latex: str
    quality: int
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `pytest -q && ruff check .`
Expected: tüm test dosyaları yeşil, ruff temiz. Bu, Faz 1'in bütünlük kontrolüdür —
tek tek görevler geçerken bütün başarısız oluyorsa aradaki sözleşme kırılmıştır.

- [ ] **Adım 5: Commit ve Faz 1 etiketi**

```bash
git add questioncrator/llm tests/test_llm_client.py
git commit -m "feat: LLM istemcisi sözleşmesi ve NullLLMClient"
git tag faz1
git push -u origin master --tags
```

---

## Faz 1 Bitiş Kontrolü

Bu görevler bittiğinde şunlar doğrulanmış olmalıdır:

- [ ] `pytest -q` tamamen yeşil, `ruff check .` temiz.
- [ ] `tests/test_topic_agnostic.py` geçiyor — kaynak kodda hiçbir konu adı yok, üç farklı konu aynı boru hattından geçiyor.
- [ ] `streamlit run questioncrator/app/main.py` ile Görev 10 Adım 6'daki beş maddelik elle kontrol listesi tamamlanmış.
- [ ] Deneme modu gözlemlenmiş: yeni şablondan bir partide en fazla 2 kart çıkıyor.
- [ ] `.tex` çıktıları LaTeX'te derleniyor (pdflatex kuruluysa `build_pdf` ile).

**Faz 1 sonrası kör test (tasarım §6).** Kod işi değildir, ölçüm işidir: hocanın 10 sorusu + sistemin 10 sorusu karıştırılıp hocaya verilir; hangisinin kime ait olduğunu ayırt edebiliyor mu, kurgu puanları arasında fark var mı ölçülür. Sonuç `docs/olcumler/faz1-kor-test.md` altına yazılır.

---

## Faz 2-4 Taslağı

Detaylı planları, Faz 1 bitip kör test sonucu geldikten sonra ayrı belgeler olarak yazılacaktır. Buradaki liste yalnız kapsam sınırlarını çizer.

### Faz 2 — Öğrenme döngüsü + LLM katmanı

- **Few-shot seçimi.** `scoring/examples.py`: onaylı ve kurgu puanı yüksek sorulardan `FewShotExample` listesi üretir; kazanıma göre filtreler.
- **Şablon ağırlıklama.** `engine.generate_batch` içindeki eşit pay yerine skor ağırlıklı pay: `TemplateScore.approval_rate` ve `avg_quality` çarpımı ağırlık olur.
- **Zorluk kalibrasyonu.** `Template`'e `difficulty_offset` alanı eklenir. Sistem hedef zorluğu ile hocanın verdiği puanın ortalama sapması hesaplanır; sistematikse parametre aralıkları (`Parameter.low/high`) kaydırılır.
- **Somut LLM istemcisi.** `llm/client.py`'deki protokolü uygulayan sağlayıcı sınıfı. Sağlayıcı seçimi bu fazın ilk kararı.
- **Giydirme + çeldirici.** `llm/dressing.py`: parametrik soruyu gerçek hayat bağlamına giydirir; çoktan seçmeli için çeldirici üretir. Çıktı yine `checks.verify`'den geçer — LLM doğrulayıcıyı atlayamaz.
- **Varyant keşfi.** `templating/extract.py`'nin LLM destekli ikinci yolu: aynı kazanımı ölçen yapısal olarak farklı reçeteler önerir.
- **Word çıktısı.** `export/docx.py`, `python-docx` ile.
- **Dağılımlı dosya oluşturma.** Tasarım §1'deki "20 soru, ağırlık şu kazanım, orta zorluk" isteği. Faz 1 tüm onaylıları basar; burada kazanım/zorluk kotalarına göre seçim yapan `export/selection.py` eklenir — girdisi `TemplateScore.avg_difficulty` ve hocanın verdiği zorluk puanlarıdır.

### Faz 3 — Serbest format alımı + öğrenci sayfaları

- **Alım genişlemesi.** `ingest/` altına `docx.py`, `pdf.py`, `latex.py`, `ocr.py` (Mathpix). Hepsi `parse_pool` ile aynı imzayı döndürür.
- **Belirsiz format için LLM ayrıştırma.** Düşük güvenli çıktılar `needs_review=True` ile "elle kontrol" kuyruğuna.
- **Öğrenci şeması.** `students` tablosu: `{id, alias, weak_objectives}`; `generated_questions`'a `student_id` sütunu. Not/sonuç alanı **eklenmez** (gizlilik kararı).
- **Sekme 3.** Öğrenci ekleme, zayıf kazanım işaretleme, öğrenciye özel üretim, çalışma kağıdı indirme.
- **Tekrar filtresi.** Öğrenciye verilmiş soruların cevap anahtarları + aynı şablondan yakın komşular; yapısal benzerlik eşiği.

### Faz 4 — Ölçek ve genelleme

- Tam havuzun yüklenmesi, performans profili.
- Gerekirse `sqlite-vec` + `sentence-transformers` ile anlamsal kopya kontrolü (şu anki `srepr` eşitliği tam kopyayı yakalar, yakın kopyayı yakalamaz).
- İkinci ders ile genelleme sınaması — konu bağımsızlığı iddiasının gerçek testi.
