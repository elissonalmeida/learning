import storage


def test_slugify_handles_accents_and_spaces():
    assert storage.slugify("Ritual Matinal com Óleo de Lavanda") == "ritual-matinal-com-oleo-de-lavanda"


def test_slugify_strips_punctuation():
    assert storage.slugify("3 sinais! (importante)") == "3-sinais-importante"


def test_make_carousel_folder_returns_date_and_slug(tmp_path):
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal"


def test_make_carousel_folder_appends_suffix_on_collision(tmp_path):
    (tmp_path / "2026-09-13_ritual-matinal").mkdir()
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal_2"


def test_make_carousel_folder_increments_past_multiple_collisions(tmp_path):
    (tmp_path / "2026-09-13_ritual-matinal").mkdir()
    (tmp_path / "2026-09-13_ritual-matinal_2").mkdir()
    name = storage.make_carousel_folder(tmp_path, "Ritual Matinal", "2026-09-13")
    assert name == "2026-09-13_ritual-matinal_3"


def test_images_root_is_sibling_of_db_file():
    root = storage.images_root(r"C:\Users\Elisson\Dropbox\learning\aura\mariana_content.db")
    assert str(root) == r"C:\Users\Elisson\Dropbox\learning\aura\images"


def test_make_carousel_folder_caps_long_topics(tmp_path):
    name = storage.make_carousel_folder(tmp_path, "palavra " * 60, "2026-09-25")
    assert len(name) <= 70
    assert not name.endswith("-")
    assert name.startswith("2026-09-25_palavra-palavra")


def test_is_valid_folder_name_rejects_overlong_legacy_names():
    assert storage.is_valid_folder_name("2026-09-13_ritual-matinal")
    assert storage.is_valid_folder_name("2026-09-13_ritual-matinal_2")
    assert not storage.is_valid_folder_name("2026-09-25_" + "a" * 200)
