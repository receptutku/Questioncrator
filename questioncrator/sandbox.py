"""Ağır ve güvenilmeyen SymPy işlerini ayrı süreçte, süre sınırıyla çalıştırır.

İş parçacığı zorla durdurulamaz; süresi dolan bir hesap sunucu sürecinde
sonsuza dek CPU yiyebilir. Bu yüzden çekirdek işler kalıcı işçi
süreçlerde koşar. Süre aşılırsa işçi öldürülür ve yerine yenisi açılır.

Güvenlik sınırı: Bu modül kod çalıştırmaya karşı tek başına bir sınır
DEĞİLDİR; o sınır reçete bekçileridir (`questioncrator.mathenv`). Bu taraf
CPU (süre sınırı + öldürme), bellek (Linux'ta `RLIMIT_AS`) ve aktarım
güvenliği sağlar: işçiden gelen yanıt güvenilmeyen bayt kabul edilir.
Ebeveyn yanıtı boyut sınırıyla okur ve yalnız beyaz listedeki türleri
(ilkel türler ve kaplar, `questioncrator.models` veri sınıfları, yerleşik ve
paket içi `Exception` alt sınıfları) açan kısıtlı bir unpickler kullanır.
SymPy nesneleri de reddedilir: açılırken `cls(*args)` ile yeniden kurulup
ebeveynde süresiz hesap yapabilirler. Reddedilen tür `SandboxCrashed` olur.

İşçiler `forkserver` bağlamıyla açılır; sunucu `sympy` ve
`questioncrator.mathenv` modüllerini önceden yükler, böylece reçete
bekçileri her işçide daha ilk işten önce kuruludur. İşçi açılışında aynı
modüller yeniden içe aktarılır: önyükleme bir nedenle atlanmış olsa bile
bekçiler kurulmadan hiçbir iş çalışmaz.

İşçi şu durumlarda sonucu gönderdikten sonra kendini kapatır (yenisi
açılır): kısa bir bekleme penceresinden sonra hâlâ çalışan yardımcı iş
parçacığı kaldıysa, hata zincirinde `MemoryError` varsa ya da sonuç
aktarılamadıysa.

Bellek sınırı (`RLIMIT_AS`) işçi başında, fork'tan sonra kurulur; forkserver
sürecini ve ebeveyni etkilemez. Sınır yalnız Linux'ta uygulanır: macOS
`RLIMIT_AS`i uygulamaz, orada bellek koruması yoktur. Üretim ortamı
Docker/Linux olduğu için bu kabul edilmiştir.

Ortam (havuz kurulurken bir kez okunur): `QC_SANDBOX` (`process` | `inline`),
`QC_SANDBOX_WORKERS` (2), `QC_SANDBOX_MEMORY_MB` (1024),
`QC_SANDBOX_MAX_RESULT_MB` (16).
"""

from __future__ import annotations

import atexit
import builtins
import dataclasses
import importlib
import io
import multiprocessing
import os
import pickle
import sys
import threading
import time
from collections.abc import Callable
from multiprocessing.reduction import ForkingPickler
from typing import Any, TypeVar

T = TypeVar("T")

_PRELOAD = ["sympy", "questioncrator.mathenv"]
_PACKAGE = "questioncrator"
_MODELS = "questioncrator.models"
# İşçi sonucu gönderirken yardımcı iş parçacıklarının kapanmasını bekleme penceresi.
_THREAD_GRACE_SECONDS = 0.1

_POOL_LOCK = threading.Lock()
_POOL: _Pool | None = None


class SandboxTimeout(Exception):
    """İş verilen sürede bitmedi; işçi öldürüldü."""


class SandboxCrashed(Exception):
    """İşçi süreç beklenmedik biçimde sonlandı ya da sonuç aktarılamadı."""


def _mode() -> str:
    return os.environ.get("QC_SANDBOX", "process")


def _worker_count() -> int:
    return max(1, int(os.environ.get("QC_SANDBOX_WORKERS", "2")))


def _memory_mb() -> int:
    return int(os.environ.get("QC_SANDBOX_MEMORY_MB", "1024"))


def _max_result_bytes() -> int:
    return max(1, int(os.environ.get("QC_SANDBOX_MAX_RESULT_MB", "16"))) * 1024 * 1024


def _context() -> Any:
    if sys.platform == "win32":
        return multiprocessing.get_context("spawn")
    ctx = multiprocessing.get_context("forkserver")
    ctx.set_forkserver_preload(_PRELOAD)
    return ctx


# --- Ebeveyn: kısıtlı açma ----------------------------------------------


