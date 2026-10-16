def unique_words(text):
    words = []
    current_word = []
    seen = set()
    for ch in text:
        # Check if character is an ASCII letter
        if 'a' <= ch.lower() <= 'z':
            current_word.append(ch.lower())
        else:
            if current_word:
                word = ''.join(current_word)
                if word not in seen:
                    seen.add(word)
                    words.append(word)
                current_word = []
    # Last word check
    if current_word:
        word = ''.join(current_word)
        if word not in seen:
            seen.add(word)
            words.append(word)
    return words
