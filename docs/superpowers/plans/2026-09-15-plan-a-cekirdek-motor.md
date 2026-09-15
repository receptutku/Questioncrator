# Plan A — Çekirdek Motor + Güvenlik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faz 1 çekirdeğini ürün v1 spec'inin istediği tam, güvenli, konu bağımsız kütüphaneye tamamlamak: sertleştirilmiş reçete dili, izole değerlendirme süreci, şema v2 + göçler, düzgün metin render'ı, doğrulayıcı, zorluk tahmini, çeldiriciler, öğrenme döngüsü skorları, ağırlıklı üretim motoru, kitapçık + LaTeX + Word çıktısı.

**Architecture:** Saf Python kütüphanesi (`questioncrator/`), HTTP bilmez. Her modül tek sorumluluk taşır ve `conn`, `rng`, `now`, `id_factory` gibi bağımlılıkları dışarıdan alır. Bu plan bittiğinde API/arayüz yoktur (Plan B/C); tüm davranış pytest ile kanıtlanır.

**Tech Stack:** Python 3.11+, SymPy, sqlite3, Jinja2, python-docx, latex2mathml, mathml2omml, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-15-urun-v1-design.md` (önceki: `docs/tasarim-v0.5.md`, Faz 1 planı `docs/superpowers/plans/2026-08-13-faz1-cekirdek-kart-akisi.md` — o planın Task 6-9 içerikleri bu plana birleştirilmiştir; Task 10 (Streamlit) ve Task 11 iptal/Plan B'ye taşındı).

## Global Constraints

- **Konu bağımsızlığı (ihlal edilemez).** `questioncrator/**/*.py` içinde hiçbir konuya özel dal, sabit, isim veya yorum yok. Yasak kelimeler (küçük harf alt dize taraması, yorumlar dahil): `turev`, `türev`, `limit`, `integral`, `matris`, `determinant`, `polinom`. Bekçi test: `tests/test_topic_agnostic.py`.
- **Python 3.11+.** Kod içeren her modülde `from __future__ import annotations` (docstring'den sonra ilk satır). Yalnız docstring içeren `__init__.py` muaf.
- **Dil:** Kullanıcıya görünen dizeler, docstring ve yorumlar Türkçe; `questioncrator/` altındaki tüm kod tanımlayıcıları (yerel değişkenler dahil) İngilizce. `tests/` altında Türkçe test adları/yerel adlar serbest.
- **Rastgelelik enjekte edilir:** üretim yapan fonksiyonlar `rng: random.Random` alır; global `random` çağrısı yok.
- **Zaman enjekte edilir:** `created_at` üreten fonksiyonlar ISO-8601 `now: str` alır.
- **Kimlikler enjekte edilir:** yeni kayıt kimliği üreten fonksiyonlar `id_factory: Callable[[], str]` alır; biçim `önek_12onaltılık` (`questioncrator.ids.new_id`).
- **Puanlar 1-10 tam sayı**, veritabanında `CHECK` ile.
- **Komutlar:** `.venv/bin/pytest -q` ve `.venv/bin/ruff check .` her task sonunda yeşil. (Depo kökünde `.venv` mevcut.)
- **Commit mesajları** Türkçe, conventional biçim (`feat:`, `fix:`, `refactor:`, `test:`); **Co-Authored-By veya başka iz satırı eklenmez.**

---

## Dosya Yapısı

```
questioncrator/
  ids.py                     YENİ  new_id(prefix, rng=None)
  mathenv.py                 DEĞİŞ jeton denetimi, DENIED_NAMES, modülsüz ad alanı
  sandbox.py                 YENİ  izole işçi süreçler, zaman aşımında öldürme
  models.py                  DEĞİŞ yeni alanlar + Student, Exam, FewShotExample
  db.py                      DEĞİŞ göçler (user_version), v2 şema, yeni CRUD
  ingest/markdown.py         DEĞİŞ `### Çözüm` başlığı -> answer_text
  templating/render.py       DEĞİŞ güvenli yer tutucu + işaret/katsayı sadeleştirme
  templating/extract.py      DEĞİŞ difficulty_estimate doldurulur (Task 6)
  verification/__init__.py   YENİ
  verification/checks.py     YENİ  verify(), VerificationResult
  generation/difficulty.py   YENİ  estimate_difficulty()
  generation/distractors.py  YENİ  build_choices()
  generation/engine.py       YENİ  GenerationRequest, generate_from_template, generate_batch
  scoring/__init__.py        YENİ
  scoring/store.py           YENİ  record_review, template_scores, apply_status_transitions
  scoring/weights.py         YENİ  template_weight()
  scoring/calibration.py     YENİ  workspace_bias, calibrated_difficulty, difficulty_deviation
  scoring/stats.py           YENİ  learning_stats()
  scoring/examples.py        YENİ  few_shot_examples()
  export/__init__.py         YENİ
  export/booklet.py          YENİ  build_booklets, answer_key
  export/text.py             YENİ  split_math(), metin/matematik parçalama
  export/latex.py            YENİ  render_exam_tex, render_answers_tex
  export/docx.py             YENİ  render_exam_docx
  export/templates/exam.tex.j2, answers.tex.j2
tests/
  conftest.py                YENİ  QC_SANDBOX=inline varsayılanı
  test_mathenv.py (+), test_sandbox.py, test_db.py (+), test_ids.py, test_render.py,
  test_ingest_markdown.py (+), test_verification.py, test_topic_agnostic.py,
  test_difficulty.py, test_distractors.py, test_engine.py, test_scoring.py,
  test_export_booklet.py, test_export_latex.py, test_export_docx.py
```

---

### Task 1: Reçete dilini sertleştir (RCE kapatma)

Doğrulanmış açık: `parse('sympify("_"+"_imp"+"ort_"+"_(\'os\').getcwd()")')` bugün `os.getcwd()` çalıştırıyor (sonuç hata mesajında görünüyor). Sebep: ad alanındaki `sympify`, kendi (builtins'li) ad alanıyla ikinci bir eval yapıyor; dizge birleştirme `__`/`import` alt dize filtresini atlatıyor.

**Files:**
- Modify: `questioncrator/mathenv.py`
- Test: `tests/test_mathenv.py` (mevcut testler korunur, yenileri eklenir)

**Interfaces:**
- Produces:
  - `mathenv.UnsafeExpression(ValueError)` (mevcut)
  - `mathenv.MAX_RECIPE_LENGTH = 2000`, `mathenv.MAX_NUMBER_DIGITS = 12`
  - `mathenv.DENIED_NAMES: frozenset[str]`, `mathenv.DENIED_PREFIXES: tuple[str, ...]`
  - `mathenv.check_recipe(recipe: str) -> None` — ihlalde `UnsafeExpression`
  - `mathenv.parse(recipe) -> sympy.Basic`, `mathenv.parse_with_timeout(recipe, seconds=5.0)` (imzalar aynı)

- [ ] **Adım 1: Başarısız testleri ekle** (`tests/test_mathenv.py` sonuna)

```python
import types

import pytest

from questioncrator import mathenv


@pytest.mark.parametrize(
    "recete",
    [
        'sympify("_"+"_imp"+"ort_"+"_(\'os\').getcwd()")',
        'S("x")',
        '"abc"',
        "f'{x}'",
        "x.__class__",
        "_x + 1",
        "lambda: 1",
        "[i for i in range(3)]",
        "preview(x)",
        "plot(x)",
        "print_latex(x)",
        "lambdify(x, x)",
        "var(x)",
        "init_session()",
        "exec(x)",
        "open(x)",
        "getattr(x, x)",
        "(y := 3)",
        "1" + "0" * 12,
        "x + " * 600 + "x",
    ],
)
def test_tehlikeli_recete_reddedilir(recete):
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(recete)


def test_kacis_denemesi_kod_calistirmiyor(tmp_path, monkeypatch):
    # Kaçış çalışsaydı dosya oluşurdu.
    hedef = tmp_path / "izi"
    recete = 'sympify("_"+"_imp"+"ort_"+"_(\'os\').mkdir(\'' + str(hedef) + '\')")'
    with pytest.raises(mathenv.UnsafeExpression):
        mathenv.parse(recete)
    assert not hedef.exists()


def test_ad_alaninda_modul_ve_yasakli_ad_yok():
    ad_alani = mathenv._allowed_namespace()
    assert not [ad for ad, deger in ad_alani.items() if isinstance(deger, types.ModuleType)]
    assert not (set(ad_alani) & mathenv.DENIED_NAMES)
    assert not [ad for ad in ad_alani if ad != "__builtins__" and ad.startswith(mathenv.DENIED_PREFIXES)]


def test_modul_adi_otomatik_sembole_duser_ve_alt_modul_erisilemez():
    # `utilities` bir sympy modülüdür; ad alanında olmadığı için Symbol olur.
    with pytest.raises(Exception) as bilgi:
        mathenv.parse("utilities.lambdify")
    assert not isinstance(bilgi.value, SystemExit)


@pytest.mark.parametrize(
    "recete",
    [
        "diff(3*x**2 + 5*x - 2, x)",
        "Matrix([[2, 1], [4, 3]]).det()",
        "Rational(1, 3) + 2",
        "solve(2*y + 6, y)",
        "x < 3",
        "sqrt(8) and True",
        "123456789012",
        "3.25*x",
    ],
)
def test_mesru_receteler_calismaya_devam_eder(recete):
    mathenv.parse(recete)
```

- [ ] **Adım 2: Testlerin başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_mathenv.py -q`
Expected: FAIL — `AttributeError: module 'questioncrator.mathenv' has no attribute 'DENIED_NAMES'` ve kaçış testlerinde `UnsafeExpression` yükselmemesi.

- [ ] **Adım 3: Uygulamayı yaz** — `questioncrator/mathenv.py` içinde mevcut `parse`, `_normalize`, `parse_with_timeout` korunur; aşağıdakiler eklenir/değişir:

```python
import functools
import io
import keyword
import re
import tokenize
import types

MAX_RECIPE_LENGTH = 2000
MAX_NUMBER_DIGITS = 12

# İkincil koruma: yan etkili ya da ikinci bir eval açan sympy adları.
# Birincil koruma dizge yasağı + alt çizgi yasağıdır (bkz. check_recipe).
DENIED_NAMES = frozenset(
    {
        "sympify", "S", "parse_expr", "lambdify", "preview", "init_printing",
        "init_session", "var", "pprint", "pretty_print", "pager_print",
        "interactive_traversal", "textplot", "dotprint", "test", "doctest",
        "exec", "eval", "open", "compile", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "input", "help", "breakpoint", "exit", "quit",
    }
)
DENIED_PREFIXES = ("_", "plot", "print_", "pprint")
_ALLOWED_KEYWORDS = frozenset({"True", "False", "None", "and", "or", "not", "in", "is"})


def check_recipe(recipe: str) -> None:
    """Reçeteyi değerlendirmeden önce jeton düzeyinde denetler.

    Reçete dili yalnız sayı, ad, işlem ve parantezden oluşur: dizge,
    alt çizgiyle başlayan ad, anahtar sözcük (mantıksal olanlar hariç)
    ve atama ifadesi yasaktır.
    """
    if len(recipe) > MAX_RECIPE_LENGTH:
        raise UnsafeExpression(f"reçete {MAX_RECIPE_LENGTH} karakterden uzun")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(recipe).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise UnsafeExpression("reçete jetonlara ayrılamadı") from exc
    for token in tokens:
        kind = tokenize.tok_name.get(token.type, "")
        if token.type == tokenize.STRING or kind.startswith("FSTRING"):
            raise UnsafeExpression("dizge içeren reçete reddedildi")
        if token.type == tokenize.OP and token.string == ":=":
            raise UnsafeExpression("atama içeren reçete reddedildi")
        if token.type == tokenize.NUMBER:
            if len(re.sub(r"[^0-9]", "", token.string)) > MAX_NUMBER_DIGITS:
                raise UnsafeExpression("çok büyük sayı literali reddedildi")
        if token.type == tokenize.NAME:
            name = token.string
            if keyword.iskeyword(name) and name not in _ALLOWED_KEYWORDS:
                raise UnsafeExpression(f"`{name}` içeren reçete reddedildi")
            if name in DENIED_NAMES or name.startswith(DENIED_PREFIXES):
                raise UnsafeExpression(f"`{name}` adı reçetede kullanılamaz")


@functools.cache
def _base_namespace() -> dict[str, object]:
    namespace: dict[str, object] = {}
    for name in sympy.__all__:
        if name in DENIED_NAMES or name.startswith(DENIED_PREFIXES):
            continue
        value = getattr(sympy, name)
        if isinstance(value, types.ModuleType):
            continue
        namespace[name] = value
    return namespace


def _allowed_namespace() -> dict[str, object]:
    ns = dict(_base_namespace())
    ns["__builtins__"] = {}
    return ns
```

