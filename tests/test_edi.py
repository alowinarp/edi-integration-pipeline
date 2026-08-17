"""
test_edi.py
-----------
pytest finds tests by NAME: any function starting with "test_" in a file named
test_*.py is collected and run. Each test follows the same shape:

    1. arrange - build or read the input
    2. act     - call one function
    3. assert  - state what the answer must be

`assert` is plain Python: if the expression is False the test fails, and pytest
prints the values involved.

Run them from the project folder with:   pytest
"""

import os
import sys

# The application code lives in src/, which is not on Python's import path when
# pytest runs from the project folder. This adds it, so `import edi_parser`
# works below. sys.path is just a list of folders Python searches.
SRC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, SRC_FOLDER)

from edi_parser import parse_edi, get_segment, get_segments, convert_850_to_json
from validation import validate_850, validate_invoice, validate_generated_810
from edi_997 import generate_997
from edi_810 import generate_810, calculate_invoice_total

INPUT_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "input"
)


# ---------------------------------------------------------------------------
# Small helpers used by several tests
# ---------------------------------------------------------------------------

def read_sample_850(file_name):
    path = os.path.join(INPUT_FOLDER, file_name)
    with open(path, "r") as open_file:
        return open_file.read()


def build_sample_invoice():
    """One valid invoice, built in Python so the tests do not depend on files."""
    invoice = {
        "invoice_number": "INV10001",
        "invoice_date": "20260817",
        "purchase_order_number": "PO10001",
        "buyer": {"name": "NORTHWIND RETAIL LLC", "id": "BUYER001"},
        "seller": {"name": "CASCADE SUPPLY CO", "id": "SELLER001"},
        "line_items": [
            {
                "line_number": "1",
                "product_id": "WIDGET-100",
                "quantity": "10",
                "unit_of_measure": "EA",
                "unit_price": "12.50",
            },
            {
                "line_number": "2",
                "product_id": "GADGET-200",
                "quantity": "5",
                "unit_of_measure": "CA",
                "unit_price": "45.00",
            },
        ],
    }

    return invoice


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_valid_850_finds_the_expected_segments():
    edi_text = read_sample_850("valid_850.txt")

    segments = parse_edi(edi_text)

    # The first element of the first segment is the segment ID.
    assert segments[0][0] == "ISA"
    assert get_segment(segments, "BEG") is not None
    assert get_segment(segments, "IEA") is not None
    assert len(get_segments(segments, "PO1")) == 2


def test_parse_reads_individual_elements():
    edi_text = read_sample_850("valid_850.txt")

    segments = parse_edi(edi_text)
    beg_segment = get_segment(segments, "BEG")

    assert beg_segment[3] == "PO10001"   # BEG03 purchase order number
    assert beg_segment[5] == "20260817"  # BEG05 purchase order date


# ---------------------------------------------------------------------------
# 850 validation
# ---------------------------------------------------------------------------

def test_valid_850_has_no_validation_errors():
    segments = parse_edi(read_sample_850("valid_850.txt"))

    errors = validate_850(segments)

    assert errors == []


def test_invalid_850_is_detected():
    segments = parse_edi(read_sample_850("invalid_850.txt"))

    errors = validate_850(segments)

    assert len(errors) > 0

    # Join the messages into one string so they can be searched easily.
    all_errors = " ".join(errors)
    assert "Purchase order number is missing" in all_errors
    assert "Purchase order date is missing" in all_errors
    assert "quantity 'ABC'" in all_errors


# ---------------------------------------------------------------------------
# 850 -> JSON
# ---------------------------------------------------------------------------

def test_convert_850_to_json_returns_the_business_data():
    segments = parse_edi(read_sample_850("valid_850.txt"))

    purchase_order = convert_850_to_json(segments)

    assert purchase_order["purchase_order_number"] == "PO10001"
    assert purchase_order["purchase_order_date"] == "20260817"
    assert purchase_order["buyer"]["name"] == "NORTHWIND RETAIL LLC"
    assert purchase_order["seller"]["name"] == "CASCADE SUPPLY CO"


