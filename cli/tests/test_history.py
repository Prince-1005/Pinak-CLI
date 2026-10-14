"""Integration-ish tests for history DB using an isolated temp SQLite file."""

from pinak import history as history_mod


def test_record_and_query_history(isolated_history_db):
    history_mod.record_download("https://example.com/v1", status="success", mode="media")
    history_mod.record_download("https://example.com/v2", status="failed", mode="audio")

    all_rows = history_mod.get_history("")
    assert len(all_rows) == 2

    assert history_mod.url_downloaded_successfully("https://example.com/v1") is True
    assert history_mod.url_downloaded_successfully("https://example.com/v2") is False


def test_history_filters(isolated_history_db):
    history_mod.record_download("https://example.com/a", status="success", mode="audio")
    history_mod.record_download("https://example.com/b", status="failed", mode="media")

    assert len(history_mod.get_history("failed")) == 1
    assert len(history_mod.get_history("audio")) == 1
    assert len(history_mod.get_history("search example.com/a")) == 1


def test_history_delete(isolated_history_db):
    history_mod.record_download("https://example.com/x", status="success")
    history_mod.record_download("https://example.com/y", status="success")
    ids = history_mod.get_history_ids_desc()
    assert len(ids) == 2

    history_mod.delete_history_by_ids([ids[0]])
    assert len(history_mod.get_history("")) == 1

    history_mod.clear_all_history()
    assert history_mod.get_history("") == []


def test_stats_empty_returns_none(isolated_history_db):
    assert history_mod.get_stats_data() is None


def test_stats_with_data(isolated_history_db, tmp_output_dir):
    import os

    f1 = os.path.join(tmp_output_dir, "v.mp4")
    with open(f1, "wb") as fh:
        fh.write(b"x" * 1024)
    history_mod.record_download("https://example.com/v", status="success", files=[f1], duration=60)
    stats = history_mod.get_stats_data()
    assert stats is not None
    assert stats["total_attempts"] == 1
    assert stats["successes"] == 1
    assert stats["success_rate"] == 100.0


def test_history_recovers_from_corrupt_db(isolated_history_db):
    # Corrupt the database file with invalid header / bytes
    with open(isolated_history_db, "wb") as f:
        f.write(b"NOT A VALID SQLITE DATABASE FILE HEADER")

    # Accessing history should self-heal and create a fresh DB
    history_mod.record_download("https://example.com/healed", status="success")
    rows = history_mod.get_history("")
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.com/healed"


def test_history_graceful_on_total_db_failure(monkeypatch):
    def _boom():
        raise OSError("disk failure")

    monkeypatch.setattr(history_mod, "get_db_connection", _boom)

    # All public history functions must fail gracefully without raising
    history_mod.record_download("https://example.com/fail")
    assert history_mod.url_downloaded_successfully("https://example.com/fail") is False
    assert history_mod.get_history("") == []
    assert history_mod.get_history_ids_desc() == []
    assert history_mod.get_stats_data() is None
    history_mod.delete_history_by_ids([1, 2])
    history_mod.clear_all_history()