`parse` içinde mevcut iki alt dize kontrolünden sonra `check_recipe(recipe)` çağrılır (eski kontroller geriye dönük test uyumu için kalır). `parse_expr` çağrısı `global_dict=_allowed_namespace()` ile aynen sürer.

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: tüm testler PASS (eski 45 + yeniler), ruff temiz. Kaçış probunu elle de çalıştır:
`.venv/bin/python -c "from questioncrator.mathenv import parse; parse('sympify(\"_\"+\"_imp\"+\"ort_\"+\"_(\'os\').getcwd()\")')"` → `UnsafeExpression`, çıktıda dizin yolu **görünmemeli**.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/mathenv.py tests/test_mathenv.py
git commit -m "fix(mathenv): dizge/alt çizgi/yasak ad denetimiyle reçete kaçışını kapat"
```

---

### Task 2: İzole değerlendirme süreci (`sandbox.py`)

Süresi dolan SymPy iş parçacıkları öldürülemez; sunucuda CPU'yu kalıcı yer. Ağır işler kalıcı işçi süreçlerde koşar, süre aşılırsa işçi öldürülüp yenilenir.

**Files:**
- Create: `questioncrator/sandbox.py`
- Create: `tests/conftest.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Produces:
  - `sandbox.SandboxTimeout(Exception)`, `sandbox.SandboxCrashed(Exception)`
  - `sandbox.run(fn: Callable[..., T], *args, timeout: float, **kwargs) -> T` — `fn` modül düzeyinde (pickle'lanabilir) olmalı; `fn`'in yükselttiği istisna aynen yeniden yükseltilir (pickle'lanamıyorsa `SandboxCrashed(str(exc))`).
  - `sandbox.shutdown() -> None`
  - Ortam: `QC_SANDBOX` = `process` (varsayılan) | `inline`; `QC_SANDBOX_WORKERS` (varsayılan 2); `QC_SANDBOX_MEMORY_MB` (varsayılan 1024, yalnız Linux).

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/conftest.py`:
```python
from __future__ import annotations

import os

# Test paketinin geneli süreç içi çalışır (hız). Sandbox testleri kendi
# içinde `process` kipini açıkça seçer.
os.environ.setdefault("QC_SANDBOX", "inline")
```

`tests/test_sandbox.py`:
```python
from __future__ import annotations

import os
import time

import pytest

from questioncrator import sandbox


@pytest.fixture
def surec_kipi(monkeypatch):
    monkeypatch.setenv("QC_SANDBOX", "process")
    yield
    sandbox.shutdown()


def test_sonuc_surecten_doner(surec_kipi):
    assert sandbox.run(pow, 2, 10, timeout=20) == 1024


def test_is_ayri_surecte_calisir(surec_kipi):
    assert sandbox.run(os.getpid, timeout=20) != os.getpid()


def test_zaman_asiminda_isci_oldurulur_ve_yenilenir(surec_kipi):
    sandbox.run(pow, 1, 1, timeout=20)  # işçiyi ısıt
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxTimeout):
        sandbox.run(time.sleep, 30, timeout=0.5)
    assert time.monotonic() - baslangic < 5
    assert sandbox.run(pow, 3, 2, timeout=20) == 9


def test_istisna_aynen_yukselir(surec_kipi):
    with pytest.raises(ValueError):
        sandbox.run(int, "sayi-degil", timeout=20)


def test_isci_cokerse_hata_verir_ve_toparlanir(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(os._exit, 3, timeout=20)
    assert sandbox.run(pow, 2, 3, timeout=20) == 8


def test_inline_kip_ayni_surecte_calisir(monkeypatch):
    monkeypatch.setenv("QC_SANDBOX", "inline")
    assert sandbox.run(os.getpid, timeout=1) == os.getpid()


def guvensiz_recete_dener(recete: str) -> str:
    """İşçi süreçte çalışır: reçete reddedilirse istisna adını döndürür."""
    from questioncrator.mathenv import parse

    try:
        parse(recete)
    except Exception as exc:  # noqa: BLE001 — istisna adı ebeveyne taşınıyor
        return type(exc).__name__
    return "ISTISNA_YOK"


def test_isci_surecte_recete_bekcileri_etkin(surec_kipi):
    # Task 1'in sertleştirmesi işçi süreçte de kurulu olmalı: guard'lar
    # `questioncrator.mathenv` import edilirken kurulur, fork edilen işçide de.
    assert sandbox.run(guvensiz_recete_dener, 'sympify("x")', timeout=30) == "UnsafeExpression"
    assert sandbox.run(guvensiz_recete_dener, "nsolve(sin(x)-1, x, 1)", timeout=30) == "UnsafeExpression"
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"
```

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_sandbox.py -q`
Expected: FAIL — `ImportError: cannot import name 'sandbox'`

- [ ] **Adım 3: Uygulamayı yaz** — `questioncrator/sandbox.py`:

```python
"""Ağır ve güvenilmeyen SymPy işlerini ayrı süreçte, süre sınırıyla çalıştırır.

İş parçacığı zorla durdurulamaz; süresi dolan bir hesap sunucu sürecinde
sonsuza dek CPU yiyebilir. Bu yüzden çekirdek işler kalıcı işçi
süreçlerde koşar. Süre aşılırsa işçi öldürülür ve yerine yenisi açılır.
Bir iş, arkasında hâlâ çalışan yardımcı iş parçacığı bırakırsa işçi
sonucu gönderdikten sonra kendini kapatır (yenisi açılır).
"""

from __future__ import annotations

import atexit
import multiprocessing
import os
import pickle
import queue
import sys
import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_POOL_LOCK = threading.Lock()
_IDLE: queue.Queue[_Worker] | None = None
_ALL: list[_Worker] = []


class SandboxTimeout(Exception):
    """İş verilen sürede bitmedi; işçi öldürüldü."""


class SandboxCrashed(Exception):
    """İşçi süreç beklenmedik biçimde sonlandı ya da sonuç aktarılamadı."""


def _mode() -> str:
    return os.environ.get("QC_SANDBOX", "process")


def _worker_count() -> int:
    return max(1, int(os.environ.get("QC_SANDBOX_WORKERS", "2")))


def _limit_memory() -> None:
    if not sys.platform.startswith("linux"):
        return
    import resource

    limit = int(os.environ.get("QC_SANDBOX_MEMORY_MB", "1024")) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _serve(conn: Any) -> None:
    _limit_memory()
    while True:
        try:
            fn, args, kwargs = conn.recv()
        except EOFError:
            return
        try:
            payload: tuple[str, Any] = ("ok", fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 — her hata ebeveyne taşınır
            payload = ("err", exc)
        try:
            conn.send(payload)
        except (pickle.PicklingError, TypeError, AttributeError) as exc:
            conn.send(("crash", f"sonuç aktarılamadı: {exc}"))
        if threading.active_count() > 1:
            return  # arkada kaçak hesap kaldı: işçiyi yenile


class _Worker:
    def __init__(self) -> None:
        ctx = multiprocessing.get_context("spawn" if sys.platform == "win32" else "forkserver")
        if ctx.get_start_method() == "forkserver":
            ctx.set_forkserver_preload(["sympy", "questioncrator.mathenv"])
        self.conn, child = ctx.Pipe()
        self.process = ctx.Process(target=_serve, args=(child,), daemon=True)
        self.process.start()
        child.close()

    def kill(self) -> None:
        if self.process.is_alive():
            self.process.kill()
        self.process.join(timeout=5)
        self.conn.close()


def _pool() -> queue.Queue[_Worker]:
    global _IDLE
    with _POOL_LOCK:
        if _IDLE is None:
            _IDLE = queue.Queue()
            for _ in range(_worker_count()):
                worker = _Worker()
                _ALL.append(worker)
                _IDLE.put(worker)
        return _IDLE


def _replace(worker: _Worker) -> _Worker:
    worker.kill()
    fresh = _Worker()
    with _POOL_LOCK:
        if worker in _ALL:
            _ALL.remove(worker)
        _ALL.append(fresh)
    return fresh


def run(fn: Callable[..., T], *args: Any, timeout: float, **kwargs: Any) -> T:
    """`fn(*args, **kwargs)` sonucunu döndürür; süre aşılırsa `SandboxTimeout`."""
    if _mode() == "inline":
        return fn(*args, **kwargs)

    idle = _pool()
    try:
        worker = idle.get(timeout=timeout)
    except queue.Empty as exc:
        raise SandboxTimeout("boş değerlendirme işçisi bulunamadı") from exc

    try:
        if not worker.process.is_alive():
            worker = _replace(worker)
        worker.conn.send((fn, args, kwargs))
        if not worker.conn.poll(timeout):
            worker = _replace(worker)
            raise SandboxTimeout(f"iş {timeout} saniyede bitmedi")
        try:
            status, value = worker.conn.recv()
        except (EOFError, OSError) as exc:
            worker = _replace(worker)
            raise SandboxCrashed("değerlendirme süreci beklenmedik biçimde kapandı") from exc
        if not worker.process.is_alive() or status == "crash":
            worker.process.join(timeout=1)
            worker = _replace(worker)
        if status == "ok":
            return value
        if status == "crash":
            raise SandboxCrashed(value)
        raise value
    finally:
        idle.put(worker)


def shutdown() -> None:
    """Tüm işçileri kapatır (testler ve süreç çıkışı için)."""
    global _IDLE
    with _POOL_LOCK:
        for worker in _ALL:
            worker.kill()
        _ALL.clear()
        _IDLE = None


atexit.register(shutdown)
```

Not (uygulayıcıya): İşçi `_serve` sonucu gönderip `threading.active_count() > 1` ile çıkarsa ebeveyn bir sonraki `run` başında `is_alive()` kontrolüyle yeniler; yukarıdaki `recv` sonrası `is_alive` kontrolü yarış durumuna göre bunu hemen de yakalayabilir — ikisi de doğru sonuç verir. `os._exit` testi `recv`'de `EOFError` üretir. Uygulama sırasında bu akışlardan birinde hata bulursan davranışı (sonuç + yenileme) koruyarak düzelt ve raporda belirt.

- [ ] **Adım 4: Testleri çalıştır**

Run: `.venv/bin/pytest tests/test_sandbox.py -q && .venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: 7 passed; tüm paket yeşil.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/sandbox.py tests/conftest.py tests/test_sandbox.py
git commit -m "feat(sandbox): süre sınırlı izole değerlendirme işçileri"
```

---

### Task 3: Kimlikler, model alanları, şema v2 ve göçler

**Files:**
- Create: `questioncrator/ids.py`, `tests/test_ids.py`
- Modify: `questioncrator/models.py`, `questioncrator/db.py`
- Test: `tests/test_db.py` (mevcut testler korunur; pozisyonel INSERT beklentisi yoksa değişmez)

**Interfaces:**
- Produces:
  - `ids.new_id(prefix: str, rng: random.Random | None = None) -> str` → `"q_0123456789ab"`
  - `models.SourceQuestion` + `answer_text: str | None = None`, `origin: str = "markdown"`, `review_note: str | None = None`, `created_at: str = ""`
  - `models.Template` + `difficulty_estimate: float = 5.0`
  - `models.GeneratedQuestion` + `choices: tuple[str, ...] = ()`, `correct_index: int | None = None`, `difficulty_estimate: float = 5.0`, `student_id: str | None = None`, `created_by: str | None = None`, `archived: bool = False`, `similar_given: bool = False`
  - `models.Review` + `reviewer_id: str | None = None`
  - `models.Student(id, alias, weak_objectives: tuple[str, ...] = (), level: int | None = None, created_at: str = "", archived: bool = False)`
  - `models.Exam(id, title, kind: str = "exam", question_ids: tuple[str, ...] = (), settings: dict[str, object] = {}, student_id: str | None = None, created_by: str | None = None, created_at: str = "")`
  - `models.FewShotExample(question_text: str, answer_latex: str, quality: int, objective: str | None = None)`
  - `db.SCHEMA_VERSION = 2`, `db.migrate(conn)`, `db.connect(path, *, check_same_thread=True)`
  - Kaynak: `save_source`, `load_sources`, `get_source(conn, id) -> SourceQuestion | None`, `delete_source(conn, id)` (şablonlarını `disabled` yapar)
  - Şablon: `save_template`, `load_templates`, `get_template`, `load_templates_for_source(conn, source_id)`, `set_template_status`
  - Soru: `save_question`, `load_questions(conn, *, include_archived=True)`, `get_question`, `set_question_archived(conn, id, archived: bool)`, `load_answer_keys`
  - Değerlendirme: `save_review`, `load_reviews`, `get_review`, `delete_review`
  - Öğrenci: `save_student`, `load_students(conn, *, include_archived=False)`, `get_student`, `assign_questions(conn, student_id, question_ids, assigned_at)`, `load_student_question_ids(conn, student_id) -> set[str]`, `load_student_template_ids(conn, student_id) -> set[str]`
  - Sınav: `save_exam`, `load_exams(conn, *, student_id=None)` (en yeni önce), `get_exam`, `delete_exam`
  - Tüm `save_*` fonksiyonları `INSERT ... ON CONFLICT(id) DO UPDATE` (upsert) ve adlandırılmış sütun listesi kullanır; her biri `commit` eder.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_ids.py`:
```python
from __future__ import annotations

import random
import re

from questioncrator.ids import new_id


def test_bicim():
    assert re.fullmatch(r"q_[0-9a-f]{12}", new_id("q"))


def test_rng_ile_deterministik():
    assert new_id("s", random.Random(1)) == new_id("s", random.Random(1))


def test_rngsiz_benzersiz():
    assert len({new_id("t") for _ in range(200)}) == 200
```

`tests/test_db.py` sonuna eklenecek testler:
```python
import sqlite3 as _sqlite3

from questioncrator.models import Exam, Student


def test_yeni_veritabani_son_surumde(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tablolar = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"students", "student_questions", "exams"} <= tablolar


def test_v1_dosyasi_veri_kaybetmeden_goc_eder(tmp_path):
    yol = tmp_path / "eski.db"
    ham = _sqlite3.connect(yol)
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
    with pytest.raises(_sqlite3.IntegrityError):
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
    with pytest.raises(_sqlite3.IntegrityError):
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
```

(Dosyanın başındaki mevcut importlar `pytest`, `db`, `GeneratedQuestion`, `Parameter`, `Review`, `SourceQuestion`, `Template` içerir; eksik olanı ekle. Mevcut `conn` fikstürü `db.connect(":memory:")` kullanır.)

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_ids.py tests/test_db.py -q`
Expected: FAIL — `ModuleNotFoundError: questioncrator.ids`, `ImportError: Exam`.

- [ ] **Adım 3: `ids.py` ve `models.py`**

`questioncrator/ids.py`:
```python
"""Kayıt kimlikleri: `önek_12onaltılık`.

Sıra numarası yerine rastgele kimlik kullanılır: aynı çalışma alanında
iki hoca aynı anda üretim yaptığında çakışma olmaz.
"""

from __future__ import annotations

import random
import secrets


def new_id(prefix: str, rng: random.Random | None = None) -> str:
    bits = rng.getrandbits(48) if rng is not None else secrets.randbits(48)
    return f"{prefix}_{bits:012x}"
```

`questioncrator/models.py`: Interfaces bloğundaki alanları ekle (hepsi varsayılanlı, mevcut alanların **sonuna**). `Exam.settings` için `field(default_factory=dict)`. Yeni sınıflar `@dataclass(frozen=True)` ve Türkçe docstring'li:
- `Student`: "Hocanın rumuzla eklediği öğrenci. Not/sonuç tutulmaz (gizlilik kararı)."
- `Exam`: "Onaylı sorulardan oluşturulmuş sınav ya da öğrenciye özel çalışma kağıdı."
- `FewShotExample`: "LLM istemine eklenecek örnek: hocanın yüksek kurgu puanı verdiği onaylı soru."

- [ ] **Adım 4: `db.py` yeniden yaz**

```python
"""Çalışma alanı veritabanı: şema göçleri ve kaydet/yükle fonksiyonları.

Her çalışma alanı (dershane) kendi SQLite dosyasındadır; bu modül kiracı
kavramını bilmez. Karmaşık alanlar JSON metin sütunlarında saklanır.
Şema `PRAGMA user_version` ile sürümlenir; `MIGRATIONS` yalnız sona
eklenerek büyür, var olan bir göç asla değiştirilmez.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
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
ALTER TABLE generated_questions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
ALTER TABLE generated_questions ADD COLUMN similar_given INTEGER NOT NULL DEFAULT 0;

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


def migrate(conn: sqlite3.Connection) -> None:
    """Eksik göçleri sırayla, her birini tek işlemde uygular."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version in range(current + 1, SCHEMA_VERSION + 1):
        script = f"BEGIN;\n{MIGRATIONS[version - 1]}\nPRAGMA user_version = {version};\nCOMMIT;"
        try:
            conn.executescript(script)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def connect(
    path: str | Path = "questioncrator.db", *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Bağlantı açar, göçleri uygular.

    `check_same_thread=False` bağlantının başka bir iş parçacığında
    kullanılacağı durumlar içindir (ör. web çerçevesinin iş havuzu).
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # PRAGMA'lar işlem dışında verilmelidir; göçten önce.
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def _upsert(conn: sqlite3.Connection, table: str, key: str, row: dict[str, object]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    updates = ", ".join(f"{c} = excluded.{c}" for c in row if c != key)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT({key}) DO UPDATE SET {updates}",
        tuple(row.values()),
    )
    conn.commit()


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
    rows = conn.execute("SELECT * FROM source_questions ORDER BY created_at, id").fetchall()
    return [_source(r) for r in rows]


def get_source(conn: sqlite3.Connection, source_id: str) -> SourceQuestion | None:
    r = conn.execute("SELECT * FROM source_questions WHERE id = ?", (source_id,)).fetchone()
    return _source(r) if r else None


def delete_source(conn: sqlite3.Connection, source_id: str) -> None:
    """Kaynağı siler; şablonları üretilmiş soruları korumak için silinmez, kapatılır."""
    conn.execute("UPDATE templates SET status = 'disabled' WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM source_questions WHERE id = ?", (source_id,))
    conn.commit()


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
    return [_template(r) for r in conn.execute("SELECT * FROM templates ORDER BY id")]


def get_template(conn: sqlite3.Connection, template_id: str) -> Template | None:
    r = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    return _template(r) if r else None


def load_templates_for_source(conn: sqlite3.Connection, source_id: str) -> list[Template]:
    rows = conn.execute("SELECT * FROM templates WHERE source_id = ? ORDER BY id", (source_id,))
    return [_template(r) for r in rows]


def set_template_status(conn: sqlite3.Connection, template_id: str, status: str) -> None:
    conn.execute("UPDATE templates SET status = ? WHERE id = ?", (status, template_id))
    conn.commit()


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
    rows = conn.execute(f"SELECT * FROM generated_questions {where} ORDER BY created_at, id")
    return [_question(r) for r in rows]


def get_question(conn: sqlite3.Connection, question_id: str) -> GeneratedQuestion | None:
    r = conn.execute("SELECT * FROM generated_questions WHERE id = ?", (question_id,)).fetchone()
    return _question(r) if r else None


def set_question_archived(conn: sqlite3.Connection, question_id: str, archived: bool) -> None:
    conn.execute(
        "UPDATE generated_questions SET archived = ? WHERE id = ?", (int(archived), question_id)
    )
    conn.commit()


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
    rows = conn.execute("SELECT * FROM reviews ORDER BY created_at, question_id")
    return [_review(r) for r in rows]


def get_review(conn: sqlite3.Connection, question_id: str) -> Review | None:
    r = conn.execute("SELECT * FROM reviews WHERE question_id = ?", (question_id,)).fetchone()
    return _review(r) if r else None


def delete_review(conn: sqlite3.Connection, question_id: str) -> None:
    conn.execute("DELETE FROM reviews WHERE question_id = ?", (question_id,))
    conn.commit()


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
    return [_student(r) for r in conn.execute(f"SELECT * FROM students {where} ORDER BY alias, id")]


def get_student(conn: sqlite3.Connection, student_id: str) -> Student | None:
    r = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return _student(r) if r else None


def assign_questions(
    conn: sqlite3.Connection, student_id: str, question_ids: Iterable[str], assigned_at: str
) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO student_questions (student_id, question_id, assigned_at) "
        "VALUES (?, ?, ?)",
        [(student_id, qid, assigned_at) for qid in question_ids],
    )
    conn.commit()


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
        rows = conn.execute("SELECT * FROM exams ORDER BY created_at DESC, id")
    else:
        rows = conn.execute(
            "SELECT * FROM exams WHERE student_id = ? ORDER BY created_at DESC, id", (student_id,)
        )
    return [_exam(r) for r in rows]


def get_exam(conn: sqlite3.Connection, exam_id: str) -> Exam | None:
    r = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    return _exam(r) if r else None


def delete_exam(conn: sqlite3.Connection, exam_id: str) -> None:
    conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    conn.commit()
```

- [ ] **Adım 5: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: tüm testler PASS. (`_upsert`'teki f-string SQL yalnız kod içi sabit tablo/sütun adlarını birleştirir; kullanıcı girdisi değer olarak `?` ile bağlanır. Ruff `S608` seçili değil.)

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/ids.py questioncrator/models.py questioncrator/db.py tests/test_ids.py tests/test_db.py
git commit -m "feat(db): şema v2, sürümlü göçler, öğrenci/sınav tabloları ve rastgele kimlikler"
```

---

### Task 4: Metin render düzeltmeleri + `### Çözüm` alımı

Doğrulanmış hatalar: `render_text` LaTeX'li metinde `KeyError: 'x \\to 0'`; negatif değerlerde `3x^2 + -4x - -4`.

**Files:**
- Modify: `questioncrator/templating/render.py`, `questioncrator/ingest/markdown.py`
- Test: `tests/test_render.py` (yeni), `tests/test_ingest_markdown.py` (ekleme)

**Interfaces:**
- Produces: `render.render_text(template, bindings) -> str` (imza aynı, davranış düzeldi), `render.render_recipe` (değişmez); `markdown.parse_pool` artık `### Çözüm` gövdesini `answer_text`'e yazar, `origin="markdown"`.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_render.py`:
```python
from __future__ import annotations

import pytest

from questioncrator.models import Parameter, Template
from questioncrator.templating.render import render_text


def sablon(iskelet: str, adet: int = 3) -> Template:
    return Template(
        id="t1", source_id="s1", skeleton=iskelet, recipe="{p0}",
        parameters=tuple(Parameter(f"p{i}", -9, 9, (0,)) for i in range(adet)),
    )


def test_latex_suslu_parantezleri_bozulmaz():
    t = sablon(r"$\lim_{x \to 0} \frac{\sin({p0}x)}{x}$ limitini hesaplayınız.", 1)
    assert render_text(t, {"p0": 4}) == r"$\lim_{x \to 0} \frac{\sin(4x)}{x}$ limitini hesaplayınız."


def test_cift_suslu_icinde_yer_tutucu():
    t = sablon(r"$\frac{{p0}}{x}$", 1)
    assert render_text(t, {"p0": 7}) == r"$\frac{7}{x}$"


@pytest.mark.parametrize(
    ("degerler", "beklenen"),
    [
        ((3, 5, 2), "f(x) = 3x^2 + 5x - 2"),
        ((-4, -4, -4), "f(x) = -4x^2 - 4x + 4"),
        ((1, -1, 5), "f(x) = x^2 - x - 5"),
        ((-1, 1, -1), "f(x) = -x^2 + x + 1"),
    ],
)
def test_isaret_ve_katsayi_sadelesir(degerler, beklenen):
    t = sablon("f(x) = {p0}x^2 + {p1}x - {p2}")
    assert render_text(t, dict(zip(["p0", "p1", "p2"], degerler, strict=True))) == beklenen


def test_esittir_sonrasi_eksi_eksi_arti_yazilmaz():
    t = sablon("y = -{p0}x", 1)
    assert render_text(t, {"p0": -3}) == "y = 3x"


def test_carpma_sonrasi_negatif_parantezlenir():
    t = sablon(r"2 \cdot {p0} ve 5 * {p1}", 2)
    assert render_text(t, {"p0": -3, "p1": -1}) == r"2 \cdot (-3) ve 5 * (-1)"


def test_liste_icinde_negatif_ve_bir_korunur():
    t = sablon("A = [[{p0}, {p1}], [{p2}, 2]]")
    assert render_text(t, {"p0": -4, "p1": 1, "p2": -1}) == "A = [[-4, 1], [-1, 2]]"


def test_eksik_baglama_hata_verir():
    with pytest.raises(KeyError):
        render_text(sablon("{p0}", 1), {})
```

`tests/test_ingest_markdown.py` sonuna:
```python
def test_cozum_basligi_answer_text_olur():
    icerik = "### Soru\nMetin\n\n### Cevap\n2*x\n\n### Çözüm\nCevap 2x olur.\n"
    (soru,) = markdown.parse_pool(icerik)
    assert soru.answer_text == "Cevap 2x olur."
    assert soru.recipe == "2*x"
    assert soru.origin == "markdown"
```

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_render.py tests/test_ingest_markdown.py -q`
Expected: FAIL (KeyError, işaret beklentileri, `answer_text is None`).

- [ ] **Adım 3: `render.py`**

```python
"""Şablon + bağlamadan soru metni ve çalıştırılabilir reçete üretir."""

from __future__ import annotations

import re

from questioncrator.models import Template

_PLACEHOLDER = re.compile(r"\{(p\d+)\}")
# Eksi işareti bunlardan sonra geliyorsa işaret değil, ifadenin başıdır.
_OPENERS = frozenset("=([{,;:$")
# Bunlardan sonra gelen negatif sayı parantez içine alınır.
_MULTIPLIERS = ("*", "/", "×", "·", "^", "\\cdot", "\\times")


def _append_number(text: str, value: int, is_coefficient: bool) -> str:
    magnitude = abs(value)
    body = "" if is_coefficient and magnitude == 1 else str(magnitude)
    if value >= 0:
        return text + body

    stripped = text.rstrip()
    gap = text[len(stripped):]
    if stripped.endswith("+"):
        return stripped[:-1] + "-" + gap + body
    if stripped.endswith("-"):
        before = stripped[:-1].rstrip()
        if not before or before[-1] in _OPENERS:
            return stripped[:-1] + body
        return stripped[:-1] + "+" + gap + body
    if stripped.endswith(_MULTIPLIERS):
        return text + f"(-{magnitude})"
    return text + "-" + body


def render_text(template: Template, bindings: dict[str, int]) -> str:
    """Hocaya ve öğrenciye görünecek soru metni.

    Yalnız `{pN}` yer tutucuları değiştirilir; metindeki diğer süslü
    parantezler (LaTeX) olduğu gibi kalır. Negatif değerlerde önceki
    işaret sadeleştirilir (`+ -4` -> `- 4`), bir harf ya da parantez
    önündeki 1 katsayısı yazılmaz (`1x` -> `x`).
    """
    skeleton = template.skeleton
    text = ""
    position = 0
    for match in _PLACEHOLDER.finditer(skeleton):
        text += skeleton[position:match.start()]
        position = match.end()
        following = skeleton[position:position + 1]
        is_coefficient = following.isalpha() or following in ("\\", "(")
        text = _append_number(text, bindings[match.group(1)], is_coefficient)
    return text + skeleton[position:]


def render_recipe(template: Template, bindings: dict[str, int]) -> str:
    """SymPy'ye verilecek reçete.

    Değerler parantezlenir: parantezsiz `-3**2` Python'da -9 verir, oysa
    kastedilen (-3)^2 = 9'dur.
    """
    return _PLACEHOLDER.sub(lambda m: f"({bindings[m.group(1)]})", template.recipe)
```

Not: `render_recipe` artık da `str.format` yerine regex kullanır; reçetede `{}` (Python set/dict literal) zaten anlamsızdır, davranış mevcut testlerle aynı kalmalıdır. `tests/test_templating.py` içindeki mevcut render testi bu değişiklikle geçmeye devam etmeli; geçmezse beklentiyi değil uygulamayı düzelt.

- [ ] **Adım 4: `markdown.py`** — `_HEADING` regex'ine `Çözüm` eklenir (`(Soru|Cevap|Çözüm|Kazanım)`), `SourceQuestion(...)` çağrısına `answer_text=fields.get("Çözüm") or None, origin="markdown"` eklenir; `parse_pool` docstring'i `### Çözüm` başlığını anlatacak şekilde güncellenir.

- [ ] **Adım 5: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Adım 6: Commit**

```bash
git add questioncrator/templating/render.py questioncrator/ingest/markdown.py tests/test_render.py tests/test_ingest_markdown.py
git commit -m "fix(render): LaTeX parantezleri, işaret ve katsayı sadeleştirme; Çözüm başlığı"
```

---

### Task 5: Doğrulayıcı (A6) + konu bağımsızlığı bekçisi

**Files:**
- Create: `questioncrator/verification/__init__.py` (`"""Doğrulama katmanı (A6)."""`), `questioncrator/verification/checks.py`
- Test: `tests/test_verification.py`, `tests/test_topic_agnostic.py`

**Interfaces:**
- Consumes: `mathenv.parse_with_timeout`, `mathenv.EvaluationTimeout`, `mathenv.UnsafeExpression`, `render.render_recipe`, `sampler.satisfies_constraints`
- Produces:
  - `checks.VerificationResult(ok: bool, answer: sympy.Basic | None, notes: tuple[str, ...])`
  - `checks.verify(template, bindings, *, timeout=5.0) -> VerificationResult`
  - `checks.evaluate_answer(recipe: str, *, timeout=5.0) -> sympy.Basic` (hata türlerini `ValueError` altında birleştirir: `checks.EvaluationFailed(ValueError)`)
  - `checks.answer_problems(answer: sympy.Basic, *, seed_answer_ops: int = 0) -> list[str]` — tanımsızlık, dejenerelik, sayı büyüklüğü, değerlendirilmemiş işlem, görsel uzunluk kontrolleri (çeldiriciler de kullanır)
  - `checks.MAX_NUMERATOR = 9999`, `checks.MAX_DENOMINATOR = 99`, `checks.MIN_OPS_RATIO = 0.5`, `checks.MAX_LATEX_LENGTH = 160`
- Not (controller, Task 2 sonrası): `EvaluationFailed` sandbox işçisinden ebeveyne taşınabilmesi için `questioncrator/wire.py` istisna kaydına eklenmeli (sabit sözlük ya da `register_exception`); bunu sabitleyen bir gidiş-dönüş testi `tests/test_wire.py`'ye eklenir. `VerificationResult.answer` (sympy) sandbox sınırından geçmez — sandbox üzerinden dönen yollar cevabı str/latex'e çevirir.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_verification.py`:
```python
from __future__ import annotations

from dataclasses import replace

import sympy

from questioncrator.models import Parameter, Template
from questioncrator.verification import checks


def turev_sablonu() -> Template:
    return Template(
        id="t1", source_id="s1", skeleton="f(x) = {p0}x^2 + {p1}x",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5}, seed_answer_ops=2,
    )


def iki_parametreli(recete: str, ops: int = 1) -> Template:
    return Template(
        id="t1", source_id="s1", skeleton="{p0} {p1}", recipe=recete,
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5}, seed_answer_ops=ops,
    )


def test_gecerli_baglama_dogrulanir():
    sonuc = checks.verify(turev_sablonu(), {"p0": 4, "p1": -2})
    assert sonuc.ok is True
    assert sonuc.answer == sympy.sympify("8*x - 2")
    assert sonuc.notes == ()


def test_tanimsiz_sonuc_reddedilir():
    sonuc = checks.verify(iki_parametreli("{p0}/({p1} - {p1})"), {"p0": 4, "p1": 2})
    assert sonuc.ok is False
    assert any("tanımsız" in n for n in sonuc.notes)


def test_dejenere_sadelesme_reddedilir():
    sonuc = checks.verify(iki_parametreli("{p0}*x - {p0}*x + {p1}", ops=4), {"p0": 3, "p1": 5})
    assert sonuc.ok is False
    assert any("dejenere" in n for n in sonuc.notes)


def test_cirkin_sayi_reddedilir():
    sonuc = checks.verify(iki_parametreli("Rational({p0}, {p1}) * 10**6"), {"p0": 7, "p1": 3})
    assert sonuc.ok is False
    assert any("sayı büyüklüğü" in n for n in sonuc.notes)


def test_kisit_ihlali_reddedilir():
    t = replace(turev_sablonu(), constraints=("{p0} > {p1}",))
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


def test_degerlendirilmemis_islem_reddedilir():
    # x**x'in kapalı biçimde ilkeli yok: sympy işlemi değerlendirmeden bırakır.
    t = Template(
        id="t1", source_id="s1", skeleton="{p0}", recipe="integrate(x**x + {p0}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)),), seed_bindings={"p0": 2}, seed_answer_ops=0,
    )
    sonuc = checks.verify(t, {"p0": 2})
    assert sonuc.ok is False
    assert any("değerlendirilmemiş" in n for n in sonuc.notes)


def test_cok_uzun_cevap_reddedilir():
    t = Template(
        id="t1", source_id="s1", skeleton="{p0}", recipe="expand((x + {p0})**12)",
        parameters=(Parameter("p0", -9, 9, (0,)),), seed_bindings={"p0": 2}, seed_answer_ops=0,
    )
    sonuc = checks.verify(t, {"p0": 7})
    assert sonuc.ok is False
    assert any("uzun" in n or "sayı büyüklüğü" in n for n in sonuc.notes)


def test_guvensiz_recete_istisna_firlatmaz():
    sonuc = checks.verify(iki_parametreli('sympify("x") + {p0} + {p1}'), {"p0": 1, "p1": 2})
    assert sonuc.ok is False
    assert any("değerlendirilemedi" in n for n in sonuc.notes)


def test_answer_problems_dogrudan():
    assert checks.answer_problems(sympy.sympify("2*x + 1")) == []
    assert checks.answer_problems(sympy.zoo) != []
```

`tests/test_topic_agnostic.py`:
```python
from __future__ import annotations

import random
from pathlib import Path

from questioncrator.generation import sampler
from questioncrator.ingest import markdown
from questioncrator.templating import extract
from questioncrator.templating.render import render_text
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
    assert len(kaynaklar) == 3
    for i, kaynak in enumerate(kaynaklar):
        sablon = extract.extract_template(kaynak, f"t{i}")
        baglama = sampler.sample_bindings(sablon, random.Random(i))
        assert baglama is not None, f"{kaynak.id}: bağlama üretilemedi"
        render_text(sablon, baglama)  # LaTeX'li metinde de istisna yok
        sonuc = checks.verify(sablon, baglama)
        assert isinstance(sonuc.ok, bool)
```

Not: `test_degerlendirilmemis_islem_reddedilir` reçete dizesinde yasak kelime içerir; bu **test** dosyasıdır, bekçi yalnız `questioncrator/` altını tarar.

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_verification.py tests/test_topic_agnostic.py -q`
Expected: FAIL — `ModuleNotFoundError: questioncrator.verification`

- [ ] **Adım 3: `checks.py`**

```python
"""Üretilen bir sorunun matematiksel olarak sağlam olup olmadığını denetler (A6).

Şablon onayı kaldırıldığı için otomatik kalite kapısı burasıdır. Tüm
kontroller jeneriktir: cevabın hangi işlemden geldiğini bilmez, yalnız
sonucun kendisine bakar.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import sympy

from questioncrator.generation.sampler import satisfies_constraints
from questioncrator.mathenv import EvaluationTimeout, UnsafeExpression, parse_with_timeout
from questioncrator.models import Template
from questioncrator.templating.render import render_recipe

MAX_NUMERATOR = 9999
MAX_DENOMINATOR = 99
MIN_OPS_RATIO = 0.5  # cevap, tohum cevabının en az yarısı kadar "zengin" olmalı
MAX_LATEX_LENGTH = 160

_UNDEFINED = (sympy.nan, sympy.zoo, sympy.oo, -sympy.oo)

# `doit` metodunu kendisi tanımlayan sympy sınıfları, işlemi değerlendirmeden
# taşıyabilen sınıflardır. Aşağıdakiler cevapta meşru olarak kalabilir.
_BENIGN_DOIT = (sympy.Basic, sympy.Atom, sympy.sign, sympy.Piecewise, sympy.beta,
                sympy.LeviCivita, sympy.ImageSet)
_UNEVALUATED_TYPES = tuple(
    cls
    for name in sympy.__all__
    if inspect.isclass(cls := getattr(sympy, name))
    and issubclass(cls, sympy.Basic)
    and "doit" in cls.__dict__
    and cls not in _BENIGN_DOIT
)


class EvaluationFailed(ValueError):
    """Reçete değerlendirilemedi (güvensiz, sözdizimi hatası, zaman aşımı...)."""


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    answer: sympy.Basic | None
    notes: tuple[str, ...]


def evaluate_answer(recipe: str, *, timeout: float = 5.0) -> sympy.Basic:
    try:
        return parse_with_timeout(recipe, seconds=timeout)
    except EvaluationTimeout as exc:
        raise EvaluationFailed("değerlendirme zaman aşımına uğradı") from exc
    except (UnsafeExpression, SyntaxError, TypeError, ValueError, ZeroDivisionError,
            AttributeError, sympy.SympifyError) as exc:
        raise EvaluationFailed(f"değerlendirilemedi: {exc}") from exc


def _is_undefined(expr: sympy.Basic) -> bool:
    return any(node in _UNDEFINED for node in sympy.preorder_traversal(expr))


def _has_unevaluated(expr: sympy.Basic) -> bool:
    return any(isinstance(node, _UNEVALUATED_TYPES) for node in sympy.preorder_traversal(expr))


def _numbers_too_large(expr: sympy.Basic) -> bool:
    return any(
        abs(atom.p) > MAX_NUMERATOR or abs(atom.q) > MAX_DENOMINATOR
        for atom in expr.atoms(sympy.Rational)
    )


def answer_problems(answer: sympy.Basic, *, seed_answer_ops: int = 0) -> list[str]:
    """Cevaptaki jenerik kusurları Türkçe notlar olarak döndürür; boşsa cevap sağlamdır."""
    notes: list[str] = []
    if _is_undefined(answer):
        notes.append("sonuç tanımsız (nan/zoo/oo)")
    if _has_unevaluated(answer):
        notes.append("kapalı biçim yok: sonuç değerlendirilmemiş işlem içeriyor")
    if seed_answer_ops and answer.count_ops() < seed_answer_ops * MIN_OPS_RATIO:
        notes.append("dejenere sadeleşme: cevap tohum cevabından çok daha basit")
    if _numbers_too_large(answer):
        notes.append("sayı büyüklüğü sınırları aşıldı")
    if len(sympy.latex(answer)) > MAX_LATEX_LENGTH:
        notes.append("cevap yazımı çok uzun")
    return notes


def verify(
    template: Template, bindings: dict[str, int], *, timeout: float = 5.0
) -> VerificationResult:
    if not satisfies_constraints(template, bindings):
        return VerificationResult(False, None, ("şablon kısıtları sağlanmıyor",))

    recipe = render_recipe(template, bindings)
    try:
        answer = evaluate_answer(recipe, timeout=timeout)
        second = evaluate_answer(recipe, timeout=timeout)
    except EvaluationFailed as exc:
        return VerificationResult(False, None, (str(exc),))

    notes = answer_problems(answer, seed_answer_ops=template.seed_answer_ops)
    if sympy.srepr(second) != sympy.srepr(answer):
        notes.append("kararsız sonuç: iki değerlendirme farklı çıktı")

    return VerificationResult(ok=not notes, answer=answer, notes=tuple(notes))
```

Not: `satisfies_constraints` kısıt dizesini `parse` ile değerlendirir; güvensiz kısıt `UnsafeExpression` fırlatabilir. `verify` bunu da `EvaluationFailed` gibi not olarak döndürmelidir — kısıt kontrolünü `try/except (UnsafeExpression, SyntaxError, TypeError, ValueError, sympy.SympifyError)` ile sar ve `("şablon kısıtları değerlendirilemedi",)` döndür. Bunun için bir test ekle (`constraints=('"a" > 1',)`).

- [ ] **Adım 4: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS. Bekçi test ihlal bulursa ilgili modüldeki kelimeyi (yorum dahil) kaldır.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/verification tests/test_verification.py tests/test_topic_agnostic.py
git commit -m "feat(verification): jenerik SymPy doğrulayıcı ve konu bağımsızlığı bekçisi"
```

---

### Task 6: Zorluk tahmini + çeldiriciler

**Files:**
- Create: `questioncrator/generation/difficulty.py`, `questioncrator/generation/distractors.py`
- Modify: `questioncrator/templating/extract.py` (şablona `difficulty_estimate` yazılır)
- Test: `tests/test_difficulty.py`, `tests/test_distractors.py`, `tests/test_templating.py` (ekleme)

**Interfaces:**
- Consumes: `checks.evaluate_answer`, `checks.answer_problems`, `checks.EvaluationFailed`, `render.render_recipe`
- Produces:
  - `difficulty.estimate_difficulty(template: Template, bindings: dict[str, int], answer: sympy.Basic) -> float` — 1.0-10.0, bir ondalık
  - `distractors.DISTRACTOR_COUNT = 4`
  - `distractors.build_choices(template, bindings, answer, rng, *, timeout=5.0) -> tuple[tuple[str, ...], int | None]` — başarıda 5 LaTeX şık + doğru indeks; aksi halde `((), None)`

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_difficulty.py`:
```python
from __future__ import annotations

import sympy

from questioncrator.generation.difficulty import estimate_difficulty
from questioncrator.models import Parameter, Template


def sablon(recete: str, adet: int = 1) -> Template:
    return Template(
        id="t1", source_id="s1", skeleton="", recipe=recete,
        parameters=tuple(Parameter(f"p{i}", -9, 9, (0,)) for i in range(adet)),
    )


def test_aralik_ve_tur():
    d = estimate_difficulty(sablon("{p0}*x"), {"p0": 2}, sympy.sympify("2*x"))
    assert isinstance(d, float)
    assert 1.0 <= d <= 10.0


def test_karmasik_recete_daha_zor():
    basit = estimate_difficulty(sablon("{p0} + 1"), {"p0": 2}, sympy.Integer(3))
    karmasik = estimate_difficulty(
        sablon("expand(({p0}*x + {p1})**3) + diff(sin({p2}*x)*x, x)", 3),
        {"p0": 2, "p1": 3, "p2": 4},
        sympy.sympify("8*x**3 + 36*x**2 + 54*x + 27 + 4*x*cos(4*x) + sin(4*x)"),
    )
    assert karmasik > basit


def test_buyuk_sayilar_zorlastirir():
    t = sablon("{p0}*x")
    kucuk = estimate_difficulty(t, {"p0": 2}, sympy.sympify("2*x"))
    buyuk = estimate_difficulty(t, {"p0": 9000}, sympy.sympify("9000*x"))
    assert buyuk > kucuk


def test_ust_sinir_kirpilir():
    t = sablon("+".join(f"f{i}({{p0}})" for i in range(40)))
    assert estimate_difficulty(t, {"p0": 99999}, sympy.sympify("x")) == 10.0
```

`tests/test_distractors.py`:
```python
from __future__ import annotations

import random

import sympy

from questioncrator.generation.distractors import DISTRACTOR_COUNT, build_choices
from questioncrator.models import Parameter, Template


def turev_sablonu() -> Template:
    return Template(
        id="t1", source_id="s1", skeleton="f(x) = {p0}x^2 + {p1}x",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5}, seed_answer_ops=2,
    )


def test_bes_farkli_sik_ve_dogru_indeks():
    cevap = sympy.sympify("8*x - 2")
    siklar, dogru = build_choices(turev_sablonu(), {"p0": 4, "p1": -2}, cevap, random.Random(0))
    assert len(siklar) == DISTRACTOR_COUNT + 1
    assert len(set(siklar)) == len(siklar)
    assert siklar[dogru] == sympy.latex(cevap)


def test_celdiriciler_dogruya_denk_degil():
    cevap = sympy.sympify("8*x - 2")
    siklar, dogru = build_choices(turev_sablonu(), {"p0": 4, "p1": -2}, cevap, random.Random(0))
    assert [s for i, s in enumerate(siklar) if i != dogru and s == sympy.latex(cevap)] == []


def test_deterministik():
    cevap = sympy.sympify("8*x - 2")
    a = build_choices(turev_sablonu(), {"p0": 4, "p1": -2}, cevap, random.Random(7))
    b = build_choices(turev_sablonu(), {"p0": 4, "p1": -2}, cevap, random.Random(7))
    assert a == b


def test_yeterli_aday_yoksa_bos():
    t = Template(
        id="t1", source_id="s1", skeleton="{p0}", recipe="Abs({p0})/Abs({p0})",
        parameters=(Parameter("p0", -9, 9, (0,)),), seed_bindings={"p0": 2},
    )
    assert build_choices(t, {"p0": 3}, sympy.Integer(1), random.Random(0)) == ((), None)


def test_liste_cevapta_istisna_yok():
    t = Template(
        id="t1", source_id="s1", skeleton="{p0}", recipe="solve(x**2 - {p0}, x)",
        parameters=(Parameter("p0", 1, 9, ()),), seed_bindings={"p0": 4},
    )
    cevap = sympy.Tuple(-2, 2)
    siklar, dogru = build_choices(t, {"p0": 4}, cevap, random.Random(0))
    assert (siklar == () and dogru is None) or siklar[dogru] == sympy.latex(cevap)
```

Denklik süzgeci birim düzeyinde `distractors._equivalent` ile ayrıca test edilir:

```python
from questioncrator.generation.distractors import _equivalent


def test_denklik_suzgeci():
    assert _equivalent(sympy.sympify("2*(x+1)"), sympy.sympify("2*x + 2"))
    assert not _equivalent(sympy.sympify("2*x + 3"), sympy.sympify("2*x + 2"))
    assert not _equivalent(sympy.Tuple(1, 2), sympy.Tuple(1, 3))
```

`tests/test_templating.py` sonuna:
```python
def test_sablon_zorluk_tahmini_tasir():
    s = kaynak("f(x) = 3x^2 + 5x", "diff(3*x**2 + 5*x, x)")
    t = extract.extract_template(s, "t1")
    assert 1.0 <= t.difficulty_estimate <= 10.0
```

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_difficulty.py tests/test_distractors.py tests/test_templating.py -q`
Expected: FAIL — modüller yok.

- [ ] **Adım 3: `difficulty.py`**

```python
"""Bir sorunun zorluğunu jenerik yapısal sinyallerden tahmin eder (1-10).

Konu bilmez: reçetedeki işlem çağrısı sayısı, cevabın işlem sayısı,
parametre sayısı ve sayıların büyüklüğü birleştirilir. Bu yalnız bir
başlangıç tahminidir; hocanın puanları `scoring.calibration` ile bunu
hocanın kendi ölçeğine taşır.
"""

from __future__ import annotations

import math
import re

import sympy

from questioncrator.models import Template

_CALL = re.compile(r"[A-Za-z]\w*\s*\(")


def estimate_difficulty(
    template: Template, bindings: dict[str, int], answer: sympy.Basic
) -> float:
    calls = len(_CALL.findall(template.recipe))
    answer_ops = min(int(answer.count_ops()), 15)
    magnitudes = [abs(v) for v in bindings.values()] + [
        abs(int(a.p)) for a in answer.atoms(sympy.Rational)
    ]
    largest = max(magnitudes, default=1)
    raw = (
        1.0
        + 1.1 * calls
        + 0.3 * answer_ops
        + 0.4 * len(template.parameters)
        + 0.9 * math.log10(largest + 1)
    )
    return round(min(10.0, max(1.0, raw)), 1)
```

- [ ] **Adım 4: `distractors.py`**

```python
"""Çoktan seçmeli sorular için jenerik çeldiriciler üretir (K5).

Adaylar iki kaynaktan gelir: (1) aynı reçetenin komşu bağlamalarla
değerlendirilmesi — biçimi korunmuş, öğrencinin bir sayıyı yanlış
okuması/işaret hatası gibi davranan yanlış cevaplar; (2) doğru cevabın
basit dönüşümleri (işaret, tamsayı ±1). Her aday doğrulayıcının cevap
kontrollerinden geçer ve doğru cevaba matematiksel olarak denk olamaz.
"""

from __future__ import annotations

import random

import sympy

from questioncrator.models import Template
from questioncrator.templating.render import render_recipe
from questioncrator.verification.checks import EvaluationFailed, answer_problems, evaluate_answer

DISTRACTOR_COUNT = 4


def _equivalent(a: sympy.Basic, b: sympy.Basic) -> bool:
    if sympy.srepr(a) == sympy.srepr(b):
        return True
    if isinstance(a, sympy.Expr) and isinstance(b, sympy.Expr):
        try:
            return sympy.simplify(a - b) == 0
        except (TypeError, ValueError, NotImplementedError):
            return False
    return False


def _neighbor_answers(
    template: Template, bindings: dict[str, int], rng: random.Random, timeout: float
) -> list[sympy.Basic]:
    names = sorted(bindings)
    rng.shuffle(names)
    excluded = {p.name: set(p.exclude) for p in template.parameters}
    candidates: list[sympy.Basic] = []
    for name in names:
        value = bindings[name]
        for new_value in (value + 1, value - 1, -value):
            if new_value == value or new_value in excluded.get(name, set()):
                continue
            recipe = render_recipe(template, {**bindings, name: new_value})
            try:
                candidates.append(evaluate_answer(recipe, timeout=timeout))
            except EvaluationFailed:
                continue
    return candidates


def _transformed_answers(answer: sympy.Basic, rng: random.Random) -> list[sympy.Basic]:
    candidates: list[sympy.Basic] = []
    try:
        candidates.append(-answer)
    except TypeError:
        pass
    integers = sorted(
        (a for a in answer.atoms(sympy.Integer) if abs(a) > 1), key=lambda a: int(a)
    )
    rng.shuffle(integers)
    for atom in integers:
        candidates.append(answer.xreplace({atom: atom + 1}))
        candidates.append(answer.xreplace({atom: atom - 1}))
    return candidates


def build_choices(
    template: Template,
    bindings: dict[str, int],
    answer: sympy.Basic,
    rng: random.Random,
    *,
    timeout: float = 5.0,
) -> tuple[tuple[str, ...], int | None]:
    correct = sympy.latex(answer)
    seen = {correct}
    chosen: list[str] = []
    for candidate in _neighbor_answers(template, bindings, rng, timeout) + _transformed_answers(
        answer, rng
    ):
        if len(chosen) == DISTRACTOR_COUNT:
            break
        if answer_problems(candidate) or _equivalent(candidate, answer):
            continue
        rendered = sympy.latex(candidate)
        if rendered in seen:
            continue
        seen.add(rendered)
        chosen.append(rendered)

    if len(chosen) < DISTRACTOR_COUNT:
        return (), None
    options = [correct, *chosen]
    rng.shuffle(options)
    return tuple(options), options.index(correct)
```

- [ ] **Adım 5: `extract.py`** — `extract_template` sonunda `Template(...)` oluşturulurken `difficulty_estimate=estimate_difficulty(<şablonun kendisi>, seed_bindings, seed_answer)` gerekir. Şablon henüz yokken tahmin için önce `difficulty_estimate` olmadan `Template` oluştur, sonra `dataclasses.replace(template, difficulty_estimate=estimate_difficulty(template, seed_bindings, seed_answer))` döndür. Import: `from questioncrator.generation.difficulty import estimate_difficulty` (döngüsel import yoktur: `difficulty` yalnız `models`'e bağımlı).

- [ ] **Adım 6: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS. `test_karmasik_recete_daha_zor` testindeki reçete dizesinde yasak kelime yoktur; `diff`/`sin`/`expand` serbesttir.

- [ ] **Adım 7: Commit**

```bash
git add questioncrator/generation/difficulty.py questioncrator/generation/distractors.py questioncrator/templating/extract.py tests/test_difficulty.py tests/test_distractors.py tests/test_templating.py
git commit -m "feat(generation): jenerik zorluk tahmini ve doğrulanmış çeldiriciler"
```

---

### Task 7: Puan deposu ve öğrenme döngüsü (skor, ağırlık, kalibrasyon, istatistik, örnekler)

**Files:**
- Create: `questioncrator/scoring/__init__.py` (`"""Puan deposu ve öğrenme sinyali katmanı."""`), `store.py`, `weights.py`, `calibration.py`, `stats.py`, `examples.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `db.*` (Task 3), `models.Review`, `models.FewShotExample`
- Produces:
  - `store.TemplateScore(template_id, reviewed, approved, approval_rate, avg_quality, avg_difficulty)`
  - `store.record_review(conn, review) -> None`, `store.template_scores(conn) -> dict[str, TemplateScore]`, `store.apply_status_transitions(conn) -> dict[str, str]`
  - `store.PROMOTE_AFTER_APPROVALS = 2`, `store.DISABLE_AFTER_REJECTIONS = 3`, `store.DISABLE_QUALITY_CEILING = 4.0`
  - `weights.DEFAULT_WEIGHT = 0.35`, `weights.template_weight(score: TemplateScore | None) -> float`, `weights.template_weights(conn) -> dict[str, float]`
  - `calibration.MIN_REVIEWS_FOR_TEMPLATE = 3`, `calibration.workspace_bias(conn) -> float`, `calibration.calibrated_difficulty(template, score, bias) -> float`, `calibration.calibrated_difficulties(conn) -> dict[str, float]`, `calibration.difficulty_deviation(conn, *, last: int = 100) -> float | None`
  - `stats.WindowStats(count, approval_rate, avg_quality)`, `stats.LearningStats(generated, pending, reviewed, approved, approval_rate, avg_quality, first_window, last_window, difficulty_deviation, templates_by_status: dict[str, int])`, `stats.learning_stats(conn) -> LearningStats`
  - `examples.few_shot_examples(conn, *, objective: str | None = None, k: int = 3, min_quality: int = 8) -> list[FewShotExample]`

**Kurallar.**
- Geçişler: Faz 1 planı Task 8 ile aynı (devre dışı bırakma öncelikli; `disabled` şablon geri açılmaz).
- Ağırlık: `((approved + 1) / (reviewed + 2)) * ((avg_quality * reviewed + 7 * 2) / (reviewed + 2) / 10)`; `score is None` → `DEFAULT_WEIGHT` (= 0.5 × 0.7).
- Kalibrasyon: `workspace_bias` = değerlendirilmiş sorularda `ortalama(review.difficulty − question.difficulty_estimate)`, yoksa 0.0. `calibrated_difficulty`: `score.reviewed >= 3` ise `score.avg_difficulty`, değilse `template.difficulty_estimate + bias`; 1-10'a kırpılır.
- `difficulty_deviation`: son `last` değerlendirmede `ortalama |review.difficulty − (question.difficulty_estimate + bias)|`; değerlendirme yoksa `None`.
- İstatistik pencereleri: değerlendirme sayısı `n`, `pencere = min(50, n // 2)`; `pencere < 10` ise `first_window = last_window = None`. Değerlendirme sırası `created_at, question_id`.
- `pending` = arşivlenmemiş ve değerlendirilmemiş soru sayısı; `generated` = tüm sorular.
- Örnekler: onaylı, `quality >= min_quality`, arşivlenmemiş; `objective` verilirse şablonun kazanımıyla eşleşenler; kurgu puanı azalan, sonra `created_at` azalan; ilk `k`.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_scoring.py`:

```python
from __future__ import annotations

import pytest

from questioncrator import db
from questioncrator.models import GeneratedQuestion, Parameter, Review, Template
from questioncrator.scoring import calibration, examples, stats, store, weights


def zaman(i: int) -> str:
    return f"2026-09-15T10:{i // 60:02d}:{i % 60:02d}+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def hazirla(conn, template_id, adet, status="trial", objective="k1", tahmin=5.0):
    db.save_template(conn, Template(
        id=template_id, source_id="s1", skeleton="{p0}", recipe="{p0}*x",
        parameters=(Parameter("p0", -9, 9, (0,)),), seed_bindings={"p0": 3},
        seed_answer_ops=1, status=status, objective=objective, difficulty_estimate=tahmin,
    ))
    idler = []
    for i in range(adet):
        qid = f"{template_id}-q{i}"
        db.save_question(conn, GeneratedQuestion(
            id=qid, template_id=template_id, bindings={"p0": i + 1}, text=f"metin {i}",
            answer_latex="x", answer_key=f"k{template_id}{i}", created_at=zaman(i),
            difficulty_estimate=tahmin,
        ))
        idler.append(qid)
    return idler


def puanla(conn, idler, kararlar, basla=0):
    for j, (qid, (onay, zorluk, kurgu)) in enumerate(zip(idler, kararlar, strict=True)):
        store.record_review(conn, Review(qid, onay, zorluk, kurgu, zaman(basla + j)))


def test_skorlar_hesaplanir(conn):
    idler = hazirla(conn, "t1", 4)
    puanla(conn, idler, [(True, 5, 8), (True, 6, 6), (False, 3, 4), (True, 7, 9)])
    skor = store.template_scores(conn)["t1"]
    assert (skor.reviewed, skor.approved) == (4, 3)
    assert skor.approval_rate == pytest.approx(0.75)
    assert skor.avg_quality == pytest.approx(27 / 4)
    assert skor.avg_difficulty == pytest.approx(21 / 4)


def test_iki_onay_deneme_sablonunu_etkinlestirir(conn):
    puanla(conn, hazirla(conn, "t1", 2), [(True, 5, 8)] * 2)
    assert store.apply_status_transitions(conn) == {"t1": "active"}
    assert db.get_template(conn, "t1").status == "active"


def test_uc_red_ve_dusuk_kurgu_sablonu_kapatir(conn):
    puanla(conn, hazirla(conn, "t1", 3), [(False, 5, 2)] * 3)
    assert store.apply_status_transitions(conn) == {"t1": "disabled"}


def test_uc_red_ama_yuksek_kurgu_kapatmaz(conn):
    puanla(conn, hazirla(conn, "t1", 3), [(False, 5, 9)] * 3)
    assert store.apply_status_transitions(conn) == {}


def test_kapatma_etkinlestirmeden_onceliklidir(conn):
    kararlar = [(True, 5, 8), (True, 5, 8), (False, 5, 1), (False, 5, 1), (False, 5, 1)]
    puanla(conn, hazirla(conn, "t1", 5), kararlar)
    assert store.apply_status_transitions(conn) == {"t1": "disabled"}


def test_degerlendirilmemis_sablon_gecis_yapmaz(conn):
    hazirla(conn, "t1", 2)
    assert store.apply_status_transitions(conn) == {}


def test_agirlik_iyi_sablonu_one_cikarir(conn):
    puanla(conn, hazirla(conn, "iyi", 4), [(True, 5, 9)] * 4)
    puanla(conn, hazirla(conn, "kotu", 4), [(False, 5, 2)] * 4, basla=10)
    agirliklar = weights.template_weights(conn)
    assert agirliklar["iyi"] > weights.DEFAULT_WEIGHT > agirliklar["kotu"]
    assert weights.template_weight(None) == weights.DEFAULT_WEIGHT


def test_kalibrasyon_sapma_ve_sablon_zorlugu(conn):
    idler = hazirla(conn, "t1", 3, tahmin=4.0)
    puanla(conn, idler, [(True, 7, 8), (True, 7, 8), (True, 7, 8)])
    hazirla(conn, "t2", 1, tahmin=4.0)
    assert calibration.workspace_bias(conn) == pytest.approx(3.0)
    zorluklar = calibration.calibrated_difficulties(conn)
    assert zorluklar["t1"] == pytest.approx(7.0)   # 3 puan: hocanın ortalaması
    assert zorluklar["t2"] == pytest.approx(7.0)   # tahmin 4 + genel sapma 3
    assert calibration.difficulty_deviation(conn) == pytest.approx(0.0)


def test_kalibrasyon_bos_depoda_notr(conn):
    hazirla(conn, "t1", 1, tahmin=9.5)
    assert calibration.workspace_bias(conn) == 0.0
    assert calibration.difficulty_deviation(conn) is None
    assert calibration.calibrated_difficulties(conn)["t1"] == pytest.approx(9.5)


def test_ogrenme_istatistikleri_pencereler(conn):
    idler = hazirla(conn, "t1", 40)
    kararlar = [(False, 5, 3)] * 20 + [(True, 5, 9)] * 20
    puanla(conn, idler, kararlar)
    ist = stats.learning_stats(conn)
    assert (ist.generated, ist.reviewed, ist.approved, ist.pending) == (40, 40, 20, 0)
    assert ist.first_window.count == 20 and ist.first_window.approval_rate == 0.0
    assert ist.last_window.approval_rate == 1.0
    assert ist.last_window.avg_quality == pytest.approx(9.0)
    assert ist.templates_by_status == {"trial": 1}


def test_az_veride_pencere_yok(conn):
    puanla(conn, hazirla(conn, "t1", 5), [(True, 5, 8)] * 5)
    ist = stats.learning_stats(conn)
    assert ist.first_window is None and ist.last_window is None


def test_fewshot_ornekleri_yuksek_kurgulu_onaylilar(conn):
    idler = hazirla(conn, "t1", 4, objective="k1")
    puanla(conn, idler, [(True, 5, 9), (True, 5, 7), (False, 5, 10), (True, 5, 8)])
    diger = hazirla(conn, "t2", 1, objective="k2")
    puanla(conn, diger, [(True, 5, 10)], basla=20)
    ornekler = examples.few_shot_examples(conn, objective="k1", k=5)
    assert [o.quality for o in ornekler] == [9, 8]
    assert all(o.objective == "k1" for o in ornekler)
    assert len(examples.few_shot_examples(conn, k=1)) == 1
```

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_scoring.py -q`
Expected: FAIL — `ModuleNotFoundError: questioncrator.scoring`

- [ ] **Adım 3: Uygulamayı yaz**

`scoring/store.py`:
```python
"""Hocanın onay/red kararlarını ve çift puanını biriktirir, şablon skorlarına çevirir."""

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
        SELECT g.template_id AS template_id, COUNT(*) AS reviewed,
               SUM(r.approved) AS approved, AVG(r.quality) AS avg_quality,
               AVG(r.difficulty) AS avg_difficulty
        FROM reviews r JOIN generated_questions g ON g.id = r.question_id
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
    scores = template_scores(conn)
    changed: dict[str, str] = {}
    for template in db.load_templates(conn):
        score = scores.get(template.id)
        if score is None or template.status == "disabled":
            continue
        rejected = score.reviewed - score.approved
        if rejected >= DISABLE_AFTER_REJECTIONS and score.avg_quality < DISABLE_QUALITY_CEILING:
            new_status = "disabled"
        elif template.status == "trial" and score.approved >= PROMOTE_AFTER_APPROVALS:
            new_status = "active"
        else:
            continue
        db.set_template_status(conn, template.id, new_status)
        changed[template.id] = new_status
    return changed
```

`scoring/weights.py`:
```python
"""Şablon ağırlıkları: puanlandıkça iyi şablonlar daha sık, kötüler daha seyrek üretilir."""

from __future__ import annotations

import sqlite3

from questioncrator.scoring.store import TemplateScore, template_scores

PRIOR_QUALITY = 7.0
PRIOR_COUNT = 2
DEFAULT_WEIGHT = 0.5 * (PRIOR_QUALITY / 10)


def template_weight(score: TemplateScore | None) -> float:
    if score is None:
        return DEFAULT_WEIGHT
    approval = (score.approved + 1) / (score.reviewed + 2)
    quality = (score.avg_quality * score.reviewed + PRIOR_QUALITY * PRIOR_COUNT) / (
        score.reviewed + PRIOR_COUNT
    )
    return approval * quality / 10


def template_weights(conn: sqlite3.Connection) -> dict[str, float]:
    return {tid: template_weight(score) for tid, score in template_scores(conn).items()}
```

`scoring/calibration.py`:
```python
"""Zorluk kalibrasyonu: sistemin tahminini hocanın kendi ölçeğine taşır."""

from __future__ import annotations

import sqlite3

from questioncrator import db
from questioncrator.models import Template
from questioncrator.scoring.store import TemplateScore, template_scores

MIN_REVIEWS_FOR_TEMPLATE = 3


def _clamp(value: float) -> float:
    return min(10.0, max(1.0, value))


def _pairs(conn: sqlite3.Connection) -> list[tuple[int, float]]:
    rows = conn.execute(
        """
        SELECT r.difficulty AS teacher, g.difficulty_estimate AS system
        FROM reviews r JOIN generated_questions g ON g.id = r.question_id
        ORDER BY r.created_at, r.question_id
        """
    ).fetchall()
    return [(r["teacher"], r["system"]) for r in rows]


def workspace_bias(conn: sqlite3.Connection) -> float:
    pairs = _pairs(conn)
    if not pairs:
        return 0.0
    return sum(teacher - system for teacher, system in pairs) / len(pairs)


def calibrated_difficulty(template: Template, score: TemplateScore | None, bias: float) -> float:
    if score is not None and score.reviewed >= MIN_REVIEWS_FOR_TEMPLATE:
        return _clamp(score.avg_difficulty)
    return _clamp(template.difficulty_estimate + bias)


def calibrated_difficulties(conn: sqlite3.Connection) -> dict[str, float]:
    bias = workspace_bias(conn)
    scores = template_scores(conn)
    return {
        t.id: calibrated_difficulty(t, scores.get(t.id), bias) for t in db.load_templates(conn)
    }


def difficulty_deviation(conn: sqlite3.Connection, *, last: int = 100) -> float | None:
    pairs = _pairs(conn)
    if not pairs:
        return None
    bias = workspace_bias(conn)
    recent = pairs[-last:]
    return sum(abs(teacher - (system + bias)) for teacher, system in recent) / len(recent)
```

`scoring/stats.py`:
```python
"""Panel metrikleri: öğrenme döngüsünün hocaya görünen kanıtı (tasarım §6)."""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass

from questioncrator import db
from questioncrator.models import Review
from questioncrator.scoring.calibration import difficulty_deviation

WINDOW = 50
MIN_WINDOW = 10


@dataclass(frozen=True)
class WindowStats:
    count: int
    approval_rate: float
    avg_quality: float


@dataclass(frozen=True)
class LearningStats:
    generated: int
    pending: int
    reviewed: int
    approved: int
    approval_rate: float | None
    avg_quality: float | None
    first_window: WindowStats | None
    last_window: WindowStats | None
    difficulty_deviation: float | None
    templates_by_status: dict[str, int]


def _window(reviews: list[Review]) -> WindowStats:
    return WindowStats(
        count=len(reviews),
        approval_rate=sum(r.approved for r in reviews) / len(reviews),
        avg_quality=sum(r.quality for r in reviews) / len(reviews),
    )


def learning_stats(conn: sqlite3.Connection) -> LearningStats:
    reviews = db.load_reviews(conn)
    questions = db.load_questions(conn)
    reviewed_ids = {r.question_id for r in reviews}
    size = min(WINDOW, len(reviews) // 2)
    has_windows = size >= MIN_WINDOW
    return LearningStats(
        generated=len(questions),
        pending=sum(1 for q in questions if not q.archived and q.id not in reviewed_ids),
        reviewed=len(reviews),
        approved=sum(1 for r in reviews if r.approved),
        approval_rate=_window(reviews).approval_rate if reviews else None,
        avg_quality=_window(reviews).avg_quality if reviews else None,
        first_window=_window(reviews[:size]) if has_windows else None,
        last_window=_window(reviews[-size:]) if has_windows else None,
        difficulty_deviation=difficulty_deviation(conn),
        templates_by_status=dict(Counter(t.status for t in db.load_templates(conn))),
    )
```

`scoring/examples.py`:
```python
"""Few-shot örnek seçimi: hocanın iyi dediği onaylı sorular (tasarım §2.1)."""

from __future__ import annotations

import sqlite3

from questioncrator.models import FewShotExample


def few_shot_examples(
    conn: sqlite3.Connection,
    *,
    objective: str | None = None,
    k: int = 3,
    min_quality: int = 8,
) -> list[FewShotExample]:
    query = """
        SELECT g.text AS text, g.answer_latex AS answer_latex, r.quality AS quality,
               t.objective AS objective
        FROM reviews r
        JOIN generated_questions g ON g.id = r.question_id
        JOIN templates t ON t.id = g.template_id
        WHERE r.approved = 1 AND r.quality >= ? AND g.archived = 0
    """
    params: list[object] = [min_quality]
    if objective is not None:
        query += " AND t.objective = ?"
        params.append(objective)
    query += " ORDER BY r.quality DESC, g.created_at DESC LIMIT ?"
    params.append(k)
    return [
        FewShotExample(
            question_text=r["text"],
            answer_latex=r["answer_latex"],
            quality=r["quality"],
            objective=r["objective"],
        )
        for r in conn.execute(query, params)
    ]
```

- [ ] **Adım 4: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/scoring tests/test_scoring.py
git commit -m "feat(scoring): puan deposu, şablon ağırlıkları, zorluk kalibrasyonu, panel istatistikleri"
```

---

### Task 8: Üretim motoru

**Files:**
- Create: `questioncrator/generation/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `sampler.sample_bindings`, `checks.verify`, `render.render_text`, `distractors.build_choices`, `difficulty.estimate_difficulty`, `weights.DEFAULT_WEIGHT`
- Produces:
  - `engine.TRIAL_BATCH_CAP = 2`, `engine.MAX_ATTEMPTS_PER_QUESTION = 20`, `engine.DIFFICULTY_TOLERANCE = 2.0`
  - `engine.GenerationRequest(total: int, objectives: frozenset[str] | None = None, target_difficulty: float | None = None, avoid_template_ids: frozenset[str] = frozenset(), student_id: str | None = None, created_by: str | None = None, with_choices: bool = True)`
  - `engine.generate_from_template(template, *, count, rng, now, seen_answer_keys: set[str], id_factory, student_id=None, created_by=None, similar_given=False, with_choices=True) -> list[GeneratedQuestion]` — `seen_answer_keys`'i **değiştirmez**
  - `engine.generate_batch(templates, request, *, rng, now, seen_answer_keys, id_factory, weights: dict[str, float] | None = None, difficulties: dict[str, float] | None = None) -> list[GeneratedQuestion]`

**Kurallar.**
1. Uygun şablon: `status != "disabled"` ve (`objectives is None` ya da `template.objective in objectives`).
2. Hedef zorluk verildiyse: `difficulties.get(t.id, t.difficulty_estimate)` ile `|d − hedef| <= DIFFICULTY_TOLERANCE` olanlar; hiç yoksa en yakın mesafeye `+1.0` içinde kalanlar.
3. Havuz ikiye bölünür: taze (`id not in avoid_template_ids`) ve benzer. Önce taze havuzdan üretilir; toplam dolmazsa benzer havuzdan `similar_given=True` ile devam edilir.
4. Her adımda şablon, kapasitesi kalanlar arasından `rng.choices` ile seçilir; etkin ağırlık `weights.get(id, DEFAULT_WEIGHT) / (1 + bu partide o şablondan üretilen)`. Seçilen şablondan `count=1` üretilir; üretemezse şablon havuzdan çıkar.
5. `trial` şablonun parti kapasitesi `TRIAL_BATCH_CAP`; diğerlerinin sınırı yok.
6. Kopya filtresi: partide görülen anahtarlar `seen_answer_keys` kopyasına eklenir; aynı cevap iki kez çıkmaz.
7. Soru alanları: `id=id_factory()`, `answer_key=sympy.srepr(answer)`, `answer_latex=sympy.latex(answer)`, `difficulty_estimate=estimate_difficulty(...)`, `with_choices` ise `build_choices` sonucu.
8. Tamamen deterministik: aynı `rng` tohumu + aynı girdiler → aynı çıktı.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_engine.py`:

```python
from __future__ import annotations

import itertools
import random

import pytest

from questioncrator.generation import engine
from questioncrator.models import Parameter, Template

SIMDI = "2026-09-15T10:00:00+00:00"


def sayac():
    c = itertools.count()
    return lambda: f"q_{next(c):012x}"


def sablon(tid, status="active", objective="k1", tahmin=5.0):
    return Template(
        id=tid, source_id="s1", skeleton="f(x) = {p0}x^2 + {p1}x fonksiyonunu inceleyiniz.",
        recipe="diff({p0}*x**2 + {p1}*x, x)",
        parameters=(Parameter("p0", -9, 9, (0,)), Parameter("p1", -9, 9, (0,))),
        seed_bindings={"p0": 3, "p1": 5}, seed_answer_ops=2, objective=objective,
        status=status, difficulty_estimate=tahmin,
    )


def uret(sablonlar, istek, tohum=0, **ek):
    return engine.generate_batch(
        sablonlar, istek, rng=random.Random(tohum), now=SIMDI,
        seen_answer_keys=ek.pop("gorulen", set()), id_factory=sayac(), **ek,
    )


def test_tek_sablondan_istenen_sayida_farkli_soru():
    sorular = engine.generate_from_template(
        sablon("t1"), count=5, rng=random.Random(0), now=SIMDI,
        seen_answer_keys=set(), id_factory=sayac(),
    )
    assert len(sorular) == 5
    assert len({s.answer_key for s in sorular}) == 5
    assert len({s.id for s in sorular}) == 5


def test_uretilen_soru_tam_dolu():
    (soru,) = engine.generate_from_template(
        sablon("t1"), count=1, rng=random.Random(3), now=SIMDI,
        seen_answer_keys=set(), id_factory=sayac(), student_id="st1", created_by="u1",
    )
    assert "{p0}" not in soru.text
    assert len(soru.choices) == 5 and soru.choices[soru.correct_index] == soru.answer_latex
    assert 1.0 <= soru.difficulty_estimate <= 10.0
    assert (soru.student_id, soru.created_by, soru.created_at) == ("st1", "u1", SIMDI)


def test_siksiz_uretim():
    (soru,) = engine.generate_from_template(
        sablon("t1"), count=1, rng=random.Random(3), now=SIMDI,
        seen_answer_keys=set(), id_factory=sayac(), with_choices=False,
    )
    assert soru.choices == () and soru.correct_index is None


def test_gorulen_kume_degistirilmez_ve_kopya_uretilmez():
    ilk = engine.generate_from_template(
        sablon("t1"), count=6, rng=random.Random(1), now=SIMDI,
        seen_answer_keys=set(), id_factory=sayac(),
    )
    gorulen = {s.answer_key for s in ilk}
    kopya = set(gorulen)
    ikinci = engine.generate_from_template(
        sablon("t1"), count=6, rng=random.Random(1), now=SIMDI,
        seen_answer_keys=gorulen, id_factory=sayac(),
    )
    assert gorulen == kopya
    assert gorulen.isdisjoint({s.answer_key for s in ikinci})


def test_deneme_sablonu_partide_iki_soruyla_sinirli():
    sorular = uret([sablon("t1", status="trial")], engine.GenerationRequest(total=10))
    assert len(sorular) == engine.TRIAL_BATCH_CAP


def test_devre_disi_sablon_kullanilmaz():
    assert uret([sablon("t1", status="disabled")], engine.GenerationRequest(total=5)) == []


def test_kazanim_filtresi():
    sorular = uret(
        [sablon("t1", objective="k1"), sablon("t2", objective="k2")],
        engine.GenerationRequest(total=6, objectives=frozenset({"k2"})),
    )
    assert sorular and {s.template_id for s in sorular} == {"t2"}


def test_hedef_zorluga_yakin_sablon_secilir():
    sorular = uret(
        [sablon("kolay", tahmin=2.0), sablon("zor", tahmin=9.0)],
        engine.GenerationRequest(total=4, target_difficulty=8.5),
    )
    assert {s.template_id for s in sorular} == {"zor"}


def test_kalibre_zorluk_tahminden_onceliklidir():
    sorular = uret(
        [sablon("a", tahmin=2.0), sablon("b", tahmin=9.0)],
        engine.GenerationRequest(total=4, target_difficulty=2.0),
        difficulties={"a": 9.0, "b": 2.0},
    )
    assert {s.template_id for s in sorular} == {"b"}


def test_hedefe_uygun_yoksa_en_yakinlar_kullanilir():
    sorular = uret(
        [sablon("a", tahmin=5.0), sablon("b", tahmin=6.5)],
        engine.GenerationRequest(total=3, target_difficulty=10.0),
    )
    assert {s.template_id for s in sorular} == {"b"}


def test_ogrenciye_verilmis_sablon_once_kacinilir():
    sorular = uret(
        [sablon("verilen"), sablon("taze")],
        engine.GenerationRequest(total=3, avoid_template_ids=frozenset({"verilen"})),
    )
    assert {s.template_id for s in sorular} == {"taze"}
    assert not any(s.similar_given for s in sorular)


def test_kota_dolmazsa_benzer_isaretli_kullanilir():
    sorular = uret(
        [sablon("verilen"), sablon("taze", status="trial")],
        engine.GenerationRequest(total=4, avoid_template_ids=frozenset({"verilen"})),
    )
    assert len(sorular) == 4
    assert all(s.similar_given for s in sorular if s.template_id == "verilen")
    assert any(s.template_id == "verilen" for s in sorular)


def test_agirlik_dagilimi_etkiler():
    istek = engine.GenerationRequest(total=30)
    sorular = uret([sablon("iyi"), sablon("kotu")], istek, weights={"iyi": 0.95, "kotu": 0.02})
    iyi = sum(1 for s in sorular if s.template_id == "iyi")
    assert iyi > len(sorular) - iyi


def test_parti_deterministik():
    istek = engine.GenerationRequest(total=6)
    a = uret([sablon("t1"), sablon("t2")], istek, tohum=42)
    b = uret([sablon("t1"), sablon("t2")], istek, tohum=42)
    assert [(s.template_id, s.text, s.choices) for s in a] == [
        (s.template_id, s.text, s.choices) for s in b
    ]


@pytest.mark.parametrize("toplam", [0, -1])
def test_sifir_ya_da_negatif_toplam_bos(toplam):
    assert uret([sablon("t1")], engine.GenerationRequest(total=toplam)) == []
```

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_engine.py -q`
Expected: FAIL — `ImportError: cannot import name 'engine'`

- [ ] **Adım 3: `engine.py`**

```python
"""Üretim partisini orkestre eder (A4 + A6).

Şablon seçer (öğrenme döngüsü ağırlıklarıyla), parametre örnekler,
doğrulatır, kopyaları eler, çeldirici ve zorluk tahmini ekler. Deneme
modundaki şablonların hacmini kısarak hatalı bir şablonun tek seferde
çöp dalgası üretmesini engeller.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import sympy

from questioncrator.generation.difficulty import estimate_difficulty
from questioncrator.generation.distractors import build_choices
from questioncrator.generation.sampler import sample_bindings
from questioncrator.models import GeneratedQuestion, Template
from questioncrator.scoring.weights import DEFAULT_WEIGHT
from questioncrator.templating.render import render_text
from questioncrator.verification.checks import verify

TRIAL_BATCH_CAP = 2
MAX_ATTEMPTS_PER_QUESTION = 20
DIFFICULTY_TOLERANCE = 2.0


@dataclass(frozen=True)
class GenerationRequest:
    total: int
    objectives: frozenset[str] | None = None
    target_difficulty: float | None = None
    avoid_template_ids: frozenset[str] = frozenset()
    student_id: str | None = None
    created_by: str | None = None
    with_choices: bool = True


def generate_from_template(
    template: Template,
    *,
    count: int,
    rng: random.Random,
    now: str,
    seen_answer_keys: set[str],
    id_factory: Callable[[], str],
    student_id: str | None = None,
    created_by: str | None = None,
    similar_given: bool = False,
    with_choices: bool = True,
) -> list[GeneratedQuestion]:
    """Tek şablondan en fazla `count` doğrulanmış, birbirinden farklı soru üretir."""
    produced: list[GeneratedQuestion] = []
    seen = set(seen_answer_keys)
    while len(produced) < count:
        question = None
        for _ in range(MAX_ATTEMPTS_PER_QUESTION):
            bindings = sample_bindings(template, rng)
            if bindings is None:
                continue
            result = verify(template, bindings)
            if not result.ok or result.answer is None:
                continue
            key = sympy.srepr(result.answer)
            if key in seen:
                continue
            seen.add(key)
            choices, correct_index = (
                build_choices(template, bindings, result.answer, rng)
                if with_choices
                else ((), None)
            )
            question = GeneratedQuestion(
                id=id_factory(),
                template_id=template.id,
                bindings=bindings,
                text=render_text(template, bindings),
                answer_latex=sympy.latex(result.answer),
                answer_key=key,
                created_at=now,
                choices=choices,
                correct_index=correct_index,
                difficulty_estimate=estimate_difficulty(template, bindings, result.answer),
                student_id=student_id,
                created_by=created_by,
                similar_given=similar_given,
            )
            break
        if question is None:
            break  # bu şablon tükendi
        produced.append(question)
    return produced


def _eligible(
    templates: list[Template], request: GenerationRequest, difficulties: dict[str, float]
) -> list[Template]:
    pool = [
        t
        for t in templates
        if t.status != "disabled"
        and (request.objectives is None or t.objective in request.objectives)
    ]
    if request.target_difficulty is None or not pool:
        return pool
    distance = {
        t.id: abs(difficulties.get(t.id, t.difficulty_estimate) - request.target_difficulty)
        for t in pool
    }
    within = [t for t in pool if distance[t.id] <= DIFFICULTY_TOLERANCE]
    if within:
        return within
    closest = min(distance.values())
    return [t for t in pool if distance[t.id] <= closest + 1.0]


def generate_batch(
    templates: list[Template],
    request: GenerationRequest,
    *,
    rng: random.Random,
    now: str,
    seen_answer_keys: set[str],
    id_factory: Callable[[], str],
    weights: dict[str, float] | None = None,
    difficulties: dict[str, float] | None = None,
) -> list[GeneratedQuestion]:
    """Uygun şablonlar arasından ağırlıklı seçimle toplam `request.total` soruya kadar üretir."""
    if request.total <= 0:
        return []
    weights = weights or {}
    pool = _eligible(templates, request, difficulties or {})
    fresh = [t for t in pool if t.id not in request.avoid_template_ids]
    similar = [t for t in pool if t.id in request.avoid_template_ids]

    result: list[GeneratedQuestion] = []
    seen = set(seen_answer_keys)
    produced: Counter[str] = Counter()

    for candidates, is_similar in ((fresh, False), (similar, True)):
        active = list(candidates)
        while active and len(result) < request.total:
            active = [
                t for t in active if t.status != "trial" or produced[t.id] < TRIAL_BATCH_CAP
            ]
            if not active:
                break
            chosen = rng.choices(
                active,
                weights=[
                    weights.get(t.id, DEFAULT_WEIGHT) / (1 + produced[t.id]) for t in active
                ],
            )[0]
            batch = generate_from_template(
                chosen,
                count=1,
                rng=rng,
                now=now,
                seen_answer_keys=seen,
                id_factory=id_factory,
                student_id=request.student_id,
                created_by=request.created_by,
                similar_given=is_similar,
                with_choices=request.with_choices,
            )
            if not batch:
                active.remove(chosen)
                continue
            seen.update(q.answer_key for q in batch)
            produced[chosen.id] += len(batch)
            result.extend(batch)
    return result
```

Not: `weights` sözlüğündeki bir değer 0 ise `rng.choices` tüm ağırlıklar sıfırsa `ValueError` verir. `template_weight` asla 0 dönmez (Laplace düzeltmesi), ama savunma olarak etkin ağırlığa `max(..., 1e-6)` uygula.

- [ ] **Adım 4: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS. (`test_agirlik_dagilimi_etkiler` olasılıksal değil, tohumlu; yine de tohumu değiştirince kırılıyorsa ağırlık formülünü kontrol et, testi değil.)

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/generation/engine.py tests/test_engine.py
git commit -m "feat(generation): ağırlıklı, zorluk hedefli, öğrenci farkındalıklı üretim motoru"
```

---

### Task 9: Kitapçık + LaTeX + Word çıktısı

**Files:**
- Create: `questioncrator/export/__init__.py` (`"""Çıktı katmanı (A8)."""`), `export/text.py`, `export/booklet.py`, `export/latex.py`, `export/docx.py`, `export/templates/exam.tex.j2`, `export/templates/answers.tex.j2`
- Modify: `pyproject.toml` (bağımlılıklar: `python-docx>=1.1`, `latex2mathml>=3.77`, `mathml2omml>=0.0.2`)
- Test: `tests/test_export_booklet.py`, `tests/test_export_latex.py`, `tests/test_export_docx.py`

**Interfaces:**
- Consumes: `models.GeneratedQuestion`
- Produces:
  - `text.split_math(text: str) -> list[tuple[bool, str]]` — `(is_math, parça)`; `$$..$$` ve `$..$` matematik parçasıdır (sınırlayıcılar parçaya dahil değildir), kaçışlı `\$` düz metindir.
  - `booklet.LETTERS = "ABCDE"`
  - `booklet.BookletItem(number: int, question: GeneratedQuestion, choices: tuple[str, ...], correct_letter: str | None)`
  - `booklet.Booklet(name: str, items: tuple[BookletItem, ...])`
  - `booklet.build_booklets(questions: Sequence[GeneratedQuestion], *, names: Sequence[str], seed: int, fmt: str) -> list[Booklet]` — `fmt` `"mc"` | `"open"`; ilk kitapçık özgün sıradır; sonrakiler `random.Random(f"{seed}:{name}")` ile soru ve şık sırası karıştırılmış.
  - `booklet.answer_key(booklet) -> list[tuple[int, str]]` — `(numara, harf)` test sorusunda, `(numara, answer_latex)` klasik soruda.
  - `latex.escape_text(text) -> str`, `latex.render_exam_tex(booklet, title) -> str`, `latex.render_answers_tex(booklet, title) -> str`
  - `docx.render_exam_docx(booklet, title, *, with_answers: bool) -> bytes`, `docx.latex_to_omml(latex: str) -> lxml element | None`

- [ ] **Adım 1: Bağımlılıkları kur**

`pyproject.toml` `dependencies` listesine üç paketi ekle, sonra:
Run: `.venv/bin/pip install -e ".[dev]" -q`
Expected: hatasız.

- [ ] **Adım 2: Başarısız testleri yaz**

`tests/test_export_booklet.py`:
```python
from __future__ import annotations

from questioncrator.export.booklet import answer_key, build_booklets
from questioncrator.export.text import split_math
from questioncrator.models import GeneratedQuestion

SIMDI = "2026-09-15T10:00:00+00:00"


def soru(i: int, siklar=True) -> GeneratedQuestion:
    return GeneratedQuestion(
        id=f"q{i}", template_id="t1", bindings={"p0": i}, text=f"Soru {i}: ${i}x$",
        answer_latex=f"{i} x", answer_key=f"k{i}", created_at=SIMDI,
        choices=(f"{i} x", f"{i + 1} x", f"{i + 2} x", f"{i + 3} x", f"{i + 4} x") if siklar else (),
        correct_index=0 if siklar else None,
    )


SORULAR = [soru(i) for i in range(1, 9)] + [soru(9, siklar=False)]


def test_ilk_kitapcik_ozgun_sirada():
    (a,) = build_booklets(SORULAR, names=["A"], seed=1, fmt="mc")
    assert [it.question.id for it in a.items] == [q.id for q in SORULAR]
    assert [it.number for it in a.items] == list(range(1, 10))
    assert a.items[0].choices == SORULAR[0].choices and a.items[0].correct_letter == "A"


def test_b_kitapcigi_karisik_ama_ayni_sorular():
    a, b = build_booklets(SORULAR, names=["A", "B"], seed=1, fmt="mc")
    assert [it.question.id for it in b.items] != [it.question.id for it in a.items]
    assert sorted(it.question.id for it in b.items) == sorted(q.id for q in SORULAR)
    for it in b.items:
        if it.choices:
            assert it.choices[ord(it.correct_letter) - ord("A")] == it.question.answer_latex


def test_kitapcik_deterministik():
    assert build_booklets(SORULAR, names=["A", "B"], seed=5, fmt="mc") == build_booklets(
        SORULAR, names=["A", "B"], seed=5, fmt="mc"
    )


def test_klasik_formatta_sik_yok_ve_anahtar_cevap():
    (a,) = build_booklets(SORULAR[:2], names=["A"], seed=1, fmt="open")
    assert all(it.choices == () and it.correct_letter is None for it in a.items)
    assert answer_key(a) == [(1, "1 x"), (2, "2 x")]


def test_test_formatinda_siksiz_soru_klasik_kalir():
    (a,) = build_booklets(SORULAR, names=["A"], seed=1, fmt="mc")
    anahtar = dict(answer_key(a))
    assert anahtar[1] == "A" and anahtar[9] == "9 x"


def test_split_math():
    assert split_math(r"a $x^2$ b $$\frac{1}{2}$$ c \$5") == [
        (False, "a "), (True, "x^2"), (False, " b "), (True, r"\frac{1}{2}"), (False, r" c \$5"),
    ]
```

`tests/test_export_latex.py`:
```python
from __future__ import annotations

import shutil
import subprocess

import pytest

from questioncrator.export import latex
from questioncrator.export.booklet import build_booklets
from questioncrator.models import GeneratedQuestion

SIMDI = "2026-09-15T10:00:00+00:00"
SORULAR = [
    GeneratedQuestion(
        id="q1", template_id="t1", bindings={"p0": 4}, text="f(x) = 4x^2 %50 & $4x^2$ ğşı",
        answer_latex="8 x", answer_key="k1", created_at=SIMDI,
        choices=("8 x", "9 x", "7 x", "-8 x", "4 x"), correct_index=0,
    ),
    GeneratedQuestion(
        id="q2", template_id="t1", bindings={"p0": 5}, text="g(x) = $5x$",
        answer_latex="5", answer_key="k2", created_at=SIMDI,
    ),
]


def kitapcik(fmt="mc"):
    return build_booklets(SORULAR, names=["A"], seed=1, fmt=fmt)[0]


def test_escape_text_matematik_disini_kacislar():
    assert latex.escape_text("4x^2 %50 & $4x^2$") == r"4x\^{}2 \%50 \& $4x^2$"


def test_sinav_tex_uretilir_cevap_sizmaz():
    tex = latex.render_exam_tex(kitapcik(), title="Ara Sınav")
    assert r"\documentclass" in tex and "Ara Sınav" in tex
    assert r"\%50" in tex and "ğşı" in tex
    assert "A)" in tex and "$9 x$" in tex
    assert "Cevap" not in tex


def test_cevap_anahtari_tex():
    tex = latex.render_answers_tex(kitapcik(), title="Ara Sınav")
    assert "Cevap Anahtarı" in tex
    assert "1. A" in tex and "$5$" in tex


def test_bos_kitapcik_gecerli_tex():
    bos = build_booklets([], names=["A"], seed=1, fmt="mc")[0]
    tex = latex.render_exam_tex(bos, title="Boş")
    assert r"\begin{document}" in tex and r"\end{document}" in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex kurulu değil")
def test_pdflatex_derler(tmp_path):
    (tmp_path / "s.tex").write_text(latex.render_exam_tex(kitapcik(), "Ara Sınav"), encoding="utf-8")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "s.tex"], cwd=tmp_path, check=True,
                   capture_output=True)
    assert (tmp_path / "s.pdf").exists()
