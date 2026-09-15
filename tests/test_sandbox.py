from __future__ import annotations

import os
import sys
import time

import pytest

from questioncrator import sandbox

linux_gerekir = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="RLIMIT_AS yalnız Linux'ta uygulanır"
)


@pytest.fixture
def surec_kipi(monkeypatch):
    monkeypatch.setenv("QC_SANDBOX", "process")
    sandbox.shutdown()
    yield
    sandbox.shutdown()


def test_sonuc_surecten_doner(surec_kipi):
    assert sandbox.run(pow, 2, 10, timeout=20) == 1024


def test_is_ayri_surecte_calisir(surec_kipi):
    assert sandbox.run(os.getpid, timeout=20) != os.getpid()


def test_isci_isler_arasinda_yeniden_kullanilir(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    ilk = sandbox.run(os.getpid, timeout=20)
    assert sandbox.run(os.getpid, timeout=20) == ilk


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


class _AktarilamayanHata(Exception):
    def __init__(self) -> None:
        super().__init__("aktarılamaz")
        self.kilit = __import__("threading").Lock()


def aktarilamayan_hata_firlat() -> None:
    raise _AktarilamayanHata()


def aktarilamayan_sonuc_dondur() -> object:
    import threading

    return threading.Lock()


def test_aktarilamayan_istisna_crashed_olur(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(aktarilamayan_hata_firlat, timeout=20)
    assert sandbox.run(pow, 2, 5, timeout=20) == 32


def test_aktarilamayan_sonuc_crashed_olur(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(aktarilamayan_sonuc_dondur, timeout=20)
    assert sandbox.run(pow, 2, 6, timeout=20) == 64


def test_isci_cokerse_hata_verir_ve_toparlanir(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(os._exit, 3, timeout=20)
    assert sandbox.run(pow, 2, 3, timeout=20) == 8


def kacak_is_parcacigi_birakir() -> int:
    import threading

    threading.Thread(target=time.sleep, args=(30,), daemon=True).start()
    return os.getpid()


def test_kacak_is_parcacigi_birakan_isci_yenilenir(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(kacak_is_parcacigi_birakir, timeout=20)
    assert eski != os.getpid()
    # Sonuç doğru döndü; bir sonraki iş yeni işçide, hatasız koşar.
    yeni = sandbox.run(os.getpid, timeout=20)
    assert yeni != eski
    assert sandbox.run(os.getpid, timeout=20) == yeni


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
    assert (
        sandbox.run(guvensiz_recete_dener, "nsolve(sin(x)-1, x, 1)", timeout=30)
        == "UnsafeExpression"
    )
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"


def isci_bekci_durumu() -> tuple[bool, bool, bool]:
    """İşçi süreçte, hiçbir şey içe aktarmadan bekçilerin kurulu olup olmadığını okur."""
    sympy = sys.modules.get("sympy")
    if sympy is None:
        return (False, False, False)
    from sympy.parsing import sympy_parser

    return (
        "questioncrator.mathenv" in sys.modules,
        getattr(sympy.lambdify, "_qc_guard", False),
        getattr(sympy_parser.parse_expr, "_qc_guard", False),
    )


def test_isci_acilista_bekciler_kurulu(surec_kipi):
    # İş gelmeden önce (önyükleme ya da işçi açılışı) bekçiler kurulmuş olmalı.
    assert sandbox.run(isci_bekci_durumu, timeout=30) == (True, True, True)


@pytest.mark.parametrize("recete", ["Integer(10)**10**8", "factorial(10**7)"])
def test_cpu_kaldiraci_zaman_asimiyla_durdurulur(surec_kipi, recete):
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxTimeout):
        sandbox.run(guvensiz_recete_dener, recete, timeout=2)
    assert time.monotonic() - baslangic < 6
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"


def bellek_kaldiraci_dener(recete: str) -> str:
    """İşçide ham `MemoryError`ı görünür kılar (mathenv onu `UnsafeExpression`e sarar)."""
    from questioncrator.mathenv import parse

    try:
        parse(recete)
    except MemoryError:
        return "MemoryError"
    except Exception as exc:  # noqa: BLE001
        cause = exc.__cause__
        if isinstance(cause, MemoryError) or "bellek" in str(exc):
            return "MemoryError"
        return type(exc).__name__
    return "ISTISNA_YOK"


def isci_bellek_siniri() -> tuple[int, int]:
    import resource

    return resource.getrlimit(resource.RLIMIT_AS)


@linux_gerekir
@pytest.mark.parametrize("recete", ["Matrix([[1]]).rows << 8*10**9", "zeros(6000)"])
def test_bellek_kaldiraci_iscide_sinirlanir(surec_kipi, monkeypatch, recete):
    monkeypatch.setenv("QC_SANDBOX_MEMORY_MB", "256")
    ebeveyn_pid = os.getpid()
    try:
        sonuc = sandbox.run(bellek_kaldiraci_dener, recete, timeout=60)
    except sandbox.SandboxCrashed:
        sonuc = "MemoryError"
    assert sonuc == "MemoryError"
    assert os.getpid() == ebeveyn_pid
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"


@linux_gerekir
def test_bellek_siniri_iscide_ebeveynde_degil(surec_kipi, monkeypatch):
    import resource

    monkeypatch.setenv("QC_SANDBOX_MEMORY_MB", "256")
    limit = 256 * 1024 * 1024
    assert sandbox.run(isci_bellek_siniri, timeout=30) == (limit, limit)
    assert resource.getrlimit(resource.RLIMIT_AS)[0] != limit
    # Önyükleme sınırdan etkilenmedi: bekçiler ve sympy işçide hazır.
    assert sandbox.run(isci_bekci_durumu, timeout=30) == (True, True, True)
