from __future__ import annotations

import json
import math

import pytest
import sympy

from questioncrator import wire
from questioncrator.mathenv import EvaluationTimeout, UnsafeExpression
from questioncrator.models import Parameter, Review, Template
from questioncrator.templating.extract import NoParametersFound


def _ok(value: object) -> bytes:
    return json.dumps({"status": "ok", "value": value, "retire": False}).encode()


def _sablon() -> Template:
    return Template(
        id="t_1",
        source_id="s_1",
        skeleton="{a} + {b}",
        recipe="a + b",
        parameters=(Parameter("a", 1, 9), Parameter("b", 2, 8, exclude=(0, 5))),
        constraints=("a != b",),
        seed_bindings={"a": 3, "b": 4},
        seed_answer_ops=2,
    )


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
        "düz metin \" [ { \\ } ] ,",
        [1, [2, [3]]],
        (1, (2, None), []),
        {"a": [1, (2, 3)], "b": {"c": {"d": ()}}},
        (),
        {},
    ],
)
def test_ilkel_ve_ic_ice_kaplar_gidis_donus(deger):
    status, sonuc, retire = wire.loads_reply(wire.dumps_ok(deger, retire=False))
    assert (status, retire) == ("ok", False)
    assert sonuc == deger
    assert type(sonuc) is type(deger)


def test_tuple_ve_liste_ayrimi_korunur():
    _, sonuc, _ = wire.loads_reply(wire.dumps_ok([(1, [2]), [(3,)]], retire=False))
    assert sonuc == [(1, [2]), [(3,)]]
    assert isinstance(sonuc[0], tuple) and isinstance(sonuc[0][1], list)


def test_models_dataclasslari_gidis_donus():
    deger = {"sablon": _sablon(), "inceleme": Review("q_1", True, 4, 7, "2026-09-15")}
    _, sonuc, _ = wire.loads_reply(wire.dumps_ok(deger, retire=True))
    assert sonuc == deger
    assert type(sonuc["sablon"].parameters[0]) is Parameter


def test_kayit_models_dataclasslarinin_hepsini_kapsar():
    import dataclasses

    from questioncrator import models

    beklenen = {
        ad
        for ad, nesne in vars(models).items()
        if isinstance(nesne, type)
        and dataclasses.is_dataclass(nesne)
        and nesne.__module__ == models.__name__
    }
    assert beklenen and set(wire.model_names()) == beklenen


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
    ],
)
def test_kayitli_istisnalar_turuyle_doner(istisna):
    status, sonuc, retire = wire.loads_reply(wire.dumps_error(istisna, retire=False))
    assert status == "err"
    assert type(sonuc) is type(istisna)
    assert str(sonuc) == str(istisna)


def test_istisna_kaydina_alt_sinif_eklenebilir():
    class OzelHata(ValueError):
        pass

    ham = wire.dumps_error(OzelHata("özel"), retire=False)
    assert wire.loads_reply(ham)[0] == "crash"
    wire.register_exception(OzelHata)
    try:
        status, sonuc, _ = wire.loads_reply(ham)
        assert status == "err" and type(sonuc) is OzelHata and str(sonuc) == "özel"
    finally:
        wire.unregister_exception(OzelHata)


def test_mesajdan_kurulamayan_istisna_crash_olur():
    class IkiArguman(Exception):
        def __init__(self, a, b):
            super().__init__(a, b)

    wire.register_exception(IkiArguman)
    try:
        ham = wire.dumps_error(IkiArguman("x", "y"), retire=False)
        assert wire.loads_reply(ham)[0] == "crash"
    finally:
        wire.unregister_exception(IkiArguman)


def test_istisna_from_message_yolu():
    class IkiArguman(Exception):
        def __init__(self, a, b):
            super().__init__(a, b)

    wire.register_exception(IkiArguman, from_message=lambda mesaj: IkiArguman(mesaj, None))
    try:
        status, sonuc, _ = wire.loads_reply(wire.dumps_error(IkiArguman("x", "y"), retire=False))
        assert status == "err" and type(sonuc) is IkiArguman
    finally:
        wire.unregister_exception(IkiArguman)