class _RefusedType(pickle.UnpicklingError):
    """Beyaz listede olmayan bir tür yanıtta geçti."""


def _safe_bytes(*args: Any) -> bytes:
    # `bytes(n)` küçük bir yükle dev tahsis yaptırır; yalnız hazır içerik kabul.
    if args and isinstance(args[0], int):
        raise _RefusedType("builtins.bytes(int)")
    return bytes(*args)


_BUILTIN_TYPES: dict[str, Any] = {
    "int": int,
    "float": float,
    "complex": complex,
    "str": str,
    "bytes": _safe_bytes,
    "bool": bool,
    "NoneType": type(None),
    "tuple": tuple,
    "list": list,
    "dict": dict,
    "set": set,
    "frozenset": frozenset,
}

# Paket içi sınıflarda bu kancalardan biri tanımlıysa açma sırasında rastgele
# kod çalışabilir; böyle sınıflar beyaz listeye girmez.
_EXCEPTION_HOOKS = (
    "__reduce__",
    "__reduce_ex__",
    "__setstate__",
    "__new__",
    "__init__",
    "__setattr__",
    "__getattr__",
    "__getattribute__",
)
_DATACLASS_HOOKS = (
    "__reduce__",
    "__reduce_ex__",
    "__setstate__",
    "__new__",
    "__post_init__",
    "__getattr__",
    "__getattribute__",
)


def _defines_hook(cls: type, hooks: tuple[str, ...]) -> bool:
    for klass in cls.__mro__:
        module = getattr(klass, "__module__", "")
        if module == _PACKAGE or module.startswith(_PACKAGE + "."):
            if any(hook in vars(klass) for hook in hooks):
                return True
    return False


def _allowed_class(module: str, name: str) -> Any | None:
    if "." in name:
        return None
    if module == "builtins":
        if name in _BUILTIN_TYPES:
            return _BUILTIN_TYPES[name]
        obj = getattr(builtins, name, None)
        if isinstance(obj, type) and issubclass(obj, Exception):
            return obj
        return None
    if module != _PACKAGE and not module.startswith(_PACKAGE + "."):
        return None
    # İçe aktarma yapılmaz: işçinin seçtiği bir modülün yan etkisi ebeveynde
    # çalışmasın. Yalnız ebeveynde zaten yüklü olan paket modüllerine bakılır.
    loaded = sys.modules.get(module)
    obj = getattr(loaded, name, None) if loaded is not None else None
    if not isinstance(obj, type) or obj.__module__ != module or obj.__qualname__ != name:
        return None
    if module == _MODELS and dataclasses.is_dataclass(obj):
        return None if _defines_hook(obj, _DATACLASS_HOOKS) else obj
    if issubclass(obj, Exception):
        return None if _defines_hook(obj, _EXCEPTION_HOOKS) else obj
    return None


class _ResultUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        allowed = _allowed_class(module, name)
        if allowed is None:
            raise _RefusedType(f"{module}.{name}")
        return allowed

    def persistent_load(self, pid: Any) -> Any:
        raise _RefusedType("persistent_id")


def _load_reply(raw: bytes) -> tuple[str, Any, bool]:
    reply = _ResultUnpickler(io.BytesIO(raw)).load()
    if not (isinstance(reply, tuple) and len(reply) == 3):
        raise pickle.UnpicklingError("yanıt biçimi geçersiz")
    status, value, retire = reply
    valid = (
        (status == "ok")
        or (status == "err" and isinstance(value, Exception))
        or (status == "crash" and isinstance(value, str))
    )
    if not valid or not isinstance(retire, bool):
        raise pickle.UnpicklingError("yanıt biçimi geçersiz")
    return status, value, retire


# --- İşçi ----------------------------------------------------------------


def _limit_memory(memory_mb: int) -> None:
    if not sys.platform.startswith("linux"):
        return
    import resource

    limit = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _has_memory_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen or len(seen) > 100:
            continue
        seen.add(id(current))
        if isinstance(current, MemoryError):
            return True
        stack.extend((current.__cause__, current.__context__))
    return False


def _lingering_threads() -> bool:
    """Pencere içinde kapanmayan yardımcı iş parçacığı var mı?

    `ThreadPoolExecutor.shutdown(wait=False)` sonrası iş parçacığı birkaç
    milisaniye içinde çıkar; bu yüzden anlık sayım yerine kısa süre birleşilir.
    Gerçekten süren bir hesap pencereden sonra hâlâ canlıdır.
    """
    deadline = time.monotonic() + _THREAD_GRACE_SECONDS
    current = threading.current_thread()
    for thread in threading.enumerate():
        if thread is current:
            continue
        try:
            thread.join(max(0.0, deadline - time.monotonic()))
        except Exception:  # noqa: BLE001 — birleşilemeyen iş parçacığı canlı sayılır
            return True
        if thread.is_alive():
            return True
    return False


