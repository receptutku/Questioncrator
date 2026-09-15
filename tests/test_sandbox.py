from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time

import pytest

from questioncrator import sandbox
from questioncrator.mathenv import UnsafeExpression, parse, parse_with_timeout
from questioncrator.models import Parameter, Template

linux_gerekir = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="RLIMIT_AS yalnız Linux'ta uygulanır"
)

# Linux bellek testlerinde 256 MB yerine 512 MB: RLIMIT_AS sanal adres alanını
# sınırlar; önyüklenmiş sympy eşlemeleri, iş parçacığı yığınları (8 MB) ve glibc
# iş parçacığı arenaları (64 MB'a kadar ayrılmış alan) sağlıklı işlerde bile
# 256 MB'a yaklaşır ve `can't start new thread` ile yanlış pozitif üretebilir.
LINUX_TEST_BELLEK_MB = "512"


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


def test_pozitif_olmayan_sure_reddedilir(surec_kipi):
    with pytest.raises(ValueError):
        sandbox.run(pow, 2, 2, timeout=0)
    with pytest.raises(ValueError):
        sandbox.run(pow, 2, 2, timeout=-1)


def test_havuz_kurulumu_sureye_dahildir(surec_kipi):
    with pytest.raises(sandbox.SandboxTimeout):
        sandbox.run(pow, 2, 2, timeout=1e-6)
    assert sandbox.run(pow, 2, 2, timeout=20) == 4


def test_istisna_aynen_yukselir(surec_kipi):
    with pytest.raises(ValueError):
        sandbox.run(int, "sayi-degil", timeout=20)


def test_paket_istisnasi_aynen_yukselir(surec_kipi):
    with pytest.raises(UnsafeExpression) as bilgi:
        sandbox.run(parse, 'sympify("x")', timeout=30)
    assert type(bilgi.value) is UnsafeExpression


class _AktarilamayanHata(Exception):
    def __init__(self) -> None:
        super().__init__("aktarılamaz")
        self.kilit = threading.Lock()


def aktarilamayan_hata_firlat() -> None:
    raise _AktarilamayanHata()


def aktarilamayan_sonuc_dondur() -> object:
    return threading.Lock()


class _YabanciHata(Exception):
    pass


def yabanci_hata_firlat() -> None:
    raise _YabanciHata("paket dışı istisna")


