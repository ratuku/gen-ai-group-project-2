"""Explicitly restore the two demo implementation files before another take.

This overwrites edits in cart.py and exporter.py. Check scripts are unchanged.
"""

from pathlib import Path


STARTERS = {
    "task1_cart/cart.py": '''"""Shopping cart calculator with intentionally broken calculations."""


def calculate_total(items, discount_percent=0, tax_percent=0):
    subtotal = sum(item["price"] for item in items)
    return round(subtotal - discount_percent + tax_percent, 2)
''',
    "task2_export/exporter.py": '''"""Order export feature to implement during the demo."""


def export_orders(orders, output_directory):
    raise NotImplementedError("Implement JSON order export using pathlib")
''',
}


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for relative, source in STARTERS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        print(f"Restored {path}")
