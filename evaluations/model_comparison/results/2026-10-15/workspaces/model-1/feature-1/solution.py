def unique_words(text):
    """Return a list of unique lowercase ASCII words from *text*.

    A word is defined as a maximal run of ASCII letters (a–z or A–Z).
    Digits and punctuation act as word boundaries.  The returned list
    preserves the order of first appearance in the input string.

    Parameters
    ----------
    text : str
        Input text to process.

    Returns
    -------
    list[str]
        Lower‑case unique words.
    """
    import re

    # If input is empty or None, return an empty list
    if not text:
        return []

    # Find all maximal letter runs (case insensitive) using a regular expression
    # The pattern [A-Za-z]+ matches one or more ASCII letters.
    words = re.findall(r"[A-Za-z]+", text)
    seen = set()
    unique = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            unique.append(lw)
    return unique
