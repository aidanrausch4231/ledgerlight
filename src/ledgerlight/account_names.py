"""Account display names shared by import and the one-time legacy migration."""

import re
import unicodedata


def clean_account_name(raw, fallback):
    def clean(value):
        text = "".join(
            char
            for char in (value or "")
            if char != "\ufffd" and unicodedata.category(char) not in {"Cc", "Cf"}
        )
        text = " ".join(text.split())
        if text.isupper() and sum(char.isalpha() for char in text) > 3:
            # Title each alphabetic run, including those on either side of digits.
            text = re.sub(r"[^\W\d_]+", lambda match: match[0].title(), text)
        return text

    return clean(raw) or clean(fallback)


def account_name_fallback(subtype=None, mask=None):
    return f"{(subtype or 'Account').title()} ••{mask or ''}"
