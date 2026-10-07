"""Regression contracts for public releases and isolated private builds."""

from pathlib import Path

import yaml

from src.core.version import __version__

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_IMAGE = "willnix/smarttub-mqtt"
PRIVATE_IMAGE = "${{ vars.GITEA_IMAGE }}"
PRIVATE_COMPOSE_IMAGE = "${SMARTTUB_PRIVATE_IMAGE:?Set SMARTTUB_PRIVATE_IMAGE to your private development image}"


def _workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def test_compose_pins_public_release_and_preserves_private_override() -> None:
    service = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"][
        "smarttub-mqtt"
    ]
    assert service["image"] == f"{PUBLIC_IMAGE}:{__version__}"
    assert service["restart"] == "unless-stopped"
    private = yaml.safe_load((ROOT / "docker-compose.gitea.yml").read_text())
    assert private["services"]["smarttub-mqtt"]["image"] == PRIVATE_COMPOSE_IMAGE
    local = yaml.safe_load((ROOT / "docker-compose.local.yml").read_text())
    assert local["services"]["smarttub-mqtt"]["build"]["args"]["APP_VERSION"] == (
        __version__
    )


def test_public_release_is_gated_by_ci_and_credentials() -> None:
    release = _workflow("release.yml")
    jobs = release["jobs"]
    assert jobs["preflight"]["if"] == "github.server_url == 'https://github.com'"
    assert jobs["checks"]["needs"] == "preflight"
    assert jobs["checks"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["docker-release"]["needs"] == "checks"
    preflight = jobs["preflight"]["steps"][-1]
    assert set(preflight["env"]) == {
        "DOCKERHUB_USERNAME",
        "DOCKERHUB_TOKEN",
        "COSIGN_PRIVATE_KEY",
    }
    assert 'test "$tag_version" = "$source_version"' in preflight["run"]
    assert "refs/tags/v*" in preflight["run"]
    # PyYAML's YAML 1.1 loader reads the GitHub key 'on' as boolean True.
    ci = _workflow("ci.yml")
    assert "workflow_call" in ci[True]


def test_signing_key_validation_precedes_multiplatform_push() -> None:
    steps = _workflow("release.yml")["jobs"]["docker-release"]["steps"]
    build_index = next(i for i, step in enumerate(steps) if step.get("id") == "build")
    key_index = next(
        i for i, step in enumerate(steps) if "cosign public-key" in step.get("run", "")
    )
    qemu_index = next(
        i for i, step in enumerate(steps) if "setup-qemu-action" in step.get("uses", "")
    )
    assert key_index < build_index
    assert qemu_index < build_index
    build = steps[build_index]["with"]
    assert build["platforms"] == "linux/amd64,linux/arm64"
    assert build["sbom"] is True
    assert build["provenance"] == "mode=max"
    login = next(step for step in steps if "login-action" in step.get("uses", ""))
    assert "registry" not in login["with"]  # Docker Hub is the login default.
    assert login["with"]["password"] == "${{ secrets.DOCKERHUB_TOKEN }}"
    meta = next(step for step in steps if step.get("id") == "meta")["with"]
    assert meta["images"] == PUBLIC_IMAGE
    assert "type=raw,value=latest" in meta["tags"]
    sign = next(step for step in steps if "cosign sign" in step.get("run", ""))
    assert PUBLIC_IMAGE in sign["run"]
    assert PRIVATE_IMAGE not in sign["run"]


def test_main_publish_is_private_only_and_follows_checks() -> None:
    publish = _workflow("ci.yml")["jobs"]["docker-publish"]
    assert "github.server_url != 'https://github.com'" in publish["if"]
    assert "github.ref == 'refs/heads/main'" in publish["if"]
    assert set(publish["needs"]) == {"lint", "browser-smoke", "docker", "security"}
    steps = publish["steps"]
    validation_index = next(
        i
        for i, step in enumerate(steps)
        if step["name"] == "Validate private registry configuration"
    )
    login_index = next(
        i for i, step in enumerate(steps) if "login-action" in step.get("uses", "")
    )
    assert validation_index < login_index
    assert steps[login_index]["with"]["registry"] == "${{ vars.GITEA_REGISTRY }}"
    assert steps[validation_index]["env"] == {
        "REGISTRY_HOST": "${{ vars.GITEA_REGISTRY }}",
        "IMAGE_NAME": PRIVATE_IMAGE,
    }
    assert '"$REGISTRY_HOST/"*' in steps[validation_index]["run"]
    build = next(
        step for step in publish["steps"] if "build-push-action" in step.get("uses", "")
    )
    assert build["with"]["tags"] == f"{PRIVATE_IMAGE}:edge"


def test_release_notes_and_container_docs_match_version() -> None:
    release = _workflow("release.yml")["jobs"]["github-release"]
    assert release["needs"] == "docker-release"
    notes = next(
        step for step in release["steps"] if "RELEASE_VERSION" in step.get("env", {})
    )
    assert "Missing changelog section" in notes["run"]
    assert "body_path" in release["steps"][-1]["with"]
    assert release["steps"][-1]["with"]["files"] == "cosign.pub"
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text()
    for name in ("README.md", "docs/dockerhub.md"):
        text = (ROOT / name).read_text()
        assert f"{PUBLIC_IMAGE}:{__version__}" in text
    assert len((ROOT / "docs/dockerhub.md").read_bytes()) < 25000