def _encode(status: str, value: Any, retire: bool, max_bytes: int) -> tuple[bytes, bool]:
    """Yanıtı baytlar; aktarılamayan ya da sınırı aşan sonuç işçiyi emekli eder."""
    try:
        data = bytes(ForkingPickler.dumps((status, value, retire)))
    except Exception as exc:  # noqa: BLE001 — aktarılamayan her değer
        message = f"sonuç aktarılamadı: {type(exc).__name__}: {exc}"
        return bytes(ForkingPickler.dumps(("crash", message, True))), True
    if len(data) > max_bytes:
        message = f"sonuç boyut sınırını aştı ({len(data)} > {max_bytes} bayt)"
        return bytes(ForkingPickler.dumps(("crash", message, True))), True
    return data, retire


def _serve(conn: Any, memory_mb: int, max_bytes: int) -> None:
    # Ayarlar ortamdan değil argümandan gelir: forkserver'dan doğan işçi,
    # ebeveynin güncel ortamını değil forkserver'ın ortamını görür.
    _limit_memory(memory_mb)
    for name in _PRELOAD:
        importlib.import_module(name)
    while True:
        try:
            fn, args, kwargs = conn.recv()
        except EOFError:
            return
        except Exception as exc:  # noqa: BLE001 — iş işçide açılamadı
            conn.send_bytes(_encode("crash", f"iş aktarılamadı: {exc}", True, max_bytes)[0])
            return
        retire = False
        try:
            status, value = "ok", fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — her hata ebeveyne taşınır
            status, value = "err", exc
            retire = _has_memory_error(exc)
        except BaseException as exc:  # noqa: BLE001 — SystemExit vb. ebeveyni durdurmamalı
            status, value = "crash", f"iş süreci sonlandırdı: {type(exc).__name__}"
            retire = True
        # Emeklilik sonuçla birlikte bildirilir ki ebeveyn kapanan işçiye yeni
        # iş göndermesin.
        retire = retire or _lingering_threads()
        data, retire = _encode(status, value, retire, max_bytes)
        del value
        conn.send_bytes(data)
        if retire:
            return


