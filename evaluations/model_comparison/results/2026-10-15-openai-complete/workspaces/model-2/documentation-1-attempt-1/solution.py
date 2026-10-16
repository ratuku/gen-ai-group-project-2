from pathlib import Path

def write_greeting(path, name):
    greeting = f"Hello, {name}!\n"
    return Path(path).write_text(greeting, encoding="utf-8")
