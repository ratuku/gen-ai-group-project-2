"""Fixed coding tasks and evaluator-owned checks for issue #14."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    name: str
    prompt: str
    source: str
    checks: str
    required_tools: tuple[str, ...] = ()


TASKS = (
    Task(
        "bugfix",
        "Fix average() in solution.py: return the arithmetic mean for nonempty "
        "numeric sequences, and raise ValueError for an empty sequence. Preserve "
        "the public function name. Read the existing code before editing it.",
        "def average(values):\n    return sum(values) / (len(values) - 1)\n",
        "assert s['average']([2, 4, 6]) == 4\n"
        "assert s['average']([5]) == 5\n"
        "assert s['average']([-4, 0, 1]) == -1\n"
        "assert s['average']((1.5, 2.5)) == 2\n"
        "try:\n    s['average']([])\nexcept ValueError:\n    pass\n"
        "else:\n    raise AssertionError('empty input must raise ValueError')\n",
    ),
    Task(
        "feature",
        "Implement unique_words(text) in solution.py. Return lowercase unique "
        "ASCII words in order of first appearance. A word is a maximal run of "
        "ASCII letters a-z, ignoring case; digits and punctuation separate words. "
        "Empty input returns an empty list. Read the existing code before editing.",
        "def unique_words(text):\n    raise NotImplementedError\n",
        "assert s['unique_words']('Hello, HELLO world!') == ['hello', 'world']\n"
        "assert s['unique_words']('b a b C a') == ['b', 'a', 'c']\n"
        "assert s['unique_words']('abc123DEF x_y') == ['abc', 'def', 'x', 'y']\n"
        "assert s['unique_words']('') == []\n"
        "assert s['unique_words']('123 !?') == []\n"
        "assert s['unique_words']('café K İ hello') == ['caf', 'hello']\n",
    ),
    Task(
        "refactor",
        "Refactor summarize_sales(rows) in solution.py to remove the duplicated "
        "region aggregation using a shared helper. Preserve its output format "
        "and behavior for any region, empty rows, negative and fractional amounts. "
        "Keep the summarize_sales public API. Read existing code before editing.",
        "def summarize_sales(rows):\n"
        "    north = sum(r['amount'] for r in rows if r['region'] == 'north')\n"
        "    south = sum(r['amount'] for r in rows if r['region'] == 'south')\n"
        "    other = {}\n"
        "    for row in rows:\n"
        "        if row['region'] not in ('north', 'south'):\n"
        "            other[row['region']] = other.get(row['region'], 0) + row['amount']\n"
        "    return {'north': north, 'south': south, **other}\n",
        "f = s['summarize_sales']\n"
        "assert f([]) == {'north': 0, 'south': 0}\n"
        "rows = [{'region': 'north', 'amount': 2}, {'region': 'north', 'amount': -1}, "
        "{'region': 'west', 'amount': 1.5}, {'region': 'west', 'amount': 2.5}]\n"
        "import copy\noriginal = copy.deepcopy(rows)\n"
        "assert f(rows) == {'north': 1, 'south': 0, 'west': 4}\n"
        "assert rows == original\n"
        "import ast\ntree = ast.parse(source)\n"
        "assert len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda))]) >= 2, 'shared helper missing'\n",
    ),
    Task(
        "documentation",
        "Implement write_greeting(path, name) in solution.py using pathlib: write "
        "exactly 'Hello, {name}!\\n' as UTF-8 and return the character count returned "
        "by Path.write_text. Before editing, use rag.search_docs for Path.write_text "
        "and an available DeepWiki tool to research pathlib usage in the public "
        "python/cpython repository. Summarize what the retrieved sources support "
        "in your final answer, including source identifiers. Read existing code.",
        "def write_greeting(path, name):\n    raise NotImplementedError\n",
        "from pathlib import Path\nimport tempfile\n"
        "with tempfile.TemporaryDirectory() as directory:\n"
        "    p = Path(directory) / 'greeting.txt'\n"
        "    assert s['write_greeting'](p, 'Ada') == 12\n"
        "    assert p.read_text(encoding='utf-8') == 'Hello, Ada!\\n'\n"
        "    assert s['write_greeting'](str(p), 'Zoë') == 12\n"
        "    assert p.read_text(encoding='utf-8') == 'Hello, Zoë!\\n'\n",
        ("rag.search_docs", "deepwiki."),
    ),
)