```

`tests/test_export_docx.py`:
```python
from __future__ import annotations

import io
import zipfile

from questioncrator.export import docx as docx_export
from questioncrator.export.booklet import build_booklets
from questioncrator.models import GeneratedQuestion

SIMDI = "2026-09-15T10:00:00+00:00"
SORULAR = [
    GeneratedQuestion(
        id="q1", template_id="t1", bindings={"p0": 4}, text=r"Hesaplayınız: $\frac{4}{x}$ ğüşıöç",
        answer_latex=r"- \frac{4}{x^{2}}", answer_key="k1", created_at=SIMDI,
        choices=(r"- \frac{4}{x^{2}}", "a", "b", "c", "d"), correct_index=0,
    ),
]


def belge_xml(veri: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(veri)) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_docx_gecerli_ve_denklem_icerir():
    kitapcik = build_booklets(SORULAR, names=["A"], seed=1, fmt="mc")[0]
    veri = docx_export.render_exam_docx(kitapcik, "Deneme", with_answers=False)
    xml = belge_xml(veri)
    assert "Deneme" in xml and "ğüşıöç" in xml
    assert "<m:oMath" in xml
    assert "Ad Soyad" in xml
    assert "Cevap Anahtarı" not in xml


def test_docx_cevap_anahtari():
    kitapcik = build_booklets(SORULAR, names=["A"], seed=1, fmt="mc")[0]
    xml = belge_xml(docx_export.render_exam_docx(kitapcik, "Deneme", with_answers=True))
    assert "Cevap Anahtarı" in xml


