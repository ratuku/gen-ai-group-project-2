def unique_words(text):
    """Return a list of unique ASCII words from *text*.

    A word is defined as a maximal contiguous sequence of ASCII letters
    (``a``–``z`` or ``A``–``Z``).  The comparison is case‑insensitive, but
    the returned words are all lower‑case.  The order of the list follows
    the first appearance of each distinct word in the input string.

    Parameters
    ----------
    text : str
        The input string to process.

    Returns
    -------
    list[str]
        List of unique words in lower‑case, preserving first‑occurrence order.
    """
    if not text:
        return []
    words = []
    current = []
    for ch in text:
        if 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
            current.append(ch.lower())
        else:
            if current:
                word = ''.join(current)
                if word not in words:
                    words.append(word)
                current = []
    # handle last word
    if current:
        word = ''.join(current)
        if word not in words:
            words.append(word)
    return words
