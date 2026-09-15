"""Uçtan uca değişmezlik: çıkarılan şablon, öğrencinin gördüğü metinle
reçeteyi hep birlikte değiştirir; biri değişip öteki sabit kalmaz.

Derlem gerçek içeriktir (`tests/data/extract_derlem.json`); hiçbir şey
taklit edilmez, gerçek `extract_template`, `render_text`, `render_recipe`
ve `mathenv.parse` çağrılır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from questioncrator import mathenv
from questioncrator.models import SourceQuestion
from questioncrator.templating import extract
from questioncrator.templating.render import render_recipe, render_text

DERLEM = json.loads(
    (Path(__file__).parent / "data" / "extract_derlem.json").read_text(encoding="utf-8")
)
_UST_SIMGE = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def _kaynak(ornek: dict) -> SourceQuestion:
    return SourceQuestion(id=ornek["id"], text=ornek["metin"], recipe=ornek["recete"])


def _cikar(ornek: dict):
    try:
        return extract.extract_template(_kaynak(ornek), "t1")
    except extract.NoParametersFound:
        return None


def _ayirt_edici(ornek: dict) -> int:
    for aday in (7, 8, 6, 9, 11, 13):
        if str(aday) not in ornek["metin"] and str(aday) not in ornek["recete"]:
            return aday
    raise AssertionError("ayırt edici değer bulunamadı")


def _guvensiz(metin: str, bas: int, son: int) -> bool:
    """Brief'teki güvensiz bağlam listesinin testteki bağımsız karşılığı."""
    once, sonra = metin[:bas], metin[son:]
    if re.search(r"[0-9]$", once) or re.match(r"[0-9]", sonra):
        return True
    if re.search(r"\d[.,]$", once) or re.match(r"[.,]\d", sonra):
        return True
    if re.search(r"(\^|\*\*|_)\s*-?\s*$", once):
        return True
    derinlik = {"{": 0, "[": 0}
    for i in range(len(once) - 1, -1, -1):
        karakter = once[i]
        if karakter in "}]":
            derinlik["{" if karakter == "}" else "["] -= 1
        elif karakter in "{[":
            derinlik[karakter] += 1
            if derinlik[karakter] > 0:
                if karakter == "{" and once[:i].rstrip()[-1:] in ("^", "_"):
                    return True
                if karakter == "[" and once[:i].rstrip().endswith("\\sqrt"):
                    return True
                derinlik[karakter] = 0
    return False


def _gecisler(metin: str, sayi: int) -> list[re.Match]:
    return [m for m in re.finditer(r"[0-9]+", metin) if m.group() == str(sayi)]


@pytest.mark.parametrize("ornek", DERLEM, ids=[o["id"] for o in DERLEM])
def test_receteler_gecerli_ve_beklenen_parametreler(ornek):
    mathenv.parse(ornek["recete"])
    t = _cikar(ornek)
    beklenen = ornek["parametreler"]
    if not beklenen:
        assert t is None, f"parametre beklenmiyordu: {t and t.recipe}"
        return
    assert t is not None
    assert [t.seed_bindings[p.name] for p in t.parameters] == beklenen


@pytest.mark.parametrize("ornek", DERLEM, ids=[o["id"] for o in DERLEM])
def test_tohumla_gidis_donus(ornek):
    t = _cikar(ornek)
    if t is None:
        return
    tohum = t.seed_bindings
    assert render_text(t, tohum) == ornek.get("beklenen_metin", ornek["metin"])
    geri = re.sub(r"\{(p\d+)\}", lambda m: str(tohum[m.group(1)]), t.recipe)
    assert geri == ornek["recete"]
    assert mathenv.parse(render_recipe(t, tohum)) == mathenv.parse(ornek["recete"])


@pytest.mark.parametrize("ornek", DERLEM, ids=[o["id"] for o in DERLEM])
def test_her_parametre_metinde_ve_recetede_gorunur(ornek):
    t = _cikar(ornek)
    if t is None:
        return
    ayirt = _ayirt_edici(ornek)
    for parametre in t.parameters:
        for deger in (ayirt, -ayirt):
            baglama = {**t.seed_bindings, parametre.name: deger}
            metin = render_text(t, baglama)
            recete = render_recipe(t, baglama)
            gecisler = _gecisler(metin, ayirt)
            baglam = f"{parametre.name}={deger}: {metin!r}"
            assert gecisler, f"değer metinde görünmüyor: {baglam}"
            for m in gecisler:
                assert not _guvensiz(metin, m.start(), m.end()), f"güvensiz bağlam: {baglam}"
            assert f"({deger})" in recete, f"değer reçetede yok: {recete!r}"
            mathenv.parse(recete)
            if deger < 0:
                for m in gecisler:
                    sonra = metin[m.end():]
                    sonra = re.sub(r"^\s*(\}|\\right\))?\s*", "", sonra)
                    kuvvet = sonra[:1] in ("^", "!") or sonra.startswith("**")
                    if kuvvet or sonra[:1] in _UST_SIMGE:
                        assert metin[:m.start()].endswith("(-"), (
                            f"negatif taban parantezsiz: {baglam}"
                        )