def test_bozuk_latex_istisna_firlatmaz():
    docx_export.latex_to_omml(r"\frac{")  # None ya da öğe; istisna yok


def test_docx_yeniden_okunabilir():
    from docx import Document

    kitapcik = build_booklets(SORULAR, names=["A"], seed=1, fmt="mc")[0]
    Document(io.BytesIO(docx_export.render_exam_docx(kitapcik, "Deneme", with_answers=False)))
```

- [ ] **Adım 3: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_export_booklet.py tests/test_export_latex.py tests/test_export_docx.py -q`
Expected: FAIL — `ModuleNotFoundError: questioncrator.export`

- [ ] **Adım 4: `text.py` ve `booklet.py`**

```python
"""Soru metnini düz metin ve matematik parçalarına ayırır."""

from __future__ import annotations

import re

_MATH = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.DOTALL)


def split_math(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    position = 0
    for match in _MATH.finditer(text):
        if match.start() > position:
            parts.append((False, text[position:match.start()]))
        parts.append((True, match.group(1) if match.group(1) is not None else match.group(2)))
        position = match.end()
    if position < len(text):
        parts.append((False, text[position:]))
    return parts
```

```python
"""Sınav kitapçıkları: soru ve şık sırası, cevap anahtarı (A8).

Yazdırma görünümü, Word ve LaTeX çıktılarının hepsi aynı kitapçık
nesnesinden beslenir; A ve B kitapçıklarının anahtarı hiçbir çıktıda
birbirinden sapamaz.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from questioncrator.models import GeneratedQuestion

LETTERS = "ABCDE"


@dataclass(frozen=True)
class BookletItem:
    number: int
    question: GeneratedQuestion
    choices: tuple[str, ...]
    correct_letter: str | None


@dataclass(frozen=True)
class Booklet:
    name: str
    items: tuple[BookletItem, ...]


def _item(
    number: int, question: GeneratedQuestion, fmt: str, rng: random.Random | None
) -> BookletItem:
    if fmt != "mc" or not question.choices or question.correct_index is None:
        return BookletItem(number, question, (), None)
    order = list(range(len(question.choices)))
    if rng is not None:
        rng.shuffle(order)
    choices = tuple(question.choices[i] for i in order)
    return BookletItem(number, question, choices, LETTERS[order.index(question.correct_index)])


def build_booklets(
    questions: Sequence[GeneratedQuestion], *, names: Sequence[str], seed: int, fmt: str
) -> list[Booklet]:
    booklets: list[Booklet] = []
    for index, name in enumerate(names):
        rng = None if index == 0 else random.Random(f"{seed}:{name}")
        ordered = list(questions)
        if rng is not None:
            rng.shuffle(ordered)
        items = tuple(_item(n, q, fmt, rng) for n, q in enumerate(ordered, start=1))
        booklets.append(Booklet(name=name, items=items))
    return booklets


def answer_key(booklet: Booklet) -> list[tuple[int, str]]:
    return [
        (item.number, item.correct_letter or item.question.answer_latex) for item in booklet.items
    ]
```

