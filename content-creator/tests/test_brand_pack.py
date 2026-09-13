from pathlib import Path

BRAND_PACK_DIR = Path(__file__).parent.parent / "brands" / "marianabotelho-ig"

REQUIRED_FILES = [
    "tone-of-voice.md",
    "domain-framework.md",
    "quality-criteria.md",
    "anti-patterns.md",
    "output-examples.md",
    "research-brief.md",
]


def test_all_required_brand_files_exist_and_are_nonempty():
    for filename in REQUIRED_FILES:
        path = BRAND_PACK_DIR / filename
        assert path.exists(), f"missing brand file: {filename}"
        assert len(path.read_text(encoding="utf-8").strip()) > 0, f"empty brand file: {filename}"
