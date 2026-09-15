"""Ağır ve güvenilmeyen SymPy işlerini ayrı süreçte, süre sınırıyla çalıştırır.

İş parçacığı zorla durdurulamaz; süresi dolan bir hesap sunucu sürecinde
sonsuza dek CPU yiyebilir. Bu yüzden çekirdek işler kalıcı işçi
süreçlerde koşar. Süre aşılırsa işçi öldürülür ve yerine yenisi açılır.

Güvenlik sınırı: Bu modül kod çalıştırmaya karşı tek başına bir sınır
DEĞİLDİR; o sınır reçete bekçileridir (`questioncrator.mathenv`). Bu taraf
CPU (süre sınırı + öldürme), bellek (Linux'ta `RLIMIT_AS`) ve aktarım
güvenliği sağlar.

Aktarım: Ebeveyn→işçi yönü pickle'dır (ebeveyn güvenilir taraftır); her istek
artan bir sıra numarası taşır. İşçi→ebeveyn yönünde pickle YOKTUR; işçi
yanıtı güvenilmeyen bayt sayılır ve `questioncrator.wire` tür etiketli JSON
kodeğiyle taşınır. Çerçeve 8 baytlık büyük uçlu uzunluk başlığı + gövdedir.
Ebeveyn uzunluğu okumadan önce `QC_SANDBOX_MAX_RESULT_MB` sınırıyla denetler
ve başlığı da gövdeyi de toplam süre içinde, seçici + `os.read` döngüsüyle
okur; kısmi çerçeve yazıp bekleyen işçi zaman aşımıyla öldürülür. Yanıtın
sıra numarası isteğinkiyle eşleşmezse (ör. işçi fazladan çerçeve yazdıysa)
yanıt reddedilir. İstek de aynı toplam süre içinde, bloklamasız ebeveyn
fd'sine seçici + `os.write` döngüsüyle yazılır (`send_bytes` çerçevesi);
okumayan işçi zaman aşımıyla öldürülür. İşçiden gelen `MemoryError` ve
`RecursionError` ebeveynde `SandboxCrashed` olur, işçi yenilenir.
Aktarılamayan sonuç türü (sympy nesneleri dahil) işçide
`SandboxCrashed("sonuç türü aktarılamaz: <modül.ad>")` olur; ebeveynin
reddettiği yanıt da `SandboxCrashed` olur. İkisinde de işçi yenilenir.

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
Docker/Linux olduğu için bu kabul edilmiştir. Süreç kipi Windows'u
desteklemez.

Ortam (havuz kurulurken bir kez okunur): `QC_SANDBOX` (`process` | `inline`),
`QC_SANDBOX_WORKERS` (2), `QC_SANDBOX_MEMORY_MB` (1024),
`QC_SANDBOX_MAX_RESULT_MB` (4).
"""

from __future__ import annotations

import atexit
import importlib
import itertools
import multiprocessing
import os
import selectors
import sys
import threading
import time
from collections.abc import Callable
from multiprocessing.reduction import ForkingPickler
from typing import Any, TypeVar

from questioncrator import models as _models  # noqa: F401 — kodek kaydı ebeveynde hazır olsun
from questioncrator import wire

T = TypeVar("T")

_PRELOAD = ["sympy", "questioncrator.mathenv"]
# İşçi sonucu gönderirken yardımcı iş parçacıklarının kapanmasını bekleme penceresi.
_THREAD_GRACE_SECONDS = 0.1
_HEADER_BYTES = 8
_READ_CHUNK = 1 << 20

_POOL_LOCK = threading.Lock()
_POOL: _Pool | None = None
# Yalnız işçi süreçte dolu: yanıt çerçevelerinin yazıldığı kanal ve geçerli
# isteğin sıra numarası.
_WORKER_FD: int | None = None
_WORKER_SEQ: int = -1


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
    return max(1, int(os.environ.get("QC_SANDBOX_MAX_RESULT_MB", "4"))) * 1024 * 1024


def _context() -> Any:
    ctx = multiprocessing.get_context("forkserver")
    ctx.set_forkserver_preload(_PRELOAD)
    return ctx


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


