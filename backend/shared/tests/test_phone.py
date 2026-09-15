import pytest

from shared.phone import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9812345678", "+9779812345678"),
        ("+977 981-2345678", "+9779812345678"),
        ("009779812345678", "+9779812345678"),
        ("9779812345678", "+9779812345678"),
        ("01-4412345", "+97714412345"),
        ("+91 98765 43210", "+919876543210"),
    ],
)
def test_normalize_phone_accepts_common_formats(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_normalize_phone_returns_none_for_empty(raw):
    assert normalize_phone(raw) is None


@pytest.mark.parametrize("raw", ["12345", "98123abc78", "+97", "98+12345678"])
def test_normalize_phone_rejects_garbage(raw):
    with pytest.raises(ValueError, match="Unrecognised phone number"):
        normalize_phone(raw)
