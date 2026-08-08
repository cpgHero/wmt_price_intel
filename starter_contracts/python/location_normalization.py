"""Reference normalization behavior. Keep raw values in production."""
import re

def normalize_us_zip(raw: str | None, country: str | None) -> str | None:
    if raw is None:
        return None
    z = str(raw).strip()
    c = (country or "").strip().upper()
    if c in {"USA","US","UNITED STATES","PUERTO RICO","PR"} and re.fullmatch(r"\d{1,4}", z):
        return z.zfill(5)
    return z or None

def normalize_identifier(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
