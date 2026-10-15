def unique_words(text):
    """Return a list of unique ASCII words in *text*.

    Words are defined as maximal runs of ASCII letters (a‑z, case‑insensitive).
    The function lower‑cases each word and returns them in the order of their
    first appearance, discarding duplicates. Non‑letter characters (digits,
    punctuation, whitespace, etc.) act as separators. An empty input yields an
    empty list.
    """
    import re
    # Find all sequences of ASCII letters
    words = re.findall(r"[A-Za-z]+", text)
    seen = set()
    unique = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            unique.append(lw)
    return unique