class _Worker:
    def __init__(self, memory_mb: int, max_bytes: int) -> None:
        ctx = _context()
        self._lock = threading.Lock()
        self._closed = False
        self.conn, child = ctx.Pipe()
        self.process = ctx.Process(
            target=_serve, args=(child, memory_mb, max_bytes), daemon=True
        )
        self.process.start()
        child.close()

    def alive(self) -> bool:
        with self._lock:
            return not self._closed and self.process.exitcode is None

    def terminate(self) -> None:
        """Yalnız süreci öldürür; bağlantıyı onu kullanan iş parçacığı kapatır."""
        with self._lock:
            if self._closed:
                return
            try:
                if self.process.exitcode is None:
                    self.process.kill()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        """İdempotent: süreci öldürür, bekler ve bağlantıyı bir kez kapatır."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self.process.exitcode is None:
                    self.process.kill()
                self.process.join(timeout=5)
            except (OSError, ValueError):
                pass
            self.conn.close()


class _Pool:
    """Bir havuz nesli. `shutdown` nesli kapatır; kapalı nesle işçi dönmez."""

    def __init__(self) -> None:
        self.size = _worker_count()
        self.memory_mb = _memory_mb()
        self.max_result_bytes = _max_result_bytes()
        self._cond = threading.Condition()
        self.closed = False
        self._idle: list[_Worker] = []
        self._busy: set[_Worker] = set()
        for _ in range(self.size):
            self._idle.append(self._spawn())

    def _spawn(self) -> _Worker:
        return _Worker(self.memory_mb, self.max_result_bytes)

    def acquire(self, deadline: float) -> _Worker:
        with self._cond:
            while True:
                if self.closed:
                    raise SandboxCrashed("değerlendirme havuzu kapatıldı")
                if self._idle:
                    worker = self._idle.pop()
                    self._busy.add(worker)
                    return worker
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SandboxTimeout("boş değerlendirme işçisi bulunamadı")
                self._cond.wait(remaining)

    def replace(self, worker: _Worker) -> _Worker:
        worker.close()
        if self.closed:
            raise SandboxCrashed("değerlendirme havuzu kapatıldı")
        try:
            fresh = self._spawn()
        except Exception as exc:  # noqa: BLE001
            raise SandboxCrashed(f"yeni değerlendirme işçisi açılamadı: {exc}") from exc
        with self._cond:
            if not self.closed:
                self._busy.discard(worker)
                self._busy.add(fresh)
                return fresh
        fresh.close()
        raise SandboxCrashed("değerlendirme havuzu kapatıldı")

    def release(self, worker: _Worker) -> None:
        with self._cond:
            self._busy.discard(worker)
            if not self.closed:
                # Ölü işçi de geri konur; sonraki `run` onu yeniler, havuz küçülmez.
                self._idle.append(worker)
                self._cond.notify()
                return
        worker.close()

    def close(self) -> None:
        with self._cond:
            self.closed = True
            idle, self._idle = self._idle, []
            busy = list(self._busy)
            self._cond.notify_all()
        for worker in idle:
            worker.close()
        for worker in busy:
            worker.terminate()


def _pool() -> _Pool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = _Pool()
        return _POOL


def run(fn: Callable[..., T], *args: Any, timeout: float, **kwargs: Any) -> T:
    """`fn(*args, **kwargs)` sonucunu döndürür; süre aşılırsa `SandboxTimeout`.

    `timeout`, havuz kurulumu ve boş işçi beklemesi dahil işin toplam süresidir.
    """
    if not timeout > 0:
        raise ValueError("timeout pozitif olmalı")
    if _mode() == "inline":
        return fn(*args, **kwargs)

    deadline = time.monotonic() + timeout
    pool = _pool()
    worker = pool.acquire(deadline)
    try:
        if not worker.alive():
            worker = pool.replace(worker)
        # İş önce tümüyle pickle'lanır: aktarılamayan bir iş işçiye hiç ulaşmaz
        # ve istisnası (PicklingError vb.) olduğu gibi çağırana döner.
        request = bytes(ForkingPickler.dumps((fn, args, kwargs)))
        if time.monotonic() >= deadline:
            raise SandboxTimeout(f"iş {timeout} saniyede başlatılamadı")
        try:
            worker.conn.send_bytes(request)
        except OSError:
            worker = pool.replace(worker)
            try:
                worker.conn.send_bytes(request)
            except OSError as exc:
                worker = pool.replace(worker)
                raise SandboxCrashed("iş değerlendirme sürecine gönderilemedi") from exc

        try:
            ready = worker.conn.poll(max(0.0, deadline - time.monotonic()))
        except (EOFError, OSError):
            ready = True
        if not ready:
            worker = pool.replace(worker)
            raise SandboxTimeout(f"iş {timeout} saniyede bitmedi")
        try:
            raw = worker.conn.recv_bytes(pool.max_result_bytes)
        except (EOFError, OSError) as exc:
            # Süreç kapandı ya da sonuç boyut sınırını aştı (akış artık kaymış).
            worker = pool.replace(worker)
            raise SandboxCrashed(
                "değerlendirme sonucu alınamadı: süreç kapandı ya da sonuç çok büyük"
            ) from exc
        try:
            status, value, retire = _load_reply(raw)
        except _RefusedType as exc:
            # Tür reddi ya bir hata ya da ele geçirilmiş işçi demek; ikisini
            # ayırt edemeyiz. Yenilemek bir fork'a mal olur, bu yüzden yenilenir.
            worker = pool.replace(worker)
            raise SandboxCrashed(f"sonuç türü aktarılamaz: {exc}") from None
        except Exception as exc:  # noqa: BLE001 — sonuç ebeveynde açılamadı
            worker = pool.replace(worker)
            raise SandboxCrashed(f"sonuç aktarılamadı: {type(exc).__name__}") from None
        if retire:
            try:
                worker = pool.replace(worker)
            except SandboxCrashed:
                # Sonuç zaten elimizde; yenileme başarısızsa ölü işçi havuza döner
                # (ya da kapalı nesilde kapatılır) ve sonraki `run` onu yeniler.
                pass
        if status == "ok":
            return value
        if status == "crash":
            raise SandboxCrashed(value)
        raise value
    finally:
        pool.release(worker)


def shutdown() -> None:
    """Geçerli havuz neslini kapatır (testler ve süreç çıkışı için).

    Boştaki işçiler hemen kapatılır; iş başındakiler öldürülür ve bağlantıları
    onları kullanan `run` çağrısı bitince kapanır. Sonraki `run` yeni nesil açar.
    """
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.close()


atexit.register(shutdown)
