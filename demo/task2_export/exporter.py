"""Order export feature to implement during the demo."""

from json import dumps
from pathlib import Path


def export_orders(orders, output_directory):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    exported_paths = []
    for order in orders:
        order_id = order["id"]
        if (
            not isinstance(order_id, str)
            or not order_id
            or order_id.strip() != order_id
            or order_id in {".", ".."}
            or any(ch.isspace() for ch in order_id)
            or any(sep in order_id for sep in ("/", "\\"))
            or any(part == ".." for part in Path(order_id).parts)
        ):
            raise ValueError("Invalid order id")
        path = output_directory / f"{order_id}.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(dumps(order, ensure_ascii=False), encoding="utf-8")
        exported_paths.append(path)
    return exported_paths