def test_aktarilamayan_istisna_crashed_olur(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(aktarilamayan_hata_firlat, timeout=20)
    assert sandbox.run(pow, 2, 5, timeout=20) == 32


def test_aktarilamayan_sonuc_crashed_olur(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(aktarilamayan_sonuc_dondur, timeout=20)
    assert sandbox.run(pow, 2, 6, timeout=20) == 64


def test_paket_disi_istisna_turu_aktarilmaz(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed, match="paket dışı istisna"):
        sandbox.run(yabanci_hata_firlat, timeout=20)


def dur_firlat() -> None:
    raise StopIteration("dur")


def test_stopiteration_yeniden_yukseltilmez(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(dur_firlat, timeout=20)


def test_isci_cokerse_hata_verir_ve_toparlanir(surec_kipi):
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(os._exit, 3, timeout=20)
    assert sandbox.run(pow, 2, 3, timeout=20) == 8


def kacak_is_parcacigi_birakir() -> int:
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


def sureli_ayristir_pid(recete: str) -> int:
    parse_with_timeout(recete, 5.0)
    return os.getpid()


def test_sureli_ayristirma_isciyi_emekli_etmez(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    pidler = {sandbox.run(sureli_ayristir_pid, "diff(3*x**2, x)", timeout=30) for _ in range(5)}
    assert len(pidler) == 1


def test_inline_kip_ayni_surecte_calisir(monkeypatch):
    monkeypatch.setenv("QC_SANDBOX", "inline")
    assert sandbox.run(os.getpid, timeout=1) == os.getpid()


# --- Aktarım güvenliği ---------------------------------------------------


def ayristirma_sonucu_dondur(recete: str) -> object:
    return parse(recete)


def test_sympy_sonucu_ebeveynde_acilmaz(surec_kipi):
    sandbox.run(pow, 1, 1, timeout=30)  # işçiyi ısıt
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxCrashed, match="sonuç türü aktarılamaz: sympy"):
        sandbox.run(ayristirma_sonucu_dondur, "Pow(10, 10**8, evaluate=False)", timeout=30)
    assert time.monotonic() - baslangic < 2
    with pytest.raises(sandbox.SandboxCrashed, match="sonuç türü aktarılamaz: sympy"):
        sandbox.run(ayristirma_sonucu_dondur, "diff(3*x**2, x)", timeout=30)
    assert sandbox.run(pow, 2, 4, timeout=20) == 16


def kume_dondur() -> object:
    return {1, 2}


def test_desteklenmeyen_sonuc_turu_isciyi_yeniler(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    with pytest.raises(sandbox.SandboxCrashed, match="sonuç türü aktarılamaz: builtins.set"):
        sandbox.run(kume_dondur, timeout=30)
    assert sandbox.run(os.getpid, timeout=30) != eski


def model_ve_kaplar_dondur() -> object:
    sablon = Template(
        id="t_1",
        source_id="s_1",
        skeleton="{a} + {b}",
        recipe="a + b",
        parameters=(Parameter("a", 1, 9), Parameter("b", 2, 8, exclude=(0, 5))),
        seed_bindings={"a": 3, "b": 4},
    )
    kaplar = {
        "liste": [1, 2.5, (3, None), True],
        "ic": {"derin": [[{"k": (1,)}]]},
        "buyuk": 10**40,
        "metin": 'tırnak " ve [ { \\',
    }
    return (sablon, kaplar)


def test_model_ve_ic_ice_ilkel_kaplar_doner(surec_kipi):
    assert sandbox.run(model_ve_kaplar_dondur, timeout=30) == model_ve_kaplar_dondur()


# --- Elle yazılmış işçi davranışları (çerçeve düzeyi) ---------------------


def _cerceve(govde: bytes) -> bytes:
    return len(govde).to_bytes(8, "big") + govde


def ham_yaz_ve_uyu(veri: bytes) -> None:
    """İşçi kanalına elle bayt yazar ve bekler (kötü niyetli işçi taklidi)."""
    kalan = memoryview(veri)
    while kalan:
        kalan = kalan[os.write(sandbox._WORKER_FD, kalan) :]
    time.sleep(30)


def test_kismi_cerceve_suresiz_bloklamaz(surec_kipi):
    sandbox.run(pow, 1, 1, timeout=30)
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxTimeout):
        sandbox.run(ham_yaz_ve_uyu, _cerceve(b'{"status":"ok"')[:9], timeout=1)
    assert time.monotonic() - baslangic < 3
    assert sandbox.run(pow, 2, 2, timeout=30) == 4


def test_kismi_baslik_suresiz_bloklamaz(surec_kipi):
    sandbox.run(pow, 1, 1, timeout=30)
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxTimeout):
        sandbox.run(ham_yaz_ve_uyu, b"\x00\x00\x00", timeout=1)
    assert time.monotonic() - baslangic < 3


def test_baslikta_buyuk_uzunluk_okunmadan_reddedilir(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(ham_yaz_ve_uyu, (2**40).to_bytes(8, "big"), timeout=10)
    assert time.monotonic() - baslangic < 3
    assert sandbox.run(os.getpid, timeout=30) != eski


@pytest.mark.parametrize(
    "govde",
    [
        b'{"status":"ok","status":"ok","value":1,"retire":false}',
        b'{"status":"ok","value":' + b"9" * 5000 + b',"retire":false}',
        b'{"status":"ok","value":' + b"[" * 100 + b"]" * 100 + b',"retire":false}',
        b'{"status":"ok","value":{"$zz":1},"retire":false}',
        b'{"status":"ok","value":{"$m":["Parameter",{"$d":{"__init__":1}}]},"retire":false}',
        b"\x80\x04N.",
    ],
)
def test_kotu_yanit_crashed_olur_ve_isci_yenilenir(surec_kipi, monkeypatch, govde):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    baslangic = time.monotonic()
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(ham_yaz_ve_uyu, _cerceve(govde), timeout=10)
    assert time.monotonic() - baslangic < 3
    assert sandbox.run(os.getpid, timeout=30) != eski
    assert Parameter("a", 1, 9).high == 9


def test_ebeveynde_pickle_acma_yok():
    import inspect

    from questioncrator import wire

    for modul in (sandbox, wire):
        kaynak = inspect.getsource(modul)
        for yasak in ("pickle.loads", "Unpickler", "ForkingPickler.loads", "recv_bytes"):
            assert yasak not in kaynak, (modul.__name__, yasak)
    # İşçi→ebeveyn yönü JSON; `conn.recv()` yalnız işçide (güvenilir ebeveynin
    # isteğini açmak için) kullanılır.
    assert inspect.getsource(sandbox).count(".recv(") == 1
    assert ".recv(" in inspect.getsource(sandbox._serve)


def buyuk_metin_dondur(boyut: int) -> str:
    return "x" * boyut


def test_sonuc_boyut_siniri_iscide_uygulanir(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    monkeypatch.setenv("QC_SANDBOX_MAX_RESULT_MB", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(buyuk_metin_dondur, 2 * 1024 * 1024, timeout=30)
    assert sandbox.run(os.getpid, timeout=30) != eski
    assert sandbox.run(buyuk_metin_dondur, 10, timeout=30) == "x" * 10


def test_sonuc_boyut_siniri_ebeveynde_de_uygulanir(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    # İşçi 16 MB sınırıyla açıldı; ebeveyn tarafını tek başına daraltıyoruz.
    sandbox._pool().max_result_bytes = 64 * 1024
    with pytest.raises(sandbox.SandboxCrashed):
        sandbox.run(buyuk_metin_dondur, 256 * 1024, timeout=30)
    assert sandbox.run(os.getpid, timeout=30) != eski


# --- Kapatma yarışı ------------------------------------------------------


def test_calisirken_kapatma_yarissiz(surec_kipi, monkeypatch):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "2")
    sandbox.run(pow, 1, 1, timeout=30)
    hatalar: list[BaseException] = []

    def cagir() -> None:
        try:
            sandbox.run(time.sleep, 3, timeout=20)
        except (sandbox.SandboxCrashed, sandbox.SandboxTimeout):
            pass
        except BaseException as exc:  # noqa: BLE001
            hatalar.append(exc)

    iplikler = [threading.Thread(target=cagir) for _ in range(4)]
    for iplik in iplikler:
        iplik.start()
    time.sleep(0.5)
    sandbox.shutdown()  # istisnasız tamamlanmalı
    for iplik in iplikler:
        iplik.join(timeout=30)
    assert not any(iplik.is_alive() for iplik in iplikler)
    assert hatalar == []
    # Eski nesilden hiçbir işçi ayakta kalmadı ya da yeni havuza sızmadı.
    assert multiprocessing.active_children() == []
    assert sandbox.run(pow, 2, 2, timeout=30) == 4
    assert len(multiprocessing.active_children()) == 2


# --- Reçete bekçileri ve CPU ---------------------------------------------


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


# --- Bellek (yalnız Linux) -----------------------------------------------


def bellek_kaldiraci_dener(recete: str) -> str:
    """Başarıda metin döner; hata olduğu gibi yükselir.

    Başarı sympy nesnesi döndürmez: aksi halde aktarım reddi (`SandboxCrashed`)
    bellek hatasıyla karışırdı.
    """
    parse(recete)
    return "ISTISNA_YOK"


def isci_bellek_siniri() -> tuple[int, int]:
    import resource

    return resource.getrlimit(resource.RLIMIT_AS)


@linux_gerekir
@pytest.mark.parametrize("recete", ["Matrix([[1]]).rows << 8*10**9", "zeros(6000)"])
def test_bellek_kaldiraci_iscide_sinirlanir(surec_kipi, monkeypatch, recete):
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    monkeypatch.setenv("QC_SANDBOX_MEMORY_MB", LINUX_TEST_BELLEK_MB)
    eski = sandbox.run(os.getpid, timeout=30)
    # MemoryError ham gelebilir ya da mathenv onu UnsafeExpression'a sarar; ikinci
    # durumda MemoryError kökenini işçinin yenilenmesi (pid değişimi) kanıtlar:
    # sandbox yalnız MemoryError zinciri taşıyan hatada işçiyi emekli eder.
    with pytest.raises((MemoryError, UnsafeExpression, sandbox.SandboxCrashed)):
        sandbox.run(bellek_kaldiraci_dener, recete, timeout=60)
    assert sandbox.run(os.getpid, timeout=30) != eski
    assert sandbox.run(guvensiz_recete_dener, "diff(3*x**2, x)", timeout=30) == "ISTISNA_YOK"


@linux_gerekir
def test_bellek_siniri_iscide_ebeveynde_degil(surec_kipi, monkeypatch):
    import resource

    monkeypatch.setenv("QC_SANDBOX_MEMORY_MB", LINUX_TEST_BELLEK_MB)
    limit = int(LINUX_TEST_BELLEK_MB) * 1024 * 1024
    assert sandbox.run(isci_bellek_siniri, timeout=30) == (limit, limit)
    assert resource.getrlimit(resource.RLIMIT_AS)[0] != limit
    # Önyükleme sınırdan etkilenmedi: bekçiler ve sympy işçide hazır.
    assert sandbox.run(isci_bekci_durumu, timeout=30) == (True, True, True)


def bellek_hatasi_zinciri_firlat() -> None:
    try:
        raise MemoryError
    except MemoryError as exc:
        raise UnsafeExpression("sarılmış") from exc


def test_bellek_hatasi_zinciri_isciyi_yeniler(surec_kipi, monkeypatch):
    # Platformdan bağımsız: MemoryError kökenli hata işçiyi emekli eder.
    monkeypatch.setenv("QC_SANDBOX_WORKERS", "1")
    eski = sandbox.run(os.getpid, timeout=30)
    with pytest.raises(UnsafeExpression):
        sandbox.run(bellek_hatasi_zinciri_firlat, timeout=30)
    assert sandbox.run(os.getpid, timeout=30) != eski
