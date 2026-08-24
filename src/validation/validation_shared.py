"""
validation_shared.py
-------------
contains functions shared by all specific validation modules
"""

# ---------------------------------------------------------------------------
# Small shared helpers
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
