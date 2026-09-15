"""Ağır ve güvenilmeyen SymPy işlerini ayrı süreçte, süre sınırıyla çalıştırır.

İş parçacığı zorla durdurulamaz; süresi dolan bir hesap sunucu sürecinde
sonsuza dek CPU yiyebilir. Bu yüzden çekirdek işler kalıcı işçi
süreçlerde koşar. Süre aşılırsa işçi öldürülür ve yerine yenisi açılır.
Bir iş, arkasında hâlâ çalışan yardımcı iş parçacığı bırakırsa işçi
sonucu gönderdikten sonra kendini kapatır (yenisi açılır).

İşçiler `forkserver` bağlamıyla açılır; sunucu `sympy` ve
`questioncrator.mathenv` modüllerini önceden yükler, böylece reçete
bekçileri her işçide daha ilk işten önce kuruludur. İşçi açılışında aynı
modüller yeniden içe aktarılır: önyükleme bir nedenle atlanmış olsa bile
bekçiler kurulmadan hiçbir iş çalışmaz.

Bellek sınırı (`RLIMIT_AS`) işçi başında, fork'tan sonra kurulur; forkserver
sürecini ve ebeveyni etkilemez. Sınır yalnız Linux'ta uygulanır: macOS
`RLIMIT_AS`i uygulamaz, orada bellek koruması yoktur. Üretim ortamı
Docker/Linux olduğu için bu kabul edilmiştir.
"""

from __future__ import annotations

import atexit
import importlib
import multiprocessing
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from multiprocessing.reduction import ForkingPickler
from typing import Any, TypeVar

T = TypeVar("T")

_PRELOAD = ["sympy", "questioncrator.mathenv"]

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


def _memory_mb() -> int:
    return int(os.environ.get("QC_SANDBOX_MEMORY_MB", "1024"))


def _context() -> Any:
    if sys.platform == "win32":
        return multiprocessing.get_context("spawn")
    ctx = multiprocessing.get_context("forkserver")
    ctx.set_forkserver_preload(_PRELOAD)
    return ctx


def _limit_memory(memory_mb: int) -> None:
    if not sys.platform.startswith("linux"):
        return
    import resource

    limit = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _encode(status: str, value: Any, retire: bool) -> bytes:
    try:
        return bytes(ForkingPickler.dumps((status, value, retire)))
    except Exception as exc:  # noqa: BLE001 — aktarılamayan her değer
        message = f"sonuç aktarılamadı: {type(exc).__name__}: {exc}"
        return bytes(ForkingPickler.dumps(("crash", message, retire)))


def _serve(conn: Any, memory_mb: int) -> None:
    # Sınır ortam değişkeninden değil argümandan gelir: forkserver'dan doğan
    # işçi, ebeveynin güncel ortamını değil forkserver'ın ortamını görür.
    _limit_memory(memory_mb)
    for name in _PRELOAD:
        importlib.import_module(name)
    while True:
        try:
            fn, args, kwargs = conn.recv()
        except EOFError:
            return
        except Exception as exc:  # noqa: BLE001 — iş işçide açılamadı
            conn.send_bytes(_encode("crash", f"iş aktarılamadı: {exc}", False))
            continue
        fatal = False
        try:
            status, value = "ok", fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — her hata ebeveyne taşınır
            status, value = "err", exc
        except BaseException as exc:  # noqa: BLE001 — SystemExit vb. ebeveyni durdurmamalı
            status, value = "crash", f"iş süreci sonlandırdı: {type(exc).__name__}"
            fatal = True
        # Kaçak yardımcı iş parçacığı kaldıysa işçi yenilenir; bunu sonuçla
        # birlikte bildiririz ki ebeveyn kapanan işçiye yeni iş göndermesin.
        retire = fatal or threading.active_count() > 1
        conn.send_bytes(_encode(status, value, retire))
        if retire:
            return


class _Worker:
    def __init__(self) -> None:
        ctx = _context()
        self.conn, child = ctx.Pipe()
        self.process = ctx.Process(target=_serve, args=(child, _memory_mb()), daemon=True)
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
            idle: queue.Queue[_Worker] = queue.Queue()
            for _ in range(_worker_count()):
                worker = _Worker()
                _ALL.append(worker)
                idle.put(worker)
            _IDLE = idle
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
    """`fn(*args, **kwargs)` sonucunu döndürür; süre aşılırsa `SandboxTimeout`.

    `timeout`, boş işçi beklemesi dahil işin toplam süresidir.
    """
    if _mode() == "inline":
        return fn(*args, **kwargs)

    idle = _pool()
    deadline = time.monotonic() + timeout
    try:
        worker = idle.get(timeout=timeout)
    except queue.Empty as exc:
        raise SandboxTimeout("boş değerlendirme işçisi bulunamadı") from exc

    try:
        if not worker.process.is_alive():
            worker = _replace(worker)
        # İş önce tümüyle pickle'lanır: aktarılamayan bir iş işçiye hiç ulaşmaz
        # ve istisnası (PicklingError vb.) olduğu gibi çağırana döner.
        request = bytes(ForkingPickler.dumps((fn, args, kwargs)))
        try:
            worker.conn.send_bytes(request)
        except OSError:
            worker = _replace(worker)
            worker.conn.send_bytes(request)

        if not worker.conn.poll(max(0.0, deadline - time.monotonic())):
            worker = _replace(worker)
            raise SandboxTimeout(f"iş {timeout} saniyede bitmedi")
        try:
            raw = worker.conn.recv_bytes()
        except (EOFError, OSError) as exc:
            worker = _replace(worker)
            raise SandboxCrashed("değerlendirme süreci beklenmedik biçimde kapandı") from exc
        try:
            status, value, retire = ForkingPickler.loads(raw)
        except Exception as exc:  # noqa: BLE001 — sonuç ebeveynde açılamadı
            # İşçinin kapanma bildirimi de okunamadı; güvenli yol yenilemek.
            worker = _replace(worker)
            raise SandboxCrashed(f"sonuç aktarılamadı: {exc}") from exc
        if retire:
            worker.process.join(timeout=5)
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