def _encode_reply(
    status: str, value: Any, retire: bool, seq: int, max_bytes: int
) -> tuple[bytes, bool]:
    """Yanıtı JSON çerçeve gövdesine çevirir; aktarılamayan sonuç işçiyi emekli eder."""
    try:
        if status == "ok":
            data = wire.dumps_ok(value, retire=retire, seq=seq)
        elif status == "err":
            data = wire.dumps_error(value, retire=retire, seq=seq)
        else:
            data = wire.dumps_crash(value, retire=retire, seq=seq)
    except wire.WireError as exc:
        return wire.dumps_crash(str(exc), retire=True, seq=seq), True
    except Exception as exc:  # noqa: BLE001 — kodlayıcıda beklenmeyen hata
        message = f"sonuç aktarılamadı: {type(exc).__name__}"
        return wire.dumps_crash(message, retire=True, seq=seq), True
    if len(data) > max_bytes:
        message = f"sonuç boyut sınırını aştı ({len(data)} > {max_bytes} bayt)"
        return wire.dumps_crash(message, retire=True, seq=seq), True
    return data, retire


def _write_frame(fd: int, body: bytes) -> None:
    view = memoryview(len(body).to_bytes(_HEADER_BYTES, "big") + body)
    while view:
        view = view[os.write(fd, view) :]


def _serve(conn: Any, memory_mb: int, max_bytes: int) -> None:
    global _WORKER_FD, _WORKER_SEQ
    # Ayarlar ortamdan değil argümandan gelir: forkserver'dan doğan işçi,
    # ebeveynin güncel ortamını değil forkserver'ın ortamını görür.
    _limit_memory(memory_mb)
    for name in _PRELOAD:
        importlib.import_module(name)
    _WORKER_FD = conn.fileno()
    while True:
        try:
            seq, fn, args, kwargs = conn.recv()  # güvenilir ebeveynin isteği
        except EOFError:
            return
        except Exception as exc:  # noqa: BLE001 — iş işçide açılamadı
            data, _ = _encode_reply("crash", f"iş aktarılamadı: {exc}", True, -1, max_bytes)
            _write_frame(_WORKER_FD, data)
            return
        _WORKER_SEQ = seq
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
        data, retire = _encode_reply(status, value, retire, seq, max_bytes)
        del value
        _write_frame(_WORKER_FD, data)
        if retire:
            return


# --- Ebeveyn: süreye bağlı çerçeve okuma ---------------------------------


class _ReadTimeout(Exception):
    pass


class _WriteTimeout(Exception):
    pass


class _FrameTooLarge(Exception):
    pass


def _send_request(fd: int, data: bytes, deadline: float) -> None:
    """İsteği `Connection.send_bytes` çerçevesiyle toplam süre içinde yazar.

    Çerçeve: 4 bayt işaretli büyük uçlu uzunluk (2 GiB üstünde -1 + 8 bayt);
    işçi `Connection.recv` ile okumaya devam eder. Ebeveyn fd'si bloklamasızdır;
    okumayan işçiye büyük istek süresiz bekletmez. Kısmen gönderilmiş istek
    kanalı bozar; çağıran işçiyi yeniler.
    """
    size = len(data)
    if size > 0x7FFFFFFF:
        header = (-1).to_bytes(4, "big", signed=True) + size.to_bytes(8, "big")
    else:
        header = size.to_bytes(4, "big", signed=True)
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_WRITE)
        for view in (memoryview(header), memoryview(data)):
            while view:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _WriteTimeout
                if not selector.select(remaining):
                    continue
                try:
                    view = view[os.write(fd, view) :]
                except BlockingIOError:
                    continue


