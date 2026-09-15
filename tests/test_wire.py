from __future__ import annotations

import dataclasses
import json
import math
import sys
import typing

import pytest
import sympy

from questioncrator import models, wire
from questioncrator.mathenv import EvaluationTimeout, UnsafeExpression
from questioncrator.models import Parameter, Review, Template
from questioncrator.templating.extract import NoParametersFound

SIRA = 7


def _zarf(**alanlar: object) -> bytes:
    belge = {"status": "ok", "retire": False, "seq": SIRA, **alanlar}
    return json.dumps(belge).encode()


def _ok(value: object) -> bytes:
    return _zarf(value=value)


def _hata_zarfi(exc: str, message: str) -> bytes:
    belge = {"status": "err", "exc": exc, "message": message, "retire": False, "seq": SIRA}
    return json.dumps(belge).encode()


def _coz(ham: bytes, seq: int = SIRA):
    return wire.loads_reply(ham, seq=seq)


def _sablon(**degis: object) -> Template:
    alanlar: dict[str, object] = dict(
        id="t_1",
        source_id="s_1",
        skeleton="{a} + {b}",
        recipe="a + b",
        parameters=(Parameter("a", 1, 9), Parameter("b", 2, 8, exclude=(0, 5))),
        constraints=("a != b",),
        seed_bindings={"a": 3, "b": 4},
        seed_answer_ops=2,
    )
    alanlar.update(degis)
    return Template(**alanlar)  # type: ignore[arg-type]


def _sablon_json(**degis: object) -> dict[str, object]:
    """`_sablon()`un tel biçimi; alanları elle bozmak için."""
    tel = json.loads(wire.dumps_ok(_sablon(), retire=False, seq=SIRA))["value"]
    tel["$m"][1]["$d"].update(degis)
    return tel


# --- Gidiş-dönüş ---------------------------------------------------------


@pytest.mark.parametrize(
    "deger",
    [
        None,
        True,
        False,
        0,
        -(10**40),
        2.5,
        "düz metin \" [ { \\ } ] , ğüşıöç",
        [1, [2, [3]]],
        (1, (2, None), []),
        {"a": [1, (2, 3)], "b": {"c": {"d": ()}}},
        (),
        {},
    ],
)
def test_ilkel_ve_ic_ice_kaplar_gidis_donus(deger):
    status, sonuc, retire = _coz(wire.dumps_ok(deger, retire=False, seq=SIRA))
    assert (status, retire) == ("ok", False)
    assert sonuc == deger
    assert type(sonuc) is type(deger)


def test_tuple_ve_liste_ayrimi_korunur():
    _, sonuc, _ = _coz(wire.dumps_ok([(1, [2]), [(3,)]], retire=False, seq=SIRA))
    assert isinstance(sonuc[0], tuple) and isinstance(sonuc[0][1], list)


def test_models_dataclasslari_gidis_donus():
    deger = {"sablon": _sablon(), "inceleme": Review("q_1", True, 4, 7, "2026-09-15")}
    _, sonuc, _ = _coz(wire.dumps_ok(deger, retire=True, seq=SIRA))
    assert sonuc == deger
    assert type(sonuc["sablon"].parameters[0]) is Parameter


def _models_dataclasslari() -> list[type]:
    return [
        nesne
        for nesne in vars(models).values()
        if isinstance(nesne, type)
        and dataclasses.is_dataclass(nesne)
        and nesne.__module__ == models.__name__
    ]


def test_kayit_models_dataclasslarinin_hepsini_kapsar():
    beklenen = {cls.__name__ for cls in _models_dataclasslari()}
    assert beklenen and set(wire.model_names()) == beklenen


# --- Sıra numarası -------------------------------------------------------


def test_sira_numarasi_uyusmazsa_reddedilir():
    ham = wire.dumps_ok(1, retire=False, seq=SIRA)
    assert _coz(ham, seq=SIRA)[1] == 1
    with pytest.raises(wire.WireError, match="sıra"):
        _coz(ham, seq=SIRA + 1)


@pytest.mark.parametrize("seq", [None, "7", True, 7.0])
def test_sira_numarasi_tipi_denetlenir(seq):
    with pytest.raises(wire.WireError):
        _coz(_zarf(value=1, seq=seq))


def test_sira_numarasi_eksikse_reddedilir():
    with pytest.raises(wire.WireError):
        _coz(json.dumps({"status": "ok", "value": 1, "retire": False}).encode())


# --- İstisnalar ----------------------------------------------------------


