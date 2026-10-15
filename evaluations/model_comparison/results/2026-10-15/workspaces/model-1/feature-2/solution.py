def unique_words(text):
    # Extract ASCII words and return unique lowercase ones in order of first appearance
    import re
    words = re.findall(r'[A-Za-z]+', text)
    seen = set()
    unique = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            unique.append(lw)
    return unique