- [ ] **Adım 5: `latex.py` + şablonlar**

```python
"""Kitapçıktan LaTeX sınav kağıdı ve cevap anahtarı üretir (A8).

Jinja2'nin varsayılan `{{ }}` sınırlayıcıları LaTeX'te çakıştığı için
`\\VAR{}` / `\\BLOCK{}` sınırlayıcıları kullanılır. Metnin matematik
dışındaki kısmı kaçışlanır; `$...$` parçaları olduğu gibi kalır.
"""

from __future__ import annotations

import jinja2

from questioncrator.export.booklet import LETTERS, Booklet, answer_key
from questioncrator.export.text import split_math

_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}",
}

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


def escape_text(text: str) -> str:
    out: list[str] = []
    for is_math, part in split_math(text):
        if is_math:
            out.append(f"${part}$")
        else:
            out.append("".join(_SPECIAL.get(ch, ch) for ch in part.replace(r"\$", "$")).replace(
                "$", r"\$"
            ))
    return "".join(out)


def render_exam_tex(booklet: Booklet, title: str) -> str:
    return _ENV.get_template("exam.tex.j2").render(
        booklet=booklet, title=escape_text(title), escape=escape_text, letters=LETTERS
    )


def render_answers_tex(booklet: Booklet, title: str) -> str:
    return _ENV.get_template("answers.tex.j2").render(
        booklet=booklet,
        title=escape_text(title),
        key=[(n, a, len(a) == 1 and a in LETTERS) for n, a in answer_key(booklet)],
    )
```