@pytest.mark.parametrize(
    "istisna",
    [
        UnsafeExpression("güvensiz"),
        EvaluationTimeout("süre"),
        NoParametersFound("yok"),
        ValueError("değer"),
        TypeError("tür"),
        ZeroDivisionError("sıfır"),
        ArithmeticError("aritmetik"),
        OverflowError("taşma"),
        NotImplementedError("yok"),
        KeyError("anahtar"),
        IndexError("sıra"),
        RecursionError("özyineleme"),
        MemoryError("bellek"),
        RuntimeError("çalışma"),
        SyntaxError("sözdizimi"),
        AttributeError("nitelik"),
    ],
)
def test_kayitli_istisnalar_turuyle_doner(istisna):
    status, sonuc, retire = _coz(wire.dumps_error(istisna, retire=False, seq=SIRA))
    assert status == "err"
    assert type(sonuc) is type(istisna)
    assert str(sonuc) == str(istisna)


@pytest.fixture
def gecici_kayit(monkeypatch):
    monkeypatch.setattr(wire, "_EXCEPTIONS", dict(wire._EXCEPTIONS))


def test_istisna_kaydina_alt_sinif_eklenebilir(gecici_kayit):
    class OzelHata(ValueError):
        pass

    ham = wire.dumps_error(OzelHata("özel"), retire=False, seq=SIRA)
    assert _coz(ham)[0] == "crash"
    wire.register_exception(OzelHata)
    status, sonuc, _ = _coz(ham)
    assert status == "err" and type(sonuc) is OzelHata and str(sonuc) == "özel"


def test_mesajdan_kurulamayan_istisna_crash_olur(gecici_kayit):
    class IkiArguman(Exception):
        def __init__(self, a, b):
            super().__init__(a, b)

    wire.register_exception(IkiArguman)
    assert _coz(wire.dumps_error(IkiArguman("x", "y"), retire=False, seq=SIRA))[0] == "crash"


@pytest.mark.parametrize("istisna", [StopIteration("dur"), LookupError("kayıtsız"), OSError("os")])
def test_kayitsiz_istisna_crash_olur(istisna):
    status, mesaj, _ = _coz(wire.dumps_error(istisna, retire=False, seq=SIRA))
    assert status == "crash" and isinstance(mesaj, str)


def test_stopiteration_kaydedilemez():
    with pytest.raises(TypeError):
        wire.register_exception(StopIteration)


def test_crash_zarfi():
    assert _coz(wire.dumps_crash("çöktü", retire=True, seq=SIRA)) == ("crash", "çöktü", True)


def test_istisna_mesaji_iscide_kirpilir():
    belge = json.loads(wire.dumps_error(ValueError("x" * 10_000), retire=False, seq=SIRA))
    assert len(belge["message"]) == wire.MAX_MESSAGE
    belge = json.loads(wire.dumps_crash("y" * 10_000, retire=False, seq=SIRA))
    assert len(belge["message"]) == wire.MAX_MESSAGE


def test_istisna_mesaji_ebeveynde_kirpilir():
    uzun = "z" * 10_000
    _, hata, _ = _coz(_hata_zarfi("builtins.ValueError", uzun))
    assert len(str(hata)) == wire.MAX_MESSAGE
    ham = json.dumps(
        {"status": "crash", "message": uzun, "retire": False, "seq": SIRA}
    ).encode()
    assert len(_coz(ham)[1]) == wire.MAX_MESSAGE


# --- İşçi tarafı kodlama retleri ----------------------------------------


@pytest.mark.parametrize(
    "deger",
    [
        {1, 2},
        frozenset({1}),
        b"bayt",
        bytearray(b"x"),
        complex(1, 2),
        sympy.Integer(3),
        sympy.Symbol("x"),
        {1: "int anahtar"},
        {("t",): 1},
        float("nan"),
        float("inf"),
        -math.inf,
        object(),
        type("Str", (str,), {})("alt sınıf"),
        [1, {2}],
    ],
)
def test_desteklenmeyen_deger_kodlanamaz(deger):
    with pytest.raises(wire.WireError, match="sonuç türü aktarılamaz"):
        wire.dumps_ok(deger, retire=False, seq=SIRA)


def test_sympy_red_mesaji_modul_adini_tasir():
    with pytest.raises(wire.WireError, match=r"sonuç türü aktarılamaz: sympy\."):
        wire.dumps_ok(sympy.Integer(3), retire=False, seq=SIRA)


def test_kodlama_derinlik_ve_oge_siniri():
    derin: object = 1
    for _ in range(wire.MAX_DEPTH + 1):
        derin = [derin]
    with pytest.raises(wire.WireError):
        wire.dumps_ok(derin, retire=False, seq=SIRA)
    with pytest.raises(wire.WireError):
        wire.dumps_ok([0] * (wire.MAX_ITEMS + 1), retire=False, seq=SIRA)


