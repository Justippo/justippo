import json
import re
from dataclasses import dataclass

from app.models.glossary import _utcnow, parse_mistranslations


@dataclass
class MockTerm:
    mistranslations: any = None


class MockTermMissing:
    pass


def test_parse_mistranslations_missing_attr():
    term = MockTermMissing()
    assert parse_mistranslations(term) == []


def test_parse_mistranslations_none():
    term = MockTerm(mistranslations=None)
    assert parse_mistranslations(term) == []


def test_parse_mistranslations_list_strings():
    term = MockTerm(mistranslations=["apple", "banana"])
    assert parse_mistranslations(term) == ["apple", "banana"]


def test_parse_mistranslations_list_mixed():
    term = MockTerm(mistranslations=["apple", 123, True])
    assert parse_mistranslations(term) == ["apple", "123", "True"]


def test_parse_mistranslations_json_list_strings():
    term = MockTerm(mistranslations=json.dumps(["apple", "banana"]))
    assert parse_mistranslations(term) == ["apple", "banana"]


def test_parse_mistranslations_json_list_mixed():
    term = MockTerm(mistranslations=json.dumps(["apple", 123, True]))
    assert parse_mistranslations(term) == ["apple", "123", "True"]


def test_parse_mistranslations_json_dict():
    term = MockTerm(mistranslations=json.dumps({"wrong": "format"}))
    assert parse_mistranslations(term) == []


def test_parse_mistranslations_invalid_json():
    term = MockTerm(mistranslations="[this is not valid json}")
    assert parse_mistranslations(term) == []


def test_parse_mistranslations_unsupported_type():
    term = MockTerm(mistranslations=42)
    assert parse_mistranslations(term) == []


def test_utcnow():
    ts = _utcnow()
    # Check if the string matches ISO-8601 format
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)$", ts)