@pytest.mark.parametrize("istisna", [StopIteration("dur"), LookupError("kayıtsız"), OSError("os")])
def test_kayitsiz_istisna_crash_olur(istisna):
    status, mesaj, _ = wire.loads_reply(wire.dumps_error(istisna, retire=False))
    assert status == "crash"
    assert isinstance(mesaj, str)


def test_crash_zarfi():
    assert wire.loads_reply(wire.dumps_crash("çöktü", retire=True)) == ("crash", "çöktü", True)


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
        wire.dumps_ok(deger, retire=False)


def test_sympy_red_mesaji_modul_adini_tasir():
    with pytest.raises(wire.WireError, match=r"sonuç türü aktarılamaz: sympy\."):
        wire.dumps_ok(sympy.Integer(3), retire=False)


def test_kodlama_derinlik_ve_oge_siniri():
    derin: object = 1
    for _ in range(wire.MAX_DEPTH + 1):
        derin = [derin]
    with pytest.raises(wire.WireError):
        wire.dumps_ok(derin, retire=False)
    with pytest.raises(wire.WireError):
        wire.dumps_ok([0] * (wire.MAX_ITEMS + 1), retire=False)


def test_kodlama_dev_int_reddedilir():
    with pytest.raises(wire.WireError):
        wire.dumps_ok(10**5000, retire=False)


# --- Ebeveyn tarafı çözme retleri ---------------------------------------


def test_json_modulu_int_hane_sinirini_uygular():
    # Sabitleme: CPython `json` int dönüşümünde 4300 hane sınırını uygular.
    with pytest.raises(ValueError):
        json.loads("1" * 4301)
    assert json.loads("1" * 4300) == int("1" * 4300)


@pytest.mark.parametrize(
    "ham",
    [
        b'{"status":"ok","value":' + b"9" * 4301 + b',"retire":false}',
        b'{"status":"ok","value":[' + b"1" * 5000 + b'],"retire":false}',
    ],
)
def test_dev_int_metni_reddedilir(ham):
    with pytest.raises(wire.WireError):
        wire.loads_reply(ham)


def test_yinelenen_anahtar_reddedilir():
    with pytest.raises(wire.WireError):
        wire.loads_reply(b'{"status":"ok","status":"ok","value":1,"retire":false}')
    with pytest.raises(wire.WireError):
        wire.loads_reply(_ok({"$d": {}})[:-1].replace(b"{}", b'{"a":1,"a":2}') + b"}")


def test_derinlik_siniri_asimi():
    ic = "[" * (wire.MAX_DEPTH + 1) + "]" * (wire.MAX_DEPTH + 1)
    with pytest.raises(wire.WireError):
        wire.loads_reply(b'{"status":"ok","value":' + ic.encode() + b',"retire":false}')


def test_derinlik_sinirina_kadar_kabul_edilir():
    deger: object = 1
    for _ in range(wire.MAX_DEPTH - 2):
        deger = [deger]
    assert wire.loads_reply(wire.dumps_ok(deger, retire=False))[1] == deger


def test_metin_icindeki_parantezler_derinlik_sayilmaz():
    metin = "[" * 10_000 + "{" * 10_000 + '\\"' * 50
    assert wire.loads_reply(wire.dumps_ok(metin, retire=False))[1] == metin


def test_oge_siniri_asimi():
    govde = "[" + ",".join(["0"] * (wire.MAX_ITEMS + 1)) + "]"
    with pytest.raises(wire.WireError):
        wire.loads_reply(b'{"status":"ok","value":' + govde.encode() + b',"retire":false}')


def test_int_anahtar_temsil_edilemez():
    # JSON'da nesne anahtarları hep metindir; `$d` yalnız metin anahtar taşır.
    # Çakışan int anahtarlı dev sözlük/küme bu yüzden ifade edilemez.
    with pytest.raises(wire.WireError):
        wire.dumps_ok({2**61 - 1: 1, 0: 2}, retire=False)
    _, sonuc, _ = wire.loads_reply(_ok({"$d": {"1": 1}}))
    assert sonuc == {"1": 1}


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
        wire.loads_reply(_ok(deger))


