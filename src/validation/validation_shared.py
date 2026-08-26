"""
validation_shared.py
-------------
contains functions shared by all specific validation modules
"""

from enum import IntEnum
from typing import NamedTuple


class EDIError(NamedTuple):
    message: str
    code: int  # AK5Code or AK905Code value; stored as plain int so this type
               # stays tier-agnostic — generate_997() only needs int(code),
               # never which enum it came from.


class AK5Code(IntEnum):
    """Transaction Set Response Trailer error codes (AK502-AK506)."""
    TRANSACTION_SET_NOT_SUPPORTED = 1
    TRANSACTION_SET_TRAILER_MISSING = 2
    TRANSACTION_SET_CONTROL_NUMBER_MISMATCH = 3
    SEGMENT_COUNT_MISMATCH = 4
    SEGMENTS_HAVE_ERRORS = 5
    MISSING_OR_INVALID_TRANSACTION_SET_IDENTIFIER = 6
    MISSING_OR_INVALID_TRANSACTION_SET_CONTROL_NUMBER = 7


class AK905Code(IntEnum):
    """Functional Group Response Trailer error codes (AK905)."""
    FUNCTIONAL_GROUP_TRAILER_MISSING = 3
    GROUP_CONTROL_NUMBER_MISMATCH = 4
    TRANSACTION_COUNT_MISMATCH = 5
    GROUP_CONTROL_NUMBER_SYNTAX_ERROR = 6


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def is_number(value):
    """Return True if the text can be converted to a number.

    try/except is the normal Python way to test a conversion. float("ABC")
    raises ValueError, which is caught here and turned into False.
    """
    try:
        float(value)
        return True
    except ValueError:
        return False


def is_positive_number(value):
    """Return True if the text is a number greater than zero."""
    if not is_number(value):
        return False

    if float(value) <= 0:
        return False

    return True


def has_value(dictionary, key):
    """Return True if the key exists in the dictionary and is not empty."""
    if key not in dictionary:
        return False

    value = dictionary[key]
    if value is None:
        return False

    # A string of spaces counts as empty. str() protects against numbers.
    if str(value).strip() == "":
        return False

    return True
