def unique_words(text):
    # Return a list of unique ASCII words in lowercase, preserving first occurrence order.
    # A word is defined as a maximal consecutive sequence of ASCII letters (a-z, case‑insensitive).
    # Non‑letter characters (including digits, punctuation, whitespace) act as separators.
    if not text:
        return []
    result = []
    seen = set()
    word_chars = []
    for ch in text:
        # Check if character is an ASCII letter
        if 'a' <= ch.lower() <= 'z':
            word_chars.append(ch.lower())
        else:
            if word_chars:
                word = ''.join(word_chars)
                if word not in seen:
                    seen.add(word)
                    result.append(word)
                word_chars = []
    # Handle trailing word
    if word_chars:
        word = ''.join(word_chars)
        if word not in seen:
            seen.add(word)
            result.append(word)
    return result
