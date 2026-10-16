"""Check exported files inside a temporary directory that is cleaned up afterward."""

from copy import deepcopy
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory


def check(export_orders):
    orders = [
        {"id": "A100", "customer": "Zo\u00eb", "total": 37.8},
        {"id": "B-200", "customer": "Andr\u00e9", "total": 10.69},
    ]
    original = deepcopy(orders)
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        destination = root / "nested" / "orders"
        paths = export_orders(orders, destination)
        assert paths == [destination / "A100.json", destination / "B-200.json"], "Return Path objects in input order"
        for path, order in zip(paths, orders, strict=True):
            text = path.read_text(encoding="utf-8")
            assert json.loads(text) == order, "Each JSON file must contain the full original order"
            assert order["customer"] in text, "Keep Unicode characters readable instead of ASCII escapes"
        assert orders == original, "Do not change input orders"
        print("PASS: nested directories, JSON contents, Unicode, returned paths, and unchanged inputs")

        empty_destination = root / "empty"
        assert export_orders([], str(empty_destination)) == []
        assert empty_destination.is_dir(), "Create the output directory even for no orders"
        print("PASS: empty orders and string directory paths")

        saved = paths[0].read_bytes()
        try:
            export_orders([{"id": "A100", "customer": "Replacement", "total": 0}], destination)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing files must raise FileExistsError")
        assert paths[0].read_bytes() == saved, "Existing order was overwritten"
        print("PASS: existing exports are preserved")

        for bad_id in ("", "../escape", "folder/order", "space here"):
            try:
                export_orders([{"id": bad_id, "customer": "Test", "total": 1}], root / "invalid")
            except ValueError:
                pass
            else:
                raise AssertionError(f"Expected ValueError for invalid ID: {bad_id!r}")
        print("PASS: invalid order IDs are rejected")
    print("ALL EXPORT CHECKS PASSED")


if __name__ == "__main__":
    module = runpy.run_path(str(Path(__file__).with_name("exporter.py")))
    check(module["export_orders"])
