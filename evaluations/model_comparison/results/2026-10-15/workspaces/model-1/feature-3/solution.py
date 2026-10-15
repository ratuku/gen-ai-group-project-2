def unique_words(text):
    import re
    # Find all maximal runs of ASCII letters (case-insensitive)
    words = re.findall(r"[A-Za-z]+", text)
    seen = set()
    result = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            result.append(lw)
    return result
