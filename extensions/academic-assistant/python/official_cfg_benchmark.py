#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""Audit an operator-supplied official JaamSim CFG ZIP without redistributing it.

The exact 2026-03 corpus contains 90 CFGs, including 20 BigLean models with
separate CC BY-ND licensing. This script writes counts and diagnostics only.
It never republishes CFG bytes. Supply the ZIP and its SHA-256 index locally.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

import jaamsim_cfg_to_snapshot as bridge


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_archive_name(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(parts) and not name.startswith("/") and "\\" not in name and all(
        part not in {"", ".", ".."} for part in parts
    ) and name.lower().endswith(".cfg")


def read_index(index_path: Path) -> dict[str, tuple[int, str]]:
    index: dict[str, tuple[int, str]] = {}
    with index_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"relative_path", "size_bytes", "sha256"} <= set(reader.fieldnames or []):
            raise ValueError("Index requires relative_path,size_bytes,sha256 headers")
        for row in reader:
            name = row["relative_path"]
            digest = row["sha256"].lower()
            if not safe_archive_name(name) or name in index:
                raise ValueError(f"Unsafe or duplicate index path: {name!r}")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"Invalid index SHA-256 for {name!r}")
            index[name] = (int(row["size_bytes"]), digest)
    return index


def verify_archive(archive_path: Path, index: dict[str, tuple[int, str]]) -> dict[str, bytes]:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in entries]
        if any(not safe_archive_name(name) for name in names):
            raise ValueError("ZIP contains non-CFG or unsafe paths")
        if len(set(names)) != len(names) or set(names) != set(index):
            raise ValueError("ZIP entries do not match the canonical index exactly")
        documents: dict[str, bytes] = {}
        for entry in entries:
            data = archive.read(entry)
            expected_size, expected_sha = index[entry.filename]
            if len(data) != expected_size or sha256_bytes(data) != expected_sha:
                raise ValueError(f"Integrity mismatch: {entry.filename}")
            documents[entry.filename] = data
    return documents