def test_convert_850_to_json_returns_two_line_items():
    segments = parse_edi(read_sample_850("valid_850.txt"))

    purchase_order = convert_850_to_json(segments)

    assert purchase_order["line_item_count"] == 2

    first_line = purchase_order["line_items"][0]
    assert first_line["product_id"] == "WIDGET-100"
    assert first_line["quantity"] == "10"
    assert first_line["unit_of_measure"] == "EA"
    assert first_line["extended_amount"] == 125.00


# ---------------------------------------------------------------------------
# 997 generation
# ---------------------------------------------------------------------------

def test_generate_997_accepts_a_valid_850():
    segments = parse_edi(read_sample_850("valid_850.txt"))
    errors = validate_850(segments)

    acknowledgment = generate_997(segments, errors)

    assert "ST*997*" in acknowledgment
    assert "AK1*PO*101" in acknowledgment    # group control number from the 850
    assert "AK2*850*0001" in acknowledgment  # ST control number from the 850
    assert "AK5*A" in acknowledgment
    assert "AK9*A*1*1*1" in acknowledgment


def test_generate_997_rejects_an_invalid_850():
    segments = parse_edi(read_sample_850("invalid_850.txt"))
    errors = validate_850(segments)

    acknowledgment = generate_997(segments, errors)

    assert "AK5*R*5" in acknowledgment
    assert "AK9*R*1*1*0" in acknowledgment


# ---------------------------------------------------------------------------
# Invoice validation
# ---------------------------------------------------------------------------

def test_valid_invoice_has_no_validation_errors():
    invoice = build_sample_invoice()

    errors = validate_invoice(invoice)

    assert errors == []


def test_invalid_invoice_is_detected():
    invoice = build_sample_invoice()

    # Break the invoice on purpose: remove the invoice number and the seller,
    # and put a non numeric quantity on the first line.
    del invoice["invoice_number"]
    del invoice["seller"]
    invoice["line_items"][0]["quantity"] = "ABC"

    errors = validate_invoice(invoice)

    all_errors = " ".join(errors)
    assert "invoice_number" in all_errors
    assert "seller" in all_errors
    assert "quantity 'ABC'" in all_errors


# ---------------------------------------------------------------------------
# Invoice -> 810
# ---------------------------------------------------------------------------

def test_calculate_invoice_total():
    invoice = build_sample_invoice()

    # (10 x 12.50) + (5 x 45.00) = 125.00 + 225.00 = 350.00
    assert calculate_invoice_total(invoice) == 350.00


def test_generate_810_builds_the_expected_segments():
    invoice = build_sample_invoice()

    edi_810 = generate_810(invoice)

    assert edi_810.startswith("ISA*")
    assert "ST*810*0001" in edi_810
    assert "BIG*20260817*INV10001**PO10001" in edi_810
    assert "N1*BY*NORTHWIND RETAIL LLC*92*BUYER001" in edi_810
    assert "N1*SE*CASCADE SUPPLY CO*92*SELLER001" in edi_810
    assert "TDS*35000" in edi_810   # 350.00 with an implied decimal
    assert "CTT*2" in edi_810


def test_generate_810_creates_one_it1_per_line_item():
    invoice = build_sample_invoice()

    edi_810 = generate_810(invoice)
    segments = parse_edi(edi_810)

    it1_segments = get_segments(segments, "IT1")
    assert len(it1_segments) == 2
    assert it1_segments[0][7] == "WIDGET-100"   # IT107 product id
    assert it1_segments[1][7] == "GADGET-200"


def test_generated_810_passes_its_own_validation():
    invoice = build_sample_invoice()

    edi_810 = generate_810(invoice)
    errors = validate_generated_810(edi_810)

    assert errors == []


def test_generated_810_se_count_is_correct():
    invoice = build_sample_invoice()

    edi_810 = generate_810(invoice)
    segments = parse_edi(edi_810)

    # ST, BIG, REF, N1, N1, IT1, IT1, TDS, CTT, SE = 10 segments
    se_segment = get_segment(segments, "SE")
    assert se_segment[1] == "10"