`export/templates/exam.tex.j2`:
```
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage[a4paper,margin=2cm]{geometry}
\pagestyle{empty}
\begin{document}
\begin{center}{\Large \textbf{\VAR{title}}}\\[0.3em]Kitapçık \VAR{booklet.name}\end{center}
\noindent Ad Soyad: \hrulefill\quad Sınıf: \rule{2cm}{0.4pt}\quad Tarih: \rule{2.5cm}{0.4pt}
\vspace{1em}
\begin{enumerate}
\BLOCK{for item in booklet.items}
  \item \VAR{escape(item.question.text)}
\BLOCK{if item.choices}
  \\[0.4em]
\BLOCK{for choice in item.choices}
  \VAR{letters[loop.index0]}) $\VAR{choice}$\quad
\BLOCK{endfor}
  \vspace{1.2em}
\BLOCK{else}
  \vspace{3cm}
\BLOCK{endif}
\BLOCK{endfor}
\end{enumerate}
\end{document}
```

`export/templates/answers.tex.j2`:
```
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage[a4paper,margin=2cm]{geometry}
\pagestyle{empty}
\begin{document}
\begin{center}{\Large \textbf{\VAR{title} --- Cevap Anahtarı}}\\[0.3em]Kitapçık \VAR{booklet.name}\end{center}
\vspace{1em}
\begin{itemize}
\BLOCK{for number, answer, is_letter in key}
\BLOCK{if is_letter}
  \item[] \VAR{number}. \VAR{answer}
\BLOCK{else}
  \item[] \VAR{number}. $\VAR{answer}$
\BLOCK{endif}
\BLOCK{endfor}
\end{itemize}
\end{document}
```

