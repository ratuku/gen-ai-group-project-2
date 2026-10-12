"""Step 2: import the prepared embeddings into a persistent Chroma database."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from rag_server.prepare import DEFAULT_OUTPUT
from rag_server.storage.chroma import DEFAULT_STORE, build_index


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    options = parser.parse_args(arguments)
    try:
        result = build_index(options.prepared, options.store)
    except Exception as error:
        parser.exit(1, f"Indexing failed: {error}\n")
    print(f"Indexed {result['chunk_count']} chunks using {result['model']}.")
    print(f"Chroma store: {options.store.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
