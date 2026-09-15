# Plan B — Hesaplar, Servisler, HTTP API, Alım, LLM, Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan A çekirdeğini çok kiracılı, kimlik doğrulamalı bir FastAPI arka ucuna dönüştürmek: hesap/çalışma alanı yönetimi, HTTP'den bağımsız servis katmanı, tüm spec §8 uç noktaları, dosya alımı (md/txt/docx/pdf/görsel), LLM katmanı (Anthropic SDK, anahtar yoksa kapalı), demo havuzu ve CLI.

**Architecture:** `questioncrator/services/*` HTTP bilmez; `conn`, `now`, `rng`/`seed`, `actor` alır ve Plan A modüllerini çağırır. Ağır SymPy işleri `services/jobs.py` içindeki modül düzeyi fonksiyonlarla `sandbox.run` üzerinden koşar. `questioncrator/api/*` ince katmandır: oturum çözer, çalışma alanı bağlantısını açar, pydantic şemalarıyla servisleri çağırır. Hesap verisi `accounts.db`'de, her çalışma alanı `workspaces/<id>.db`'de.

**Tech Stack:** Python 3.11+, FastAPI, pydantic v2, uvicorn, python-multipart, httpx (TestClient), pypdf, python-docx, anthropic (resmi SDK), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-15-urun-v1-design.md` · Önkoşul: Plan A (`docs/superpowers/plans/2026-09-15-plan-a-cekirdek-motor.md`) tamamlanmış olmalı.

## Global Constraints

- Plan A'nın tüm Global Constraints maddeleri aynen geçerlidir (konu bağımsızlığı bekçisi `questioncrator/**/*.py` — API ve servisler dahil; `from __future__ import annotations`; Türkçe metin/İngilizce tanımlayıcı; `rng`/`now`/`id_factory` enjeksiyonu; Co-Authored-By yok).
- **Kiracı izolasyonu:** bir çalışma alanının verisine yalnız o çalışma alanının üyesinin oturumuyla erişilir; başka çalışma alanının kaydı her zaman **404** döner (403 değil — varlık sızdırılmaz).
- **Hata biçimi:** `{"detail": "<Türkçe mesaj>"}`. Doğrulama 422, yetkisiz 401, rol yetersiz 403, yok 404, çakışma 409, istek sınırı 429, sandbox zaman aşımı 504.
- **Oturum çerezi:** ad `qc_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` yalnız `QC_COOKIE_SECURE=1` iken; ömür 30 gün, her doğrulanmış istekte kalan süre 15 günün altındaysa uzatılır.
- **Parola:** `hashlib.scrypt(n=2**14, r=8, p=1, dklen=32)`, 16 bayt tuz; saklama biçimi `scrypt$<tuz_hex>$<özet_hex>`; en az 8 karakter; karşılaştırma `hmac.compare_digest`.
- **Giriş sınırı:** (e-posta küçük harf, istemci IP) başına 600 sn'de 10 başarısız deneme → 429.
- **Yükleme:** en fazla 15 MB; türler `.md .txt .docx .pdf .png .jpg .jpeg`; diğerleri 422.
- **Ortam değişkenleri:** `QC_DATA_DIR` (varsayılan `./data`), `QC_COOKIE_SECURE` (`0`), `QC_ALLOW_REGISTRATION` (`1`), `ANTHROPIC_API_KEY` (yoksa LLM kapalı), `QC_LLM_MODEL` (`claude-opus-5`), `QC_SANDBOX` (`process`).
- **LLM:** resmi `anthropic` Python SDK'sı; ham HTTP yok. LLM çıktısı asla doğrulayıcıyı atlayamaz (spec K7).
- **Testler ağ çağrısı yapmaz:** LLM testleri `ScriptedLLMClient` ile; `tests/conftest.py` `QC_SANDBOX=inline` varsayılanı Plan A'da kuruldu.
- **Komutlar:** `.venv/bin/pytest -q`, `.venv/bin/ruff check .`.

---

## Dosya Yapısı

```
questioncrator/
  config.py                 Settings (ortamdan), get_settings()
  accounts.py               accounts.db şeması + kullanıcı/çalışma alanı/üyelik/davet/oturum
  security.py               hash_password, verify_password, new_token, token_hash, LoginRateLimiter
  storage.py                çalışma alanı DB yolu, open_workspace, create/delete/backup
  services/
    __init__.py
    errors.py               NotFound, Conflict, Invalid (Türkçe mesajlı servis hataları)
    jobs.py                 sandbox'ta koşan saf işler: extract_job, preview_job, generate_job
    pool.py                 havuz: özet, liste, alım, elle ekleme, düzenleme, silme, önizleme
    cards.py                üretim, bekleyenler, değerlendirme, geri alma, soru bankası, arşiv
    exams.py                sınav/çalışma kağıdı oluşturma, kitapçık görünümü, docx/tex
    students.py             öğrenci CRUD, öğrenciye üretim, geçmiş, çalışma kağıdı
    dashboard.py            panel verisi (learning_stats + sayaçlar)
    demo.py                 demo havuzunu çalışma alanına yükleme
  ingest/
    documents.py            txt/docx/pdf -> düz metin; split_numbered_questions
  llm/
    __init__.py
    client.py               LLMClient protokolü, NullLLMClient, ScriptedLLMClient, LLMNotConfigured, get_llm_client
    anthropic_client.py     AnthropicLLMClient (resmi SDK, JSON şema çıktısı, görsel)
    tasks.py                structure_questions, suggest_recipe, dress_question, LLMTaskFailed
  demo/
    __init__.py
    havuz.md                ≥30 reçeteli soru, ≥8 kazanım
  api/
    __init__.py
    app.py                  create_app(settings) — yönlendiriciler, hata eşleme, SPA sunumu
    deps.py                 get_settings, get_accounts, current_auth, workspace_conn, require_owner
    schemas.py              pydantic istek/yanıt modelleri
    routes_auth.py          /api/auth/*
    routes_workspace.py     /api/workspace/*
    routes_pool.py          /api/pool/*
    routes_cards.py         /api/cards/*, /api/questions/*
    routes_exams.py         /api/exams/*
    routes_students.py      /api/students/*
    routes_system.py        /api/system/*, /api/stats
  cli.py                    questioncrator serve | create-user | set-password | backup
tests/
  api/conftest.py           uygulama + istemci fikstürleri (tmp veri dizini, inline sandbox)
  test_security.py, test_accounts.py, test_storage.py
  test_services_pool.py, test_services_cards.py, test_services_exams.py, test_services_students.py
  test_ingest_documents.py, test_llm.py, test_demo.py, test_cli.py
  api/test_auth.py, api/test_workspace.py, api/test_pool.py, api/test_cards.py,
  api/test_exams.py, api/test_students.py, api/test_isolation.py
```

Görev sırası: 1 güvenlik+config+hesaplar · 2 depolama+servis hataları+işler · 3 havuz servisi · 4 kart servisi · 5 sınav+öğrenci+panel servisleri · 6 API iskeleti + auth + çalışma alanı · 7 havuz/kart/soru uç noktaları · 8 sınav/öğrenci/panel/sistem uç noktaları + SPA · 9 belge alımı · 10 LLM katmanı + uç noktaları · 11 demo havuzu + kayıtta yükleme · 12 CLI + bağımlılık temizliği + README.

---
### Task 1: Güvenlik yardımcıları, ayarlar ve hesap veritabanı

**Files:**
- Create: `questioncrator/config.py`, `questioncrator/security.py`, `questioncrator/accounts.py`
- Test: `tests/test_security.py`, `tests/test_accounts.py`

**Interfaces:**
- Produces:
  - `config.Settings(data_dir: Path, cookie_secure: bool, allow_registration: bool, anthropic_api_key: str | None, llm_model: str)` — frozen dataclass; `config.Settings.from_env(env: Mapping[str, str] | None = None) -> Settings`
  - `security.hash_password(password: str) -> str`, `security.verify_password(password: str, stored: str) -> bool`
  - `security.new_token() -> str` (32 bayt, `secrets.token_urlsafe`), `security.token_hash(token: str) -> str` (SHA-256 hex)
  - `security.new_invite_code() -> str` — 10 karakter, alfabe `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (karışan harf yok)
  - `security.LoginRateLimiter(max_failures: int = 10, window_seconds: float = 600, clock: Callable[[], float] = time.monotonic)` — `is_blocked(key) -> bool`, `record_failure(key)`, `reset(key)`; iş parçacığı güvenli
  - `accounts.MIN_PASSWORD_LENGTH = 8`, `accounts.SESSION_DAYS = 30`, `accounts.SESSION_REFRESH_BELOW_DAYS = 15`, `accounts.INVITE_DAYS = 7`
  - `accounts.User(id, email, name, created_at)`, `accounts.Workspace(id, name, created_at)`, `accounts.Member(user: User, role: str)`, `accounts.Auth(user: User, workspace: Workspace, role: str, session_expires_at: str)`
  - `accounts.AccountError(ValueError)` — Türkçe mesajlı; alt sınıflar `EmailTaken`, `InvalidCredentials`, `InvalidInvite`
  - `accounts.connect_accounts(path) -> sqlite3.Connection` (şema + `foreign_keys=ON`, dosyaysa WAL)
  - `accounts.register(conn, *, email, name, password, workspace_name, now: datetime, id_factory) -> tuple[User, Workspace]` — kullanıcı `owner` olur
  - `accounts.authenticate(conn, *, email, password) -> User` — hatalıysa `InvalidCredentials("E-posta ya da parola hatalı.")`
  - `accounts.create_session(conn, user_id, *, now: datetime) -> tuple[str, str]` → (açık belirteç, `expires_at` ISO)
  - `accounts.resolve_session(conn, token, *, now: datetime) -> Auth | None` — süresi dolmuşsa siler ve `None`; kalan < 15 gün ise 30 güne uzatır
  - `accounts.delete_session(conn, token) -> None`, `accounts.delete_user_sessions(conn, user_id) -> None`
  - `accounts.create_invite(conn, workspace_id, *, role: str, created_by: str, now: datetime) -> str`
  - `accounts.join_with_invite(conn, *, code, email, name, password, now: datetime, id_factory) -> tuple[User, Workspace]` — tek kullanımlık, süresi dolmuş/kullanılmış → `InvalidInvite("Davet kodu geçersiz ya da süresi dolmuş.")`
  - `accounts.list_members(conn, workspace_id) -> list[Member]`, `accounts.remove_member(conn, workspace_id, user_id) -> None` (son owner silinemez → `AccountError("Çalışma alanının son yöneticisi çıkarılamaz.")`; kullanıcı ve oturumları da silinir)
  - `accounts.rename_workspace(conn, workspace_id, name) -> Workspace`, `accounts.delete_workspace(conn, workspace_id) -> list[str]` (silinen kullanıcı kimlikleri)
  - `accounts.set_password(conn, email, password) -> None` (CLI için; oturumları siler)

**Kurallar.**
- E-posta `strip().lower()` ile normalleşir; `@` içermeyen e-posta `AccountError("Geçerli bir e-posta adresi girin.")`.
- Parola 8 karakterden kısa → `AccountError("Parola en az 8 karakter olmalı.")`. Ad ve çalışma alanı adı `strip()` sonrası boş olamaz, 120 karakteri aşamaz.
- `authenticate` kullanıcı yoksa da sahte bir `verify_password` çalıştırır (zamanlama farkı olmasın).
- Kimlikler: kullanıcı `u_`, çalışma alanı `w_` önekli (`ids.new_id`).
- v1'de kullanıcı tek çalışma alanına üyedir; `memberships` birincil anahtarı `user_id`.
- Zaman `datetime` (UTC, tz'li) olarak enjekte edilir; saklama ISO-8601.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_security.py`:
```python
from __future__ import annotations

from questioncrator import security


def test_parola_ozeti_dogrulanir_ve_tuzludur():
    ozet = security.hash_password("gizli-parola")
    assert ozet.startswith("scrypt$")
    assert security.verify_password("gizli-parola", ozet)
    assert not security.verify_password("yanlis-parola", ozet)
    assert security.hash_password("gizli-parola") != ozet


def test_bozuk_ozet_false_doner():
    assert security.verify_password("x", "bozuk") is False


def test_belirtec_ve_ozeti():
    a, b = security.new_token(), security.new_token()
    assert a != b and len(a) >= 40
    assert security.token_hash(a) == security.token_hash(a) != security.token_hash(b)


def test_davet_kodu_bicimi():
    kod = security.new_invite_code()
    assert len(kod) == 10 and set(kod) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def test_giris_sinirlayici_pencere():
    saat = [0.0]
    s = security.LoginRateLimiter(max_failures=3, window_seconds=60, clock=lambda: saat[0])
    for _ in range(3):
        assert not s.is_blocked("k")
        s.record_failure("k")
    assert s.is_blocked("k")
    saat[0] = 61.0
    assert not s.is_blocked("k")
    s.record_failure("k")
    s.reset("k")
    assert not s.is_blocked("k")
```

`tests/test_accounts.py`:
```python
from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest

from questioncrator import accounts
from questioncrator.config import Settings

SIMDI = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path):
    c = accounts.connect_accounts(tmp_path / "accounts.db")
    yield c
    c.close()


def kimlik():
    sayac = itertools.count()
    return lambda prefix: f"{prefix}_{next(sayac):012x}"


def kayit(conn, email="Hoca@Ornek.com", parola="parola123", ids=None):
    ids = ids or kimlik()
    return accounts.register(
        conn, email=email, name="Ayşe Hoca", password=parola,
        workspace_name="Işık Dershanesi", now=SIMDI, id_factory=ids,
    )


def test_kayit_owner_uye_olusturur(conn):
    kullanici, alan = kayit(conn)
    assert kullanici.email == "hoca@ornek.com"
    assert alan.name == "Işık Dershanesi"
    (uye,) = accounts.list_members(conn, alan.id)
    assert uye.role == "owner" and uye.user.id == kullanici.id


@pytest.mark.parametrize(
    ("alanlar", "mesaj"),
    [
        ({"email": "gecersiz"}, "e-posta"),
        ({"parola": "kisa"}, "8 karakter"),
    ],
)
def test_kayit_dogrulamasi(conn, alanlar, mesaj):
    with pytest.raises(accounts.AccountError, match=mesaj):
        kayit(conn, **alanlar)


def test_ayni_eposta_ikinci_kez_alinamaz(conn):
    kayit(conn)
    with pytest.raises(accounts.EmailTaken):
        kayit(conn, email="hoca@ornek.com ", ids=kimlik())


def test_kimlik_dogrulama(conn):
    kayit(conn)
    assert accounts.authenticate(conn, email="HOCA@ornek.com", password="parola123").name == "Ayşe Hoca"
    with pytest.raises(accounts.InvalidCredentials):
        accounts.authenticate(conn, email="hoca@ornek.com", password="yanlis123")
    with pytest.raises(accounts.InvalidCredentials):
        accounts.authenticate(conn, email="yok@ornek.com", password="parola123")


def test_oturum_cozulur_uzatilir_ve_dolar(conn):
    kullanici, alan = kayit(conn)
    belirtec, bitis = accounts.create_session(conn, kullanici.id, now=SIMDI)
    auth = accounts.resolve_session(conn, belirtec, now=SIMDI + timedelta(days=1))
    assert auth.user.id == kullanici.id and auth.workspace.id == alan.id and auth.role == "owner"
    assert auth.session_expires_at == bitis  # 29 gün kaldı: uzatma yok

    uzatilan = accounts.resolve_session(conn, belirtec, now=SIMDI + timedelta(days=20))
    assert uzatilan.session_expires_at == (SIMDI + timedelta(days=50)).isoformat()

    assert accounts.resolve_session(conn, belirtec, now=SIMDI + timedelta(days=51)) is None
    assert accounts.resolve_session(conn, belirtec, now=SIMDI + timedelta(days=21)) is None  # silindi
    assert accounts.resolve_session(conn, "uydurma", now=SIMDI) is None


def test_oturum_veritabaninda_acik_saklanmaz(conn):
    kullanici, _ = kayit(conn)
    belirtec, _ = accounts.create_session(conn, kullanici.id, now=SIMDI)
    satirlar = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert belirtec not in {r[0] for r in satirlar}


def test_cikis_oturumu_siler(conn):
    kullanici, _ = kayit(conn)
    belirtec, _ = accounts.create_session(conn, kullanici.id, now=SIMDI)
    accounts.delete_session(conn, belirtec)
    assert accounts.resolve_session(conn, belirtec, now=SIMDI) is None


def test_davetle_katilim_tek_kullanimlik(conn):
    ids = kimlik()
    sahip, alan = kayit(conn, ids=ids)
    kod = accounts.create_invite(conn, alan.id, role="teacher", created_by=sahip.id, now=SIMDI)
    yeni, katilinan = accounts.join_with_invite(
        conn, code=kod.lower(), email="ogretmen@ornek.com", name="Mehmet", password="parola456",
        now=SIMDI + timedelta(days=1), id_factory=ids,
    )
    assert katilinan.id == alan.id
    roller = {u.user.id: u.role for u in accounts.list_members(conn, alan.id)}
    assert roller == {sahip.id: "owner", yeni.id: "teacher"}
    with pytest.raises(accounts.InvalidInvite):
        accounts.join_with_invite(
            conn, code=kod, email="baska@ornek.com", name="X", password="parola789",
            now=SIMDI + timedelta(days=1), id_factory=ids,
        )


def test_suresi_dolan_davet(conn):
    ids = kimlik()
    sahip, alan = kayit(conn, ids=ids)
    kod = accounts.create_invite(conn, alan.id, role="teacher", created_by=sahip.id, now=SIMDI)
    with pytest.raises(accounts.InvalidInvite):
        accounts.join_with_invite(
            conn, code=kod, email="o@ornek.com", name="O", password="parola456",
            now=SIMDI + timedelta(days=8), id_factory=ids,
        )


def test_uye_cikarma_ve_son_owner_korumasi(conn):
    ids = kimlik()
    sahip, alan = kayit(conn, ids=ids)
    kod = accounts.create_invite(conn, alan.id, role="teacher", created_by=sahip.id, now=SIMDI)
    ogretmen, _ = accounts.join_with_invite(
        conn, code=kod, email="o@ornek.com", name="O", password="parola456", now=SIMDI, id_factory=ids,
    )
    belirtec, _ = accounts.create_session(conn, ogretmen.id, now=SIMDI)
    accounts.remove_member(conn, alan.id, ogretmen.id)
    assert accounts.resolve_session(conn, belirtec, now=SIMDI) is None
    with pytest.raises(accounts.AccountError, match="son yöneticisi"):
        accounts.remove_member(conn, alan.id, sahip.id)


def test_calisma_alani_silme_ve_parola_degistirme(conn):
    sahip, alan = kayit(conn)
    belirtec, _ = accounts.create_session(conn, sahip.id, now=SIMDI)
    accounts.set_password(conn, "hoca@ornek.com", "yeniparola1")
    assert accounts.resolve_session(conn, belirtec, now=SIMDI) is None
    assert accounts.authenticate(conn, email="hoca@ornek.com", password="yeniparola1")
    assert accounts.rename_workspace(conn, alan.id, "Yeni Ad").name == "Yeni Ad"
    assert accounts.delete_workspace(conn, alan.id) == [sahip.id]
    with pytest.raises(accounts.InvalidCredentials):
        accounts.authenticate(conn, email="hoca@ornek.com", password="yeniparola1")


def test_ayarlar_ortamdan(tmp_path):
    s = Settings.from_env({"QC_DATA_DIR": str(tmp_path), "QC_COOKIE_SECURE": "1",
                           "QC_ALLOW_REGISTRATION": "0", "ANTHROPIC_API_KEY": "k"})
    assert s.data_dir == tmp_path and s.cookie_secure and not s.allow_registration
    assert s.anthropic_api_key == "k" and s.llm_model == "claude-opus-5"
    varsayilan = Settings.from_env({})
    assert varsayilan.allow_registration and varsayilan.anthropic_api_key is None
```

Not: `kimlik()` test yardımcısı `id_factory(prefix)` imzasını kullanır — bu yüzden `accounts` içindeki `id_factory` tipi `Callable[[str], str]`'dir (önek alır), üretimde `ids.new_id` doğrudan verilir.

- [ ] **Adım 2: Başarısız olduğunu doğrula**

Run: `.venv/bin/pytest tests/test_security.py tests/test_accounts.py -q`
Expected: FAIL — `ModuleNotFoundError: questioncrator.security`

- [ ] **Adım 3: `config.py`**

```python
"""Uygulama ayarları: yalnız ortam değişkenlerinden okunur."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LLM_MODEL = "claude-opus-5"


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cookie_secure: bool = False
    allow_registration: bool = True
    anthropic_api_key: str | None = None
    llm_model: str = DEFAULT_LLM_MODEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            data_dir=Path(env.get("QC_DATA_DIR") or "data"),
            cookie_secure=_flag(env.get("QC_COOKIE_SECURE"), False),
            allow_registration=_flag(env.get("QC_ALLOW_REGISTRATION"), True),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            llm_model=env.get("QC_LLM_MODEL") or DEFAULT_LLM_MODEL,
        )
```

- [ ] **Adım 4: `security.py`**

```python
"""Parola özeti, oturum belirteci ve giriş denemesi sınırlaması."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LEN = 32
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_LEN,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _scrypt(password, bytes.fromhex(salt_hex))
    except ValueError:
        return False
    return hmac.compare_digest(expected, actual)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(10))


class LoginRateLimiter:
    """Anahtar başına kayan pencerede başarısız deneme sayar (tek süreç, bellekte)."""

    def __init__(
        self,
        max_failures: int = 10,
        window_seconds: float = 600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = self._clock() - self._window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key] = [*self._recent(key), self._clock()]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
```

- [ ] **Adım 5: `accounts.py`** — şema ve fonksiyonlar

Şema:
```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id      TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('owner', 'teacher'))
);
CREATE TABLE IF NOT EXISTS invites (
    code         TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('owner', 'teacher')),
    created_by   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    used_at      TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
```

Uygulama gereksinimleri (kod uygulayıcıya aittir, davranış testlerle ve Interfaces bloğuyla bağlıdır):
- `register` ve `join_with_invite` tek işlemde (`with conn:`) kullanıcı + (çalışma alanı) + üyelik yazar; `sqlite3.IntegrityError` e-posta tekilliğinden gelirse `EmailTaken("Bu e-posta adresiyle zaten bir hesap var.")`.
- `authenticate` kullanıcı yoksa `security.verify_password(password, _DUMMY_HASH)` çalıştırır; `_DUMMY_HASH` modül yüklenirken bir kez `hash_password` ile üretilir.
- `resolve_session`: `token_hash` ile satırı `users`/`memberships`/`workspaces` join'iyle okur; `expires_at <= now` ise satırı siler ve `None`; `expires_at - now < 15 gün` ise `expires_at = now + 30 gün` yazar.
- `join_with_invite`: kod `upper().strip()`; `used_at IS NULL AND expires_at > now` şartı; başarıda `used_at = now`.
- `remove_member`: hedef owner ise ve çalışma alanında başka owner yoksa hata; aksi halde kullanıcı satırı silinir (CASCADE üyelik + oturum).
- `delete_workspace`: üyelerin kullanıcı satırlarını ve çalışma alanını siler, silinen kullanıcı kimliklerini sıralı döndürür.
- Tüm okuma fonksiyonları dataclass döndürür; `sqlite3.Row` dışarı sızmaz.

- [ ] **Adım 6: Testleri çalıştır**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: PASS. (scrypt n=2^14 test başına ~50 ms; paket süresi kabul edilebilir.)

- [ ] **Adım 7: Commit**

```bash
git add questioncrator/config.py questioncrator/security.py questioncrator/accounts.py tests/test_security.py tests/test_accounts.py
git commit -m "feat(accounts): ayarlar, parola/oturum güvenliği ve hesap veritabanı"
```

---
### Task 2: Çalışma alanı depolaması, servis hataları ve sandbox işleri

**Files:**
- Create: `questioncrator/storage.py`, `questioncrator/services/__init__.py` (`"""HTTP'den bağımsız uygulama servisleri."""`), `questioncrator/services/errors.py`, `questioncrator/services/jobs.py`
- Test: `tests/test_storage.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: `config.Settings`, `db.connect`, `sandbox.run/SandboxTimeout/SandboxCrashed`, `extract.extract_template/NoParametersFound`, `checks.evaluate_answer/EvaluationFailed`, `engine.GenerationRequest/generate_from_template/generate_batch`, `ids.new_id`
- Produces:
  - `storage.accounts_path(settings) -> Path` (`data_dir/accounts.db`), `storage.workspace_path(settings, workspace_id) -> Path` (`data_dir/workspaces/<id>.db`; kimlik `^w_[0-9a-f]{12}$` değilse `ValueError`)
  - `storage.open_workspace(settings, workspace_id) -> sqlite3.Connection` (dizinleri oluşturur, `db.connect(..., check_same_thread=False)`)
  - `storage.delete_workspace_files(settings, workspace_id) -> None` (`.db`, `-wal`, `-shm`; yoksa sessiz)
  - `storage.backup_workspace(settings, workspace_id) -> bytes` (sqlite `backup` API ile tutarlı kopya)
  - `errors.ServiceError(Exception)` (`.message: str`), alt sınıflar: `NotFound`, `Conflict`, `Invalid`, `Timeout`, `Unavailable`
  - `jobs.EXTRACT_TIMEOUT = 20.0`, `jobs.PREVIEW_TIMEOUT = 20.0`, `jobs.GENERATE_TIMEOUT = 120.0`
  - `jobs.PreviewVariant(text: str, answer_latex: str, choices: tuple[str, ...], correct_index: int | None)`
  - `jobs.RecipePreview(ok: bool, answer_latex: str | None, parameter_count: int, difficulty: float | None, variants: tuple[PreviewVariant, ...], error: str | None)`
  - `jobs.extract_job(source: SourceQuestion, template_id: str) -> Template | str` — başarısızsa Türkçe neden dizesi
  - `jobs.preview_job(text: str, recipe: str, seed: int, samples: int = 3) -> RecipePreview`
  - `jobs.generate_job(templates: list[Template], request: GenerationRequest, *, seed: int, now: str, seen_answer_keys: set[str], weights: dict[str, float], difficulties: dict[str, float]) -> list[GeneratedQuestion]` — soru kimlikleri `ids.new_id("q")` (rastgele, `secrets`), örnekleme `random.Random(seed)`
  - `jobs.run(fn, *args, timeout: float, **kwargs)` — `sandbox.run` sarmalayıcısı; `SandboxTimeout` → `errors.Timeout("İşlem çok uzun sürdü; reçeteyi sadeleştirip tekrar deneyin.")`, `SandboxCrashed` → `errors.Unavailable("Hesaplama servisi geçici olarak yanıt vermedi, tekrar deneyin.")`

**Kurallar / gerekçeler.**
- Soru kimlikleri servis sınırında kriptografik rastgeledir: aynı tohumla iki üretim partisi aynı kimliği üretip upsert ile birbirini ezemez. (Ruling: Plan A `id_factory` sözleşmesi korunur; deterministik kimlik yalnız çekirdek birim testlerinde kullanılır.)
- `extract_job` hata dizeleri: reçetesiz → `"Cevap reçetesi yok."`; `NoParametersFound` → `"Reçetede değiştirilebilir sayı bulunamadı."`; `EvaluationFailed`/zaman aşımı → `"Reçete hesaplanamadı: <neden>"`; tohum cevabı `answer_problems` döndürürse → `"Reçetenin cevabı kullanılamaz: <ilk not>"`.
- `preview_job`: önce `evaluate_answer(recipe)`; hata → `ok=False, error="Reçete hesaplanamadı: ..."`. Sonra şablon çıkarımı; `NoParametersFound` ise `ok=True, parameter_count=0, variants=()` ve `error="Reçetede değiştirilebilir sayı yok; bu soru olduğu gibi kalır, varyant üretilemez."`. Aksi halde `generate_from_template(count=samples, rng=Random(seed), seen_answer_keys=set(), id_factory=lambda: "onizleme")` ile varyantlar; `difficulty = template.difficulty_estimate`.
- `jobs.py` içindeki tüm fonksiyonlar modül düzeyindedir ve yalnız pickle'lanabilir değerler alır/döndürür (sandbox işçisi süreç sınırı).

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_storage.py`:
```python
from __future__ import annotations

import sqlite3

import pytest

from questioncrator import db, storage
from questioncrator.config import Settings

ALAN = "w_0123456789ab"


@pytest.fixture
def ayarlar(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.mark.parametrize("kimlik", ["../x", "w_123", "w_0123456789ag", "", "w_0123456789ab/../../y"])
def test_gecersiz_calisma_alani_kimligi_reddedilir(ayarlar, kimlik):
    with pytest.raises(ValueError):
        storage.workspace_path(ayarlar, kimlik)


def test_ac_olusturur_ve_goc_eder(ayarlar):
    conn = storage.open_workspace(ayarlar, ALAN)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    conn.close()
    assert storage.workspace_path(ayarlar, ALAN).exists()
    assert storage.accounts_path(ayarlar) == ayarlar.data_dir / "accounts.db"


def test_yedek_gecerli_sqlite(ayarlar, tmp_path):
    conn = storage.open_workspace(ayarlar, ALAN)
    conn.execute("INSERT INTO students (id, alias, created_at) VALUES ('st_1', 'Ali', 'x')")
    conn.commit()
    veri = storage.backup_workspace(ayarlar, ALAN)
    conn.close()
    hedef = tmp_path / "yedek.db"
    hedef.write_bytes(veri)
    kopya = sqlite3.connect(hedef)
    assert kopya.execute("SELECT alias FROM students").fetchall() == [("Ali",)]
    kopya.close()


def test_silme_dosyalari_kaldirir(ayarlar):
    storage.open_workspace(ayarlar, ALAN).close()
    storage.delete_workspace_files(ayarlar, ALAN)
    assert not storage.workspace_path(ayarlar, ALAN).exists()
    storage.delete_workspace_files(ayarlar, ALAN)  # ikinci kez sessiz
```

`tests/test_jobs.py`:
```python
from __future__ import annotations

import pytest

from questioncrator import sandbox
from questioncrator.generation.engine import GenerationRequest
from questioncrator.models import SourceQuestion
from questioncrator.services import errors, jobs

SIMDI = "2026-09-15T10:00:00+00:00"


def kaynak(recete="diff(3*x**2 + 5*x, x)", metin="$f(x)=3x^2+5x$ türevini bulunuz."):
    return SourceQuestion(id="s_1", text=metin, recipe=recete, objective="k1")


def test_extract_job_basari():
    sablon = jobs.extract_job(kaynak(), "t_1")
    assert not isinstance(sablon, str)
    assert sablon.id == "t_1" and sablon.source_id == "s_1"


@pytest.mark.parametrize(
    ("recete", "parca"),
    [(None, "reçetesi yok"), ("x**2", "değiştirilebilir sayı"), ('sympify("x") + 2', "hesaplanamadı"),
     ("zoo + 3", "kullanılamaz")],
)
def test_extract_job_hata_dizesi(recete, parca):
    sonuc = jobs.extract_job(kaynak(recete=recete), "t_1")
    assert isinstance(sonuc, str) and parca in sonuc


def test_preview_job_varyant_uretir():
    onizleme = jobs.preview_job("$f(x)=3x^2+5x$", "diff(3*x**2 + 5*x, x)", seed=1)
    assert onizleme.ok and onizleme.answer_latex == "6 x + 5"
    assert onizleme.parameter_count == 2 and len(onizleme.variants) == 3
    assert all("{p" not in v.text for v in onizleme.variants)


def test_preview_job_parametresiz_ve_hatali():
    sabit = jobs.preview_job("x kare", "x**2", seed=1)
    assert sabit.ok and sabit.parameter_count == 0 and sabit.variants == () and sabit.error
    bozuk = jobs.preview_job("?", "diff(", seed=1)
    assert not bozuk.ok and "hesaplanamadı" in bozuk.error


def test_generate_job_rastgele_kimlikli_sorular():
    sablon = jobs.extract_job(kaynak(), "t_1")
    sorular = jobs.generate_job(
        [sablon], GenerationRequest(total=2), seed=3, now=SIMDI,
        seen_answer_keys=set(), weights={}, difficulties={},
    )
    assert len(sorular) == 2
    assert all(s.id.startswith("q_") and len(s.id) == 14 for s in sorular)


def test_run_sandbox_hatalarini_esler(monkeypatch):
    def zaman_asimi(*a, **k):
        raise sandbox.SandboxTimeout("x")

    def cokme(*a, **k):
        raise sandbox.SandboxCrashed("x")

    monkeypatch.setattr(sandbox, "run", zaman_asimi)
    with pytest.raises(errors.Timeout):
        jobs.run(pow, 2, 3, timeout=1)
    monkeypatch.setattr(sandbox, "run", cokme)
    with pytest.raises(errors.Unavailable):
        jobs.run(pow, 2, 3, timeout=1)
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — Run: `.venv/bin/pytest tests/test_storage.py tests/test_jobs.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Adım 3: `services/errors.py`**

```python
"""Servis katmanının Türkçe mesajlı hata türleri; API bunları HTTP kodlarına eşler."""

from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(ServiceError):
    """İstenen kayıt bu çalışma alanında yok (404)."""


class Conflict(ServiceError):
    """İşlem mevcut durumla çelişiyor (409)."""


class Invalid(ServiceError):
    """Girdi iş kurallarına uymuyor (422)."""


class Timeout(ServiceError):
    """Hesaplama süre sınırını aştı (504)."""


class Unavailable(ServiceError):
    """Bağımlı servis (LLM, hesaplama işçisi) kullanılamıyor (503)."""
```

- [ ] **Adım 4: `storage.py`**

```python
"""Veri dizini düzeni: merkezi hesap veritabanı + çalışma alanı başına SQLite dosyası."""

from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

from questioncrator import db
from questioncrator.config import Settings

_WORKSPACE_ID = re.compile(r"w_[0-9a-f]{12}")


def accounts_path(settings: Settings) -> Path:
    return settings.data_dir / "accounts.db"


def workspace_path(settings: Settings, workspace_id: str) -> Path:
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise ValueError(f"geçersiz çalışma alanı kimliği: {workspace_id!r}")
    return settings.data_dir / "workspaces" / f"{workspace_id}.db"


def open_workspace(settings: Settings, workspace_id: str) -> sqlite3.Connection:
    path = workspace_path(settings, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    return db.connect(path, check_same_thread=False)


def delete_workspace_files(settings: Settings, workspace_id: str) -> None:
    base = workspace_path(settings, workspace_id)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{base}{suffix}").unlink(missing_ok=True)


def backup_workspace(settings: Settings, workspace_id: str) -> bytes:
    source = open_workspace(settings, workspace_id)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            target_path = Path(tmp) / "yedek.db"
            target = sqlite3.connect(target_path)
            try:
                source.backup(target)
            finally:
                target.close()
            return target_path.read_bytes()
    finally:
        source.close()
```

- [ ] **Adım 5: `services/jobs.py`** — Interfaces ve Kurallar bloğuna göre yaz. İskelet:

```python
"""İzole değerlendirme sürecinde koşan saf işler.

Bu fonksiyonlar veritabanına dokunmaz; yalnız pickle'lanabilir değer alıp
döndürür. Servisler bunları `run` ile sandbox işçisine gönderir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from questioncrator import sandbox
from questioncrator.generation.engine import GenerationRequest, generate_batch, generate_from_template
from questioncrator.ids import new_id
from questioncrator.mathenv import EvaluationTimeout
from questioncrator.models import GeneratedQuestion, SourceQuestion, Template
from questioncrator.services import errors
from questioncrator.templating.extract import NoParametersFound, extract_template
from questioncrator.verification.checks import EvaluationFailed, answer_problems, evaluate_answer

# ... sabitler, PreviewVariant, RecipePreview, extract_job, preview_job, generate_job, run
```

`extract_job` tohum cevabını `evaluate_answer` ile ayrıca hesaplayıp `answer_problems(answer)` boş değilse ilk notu döndürür (şablon üretime giremeyecek bir kaynağı erkenden yakalamak için). `extract_template` içindeki `parse_with_timeout` `EvaluationTimeout` fırlatabilir; o da `"Reçete hesaplanamadı: ..."` olur.

- [ ] **Adım 6: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 7: Commit**

```bash
git add questioncrator/storage.py questioncrator/services tests/test_storage.py tests/test_jobs.py
git commit -m "feat(services): çalışma alanı depolaması, servis hataları ve sandbox işleri"
```

---
### Task 3: Havuz servisi

**Files:**
- Create: `questioncrator/services/pool.py`
- Test: `tests/test_services_pool.py`

**Interfaces:**
- Consumes: `db.*`, `markdown.parse_pool`, `jobs.run/extract_job/preview_job/EXTRACT_TIMEOUT/PREVIEW_TIMEOUT/RecipePreview`, `errors.*`, `ids.new_id`
- Produces:
  - `pool.MAX_TEXT_LENGTH = 5000`, `pool.MAX_OBJECTIVE_LENGTH = 100`
  - `pool.PoolSummary(total: int, ready: int, needs_review: int, templates_by_status: dict[str, int], by_objective: dict[str, int])`
  - `pool.SourceView(source: SourceQuestion, template_status: str | None)` — kaynağın en yeni etkin/deneme şablonunun durumu, yoksa `None`
  - `pool.IngestResult(added: int, templates: int, needs_review: int, problems: list[tuple[str, str]])` — `(kaynak_kimliği, Türkçe neden)`
  - `pool.pool_summary(conn) -> PoolSummary`
  - `pool.list_sources(conn, *, status: str | None = None) -> list[SourceView]` — `status` `"ready"` | `"needs_review"` | `None`; başka değer `Invalid`
  - `pool.list_objectives(conn) -> list[str]` — kaynak ve şablonlardaki boş olmayan kazanımlar, tekil, alfabetik
  - `pool.ingest_sources(conn, drafts: list[SourceQuestion], *, now: str, origin: str) -> IngestResult`
  - `pool.ingest_markdown(conn, content: str, *, now: str) -> IngestResult`
  - `pool.get_source(conn, source_id) -> SourceView` (yoksa `NotFound("Soru bulunamadı.")`)
  - `pool.create_source(conn, *, text: str, recipe: str | None, answer_text: str | None, objective: str | None, now: str) -> SourceView` (origin `manual`)
  - `pool.update_source(conn, source_id, *, text: str, recipe: str | None, answer_text: str | None, objective: str | None, now: str) -> SourceView`
  - `pool.delete_source(conn, source_id) -> None`
  - `pool.preview_recipe(*, text: str, recipe: str, seed: int) -> RecipePreview`

**Kurallar.**
- Girdi normalleştirme: tüm metin alanları `strip()`; boş dize `None` sayılır (metin hariç). Metin boşsa `Invalid("Soru metni boş olamaz.")`; `MAX_TEXT_LENGTH`'i aşarsa `Invalid("Soru metni en fazla 5000 karakter olabilir.")`; reçete `mathenv.MAX_RECIPE_LENGTH`'i aşarsa `Invalid("Reçete en fazla 2000 karakter olabilir.")`; kazanım 100'ü aşarsa `Invalid("Kazanım en fazla 100 karakter olabilir.")`.
- `ingest_sources`: her taslağa `new_id("s")`, `created_at=now`, `origin=origin` verilir (taslak kimlikleri yok sayılır — ikinci yükleme birinciyi ezemez). Reçeteli her kaynak için `jobs.run(jobs.extract_job, source, new_id("t"), timeout=EXTRACT_TIMEOUT)`:
  - `Template` → şablon kaydedilir, kaynak `needs_review=False, review_note=None`.
  - `str` → kaynak `needs_review=True, review_note=<neden>`, `problems`'a eklenir.
  - Reçetesiz kaynak `needs_review=True, review_note="Cevap reçetesi eksik."`.
  - `jobs.run` `Timeout` yükseltirse o kaynak `needs_review=True, review_note=<hata mesajı>` olur, döngü devam eder.
- `update_source`: kaynağın mevcut tüm `trial`/`active` şablonları `disabled` yapılır (üretilmiş sorular korunur), sonra `ingest_sources` ile aynı çıkarım kuralı tek kaynağa uygulanır (kimlik ve `created_at`, `origin` korunur).
- `pool_summary.by_objective` anahtarı boş kazanım için `"Etiketsiz"`.
- `SourceView.template_status`: kaynağın `disabled` olmayan şablonu varsa onun durumu (`active` öncelikli), yoksa kaynağın şablonu hiç yoksa `None`, tümü kapalıysa `"disabled"`.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_services_pool.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.services import errors, pool

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-09-15T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def yukle(conn):
    return pool.ingest_markdown(conn, VERI.read_text(encoding="utf-8"), now=SIMDI)


def test_markdown_alimi(conn):
    sonuc = yukle(conn)
    assert (sonuc.added, sonuc.templates, sonuc.needs_review) == (4, 3, 1)
    assert len(sonuc.problems) == 0 or all(isinstance(p, tuple) for p in sonuc.problems)
    kaynaklar = db.load_sources(conn)
    assert all(k.id.startswith("s_") and k.origin == "markdown" and k.created_at == SIMDI for k in kaynaklar)
    receteSiz = [k for k in kaynaklar if k.recipe is None]
    assert receteSiz[0].needs_review and receteSiz[0].review_note == "Cevap reçetesi eksik."


def test_ikinci_alim_ezmez(conn):
    yukle(conn)
    yukle(conn)
    assert len(db.load_sources(conn)) == 8
    assert len(db.load_templates(conn)) == 6


def test_ozet_ve_liste_filtresi(conn):
    yukle(conn)
    ozet = pool.pool_summary(conn)
    assert (ozet.total, ozet.ready, ozet.needs_review) == (4, 3, 1)
    assert ozet.templates_by_status == {"trial": 3}
    assert sum(ozet.by_objective.values()) == 4
    assert len(pool.list_sources(conn, status="ready")) == 3
    assert len(pool.list_sources(conn, status="needs_review")) == 1
    assert all(v.template_status == "trial" for v in pool.list_sources(conn, status="ready"))
    with pytest.raises(errors.Invalid):
        pool.list_sources(conn, status="baska")


def test_kazanim_listesi(conn):
    yukle(conn)
    assert pool.list_objectives(conn) == sorted(pool.list_objectives(conn))
    assert "belirsiz" in pool.list_objectives(conn)


def test_elle_ekleme_hatali_recete_kontrole_duser(conn):
    gorunum = pool.create_source(
        conn, text="  Soru  ", recipe="x**2", answer_text="", objective=" k1 ", now=SIMDI,
    )
    k = gorunum.source
    assert k.text == "Soru" and k.answer_text is None and k.objective == "k1"
    assert k.origin == "manual" and k.needs_review and "değiştirilebilir sayı" in k.review_note
    assert gorunum.template_status is None


@pytest.mark.parametrize(
    ("alanlar", "parca"),
    [({"text": "   "}, "boş"), ({"text": "a" * 5001}, "5000"), ({"recipe": "x" * 2001}, "2000"),
     ({"objective": "k" * 101}, "100")],
)
def test_elle_ekleme_dogrulama(conn, alanlar, parca):
    girdi = {"text": "Soru", "recipe": "2*x", "answer_text": None, "objective": None, **alanlar}
    with pytest.raises(errors.Invalid, match=parca):
        pool.create_source(conn, now=SIMDI, **girdi)


def test_duzenleme_eski_sablonu_kapatir_yenisini_uretir(conn):
    ilk = pool.create_source(conn, text="$3x$", recipe="3*x + 1", answer_text=None, objective="k", now=SIMDI)
    (eski,) = db.load_templates_for_source(conn, ilk.source.id)
    guncel = pool.update_source(
        conn, ilk.source.id, text="$5x$", recipe="5*x + 2", answer_text=None, objective="k", now=SIMDI,
    )
    assert guncel.source.id == ilk.source.id and guncel.source.created_at == SIMDI
    sablonlar = {t.id: t.status for t in db.load_templates_for_source(conn, ilk.source.id)}
    assert sablonlar[eski.id] == "disabled"
    assert list(sablonlar.values()).count("trial") == 1
    assert guncel.template_status == "trial" and not guncel.source.needs_review


def test_duzenleme_ve_silme_bulunamaz(conn):
    with pytest.raises(errors.NotFound):
        pool.update_source(conn, "s_yok", text="a", recipe=None, answer_text=None, objective=None, now=SIMDI)
    with pytest.raises(errors.NotFound):
        pool.delete_source(conn, "s_yok")
    with pytest.raises(errors.NotFound):
        pool.get_source(conn, "s_yok")


def test_silme(conn):
    g = pool.create_source(conn, text="$3x$", recipe="3*x + 1", answer_text=None, objective=None, now=SIMDI)
    pool.delete_source(conn, g.source.id)
    assert db.load_sources(conn) == []
    assert {t.status for t in db.load_templates(conn)} == {"disabled"}


def test_zaman_asimi_kaynagi_kontrole_dusurur(conn, monkeypatch):
    from questioncrator.services import jobs

    def zaman_asimi(*a, **k):
        raise errors.Timeout("İşlem çok uzun sürdü")

    monkeypatch.setattr(jobs, "run", zaman_asimi)
    g = pool.create_source(conn, text="Soru", recipe="2*x + 3", answer_text=None, objective=None, now=SIMDI)
    assert g.source.needs_review and "uzun sürdü" in g.source.review_note


def test_onizleme():
    o = pool.preview_recipe(text="$f(x)=3x^2+5x$", recipe="diff(3*x**2 + 5*x, x)", seed=2)
    assert o.ok and len(o.variants) == 3
```

Not: `pool.py`, `jobs.run`'ı `from questioncrator.services import jobs` ile modül üzerinden çağırmalıdır (`jobs.run(...)`), yoksa monkeypatch testi çalışmaz.

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_services_pool.py -q` → FAIL.

- [ ] **Adım 3: `services/pool.py`'yi Interfaces + Kurallar bloğuna göre yaz.** Modül docstring'i: `"""Havuz servisi (Sekme 1): kaynak soruların alımı, düzenlenmesi ve şablona çevrilmesi."""`. Ortak çıkarım adımı tek bir özel fonksiyonda toplanır (`_extract_for(conn, source) -> tuple[SourceQuestion, str | None]`); `ingest_sources`, `create_source`, `update_source` onu çağırır — çıkarım mantığı üç kez yazılmaz.

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/services/pool.py tests/test_services_pool.py
git commit -m "feat(services): havuz servisi — alım, elle ekleme, düzenleme, önizleme"
```

---
### Task 4: Kart servisi (üretim, puanlama, geri alma, soru bankası)

**Files:**
- Create: `questioncrator/services/cards.py`
- Test: `tests/test_services_cards.py`

**Interfaces:**
- Consumes: `db.*`, `engine.GenerationRequest`, `jobs.run/generate_job/GENERATE_TIMEOUT`, `scoring.store.record_review/apply_status_transitions`, `scoring.weights.template_weights`, `scoring.calibration.calibrated_difficulties`, `errors.*`
- Produces:
  - `cards.MAX_BATCH = 50`
  - `cards.Card(question: GeneratedQuestion, objective: str | None, template_status: str, review: Review | None)`
  - `cards.ReviewOutcome(card: Card, transitions: dict[str, str])`
  - `cards.produce_cards(conn, *, count: int, now: str, actor_id: str | None, objectives: list[str] | None = None, target_difficulty: float | None = None, student_id: str | None = None, seed: int | None = None) -> list[Card]`
  - `cards.pending_cards(conn, *, student_id: str | None = None) -> list[Card]`
  - `cards.get_card(conn, question_id) -> Card`
  - `cards.review_card(conn, question_id, *, approved: bool, difficulty: int, quality: int, now: str, actor_id: str | None) -> ReviewOutcome`
  - `cards.undo_review(conn, question_id) -> Card`
  - `cards.question_bank(conn, *, objective: str | None = None, difficulty_min: int | None = None, difficulty_max: int | None = None) -> list[Card]`
  - `cards.set_archived(conn, question_id, archived: bool) -> Card`

**Kurallar.**
- `count` 1..50 değilse `Invalid("Tek seferde 1 ile 50 arasında soru üretilebilir.")`; `target_difficulty` verildiyse 1..10 değilse `Invalid("Hedef zorluk 1 ile 10 arasında olmalı.")`.
- `seed is None` ise `secrets.randbits(32)`.
- `student_id` verilirse: öğrenci yoksa `NotFound("Öğrenci bulunamadı.")`; `avoid_template_ids = db.load_student_template_ids(...)`; soru `student_id` alanı dolar. (Öğrenci varsayılanları — zayıf kazanım, seviye — `students` servisinin işidir; burada yalnız verilen parametreler kullanılır.)
- Üretime uygun şablon yoksa (tümü `disabled` veya kazanım filtresine uyan yok) `Invalid("Üretime hazır soru yok. Önce havuza reçeteli soru ekleyin ya da kazanım filtresini genişletin.")`. Şablon var ama üretim 0 soru döndürdüyse boş liste döner (hata değil — hepsi daha önce üretilmiş olabilir).
- `pending_cards`: arşivlenmemiş, değerlendirilmemiş, `question.student_id == student_id` (None → genel akış) sorular; `created_at, id` sırası.
- `review_card`: `difficulty`/`quality` `int` ve 1..10 değilse `Invalid("Zorluk ve kurgu puanı 1 ile 10 arasında olmalı.")`; soru yoksa `NotFound("Soru bulunamadı.")`; arşivliyse `Conflict("Arşivlenmiş soru puanlanamaz.")`; zaten değerlendirilmişse `Conflict("Bu soru zaten puanlandı; önce geri alın.")`. Kayıt `reviewer_id=actor_id` ile; ardından `apply_status_transitions`.
- `undo_review`: değerlendirme yoksa `Conflict("Bu sorunun geri alınacak bir puanı yok.")`. Şablon durum geçişleri geri alınmaz (bilinçli: geçiş birikmiş sinyalden türetilir, bir sonraki değerlendirmede yeniden hesaplanır — `disabled` bir şablon geri açılmaz; bu, docstring'de belirtilir).
- `question_bank`: onaylı + arşivlenmemiş; zorluk filtresi hocanın verdiği `review.difficulty` üzerinden; sıra: en yeni değerlendirme önce.
- `Card.objective` şablonun kazanımıdır; `template_status` şablonun güncel durumudur.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_services_cards.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.models import Student
from questioncrator.services import cards, errors, pool

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-09-15T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    pool.ingest_markdown(c, VERI.read_text(encoding="utf-8"), now=SIMDI)
    yield c
    c.close()


def uret(conn, **ek):
    return cards.produce_cards(conn, count=ek.pop("count", 6), now=SIMDI, actor_id="u_1", seed=ek.pop("seed", 1), **ek)


def test_uretim_kaydeder_ve_bekleyenlere_duser(conn):
    kartlar = uret(conn)
    assert 0 < len(kartlar) <= 6  # 3 deneme şablonu × 2
    assert {k.question.id for k in cards.pending_cards(conn)} == {k.question.id for k in kartlar}
    assert all(k.question.created_by == "u_1" and k.template_status == "trial" for k in kartlar)


@pytest.mark.parametrize("adet", [0, 51])
def test_adet_siniri(conn, adet):
    with pytest.raises(errors.Invalid):
        uret(conn, count=adet)


def test_hedef_zorluk_siniri(conn):
    with pytest.raises(errors.Invalid):
        uret(conn, target_difficulty=11)


def test_uygun_sablon_yoksa_anlasilir_hata(conn):
    with pytest.raises(errors.Invalid, match="Üretime hazır"):
        uret(conn, objectives=["olmayan-kazanim"])


def test_puanlama_ve_gecis(conn):
    kartlar = uret(conn)
    hedef = kartlar[0].question.template_id
    ayni = [k for k in kartlar if k.question.template_id == hedef][:2]
    cards.review_card(conn, ayni[0].question.id, approved=True, difficulty=5, quality=8, now=SIMDI, actor_id="u_1")
    sonuc = cards.review_card(conn, ayni[1].question.id, approved=True, difficulty=6, quality=9, now=SIMDI, actor_id="u_1")
    assert sonuc.transitions == {hedef: "active"}
    assert sonuc.card.review.reviewer_id == "u_1"
    assert ayni[0].question.id not in {k.question.id for k in cards.pending_cards(conn)}


@pytest.mark.parametrize(("zorluk", "kurgu"), [(0, 5), (5, 11), (5.5, 5)])
def test_puan_dogrulamasi(conn, zorluk, kurgu):
    k = uret(conn)[0]
    with pytest.raises(errors.Invalid):
        cards.review_card(conn, k.question.id, approved=True, difficulty=zorluk, quality=kurgu, now=SIMDI, actor_id=None)


def test_cift_puanlama_ve_geri_alma(conn):
    k = uret(conn)[0]
    cards.review_card(conn, k.question.id, approved=False, difficulty=4, quality=3, now=SIMDI, actor_id=None)
    with pytest.raises(errors.Conflict):
        cards.review_card(conn, k.question.id, approved=True, difficulty=4, quality=3, now=SIMDI, actor_id=None)
    geri = cards.undo_review(conn, k.question.id)
    assert geri.review is None
    assert k.question.id in {c.question.id for c in cards.pending_cards(conn)}
    with pytest.raises(errors.Conflict):
        cards.undo_review(conn, k.question.id)


def test_bulunamayan_soru(conn):
    with pytest.raises(errors.NotFound):
        cards.review_card(conn, "q_yok", approved=True, difficulty=5, quality=5, now=SIMDI, actor_id=None)
    with pytest.raises(errors.NotFound):
        cards.get_card(conn, "q_yok")


def test_soru_bankasi_filtreleri_ve_arsiv(conn):
    kartlar = uret(conn)
    for i, k in enumerate(kartlar[:3]):
        cards.review_card(conn, k.question.id, approved=i != 1, difficulty=3 + i * 3, quality=8,
                          now=f"2026-09-15T10:0{i}:00+00:00", actor_id=None)
    banka = cards.question_bank(conn)
    assert [c.question.id for c in banka] == [kartlar[2].question.id, kartlar[0].question.id]
    assert [c.question.id for c in cards.question_bank(conn, difficulty_min=6)] == [kartlar[2].question.id]
    cards.set_archived(conn, kartlar[2].question.id, True)
    assert [c.question.id for c in cards.question_bank(conn)] == [kartlar[0].question.id]
    with pytest.raises(errors.Conflict):
        cards.review_card(conn, kartlar[2].question.id, approved=True, difficulty=5, quality=5, now=SIMDI, actor_id=None)


def test_ogrenci_baglaminda_uretim(conn):
    db.save_student(conn, Student(id="st_1", alias="Ali", created_at=SIMDI))
    genel = uret(conn)
    ogrenci = uret(conn, student_id="st_1", seed=2)
    assert ogrenci and all(k.question.student_id == "st_1" for k in ogrenci)
    assert {k.question.id for k in cards.pending_cards(conn)} == {k.question.id for k in genel}
    assert {k.question.id for k in cards.pending_cards(conn, student_id="st_1")} == {k.question.id for k in ogrenci}
    with pytest.raises(errors.NotFound):
        uret(conn, student_id="st_yok")
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_services_cards.py -q` → FAIL.

- [ ] **Adım 3: `services/cards.py`'yi yaz.** Docstring: `"""Kart akışı servisi (Sekme 2): üretim, çift puanlı değerlendirme, soru bankası."""`. `Card` oluşturma tek bir `_card(conn, question, templates_by_id, reviews_by_id)` yardımcısında; liste fonksiyonları şablon ve değerlendirmeleri bir kez yükleyip sözlükle eşler (N+1 sorgu yok). `jobs.run` modül üzerinden çağrılır.

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/services/cards.py tests/test_services_cards.py
git commit -m "feat(services): kart servisi — üretim, puanlama, geri alma, soru bankası"
```

---
### Task 5: Sınav, öğrenci ve panel servisleri

**Files:**
- Create: `questioncrator/services/exams.py`, `questioncrator/services/students.py`, `questioncrator/services/dashboard.py`
- Test: `tests/test_services_exams.py`, `tests/test_services_students.py`

**Interfaces:**
- Consumes: `db.*`, `cards.Card/question_bank/produce_cards/pending_cards`, `pool.pool_summary/PoolSummary`, `export.booklet.build_booklets/Booklet`, `export.latex.render_exam_tex/render_answers_tex`, `export.docx.render_exam_docx`, `scoring.stats.learning_stats/LearningStats`, `errors.*`, `ids.new_id`
- Produces (exams):
  - `exams.MAX_QUESTIONS = 100`, `exams.FORMATS = ("mc", "open")`, `exams.BOOKLET_OPTIONS = (("A",), ("A", "B"))`
  - `exams.AutoSelection(count: int, objective_weights: dict[str, int] | None = None, difficulty_min: int | None = None, difficulty_max: int | None = None)`
  - `exams.ExamView(exam: Exam, booklets: list[Booklet], missing_question_ids: list[str])`
  - `exams.create_exam(conn, *, title: str, now: str, actor_id: str | None, rng: random.Random, fmt: str = "mc", booklets: tuple[str, ...] = ("A",), kind: str = "exam", question_ids: list[str] | None = None, auto: AutoSelection | None = None, student_id: str | None = None) -> Exam`
  - `exams.list_exams(conn, *, student_id: str | None = None) -> list[Exam]`
  - `exams.exam_view(conn, exam_id) -> ExamView`
  - `exams.exam_docx(conn, exam_id, *, booklet: str, with_answers: bool) -> tuple[bytes, str]` → (içerik, dosya adı)
  - `exams.exam_tex(conn, exam_id, *, booklet: str, with_answers: bool) -> tuple[str, str]`
  - `exams.delete_exam(conn, exam_id) -> None`
  - `exams.file_slug(title: str) -> str` — Türkçe harfleri ASCII'ye katlar (`ğ→g ü→u ş→s ı→i ö→o ç→c İ→i`), küçük harf, harf/rakam dışı → `-`, baş/son `-` atılır, boşsa `sinav`, en fazla 60 karakter
- Produces (students):
  - `students.StudentSummary(student: Student, given_count: int, pending_count: int)`
  - `students.StudentHistory(student: Student, given: list[Card], pending: list[Card], worksheets: list[Exam])`
  - `students.list_students(conn) -> list[StudentSummary]`
  - `students.create_student(conn, *, alias: str, weak_objectives: list[str], level: int | None, now: str) -> Student`
  - `students.update_student(conn, student_id, *, alias: str, weak_objectives: list[str], level: int | None) -> Student`
  - `students.archive_student(conn, student_id) -> None`
  - `students.get_student(conn, student_id) -> Student`
  - `students.generate_for_student(conn, student_id, *, count: int, now: str, actor_id: str | None, seed: int | None = None) -> list[Card]`
  - `students.student_history(conn, student_id) -> StudentHistory`
  - `students.create_worksheet(conn, student_id, *, title: str, question_ids: list[str], fmt: str, now: str, actor_id: str | None, rng: random.Random) -> Exam`
- Produces (dashboard):
  - `dashboard.Dashboard(stats: LearningStats, pool: PoolSummary, approved_count: int, student_count: int, exam_count: int, next_step: str)`
  - `dashboard.build_dashboard(conn) -> Dashboard` — `next_step` sırayla ilk sağlanan: havuz boş → `"upload_pool"`; hazır kaynak yok ama kontrol bekleyen var → `"fix_pool"`; bekleyen kart yok ve onaylı < 10 → `"generate"`; bekleyen kart var → `"review"`; aksi → `"build_exam"`

**Kurallar (exams).**
- Başlık `strip()`, boşsa `Invalid("Sınav başlığı boş olamaz.")`, en fazla 120 karakter. `fmt ∉ FORMATS` veya `booklets ∉ BOOKLET_OPTIONS` → `Invalid`. `kind ∉ {"exam","worksheet"}` → `Invalid`.
- `question_ids` ve `auto`'dan tam olarak biri verilmelidir → aksi `Invalid("Soruları elle seçin ya da otomatik seçim ayarlayın.")`.
- Elle: sıra korunur, tekrarlar atılır; her kimlik mevcut + onaylı + arşivsiz olmalı, değilse `Invalid("Sınava yalnız onaylı sorular eklenebilir: <kimlikler>")`; sayı 1..100.
- Otomatik: aday havuz `question_bank(difficulty_min, difficulty_max)`. `objective_weights` verilirse (pozitif ağırlıklar) her kazanıma `count × ağırlık / toplam` pay, en büyük kalan yöntemiyle tamsayıya yuvarlanır; her kazanımdan payı kadar `rng.sample`; bir kazanımda yetmezse eksik, diğer adaylardan `rng` ile tamamlanır. Ağırlık yoksa tüm adaylardan `rng.sample`. Toplam aday < `count` → `Invalid("Yeterli onaylı soru yok: <count> istendi, <n> uygun soru var.")`. Seçim sonucu kazanım adına, sonra zorluğa göre sıralanır (sınav kağıdında konu blokları).
- `settings = {"format": fmt, "booklets": list(booklets), "seed": rng.randrange(2**31)}`; kimlik `new_id("ex")`.
- `student_id` verilirse öğrenci var olmalı; `db.assign_questions(conn, student_id, ids, now)`.
- `exam_view`: silinmiş/arşivlenmiş olsa da kayıtlı sorular gösterilir; veritabanında artık olmayanlar `missing_question_ids`. Kitapçıklar `build_booklets(questions, names=booklets, seed=settings["seed"], fmt=format)`.
- `exam_docx`/`exam_tex`: `booklet` sınavın kitapçıklarından biri değilse `Invalid`; dosya adı `f"{file_slug(title)}-{booklet.lower()}{'-cevap' if with_answers else ''}.docx"` (tex için `.tex`).

**Kurallar (students).**
- Rumuz `strip()`, 1..60 karakter (`Invalid("Rumuz 1 ile 60 karakter arasında olmalı.")`); zayıf kazanımlar `strip`, boşlar atılır, tekilleştirilir, en fazla 30; seviye `None` ya da 1..10. Kimlik `new_id("st")`.
- `archive_student` sonrası `get_student` yine döner (geçmiş için) ama `list_students` göstermez; arşivli öğrenciye üretim/çalışma kağıdı → `Conflict("Arşivlenmiş öğrenci için işlem yapılamaz.")`.
- `generate_for_student`: `objectives = weak_objectives or None`, `target_difficulty = level`; `cards.produce_cards(..., student_id=...)`.
- `given`: `load_student_question_ids` kartları (en yeni atama önce); `pending`: `cards.pending_cards(student_id=...)`; `worksheets`: `exams.list_exams(student_id=...)`.
- `create_worksheet`: `exams.create_exam(kind="worksheet", student_id=..., question_ids=..., booklets=("A",))`.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_services_exams.py`:
```python
from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.services import cards, errors, exams, pool

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-09-15T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    pool.ingest_markdown(c, VERI.read_text(encoding="utf-8"), now=SIMDI)
    uretilen = cards.produce_cards(c, count=6, now=SIMDI, actor_id=None, seed=1)
    for i, k in enumerate(uretilen):
        cards.review_card(c, k.question.id, approved=True, difficulty=2 + i, quality=8,
                          now=f"2026-09-15T10:0{i}:00+00:00", actor_id=None)
    yield c
    c.close()


def onayli(conn):
    return [k.question.id for k in cards.question_bank(conn)]


def olustur(conn, **ek):
    return exams.create_exam(conn, title=ek.pop("title", "Ara Sınav"), now=SIMDI, actor_id="u_1",
                             rng=random.Random(ek.pop("tohum", 0)), **ek)


def test_elle_sinav(conn):
    ids = onayli(conn)[:3]
    sinav = olustur(conn, question_ids=[ids[0], ids[1], ids[0], ids[2]], booklets=("A", "B"))
    assert sinav.question_ids == tuple(ids) and sinav.id.startswith("ex_")
    assert sinav.settings["format"] == "mc" and sinav.settings["booklets"] == ["A", "B"]
    gorunum = exams.exam_view(conn, sinav.id)
    assert [b.name for b in gorunum.booklets] == ["A", "B"] and gorunum.missing_question_ids == []


def test_onaysiz_soru_eklenemez(conn):
    ekstra = cards.produce_cards(conn, count=2, now=SIMDI, actor_id=None, seed=9)
    if ekstra:
        with pytest.raises(errors.Invalid, match="onaylı"):
            olustur(conn, question_ids=[ekstra[0].question.id])
    with pytest.raises(errors.Invalid):
        olustur(conn, question_ids=["q_yok"])


@pytest.mark.parametrize(
    "ek",
    [{"title": "  "}, {"fmt": "pdf"}, {"booklets": ("A", "C")}, {"kind": "quiz"}, {}],
)
def test_dogrulamalar(conn, ek):
    girdi = {"question_ids": onayli(conn)[:1], **ek} if ek else {}
    with pytest.raises(errors.Invalid):
        olustur(conn, **girdi)


def test_otomatik_secim_ve_yetersizlik(conn):
    sinav = olustur(conn, auto=exams.AutoSelection(count=4), tohum=3)
    assert len(sinav.question_ids) == 4 and set(sinav.question_ids) <= set(onayli(conn))
    with pytest.raises(errors.Invalid, match="Yeterli onaylı soru yok"):
        olustur(conn, auto=exams.AutoSelection(count=50))


def test_otomatik_zorluk_ve_kazanim_agirligi(conn):
    kolay = olustur(conn, auto=exams.AutoSelection(count=2, difficulty_max=3))
    assert all(db.get_review(conn, q).difficulty <= 3 for q in kolay.question_ids)
    kazanimlar = {k.objective for k in cards.question_bank(conn)}
    hedef = sorted(kazanimlar)[0]
    agirlikli = olustur(conn, auto=exams.AutoSelection(count=2, objective_weights={hedef: 1}))
    banka = {k.question.id: k.objective for k in cards.question_bank(conn)}
    uygun = sum(1 for k in banka.values() if k == hedef)
    assert sum(1 for q in agirlikli.question_ids if banka[q] == hedef) == min(2, uygun)


def test_ciktilar_ve_dosya_adi(conn):
    sinav = olustur(conn, title="Işık Dershanesi Ünite 1", question_ids=onayli(conn)[:2])
    veri, ad = exams.exam_docx(conn, sinav.id, booklet="A", with_answers=True)
    assert ad == "isik-dershanesi-unite-1-a-cevap.docx"
    with zipfile.ZipFile(io.BytesIO(veri)) as z:
        assert "Cevap Anahtarı" in z.read("word/document.xml").decode("utf-8")
    tex, tex_ad = exams.exam_tex(conn, sinav.id, booklet="A", with_answers=False)
    assert r"\documentclass" in tex and tex_ad == "isik-dershanesi-unite-1-a.tex"
    with pytest.raises(errors.Invalid):
        exams.exam_docx(conn, sinav.id, booklet="B", with_answers=False)


def test_liste_silme_ve_bulunamaz(conn):
    sinav = olustur(conn, question_ids=onayli(conn)[:1])
    assert [e.id for e in exams.list_exams(conn)] == [sinav.id]
    exams.delete_exam(conn, sinav.id)
    for islem in (lambda: exams.exam_view(conn, sinav.id), lambda: exams.delete_exam(conn, sinav.id)):
        with pytest.raises(errors.NotFound):
            islem()


@pytest.mark.parametrize(("baslik", "beklenen"), [("ĞÜŞİÖÇ ğüşıöç", "gusioc-gusioc"), ("!!!", "sinav")])
def test_file_slug(baslik, beklenen):
    assert exams.file_slug(baslik) == beklenen
```

`tests/test_services_students.py`:
```python
from __future__ import annotations

import random
from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.services import cards, dashboard, errors, pool, students

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-09-15T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def havuzlu(conn):
    pool.ingest_markdown(conn, VERI.read_text(encoding="utf-8"), now=SIMDI)


def test_olusturma_normallestirir_ve_dogrular(conn):
    ogrenci = students.create_student(conn, alias="  Ali  ", weak_objectives=[" k1", "k1", "", "k2"], level=6, now=SIMDI)
    assert ogrenci.alias == "Ali" and ogrenci.weak_objectives == ("k1", "k2") and ogrenci.id.startswith("st_")
    for alanlar in ({"alias": ""}, {"alias": "a" * 61}, {"level": 0}, {"weak_objectives": [f"k{i}" for i in range(31)]}):
        girdi = {"alias": "Ayşe", "weak_objectives": [], "level": None, **alanlar}
        with pytest.raises(errors.Invalid):
            students.create_student(conn, now=SIMDI, **girdi)


def test_guncelleme_arsiv_ve_liste(conn):
    o = students.create_student(conn, alias="Ali", weak_objectives=[], level=None, now=SIMDI)
    students.update_student(conn, o.id, alias="Ali K.", weak_objectives=["k"], level=3)
    assert students.get_student(conn, o.id).level == 3
    students.archive_student(conn, o.id)
    assert students.list_students(conn) == []
    assert students.get_student(conn, o.id).archived
    with pytest.raises(errors.NotFound):
        students.get_student(conn, "st_yok")


def test_ogrenci_icin_uretim_zayif_kazanima_odaklanir(conn):
    havuzlu(conn)
    hedef = sorted(k.objective for k in db.load_templates(conn))[0]
    o = students.create_student(conn, alias="Ali", weak_objectives=[hedef], level=None, now=SIMDI)
    kartlar = students.generate_for_student(conn, o.id, count=4, now=SIMDI, actor_id=None, seed=1)
    assert kartlar and {k.objective for k in kartlar} == {hedef}
    assert all(k.question.student_id == o.id for k in kartlar)


def test_calisma_kagidi_gecmis_ve_arsiv_engeli(conn):
    havuzlu(conn)
    o = students.create_student(conn, alias="Ali", weak_objectives=[], level=None, now=SIMDI)
    kartlar = students.generate_for_student(conn, o.id, count=4, now=SIMDI, actor_id=None, seed=1)
    for k in kartlar:
        cards.review_card(conn, k.question.id, approved=True, difficulty=5, quality=8, now=SIMDI, actor_id=None)
    kagit = students.create_worksheet(conn, o.id, title="Ali — Tekrar", question_ids=[k.question.id for k in kartlar],
                                      fmt="open", now=SIMDI, actor_id=None, rng=random.Random(0))
    assert kagit.kind == "worksheet" and kagit.student_id == o.id
    gecmis = students.student_history(conn, o.id)
    assert {k.question.id for k in gecmis.given} == {k.question.id for k in kartlar}
    assert [w.id for w in gecmis.worksheets] == [kagit.id] and gecmis.pending == []
    (ozet,) = students.list_students(conn)
    assert (ozet.given_count, ozet.pending_count) == (len(kartlar), 0)
    students.archive_student(conn, o.id)
    with pytest.raises(errors.Conflict):
        students.generate_for_student(conn, o.id, count=1, now=SIMDI, actor_id=None)


def test_panel_sonraki_adim(conn):
    assert dashboard.build_dashboard(conn).next_step == "upload_pool"
    pool.create_source(conn, text="Soru", recipe=None, answer_text=None, objective=None, now=SIMDI)
    assert dashboard.build_dashboard(conn).next_step == "fix_pool"
    havuzlu(conn)
    assert dashboard.build_dashboard(conn).next_step == "generate"
    cards.produce_cards(conn, count=2, now=SIMDI, actor_id=None, seed=1)
    panel = dashboard.build_dashboard(conn)
    assert panel.next_step == "review" and panel.stats.pending == 2 and panel.pool.total == 5
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_services_exams.py tests/test_services_students.py -q` → FAIL.

- [ ] **Adım 3: Üç modülü Interfaces + Kurallar bloğuna göre yaz.** Döngüsel import yasağı: `students` → `exams`, `cards`; `exams` → `cards`; `dashboard` → `cards`, `pool`; `cards` bunların hiçbirini import etmez.

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/services/exams.py questioncrator/services/students.py questioncrator/services/dashboard.py tests/test_services_exams.py tests/test_services_students.py
git commit -m "feat(services): sınav, öğrenci ve panel servisleri"
```

---
### Task 6: API iskeleti, kimlik doğrulama ve çalışma alanı uç noktaları

**Files:**
- Create: `questioncrator/api/__init__.py` (`"""HTTP API katmanı (FastAPI)."""`), `api/app.py`, `api/deps.py`, `api/schemas.py`, `api/routes_auth.py`, `api/routes_workspace.py`, `api/routes_system.py`
- Modify: `pyproject.toml` — bağımlılıklar: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9`; dev: `httpx>=0.27`
- Test: `tests/__init__.py` (boş, yoksa oluştur — `from tests.api.conftest import ...` için), `tests/api/__init__.py` (boş), `tests/api/conftest.py`, `tests/api/test_auth.py`, `tests/api/test_workspace.py`

**Interfaces:**
- Consumes: `config.Settings`, `accounts.*`, `security.LoginRateLimiter`, `storage.*`, `services.errors.*`, `ids.new_id`
- Produces:
  - `app.create_app(settings: Settings | None = None) -> FastAPI` — `settings` yoksa `Settings.from_env()`; `app.state.settings`, `app.state.login_limiter`
  - `deps.SESSION_COOKIE = "qc_session"`
  - `deps.get_settings(request) -> Settings`, `deps.get_now() -> datetime` (UTC; testlerde `app.dependency_overrides` ile ezilir)
  - `deps.accounts_conn(settings) -> Iterator[sqlite3.Connection]` (istek başına aç/kapa)
  - `deps.current_auth(request, response, conn, now) -> accounts.Auth` — çerez yok/geçersiz → 401 `"Oturum açmanız gerekiyor."`; geçerliyse çerezi `expires_at`'e göre yeniden yazar
  - `deps.require_owner(auth) -> accounts.Auth` — 403 `"Bu işlem için yönetici yetkisi gerekiyor."`
  - `deps.workspace_conn(auth, settings) -> Iterator[sqlite3.Connection]`
  - `deps.set_session_cookie(response, token, expires_at_iso, settings)`, `deps.clear_session_cookie(response, settings)`
  - `deps.iso(now: datetime) -> str`
  - Hata eşleme (app.py): `errors.NotFound`→404, `Conflict`→409, `Invalid`→422, `Timeout`→504, `Unavailable`→503; `accounts.EmailTaken`→409, `InvalidCredentials`→401, `InvalidInvite`→422, diğer `AccountError`→422; `RequestValidationError`→422 `{"detail": "Geçersiz istek: <alan>: <pydantic mesajı>"}` (ilk hata)
  - `schemas`: `UserOut(id, email, name)`, `WorkspaceOut(id, name, created_at)`, `SessionOut(user: UserOut, workspace: WorkspaceOut, role: str)`, `RegisterIn(name, email, password, workspace_name, load_demo: bool = True)`, `LoginIn(email, password)`, `JoinIn(code, name, email, password)`, `WorkspacePatchIn(name)`, `MemberOut(id, email, name, role)`, `InviteIn(role: Literal["teacher", "owner"] = "teacher")`, `InviteOut(code, expires_at)`, `WorkspaceDeleteIn(confirm_name)`, `ConfigOut(llm_enabled: bool, registration_open: bool, version: str)`

**Uç noktalar.**

| Yöntem ve yol | Yetki | Başarı | Notlar |
|---|---|---|---|
| `POST /api/auth/register` | yok | 201 `SessionOut` + çerez | `allow_registration=False` → 403 `"Yeni kayıt şu anda kapalı."`; çalışma alanı DB dosyası `storage.open_workspace` ile oluşturulur; `load_demo` Task 11'de bağlanır (bu task'ta yok sayılır) |
| `POST /api/auth/login` | yok | 200 `SessionOut` + çerez | sınır anahtarı `f"{email.strip().lower()}|{client_ip}"`; engelliyse 429 `"Çok fazla hatalı deneme. Lütfen 10 dakika sonra tekrar deneyin."`; başarısızlık `record_failure`, başarı `reset` |
| `POST /api/auth/logout` | çerez varsa | 204, çerez silinir | oturum yoksa da 204 |
| `GET /api/auth/me` | oturum | 200 `SessionOut` | |
| `POST /api/auth/join` | yok | 201 `SessionOut` + çerez | |
| `GET /api/workspace` | oturum | 200 `WorkspaceOut` | |
| `PATCH /api/workspace` | owner | 200 `WorkspaceOut` | |
| `GET /api/workspace/members` | oturum | 200 `list[MemberOut]` | |
| `POST /api/workspace/invites` | owner | 201 `InviteOut` | |
| `DELETE /api/workspace/members/{user_id}` | owner | 204 | başka çalışma alanının kullanıcısı → 404 `"Üye bulunamadı."` |
| `GET /api/workspace/backup` | owner | 200 `application/octet-stream`, `Content-Disposition: attachment; filename="questioncrator-yedek-YYYYMMDD.db"` | |
| `DELETE /api/workspace` | owner | 204, çerez silinir | `confirm_name` çalışma alanı adıyla birebir değilse 422 `"Onay için çalışma alanı adını aynen yazın."`; hesap satırları + dosyalar silinir |
| `GET /api/system/health` | yok | 200 `{"status": "ok"}` | |
| `GET /api/system/config` | yok | 200 `ConfigOut` | `version` = `importlib.metadata.version("questioncrator")` |

Tüm `routes_*` modülleri `APIRouter(prefix=...)` tanımlar; iş mantığı içermez — `accounts`/`storage`/servis çağrısı + şema dönüşümü. Uç nokta fonksiyonları `def` (senkron; FastAPI iş havuzunda koşar).

- [ ] **Adım 1: Bağımlılıkları ekle ve kur** — `pyproject.toml`'u güncelle, `.venv/bin/pip install -e ".[dev]" -q`.

- [ ] **Adım 2: Başarısız testleri yaz**

`tests/api/conftest.py`:
```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from questioncrator.api.app import create_app
from questioncrator.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "veri")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def kayit_ol(client, email="hoca@ornek.com", parola="parola123", alan="Işık Dershanesi", **ek):
    yanit = client.post("/api/auth/register", json={
        "name": "Ayşe Hoca", "email": email, "password": parola,
        "workspace_name": alan, "load_demo": False, **ek,
    })
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


@pytest.fixture
def hoca(client):
    return kayit_ol(client)
```

`tests/api/test_auth.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from questioncrator import storage
from questioncrator.api.app import create_app
from questioncrator.config import Settings
from tests.api.conftest import kayit_ol


def test_kayit_cerez_ve_me(client, settings):
    veri = kayit_ol(client)
    assert veri["role"] == "owner" and veri["user"]["email"] == "hoca@ornek.com"
    cerez = client.cookies.get("qc_session")
    assert cerez
    me = client.get("/api/auth/me").json()
    assert me["workspace"]["name"] == "Işık Dershanesi"
    assert storage.workspace_path(settings, veri["workspace"]["id"]).exists()


def test_cerez_ozellikleri(client):
    yanit = client.post("/api/auth/register", json={
        "name": "A", "email": "a@ornek.com", "password": "parola123", "workspace_name": "W", "load_demo": False,
    })
    baslik = yanit.headers["set-cookie"].lower()
    assert "httponly" in baslik and "samesite=lax" in baslik and "path=/" in baslik
    assert "secure" not in baslik


def test_oturumsuz_401_turkce(client):
    yanit = client.get("/api/auth/me")
    assert yanit.status_code == 401 and yanit.json() == {"detail": "Oturum açmanız gerekiyor."}


def test_ayni_eposta_409_ve_dogrulama_422(client):
    kayit_ol(client)
    client.cookies.clear()
    ikinci = client.post("/api/auth/register", json={
        "name": "B", "email": "HOCA@ornek.com", "password": "parola123", "workspace_name": "W", "load_demo": False,
    })
    assert ikinci.status_code == 409
    kisa = client.post("/api/auth/register", json={
        "name": "B", "email": "b@ornek.com", "password": "kisa", "workspace_name": "W", "load_demo": False,
    })
    assert kisa.status_code == 422 and "8 karakter" in kisa.json()["detail"]
    eksik = client.post("/api/auth/register", json={"name": "B"})
    assert eksik.status_code == 422 and eksik.json()["detail"].startswith("Geçersiz istek")


def test_giris_cikis(client):
    kayit_ol(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "hoca@ornek.com", "password": "yanlis123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "hoca@ornek.com", "password": "parola123"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_giris_siniri(client):
    kayit_ol(client)
    client.cookies.clear()
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "hoca@ornek.com", "password": "yanlis123"})
    yanit = client.post("/api/auth/login", json={"email": "hoca@ornek.com", "password": "parola123"})
    assert yanit.status_code == 429 and "10 dakika" in yanit.json()["detail"]


def test_kayit_kapali(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, allow_registration=False))) as c:
        yanit = c.post("/api/auth/register", json={
            "name": "A", "email": "a@ornek.com", "password": "parola123", "workspace_name": "W", "load_demo": False,
        })
        assert yanit.status_code == 403
        assert c.get("/api/system/config").json()["registration_open"] is False


def test_davetle_katilim(client, app):
    kayit_ol(client)
    kod = client.post("/api/workspace/invites", json={}).json()["code"]
    with TestClient(app) as ikinci:
        yanit = ikinci.post("/api/auth/join", json={
            "code": kod, "name": "Mehmet", "email": "m@ornek.com", "password": "parola456",
        })
        assert yanit.status_code == 201 and yanit.json()["role"] == "teacher"
        assert ikinci.post("/api/workspace/invites", json={}).status_code == 403


def test_saglik_ve_yapilandirma(client):
    assert client.get("/api/system/health").json() == {"status": "ok"}
    yapilandirma = client.get("/api/system/config").json()
    assert yapilandirma["llm_enabled"] is False and yapilandirma["registration_open"] is True
```

`tests/api/test_workspace.py`:
```python
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from questioncrator import storage
from tests.api.conftest import kayit_ol


def test_ad_degistirme_ve_uyeler(client, hoca):
    assert client.patch("/api/workspace", json={"name": "Yeni Ad"}).json()["name"] == "Yeni Ad"
    (uye,) = client.get("/api/workspace/members").json()
    assert uye["role"] == "owner" and uye["email"] == "hoca@ornek.com"


def test_uye_cikarma_ve_baska_alan_404(client, app, hoca):
    kod = client.post("/api/workspace/invites", json={}).json()["code"]
    with TestClient(app) as ogretmen, TestClient(app) as yabanci:
        ogr = ogretmen.post("/api/auth/join", json={
            "code": kod, "name": "M", "email": "m@ornek.com", "password": "parola456"}).json()
        diger = kayit_ol(yabanci, email="d@ornek.com", alan="Başka")
        assert client.delete(f"/api/workspace/members/{diger['user']['id']}").status_code == 404
        assert client.delete(f"/api/workspace/members/{ogr['user']['id']}").status_code == 204
        assert ogretmen.get("/api/auth/me").status_code == 401
    assert client.delete(f"/api/workspace/members/{hoca['user']['id']}").status_code == 422


def test_yedek_indirme(client, hoca, tmp_path):
    yanit = client.get("/api/workspace/backup")
    assert yanit.status_code == 200
    assert "attachment" in yanit.headers["content-disposition"] and ".db" in yanit.headers["content-disposition"]
    yol = tmp_path / "y.db"
    yol.write_bytes(yanit.content)
    assert sqlite3.connect(yol).execute("PRAGMA user_version").fetchone()[0] >= 2


def test_calisma_alani_silme_onayli(client, hoca, settings):
    assert client.request("DELETE", "/api/workspace", json={"confirm_name": "yanlış"}).status_code == 422
    assert client.request("DELETE", "/api/workspace", json={"confirm_name": "Işık Dershanesi"}).status_code == 204
    assert not storage.workspace_path(settings, hoca["workspace"]["id"]).exists()
    assert client.post("/api/auth/login", json={"email": "hoca@ornek.com", "password": "parola123"}).status_code == 401
```

- [ ] **Adım 3: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/api -q` → FAIL (`ModuleNotFoundError: questioncrator.api`).

- [ ] **Adım 4: Uygulamayı yaz** — Interfaces + uç nokta tablosuna göre `deps.py`, `schemas.py`, `routes_auth.py`, `routes_workspace.py`, `routes_system.py`, `app.py`. İstemci IP'si `request.client.host` (yoksa `"bilinmiyor"`). `create_app` başında `settings.data_dir.mkdir(parents=True, exist_ok=True)`.

- [ ] **Adım 5: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 6: Commit**

```bash
git add pyproject.toml questioncrator/api tests/api
git commit -m "feat(api): FastAPI iskeleti, oturum çerezi, kayıt/giriş/davet ve çalışma alanı uç noktaları"
```

---
### Task 7: Havuz, kart ve soru bankası uç noktaları + kiracı izolasyonu

**Files:**
- Create: `questioncrator/api/routes_pool.py`, `questioncrator/api/routes_cards.py`
- Modify: `questioncrator/api/schemas.py`, `questioncrator/api/app.py` (yönlendiricileri ekle)
- Test: `tests/api/test_pool.py`, `tests/api/test_cards.py`, `tests/api/test_isolation.py`

**Interfaces:**
- Consumes: `services.pool.*`, `services.cards.*`, `deps.current_auth/workspace_conn/get_now/iso`
- Produces (schemas):
  - `SourceIn(text: str, recipe: str | None = None, answer_text: str | None = None, objective: str | None = None)`
  - `SourceOut(id, text, recipe, answer_text, objective, needs_review: bool, review_note, origin, created_at, template_status: str | None)`
  - `PoolSummaryOut(total, ready, needs_review, templates_by_status: dict[str, int], by_objective: dict[str, int])`
  - `IngestOut(added, templates, needs_review, problems: list[ProblemOut])`, `ProblemOut(source_id, reason)`
  - `PreviewIn(text: str, recipe: str)`, `PreviewVariantOut(text, answer_latex, choices: list[str], correct_index: int | None)`, `PreviewOut(ok, answer_latex, parameter_count, difficulty, variants: list[PreviewVariantOut], error)`
  - `GenerateIn(count: int = 10, objectives: list[str] | None = None, target_difficulty: float | None = None)`
  - `ReviewIn(approved: bool, difficulty: int, quality: int)`, `ReviewOut(approved, difficulty, quality, created_at)`
  - `CardOut(id, text, answer_latex, choices: list[str], correct_index: int | None, difficulty_estimate: float, objective: str | None, template_status: str, student_id: str | None, similar_given: bool, archived: bool, created_at: str, review: ReviewOut | None)`
  - `ReviewOutcomeOut(card: CardOut, transitions: dict[str, str])`
  - `ArchiveIn(archived: bool)`
  - `schemas.card_out(card: cards.Card) -> CardOut`, `schemas.source_out(view: pool.SourceView) -> SourceOut` — tek dönüştürücü, tüm yönlendiriciler bunu kullanır

**Uç noktalar** (hepsi oturum ister; `actor_id = auth.user.id`, `now = iso(get_now())`):

| Yöntem ve yol | Başarı | Servis |
|---|---|---|
| `GET /api/pool/summary` | 200 `PoolSummaryOut` | `pool_summary` |
| `GET /api/pool/sources?status=` | 200 `list[SourceOut]` | `list_sources` |
| `GET /api/pool/sources/{id}` | 200 `SourceOut` | `get_source` |
| `POST /api/pool/sources` | 201 `SourceOut` | `create_source` |
| `PATCH /api/pool/sources/{id}` | 200 `SourceOut` | `update_source` |
| `DELETE /api/pool/sources/{id}` | 204 | `delete_source` |
| `POST /api/pool/upload` (multipart alan adı `file`) | 201 `IngestOut` | `.md`/`.txt` → `ingest_markdown` (UTF-8; çözülemezse 422 `"Dosya UTF-8 metin olarak okunamadı."`); diğer türler bu task'ta 422 `"Bu dosya türü desteklenmiyor. Desteklenenler: .md, .txt"` (Task 9 genişletir); boyut > 15 MB → 413 `"Dosya en fazla 15 MB olabilir."`; boş dosya → 422 `"Dosya boş."` |
| `POST /api/pool/preview-recipe` | 200 `PreviewOut` | `preview_recipe(seed=secrets.randbits(32))` |
| `GET /api/pool/objectives` | 200 `list[str]` | `list_objectives` |
| `POST /api/cards/generate` | 201 `list[CardOut]` | `produce_cards` |
| `GET /api/cards/pending` | 200 `list[CardOut]` | `pending_cards` (genel akış) |
| `GET /api/cards/{id}` | 200 `CardOut` | `get_card` |
| `POST /api/cards/{id}/review` | 200 `ReviewOutcomeOut` | `review_card` |
| `DELETE /api/cards/{id}/review` | 200 `CardOut` | `undo_review` |
| `GET /api/questions?objective=&difficulty_min=&difficulty_max=` | 200 `list[CardOut]` | `question_bank` |
| `PATCH /api/questions/{id}` | 200 `CardOut` | `set_archived` |

Yükleme boyutu `UploadFile` okunurken 15 MB + 1 bayta kadar okunarak denetlenir (tümü belleğe alınmadan önce sınır). `CardOut` şablon reçetesini, bağlamaları ve `answer_key`'i **dışarı vermez**.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/api/test_pool.py`:
```python
from __future__ import annotations

from pathlib import Path

VERI = Path(__file__).parent.parent / "data" / "ornek_havuz.md"


def yukle(client, ad="havuz.md", icerik=None, tur="text/markdown"):
    veri = VERI.read_bytes() if icerik is None else icerik
    return client.post("/api/pool/upload", files={"file": (ad, veri, tur)})


def test_yukleme_ozet_liste(client, hoca):
    yanit = yukle(client)
    assert yanit.status_code == 201
    assert yanit.json()["added"] == 4 and yanit.json()["templates"] == 3
    ozet = client.get("/api/pool/summary").json()
    assert ozet["total"] == 4 and ozet["needs_review"] == 1
    kontrol = client.get("/api/pool/sources", params={"status": "needs_review"}).json()
    assert len(kontrol) == 1 and kontrol[0]["review_note"]
    assert "belirsiz" in client.get("/api/pool/objectives").json()


def test_yukleme_hatalari(client, hoca):
    assert yukle(client, ad="x.exe", icerik=b"abc", tur="application/octet-stream").status_code == 422
    assert yukle(client, icerik=b"").status_code == 422
    assert yukle(client, icerik="ğ".encode("utf-16")).status_code == 422
    buyuk = yukle(client, ad="b.txt", icerik=b"a" * (15 * 1024 * 1024 + 1), tur="text/plain")
    assert buyuk.status_code == 413


def test_elle_kaynak_crud(client, hoca):
    olusan = client.post("/api/pool/sources", json={"text": "$3x+1$ ifadesinde x=2 için değer?", "recipe": "3*2 + 1"})
    assert olusan.status_code == 201
    kimlik = olusan.json()["id"]
    duzelt = client.patch(f"/api/pool/sources/{kimlik}", json={"text": "$4x$", "recipe": "4*x + 3", "objective": "k"})
    assert duzelt.status_code == 200 and duzelt.json()["template_status"] == "trial"
    assert client.get(f"/api/pool/sources/{kimlik}").json()["objective"] == "k"
    assert client.delete(f"/api/pool/sources/{kimlik}").status_code == 204
    assert client.get(f"/api/pool/sources/{kimlik}").status_code == 404
    assert client.post("/api/pool/sources", json={"text": " "}).status_code == 422


def test_onizleme(client, hoca):
    yanit = client.post("/api/pool/preview-recipe", json={"text": "$3x^2$", "recipe": "diff(3*x**2 + 2*x, x)"})
    assert yanit.status_code == 200 and yanit.json()["ok"] and len(yanit.json()["variants"]) == 3


def test_oturumsuz_erisim_yok(client):
    assert client.get("/api/pool/summary").status_code == 401
```

`tests/api/test_cards.py`:
```python
from __future__ import annotations

from tests.api.test_pool import yukle


def test_kart_akisi(client, hoca):
    yukle(client)
    kartlar = client.post("/api/cards/generate", json={"count": 6}).json()
    assert kartlar and {"id", "text", "choices", "review"} <= set(kartlar[0])
    assert "answer_key" not in kartlar[0] and "bindings" not in kartlar[0]
    assert len(client.get("/api/cards/pending").json()) == len(kartlar)

    ilk = kartlar[0]["id"]
    sonuc = client.post(f"/api/cards/{ilk}/review", json={"approved": True, "difficulty": 6, "quality": 8})
    assert sonuc.status_code == 200 and sonuc.json()["card"]["review"]["difficulty"] == 6
    assert client.post(f"/api/cards/{ilk}/review", json={"approved": True, "difficulty": 6, "quality": 8}).status_code == 409
    assert [q["id"] for q in client.get("/api/questions").json()] == [ilk]
    assert client.get("/api/questions", params={"difficulty_min": 7}).json() == []

    assert client.delete(f"/api/cards/{ilk}/review").json()["review"] is None
    assert client.get("/api/questions").json() == []


def test_kart_dogrulama_ve_bulunamaz(client, hoca):
    yukle(client)
    assert client.post("/api/cards/generate", json={"count": 0}).status_code == 422
    assert client.post("/api/cards/generate", json={"count": 3, "objectives": ["yok"]}).status_code == 422
    kart = client.post("/api/cards/generate", json={"count": 1}).json()[0]
    assert client.post(f"/api/cards/{kart['id']}/review", json={"approved": True, "difficulty": 11, "quality": 5}).status_code == 422
    assert client.get("/api/cards/q_000000000000").status_code == 404


def test_arsivleme(client, hoca):
    yukle(client)
    kart = client.post("/api/cards/generate", json={"count": 1}).json()[0]
    client.post(f"/api/cards/{kart['id']}/review", json={"approved": True, "difficulty": 5, "quality": 9})
    assert client.patch(f"/api/questions/{kart['id']}", json={"archived": True}).json()["archived"] is True
    assert client.get("/api/questions").json() == []
```

`tests/api/test_isolation.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import kayit_ol
from tests.api.test_pool import yukle


def test_baska_calisma_alaninin_kayitlari_404(client, app, hoca):
    yukle(client)
    kaynak = client.get("/api/pool/sources").json()[0]["id"]
    kart = client.post("/api/cards/generate", json={"count": 1}).json()[0]["id"]

    with TestClient(app) as yabanci:
        kayit_ol(yabanci, email="yabanci@ornek.com", alan="Rakip Dershane")
        assert yabanci.get("/api/pool/summary").json()["total"] == 0
        assert yabanci.get(f"/api/pool/sources/{kaynak}").status_code == 404
        assert yabanci.patch(f"/api/pool/sources/{kaynak}", json={"text": "x"}).status_code == 404
        assert yabanci.delete(f"/api/pool/sources/{kaynak}").status_code == 404
        assert yabanci.get(f"/api/cards/{kart}").status_code == 404
        assert yabanci.post(f"/api/cards/{kart}/review", json={"approved": True, "difficulty": 5, "quality": 5}).status_code == 404
        assert yabanci.patch(f"/api/questions/{kart}", json={"archived": True}).status_code == 404
        assert yabanci.get("/api/cards/pending").json() == []

    assert client.get(f"/api/cards/{kart}").json()["review"] is None
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/api -q` → yeni testler FAIL (404/405).

- [ ] **Adım 3: Şemaları, iki yönlendiriciyi yaz; `app.py`'ye ekle.**

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/api tests/api
git commit -m "feat(api): havuz, kart ve soru bankası uç noktaları; kiracı izolasyonu testleri"
```

---
### Task 8: Sınav, öğrenci, panel uç noktaları + SPA sunumu + güvenlik başlıkları

**Files:**
- Create: `questioncrator/api/routes_exams.py`, `questioncrator/api/routes_students.py`
- Modify: `questioncrator/api/routes_system.py` (`GET /api/stats`), `questioncrator/api/schemas.py`, `questioncrator/api/app.py`, `questioncrator/config.py` (`web_dist: Path | None`, ortam `QC_WEB_DIST`; boşsa depo kökündeki `web/dist` varsa o, yoksa `None`)
- Test: `tests/api/test_exams.py`, `tests/api/test_students.py`, `tests/api/test_app_shell.py`

**Interfaces:**
- Consumes: `services.exams.*`, `services.students.*`, `services.dashboard.build_dashboard`, `schemas.card_out`
- Produces (schemas):
  - `AutoSelectionIn(count: int, objective_weights: dict[str, int] | None = None, difficulty_min: int | None = None, difficulty_max: int | None = None)`
  - `ExamIn(title: str, kind: Literal["exam", "worksheet"] = "exam", format: Literal["mc", "open"] = "mc", booklets: list[str] = ["A"], question_ids: list[str] | None = None, auto: AutoSelectionIn | None = None, student_id: str | None = None)`
  - `ExamOut(id, title, kind, format, booklets: list[str], question_count: int, student_id, created_at)`
  - `BookletItemOut(number: int, question: CardOut, choices: list[str], correct_letter: str | None)`, `BookletOut(name, items: list[BookletItemOut], answer_key: list[tuple[int, str]])`
  - `ExamDetailOut(exam: ExamOut, booklets: list[BookletOut], missing_question_ids: list[str])`
  - `StudentIn(alias: str, weak_objectives: list[str] = [], level: int | None = None)`, `StudentOut(id, alias, weak_objectives: list[str], level, created_at, archived)`, `StudentSummaryOut(student: StudentOut, given_count, pending_count)`
  - `StudentGenerateIn(count: int = 5)`, `WorksheetIn(title: str, question_ids: list[str], format: Literal["mc", "open"] = "open")`
  - `StudentHistoryOut(student: StudentOut, given: list[CardOut], pending: list[CardOut], worksheets: list[ExamOut])`
  - `WindowOut(count, approval_rate, avg_quality)`, `StatsOut(generated, pending, reviewed, approved, approval_rate, avg_quality, first_window: WindowOut | None, last_window: WindowOut | None, difficulty_deviation, templates_by_status)`, `DashboardOut(stats: StatsOut, pool: PoolSummaryOut, approved_count, student_count, exam_count, next_step)`

**Uç noktalar** (oturum gerekli):

| Yöntem ve yol | Başarı | Not |
|---|---|---|
| `POST /api/exams` | 201 `ExamOut` | `rng=random.Random(secrets.randbits(32))`; `booklets` listesi tuple'a çevrilir |
| `GET /api/exams?student_id=` | 200 `list[ExamOut]` | |
| `GET /api/exams/{id}` | 200 `ExamDetailOut` | `CardOut` içindeki `review` dahil |
| `GET /api/exams/{id}/docx?booklet=A&answers=false` | 200 docx | `media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"`; `Content-Disposition` hem `filename=` (ASCII slug) hem `filename*=UTF-8''` |
| `GET /api/exams/{id}/tex?booklet=A&answers=false` | 200 `text/x-tex; charset=utf-8` ek | |
| `DELETE /api/exams/{id}` | 204 | |
| `GET /api/students` | 200 `list[StudentSummaryOut]` | |
| `POST /api/students` | 201 `StudentOut` | |
| `GET /api/students/{id}` | 200 `StudentOut` | |
| `PATCH /api/students/{id}` | 200 `StudentOut` | |
| `DELETE /api/students/{id}` | 204 | arşivler |
| `POST /api/students/{id}/generate` | 201 `list[CardOut]` | |
| `GET /api/students/{id}/history` | 200 `StudentHistoryOut` | |
| `POST /api/students/{id}/worksheet` | 201 `ExamOut` | |
| `GET /api/cards/pending?student_id=` | 200 | Task 7 uç noktasına isteğe bağlı `student_id` sorgu parametresi eklenir |
| `GET /api/stats` | 200 `DashboardOut` | |

**SPA ve başlıklar (app.py).**
- `settings.web_dist` bir dizinse: `/assets` → `StaticFiles(directory=web_dist/"assets")`; `/api` ile başlamayan her `GET` yolu için dosya varsa o dosya (yol `web_dist` dışına çıkamaz — `resolve()` + `is_relative_to` denetimi), yoksa `index.html` (`Cache-Control: no-cache`). `web_dist` yoksa `/` 404 JSON.
- Eşleşmeyen `/api/*` → 404 `{"detail": "Bulunamadı."}`.
- Tüm yanıtlara ara katman: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/api/test_exams.py`:
```python
from __future__ import annotations

from tests.api.test_pool import yukle


def onayli_sorular(client, adet=6):
    yukle(client)
    kartlar = client.post("/api/cards/generate", json={"count": adet}).json()
    for k in kartlar:
        client.post(f"/api/cards/{k['id']}/review", json={"approved": True, "difficulty": 5, "quality": 8})
    return [k["id"] for k in kartlar]


def test_sinav_olustur_goruntule_indir_sil(client, hoca):
    ids = onayli_sorular(client)
    yanit = client.post("/api/exams", json={"title": "Ünite Sınavı", "question_ids": ids[:3], "booklets": ["A", "B"]})
    assert yanit.status_code == 201
    sinav = yanit.json()
    assert sinav["question_count"] == 3 and sinav["booklets"] == ["A", "B"]

    detay = client.get(f"/api/exams/{sinav['id']}").json()
    assert [b["name"] for b in detay["booklets"]] == ["A", "B"]
    assert len(detay["booklets"][1]["answer_key"]) == 3

    docx = client.get(f"/api/exams/{sinav['id']}/docx", params={"booklet": "B", "answers": "true"})
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert "unite-sinavi-b-cevap.docx" in docx.headers["content-disposition"]
    tex = client.get(f"/api/exams/{sinav['id']}/tex", params={"booklet": "A"})
    assert tex.status_code == 200 and r"\documentclass" in tex.text

    assert [e["id"] for e in client.get("/api/exams").json()] == [sinav["id"]]
    assert client.delete(f"/api/exams/{sinav['id']}").status_code == 204
    assert client.get(f"/api/exams/{sinav['id']}").status_code == 404


def test_otomatik_sinav_ve_hatalar(client, hoca):
    onayli_sorular(client)
    assert client.post("/api/exams", json={"title": "Oto", "auto": {"count": 3}}).status_code == 201
    assert client.post("/api/exams", json={"title": "Oto", "auto": {"count": 99}}).status_code == 422
    assert client.post("/api/exams", json={"title": "Boş"}).status_code == 422
    assert client.post("/api/exams", json={"title": "X", "format": "pdf", "auto": {"count": 1}}).status_code == 422
```

`tests/api/test_students.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import kayit_ol
from tests.api.test_pool import yukle


def test_ogrenci_akisi(client, app, hoca):
    yukle(client)
    kazanim = client.get("/api/pool/objectives").json()[0]
    ogrenci = client.post("/api/students", json={"alias": "Ali", "weak_objectives": [kazanim], "level": 5}).json()
    assert ogrenci["alias"] == "Ali"
    kartlar = client.post(f"/api/students/{ogrenci['id']}/generate", json={"count": 3}).json()
    assert kartlar and all(k["student_id"] == ogrenci["id"] for k in kartlar)
    bekleyen = client.get("/api/cards/pending", params={"student_id": ogrenci["id"]}).json()
    assert {k["id"] for k in bekleyen} == {k["id"] for k in kartlar}
    for k in kartlar:
        client.post(f"/api/cards/{k['id']}/review", json={"approved": True, "difficulty": 5, "quality": 7})
    kagit = client.post(f"/api/students/{ogrenci['id']}/worksheet",
                        json={"title": "Ali tekrar", "question_ids": [k["id"] for k in kartlar]})
    assert kagit.status_code == 201 and kagit.json()["kind"] == "worksheet"
    gecmis = client.get(f"/api/students/{ogrenci['id']}/history").json()
    assert len(gecmis["given"]) == len(kartlar) and len(gecmis["worksheets"]) == 1
    assert client.patch(f"/api/students/{ogrenci['id']}", json={"alias": "Ali K.", "weak_objectives": [], "level": None}).json()["level"] is None
    (ozet,) = client.get("/api/students").json()
    assert ozet["given_count"] == len(kartlar)

    with TestClient(app) as yabanci:
        kayit_ol(yabanci, email="y@ornek.com", alan="Başka")
        assert yabanci.get(f"/api/students/{ogrenci['id']}").status_code == 404
        assert yabanci.post(f"/api/students/{ogrenci['id']}/generate", json={"count": 1}).status_code == 404
        assert yabanci.get(f"/api/exams/{kagit.json()['id']}").status_code == 404

    assert client.delete(f"/api/students/{ogrenci['id']}").status_code == 204
    assert client.get("/api/students").json() == []


def test_panel(client, hoca):
    panel = client.get("/api/stats").json()
    assert panel["next_step"] == "upload_pool" and panel["stats"]["generated"] == 0
```

`tests/api/test_app_shell.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from questioncrator.api.app import create_app
from questioncrator.config import Settings


def test_spa_geri_donusu_ve_statik(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>uygulama</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "gizli.txt").write_text("sır", encoding="utf-8")
    with TestClient(create_app(Settings(data_dir=tmp_path / "veri", web_dist=dist))) as c:
        assert "uygulama" in c.get("/").text
        assert "uygulama" in c.get("/ogrenciler/st_1").text
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert "sır" not in c.get("/..%2Fgizli.txt").text
        yanit = c.get("/api/olmayan")
        assert yanit.status_code == 404 and yanit.json() == {"detail": "Bulunamadı."}


def test_guvenlik_basliklari(client):
    yanit = client.get("/api/system/health")
    assert yanit.headers["x-frame-options"] == "DENY"
    assert yanit.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in yanit.headers["content-security-policy"]
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/api -q` → yeni testler FAIL.

- [ ] **Adım 3: Yönlendiricileri, şemaları, `app.py` değişikliklerini ve `Settings.web_dist`'i yaz.** `Settings` alanı varsayılanlı (`web_dist: Path | None = None`) eklenir; `from_env` kuralı Files bölümündeki gibi. Mevcut `test_ayarlar_ortamdan` testine `web_dist` beklentisi eklenmez (depo kökünde `web/dist` olup olmaması ortama bağlı).

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add questioncrator/api questioncrator/config.py tests/api
git commit -m "feat(api): sınav, öğrenci ve panel uç noktaları; SPA sunumu ve güvenlik başlıkları"
```

---
### Task 9: Belge alımı (txt, docx, pdf) ve yükleme yönlendirmesi

**Files:**
- Create: `questioncrator/ingest/documents.py`
- Modify: `questioncrator/services/pool.py` (`ingest_upload` eklenir), `questioncrator/api/routes_pool.py` (yükleme `ingest_upload`'a bağlanır), `pyproject.toml` (`pypdf>=4.0`)
- Test: `tests/test_ingest_documents.py`, `tests/test_services_pool.py` (ekleme), `tests/api/test_pool.py` (güncelleme: `.exe` hâlâ 422; `.docx` artık 201)

**Interfaces:**
- Produces:
  - `documents.DocumentError(ValueError)` — Türkçe mesajlı
  - `documents.SUPPORTED_EXTENSIONS = (".md", ".txt", ".docx", ".pdf", ".png", ".jpg", ".jpeg")`
  - `documents.extract_text(filename: str, data: bytes) -> str` — `.txt`/`.md`: UTF-8 (BOM'lu dahil), olmazsa `cp1254`; `.docx`: paragraflar + tablo hücreleri (belge sırasıyla), satır sonlarıyla; `.pdf`: sayfa metinleri `"\n\n"` ile. Bozuk dosya → `DocumentError("Dosya okunamadı; bozuk ya da parola korumalı olabilir.")`; metinsiz PDF → `DocumentError("PDF'te seçilebilir metin bulunamadı; taranmış bir belge olabilir.")`
  - `documents.split_numbered_questions(text: str) -> list[str]`
  - `documents.drafts_from_text(text: str) -> list[SourceQuestion]` — her blok bir taslak, `recipe=None`, `needs_review=True`, `review_note="Dosyadan okundu; cevap reçetesini ekleyin."`
  - `pool.ingest_upload(conn, filename: str, data: bytes, *, now: str, llm: object | None = None) -> IngestResult` (Task 10 `llm`'i kullanır; bu task'ta yok sayılır)

**Kurallar.**
- `split_numbered_questions`: satır başı numara deseni `^\s*(?:Soru\s*)?(\d{1,3})\s*[.):\-]\s*` (büyük/küçük harf duyarsız). İlk eşleşmenin numarası `n` ise sonraki bölme yalnız `n+1` numaralı satırda yapılır (ör. soru içinde `2. dereceden` satır başı olsa bile sıra `n+1` değilse bölünmez). Numara öneki bloktan atılır; bloklar `strip()`; boş bloklar atılır. Hiç numara yoksa boş olmayan tüm metin tek blok.
- `ingest_upload` yönlendirme (uzantı küçük harfe çevrilir):
  - `.md` → `ingest_markdown`
  - `.txt` → metinde `### Soru` başlığı varsa `ingest_markdown`, yoksa `drafts_from_text` + `ingest_sources(origin="file")`
  - `.docx`, `.pdf` → `extract_text` + `drafts_from_text` + `ingest_sources(origin="file")`
  - `.png/.jpg/.jpeg` → `llm is None` ise `Invalid("Görsellerden soru okumak için yapay zekâ bağlantısı gerekir.")`
  - desteklenmeyen → `Invalid("Bu dosya türü desteklenmiyor. Desteklenenler: .md, .txt, .docx, .pdf, .png, .jpg")`
  - `DocumentError` → `Invalid(<mesaj>)`; çıkan taslak yoksa `Invalid("Dosyada soru bulunamadı.")`
- API yüklemesi: boyut/boş denetimi yönlendiricide kalır; tür ve içerik kararları `ingest_upload`'ta.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_ingest_documents.py`:
```python
from __future__ import annotations

import io

import pytest
from docx import Document

from questioncrator.ingest import documents


def docx_bayt(paragraflar, tablo=None):
    belge = Document()
    for p in paragraflar:
        belge.add_paragraph(p)
    if tablo:
        t = belge.add_table(rows=len(tablo), cols=len(tablo[0]))
        for i, satir in enumerate(tablo):
            for j, hucre in enumerate(satir):
                t.cell(i, j).text = hucre
    tampon = io.BytesIO()
    belge.save(tampon)
    return tampon.getvalue()


def basit_pdf(satirlar):
    akis = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({s}) Tj 0 -16 Td" for s in satirlar) + " ET"
    nesneler = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(akis)} >>\nstream\n{akis}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    govde = "%PDF-1.4\n"
    konumlar = []
    for i, n in enumerate(nesneler, start=1):
        konumlar.append(len(govde.encode("latin-1")))
        govde += f"{i} 0 obj\n{n}\nendobj\n"
    xref = len(govde.encode("latin-1"))
    govde += f"xref\n0 {len(nesneler) + 1}\n0000000000 65535 f \n"
    govde += "".join(f"{k:010d} 00000 n \n" for k in konumlar)
    govde += f"trailer\n<< /Size {len(nesneler) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return govde.encode("latin-1")


def test_numarali_bolme():
    metin = "Açıklama\n1. Birinci soru\nA) 3\nB) 4\n2) İkinci soru\n2. dereceden bir satır\nSoru 3: Üçüncü"
    assert documents.split_numbered_questions(metin) == [
        "Birinci soru\nA) 3\nB) 4",
        "İkinci soru\n2. dereceden bir satır",
        "Üçüncü",
    ]


def test_numarasiz_metin_tek_blok_bos_metin_bos_liste():
    assert documents.split_numbered_questions("  sadece metin  ") == ["sadece metin"]
    assert documents.split_numbered_questions("   ") == []


def test_txt_utf8_ve_cp1254():
    assert documents.extract_text("a.txt", "ğüşıöç".encode()) == "ğüşıöç"
    assert documents.extract_text("a.txt", "﻿metin".encode()) == "metin"
    assert documents.extract_text("a.txt", "ğüş".encode("cp1254")) == "ğüş"


def test_docx_paragraf_ve_tablo():
    metin = documents.extract_text("s.docx", docx_bayt(["1. Soru bir", "2. Soru iki"], tablo=[["A) 1", "B) 2"]]))
    assert "Soru bir" in metin and "Soru iki" in metin and "B) 2" in metin


def test_pdf_metni():
    metin = documents.extract_text("s.pdf", basit_pdf(["1. Birinci soru", "2. Ikinci soru"]))
    assert "Birinci soru" in metin and "Ikinci soru" in metin


def test_bozuk_dosyalar():
    with pytest.raises(documents.DocumentError):
        documents.extract_text("s.docx", b"docx degil")
    with pytest.raises(documents.DocumentError):
        documents.extract_text("s.pdf", b"%PDF-bozuk")


def test_taslaklar():
    (taslak,) = documents.drafts_from_text("1. Soru metni")
    assert taslak.text == "Soru metni" and taslak.recipe is None and taslak.needs_review
    assert "reçete" in taslak.review_note
```

`tests/test_services_pool.py` sonuna:
```python
from tests.test_ingest_documents import basit_pdf, docx_bayt  # noqa: E402


def test_yukleme_yonlendirmesi(conn):
    sonuc = pool.ingest_upload(conn, "sorular.DOCX", docx_bayt(["1. Bir", "2. İki"]), now=SIMDI)
    assert (sonuc.added, sonuc.templates, sonuc.needs_review) == (2, 0, 2)
    assert {k.origin for k in db.load_sources(conn)} == {"file"}
    assert pool.ingest_upload(conn, "s.pdf", basit_pdf(["1. Tek soru"]), now=SIMDI).added == 1
    assert pool.ingest_upload(conn, "h.txt", VERI.read_bytes(), now=SIMDI).templates == 3
    assert pool.ingest_upload(conn, "d.txt", "1. Düz metin sorusu".encode(), now=SIMDI).added == 1
    with pytest.raises(errors.Invalid, match="yapay zekâ"):
        pool.ingest_upload(conn, "foto.jpg", b"\xff\xd8\xff", now=SIMDI)
    with pytest.raises(errors.Invalid, match="desteklenmiyor"):
        pool.ingest_upload(conn, "x.exe", b"abc", now=SIMDI)
    with pytest.raises(errors.Invalid, match="okunamadı"):
        pool.ingest_upload(conn, "b.pdf", b"%PDF-bozuk", now=SIMDI)
```

`tests/api/test_pool.py` içinde `test_yukleme_hatalari` fonksiyonuna şu satırı ekle:
```python
    from tests.test_ingest_documents import docx_bayt

    assert yukle(client, ad="s.docx", icerik=docx_bayt(["1. Bir"]),
                 tur="application/vnd.openxmlformats-officedocument.wordprocessingml.document").status_code == 201
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_ingest_documents.py tests/test_services_pool.py tests/api/test_pool.py -q` → FAIL.

- [ ] **Adım 3: `documents.py`, `pool.ingest_upload` ve yönlendirici değişikliğini yaz.** `pypdf` uyarılarını (`logging`) test çıktısına sızdırmamak için `logging.getLogger("pypdf").setLevel(logging.ERROR)` modül yüklenirken ayarlanır. `.docx` belge sırası için `document.element.body` altındaki `w:p` ve `w:tbl` öğeleri sırayla gezilir.

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS.

- [ ] **Adım 5: Commit**

```bash
git add pyproject.toml questioncrator/ingest/documents.py questioncrator/services/pool.py questioncrator/api/routes_pool.py tests/test_ingest_documents.py tests/test_services_pool.py tests/api/test_pool.py
git commit -m "feat(ingest): txt/docx/pdf alımı, numaralı soru bölücü ve yükleme yönlendirmesi"
```

---
### Task 10: LLM katmanı (Anthropic SDK) ve LLM destekli uç noktalar

**Files:**
- Create: `questioncrator/llm/__init__.py` (`"""LLM katmanı (A5): istemci soyutlaması ve görevler."""`), `llm/client.py`, `llm/anthropic_client.py`, `llm/tasks.py`
- Modify: `questioncrator/services/pool.py` (`ingest_upload` LLM dalı, `suggest_recipe`), `questioncrator/services/cards.py` (`dress_card`), `questioncrator/api/deps.py` (`get_llm`), `questioncrator/api/routes_pool.py`, `questioncrator/api/routes_cards.py`, `questioncrator/api/routes_system.py`, `pyproject.toml` (`anthropic>=1.5` — 1.x `httpx2` tabanlıdır; test/istemci kodunda `httpx` yerine `import httpx2 as httpx`)
- Test: `tests/test_llm.py`, `tests/test_services_llm.py`, `tests/api/test_llm_endpoints.py`

**Interfaces:**
- Produces (client):
  - `client.LLMNotConfigured(RuntimeError)`, `client.LLMError(RuntimeError)` — Türkçe mesajlı
  - `client.ImageInput(media_type: str, data: bytes)` (frozen)
  - `client.LLMClient` (Protocol, runtime_checkable): `complete_json(self, *, system: str, prompt: str, schema: dict, images: Sequence[ImageInput] = (), max_tokens: int = 16000) -> dict`
  - `client.NullLLMClient` — her çağrıda `LLMNotConfigured("Yapay zekâ bağlantısı yapılandırılmadı.")`
  - `client.ScriptedLLMClient(responses: list[dict | Exception])` — sırayla döner/yükseltir; `calls: list[dict]` (her çağrının anahtar argümanları); yanıt biterse `AssertionError`
  - `client.get_llm_client(settings) -> LLMClient | None` — anahtar yoksa `None`, varsa `AnthropicLLMClient(settings.anthropic_api_key, settings.llm_model)`
- Produces (anthropic_client):
  - `AnthropicLLMClient(api_key: str, model: str, *, sdk_client: object | None = None)` — `sdk_client` testlerde sahte nesne
  - İstek: `sdk_client.beta.messages.create(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": [*görseller, {"type": "text", "text": prompt}]}], output_config={"format": {"type": "json_schema", "schema": schema}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Görsel bloğu: `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": base64}}`. Kurulu SDK `output_config`/`fallbacks` anahtarlarını kabul etmiyorsa aynı değerleri `extra_body` ile gönder (davranış aynı; testler anahtarların isteğe ulaştığını denetler — `extra_body` kullanılırsa test onu da kabul etmeli).
  - Yanıt: `stop_reason == "refusal"` → `LLMError("Yapay zekâ bu isteği işlemedi.")`; `"max_tokens"` → `LLMError("Yapay zekâ yanıtı yarıda kesildi.")`; ilk `text` bloğu `json.loads`, `dict` değilse ya da çözülemezse `LLMError("Yapay zekâ yanıtı okunamadı.")`
  - SDK hataları: `anthropic.RateLimitError` → `LLMError("Yapay zekâ servisi şu an yoğun, biraz sonra tekrar deneyin.")`; `anthropic.AuthenticationError`/`PermissionDeniedError` → `LLMError("Yapay zekâ anahtarı geçersiz.")`; diğer `anthropic.APIStatusError`, `anthropic.APIConnectionError` → `LLMError("Yapay zekâ servisine ulaşılamadı.")`. SDK istemcisi `max_retries=2`, `timeout=120.0` ile kurulur.
- Produces (tasks):
  - `tasks.LLMTaskFailed(RuntimeError)`
  - `tasks.DraftQuestion(text: str, answer_text: str | None, recipe: str | None, objective: str | None)`
  - `tasks.MAX_CHUNK_CHARS = 12000`
  - `tasks.structure_questions(llm, *, text: str | None = None, images: Sequence[ImageInput] = ()) -> list[DraftQuestion]` — metin `MAX_CHUNK_CHARS`'ı aşarsa `documents.split_numbered_questions` bloklarından parçalara bölünüp parça başına bir çağrı
  - `tasks.suggest_recipe(llm, *, question_text: str, answer_text: str | None) -> str` — boş reçete → `LLMTaskFailed("Yapay zekâ reçete öneremedi.")`
  - `tasks.dress_question(llm, *, text: str, answer_latex: str, bindings: dict[str, int], examples: list[FewShotExample]) -> str` — sonuçta her `abs(değer)` sayı olarak (`(?<!\d)N(?!\d)`) geçmiyorsa ya da metin boşsa/5000'i aşıyorsa `LLMTaskFailed("Güzelleştirilmiş metin sorudaki sayıları korumadı.")`
  - Şemalar (hepsi `additionalProperties: false`, tüm alanlar `required`, "yok" = boş dize):
    - yapı: `{"questions": [{"text": str, "answer_text": str, "recipe": str, "objective": str}]}`
    - reçete: `{"recipe": str}`
    - giydirme: `{"text": str}`
- Produces (servisler / API):
  - `pool.ingest_upload(..., llm)` — `llm` verilmişse `.txt` (markdown olmayan), `.docx`, `.pdf` için `structure_questions(text=...)` → taslaklar `origin="llm"` → `ingest_sources`; `LLMError`/`LLMTaskFailed` olursa sezgisel `drafts_from_text` yoluna düşer ve `problems`'a `("", "Yapay zekâ yanıt vermedi; sorular numaralarına göre ayrıldı.")` eklenir. Görsel: `structure_questions(images=[ImageInput(<mime>, data)])`; hata → `Unavailable(<mesaj>)`. Uzantıdan mime: `.png`→`image/png`, `.jpg/.jpeg`→`image/jpeg`.
  - `pool.suggest_recipe(conn, source_id, *, llm) -> str` — `llm is None` → `Unavailable("Yapay zekâ bağlantısı yapılandırılmadı.")`; kaydetmez
  - `cards.dress_card(conn, question_id, *, llm) -> Card` — değerlendirilmiş soru → `Conflict("Puanlanmış soru değiştirilemez.")`; örnekler `few_shot_examples(conn, objective=<şablon kazanımı>, k=3)`; başarıda yalnız `text` güncellenir
  - Hata eşleme: `LLMNotConfigured` → `Unavailable`, `LLMError` → `Unavailable(mesaj)`, `LLMTaskFailed` → `Invalid(mesaj)` (servis sınırında dönüştürülür)
  - `deps.get_llm(settings) -> LLMClient | None` (testlerde `app.dependency_overrides[deps.get_llm]`)
  - `POST /api/pool/sources/{id}/suggest-recipe` → 200 `{"recipe": str}`; `POST /api/cards/{id}/dress` → 200 `CardOut`; yükleme uç noktası `llm=get_llm(...)` geçirir; `GET /api/system/config` `llm_enabled = get_llm(...) is not None`

**İstem metinleri** (`tasks.py` içinde sabit, Türkçe; sistem istemi sabit kalır — önbellek dostu; değişken içerik yalnız kullanıcı isteminde):
- `STRUCTURE_SYSTEM`: "Sen Türkiye'deki dershaneler için soru havuzu hazırlayan bir matematik editörüsün. Sana verilen metin ya da görseldeki soruları tek tek ayır. Her soru için: `text` — soru metni, matematik ifadeleri `$...$` içinde LaTeX; şıklar varsa metne ekleme, yalnız kökü yaz. `answer_text` — doğru cevap insan dilinde (yoksa boş). `recipe` — cevabı hesaplayan tek bir SymPy ifadesi: yalnız sayılar, `x y z t n` gibi tek harfli değişkenler ve SymPy fonksiyonları (`diff`, `integrate`, `solve`, `simplify`, `Rational`, `Matrix`, `sqrt`, `factorial`...) kullan; tırnak, alt çizgi, atama, `import` yok; ondalık yerine `Rational(a, b)`; sorudaki her sayı reçetede aynı değerle geçmeli; hesaplanamayan (sözel, ispat, şekil gerektiren) sorularda boş bırak. `objective` — kısa kazanım etiketi, küçük harf, `ders.konu` biçiminde (ör. `matematik.olasilik`), bilinmiyorsa boş. Soru uydurma, metinde olmayan soruyu ekleme."
- `RECIPE_SYSTEM`: yapı istemindeki `recipe` kuralları + "Yalnız `recipe` alanını doldur; cevabı hesaplayamıyorsan boş bırak."
- `DRESS_SYSTEM`: "Verilen matematik sorusunu, anlamını, sayılarını ve cevabını değiştirmeden daha anlaşılır ve günlük hayata bağlı bir Türkçe ile yeniden yaz. Bütün sayılar aynen kalmalı; matematik `$...$` içinde LaTeX. Örnekler bu hocanın beğendiği üsluptadır."

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_llm.py`:
```python
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx  # anthropic 1.x httpx2 kullanır; httpx nesneleri reddedilir
import pytest

from questioncrator.config import Settings
from questioncrator.llm import client as llm_client
from questioncrator.llm import tasks
from questioncrator.llm.anthropic_client import AnthropicLLMClient
from questioncrator.models import FewShotExample


class SahteSDK:
    def __init__(self, yanit=None, hata=None):
        self.yanit, self.hata, self.cagrilar = yanit, hata, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.cagrilar.append(kwargs)
        if self.hata:
            raise self.hata
        return self.yanit


def mesaj(metin, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=metin)])


def istek_alani(cagri, anahtar):
    return cagri.get(anahtar, cagri.get("extra_body", {}).get(anahtar))


def test_anthropic_istemcisi_istek_bicimi():
    sdk = SahteSDK(mesaj('{"recipe": "2*x"}'))
    istemci = AnthropicLLMClient("k", "claude-opus-5", sdk_client=sdk)
    sema = {"type": "object", "properties": {"recipe": {"type": "string"}}, "required": ["recipe"],
            "additionalProperties": False}
    sonuc = istemci.complete_json(system="S", prompt="P", schema=sema,
                                  images=[llm_client.ImageInput("image/png", b"\x89PNG")])
    assert sonuc == {"recipe": "2*x"}
    (cagri,) = sdk.cagrilar
    assert cagri["model"] == "claude-opus-5" and cagri["system"] == "S"
    icerik = cagri["messages"][0]["content"]
    assert icerik[0]["type"] == "image" and icerik[0]["source"]["data"] == base64.b64encode(b"\x89PNG").decode()
    assert icerik[-1] == {"type": "text", "text": "P"}
    assert istek_alani(cagri, "output_config") == {"format": {"type": "json_schema", "schema": sema}}
    assert istek_alani(cagri, "fallbacks") == "default"


@pytest.mark.parametrize(
    ("yanit", "parca"),
    [(mesaj("", stop="refusal"), "işlemedi"), (mesaj("{", stop="max_tokens"), "yarıda"), (mesaj("[1]"), "okunamadı")],
)
def test_anthropic_yanit_hatalari(yanit, parca):
    with pytest.raises(llm_client.LLMError, match=parca):
        AnthropicLLMClient("k", "m", sdk_client=SahteSDK(yanit)).complete_json(system="", prompt="", schema={})


def test_anthropic_sdk_hatalari():
    istek = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    hiz = anthropic.RateLimitError("yavaş", response=httpx.Response(429, request=istek), body=None)
    with pytest.raises(llm_client.LLMError, match="yoğun"):
        AnthropicLLMClient("k", "m", sdk_client=SahteSDK(hata=hiz)).complete_json(system="", prompt="", schema={})
    baglanti = anthropic.APIConnectionError(request=istek)
    with pytest.raises(llm_client.LLMError, match="ulaşılamadı"):
        AnthropicLLMClient("k", "m", sdk_client=SahteSDK(hata=baglanti)).complete_json(system="", prompt="", schema={})


def test_istemci_secimi_ve_null():
    assert llm_client.get_llm_client(Settings(data_dir="x")) is None
    assert isinstance(llm_client.get_llm_client(Settings(data_dir="x", anthropic_api_key="k")), AnthropicLLMClient)
    with pytest.raises(llm_client.LLMNotConfigured):
        llm_client.NullLLMClient().complete_json(system="", prompt="", schema={})
    assert isinstance(llm_client.ScriptedLLMClient([]), llm_client.LLMClient)


def test_yapilandirma_gorevi_normallestirir():
    llm = llm_client.ScriptedLLMClient([{"questions": [
        {"text": " $3x^2$ ifadesinin türevi? ", "answer_text": "6x", "recipe": "diff(3*x**2, x)", "objective": "matematik.turev"},
        {"text": "  ", "answer_text": "", "recipe": "", "objective": ""},
        {"text": "Sözel soru", "answer_text": "", "recipe": "", "objective": ""},
    ]}])
    taslaklar = tasks.structure_questions(llm, text="1. ...")
    assert [t.text for t in taslaklar] == ["$3x^2$ ifadesinin türevi?", "Sözel soru"]
    assert taslaklar[1].recipe is None and taslaklar[1].objective is None
    assert llm.calls[0]["system"] == tasks.STRUCTURE_SYSTEM


def test_uzun_metin_parcalara_bolunur():
    blok = "Soru " + "x" * 5000
    metin = "\n".join(f"{i}. {blok}" for i in range(1, 6))
    llm = llm_client.ScriptedLLMClient([{"questions": []}] * 5)
    tasks.structure_questions(llm, text=metin)
    assert 2 <= len(llm.calls) <= 5
    assert all(len(c["prompt"]) <= tasks.MAX_CHUNK_CHARS + 2000 for c in llm.calls)


def test_recete_onerisi():
    assert tasks.suggest_recipe(llm_client.ScriptedLLMClient([{"recipe": " 2*3 "}]),
                                question_text="2 kere 3?", answer_text=None) == "2*3"
    with pytest.raises(tasks.LLMTaskFailed):
        tasks.suggest_recipe(llm_client.ScriptedLLMClient([{"recipe": ""}]), question_text="?", answer_text=None)


def test_giydirme_sayilari_korumali():
    ornek = FewShotExample(question_text="Bir manav 4 kasa...", answer_latex="12", quality=9, objective="k")
    iyi = llm_client.ScriptedLLMClient([{"text": "Ayşe'nin bahçesinde 12 ve 7 elma var: $12-7$?"}])
    assert "12" in tasks.dress_question(iyi, text="$12-7$", answer_latex="5", bindings={"p0": 12, "p1": -7}, examples=[ornek])
    assert "Bir manav" in iyi.calls[0]["prompt"]
    kotu = llm_client.ScriptedLLMClient([{"text": "Ayşe'nin 13 elması var"}])
    with pytest.raises(tasks.LLMTaskFailed):
        tasks.dress_question(kotu, text="$12-7$", answer_latex="5", bindings={"p0": 12, "p1": -7}, examples=[])
    ic_ice = llm_client.ScriptedLLMClient([{"text": "Toplam 120 elma"}])
    with pytest.raises(tasks.LLMTaskFailed):
        tasks.dress_question(ic_ice, text="$12$", answer_latex="12", bindings={"p0": 12}, examples=[])
```

(Not: yapı yanıtındaki `objective` değeri **test verisidir**; `tests/` konu bağımsızlığı taramasının dışındadır.)

`tests/test_services_llm.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest

from questioncrator import db
from questioncrator.llm.client import LLMError, ScriptedLLMClient
from questioncrator.services import cards, errors, pool
from tests.test_ingest_documents import docx_bayt

VERI = Path(__file__).parent / "data" / "ornek_havuz.md"
SIMDI = "2026-09-15T10:00:00+00:00"

# Controller'ın elle yazdığı "yapay zekâ" yanıtı: gerçek bir modelin döndüreceği biçimde.
YAPI_YANITI = {"questions": [
    {"text": "$f(x) = 2x^3 - 4x$ fonksiyonunun $x = 1$ noktasındaki eğimi kaçtır?",
     "answer_text": "f'(1) = 6 - 4 = 2", "recipe": "diff(2*x**3 - 4*x, x).subs(x, 1)", "objective": "matematik.egim"},
    {"text": "Bir zar iki kez atılıyor. Toplamın 7 olma olasılığı kaçtır?",
     "answer_text": "1/6", "recipe": "", "objective": "matematik.olasilik"},
]}


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def test_llm_ile_docx_alimi(conn):
    llm = ScriptedLLMClient([YAPI_YANITI])
    sonuc = pool.ingest_upload(conn, "s.docx", docx_bayt(["1. eğim", "2. zar"]), now=SIMDI, llm=llm)
    assert (sonuc.added, sonuc.templates, sonuc.needs_review) == (2, 1, 1)
    assert {k.origin for k in db.load_sources(conn)} == {"llm"}
    assert "eğim" not in llm.calls[0]["system"]


def test_llm_hatasinda_sezgisel_yola_duser(conn):
    llm = ScriptedLLMClient([LLMError("Yapay zekâ servisine ulaşılamadı.")])
    sonuc = pool.ingest_upload(conn, "s.docx", docx_bayt(["1. Bir", "2. İki"]), now=SIMDI, llm=llm)
    assert sonuc.added == 2 and any("numaralarına göre" in n for _, n in sonuc.problems)


def test_gorsel_alimi(conn):
    llm = ScriptedLLMClient([YAPI_YANITI])
    assert pool.ingest_upload(conn, "foto.PNG", b"\x89PNG\r\n", now=SIMDI, llm=llm).added == 2
    assert llm.calls[0]["images"][0].media_type == "image/png"
    with pytest.raises(errors.Unavailable):
        pool.ingest_upload(conn, "f.jpg", b"\xff\xd8", now=SIMDI, llm=ScriptedLLMClient([LLMError("x")]))


def test_recete_onerisi_servisi(conn):
    kaynak = pool.create_source(conn, text="2 kere 3 kaçtır?", recipe=None, answer_text="6", objective=None, now=SIMDI)
    assert pool.suggest_recipe(conn, kaynak.source.id, llm=ScriptedLLMClient([{"recipe": "2*3"}])) == "2*3"
    with pytest.raises(errors.Unavailable):
        pool.suggest_recipe(conn, kaynak.source.id, llm=None)
    with pytest.raises(errors.NotFound):
        pool.suggest_recipe(conn, "s_yok", llm=ScriptedLLMClient([]))


def test_kart_giydirme(conn):
    pool.ingest_markdown(conn, VERI.read_text(encoding="utf-8"), now=SIMDI)
    kart = cards.produce_cards(conn, count=1, now=SIMDI, actor_id=None, seed=4)[0]
    sayilar = " ".join(str(abs(v)) for v in kart.question.bindings.values())
    guzel = cards.dress_card(conn, kart.question.id, llm=ScriptedLLMClient([{"text": f"Günlük hayattan: {sayilar}"}]))
    assert guzel.question.text.startswith("Günlük hayattan") and guzel.question.answer_latex == kart.question.answer_latex
    with pytest.raises(errors.Invalid):
        cards.dress_card(conn, kart.question.id, llm=ScriptedLLMClient([{"text": "sayısız metin"}]))
    cards.review_card(conn, kart.question.id, approved=True, difficulty=5, quality=5, now=SIMDI, actor_id=None)
    with pytest.raises(errors.Conflict):
        cards.dress_card(conn, kart.question.id, llm=ScriptedLLMClient([]))
```

`tests/api/test_llm_endpoints.py`:
```python
from __future__ import annotations

from questioncrator.api import deps
from questioncrator.llm.client import ScriptedLLMClient


def test_llm_yokken_503_ve_config(client, hoca):
    kaynak = client.post("/api/pool/sources", json={"text": "2 kere 3?"}).json()
    yanit = client.post(f"/api/pool/sources/{kaynak['id']}/suggest-recipe")
    assert yanit.status_code == 503 and "yapılandırılmadı" in yanit.json()["detail"]
    assert client.get("/api/system/config").json()["llm_enabled"] is False


def test_llm_varken_oneri(client, app, hoca):
    betik = ScriptedLLMClient([{"recipe": "2*3"}])
    app.dependency_overrides[deps.get_llm] = lambda: betik
    kaynak = client.post("/api/pool/sources", json={"text": "2 kere 3?"}).json()
    assert client.post(f"/api/pool/sources/{kaynak['id']}/suggest-recipe").json() == {"recipe": "2*3"}
    assert client.get("/api/system/config").json()["llm_enabled"] is True
    app.dependency_overrides.clear()
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_llm.py tests/test_services_llm.py tests/api/test_llm_endpoints.py -q` → FAIL.

- [ ] **Adım 3: Uygula.** `llm/client.py` → `llm/anthropic_client.py` → `llm/tasks.py` → servis dalları → API. `anthropic` SDK'sı yalnız `anthropic_client.py` içinde import edilir (paketin geri kalanı SDK'sız çalışabilir). Few-shot örnekleri kullanıcı istemine `Örnek (kurgu puanı N/10): ...` satırlarıyla eklenir.

- [ ] **Adım 4: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS. Ağ çağrısı olmadığını doğrula: `ANTHROPIC_API_KEY= .venv/bin/pytest tests/test_llm.py -q` aynı sonucu verir.

- [ ] **Adım 5: Commit**

```bash
git add pyproject.toml questioncrator/llm questioncrator/services questioncrator/api tests/test_llm.py tests/test_services_llm.py tests/api/test_llm_endpoints.py
git commit -m "feat(llm): Anthropic SDK istemcisi, soru yapılandırma/reçete önerisi/giydirme görevleri ve uç noktaları"
```

---
### Task 11: Demo havuzu ve kayıtta örnek içerikle başlama

Satış demosunun ve ilk deneyimin temeli: yeni bir dershane kaydolduğunda havuz boş gelmez.

**Files:**
- Create: `questioncrator/demo/__init__.py` (`"""Örnek havuz içeriği."""`), `questioncrator/demo/havuz.md`, `questioncrator/services/demo.py`
- Modify: `questioncrator/api/routes_auth.py` (`load_demo`), `pyproject.toml` (`[tool.setuptools.package-data]` içine `"questioncrator.demo" = ["*.md"]`)
- Test: `tests/test_demo.py`, `tests/api/test_auth.py` (ekleme)

**Interfaces:**
- Produces:
  - `demo.DEMO_PATH: Path` — paketlenmiş `havuz.md`
  - `demo.load_demo(conn, *, now: str) -> pool.IngestResult` — havuzu alır (kaynaklar `origin="markdown"`)
  - `POST /api/auth/register` `load_demo=true` ise yeni çalışma alanına demo yüklenir (hata olursa kayıt yine başarılı; sessizce atlanır ve sunucu günlüğüne yazılır)

**İçerik kuralları (`demo/havuz.md`) — testlerle zorlanır:**
- En az **30** soru bloğu, her biri `### Soru` / `### Cevap` / `### Kazanım` (isteğe bağlı `### Çözüm`).
- En az **8 farklı kazanım**; kazanım etiketleri `ders.konu` biçiminde, küçük harf, Türkçe karaktersiz (ör. `matematik.carpanlara_ayirma`).
- Sorular Türkiye lise/TYT-AYT düzeyinde, **konu çeşitliliği geniş** (cebir, oran-orantı, olasılık, sayı kuramı, üslü/köklü sayılar, denklem sistemleri, geometri hesapları, fonksiyon değeri, diziler, yüzde-faiz gibi). Şekil/grafik gerektiren soru yok.
- Soru metinlerinde matematik `$...$` içinde LaTeX; metindeki her sayısal katsayı `### Cevap` reçetesinde **aynı değerle** geçmeli (şablon çıkarımı metin ve reçeteyi aynı parametreye bağlayabilsin).
- `### Cevap` tek satırlık geçerli bir SymPy ifadesi; `mathenv.check_recipe`'ten geçmeli (dizge yok, yasak ad yok); ondalık yerine `Rational(a, b)`.
- Her sorunun en az bir parametreleştirilebilir sayısı olmalı (aksi halde şablon çıkmaz).
- Üretilen varyantların çoğu 5 şıklı olabilmeli (çeldirici üretilebilsin): cevabı tek bir sabit sayı ya da ifade olan sorular tercih edilir; cevabı `True/False` ya da küme olan sorulardan kaçın.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_demo.py`:

```python
from __future__ import annotations

import random

import pytest

from questioncrator import db, mathenv
from questioncrator.ingest import markdown
from questioncrator.services import cards, demo

SIMDI = "2026-09-15T10:00:00+00:00"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(scope="module")
def kaynaklar():
    return markdown.load_pool(demo.DEMO_PATH)


def test_icerik_kapsami(kaynaklar):
    assert len(kaynaklar) >= 30
    assert all(k.recipe for k in kaynaklar)
    kazanimlar = {k.objective for k in kaynaklar}
    assert len(kazanimlar) >= 8
    assert all(k and k.islower() and "." in k and k.isascii() for k in kazanimlar)
    assert all("$" in k.text for k in kaynaklar)


def test_receteler_guvenli_ve_hesaplanabilir(kaynaklar):
    for k in kaynaklar:
        mathenv.check_recipe(k.recipe)
        mathenv.parse_with_timeout(k.recipe)


def test_yukleme_hepsinden_sablon_uretir(conn):
    sonuc = demo.load_demo(conn, now=SIMDI)
    assert sonuc.added >= 30
    assert sonuc.problems == [], f"şablona çevrilemeyen sorular: {sonuc.problems}"
    assert sonuc.templates == sonuc.added and sonuc.needs_review == 0


def test_demodan_uretim_kaliteli_kart_verir(conn):
    demo.load_demo(conn, now=SIMDI)
    uretilen = []
    for tohum in range(5):
        uretilen += cards.produce_cards(conn, count=20, now=SIMDI, actor_id=None, seed=tohum)
    assert len(uretilen) >= 20
    assert all("{p" not in k.question.text for k in uretilen)
    siklilar = [k for k in uretilen if len(k.question.choices) == 5]
    assert len(siklilar) >= len(uretilen) // 2
    assert all(k.question.choices[k.question.correct_index] == k.question.answer_latex for k in siklilar)
    assert len({k.question.template_id for k in uretilen}) >= 8
```

`tests/api/test_auth.py` sonuna:
```python
def test_kayitta_demo_havuzu(client):
    client.post("/api/auth/register", json={
        "name": "A", "email": "demo@ornek.com", "password": "parola123",
        "workspace_name": "Demo Dershane", "load_demo": True,
    })
    assert client.get("/api/pool/summary").json()["total"] >= 30
    assert client.get("/api/stats").json()["next_step"] == "generate"
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_demo.py -q` → FAIL.

- [ ] **Adım 3: `demo/havuz.md`'yi yaz.** Soruları sen üreteceksin; her soruyu yazdıktan sonra reçetesini `.venv/bin/python -c "from questioncrator.mathenv import parse; print(parse('<reçete>'))"` ile doğrula. Yazım bittiğinde tüm dosyayı tek seferde şu betikle denetle ve hatalıları düzelt:
```bash
.venv/bin/python - <<'PY'
from questioncrator.ingest import markdown
from questioncrator.templating import extract
from questioncrator.services import demo
for k in markdown.load_pool(demo.DEMO_PATH):
    try:
        t = extract.extract_template(k, "t")
        print("OK ", k.objective, len(t.parameters), t.skeleton[:60])
    except Exception as e:
        print("HATA", k.text[:60], type(e).__name__, e)
PY
```

- [ ] **Adım 4: `services/demo.py` ve kayıt bağlantısını yaz.** `DEMO_PATH = Path(__file__).resolve().parent.parent / "demo" / "havuz.md"` (paket içi). Kayıt uç noktasında demo yükleme `try/except Exception` ile sarılır; hata `logging.getLogger("questioncrator").warning(...)` ile yazılır, kayıt bozulmaz.

- [ ] **Adım 5: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS. (`test_demodan_uretim_kaliteli_kart_verir` yavaşsa kabul; 5 tohum × 20 kart.)

- [ ] **Adım 6: Commit**

```bash
git add pyproject.toml questioncrator/demo questioncrator/services/demo.py questioncrator/api/routes_auth.py tests/test_demo.py tests/api/test_auth.py
git commit -m "feat(demo): 30+ soruluk örnek havuz ve kayıtta demo içerikle başlama"
```

---

### Task 12: CLI, bağımlılık temizliği ve README

**Files:**
- Create: `questioncrator/cli.py`, `tests/test_cli.py`
- Modify: `pyproject.toml` (`[project.scripts] questioncrator = "questioncrator.cli:main"`; `streamlit` bağımlılığı **kaldırılır**), `README.md`
- Delete: yok (Streamlit uygulaması Plan A'da hiç yazılmadı)

**Interfaces:**
- Produces:
  - `cli.main(argv: list[str] | None = None) -> int` — `argparse`; alt komutlar:
    - `serve [--host 127.0.0.1] [--port 8000] [--reload]` → `uvicorn.run("questioncrator.api.app:app_factory", factory=True, ...)`; `app.py` içinde `def app_factory() -> FastAPI: return create_app()`
    - `create-user --email --name --workspace [--password]` → parola verilmezse `getpass`; yeni çalışma alanı + owner; kimlikleri yazdırır
    - `set-password --email [--password]` → `accounts.set_password`
    - `backup --workspace <id> --out <yol>` → `storage.backup_workspace` çıktısını dosyaya yazar
    - `list-workspaces` → `<id>\t<ad>\t<üye sayısı>` satırları
  - Tüm çıktılar Türkçe; hata durumunda `stderr` + dönüş kodu 1.

- [ ] **Adım 1: Başarısız testleri yaz** — `tests/test_cli.py`:

```python
from __future__ import annotations

import sqlite3

import pytest

from questioncrator import accounts, cli, storage
from questioncrator.config import Settings


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    return Settings(data_dir=tmp_path)


def test_kullanici_olusturma_ve_parola(ortam, capsys):
    assert cli.main(["create-user", "--email", "h@ornek.com", "--name", "Hoca",
                     "--workspace", "Işık", "--password", "parola123"]) == 0
    cikti = capsys.readouterr().out
    assert "w_" in cikti and "u_" in cikti
    conn = accounts.connect_accounts(storage.accounts_path(ortam))
    assert accounts.authenticate(conn, email="h@ornek.com", password="parola123")
    assert cli.main(["create-user", "--email", "h@ornek.com", "--name", "X",
                     "--workspace", "Y", "--password", "parola123"]) == 1
    assert cli.main(["set-password", "--email", "h@ornek.com", "--password", "yeniparola"]) == 0
    conn2 = accounts.connect_accounts(storage.accounts_path(ortam))
    assert accounts.authenticate(conn2, email="h@ornek.com", password="yeniparola")
    assert cli.main(["set-password", "--email", "yok@ornek.com", "--password", "yeniparola"]) == 1


def test_liste_ve_yedek(ortam, tmp_path, capsys):
    cli.main(["create-user", "--email", "h@ornek.com", "--name", "Hoca",
              "--workspace", "Işık", "--password", "parola123"])
    capsys.readouterr()
    assert cli.main(["list-workspaces"]) == 0
    satir = capsys.readouterr().out.strip()
    alan_id = satir.split("\t")[0]
    assert alan_id.startswith("w_") and "Işık" in satir
    hedef = tmp_path / "yedek.db"
    assert cli.main(["backup", "--workspace", alan_id, "--out", str(hedef)]) == 0
    assert sqlite3.connect(hedef).execute("PRAGMA user_version").fetchone()[0] >= 2
    assert cli.main(["backup", "--workspace", "w_000000000000", "--out", str(hedef)]) == 1


def test_bilinmeyen_komut(ortam):
    with pytest.raises(SystemExit):
        cli.main(["olmayan"])
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `.venv/bin/pytest tests/test_cli.py -q` → FAIL.

- [ ] **Adım 3: `cli.py`'yi yaz** (uvicorn yalnız `serve` içinde import edilir).

- [ ] **Adım 4: `pyproject.toml`'u güncelle** — `streamlit` bağımlılığını kaldır, `[project.scripts]` ekle, `.venv/bin/pip install -e ".[dev]" -q` ile yeniden kur; `.venv/bin/questioncrator --help` çalışmalı.

- [ ] **Adım 5: README.md'yi yeniden yaz** (Türkçe): ürünün ne olduğu (2 paragraf), kurulum (venv + `pip install -e ".[dev]"`), geliştirme (`questioncrator serve`, `pytest`, `ruff`), ortam değişkenleri tablosu (`QC_DATA_DIR`, `QC_COOKIE_SECURE`, `QC_ALLOW_REGISTRATION`, `QC_LLM_MODEL`, `ANTHROPIC_API_KEY`, `QC_SANDBOX`, `QC_WEB_DIST`), CLI komutları, veri düzeni ve yedekleme, güvenlik notu (reçete değerlendirmesi izole süreçte), "LLM bağlamak" bölümü (anahtar verilince neler açılır). Streamlit'e atıf kalmamalı.

- [ ] **Adım 6: Testleri çalıştır** — `.venv/bin/pytest -q && .venv/bin/ruff check .` → PASS. Ayrıca elle: `QC_DATA_DIR=/tmp/qc-deneme .venv/bin/questioncrator serve --port 8123 &` → `curl -s localhost:8123/api/system/health` → `{"status":"ok"}`; süreci kapat. Sonucu rapora yaz.

- [ ] **Adım 7: Commit**

```bash
git add pyproject.toml questioncrator/cli.py questioncrator/api/app.py README.md tests/test_cli.py
git commit -m "feat(cli): serve/create-user/set-password/backup komutları, Streamlit bağımlılığı kaldırıldı"
```

---

## Plan B Bitiş Kontrolü

- [ ] `.venv/bin/pytest -q` yeşil, `.venv/bin/ruff check .` temiz.
- [ ] `tests/test_topic_agnostic.py` hâlâ geçiyor (API ve servisler dahil).
- [ ] Kiracı izolasyonu testleri: başka çalışma alanının her kaydı 404.
- [ ] Demo havuzuyla kayıt → kart üret → puanla → sınav oluştur → docx indir akışı API testlerinde uçtan uca geçiyor.
- [ ] LLM anahtarsız tüm akışlar çalışıyor; `GET /api/system/config` `llm_enabled=false`.
- [ ] Bağımsız kod incelemesi (tüm plan aralığı) + bulguların ikinci geçişte doğrulanması.