- [ ] **Adım 6: `docx.py`**

```python
"""Kitapçıktan Word belgesi üretir; matematik gerçek Word denklemi olarak yazılır.

LaTeX -> MathML (`latex2mathml`) -> OMML (`mathml2omml`). Dönüşüm
başarısız olursa parça düz metin olarak yazılır: belge asla yarım kalmaz.
"""

from __future__ import annotations

import io

import latex2mathml.converter
import mathml2omml
from docx import Document
from docx.oxml import parse_xml
from docx.shared import Pt

from questioncrator.export.booklet import LETTERS, Booklet, answer_key
from questioncrator.export.text import split_math

_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def latex_to_omml(latex: str):  # noqa: ANN201 — lxml öğesi
    try:
        mathml = latex2mathml.converter.convert(latex)
        omml = mathml2omml.convert(mathml)
        if "xmlns:m=" not in omml:
            omml = omml.replace("<m:oMath", f'<m:oMath xmlns:m="{_M_NS}"', 1)
        return parse_xml(omml)
    except Exception:  # noqa: BLE001 — her dönüşüm hatası düz metne düşer
        return None


def _write_math(paragraph, latex: str) -> None:
    element = latex_to_omml(latex)
    if element is None:
        paragraph.add_run(latex)
    else:
        paragraph._p.append(element)


def _write_text(paragraph, text: str) -> None:
    for is_math, part in split_math(text):
        if is_math:
            _write_math(paragraph, part)
        else:
            paragraph.add_run(part.replace(r"\$", "$"))


def render_exam_docx(booklet: Booklet, title: str, *, with_answers: bool) -> bytes:
    document = Document()
    document.styles["Normal"].font.size = Pt(11)
    heading = title if not with_answers else f"{title} — Cevap Anahtarı"
    document.add_heading(heading, level=1)
    document.add_paragraph(f"Kitapçık {booklet.name}")

    if with_answers:
        for number, answer in answer_key(booklet):
            paragraph = document.add_paragraph(f"{number}. ")
            if len(answer) == 1 and answer in LETTERS:
                paragraph.add_run(answer)
            else:
                _write_math(paragraph, answer)
    else:
        document.add_paragraph("Ad Soyad: ____________________   Sınıf: ______   Tarih: ________")
        for item in booklet.items:
            paragraph = document.add_paragraph(f"{item.number}. ")
            _write_text(paragraph, item.question.text)
            for index, choice in enumerate(item.choices):
                option = document.add_paragraph(f"    {LETTERS[index]}) ")
                _write_math(option, choice)
            if not item.choices:
                for _ in range(4):
                    document.add_paragraph("")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
```