def _read_frame(fd: int, max_bytes: int, deadline: float) -> bytes:
    """Başlık + gövdeyi toplam süre içinde okur; kısmi çerçevede de süresiz beklemez.

    `select.select` yerine `selectors` kullanılır: 1024'ten büyük fd
    numaralarında (`FD_SETSIZE`) da çalışır.
    """
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)

        def read_exact(size: int) -> bytes:
            buffer = bytearray()
            while len(buffer) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _ReadTimeout
                if not selector.select(remaining):
                    continue
                try:
                    chunk = os.read(fd, min(size - len(buffer), _READ_CHUNK))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise EOFError
                buffer += chunk
            return bytes(buffer)

        length = int.from_bytes(read_exact(_HEADER_BYTES), "big")
        if length > max_bytes:
            raise _FrameTooLarge(f"yanıt {length} bayt, sınır {max_bytes}")
        return read_exact(length)


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
        # Yalnız ebeveyn ucu: soket çiftinin iki ucu ayrı açık dosya
        # tanımıdır, işçinin ucu bloklayıcı kalır.
        os.set_blocking(self.conn.fileno(), False)

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
        self._seq = itertools.count(1)
        self.closed = False
        self._idle: list[_Worker] = []
        self._busy: set[_Worker] = set()
        for _ in range(self.size):
            self._idle.append(self._spawn())

    def _spawn(self) -> _Worker:
        return _Worker(self.memory_mb, self.max_result_bytes)

    def next_seq(self) -> int:
        with self._cond:
            return next(self._seq)

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

    `timeout`, havuz kurulumu, boş işçi beklemesi ve yanıt okuma dahil işin
    toplam süresidir.
    """
    if not timeout > 0:
        raise ValueError("timeout pozitif olmalı")
    if _mode() == "inline":
        return fn(*args, **kwargs)
    if sys.platform == "win32":
        raise NotImplementedError("süreç kipi Windows'ta desteklenmiyor; QC_SANDBOX=inline")

    deadline = time.monotonic() + timeout
    pool = _pool()
    worker = pool.acquire(deadline)
    try:
        if not worker.alive():
            worker = pool.replace(worker)
        seq = pool.next_seq()
        # İş önce tümüyle pickle'lanır: aktarılamayan bir iş işçiye hiç ulaşmaz
        # ve istisnası (PicklingError vb.) olduğu gibi çağırana döner.
        request = bytes(ForkingPickler.dumps((seq, fn, args, kwargs)))
        if time.monotonic() >= deadline:
            raise SandboxTimeout(f"iş {timeout} saniyede başlatılamadı")
        try:
            try:
                _send_request(worker.conn.fileno(), request, deadline)
            except OSError:
                worker = pool.replace(worker)
                try:
                    _send_request(worker.conn.fileno(), request, deadline)
                except OSError as exc:
                    worker = pool.replace(worker)
                    raise SandboxCrashed("iş değerlendirme sürecine gönderilemedi") from exc
        except _WriteTimeout:
            worker = pool.replace(worker)
            raise SandboxTimeout(f"iş {timeout} saniyede gönderilemedi") from None

        try:
            raw = _read_frame(worker.conn.fileno(), pool.max_result_bytes, deadline)
        except _ReadTimeout:
            worker = pool.replace(worker)
            raise SandboxTimeout(f"iş {timeout} saniyede bitmedi") from None
        except _FrameTooLarge as exc:
            worker = pool.replace(worker)
            raise SandboxCrashed(f"sonuç boyut sınırını aştı: {exc}") from None
        except (EOFError, OSError) as exc:
            worker = pool.replace(worker)
            raise SandboxCrashed("değerlendirme süreci beklenmedik biçimde kapandı") from exc
        try:
            status, value, retire = wire.loads_reply(raw, seq=seq)
        except wire.WireError as exc:
            # Reddedilen yanıt ya bir hata ya da ele geçirilmiş işçi demek;
            # ikisini ayırt edemeyiz. Yenilemek bir fork'a mal olur.
            worker = pool.replace(worker)
            raise SandboxCrashed(f"işçi yanıtı reddedildi: {exc}") from None
        # İşçinin bellek/özyineleme hatası ebeveynin kendi hatasıyla karışmasın.
        limit_hit = status == "err" and isinstance(value, (MemoryError, RecursionError))
        if retire or limit_hit:
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
        if limit_hit:
            raise SandboxCrashed(
                f"değerlendirme bellek/özyineleme sınırına takıldı: {value}"
            ) from None
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
