import pytest

from open_rando.json_types import as_json_object, load_json_object, load_json_object_list


def test_load_json_object_returns_the_decoded_object() -> None:
    assert load_json_object('{"elements": []}') == {"elements": []}


def test_load_json_object_refuses_an_array() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        load_json_object("[1, 2]")


def test_as_json_object_refuses_a_string() -> None:
    with pytest.raises(ValueError, match="got str"):
        as_json_object("not an object")


def test_load_json_object_list_returns_every_object() -> None:
    assert load_json_object_list('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_load_json_object_list_refuses_a_non_object_item() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        load_json_object_list('[{"a": 1}, 3]')
