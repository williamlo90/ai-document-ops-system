from __future__ import annotations

import argparse
from http.client import HTTPException
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4


POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
)


def docker(*args: str, capture: bool = False) -> str:
    completed = subprocess.run(
        ["docker", *args],
        check=True,
        text=True,
        capture_output=capture,
    )
    if not capture:
        return ""
    return "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())


def wait_for_postgres(container: str, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "docintel", "-d", "docintel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready in time.")


def http_status(url: str) -> int | None:
    try:
        with urlopen(url, timeout=3) as response:  # noqa: S310 - fixed localhost smoke URL
            return response.status
    except HTTPError as exc:
        return exc.code
    except (HTTPException, OSError, URLError):
        return None


def wait_for_status(url: str, expected: int, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        last_status = http_status(url)
        if last_status == expected:
            return
        time.sleep(0.5)
    raise RuntimeError(f"{url} returned {last_status!r}, expected {expected}.")


def secure_runtime_args() -> list[str]:
    return [
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,uid=100,gid=101,mode=1770,size=64m",
        "--tmpfs",
        "/data:rw,noexec,nosuid,uid=100,gid=101,mode=1770,size=64m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
    ]


def application_environment(database_url: str) -> list[str]:
    values = {
        "APP_ENV": "local",
        "APP_ADMIN_TOKEN": "runtime-smoke-admin",
        "APP_METRICS_TOKEN": "runtime-smoke-metrics",
        "APP_UPLOADER_TOKEN": "runtime-smoke-uploader",
        "APP_REVIEWER_TOKEN": "runtime-smoke-reviewer",
        "DATABASE_URL": database_url,
        "DOCUMENT_STORAGE_BACKEND": "local",
        "MALWARE_SCANNER_BACKEND": "signature",
        "MALWARE_SCANNING_ENABLED": "true",
        "PROCESSING_QUEUE_BACKEND": "none",
        "SQLITE_PATH": "/data/doc_intel.sqlite3",
        "STORAGE_BACKEND": "postgres",
        "UPLOAD_ROOT": "/data/uploads",
        "WORKER_MAX_IDLE_POLL_SECONDS": "1",
        "WORKER_POLL_SECONDS": "0.2",
    }
    args: list[str] = []
    for key, value in values.items():
        args.extend(("--env", f"{key}={value}"))
    return args


def inspect_container(name: str) -> dict[str, object]:
    return json.loads(docker("inspect", name, capture=True))[0]


def assert_hardened(name: str) -> None:
    inspection = inspect_container(name)
    host_config = inspection["HostConfig"]
    if not host_config["ReadonlyRootfs"]:
        raise RuntimeError(f"{name} does not use a read-only root filesystem.")
    if "ALL" not in (host_config["CapDrop"] or []):
        raise RuntimeError(f"{name} does not drop all Linux capabilities.")
    if "no-new-privileges:true" not in (host_config["SecurityOpt"] or []):
        raise RuntimeError(f"{name} does not enable no-new-privileges.")


def assert_exit_zero(name: str) -> None:
    inspection = inspect_container(name)
    exit_code = inspection["State"]["ExitCode"]
    if exit_code != 0:
        logs = docker("logs", name, capture=True)
        raise RuntimeError(f"{name} exited with {exit_code}.\n{logs}")


def assert_image_contract(image: str, expected_revision: str | None) -> None:
    inspection = json.loads(docker("image", "inspect", image, capture=True))[0]
    if inspection["Config"]["User"] != "docintel":
        raise RuntimeError("Runtime image must use the docintel non-root user.")
    labels = inspection["Config"]["Labels"] or {}
    required = {
        "org.opencontainers.image.created",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.source",
    }
    missing = sorted(required - labels.keys())
    if missing:
        raise RuntimeError(f"Runtime image is missing OCI labels: {', '.join(missing)}")
    if expected_revision and labels["org.opencontainers.image.revision"] != expected_revision:
        raise RuntimeError("Runtime image revision label does not match the expected Git commit.")


def run_smoke(image: str, expected_revision: str | None = None) -> None:
    suffix = uuid4().hex[:10]
    network = f"docintel-runtime-{suffix}"
    postgres = f"docintel-postgres-{suffix}"
    api = f"docintel-api-{suffix}"
    worker = f"docintel-worker-{suffix}"
    containers = [worker, api, postgres]
    database_url = f"postgresql://docintel:runtime-smoke@{postgres}:5432/docintel"
    docker("network", "create", network)
    try:
        assert_image_contract(image, expected_revision)
        docker(
            "run",
            "--detach",
            "--name",
            postgres,
            "--network",
            network,
            "--env",
            "POSTGRES_DB=docintel",
            "--env",
            "POSTGRES_USER=docintel",
            "--env",
            "POSTGRES_PASSWORD=runtime-smoke",
            "--tmpfs",
            "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m",
            POSTGRES_IMAGE,
        )
        wait_for_postgres(postgres)

        migration_args = [
            "run",
            "--rm",
            "--network",
            network,
            *secure_runtime_args(),
            "--env",
            f"DATABASE_URL={database_url}",
            image,
            "python",
            "scripts/postgres_migrate.py",
        ]
        docker(*migration_args)
        second_migration = docker(*migration_args, capture=True)
        if "Applied: none" not in second_migration:
            raise RuntimeError("The migration command is not idempotent.")

        docker(
            "run",
            "--detach",
            "--name",
            api,
            "--network",
            network,
            "--publish",
            "127.0.0.1::8000",
            *secure_runtime_args(),
            *application_environment(database_url),
            image,
        )
        assert_hardened(api)
        port = docker("port", api, "8000/tcp", capture=True).rsplit(":", 1)[1]
        base_url = f"http://127.0.0.1:{port}"
        try:
            wait_for_status(f"{base_url}/health", 200)
        except RuntimeError as exc:
            logs = docker("logs", api, capture=True)
            raise RuntimeError(f"API did not start.\n{logs}") from exc
        wait_for_status(f"{base_url}/ready", 200)

        docker("stop", "--timeout", "10", postgres)
        wait_for_status(f"{base_url}/ready", 503)
        wait_for_status(f"{base_url}/health", 200)

        docker("stop", "--timeout", "15", api)
        assert_exit_zero(api)

        docker("start", postgres)
        wait_for_postgres(postgres)
        docker(*migration_args)
        docker(
            "run",
            "--detach",
            "--name",
            worker,
            "--network",
            network,
            *secure_runtime_args(),
            *application_environment(database_url),
            image,
            "python",
            "-m",
            "app.worker_loop",
        )
        assert_hardened(worker)
        time.sleep(2)
        docker("stop", "--timeout", "15", worker)
        assert_exit_zero(worker)
    finally:
        for container in containers:
            subprocess.run(
                ["docker", "rm", "--force", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(
            ["docker", "network", "rm", network],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify API, worker, and migration modes of one hardened runtime image."
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    run_smoke(args.image, args.expected_revision)
    print("Container runtime smoke: API, worker, migration, readiness, and SIGTERM passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