@pytest.mark.parametrize(
    "ham",
    [
        b"",
        b"\xff\xfe",
        b"[]",
        b'{"status":"ok","value":1}',
        b'{"status":"ok","value":1,"retire":0}',
        b'{"status":"nope","value":1,"retire":false}',
        b'{"status":"err","exc":1,"message":"m","retire":false}',
        b'{"status":"err","exc":"builtins.ValueError","retire":false}',
        b'{"status":"crash","message":["m"],"retire":false}',
        b'{"status":"ok","value":NaN,"retire":false}',
        b'{"status":"ok","value":Infinity,"retire":false}',
        b'{"status":"ok","value":1e999,"retire":false}',
    ],
)
def test_gecersiz_zarf_reddedilir(ham):
    with pytest.raises(wire.WireError):
        wire.loads_reply(ham)


_SINIR = 16 * 1024 * 1024


@pytest.mark.parametrize(
    "ham",
    [
        # Kapanmamış kaçışlı tırnak yığını: dizge regex'i her tırnaktan yeniden
        # tararsa O(n²) olur.
        b'{"status":"ok","value":' + b'"\\' * (_SINIR // 2) + b"}",
        b'{"status":"ok","value":' + b'"' * _SINIR + b"}",
        # 4300 hanelik (izinli) koşular + sonda tek 4301 hanelik koşu: geriye
        # bakışsız regex her iç konumdan yeniden sayar, O(n·4300) olur.
        b'{"status":"ok","value":['
        + (b"1" * 4300 + b",") * (_SINIR // 4301)
        + b"1" * 4301
        + b'],"retire":false}',
        b'{"status":"ok","value":'
        + b"[" * (_SINIR // 2)
        + b"]" * (_SINIR // 2)
        + b',"retire":false}',
        b'{"status":"ok","value":[' + b"0," * (_SINIR // 2) + b'0],"retire":false}',
    ],
    ids=["kacisli-tirnak", "tirnak", "hane-kosulari", "ic-ice", "virgul"],
)
def test_patolojik_yanit_dogrusal_surede_reddedilir(ham):
    # Çözme ebeveynde süre sınırı dışında koşar; en kötü 16 MB yük hızlı bitmeli.
    import time

    baslangic = time.monotonic()
    with pytest.raises(wire.WireError):
        wire.loads_reply(ham)
    assert time.monotonic() - baslangic < 2


def test_sinirdaki_gecerli_yanit_hizli_cozulur():
    import time

    ham = wire.dumps_ok(["a,[{:" * 50_000, list(range(wire.MAX_ITEMS - 10))], retire=False)
    baslangic = time.monotonic()
    assert wire.loads_reply(ham)[0] == "ok"
    assert time.monotonic() - baslangic < 2


def test_isci_yukleri_models_siniflarini_degistiremez():
    ozgun = {ad: dict(vars(Parameter)) for ad in ("Parameter",)}
    yukler = [
        _ok({"$m": ["Parameter", {"$d": {"__init__": {"$d": {}}}}]}),
        _ok({"$m": ["Parameter", {"$d": {"__setstate__": 1, "__class__": "x"}}]}),
        _ok({"$m": ["Parameter", {"$d": {"name": "a", "low": 1, "high": 2, "__dict__": {}}}]}),
        _ok({"$m": ["__init__", {"$d": {}}]}),
        b'{"status":"err","exc":"questioncrator.models.Parameter","message":"m","retire":false}',
    ]
    for ham in yukler:
        try:
            wire.loads_reply(ham)
        except wire.WireError:
            pass
    assert dict(vars(Parameter)) == ozgun["Parameter"]
    assert Parameter("a", 1, 9) == Parameter(name="a", low=1, high=9, exclude=(0,))


def test_wire_pickle_kullanmaz():
    import inspect

    kaynak = inspect.getsource(wire)
    assert "pickle" not in kaynak
