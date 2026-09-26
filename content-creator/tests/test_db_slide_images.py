import pytest
import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


@pytest.fixture
def idea(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    return db.get_idea(conn, idea_id)


def test_new_idea_has_no_image_folder(idea):
    assert idea["image_folder"] is None


def test_set_and_read_image_folder(conn, idea):
    db.set_idea_image_folder(conn, idea["id"], "2026-09-13_ritual-matinal")
    assert db.get_idea(conn, idea["id"])["image_folder"] == "2026-09-13_ritual-matinal"


def test_create_and_get_slide_image(conn, idea):
    slide_image_id = db.create_slide_image(
        conn, idea["id"], 0, "um prompt", "C:\\fake\\slide-00.png", 0.07,
    )
    row = db.get_slide_image(conn, slide_image_id)
    assert row["idea_id"] == idea["id"]
    assert row["slide_index"] == 0
    assert row["prompt"] == "um prompt"
    assert row["file_path"] == "C:\\fake\\slide-00.png"
    assert row["cost_usd"] == pytest.approx(0.07)
    assert row["status"] == "pending"


def test_update_slide_image_status(conn, idea):
    slide_image_id = db.create_slide_image(conn, idea["id"], 0, "p", "f.png", 0.07)
    db.update_slide_image_status(conn, slide_image_id, "approved")
    assert db.get_slide_image(conn, slide_image_id)["status"] == "approved"


def test_list_slide_images_returns_every_attempt(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p1", "f1.png", 0.07)
    db.create_slide_image(conn, idea["id"], 0, "p2", "f2.png", 0.07)
    rows = db.list_slide_images(conn, idea["id"])
    assert len(rows) == 2


def test_get_latest_slide_images_returns_one_row_per_slide(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p1", "f1.png", 0.07)
    db.create_slide_image(conn, idea["id"], 0, "p2", "f2.png", 0.07)
    db.create_slide_image(conn, idea["id"], 1, "p3", "f3.png", 0.07)
    latest = db.get_latest_slide_images(conn, idea["id"])
    assert [row["slide_index"] for row in latest] == [0, 1]
    assert latest[0]["prompt"] == "p2"  # the most recent attempt for slide 0


def test_hard_delete_idea_removes_slide_images(conn, idea):
    db.create_slide_image(conn, idea["id"], 0, "p", "f.png", 0.07)
    db.archive_idea(conn, idea["id"])
    db.hard_delete_idea(conn, idea["id"])
    assert db.list_slide_images(conn, idea["id"]) == []


def test_init_db_adds_text_overflow_to_an_existing_slide_images_table(tmp_path):
    connection = db.get_connection(str(tmp_path / "old.db"))
    connection.execute(
        "CREATE TABLE slide_images (id INTEGER PRIMARY KEY, idea_id INTEGER NOT NULL, "
        "slide_index INTEGER NOT NULL, prompt TEXT NOT NULL, file_path TEXT NOT NULL, "
        "cost_usd REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO slide_images (idea_id, slide_index, prompt, file_path, cost_usd, created_at) "
        "VALUES (1, 0, 'p', 'f.png', 0.07, '2026-09-01')"
    )
    db.init_db(connection)
    db.init_db(connection)  # idempotent
    assert connection.execute("SELECT text_overflow FROM slide_images").fetchone()[0] == 0


def test_create_slide_image_stores_text_overflow(conn, idea):
    slide_image_id = db.create_slide_image(conn, idea["id"], 0, "p", "f.png", 0.07, text_overflow=True)
    assert db.get_slide_image(conn, slide_image_id)["text_overflow"] == 1
