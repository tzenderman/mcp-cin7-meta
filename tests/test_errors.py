"""Tests for the Cin7 error hierarchy."""

from cin7_meta.utils.errors import (
    Cin7APIError,
    Cin7AuthError,
    Cin7Error,
    Cin7NotFoundError,
    Cin7RateLimitError,
)


def test_base_error_message():
    err = Cin7Error("Something failed")
    assert str(err) == "Something failed"


def test_subclasses_inherit_base():
    for cls in (Cin7AuthError, Cin7NotFoundError, Cin7RateLimitError, Cin7APIError):
        err = cls("boom")
        assert isinstance(err, Cin7Error)
        assert str(err) == "boom"


def test_subclasses_are_distinct():
    assert Cin7AuthError is not Cin7APIError
    assert not isinstance(Cin7AuthError("x"), Cin7NotFoundError)