def test_kodlama_dev_int_reddedilir():
    with pytest.raises(wire.WireError):
        wire.dumps_ok(10**5000, retire=False, seq=SIRA)


# --- Ebeveyn tarafı çözme retleri ---------------------------------------


@pytest.fixture
def hane_siniri_kapali():
    eski = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    yield
    sys.set_int_max_str_digits(eski)


def test_dev_int_metni_ortam_ayarindan_bagimsiz_reddedilir(hane_siniri_kapali):
    for govde in (b"9" * 4301, b"-" + b"9" * 4301, b"[" + b"1" * 5000 + b"]"):
        ham = b'{"status":"ok","retire":false,"seq":7,"value":' + govde + b"}"
        with pytest.raises(wire.WireError):
            _coz(ham)
    sinirda = b'{"status":"ok","retire":false,"seq":7,"value":-' + b"9" * 4300 + b"}"
    assert _coz(sinirda)[1] == -int("9" * 4300)


def test_yinelenen_anahtar_reddedilir():
    with pytest.raises(wire.WireError):
        _coz(b'{"status":"ok","status":"ok","value":1,"retire":false,"seq":7}')
    with pytest.raises(wire.WireError):
        _coz(b'{"status":"ok","value":{"$d":{"a":1,"a":2}},"retire":false,"seq":7}')


def test_derinlik_siniri_asimi():
    ic = "[" * (wire.MAX_DEPTH + 1) + "]" * (wire.MAX_DEPTH + 1)
    with pytest.raises(wire.WireError):
        _coz(b'{"status":"ok","retire":false,"seq":7,"value":' + ic.encode() + b"}")


def test_derinlik_sinirina_kadar_kabul_edilir():
    deger: object = 1
    for _ in range(wire.MAX_DEPTH - 2):
        deger = [deger]
    assert _coz(wire.dumps_ok(deger, retire=False, seq=SIRA))[1] == deger


def test_oge_siniri_asimi():
    govde = "[" + ",".join(["0"] * (wire.MAX_ITEMS + 1)) + "]"
    with pytest.raises(wire.WireError):
        _coz(b'{"status":"ok","retire":false,"seq":7,"value":' + govde.encode() + b"}")


def test_int_anahtar_temsil_edilemez():
    # JSON'da nesne anahtarları hep metindir; `$d` yalnız metin anahtar taşır.
    # Çakışan int anahtarlı dev sözlük/küme bu yüzden ifade edilemez.
    with pytest.raises(wire.WireError):
        wire.dumps_ok({2**61 - 1: 1, 0: 2}, retire=False, seq=SIRA)
    assert _coz(_ok({"$d": {"1": 1}}))[1] == {"1": 1}


@pytest.mark.parametrize(
    "deger",
    [
        {"$set": [1, 2]},
        {"$t": [1], "$l": []},
        {"$d": {}, "fazla": 1},
        {"$t": {"a": 1}},
        {"$d": [1]},
        {"duz": "etiketsiz nesne"},
        {"$m": ["Bilinmeyen", {"$d": {}}]},
        {"$m": ["Parameter"]},
        {"$m": ["Parameter", {"$d": {"name": "a", "low": 1}}]},
        {"$m": ["Parameter", {"$d": {"name": "a", "low": 1, "high": 2, "exclude": [], "x": 1}}]},
        {"$m": ["Parameter", {"$d": {"__init__": 1, "name": "a", "low": 1, "high": 2}}]},
    ],
)
def test_bilinmeyen_etiket_ve_alan_reddedilir(deger):
    with pytest.raises(wire.WireError):
        _coz(_ok(deger))


@pytest.mark.parametrize(
    "ham",
    [
        b"",
        b"\xff\xfe",
        b"[]",
        b'{"status":"ok","value":1,"seq":7}',
        b'{"status":"ok","value":1,"retire":0,"seq":7}',
        b'{"status":"nope","value":1,"retire":false,"seq":7}',
        b'{"status":"err","exc":1,"message":"m","retire":false,"seq":7}',
        b'{"status":"err","exc":"builtins.ValueError","retire":false,"seq":7}',
        b'{"status":"crash","message":["m"],"retire":false,"seq":7}',
        b'{"status":"ok","value":NaN,"retire":false,"seq":7}',
        b'{"status":"ok","value":Infinity,"retire":false,"seq":7}',
        b'{"status":"ok","value":1e999,"retire":false,"seq":7}',
    ],
)
def test_gecersiz_zarf_reddedilir(ham):
    with pytest.raises(wire.WireError):
        _coz(ham)


