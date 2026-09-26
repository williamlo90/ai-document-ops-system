from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import subprocess


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def assert_clean_worktree() -> None:
    status = git_output(
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        "Dockerfile",
        ".dockerignore",
        "requirements.txt",
        "backend",
        "frontend",
        "examples",
        "scripts/postgres_migrate.py",
    )
    if status:
        raise RuntimeError(
            "Release images require clean container build inputs so the OCI revision maps to "
            "exactly one commit."
        )


def source_url() -> str:
    remote = git_output("remote", "get-url", "origin")
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote.removeprefix("git@github.com:")
    return remote.removesuffix(".git")


def build_release_image(tag: str | None = None) -> tuple[str, str]:
    assert_clean_worktree()
    revision = git_output("rev-parse", "HEAD")
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    resolved_tag = tag or f"ai-document-ops-system:{revision}"
    subprocess.run(
        [
            "docker",
            "build",
            "--build-arg",
            f"BUILD_CREATED_AT={created_at}",
            "--build-arg",
            f"SOURCE_REVISION={revision}",
            "--build-arg",
            f"SOURCE_URL={source_url()}",
            "--tag",
            resolved_tag,
            ".",
        ],
        check=True,
    )
    metadata = json.loads(
        subprocess.check_output(["docker", "image", "inspect", resolved_tag], text=True)
    )[0]
    labels = metadata["Config"]["Labels"]
    if labels.get("org.opencontainers.image.revision") != revision:
        raise RuntimeError("Built image revision label does not match HEAD.")
    return resolved_tag, metadata["Id"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a revision-labelled release image from a clean Git worktree."
    )
    parser.add_argument("--tag", help="Optional immutable image tag; defaults to the full Git SHA.")
    args = parser.parse_args()
    try:
        tag, image_id = build_release_image(args.tag)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"Image: {tag}")
    print(f"Image ID: {image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
