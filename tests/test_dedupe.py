"""Tests für Dedupe."""
from src.dedupe import dedupe_batch, is_duplicate, title_similarity
from src.models import Opportunity


def o(id_, title):
    return Opportunity(id=id_, title=title)


def test_gleiche_id_ist_duplikat():
    assert is_duplicate(o("a", "X"), o("a", "ganz anders"))


def test_aehnlicher_titel_ist_duplikat():
    assert is_duplicate(o("a", "Deutsche SchülerAkademie 2027"), o("b", "Deutsche Schülerakademie 2027 "))


def test_andere_jahreszahl_ist_kein_duplikat():
    assert not is_duplicate(o("a", "Hackathon Berlin 2026"), o("b", "Hackathon Berlin 2027"))


def test_verschiedene_titel_sind_kein_duplikat():
    assert not is_duplicate(o("a", "Jugend forscht"), o("b", "Studienstiftung Stipendium"))
    assert title_similarity("abc", "abc") == 1.0


def test_batch_gegen_vorhandene_und_untereinander():
    vorhanden = [o("1", "Sommerakademie MINT")]
    neu = [o("2", "Sommerakademie MINT"), o("3", "KI Camp"), o("4", "KI Camp"), o("1", "egal")]
    behalten, entfernt = dedupe_batch(neu, vorhanden)
    assert [x.id for x in behalten] == ["3"]
    assert [x.id for x in entfernt] == ["2", "4", "1"]
