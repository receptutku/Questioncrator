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
    with pytest.raises(Exception):  # noqa: B017 - hangi istisna türü fırlatılırsa fırlatılsın erişim kapalı olmalı
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
