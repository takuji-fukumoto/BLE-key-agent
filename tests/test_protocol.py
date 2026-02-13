"""Unit tests for common.protocol module."""

import json

import pytest

from common.protocol import KeyEvent, KeyType, Modifiers


class TestKeyType:
    """Tests for KeyType enum."""

    def test_char_value(self) -> None:
        assert KeyType.CHAR.value == "c"

    def test_special_value(self) -> None:
        assert KeyType.SPECIAL.value == "s"

    def test_modifier_value(self) -> None:
        assert KeyType.MODIFIER.value == "m"

    def test_from_string(self) -> None:
        assert KeyType("c") == KeyType.CHAR
        assert KeyType("s") == KeyType.SPECIAL
        assert KeyType("m") == KeyType.MODIFIER

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            KeyType("x")


class TestModifiers:
    """Tests for Modifiers dataclass."""

    def test_default_all_false(self) -> None:
        mod = Modifiers()
        assert mod.cmd is False
        assert mod.ctrl is False
        assert mod.alt is False
        assert mod.shift is False

    def test_is_default_true(self) -> None:
        assert Modifiers().is_default() is True

    def test_is_default_false(self) -> None:
        assert Modifiers(shift=True).is_default() is False

    def test_to_dict(self) -> None:
        mod = Modifiers(cmd=True, shift=True)
        d = mod.to_dict()
        assert d == {"cmd": True, "ctrl": False, "alt": False, "shift": True}

    def test_from_dict(self) -> None:
        mod = Modifiers.from_dict({"cmd": True, "ctrl": False, "alt": False, "shift": True})
        assert mod.cmd is True
        assert mod.shift is True
        assert mod.ctrl is False

    def test_from_dict_partial(self) -> None:
        mod = Modifiers.from_dict({"shift": True})
        assert mod.shift is True
        assert mod.cmd is False

    def test_frozen(self) -> None:
        mod = Modifiers()
        with pytest.raises(AttributeError):
            mod.cmd = True  # type: ignore[misc]


