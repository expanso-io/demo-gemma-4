#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "beautifulsoup4>=4.12,<5",
#   "jsonschema>=4.23,<5",
#   "playwright==1.55.0",
#   "pyyaml>=6,<7",
#   "rust-just==1.56.0",
# ]
# ///
"""Enforce the public example bar and write durable Markdown/JSON evidence.

    uv run -s .demo-kit/public-bar.py \
      --repo . \
      --manifest public-bar.toml \
      --report artifacts/public-bar.md

The static lane validates the manifest, pipeline fixtures, platform claims,
published structure and `just up` / `just down` lifecycle, browser declarations,
and retained-feature baseline. The
browser lane is added to the same command by ``--lane all`` or run on its own
with ``--lane browser``. Every invocation writes its report, including failed
and incomplete runs.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator


PUBLIC_BAR_VERSION = "1.2.2"
CRITERIA = {
    1: "Runs",
    2: "Platform",
    3: "Structure",
    4: "Usability",
    5: "Regressions",
}
YAML_SUFFIXES = {".yaml", ".yml"}
TEXT_SUFFIXES = {".md", ".html", ".htm", ".yaml", ".yml", ".toml"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "artifacts",
    "test-results",
    "__pycache__",
    ".demo-kit",
}
PLATFORM_TERMS = {
    "kubernetes": re.compile(r"\bkubernetes\b|\bk8s\b", re.I),
    "openshift": re.compile(r"\bopenshift\b", re.I),
    "kafka": re.compile(r"\bkafka\b", re.I),
    "mqtt": re.compile(r"\bmqtt\b", re.I),
    "prometheus": re.compile(r"\bprometheus(?:-compatible)?\b", re.I),
    "aws": re.compile(r"\baws\b|amazon web services", re.I),
    "azure": re.compile(r"\bazure\b", re.I),
    "gcp": re.compile(r"\bgcp\b|google cloud", re.I),
    "regulated": re.compile(
        r"\bregulated\b|\bhipaa\b|\bfedramp\b|\bitar\b|\bcjis\b", re.I
    ),
}
PLACEHOLDER = re.compile(
    r"(?:example\.(?:com|org|net)|change[-_]?me|your[-_](?:host|bucket|project)|"
    r"<[^>]+>|\bTODO\b|\bTBD\b)",
    re.I,
)
IMAGE = re.compile(r"^([^\s@]+)(?::([^\s@/]+))?(?:@sha256:[0-9a-f]{64})?$")
JUSTFILE_NAMES = {"justfile", ".justfile"}
LIFECYCLE_RECIPES = ("up", "down")
# A README command that runs one of these scripts directly is a raw launcher:
# start and stop go through `just up` and `just down` instead.
SCRIPT_SUFFIXES = (".sh", ".bash", ".py", ".js", ".mjs", ".ts")
SCRIPT_WRAPPERS = {"bash", "sh", "zsh", "env", "exec", "nohup", "sudo", "time"}
SCRIPT_INTERPRETERS = {"python", "python3", "node", "deno", "bun"}
UV_VALUE_OPTIONS = {
    "--with",
    "--python",
    "-p",
    "--project",
    "--directory",
    "--extra",
    "--group",
    "--package",
    "--env-file",
    "--from",
}
LAUNCHER_STEM_WORDS = {
    "run",
    "start",
    "stop",
    "serve",
    "server",
    "up",
    "down",
    "launch",
    "teardown",
    "shutdown",
    "restart",
}
LAUNCHER_ARG_WORDS = {"start", "stop", "serve", "up", "down", "restart", "teardown"}
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")


@dataclass
class Assertion:
    criterion: int
    name: str
    passed: bool
    detail: str
    evidence: dict[str, str] = field(default_factory=dict)


@dataclass
class Audit:
    repo: Path
    report: Path
    lane: str
    assertions: list[Assertion] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def add(
        self,
        criterion: int,
        name: str,
        passed: bool,
        detail: str,
        **evidence: str,
    ) -> None:
        self.assertions.append(Assertion(criterion, name, passed, detail, evidence))

    def failed(self, criterion: int | None = None) -> list[Assertion]:
        return [
            item
            for item in self.assertions
            if not item.passed and (criterion is None or item.criterion == criterion)
        ]

    def status(self, criterion: int) -> str:
        matching = [a for a in self.assertions if a.criterion == criterion]
        if any(not item.passed for item in matching):
            return "FAIL"
        if self.lane == "static" and criterion == 4:
            return "NOT RUN"
        if self.lane == "browser" and criterion != 4:
            return "NOT RUN"
        if not matching:
            return "NOT RUN"
        return "PASS"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(repo: Path, value: str) -> Path:
    path = (repo / value).resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes repository: {value}") from error
    return path


def command_version(command: str, *args: str) -> str:
    binary = shutil.which(command) if "/" not in command else command
    if not binary:
        return "missing"
    result = subprocess.run(
        [binary, *args], capture_output=True, text=True, timeout=15, check=False
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else f"exit {result.returncode}"


def git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def tracked_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True
    )
    if result.returncode == 0 and result.stdout:
        paths = [repo / os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw]
    else:
        paths = [path for path in repo.rglob("*") if path.is_file()]
    # The vendored checker and its deliberately failing selftest fixtures live
    # in .demo-kit/; they are tooling, not the repo's published content.
    return [
        path
        for path in paths
        if not any(part in SKIP_PARTS for part in path.relative_to(repo).parts)
    ]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest(
    repo: Path,
    path: Path,
    schema_path: Path,
    audit: Audit,
) -> dict[str, Any] | None:
    if not path.is_file():
        audit.add(1, "manifest", False, f"missing {path.relative_to(repo)}")
        for criterion in (2, 3, 4, 5):
            audit.add(criterion, "manifest", False, "public-bar.toml is required")
        return None
    try:
        manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        audit.add(1, "manifest", False, f"cannot parse manifest: {error}")
        return None
    try:
        schema = load_json(schema_path)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(manifest),
            key=lambda item: list(item.absolute_path),
        )
    except (OSError, json.JSONDecodeError) as error:
        audit.add(1, "manifest-schema", False, f"cannot load schema: {error}")
        return None
    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "root"
            audit.add(1, "manifest-schema", False, f"{location}: {error.message}")
        for criterion in (2, 3, 4, 5):
            audit.add(
                criterion,
                "manifest-schema",
                False,
                "manifest schema failed before this criterion could run",
            )
        return None
    audit.add(1, "manifest-schema", True, "public-bar.toml matches schema version 1")
    return manifest


def run_checked(
    command: list[str], cwd: Path, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def classified_yaml(repo: Path, manifest: dict[str, Any], audit: Audit) -> None:
    repo = repo.resolve()
    classified: set[Path] = set()
    for pipeline in manifest.get("pipelines", []):
        classified.add(safe_path(repo, pipeline["path"]))
    for platform in manifest.get("platforms", []):
        for value in platform.get("files", []):
            classified.add(safe_path(repo, value))
    for entry in manifest.get("yaml", []):
        classified.add(safe_path(repo, entry["path"]))
    candidates = [
        path.resolve()
        for path in tracked_files(repo)
        if path.suffix.lower() in YAML_SUFFIXES
        and ".github/workflows" not in path.as_posix()
        and not any(part in SKIP_PARTS for part in path.parts)
    ]
    missing = [
        str(path.relative_to(repo)) for path in candidates if path not in classified
    ]
    if missing:
        for path in missing:
            audit.add(1, "yaml-inventory", False, f"unclassified YAML: {path}")
    else:
        audit.add(1, "yaml-inventory", True, f"classified {len(candidates)} YAML files")


def read_json_lines(path: Path) -> list[Any]:
    values = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{path.name}:{number}: invalid JSON: {error.msg}"
            ) from error
    return values


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)


def run_edge_fixture(
    repo: Path,
    pipeline: dict[str, Any],
    pipeline_path: Path,
    edge_binary: str,
    cli_binary: str,
) -> tuple[bool, str, dict[str, str]]:
    input_path = safe_path(repo, pipeline["input"])
    expected_path = (
        safe_path(repo, pipeline["expected"]) if pipeline.get("expected") else None
    )
    schema_path = (
        safe_path(repo, pipeline["expected_schema"])
        if pipeline.get("expected_schema")
        else None
    )
    expected: list[Any] | None = None
    expected_schema: dict[str, Any] | None = None
    if expected_path:
        try:
            expected = read_json_lines(expected_path)
        except (OSError, ValueError) as error:
            return False, str(error), {}
        if not expected:
            return False, "golden output contains no JSON records", {}
        expected_count = len(expected)
    else:
        try:
            expected_schema = load_json(schema_path)
        except (OSError, json.JSONDecodeError) as error:
            return False, f"cannot load expected schema: {error}", {}
        expected_count = int(pipeline["expected_count"])
    try:
        document = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        return False, f"cannot render local replay: {error}", {}
    config = document.get("config", document)
    if not isinstance(config, dict):
        return False, "pipeline config is not an object", {}

    with tempfile.TemporaryDirectory(prefix="public-bar-edge-") as raw_temp:
        temp = Path(raw_temp)
        output = temp / "actual.jsonl"
        rendered = json.loads(json.dumps(document))
        rendered_config = rendered.get("config", rendered)
        rendered_config["input"] = {
            "file": {"paths": [str(input_path)], "codec": "lines"}
        }
        rendered_config["output"] = {"file": {"path": str(output), "codec": "lines"}}
        rendered_path = temp / "pipeline.yaml"
        rendered["name"] = f"public-bar-{pipeline['id']}"
        rendered["type"] = "pipeline"
        rendered["config"] = rendered_config
        rendered_path.write_text(
            yaml.safe_dump(rendered, sort_keys=False), encoding="utf-8"
        )
        data_dir = temp / "edge-data"
        port = free_port()
        endpoint = f"http://127.0.0.1:{port}"
        command = [
            edge_binary,
            "run",
            "--local",
            "--no-watch",
            "--api-listen",
            f"127.0.0.1:{port}",
            "--data-dir",
            str(data_dir),
            "--log-format",
            "text",
            "--log-level",
            "warn",
        ]
        process = subprocess.Popen(
            command,
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + int(pipeline.get("timeout_seconds", 30))
        actual: list[Any] | None = None
        parse_error = ""
        try:
            healthy = False
            health_deadline = min(deadline, time.monotonic() + 15)
            while time.monotonic() < health_deadline:
                health = run_checked(
                    [cli_binary, "--endpoint", endpoint, "health"], repo, timeout=3
                )
                if health.returncode == 0:
                    healthy = True
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            if not healthy:
                return False, "local Edge API did not become healthy", {}
            deploy = run_checked(
                [
                    cli_binary,
                    "--endpoint",
                    endpoint,
                    "job",
                    "deploy",
                    str(rendered_path),
                    "--force",
                ],
                repo,
                timeout=15,
            )
            if deploy.returncode:
                return (
                    False,
                    (deploy.stderr or deploy.stdout).strip()
                    or "local job deployment failed",
                    {},
                )
            while time.monotonic() < deadline:
                if output.is_file():
                    try:
                        actual = read_json_lines(output)
                    except (OSError, ValueError) as error:
                        parse_error = str(error)
                    if actual is not None and len(actual) >= expected_count:
                        break
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        finally:
            with contextlib.suppress(subprocess.SubprocessError):
                run_checked(
                    [
                        cli_binary,
                        "--endpoint",
                        endpoint,
                        "job",
                        "delete",
                        rendered["name"],
                        "--yes",
                        "--force",
                    ],
                    repo,
                    timeout=5,
                )
            stop_process_tree(process)
        stdout, stderr = process.communicate()
        if actual is None:
            tail = "\n".join((stderr or stdout).splitlines()[-6:])
            detail = parse_error or tail or "edge produced no fixture output"
            return False, detail, {}
        evidence = {
            "input_sha256": sha256(input_path),
            "actual_sha256": sha256(output),
        }
        if expected_path:
            evidence["expected_sha256"] = sha256(expected_path)
        if schema_path:
            evidence["expected_schema_sha256"] = sha256(schema_path)
        if expected is not None and actual != expected:
            return (
                False,
                f"output mismatch: expected {len(expected)} records, got {len(actual)}",
                evidence,
            )
        if expected_schema is not None:
            errors = list(Draft202012Validator(expected_schema).iter_errors(actual))
            if errors:
                return False, f"output schema mismatch: {errors[0].message}", evidence
        return (
            True,
            f"local Edge replay matched {len(actual)} JSON records",
            evidence,
        )


def check_pipelines(
    repo: Path,
    manifest: dict[str, Any],
    audit: Audit,
    edge_binary: str,
    cli_binary: str,
) -> None:
    pipelines = manifest.get("pipelines", [])
    if not pipelines:
        audit.add(1, "pipelines", False, "manifest declares no complete pipelines")
        return
    identifiers = [pipeline["id"] for pipeline in pipelines]
    for identifier in sorted(
        {item for item in identifiers if identifiers.count(item) > 1}
    ):
        audit.add(1, "pipelines", False, f"duplicate pipeline id: {identifier}")
    for pipeline in pipelines:
        pipeline_id = pipeline["id"]
        path = safe_path(repo, pipeline["path"])
        artifacts = [
            ("pipeline", path),
            ("input", safe_path(repo, pipeline["input"])),
        ]
        if pipeline.get("expected"):
            artifacts.append(("expected", safe_path(repo, pipeline["expected"])))
        if pipeline.get("expected_schema"):
            artifacts.append(
                ("expected_schema", safe_path(repo, pipeline["expected_schema"]))
            )
        for label, value in artifacts:
            if not value.is_file():
                audit.add(
                    1, pipeline_id, False, f"missing {label}: {value.relative_to(repo)}"
                )
        if not path.is_file():
            continue
        edge = run_checked(
            [edge_binary, "validate", str(path), "--output", "json"], repo
        )
        audit.add(
            1,
            f"{pipeline_id}:edge-validate",
            edge.returncode == 0,
            "expanso-edge validate passed"
            if edge.returncode == 0
            else (edge.stderr or edge.stdout).strip() or "expanso-edge validate failed",
        )
        cli = run_checked([cli_binary, "job", "validate", str(path), "--offline"], repo)
        audit.add(
            1,
            f"{pipeline_id}:job-validate",
            cli.returncode == 0,
            "expanso-cli offline job validation passed"
            if cli.returncode == 0
            else (cli.stderr or cli.stdout).strip()
            or "expanso-cli job validation failed",
        )
        if edge.returncode == 0 and cli.returncode == 0:
            passed, detail, evidence = run_edge_fixture(
                repo, pipeline, path, edge_binary, cli_binary
            )
            audit.add(1, f"{pipeline_id}:fixture", passed, detail, **evidence)


def yaml_documents(path: Path) -> Iterable[dict[str, Any]]:
    try:
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if isinstance(document, dict):
                yield document
    except (OSError, yaml.YAMLError):
        return


def walk(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def image_is_pinned(value: str) -> bool:
    match = IMAGE.match(value)
    if not match:
        return False
    if "@sha256:" in value:
        return True
    tag = match.group(2)
    return bool(tag and tag.lower() != "latest")


def validate_kubernetes(path: Path) -> list[str]:
    errors: list[str] = []
    for document in yaml_documents(path):
        kind = str(document.get("kind", ""))
        if not document.get("apiVersion") or not kind:
            errors.append(f"{path.name}: Kubernetes object needs apiVersion and kind")
            continue
        if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
            spec = document.get("spec", {})
            if kind == "CronJob":
                pod = (
                    spec.get("jobTemplate", {})
                    .get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )
            elif kind == "Job":
                pod = spec.get("template", {}).get("spec", {})
            else:
                pod = spec.get("template", {}).get("spec", {})
            if not pod.get("serviceAccountName"):
                errors.append(f"{path.name}:{kind} needs serviceAccountName")
            if not pod.get("securityContext", {}).get("runAsNonRoot"):
                errors.append(f"{path.name}:{kind} needs pod runAsNonRoot: true")
            for container in pod.get("containers", []):
                image = str(container.get("image", ""))
                if not image_is_pinned(image):
                    errors.append(
                        f"{path.name}:{kind} image is mutable: {image or '<missing>'}"
                    )
                security = container.get("securityContext", {})
                if security.get("allowPrivilegeEscalation") is not False:
                    errors.append(
                        f"{path.name}:{kind} must disable privilege escalation"
                    )
                dropped = security.get("capabilities", {}).get("drop", [])
                if "ALL" not in dropped:
                    errors.append(f"{path.name}:{kind} must drop ALL capabilities")
                if security.get("readOnlyRootFilesystem") is not True:
                    errors.append(
                        f"{path.name}:{kind} needs readOnlyRootFilesystem: true"
                    )
        if kind in {"Role", "ClusterRole"}:
            for rule in document.get("rules", []):
                if "*" in rule.get("verbs", []) or "*" in rule.get("resources", []):
                    errors.append(f"{path.name}:{kind} contains wildcard RBAC")
        if kind == "Ingress" and not document.get("spec", {}).get("tls"):
            errors.append(f"{path.name}:Ingress needs TLS")
        if kind == "Route" and not document.get("spec", {}).get("tls"):
            errors.append(f"{path.name}:Route needs TLS")
        if kind == "Secret" and (document.get("data") or document.get("stringData")):
            errors.append(f"{path.name}:Secret embeds credential material")
    return errors


def validate_compose(path: Path) -> list[str]:
    documents = list(yaml_documents(path))
    if not documents:
        return [f"{path.name}: cannot parse Compose YAML"]
    errors: list[str] = []
    for name, service in documents[0].get("services", {}).items():
        image = str(service.get("image", ""))
        if image and not image_is_pinned(image):
            errors.append(f"{path.name}:{name} image is mutable: {image}")
        if service.get("privileged"):
            errors.append(f"{path.name}:{name} cannot be privileged")
        if service.get("read_only") is not True:
            errors.append(f"{path.name}:{name} needs read_only: true")
        if "ALL" not in service.get("cap_drop", []):
            errors.append(f"{path.name}:{name} must drop ALL capabilities")
        user = str(service.get("user", ""))
        if not user or user.split(":", 1)[0] in {"0", "root"}:
            errors.append(f"{path.name}:{name} needs a non-root user")
    return errors


def has_key(documents: Iterable[dict[str, Any]], *names: str) -> bool:
    wanted = set(names)
    return any(key in wanted for document in documents for key, _ in walk(document))


def check_platforms(repo: Path, manifest: dict[str, Any], audit: Audit) -> None:
    platforms = manifest.get("platforms", [])
    declared = {str(item["name"]).lower(): item for item in platforms}
    public_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in tracked_files(repo)
        if path.suffix.lower() in TEXT_SUFFIXES
        and not any(part in SKIP_PARTS for part in path.parts)
    )
    for name, pattern in PLATFORM_TERMS.items():
        if pattern.search(public_text) and name not in declared:
            audit.add(
                2, "platform-inventory", False, f"named platform is undeclared: {name}"
            )
    if not audit.failed(2):
        audit.add(
            2, "platform-inventory", True, f"declared {len(platforms)} named platforms"
        )

    service_ids = {service["id"] for service in manifest.get("services", [])}
    pipeline_ids = {pipeline["id"] for pipeline in manifest.get("pipelines", [])}
    for platform in platforms:
        name = platform["name"]
        profile = platform["profile"]
        files = [safe_path(repo, value) for value in platform.get("files", [])]
        errors: list[str] = []
        for path in files:
            if not path.is_file():
                errors.append(f"missing platform file: {path.relative_to(repo)}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if PLACEHOLDER.search(text):
                errors.append(f"{path.name} contains a placeholder endpoint or value")
            for key, value in walk(list(yaml_documents(path))):
                if (
                    key == "image"
                    and isinstance(value, str)
                    and not image_is_pinned(value)
                ):
                    errors.append(f"{path.name} has mutable image: {value}")
            if profile in {"kubernetes", "openshift"}:
                errors.extend(validate_kubernetes(path))
            if profile == "compose":
                errors.extend(validate_compose(path))
        documents = [document for path in files for document in yaml_documents(path)]
        validators = platform.get("validators", [])
        validator_tools = {Path(command[0]).name for command in validators if command}
        secured_profiles = {
            "kubernetes",
            "openshift",
            "compose",
            "kafka",
            "mqtt",
            "prometheus",
        }
        if profile in secured_profiles:
            for field in ("tls", "auth", "persistent"):
                if platform.get(field) is not True:
                    errors.append(f"{profile} must declare {field} = true")
        if profile in {"kubernetes", "openshift"}:
            for tool in ("kubectl", "kubeconform"):
                if tool not in validator_tools:
                    errors.append(f"{profile} needs a {tool} validator")
            if not has_key(documents, "secretKeyRef", "secretRef"):
                errors.append(f"{profile} needs an external credential reference")
            if not has_key(documents, "persistentVolumeClaim", "volumeClaimTemplates"):
                errors.append(f"{profile} needs persistent volume storage")
        if profile == "compose":
            compose_validator = any(
                len(command) >= 3
                and Path(command[0]).name == "docker"
                and command[1] == "compose"
                and "config" in command
                for command in validators
            )
            if not compose_validator:
                errors.append("compose needs a `docker compose config` validator")
            if not any(document.get("secrets") for document in documents):
                errors.append("compose needs a declared secret reference")
            if not any(document.get("volumes") for document in documents):
                errors.append("compose needs a named persistent volume")
        if profile in {"kafka", "mqtt", "prometheus"}:
            if not validators:
                errors.append(f"{profile} needs a protocol-schema validator")
            if platform.get("service") not in service_ids:
                errors.append(f"{profile} needs a declared fixture service")
            if not platform.get("probe_command"):
                errors.append(f"{profile} needs a wire-format probe_command")
        if profile == "managed-cloud":
            replay = platform.get("local_replay_pipeline")
            if replay not in pipeline_ids:
                errors.append(
                    "managed-cloud claim needs a complete local replay pipeline"
                )
        if profile == "regulated" and not platform.get("security_evidence"):
            errors.append("regulated claim needs security_evidence")
        for validator in platform.get("validators", []):
            result = run_checked(list(validator), repo)
            if result.returncode:
                errors.append(
                    (result.stderr or result.stdout).strip()
                    or f"validator failed: {' '.join(validator)}"
                )
        if errors:
            for error in errors:
                audit.add(2, name, False, error)
        else:
            audit.add(
                2, name, True, f"{profile} files and integration declaration passed"
            )


def check_structure(repo: Path, manifest: dict[str, Any], audit: Audit) -> None:
    web = manifest["web"]
    document_path = safe_path(repo, web["document"])
    if not document_path.is_file():
        audit.add(3, "published-document", False, f"missing {web['document']}")
        return
    soup = BeautifulSoup(document_path.read_text(encoding="utf-8"), "html.parser")
    for name in ("explanation", "explorer", "run", "deploy"):
        selector = web[f"{name}_selector"]
        try:
            found = soup.select(selector)
        except Exception as error:  # SoupSieve reports several selector errors.
            audit.add(3, name, False, f"invalid selector {selector}: {error}")
            continue
        audit.add(
            3,
            name,
            bool(found),
            f"{selector} matched {len(found)} element(s)"
            if found
            else f"{selector} matched no published element",
        )
    pipelines = {item["id"] for item in manifest.get("pipelines", [])}
    stage_pipelines: set[str] = set()
    stage_ids: set[str] = set()
    for stage in manifest.get("stages", []):
        stage_id = stage["id"]
        if stage_id in stage_ids:
            audit.add(3, "explorer-stage", False, f"duplicate stage id: {stage_id}")
        stage_ids.add(stage_id)
        stage_pipelines.add(stage["pipeline"])
        input_path = safe_path(repo, stage["input"])
        output_path = safe_path(repo, stage["output"])
        selector = stage["selector"]
        ok = (
            input_path.is_file()
            and output_path.is_file()
            and bool(soup.select(selector))
        )
        detail = (
            "fixture-backed explorer stage exists"
            if ok
            else f"stage needs input, output, and matching selector {selector}"
        )
        audit.add(3, f"stage:{stage_id}", ok, detail)
        if stage["pipeline"] not in pipelines:
            audit.add(
                3,
                f"stage:{stage_id}",
                False,
                f"stage references unknown pipeline: {stage['pipeline']}",
            )
    for pipeline_id in sorted(pipelines - stage_pipelines):
        audit.add(
            3,
            "pipeline-explorer",
            False,
            f"pipeline has no explorer stage: {pipeline_id}",
        )
    if not manifest.get("stages"):
        audit.add(3, "explorer-stages", False, "manifest declares no explorer stages")


def just_binary() -> str | None:
    found = shutil.which("just")
    if found:
        return found
    # `uv run -s` installs the pinned rust-just wheel beside the interpreter.
    sibling = Path(sys.executable).parent / "just"
    return str(sibling) if sibling.is_file() else None


def required_parameters(recipe: dict[str, Any]) -> list[str]:
    return [
        str(parameter.get("name"))
        for parameter in recipe.get("parameters", [])
        if parameter.get("default") is None and parameter.get("kind") != "star"
    ]


def check_justfile(repo: Path, audit: Audit) -> None:
    justfiles = sorted(
        path
        for path in repo.iterdir()
        if path.is_file() and path.name.lower() in JUSTFILE_NAMES
    )
    if not justfiles:
        audit.add(
            3,
            "justfile",
            False,
            "no justfile at the repository root; add one with up and down recipes",
        )
        return
    justfile = justfiles[0]
    binary = just_binary()
    if not binary:
        audit.add(3, "justfile", False, "just is required to read the justfile")
        return
    result = subprocess.run(
        [
            binary,
            "--justfile",
            str(justfile),
            "--working-directory",
            str(repo),
            "--dump",
            "--dump-format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        dump = json.loads(result.stdout) if result.returncode == 0 else None
    except json.JSONDecodeError:
        dump = None
    if not isinstance(dump, dict):
        error = (result.stderr or result.stdout).strip().splitlines()
        audit.add(
            3,
            "justfile",
            False,
            f"just could not parse {justfile.name}: "
            + (error[0] if error else f"exit {result.returncode}"),
        )
        return
    audit.add(3, "justfile", True, f"{justfile.name} parsed by just")
    recipes = dump.get("recipes") or {}
    aliases = dump.get("aliases") or {}
    for name in LIFECYCLE_RECIPES:
        target = name
        if name not in recipes and name in aliases:
            target = str(aliases[name].get("target", ""))
        recipe = recipes.get(target)
        if not isinstance(recipe, dict):
            audit.add(
                3,
                f"just:{name}",
                False,
                f"justfile has no `{name}` recipe; `just {name}` must "
                + ("start everything" if name == "up" else "stop and clean up"),
            )
            continue
        required = required_parameters(recipe)
        audit.add(
            3,
            f"just:{name}",
            not required,
            f"`just {name}` runs recipe {target}"
            if not required
            else f"`just {name}` needs arguments: " + ", ".join(required),
        )


def readme_code(text: str) -> Iterable[tuple[int, str, bool]]:
    """Yield (line number, code, fenced) for fenced lines and inline code."""
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            yield number, line, True
        else:
            for match in INLINE_CODE.finditer(line):
                yield number, match.group(1), False


def code_commands(code: str) -> Iterable[list[str]]:
    for segment in re.split(r"&&|\|\||[;|]", code):
        segment = re.sub(r"^\s*[$>]\s+", "", segment)
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            words = segment.split()
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if words:
            yield words


def launched_script(words: list[str]) -> tuple[str, list[str]] | None:
    """Return the script path and its arguments when a command runs one."""
    index = 0
    while index < len(words):
        word = words[index]
        if word in SCRIPT_WRAPPERS or word in SCRIPT_INTERPRETERS:
            index += 1
        elif word in {"uv", "uvx"}:
            index += 2 if index + 1 < len(words) and words[index + 1] == "run" else 1
            while index < len(words) and words[index].startswith("-"):
                index += 2 if words[index] in UV_VALUE_OPTIONS else 1
        elif word.startswith("-"):
            index += 1
        else:
            break
    if index >= len(words):
        return None
    target = words[index]
    if target.startswith(".demo-kit/") or "://" in target:
        return None
    is_path = (
        target.startswith(("./", "../", "scripts/"))
        or "/scripts/" in target
        or target.endswith(SCRIPT_SUFFIXES)
    )
    return (target, words[index + 1 :]) if is_path else None


def is_lifecycle_launcher(script: str, arguments: list[str]) -> bool:
    # A harness under tests/ runs checks, not the demo.
    if {"tests", "test"} & set(Path(script).parts[:-1]):
        return False
    stem = Path(script).name
    for suffix in SCRIPT_SUFFIXES:
        stem = stem.removesuffix(suffix)
    stem_words = set(re.split(r"[-_.]+", stem.lower()))
    argument_words = {argument.lower() for argument in arguments}
    return bool(stem_words & LAUNCHER_STEM_WORDS or argument_words & LAUNCHER_ARG_WORDS)


def check_readme_lifecycle(repo: Path, audit: Audit) -> None:
    readmes = sorted(
        path
        for path in repo.iterdir()
        if path.is_file() and path.name.lower() == "readme.md"
    )
    if not readmes:
        audit.add(3, "readme:just", False, "no README.md at the repository root")
        return
    readme = readmes[0]
    shown: set[str] = set()
    launchers: list[str] = []
    for number, code, fenced in readme_code(readme.read_text(encoding="utf-8")):
        for words in code_commands(code):
            if words[0] == "just" and len(words) > 1:
                shown.add(words[1])
            # A lone inline path such as `scripts/serve.py` names a file; it
            # is a command only when written to run, as in `./scripts/serve.py`.
            if (
                not fenced
                and len(words) == 1
                and not words[0].startswith(("./", "../"))
            ):
                continue
            launched = launched_script(words)
            if launched and is_lifecycle_launcher(*launched):
                launchers.append(f"{readme.name}:{number} `{' '.join(words)}`")
    missing = [name for name in LIFECYCLE_RECIPES if name not in shown]
    audit.add(
        3,
        "readme:just",
        not missing,
        f"{readme.name} starts with `just up` and stops with `just down`"
        if not missing
        else f"{readme.name} never shows "
        + " or ".join(f"`just {name}`" for name in missing),
    )
    audit.add(
        3,
        "readme:raw-launcher",
        not launchers,
        f"{readme.name} shows no raw start or stop script"
        if not launchers
        else "start and stop with `just up` / `just down`, not "
        + "; ".join(launchers[:5])
        + (f" (+{len(launchers) - 5} more)" if len(launchers) > 5 else ""),
    )


def check_browser_contract(manifest: dict[str, Any], audit: Audit) -> None:
    browser = manifest.get("browser", {})
    required = {
        "url",
        "start_command",
        "stop_command",
        "ready_url",
        "theme_toggle_selector",
        "stage_selector",
        "current_stage_selector",
        "scroll_anchor_selector",
        "json_selectors",
    }
    missing = sorted(
        key
        for key in required
        if key not in browser or (key != "json_selectors" and not browser.get(key))
    )
    controls = browser.get("controls", [])
    if not controls:
        missing.append("controls")
    for control in controls:
        for key in (
            "id",
            "kind",
            "selector",
            "feedback_selector",
            "success_text",
            "failure_text",
        ):
            if not control.get(key):
                missing.append(f"control {control.get('id', '<unknown>')}:{key}")
        if control.get("kind") == "download" and not control.get("failure_url_pattern"):
            missing.append(
                f"control {control.get('id', '<unknown>')}:failure_url_pattern"
            )
    audit.add(
        4,
        "browser-contract",
        not missing,
        "rendered-browser declarations are complete"
        if not missing
        else "missing browser declarations: " + ", ".join(missing),
    )


def check_ui_source(repo: Path, audit: Audit) -> None:
    patterns = {
        "pure-white": re.compile(
            r"#fff(?:fff)?\b|rgb\(\s*255\s*,\s*255\s*,\s*255", re.I
        ),
        "eyebrow-label": re.compile(
            r"(?:class|id)=[\"'][^\"']*(?:eyebrow|overline|kicker)", re.I
        ),
        "grid-background": re.compile(r"repeating-(?:linear|radial)-gradient", re.I),
        "decorative-stripe": re.compile(
            r"(?:class|id)=[\"'][^\"']*(?:side|accent|decorative)[-_ ](?:stripe|bar)",
            re.I,
        ),
    }
    findings: list[str] = []
    for path in tracked_files(repo):
        if path.suffix.lower() not in {".css", ".html", ".htm", ".js", ".jsx", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{name} in {path.relative_to(repo)}")
    for finding in findings:
        audit.add(4, "source-policy", False, finding)
    if not findings:
        audit.add(
            4, "source-policy", True, "source avoids banned public-demo decoration"
        )


def feature_ids(document: dict[str, Any]) -> dict[str, set[str]]:
    return {
        key: {str(item["id"]) for item in document.get(key, [])}
        for key in ("features", "routes", "controls", "downloads", "browser_assertions")
    }


def git_file(repo: Path, ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def baseline_refs(repo: Path, explicit: list[str]) -> list[str]:
    refs: list[str] = []
    for ref in explicit:
        if ref and ref not in refs and git(repo, "rev-parse", "--verify", ref):
            refs.append(ref)
    tag = git(repo, "describe", "--tags", "--abbrev=0", "HEAD^")
    if tag and tag not in refs:
        refs.append(tag)
    return refs


def approved_removals(repo: Path, manifest: dict[str, Any], audit: Audit) -> set[str]:
    approved: set[str] = set()
    for pattern in manifest.get("regressions", {}).get("removal_files", []):
        for path in repo.glob(pattern):
            try:
                document = load_json(path)
            except (OSError, json.JSONDecodeError) as error:
                audit.add(5, "removal-file", False, f"{path.name}: {error}")
                continue
            for entry in document.get("removals", []):
                try:
                    approved_on = dt.date.fromisoformat(
                        str(entry.get("approved_on", ""))
                    )
                except ValueError:
                    approved_on = None
                valid = (
                    entry.get("approved_by") == "captain"
                    and approved_on is not None
                    and approved_on <= dt.datetime.now(dt.timezone.utc).date()
                    and bool(entry.get("reason"))
                    and bool(entry.get("id"))
                )
                if valid:
                    approved.add(str(entry["id"]))
                else:
                    audit.add(
                        5, "removal-file", False, f"invalid approval in {path.name}"
                    )
    return approved


def check_regressions(
    repo: Path,
    manifest: dict[str, Any],
    schema_path: Path,
    audit: Audit,
    refs: list[str],
) -> None:
    feature_path_value = manifest["regressions"]["features"]
    feature_path = safe_path(repo, feature_path_value)
    if not feature_path.is_file():
        audit.add(5, "feature-manifest", False, f"missing {feature_path_value}")
        return
    try:
        current = load_json(feature_path)
        schema = load_json(schema_path)
        errors = list(Draft202012Validator(schema).iter_errors(current))
    except (OSError, json.JSONDecodeError) as error:
        audit.add(5, "feature-manifest", False, str(error))
        return
    if errors:
        for error in errors:
            audit.add(5, "feature-manifest", False, error.message)
        return
    audit.add(
        5, "feature-manifest", True, "public-features.json matches schema version 1"
    )
    current_ids = feature_ids(current)
    seen: dict[str, str] = {}
    for category, identifiers in current_ids.items():
        for identifier in identifiers:
            if identifier in seen:
                audit.add(
                    5,
                    "feature-id",
                    False,
                    f"feature id {identifier} is reused in {seen[identifier]} and {category}",
                )
            else:
                seen[identifier] = category
    stage_ids = {stage["id"] for stage in manifest.get("stages", [])}
    missing_stages = stage_ids - current_ids["features"]
    for stage_id in sorted(missing_stages):
        audit.add(
            5,
            "explorer-feature",
            False,
            f"stage is not retained as a feature: {stage_id}",
        )
    browser_controls = manifest.get("browser", {}).get("controls", [])
    expected_controls = {
        item["id"] for item in browser_controls if item["kind"] == "copy"
    }
    expected_downloads = {
        item["id"] for item in browser_controls if item["kind"] == "download"
    }
    for identifier in sorted(expected_controls - current_ids["controls"]):
        audit.add(
            5, "retained-control", False, f"copy control is not retained: {identifier}"
        )
    for identifier in sorted(expected_downloads - current_ids["downloads"]):
        audit.add(
            5, "retained-download", False, f"download is not retained: {identifier}"
        )

    removals = approved_removals(repo, manifest, audit)
    found_baseline = False
    compared_refs = baseline_refs(repo, refs)
    current_stage_ids = {str(stage["id"]) for stage in manifest.get("stages", [])}
    for ref in compared_refs:
        old_text = git_file(repo, ref, feature_path_value)
        if old_text is None:
            continue
        found_baseline = True
        try:
            old = json.loads(old_text)
        except json.JSONDecodeError as error:
            audit.add(5, "baseline", False, f"{ref}: invalid feature JSON: {error.msg}")
            continue
        for category, old_values in feature_ids(old).items():
            for identifier in sorted(old_values - current_ids[category] - removals):
                audit.add(
                    5,
                    "retained-feature",
                    False,
                    f"{ref} removed {category}:{identifier} without captain approval",
                )
        old_manifest_text = git_file(repo, ref, "public-bar.toml")
        if old_manifest_text:
            try:
                old_manifest = tomllib.loads(old_manifest_text)
            except tomllib.TOMLDecodeError as error:
                audit.add(5, "baseline", False, f"{ref}: invalid manifest: {error}")
            else:
                old_stage_ids = {
                    str(stage["id"]) for stage in old_manifest.get("stages", [])
                }
                for identifier in sorted(old_stage_ids - current_stage_ids - removals):
                    audit.add(
                        5,
                        "retained-stage",
                        False,
                        f"{ref} removed explorer stage {identifier} without captain approval",
                    )
    audit.add(
        5,
        "baseline",
        True,
        "compared retained features against " + ", ".join(compared_refs)
        if found_baseline
        else "initial adoption: no prior retained-feature baseline exists",
    )


def static_lane(
    repo: Path,
    manifest: dict[str, Any],
    audit: Audit,
    edge_binary: str,
    cli_binary: str,
    feature_schema: Path,
    refs: list[str],
) -> None:
    classified_yaml(repo, manifest, audit)
    processes: list[subprocess.Popen[str]] = []
    services: list[dict[str, Any]] = []
    ready_urls: list[str] = []
    try:
        if start_declared_services(
            repo, manifest, audit, 1, processes, services, ready_urls
        ):
            check_pipelines(repo, manifest, audit, edge_binary, cli_binary)
        else:
            audit.add(
                1,
                "pipelines",
                False,
                "pipeline fixtures not run because a declared service did not start",
            )
    finally:
        if services:
            stop_declared_services(repo, audit, 1, processes, services, ready_urls)
    check_platforms(repo, manifest, audit)
    check_structure(repo, manifest, audit)
    check_justfile(repo, audit)
    check_readme_lifecycle(repo, audit)
    check_browser_contract(manifest, audit)
    check_ui_source(repo, audit)
    check_regressions(repo, manifest, feature_schema, audit, refs)


CONTRAST_AUDIT_JS = r"""
() => {
  const parse = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const values = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return [values[0], values[1], values[2], values.length > 3 ? values[3] : 1];
  };
  const channel = (value) => {
    const scaled = value / 255;
    return scaled <= 0.04045
      ? scaled / 12.92
      : Math.pow((scaled + 0.055) / 1.055, 2.4);
  };
  const luminance = (rgb) => (
    0.2126 * channel(rgb[0]) +
    0.7152 * channel(rgb[1]) +
    0.0722 * channel(rgb[2])
  );
  const ratio = (left, right) => {
    const values = [luminance(left), luminance(right)].sort((a, b) => a - b);
    return (values[1] + 0.05) / (values[0] + 0.05);
  };
  const background = (element) => {
    let node = element;
    while (node) {
      const color = parse(getComputedStyle(node).backgroundColor);
      if (color && color[3] > 0.98) return color;
      node = node.parentElement;
    }
    return [255, 255, 255, 1];
  };
  const selector = (element) => {
    if (element.id) return `#${element.id}`;
    const name = element.tagName.toLowerCase();
    const marker = element.getAttribute("data-stage-id");
    return marker ? `${name}[data-stage-id="${marker}"]` : name;
  };
  const failures = [];
  for (const element of document.body.querySelectorAll("*")) {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    if (style.display === "none" || style.visibility === "hidden" ||
        rect.width === 0 || rect.height === 0) continue;
    const directText = Array.from(element.childNodes)
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent.trim())
      .join(" ")
      .trim();
    if (!directText) continue;
    const foreground = parse(style.color);
    const ground = background(element);
    if (!foreground || foreground[3] < 0.98) {
      failures.push({selector: selector(element), ratio: 0, reason: "transparent text"});
      continue;
    }
    const measured = ratio(foreground, ground);
    const pixels = Number.parseFloat(style.fontSize);
    const bold = Number.parseInt(style.fontWeight, 10) >= 700;
    const large = pixels >= 24 || (bold && pixels >= 18.66);
    const required = large ? 3 : 4.5;
    if (measured + 0.001 < required) {
      failures.push({
        selector: selector(element),
        ratio: Number(measured.toFixed(2)),
        required,
      });
    }
  }
  return failures;
}
"""


def wait_for_url(
    url: str, processes: list[subprocess.Popen[str]], timeout: int = 30
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() not in {None, 0} for process in processes):
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    return False


def url_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def wait_for_urls_stopped(urls: list[str], timeout: int = 8) -> list[str]:
    deadline = time.monotonic() + timeout
    remaining = [url for url in urls if url_reachable(url)]
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = [url for url in urls if url_reachable(url)]
    return remaining


def start_declared_process(command: list[str], repo: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def start_declared_services(
    repo: Path,
    manifest: dict[str, Any],
    audit: Audit,
    criterion: int,
    processes: list[subprocess.Popen[str]],
    services: list[dict[str, Any]],
    ready_urls: list[str],
) -> bool:
    """Start every declared service; callers must stop them in a finally block."""
    for service in manifest.get("services", []):
        services.append(service)
        try:
            processes.append(start_declared_process(service["command"], repo))
        except OSError as error:
            audit.add(
                criterion,
                f"service:{service['id']}",
                False,
                f"fixture service did not start: {error}",
            )
            return False
        ready_urls.append(service["ready_url"])
        if not wait_for_url(service["ready_url"], processes):
            audit.add(
                criterion,
                f"service:{service['id']}",
                False,
                "fixture service did not become ready",
            )
            return False
        audit.add(
            criterion,
            f"service:{service['id']}",
            True,
            "declared fixture service is ready",
        )
    return True


def stop_declared_services(
    repo: Path,
    audit: Audit,
    criterion: int,
    processes: list[subprocess.Popen[str]],
    services: list[dict[str, Any]],
    ready_urls: list[str],
) -> None:
    """Stop processes, run each stop_command even after failure, prove teardown."""
    for process in reversed(processes):
        stop_process_tree(process)
    for service in reversed(services):
        try:
            stop = run_checked(service["stop_command"], repo, timeout=30)
            failure = (
                (stop.stderr or stop.stdout).strip() or "fixture service stop failed"
                if stop.returncode
                else ""
            )
        except (OSError, subprocess.SubprocessError) as error:
            failure = f"fixture service stop failed: {error}"
        if failure:
            audit.add(criterion, f"service:{service['id']}:stop", False, failure)
    leaked = [process.pid for process in processes if process.poll() is None]
    live_urls = wait_for_urls_stopped(ready_urls)
    audit.add(
        criterion,
        "teardown",
        not leaked and not live_urls,
        "all declared services and browser hosts stopped"
        if not leaked and not live_urls
        else f"processes still running: {leaked}; URLs still live: {live_urls}",
    )


def theme_mode(page: Any) -> str:
    return str(
        page.evaluate(
            r"""() => {
              const root = document.documentElement;
              const named = root.dataset.theme || root.getAttribute("data-color-scheme");
              if (named) return named;
              const parse = (value) => {
                const match = value.match(/rgba?\(([^)]+)\)/);
                return match ? match[1].split(/[ ,/]+/).filter(Boolean).map(Number) : null;
              };
              let node = document.body;
              let color = null;
              while (node && (!color || (color[3] || 0) < 0.98)) {
                color = parse(getComputedStyle(node).backgroundColor);
                node = node.parentElement;
              }
              if (!color) return "unknown";
              const luminance = (0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]) / 255;
              return luminance >= 0.5 ? "light" : "dark";
            }"""
        )
    ).lower()


def check_visual_state(page: Any, label: str, audit: Audit, axe_path: Path) -> None:
    overflow = page.evaluate(
        "() => ({width: document.documentElement.scrollWidth, "
        "client: document.documentElement.clientWidth})"
    )
    audit.add(
        4,
        f"overflow:{label}",
        overflow["width"] <= overflow["client"],
        f"scrollWidth {overflow['width']} <= clientWidth {overflow['client']}",
    )
    contrast = page.evaluate(CONTRAST_AUDIT_JS)
    audit.add(
        4,
        f"contrast:{label}",
        not contrast,
        "all visible text meets WCAG AA"
        if not contrast
        else "contrast failures: " + json.dumps(contrast[:8], separators=(",", ":")),
    )
    if not page.evaluate("() => typeof axe !== 'undefined'"):
        page.add_script_tag(path=str(axe_path))
    axe = page.evaluate(
        "async () => await axe.run(document, {runOnly: {type: 'tag', "
        "values: ['wcag2a', 'wcag2aa', 'wcag21aa']}})"
    )
    violations = [
        item
        for item in axe["violations"]
        if item.get("impact") in {"minor", "moderate", "serious", "critical"}
    ]
    audit.add(
        4,
        f"axe:{label}",
        not violations,
        "axe found no WCAG A/AA violations"
        if not violations
        else "axe violations: " + ", ".join(item["id"] for item in violations),
    )


def check_stage_keys(page: Any, browser: dict[str, Any], audit: Audit) -> None:
    stage_count = page.locator(browser["stage_selector"]).count()
    current = page.locator(browser["current_stage_selector"])
    if stage_count == 0 or current.count() != 1:
        audit.add(4, "stage-keys", False, "explorer has no single current stage")
        return
    anchor = page.locator(browser["scroll_anchor_selector"])
    anchor.scroll_into_view_if_needed()
    before_id = (
        current.first.get_attribute("data-stage-id") or current.first.text_content()
    )
    before_y = page.evaluate("() => window.scrollY")
    before_top = anchor.bounding_box()["y"]
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    after = page.locator(browser["current_stage_selector"])
    after_id = after.first.get_attribute("data-stage-id") or after.first.text_content()
    after_y = page.evaluate("() => window.scrollY")
    after_top = anchor.bounding_box()["y"]
    changed = stage_count == 1 or before_id != after_id
    right_stable = abs(after_y - before_y) <= 2 and abs(after_top - before_top) <= 2
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(100)
    returned = page.locator(browser["current_stage_selector"])
    returned_id = (
        returned.first.get_attribute("data-stage-id") or returned.first.text_content()
    )
    left_y = page.evaluate("() => window.scrollY")
    left_top = anchor.bounding_box()["y"]
    returned_to_start = stage_count == 1 or returned_id == before_id
    left_stable = abs(left_y - before_y) <= 2 and abs(left_top - before_top) <= 2
    passed = changed and returned_to_start and right_stable and left_stable
    audit.add(
        4,
        "stage-keys",
        passed,
        f"Right and Left paged {stage_count} stages; scroll stayed within 2px"
        if passed
        else (
            f"right changed={changed}, left returned={returned_to_start}, "
            f"right stable={right_stable}, left stable={left_stable}"
        ),
    )


def feedback_contains(page: Any, selector: str, expected: str) -> bool:
    try:
        page.locator(selector).filter(has_text=expected).wait_for(
            state="visible", timeout=3000
        )
        return True
    except Exception:
        return False


def check_copy_control(page: Any, control: dict[str, Any], audit: Audit) -> None:
    page.evaluate(
        """() => {
          window.__publicBarCopies = [];
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {writeText: async (value) => window.__publicBarCopies.push(value)}
          });
        }"""
    )
    page.locator(control["selector"]).click()
    copied = page.evaluate("() => window.__publicBarCopies.length") > 0
    success = feedback_contains(
        page, control["feedback_selector"], control["success_text"]
    )
    page.evaluate(
        """() => Object.defineProperty(navigator, "clipboard", {
          configurable: true,
          value: {writeText: async () => { throw new Error("forced copy failure"); }}
        })"""
    )
    page.locator(control["selector"]).click()
    failure = feedback_contains(
        page, control["feedback_selector"], control["failure_text"]
    )
    audit.add(
        4,
        f"control:{control['id']}",
        copied and success and failure,
        f"copy invoked={copied}, local success={success}, forced failure={failure}",
    )


def check_download_control(page: Any, control: dict[str, Any], audit: Audit) -> None:
    downloaded = False
    try:
        with page.expect_download(timeout=5000) as pending:
            page.locator(control["selector"]).click()
        download = pending.value
        downloaded = not bool(download.failure())
        download.cancel()
    except Exception:
        downloaded = False
    success = feedback_contains(
        page, control["feedback_selector"], control["success_text"]
    )
    page.route(control["failure_url_pattern"], lambda route: route.abort("failed"))
    page.locator(control["selector"]).click()
    failure = feedback_contains(
        page, control["feedback_selector"], control["failure_text"]
    )
    page.unroute(control["failure_url_pattern"])
    audit.add(
        4,
        f"control:{control['id']}",
        downloaded and success and failure,
        f"download completed={downloaded}, local success={success}, forced failure={failure}",
    )


def check_json_blocks(page: Any, browser: dict[str, Any], audit: Audit) -> None:
    for selector in browser.get("json_selectors", []):
        locator = page.locator(selector)
        if locator.count() == 0:
            audit.add(4, "json", False, f"JSON selector matched nothing: {selector}")
            continue
        for index in range(locator.count()):
            text = locator.nth(index).text_content() or ""
            vertical = "\n" in text.strip()
            try:
                json.loads(text)
                valid = True
            except json.JSONDecodeError:
                valid = False
            audit.add(
                4,
                f"json:{selector}:{index}",
                vertical and valid,
                "JSON is valid and vertically pretty-printed"
                if vertical and valid
                else f"vertical={vertical}, valid={valid}",
            )


def find_axe_path() -> Path | None:
    configured = os.environ.get("PUBLIC_BAR_AXE_PATH")
    if configured and Path(configured).is_file():
        return Path(configured)
    node = shutil.which("node")
    if not node:
        return None
    result = subprocess.run(
        [node, "-p", "require.resolve('axe-core/axe.min.js')"],
        capture_output=True,
        text=True,
        check=False,
    )
    path = Path(result.stdout.strip())
    return path if result.returncode == 0 and path.is_file() else None


def browser_lane(repo: Path, manifest: dict[str, Any], audit: Audit) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        audit.add(4, "playwright", False, "Playwright is not installed")
        return
    axe_path = find_axe_path()
    if not axe_path:
        audit.add(
            4, "axe", False, "axe-core is not installed or PUBLIC_BAR_AXE_PATH is unset"
        )
        return
    browser_config = manifest["browser"]
    processes: list[subprocess.Popen[str]] = []
    services: list[dict[str, Any]] = []
    ready_urls: list[str] = []
    try:
        if not start_declared_services(
            repo, manifest, audit, 4, processes, services, ready_urls
        ):
            return
        for platform in manifest.get("platforms", []):
            if not platform.get("probe_command"):
                continue
            probe = run_checked(platform["probe_command"], repo, timeout=60)
            audit.add(
                2,
                f"{platform['name']}:wire-probe",
                probe.returncode == 0,
                "authenticated wire-format probe passed"
                if probe.returncode == 0
                else (probe.stderr or probe.stdout).strip()
                or "wire-format probe failed",
            )
            if probe.returncode:
                return
        processes.append(start_declared_process(browser_config["start_command"], repo))
        ready_urls.append(browser_config["ready_url"])
        if not wait_for_url(browser_config["ready_url"], processes):
            audit.add(4, "presenter", False, "presenter UI did not become ready")
            return
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch(headless=True)
            try:
                for width in (320, 400, 768, 1440):
                    context = chromium.new_context(
                        ignore_https_errors=True,
                        viewport={"width": width, "height": 900},
                    )
                    try:
                        page = context.new_page()
                        page.emulate_media(color_scheme="light")
                        page.goto(browser_config["url"], wait_until="networkidle")
                        default = theme_mode(page)
                        audit.add(
                            4,
                            f"theme-default:{width}",
                            "light" in default and "dark" not in default,
                            f"default theme reports {default or 'unknown'}",
                        )
                        check_visual_state(page, f"{width}:light", audit, axe_path)
                        page.locator(browser_config["theme_toggle_selector"]).click()
                        page.wait_for_timeout(100)
                        dark = theme_mode(page)
                        audit.add(
                            4,
                            f"theme-dark:{width}",
                            "dark" in dark,
                            f"toggle reports {dark or 'no dark theme'}",
                        )
                        check_visual_state(page, f"{width}:dark", audit, axe_path)
                    finally:
                        context.close()
                context = chromium.new_context(
                    ignore_https_errors=True,
                    viewport={"width": 1440, "height": 900},
                )
                page = context.new_page()
                page.goto(browser_config["url"], wait_until="networkidle")
                check_stage_keys(page, browser_config, audit)
                check_json_blocks(page, browser_config, audit)
                for control in browser_config["controls"]:
                    if control["kind"] == "copy":
                        check_copy_control(page, control, audit)
                    else:
                        check_download_control(page, control, audit)
                context.close()
            finally:
                chromium.close()
    except Exception as error:
        audit.add(4, "rendered-browser", False, f"browser check failed: {error}")
    finally:
        for process in reversed(processes):
            stop_process_tree(process)
        presenter_stop = run_checked(browser_config["stop_command"], repo, timeout=30)
        if presenter_stop.returncode:
            audit.add(
                4,
                "presenter:stop",
                False,
                (presenter_stop.stderr or presenter_stop.stdout).strip()
                or "presenter stop failed",
            )
        stop_declared_services(repo, audit, 4, processes, services, ready_urls)


def teardown_only(repo: Path, manifest_path: Path) -> int:
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"FAIL: cannot read teardown commands: {error}", file=sys.stderr)
        return 1
    failures: list[str] = []
    commands = [
        ("presenter", manifest.get("browser", {}).get("stop_command")),
        *[
            (f"service:{service.get('id', '<unknown>')}", service.get("stop_command"))
            for service in reversed(manifest.get("services", []))
        ],
    ]
    for name, command in commands:
        if not command:
            failures.append(f"{name} has no stop_command")
            continue
        result = run_checked(command, repo, timeout=30)
        if result.returncode:
            failures.append(
                f"{name}: "
                + ((result.stderr or result.stdout).strip() or "stop command failed")
            )
    urls = [
        manifest.get("browser", {}).get("ready_url", ""),
        *[service.get("ready_url", "") for service in manifest.get("services", [])],
    ]
    live_urls = wait_for_urls_stopped([url for url in urls if url])
    if live_urls:
        failures.append(f"URLs still live after teardown: {live_urls}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if not failures:
        print("ok: declared public-bar services are stopped")
    return 1 if failures else 0


def render_report(audit: Audit) -> tuple[str, dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    commit = git(audit.repo, "rev-parse", "HEAD") or "not-a-git-checkout"
    payload = {
        "schema_version": 1,
        "public_bar_version": PUBLIC_BAR_VERSION,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "repository": str(audit.repo),
        "commit": commit,
        "lane": audit.lane,
        "tools": audit.metadata,
        "criteria": {
            str(number): {
                "name": name,
                "status": audit.status(number),
            }
            for number, name in CRITERIA.items()
        },
        "assertions": [
            {
                "criterion": item.criterion,
                "name": item.name,
                "passed": item.passed,
                "detail": item.detail,
                "evidence": item.evidence,
            }
            for item in audit.assertions
        ],
    }
    lines = [
        "# Public bar report",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Commit: `{commit}`",
        f"- Checker: `{PUBLIC_BAR_VERSION}`",
        f"- Lane: `{audit.lane}`",
        "",
        "## Result",
        "",
        "| Criterion | Status |",
        "|---|---|",
    ]
    for number, name in CRITERIA.items():
        lines.append(f"| {number}. {name} | {audit.status(number)} |")
    lines.extend(["", "## Tool versions", ""])
    for name, version in sorted(audit.metadata.items()):
        lines.append(f"- `{name}`: {version}")
    lines.extend(
        [
            "",
            "## Assertions",
            "",
            "| Criterion | Assertion | Result | Detail |",
            "|---|---|---|---|",
        ]
    )
    for item in audit.assertions:
        detail = item.detail.replace("|", "\\|").replace("\n", " ")
        result = "PASS" if item.passed else "FAIL"
        lines.append(f"| {item.criterion} | `{item.name}` | {result} | {detail} |")
        for key, value in sorted(item.evidence.items()):
            lines.append(
                f"| {item.criterion} | `{item.name}:{key}` | EVIDENCE | `{value}` |"
            )
    lines.append("")
    return "\n".join(lines), payload


def write_report(audit: Audit) -> None:
    markdown, payload = render_report(audit)
    audit.report.parent.mkdir(parents=True, exist_ok=True)
    audit.report.write_text(markdown, encoding="utf-8")
    json_path = audit.report.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def initialize_selftest_repo(source: Path, overlay: Path | None, target: Path) -> None:
    shutil.copytree(source, target)
    shutil.copytree(source.parent / "bin", target / "bin")
    for binary in (target / "bin").iterdir():
        binary.chmod(0o755)
    commands = (
        ("init", "-q"),
        ("config", "user.email", "public-bar@example.invalid"),
        ("config", "user.name", "Public Bar Selftest"),
        ("add", "."),
        ("commit", "-qm", "fixture baseline"),
    )
    for command in commands:
        result = subprocess.run(
            ["git", *command],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "could not initialize fixture")
    if overlay:
        shutil.copytree(overlay, target, dirs_exist_ok=True)
        result = subprocess.run(
            ["git", "add", "."],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or "could not stage fixture overlay"
            )


def run_selftest(script_dir: Path) -> int:
    fixture_root = script_dir / "tests" / "fixtures" / "public-bar"
    good = fixture_root / "pass"
    bad_root = fixture_root / "fail"
    service_overlay = fixture_root / "service"
    missing = [
        path
        for path in [
            good,
            service_overlay,
            *(bad_root / str(number) for number in CRITERIA),
        ]
        if not path.is_dir()
    ]
    if missing:
        print(
            "FAIL selftest: missing fixture directories: "
            + ", ".join(str(path) for path in missing),
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="public-bar-selftest-") as raw:
        temporary = Path(raw)
        # fail/<n> and fail/<n>-<topic> each break exactly criterion n.
        cases: list[tuple[str, int | None, Path | None]] = [
            ("known-good", None, None),
            ("service-pipeline", None, service_overlay),
            *[
                (f"criterion-{overlay.name}", int(overlay.name.split("-")[0]), overlay)
                for overlay in sorted(bad_root.iterdir())
                if overlay.is_dir() and overlay.name.split("-")[0].isdigit()
            ],
        ]
        for case_name, expected_criterion, overlay in cases:
            repo = temporary / case_name
            initialize_selftest_repo(good, overlay, repo)
            report = repo / "artifacts" / "public-bar.md"
            command = [
                sys.executable,
                str(script_dir / "public-bar.py"),
                "--repo",
                str(repo),
                "--manifest",
                "public-bar.toml",
                "--report",
                str(report),
                "--lane",
                "static",
                "--base-ref",
                "HEAD",
                "--edge-binary",
                str(repo / "bin" / "expanso-edge"),
                "--cli-binary",
                str(repo / "bin" / "expanso-cli"),
            ]
            result = subprocess.run(
                command,
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            json_report = report.with_suffix(".json")
            if not json_report.is_file():
                failures.append(f"{case_name}: checker wrote no JSON report")
                continue
            payload = json.loads(json_report.read_text(encoding="utf-8"))
            failed_criteria = sorted(
                {
                    int(assertion["criterion"])
                    for assertion in payload["assertions"]
                    if not assertion["passed"]
                }
            )
            if expected_criterion is None:
                asserted = {
                    int(assertion["criterion"]) for assertion in payload["assertions"]
                }
                if (
                    result.returncode != 0
                    or failed_criteria
                    or asserted != set(CRITERIA)
                ):
                    failures.append(
                        f"{case_name}: expected all criterion checks to pass; "
                        f"exit={result.returncode}, failed={failed_criteria}, "
                        f"asserted={sorted(asserted)}"
                    )
                elif case_name == "service-pipeline" and not (
                    (repo / "sidecar.stopped").is_file()
                    and not url_reachable("http://127.0.0.1:4174/")
                ):
                    failures.append(
                        f"{case_name}: declared service was not stopped afterward"
                    )
                else:
                    print(f"PASS {case_name}: criteria 1-5 checks accepted the fixture")
                continue
            expected_name = f"FAIL {expected_criterion} {CRITERIA[expected_criterion]}:"
            if (
                result.returncode == 0
                or failed_criteria != [expected_criterion]
                or expected_name not in result.stderr
            ):
                failures.append(
                    f"{case_name}: expected nonzero exit naming only criterion "
                    f"{expected_criterion}; exit={result.returncode}, "
                    f"failed={failed_criteria}"
                )
            else:
                names = sorted(
                    {
                        str(assertion["name"])
                        for assertion in payload["assertions"]
                        if not assertion["passed"]
                    }
                )
                print(
                    f"PASS {case_name} {CRITERIA[expected_criterion]}: "
                    f"failed alone and was named ({', '.join(names)})"
                )
    if failures:
        for failure in failures:
            print(f"FAIL selftest: {failure}", file=sys.stderr)
        return 1
    print(
        f"ok: public-bar selftest (2 good, {len(cases) - 2} "
        "criterion-isolated failures)"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=Path("public-bar.toml"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/public-bar.md"))
    parser.add_argument("--lane", choices=("static", "browser", "all"), default="all")
    parser.add_argument("--base-ref", action="append", default=[])
    parser.add_argument("--edge-binary", default="expanso-edge")
    parser.add_argument("--cli-binary", default="expanso-cli")
    parser.add_argument("--schema-dir", type=Path)
    parser.add_argument("--teardown-only", action="store_true")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run known-good and criterion-isolated fixture repositories",
    )
    parser.add_argument("--version", action="version", version=PUBLIC_BAR_VERSION)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    if args.selftest:
        return run_selftest(script_dir)
    repo = args.repo.resolve()
    manifest_path = (
        args.manifest if args.manifest.is_absolute() else repo / args.manifest
    )
    report = args.report if args.report.is_absolute() else repo / args.report
    schema_dir = args.schema_dir.resolve() if args.schema_dir else script_dir
    audit = Audit(repo=repo, report=report, lane=args.lane)
    if args.teardown_only:
        return teardown_only(repo, manifest_path)
    audit.metadata = {
        "expanso-edge": command_version(args.edge_binary, "version"),
        "expanso-cli": command_version(args.cli_binary, "version"),
        "playwright": importlib.metadata.version("playwright"),
        "just": command_version(just_binary() or "just", "--version"),
        "python": sys.version.split()[0],
    }
    try:
        manifest = load_manifest(
            repo,
            manifest_path,
            schema_dir / "public-bar.schema.json",
            audit,
        )
        if manifest and args.lane in {"static", "all"}:
            static_lane(
                repo,
                manifest,
                audit,
                args.edge_binary,
                args.cli_binary,
                schema_dir / "public-features.schema.json",
                args.base_ref,
            )
        if manifest and args.lane in {"browser", "all"}:
            static_failures = [
                item for item in audit.failed() if item.name != "browser-contract"
            ]
            if args.lane == "all" and static_failures:
                audit.add(
                    4,
                    "rendered-browser",
                    False,
                    "rendered browser did not start because the static lane failed",
                )
            elif audit.failed(4):
                audit.add(
                    4,
                    "rendered-browser",
                    False,
                    "rendered browser did not start because its contract failed",
                )
            else:
                browser_lane(repo, manifest, audit)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        audit.add(1, "internal", False, f"checker error: {error}")
    finally:
        write_report(audit)
    for criterion in CRITERIA:
        failures = audit.failed(criterion)
        if failures:
            print(
                f"FAIL {criterion} {CRITERIA[criterion]}: "
                + "; ".join(item.detail for item in failures),
                file=sys.stderr,
            )
    print(f"report: {audit.report}")
    return 1 if audit.failed() else 0


if __name__ == "__main__":
    raise SystemExit(main())
