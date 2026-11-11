"""Unit tests for startup scanning, duplicate protection, and file queue progression."""

from pathlib import Path

from src.checkpoint import (
    init_checkpoint_db,
    is_file_already_completed,
    record_file_history,
)
from src.file_detector import compute_file_sha256
from src.queue_manager import enqueue_file_if_new, execute_startup_scan, pop_next_queued_file


def test_startup_scan_enqueues_eligible_files_and_skips_completed_duplicates(
    tmp_path: Path,
) -> None:
    """Verify startup scan picks up existing files while respecting completion history."""
    db_path = tmp_path / "checkpoints" / "test.db"
    init_checkpoint_db(db_path)

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    # File 1: New file
    file1 = input_dir / "new_transactions.csv"
    file1.write_text("Consumer Number,Bank / Service,Date\n1001,HBL,2026-11-10\n", encoding="utf-8")

    # File 2: Pre-completed duplicate file
    file2 = input_dir / "already_done.csv"
    file2.write_text(
        "Consumer Number,Bank / Service,Date\n2002,MEEZAN,2026-11-05\n", encoding="utf-8"
    )
    hash2 = compute_file_sha256(file2)
    record_file_history(db_path, hash2, file2.name, str(file2), "COMPLETED")
    assert is_file_already_completed(db_path, hash2) is True

    enqueued = execute_startup_scan(input_dir, db_path)
    enqueued_names = [p.name for p in enqueued]

    assert "new_transactions.csv" in enqueued_names
    assert "already_done.csv" not in enqueued_names


def test_queue_enqueue_and_fifo_popping(tmp_path: Path) -> None:
    """Verify queue accepts new paths and dispenses them in First-In-First-Out order."""
    f1 = tmp_path / "a.csv"
    f2 = tmp_path / "b.csv"
    f1.touch()
    f2.touch()

    # Clear queue state
    while pop_next_queued_file() is not None:
        pass

    assert enqueue_file_if_new(f1) is True
    assert enqueue_file_if_new(f1) is False  # Duplicate in queue ignored
    assert enqueue_file_if_new(f2) is True

    first = pop_next_queued_file()
    second = pop_next_queued_file()
    third = pop_next_queued_file()

    assert first == f1
    assert second == f2
    assert third is None
