import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Chunk, Repository, RepositorySnapshot, SnapshotStatus


def test_models_create(db_session):
    repository = Repository(owner="tiangolo", name="fastapi")
    db_session.add(repository)
    db_session.flush()

    snapshot = RepositorySnapshot(
        repository_id=repository.id,
        ref_requested="main",
        commit_sha="abc1234567890abcdef1234567890abcdef1234",
        status=SnapshotStatus.PENDING,
    )
    db_session.add(snapshot)
    db_session.flush()

    chunk = Chunk(
        repository_id=repository.id,
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha,
        file_path="fastapi/routing.py",
        chunk_index=0,
        content="def include_router(...): ...",
    )
    db_session.add(chunk)
    db_session.commit()

    assert chunk.repository_id == repository.id
    assert chunk.snapshot_id == snapshot.id
    assert chunk.commit_sha == snapshot.commit_sha


def test_snapshot_unique_per_commit(db_session):
    repository = Repository(owner="octocat", name="hello-world")
    db_session.add(repository)
    db_session.flush()

    commit_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    first_snapshot = RepositorySnapshot(
        repository_id=repository.id,
        ref_requested="main",
        commit_sha=commit_sha,
        status=SnapshotStatus.PENDING,
    )
    db_session.add(first_snapshot)
    db_session.commit()

    duplicate_snapshot = RepositorySnapshot(
        repository_id=repository.id,
        ref_requested="main",
        commit_sha=commit_sha,
        status=SnapshotStatus.READY,
    )
    db_session.add(duplicate_snapshot)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