class TestKeyEventSerialize:
    """Tests for KeyEvent.serialize()."""

    def test_char_key_full_format(self) -> None:
        event = KeyEvent(
            key_type=KeyType.CHAR,
            value="a",
            press=True,
            modifiers=Modifiers(shift=True),
            timestamp=1700000000.0,
        )
        data = event.serialize()
        obj = json.loads(data)
        assert obj["t"] == "c"
        assert obj["v"] == "a"
        assert obj["p"] is True
        assert obj["mod"]["shift"] is True
        assert obj["ts"] == 1700000000.0

    def test_short_format_no_mod_no_ts(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        data = event.serialize()
        obj = json.loads(data)
        assert "mod" not in obj
        assert "ts" not in obj
        assert obj == {"t": "c", "v": "a", "p": True}

    def test_short_format_default_modifiers_omitted(self) -> None:
        event = KeyEvent(
            key_type=KeyType.CHAR,
            value="a",
            press=True,
            modifiers=Modifiers(),
        )
        data = event.serialize()
        obj = json.loads(data)
        assert "mod" not in obj

    def test_returns_bytes(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        assert isinstance(event.serialize(), bytes)

    def test_utf8_encoding(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        data = event.serialize()
        assert data == data.decode("utf-8").encode("utf-8")

    def test_compact_json_no_spaces(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        text = event.serialize().decode("utf-8")
        assert " " not in text.replace('" "', "")  # spaces only in value


class TestKeyEventDeserialize:
    """Tests for KeyEvent.deserialize()."""

    def test_full_format(self) -> None:
        raw = b'{"t":"c","v":"a","p":true,"mod":{"cmd":false,"ctrl":false,"alt":false,"shift":true},"ts":1700000000.0}'
        event = KeyEvent.deserialize(raw)
        assert event.key_type == KeyType.CHAR
        assert event.value == "a"
        assert event.press is True
        assert event.modifiers is not None
        assert event.modifiers.shift is True
        assert event.timestamp == 1700000000.0

    def test_short_format(self) -> None:
        raw = b'{"t":"c","v":"a","p":true}'
        event = KeyEvent.deserialize(raw)
        assert event.key_type == KeyType.CHAR
        assert event.modifiers is None
        assert event.timestamp is None

    def test_special_key(self) -> None:
        raw = b'{"t":"s","v":"enter","p":true}'
        event = KeyEvent.deserialize(raw)
        assert event.key_type == KeyType.SPECIAL
        assert event.value == "enter"

    def test_modifier_key(self) -> None:
        raw = b'{"t":"m","v":"shift","p":true}'
        event = KeyEvent.deserialize(raw)
        assert event.key_type == KeyType.MODIFIER
        assert event.value == "shift"

    def test_release_event(self) -> None:
        raw = b'{"t":"c","v":"a","p":false}'
        event = KeyEvent.deserialize(raw)
        assert event.press is False


class TestKeyEventRoundTrip:
    """Tests for serialize -> deserialize round-trip."""

    def test_full_format_roundtrip(self) -> None:
        original = KeyEvent(
            key_type=KeyType.CHAR,
            value="Z",
            press=False,
            modifiers=Modifiers(cmd=True, shift=True),
            timestamp=1700000000.5,
        )
        restored = KeyEvent.deserialize(original.serialize())
        assert restored.key_type == original.key_type
        assert restored.value == original.value
        assert restored.press == original.press
        assert restored.modifiers == original.modifiers
        assert restored.timestamp == original.timestamp

    def test_short_format_roundtrip(self) -> None:
        original = KeyEvent(key_type=KeyType.SPECIAL, value="backspace", press=True)
        restored = KeyEvent.deserialize(original.serialize())
        assert restored.key_type == original.key_type
        assert restored.value == original.value
        assert restored.press == original.press
        assert restored.modifiers is None
        assert restored.timestamp is None

    def test_all_modifiers_active_roundtrip(self) -> None:
        original = KeyEvent(
            key_type=KeyType.CHAR,
            value="a",
            press=True,
            modifiers=Modifiers(cmd=True, ctrl=True, alt=True, shift=True),
        )
        restored = KeyEvent.deserialize(original.serialize())
        assert restored.modifiers == original.modifiers

    def test_modifier_key_roundtrip(self) -> None:
        original = KeyEvent(key_type=KeyType.MODIFIER, value="cmd", press=True)
        restored = KeyEvent.deserialize(original.serialize())
        assert restored.key_type == KeyType.MODIFIER
        assert restored.value == "cmd"


class TestKeyEventEdgeCases:
    """Tests for edge cases."""

    def test_space_char(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value=" ", press=True)
        restored = KeyEvent.deserialize(event.serialize())
        assert restored.value == " "

    def test_at_symbol(self) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="@", press=True)
        restored = KeyEvent.deserialize(event.serialize())
        assert restored.value == "@"

    def test_f_keys(self) -> None:
        for i in range(1, 13):
            event = KeyEvent(key_type=KeyType.SPECIAL, value=f"f{i}", press=True)
            restored = KeyEvent.deserialize(event.serialize())
            assert restored.value == f"f{i}"

    def test_arrow_keys(self) -> None:
        for direction in ("up", "down", "left", "right"):
            event = KeyEvent(key_type=KeyType.SPECIAL, value=direction, press=True)
            restored = KeyEvent.deserialize(event.serialize())
            assert restored.value == direction


class TestKeyEventInvalidData:
    """Tests for error handling on invalid data."""

    def test_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Invalid key event data"):
            KeyEvent.deserialize(b"not json")

    def test_invalid_utf8(self) -> None:
        with pytest.raises(ValueError, match="Invalid key event data"):
            KeyEvent.deserialize(b"\xff\xfe")

    def test_missing_type_field(self) -> None:
        with pytest.raises(ValueError, match="Missing required field"):
            KeyEvent.deserialize(b'{"v":"a","p":true}')

    def test_missing_value_field(self) -> None:
        with pytest.raises(ValueError, match="Missing required field"):
            KeyEvent.deserialize(b'{"t":"c","p":true}')

    def test_missing_press_field(self) -> None:
        with pytest.raises(ValueError, match="Missing required field"):
            KeyEvent.deserialize(b'{"t":"c","v":"a"}')

    def test_invalid_key_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid key type"):
            KeyEvent.deserialize(b'{"t":"x","v":"a","p":true}')

    def test_empty_bytes(self) -> None:
        with pytest.raises(ValueError):
            KeyEvent.deserialize(b"")