# --- `$m` alan tipi denetimi --------------------------------------------


@pytest.mark.parametrize(
    "bozuk",
    [
        {"id": 1},
        {"parameters": "abc"},
        {
            "parameters": [
                {
                    "$m": [
                        "Parameter",
                        {"$d": {"name": "a", "low": 1, "high": 2, "exclude": {"$t": []}}},
                    ]
                }
            ]
        },
        {"parameters": {"$t": [1]}},
        {"objective": 3},
        {"seed_bindings": {"$d": {"a": "üç"}}},
        {"seed_bindings": {"$t": []}},
        {"seed_answer_ops": True},
        {"seed_answer_ops": 2.0},
        {"constraints": {"$t": ["a", 1]}},
    ],
)
def test_model_alan_tipi_uyusmazligi_reddedilir(bozuk):
    with pytest.raises(wire.WireError, match="alan"):
        _coz(_ok(_sablon_json(**bozuk)))


def test_parameter_exclude_listesi_reddedilir():
    tel = {"$m": ["Parameter", {"$d": {"name": "a", "low": 1, "high": 2, "exclude": [0]}}]}
    with pytest.raises(wire.WireError):
        _coz(_ok(tel))


def test_model_alan_tipi_gecerli_varyantlar_kabul():
    tel = _sablon_json(objective=None, constraints={"$t": []}, seed_bindings={"$d": {}})
    assert _coz(_ok(tel))[1] == _sablon(objective=None, constraints=(), seed_bindings={})


def test_alan_ipucu_denetleyicisi_bicimleri():
    kontrol = wire._hint_check
    assert kontrol(float)(3) and kontrol(float)(2.5) and not kontrol(float)(True)
    assert kontrol(int)(3) and not kontrol(int)(True) and not kontrol(int)(3.0)
    assert kontrol(str | None)(None) and kontrol(str | None)("a") and not kontrol(str | None)(1)
    assert kontrol(tuple[int, str])((1, "a")) and not kontrol(tuple[int, str])((1, 2))
    assert not kontrol(tuple[int, str])((1,))
    assert kontrol(tuple[int, ...])(()) and not kontrol(tuple[int, ...])([1])
    assert kontrol(list[str])(["a"]) and not kontrol(list[str])(("a",))
    assert kontrol(dict[str, int])({"a": 1}) and not kontrol(dict[str, int])({"a": "b"})
    assert kontrol(Parameter)(Parameter("a", 1, 2)) and not kontrol(Parameter)({"name": "a"})
    assert kontrol(dict[str, object])({"a": [1, (2,)]})


@pytest.mark.parametrize(
    "ipucu", [set[int], typing.Any, dict[int, str], bytes, list, typing.Literal["a"], complex]
)
def test_desteklenmeyen_alan_ipucu_hata_verir(ipucu):
    with pytest.raises(TypeError):
        wire._hint_check(ipucu)


def test_mevcut_models_alanlarinin_tumu_denetleniyor():
    for cls in _models_dataclasslari():
        ipuclari = typing.get_type_hints(cls)
        for alan in dataclasses.fields(cls):
            wire._hint_check(ipuclari[alan.name])  # desteklenmiyorsa TypeError
        assert set(wire._MODEL_CHECKS[cls]) == {f.name for f in dataclasses.fields(cls)}


# --- Değişmezlik ve pickle yokluğu --------------------------------------


def test_isci_yukleri_models_siniflarini_degistiremez():
    ozgun = dict(vars(Parameter))
    yukler = [
        _ok({"$m": ["Parameter", {"$d": {"__init__": {"$d": {}}}}]}),
        _ok({"$m": ["Parameter", {"$d": {"__setstate__": 1, "__class__": "x"}}]}),
        _ok({"$m": ["Parameter", {"$d": {"name": "a", "low": 1, "high": 2, "__dict__": {}}}]}),
        _ok({"$m": ["__init__", {"$d": {}}]}),
        _hata_zarfi("questioncrator.models.Parameter", "m"),
    ]
    for ham in yukler:
        try:
            _coz(ham)
        except wire.WireError:
            pass
    assert dict(vars(Parameter)) == ozgun
    assert Parameter("a", 1, 9) == Parameter(name="a", low=1, high=9, exclude=(0,))


def test_wire_pickle_ve_regex_on_tarama_kullanmaz():
    import inspect

    kaynak = inspect.getsource(wire)
    assert "pickle" not in kaynak
    assert "import re" not in kaynak and "_prescan" not in kaynak
