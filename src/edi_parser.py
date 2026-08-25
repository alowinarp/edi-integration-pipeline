"""
edi_parser.py
-------------
Reading files, parsing EDI files, setting/retrieving the delimiters.

Python notes for this file:
  * A "segment" here is just a Python LIST of strings.
        "PO1*1*10*EA*12.50"  ->  ["PO1", "1", "10", "EA", "12.50"]
  * A parsed EDI document is just a LIST OF LISTS (a list of segments).
"""

import json
import os

from typing import NamedTuple
from edi_exceptions import EDIParseError


class Delimiters(NamedTuple):
    element_separator: str
    sub_element_separator: str
    segment_terminator: str


class EDIParsingResult(NamedTuple):
    delimiters: Delimiters
    segments: list[list[str]]


# The delimiters this system uses when it writes outbound EDI from scratch
# (there's nothing inbound to inherit delimiters from in that case).
DEFAULT_DELIMITERS = Delimiters(
    element_separator="*",
    sub_element_separator=">",
    segment_terminator="~",
)

# ---------------------------------------------------------------------------
# Retrieve Delimiters helpers
# ---------------------------------------------------------------------------

def check_isa(raw_edi: str) -> None:

    if not raw_edi.startswith("ISA"):
        raise EDIParseError("Missing ISA segment")

    if len(raw_edi) < 106:
        raise EDIParseError("Incomplete ISA segment")
    
    isa_terminator = raw_edi[105]

    if isa_terminator.isalnum():
        raise EDIParseError("Invalid segment terminator")

    return None


def detect_delimiters(raw_edi: str) -> Delimiters:
    element_separator = raw_edi[3]
    sub_element_separator = raw_edi[104]
    segment_terminator = raw_edi[105]

    return Delimiters(
        element_separator=element_separator,
        sub_element_separator=sub_element_separator,
        segment_terminator=segment_terminator,
    )


# ---------------------------------------------------------------------------
# File handling helpers
# ---------------------------------------------------------------------------

def read_text_file(file_path):
    """Read a whole text file and return it as one string.

    `with open(...)` opens the file and automatically closes it again when the
    indented block ends - even if an error happens inside the block. This is
    the standard way to work with files in Python.
    """
    with open(file_path, "r") as open_file:
        file_contents = open_file.read()

    return file_contents


def write_text_file(file_path, text):
    """Write a string to a text file, creating the folder if it is missing."""
    # os.path.dirname("output/997/PO10001_997.txt") -> "output/997"
    folder = os.path.dirname(file_path)
    if folder != "":
        # exist_ok=True means "do not raise an error if the folder is there".
        os.makedirs(folder, exist_ok=True)

    # "w" means write mode: an existing file with the same name is replaced.
    with open(file_path, "w") as open_file:
        open_file.write(text)

    return file_path


def read_json_file(file_path):
    """Read a JSON file and return it as a Python dictionary.

    json.load() reads from an open file. json.loads() (with the "s") would read
    from a string instead. That single letter is the only difference.
    """
    with open(file_path, "r") as open_file:
        data = json.load(open_file)

    return data


def write_json_file(file_path, data):
    """Write a Python dictionary to a JSON file, nicely indented."""
    folder = os.path.dirname(file_path)
    if folder != "":
        os.makedirs(folder, exist_ok=True)

    with open(file_path, "w") as open_file:
        # indent=2 makes the file readable for a human instead of one long line.
        json.dump(data, open_file, indent=2)

    return file_path


# ---------------------------------------------------------------------------
# Splitting and parsing X12
# ---------------------------------------------------------------------------

def split_segments(edi_text: str, delimiters: Delimiters) -> list:

    segments = edi_text.split(delimiters.segment_terminator)

    segment_strings = []

    for segment in segments:
        trimmed_segment = segment.strip()
        if trimmed_segment != "":
            segment_strings.append(trimmed_segment)

    return segment_strings


def parse_edi(raw_edi: str) -> EDIParsingResult:
    """Turn EDI text into a list of segments, each segment a list of elements.
    This is deliberately NOT a general purpose X12 parser. It assumes the
    separators defined at the top of this file.
    """

    edi_text = raw_edi.strip()

    check_isa(edi_text)

    edi_delimiters = detect_delimiters(edi_text)
    edi_segments = split_segments(edi_text, edi_delimiters)

    segment_elements = []
    # Split elements so segment[0] becomes "GS", segment[1] becomes "PO", etc.

    for segment in edi_segments:
        elements = segment.split(edi_delimiters.element_separator)
        segment_elements.append(elements)

    return EDIParsingResult(
        delimiters=edi_delimiters,
        segments=segment_elements,
    ) 


def get_segment(segments: list, segment_id: str) -> list | None:
    """Return the FIRST segment with this ID, or None if it is not present.

    Returning None (instead of raising an error) lets the validation code
    report a friendly message such as "BEG segment is missing".
    """
    for segment in segments:
        if segment[0] == segment_id:
            return segment

    return None


def get_segments(segments: list, segment_id: str) -> list:
    """Return ALL segments with this ID as a list (empty list if none)."""
    matching_segments = []
    for segment in segments:
        if segment[0] == segment_id:
            matching_segments.append(segment)

    return matching_segments


def get_element(segment: list[str] | None, position: int) -> str:
    """Safely read one element out of a segment.

    Trailing empty elements are often left off a segment, so segment[7] can
    raise an IndexError. This helper returns "" instead, which keeps the rest
    of the code free of length checks.
    """
    if segment is None:
        return ""

    if position < len(segment):
        return segment[position].strip()

    return ""

def build_segment(elements: str, delimiters: Delimiters):
    """Join a list of elements into one segment string ending with "~".

    "*".join(["PO1", "1", "10"]) -> "PO1*1*10"
    """
    return delimiters.element_separator.join(elements) + delimiters.segment_terminator

def pad_to_length(value, length):
    """Pad a string with trailing spaces to a fixed width (ISA needs this).

    .ljust() pads on the right. [:length] then trims anything too long.
    """
    return value.ljust(length)[:length]