def load_reference_parser(path: Path) -> Any:
    source_path = path.resolve()
    spec = importlib.util.spec_from_file_location("jaam_reference_for_benchmark", source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load reference parser: {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve module by this name
    spec.loader.exec_module(module)
    if not hasattr(module, "convert_cfg_to_snapshot"):
        raise ValueError("Reference parser lacks convert_cfg_to_snapshot")
    return module


def evaluate(parser: Any, files: dict[str, bytes]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    with tempfile.TemporaryDirectory(prefix="jaam-benchmark-") as temp:
        root = Path(temp)
        for relative_path, data in sorted(files.items()):
            local = root.joinpath(*PurePosixPath(relative_path).parts)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            try:
                snapshot = parser.convert_cfg_to_snapshot(local)
                components = snapshot.get("components", [])
                links = snapshot.get("connections", [])
                warnings = snapshot.get("parser_warnings", [])
                if not isinstance(warnings, list):
                    warnings = []
                warning_types = Counter(
                    str(item.get("type", "UNKNOWN"))
                    for item in warnings
                    if isinstance(item, dict)
                )
                warning_counts.update(warning_types)
                row = {
                    "ok": True,
                    "components": len(components),
                    "connections": len(links),
                    "resources": len(snapshot.get("resources", [])),
                    "metrics": len(snapshot.get("metrics", [])),
                    "warnings": dict(sorted(warning_types.items())),
                    "component_keys": sorted(
                        (str(item["id"]), str(item["type"])) for item in components
                    ),
                    "flow_edges": sorted(
                        (str(item["from"]), str(item["to"]), str(item.get("type", "")))
                        for item in links
                    ),
                }
                counts["parsed"] += 1
                counts["with_components"] += bool(components)
                counts["with_connections"] += bool(links)
                counts["components"] += len(components)
                counts["connections"] += len(links)
                counts["resources"] += row["resources"]
                counts["metrics"] += row["metrics"]
            except Exception as exc:
                row = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                counts["failed"] += 1
            rows[relative_path] = row
    return rows, {
        "totals": dict(counts),
        "warning_counts": dict(sorted(warning_counts.items())),
    }


def compare(bridge_rows: dict[str, dict[str, Any]], reference_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    missing_edges = 0
    missing_components = 0
    for name in sorted(reference_rows):
        new = bridge_rows[name]
        old = reference_rows[name]
        if not old["ok"] or not new["ok"]:
            continue
        missing_edge_set = set(map(tuple, old["flow_edges"])) - set(map(tuple, new["flow_edges"]))
        missing_component_set = set(map(tuple, old["component_keys"])) - set(map(tuple, new["component_keys"]))
        if missing_edge_set or missing_component_set or new["warnings"] != old["warnings"]:
            differences.append({
                "path": name,
                "missing_reference_edges": [list(x) for x in sorted(missing_edge_set)],
                "missing_reference_components": [list(x) for x in sorted(missing_component_set)],
                "new_warnings": new["warnings"],
                "reference_warnings": old["warnings"],
            })
        missing_edges += len(missing_edge_set)
        missing_components += len(missing_component_set)
    return {
        "missing_reference_edges": missing_edges,
        "missing_reference_components": missing_components,
        "files_with_structural_or_warning_differences": differences,
    }


def run_benchmark(
    archive_path: Path,
    index_path: Path,
    *,
    reference_parser_path: Path | None = None,
    expected_count: int = 90,
    min_with_components: int = 81,
    min_with_connections: int = 81,
    max_unsupported_flow: int = 0,
) -> dict[str, Any]:
    index = read_index(index_path)
    documents = verify_archive(archive_path, index)
    rows, summary = evaluate(bridge, documents)
    counts = summary["totals"]
    warnings = summary["warning_counts"]

    gates = {
        "index_exact_count": len(documents) == expected_count,
        "ingest_all": counts.get("parsed", 0) == len(documents),
        "components_min": counts.get("with_components", 0) >= min_with_components,
        "connections_min": counts.get("with_connections", 0) >= min_with_connections,
        "unsupported_flow_max": (
            warnings.get("UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET", 0)
            + warnings.get("UNPARSED_STATEMENT", 0)
        ) <= max_unsupported_flow,
    }
    comparison = None
    if reference_parser_path is not None:
        reference = load_reference_parser(reference_parser_path)
        reference_rows, reference_summary = evaluate(reference, documents)
        comparison = compare(rows, reference_rows)
        comparison["reference_summary"] = reference_summary
        gates["no_lost_reference_flow"] = comparison["missing_reference_edges"] == 0
        gates["no_lost_reference_components"] = comparison["missing_reference_components"] == 0

    # Keep the report small; never embed original CFG bytes in any JSON output.
    public_rows = {
        name: {key: value for key, value in data.items() if key not in {"component_keys", "flow_edges"}}
        for name, data in rows.items()
    }
    return {
        "format": "JAAM_AI_OFFICIAL_CFG_BENCHMARK_V1",
        "corpus": {
            "cohort": "JaamSim 2026-03 exact official CFG extracts",
            "file_count": len(documents),
            "archive_sha256": sha256_bytes(archive_path.read_bytes()),
            "index_sha256": sha256_bytes(index_path.read_bytes()),
            "license_note": "Mixed license: BigLean CC BY-ND 4.0; do not redistribute files",
        },
        "bridge_parser_sha256": sha256_bytes(Path(bridge.__file__).read_bytes()),
        "summary": summary,
        "gates": gates,
        "passed": all(gates.values()),
        "comparison": comparison,
        "models": public_rows,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Benchmark local CFG offline; no network or model inference")
    cli.add_argument("--archive", required=True, type=Path, help="Operator-provided official examples ZIP")
    cli.add_argument("--index", required=True, type=Path, help="official_examples_index.csv with per-file hashes")
    cli.add_argument("--reference-parser", type=Path, help="Optional separately preserved R001-v6 source .py")
    cli.add_argument("--report", required=True, type=Path, help="Output JSON path")
    cli.add_argument("--expected-count", type=int, default=90)
    cli.add_argument("--min-with-components", type=int, default=81)
    cli.add_argument("--min-with-connections", type=int, default=81)
    cli.add_argument("--max-unsupported-flow", type=int, default=0)
    args = cli.parse_args()

    report = run_benchmark(
        args.archive, args.index,
        reference_parser_path=args.reference_parser,
        expected_count=args.expected_count,
        min_with_components=args.min_with_components,
        min_with_connections=args.min_with_connections,
        max_unsupported_flow=args.max_unsupported_flow,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CFG_BENCHMARK passed={report['passed']} models={report['corpus']['file_count']}")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    print(f"Report: {args.report}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
