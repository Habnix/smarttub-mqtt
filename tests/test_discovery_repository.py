"""Concurrency and durability tests for the discovery YAML boundary."""

import asyncio

import pytest
import yaml

from src.core.discovery_repository import DiscoveryRepository


@pytest.mark.asyncio
async def test_parallel_repository_updates_do_not_lose_entries(tmp_path):
    path = tmp_path / "discovered_items.yaml"
    repositories = [DiscoveryRepository(path) for _ in range(20)]

    def add_entry(index):
        def update(document):
            entries = list(document.get("entries", []))
            entries.append(index)
            document["entries"] = entries
            return document

        return update

    await asyncio.gather(
        *(
            repository.update_async(add_entry(index))
            for index, repository in enumerate(repositories)
        )
    )

    document = DiscoveryRepository(path).read()
    assert sorted(document["entries"]) == list(range(20))
    assert document["schema_version"] == 1
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == document


@pytest.mark.asyncio
async def test_parallel_reads_never_observe_partial_yaml(tmp_path):
    repository = DiscoveryRepository(tmp_path / "discovered_items.yaml")
    repository.write({"generation": 0, "payload": "initial"})

    async def write_generation(generation):
        await repository.write_async(
            {"generation": generation, "payload": "x" * (generation + 1) * 100}
        )

    async def read_generation():
        document = await repository.read_async()
        assert isinstance(document["generation"], int)
        assert isinstance(document["payload"], str)

    await asyncio.gather(
        *(write_generation(index) for index in range(20)),
        *(read_generation() for _ in range(40)),
    )

    assert not list(tmp_path.glob(".discovered_items.yaml.*.tmp"))


def test_failed_atomic_replace_preserves_previous_document(tmp_path, monkeypatch):
    repository = DiscoveryRepository(tmp_path / "discovered_items.yaml")
    repository.write({"generation": 1})

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr("src.core.discovery_repository.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        repository.write({"generation": 2})

    assert repository.read()["generation"] == 1
    assert not list(tmp_path.glob(".discovered_items.yaml.*.tmp"))


def test_cache_is_shared_by_path_and_returns_detached_documents(tmp_path):
    path = tmp_path / "discovered_items.yaml"
    writer = DiscoveryRepository(path)
    reader = DiscoveryRepository(path)
    writer.write({"discovered_items": {"spa-1": {"lights": []}}})

    cached = reader.cached_discovered_items()
    cached["spa-1"]["lights"].append({"id": "changed-only-in-test"})

    assert reader.cached_discovered_items() == {"spa-1": {"lights": []}}


def test_cached_read_does_not_touch_the_filesystem(tmp_path, monkeypatch):
    repository = DiscoveryRepository(tmp_path / "discovered_items.yaml")
    repository.write({"discovered_items": {"spa-1": {"lights": []}}})

    monkeypatch.setattr(
        repository,
        "read",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected disk read")),
    )

    assert repository.cached_discovered_items() == {"spa-1": {"lights": []}}
