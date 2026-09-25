import re
import unicodedata
from pathlib import Path


def images_root(db_path):
    """Images live in an 'images' folder alongside the database file, in the
    same Dropbox-synced tree, so they get backed up the same way the DB is."""
    return Path(db_path).parent / "images"


MAX_SLUG_LEN = 50  # keeps folder paths well under the Windows 260-char limit


def slugify(text):
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def make_carousel_folder(root, topic, date_str):
    """Return a unique folder name '<date_str>_<topic-slug>' under root,
    appending a numeric suffix on collision. Does not create the directory."""
    slug = slugify(topic)[:MAX_SLUG_LEN].strip("-")
    base = f"{date_str}_{slug}"
    candidate = base
    suffix = 2
    while (Path(root) / candidate).exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def is_valid_folder_name(folder):
    """False for names longer than make_carousel_folder can produce (saved by an older version)."""
    return len(folder) <= len("2026-09-13_") + MAX_SLUG_LEN + len("_99")
