"""Run the demo's behavioral checks without third-party test dependencies."""

from copy import deepcopy
from pathlib import Path
import runpy


def check(calculate_total):
    items = [{"price": 10, "quantity": 3}, {"price": 5, "quantity": 2}]
    original = deepcopy(items)
    assert calculate_total(items) == 40, "Quantities must affect the subtotal"
    assert calculate_total(items, discount_percent=10, tax_percent=5) == 37.8, "Discount the subtotal, then tax the discounted amount"
    assert items == original, "Do not change the input cart"
    assert calculate_total([]) == 0, "Empty cart should total zero"
    assert calculate_total([{"price": 3.33, "quantity": 3}], tax_percent=7) == 10.69, "Round the final total to two decimals"
    assert calculate_total(items, discount_percent=100) == 0, "A 100 percent discount should produce zero"
    print("PASS: quantities, discounts, tax, empty cart, rounding, and unchanged input")

    for bad in (
        [{"price": -1, "quantity": 1}],
        [{"price": 10, "quantity": 0}],
        [{"price": 10, "quantity": -1}],
        [{"price": 10, "quantity": 1.5}],
    ):
        try:
            calculate_total(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for invalid item: {bad}")
    for options in ({"discount_percent": -1}, {"discount_percent": 101}, {"tax_percent": -1}):
        try:
            calculate_total(items, **options)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for invalid percentage: {options}")
    print("PASS: invalid prices, quantities, and percentages are rejected")
    print("ALL CART CHECKS PASSED")


if __name__ == "__main__":
    module = runpy.run_path(str(Path(__file__).with_name("cart.py")))
    check(module["calculate_total"])
