import re

def unique_words(text):
    words = re.findall(r'[a-zA-Z]+', text)
    seen = set()
    result = []
    for word in words:
        lw = word.lower()
        if lw not in seen:
            seen.add(lw)
            result.append(lw)
    return result