Uygulayıcıya: `mathml2omml.convert` çıktısının tam biçimini (kök öğe, ad alanı bildirimi) önce bir REPL'de gör; yukarıdaki ad alanı ekleme satırı gerçek çıktıya göre ayarlanmalı. Hedef: `word/document.xml` içinde `<m:oMath` bulunması ve belgenin `python-docx` ile yeniden okunabilmesi.

- [ ] **Adım 7: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS (pdflatex yoksa 1 skipped).

- [ ] **Adım 8: Commit**

```bash
git add pyproject.toml questioncrator/export tests/test_export_booklet.py tests/test_export_latex.py tests/test_export_docx.py
git commit -m "feat(export): A/B kitapçık, LaTeX ve gerçek denklemli Word çıktısı"
```

---

## Plan A Bitiş Kontrolü

- [ ] `.venv/bin/pytest -q` tamamen yeşil, `.venv/bin/ruff check .` temiz.
- [ ] RCE probu `UnsafeExpression` veriyor; hata metninde çalışma dizini görünmüyor.
- [ ] `tests/test_topic_agnostic.py` geçiyor.
- [ ] `tests/data/ornek_havuz.md` üç konusu için: şablon çıkar → `generate_batch` → her soru metni yer tutucusuz, en az birinde 5 şık var (elle bir betikle gözlemlenir, rapora eklenir).
- [ ] Bağımsız kod incelemesi (tüm plan aralığı) yapılır, bulgular ikinci geçişte doğrulanır, doğrulananlar düzeltilir.
