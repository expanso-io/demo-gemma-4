#!/usr/bin/env python3
"""Allocate persistent local TCP ports without starting or stopping services."""

import argparse
import fcntl
import json
import os
import re
import socket
import tempfile
from contextlib import contextmanager
from pathlib import Path

DEFAULT = Path(__file__).with_name("demo-ports.json")
NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
SLUG = re.compile(r"demo-[a-z0-9][a-z0-9-]*\Z")


def manifest(path):
    data = json.loads(path.read_text())
    if data.get("version") == 1:
        records = data["demos"]
        if len(records) != 1:
            raise ValueError(f"{path}: legacy snapshot must contain one demo")
        demo, record = next(iter(records.items()))
        data = {"version": 2, "demo": demo, "ports": record["ports"]}
    if data.get("version") != 2 or not SLUG.fullmatch(data.get("demo", "")):
        raise ValueError(f"{path}: invalid manifest version or demo name")
    values = data.get("ports")
    if not isinstance(values, dict):
        raise ValueError(f"{path}: ports must be an object")
    for name, value in values.items():
        if not NAME.fullmatch(name) or (
            value is not None and (type(value) is not int or not 1024 <= value <= 65535)
        ):
            raise ValueError(f"{path}: invalid service {name}")
    return data


def _bound(port, kind):
    # Probe both stacks: wildcard binding detects loopback and other interfaces.
    for family, address in (
        (socket.AF_INET, "0.0.0.0"),
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET6, "::"),
        (socket.AF_INET6, "::1"),
    ):
        try:
            with socket.socket(family, kind) as probe:
                if kind == socket.SOCK_STREAM:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if family == socket.AF_INET6:
                    probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                probe.bind((address, port))
                if kind == socket.SOCK_STREAM:
                    probe.listen(1)
        except OSError as error:
            if error.errno in (98, 48, 13):
                return True
    return False


def bound(port):
    return _bound(port, socket.SOCK_STREAM) or _bound(port, socket.SOCK_DGRAM)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def atomic_write(path, data):
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=path.name + ".", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve(
    demo_dir, *, allow_bound=False, reassign=False, limits=(20000, 31999), services=None
):
    demo_dir = demo_dir.resolve()
    selected = manifest(demo_dir / "ports.json")
    if services is not None and not set(services) <= selected["ports"].keys():
        raise ValueError("unknown service selected for preflight")
    kit = demo_dir.parent / "_demo-kit"
    workspace = kit.is_dir()
    state_path = (kit if workspace else demo_dir) / ".demo-port-state.json"
    if os.environ.get("DEMO_PORT_STATE"):
        state_path = Path(os.environ["DEMO_PORT_STATE"])
        if not state_path.is_absolute():
            raise ValueError("DEMO_PORT_STATE must be an absolute path")
    candidates = (
        sorted(demo_dir.parent.glob("demo-*/ports.json"))
        if workspace
        else [demo_dir / "ports.json"]
    )
    # Parse before mutating; malformed sibling manifests cannot hide allocations.
    manifests = {}
    for path in candidates:
        item = manifest(path)
        key = str(path.parent.resolve())
        manifests[key] = item
    manifests[str(demo_dir)] = selected
    with locked(state_path):
        state = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else {"version": 2, "demos": {}}
        )
        if state.get("version") != 2 or not isinstance(state.get("demos"), dict):
            raise ValueError("invalid persistent port state")
        records = state["demos"]
        used = set()
        for record in records.values():
            ports = record.get("ports", {})
            if not isinstance(ports, dict) or any(
                not NAME.fullmatch(n) or type(p) is not int or not 1024 <= p <= 65535
                for n, p in ports.items()
            ):
                raise ValueError("invalid persistent allocation")
            if used.intersection(ports.values()) or len(set(ports.values())) != len(
                ports
            ):
                raise ValueError("duplicate persistent allocation")
            used.update(ports.values())
        for key in list(records):
            if not Path(key).exists() and not any(
                bound(p) for p in records[key]["ports"].values()
            ):
                del records[key]
        if reassign:
            old = records.get(str(demo_dir), {}).get("ports", {})
            if any(bound(p) for p in old.values()):
                raise ValueError("stop the demo before explicit reassignment")
            records.pop(str(demo_dir), None)
        used = {p for record in records.values() for p in record["ports"].values()}
        # Target first; every existing allocation remains unchanged.
        order = [str(demo_dir)] + [key for key in manifests if key != str(demo_dir)]
        for key in order:
            item = manifests[key]
            record = records.setdefault(key, {"demo": item["demo"], "ports": {}})
            for service, preferred in item["ports"].items():
                if service in record["ports"]:
                    continue
                if (
                    preferred is not None
                    and preferred not in used
                    and not bound(preferred)
                ):
                    chosen = preferred
                else:
                    chosen = next(
                        (
                            p
                            for p in range(limits[0], limits[1] + 1)
                            if p not in used and not bound(p)
                        ),
                        None,
                    )
                if chosen is None:
                    raise ValueError(
                        "port range exhausted; remove retired demo folders or explicitly reassign"
                    )
                record["ports"][service] = chosen
                used.add(chosen)
        ports = {
            name: records[str(demo_dir)]["ports"][name] for name in selected["ports"]
        }
        atomic_write(state_path, state)
        if not allow_bound:
            busy = [
                f"{name}={port}"
                for name, port in ports.items()
                if (services is None or name in services) and bound(port)
            ]
            if busy:
                raise ValueError(
                    "assigned port occupied: "
                    + ", ".join(busy)
                    + "; run just down or inspect lsof -iTCP:<port>. URL preserved; "
                    "use explicit reassign only after stopping the demo"
                )
        return ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("resolve", "reassign"):
        entry = sub.add_parser(command)
        entry.add_argument("--demo-dir", type=Path, required=True)
        entry.add_argument("--format", choices=("shell", "json"), default="json")
        entry.add_argument("--allow-bound", action="store_true")
        entry.add_argument(
            "--service", action="append", help="check occupancy only for this service"
        )
    check = sub.add_parser("check")
    check.add_argument("--demos-root", type=Path)
    sub.add_parser("list")
    args = parser.parse_args()
    try:
        if args.command in ("resolve", "reassign"):
            ports = resolve(
                args.demo_dir,
                allow_bound=args.allow_bound,
                reassign=args.command == "reassign",
                services=args.service,
            )
            print(
                "\n".join(f"{n}={p}" for n, p in ports.items())
                if args.format == "shell"
                else json.dumps(ports)
            )
        else:
            if args.command == "check" and args.demos_root:
                files = sorted(args.demos_root.glob("demo-*/ports.json"))
                for path in files:
                    manifest(path)
                print(f"PASS: {len(files)} demo manifests")
                return
            data = json.loads(args.registry.read_text())
            if data.get("version") != 2:
                raise ValueError("registry must be version 2")
            for slug, record in data["demos"].items():
                values = record.get("ports", {})
                if not isinstance(values, dict) or any(
                    not NAME.fullmatch(n)
                    or (
                        p is not None and (type(p) is not int or not 1024 <= p <= 65535)
                    )
                    for n, p in values.items()
                ):
                    raise ValueError("invalid registry service")
                if not SLUG.fullmatch(slug):
                    raise ValueError("invalid demo name")
                if args.command == "list":
                    print(f"{slug}: {record.get('integration', 'manifest')}")
            if args.command == "check":
                print(f"PASS: {len(data['demos'])} demo manifest records")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
