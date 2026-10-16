from pathlib import Path

def write_greeting(path, name):
    p = Path(path)
    text = f"Hello, {name}!\n"
    count = p.write_text(text, encoding='utf-8')
    return count
