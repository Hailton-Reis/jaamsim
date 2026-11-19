#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
"""JAAM-AI C2 preflight: manifest-pinned, offline, read-only document retrieval.

The C2 retriever is intentionally independent of JaamSim state and LLM modules.
Neither a network client nor a command/model tool dispatcher is provided.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any

SCHEMA = "jaam.ai.c2.corpus_manifest.v1"
RECEIPT_SCHEMA = "jaam.ai.c2.search_receipt.v2"
ALLOWED_SUFFIXES = frozenset({".md", ".txt"})
MAX_FILE_BYTES = 1_048_576
MAX_MANIFEST_BYTES = 131_072
MAX_CORPUS_BYTES = 8 * MAX_FILE_BYTES
MAX_DOCUMENTS = 64
MAX_PASSAGES = 20_000
MAX_QUERY_CHARS = 2_000
CAPABILITY = {
    "arm_id": "C2", "model_access": True, "retrieval": True,
    "search_docs": True, "read_tools": [], "proposal_tool": False,
    "write_model": False, "write_policy": "NO_WRITE_CAPABILITY",
}


class ContractError(ValueError):
    """A manifest, query or output violates the documented C2 contract."""


class AccessDenied(PermissionError):
    """An operation or source is outside C2's allowlist."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _tokens(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return set(re.findall(r"[a-z0-9]{2,}", plain))


def _relative_document_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ContractError("invalid source path")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise AccessDenied("absolute path not allowed")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise AccessDenied("unsafe path segment")
    path = Path(value)
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise AccessDenied("C2 source must be a declared .md or .txt document")
    return path


def _read_fd(fd: int, limit: int) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ContractError("non-regular or oversized input")
    chunks: list[bytes] = []
    size = 0
    while True:
        part = os.read(fd, min(65_536, limit + 1 - size))
        if not part:
            break
        size += len(part)
        if size > limit:
            raise ContractError("input grew beyond configured limit")
        chunks.append(part)
    return b"".join(chunks)


def _no_reparse(path: Path) -> None:
    """Best-effort Windows fallback; POSIX uses descriptor-relative O_NOFOLLOW."""
    if path.is_symlink():
        raise AccessDenied("symbolic link in source path")
    info = path.lstat()
    attrs = getattr(info, "st_file_attributes", 0)
    if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise AccessDenied("reparse point in source path")


def _open_posix_absolute(path: Path, final_flags: int) -> int:
    """Resolve every component through directory descriptors, never symlinks."""
    path = path.absolute()
    directory = os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW
    components = path.parts[1:]
    fd = os.open(path.anchor, directory)
    try:
        if not components:
            return fd
        for component in components[:-1]:
            next_fd = os.open(component, directory, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        result = os.open(components[-1], final_flags | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd)
        return result
    except BaseException:
        os.close(fd)
        raise


def _open_declared(root: Path, relative: Path, limit: int) -> bytes:
    """Read pinned content. On POSIX, directory handles prevent symlink races."""
    _no_reparse(root)
    if not root.is_dir():
        raise AccessDenied("corpus root must be a real directory")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if os.name != "nt" and nofollow and directory:
        handles: list[int] = []
        try:
            current = _open_posix_absolute(root, os.O_RDONLY | directory)
            handles.append(current)
            for segment in relative.parts[:-1]:
                current = os.open(segment, os.O_RDONLY | directory | nofollow, dir_fd=current)
                handles.append(current)
            fd = os.open(relative.parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
            handles.append(fd)
            return _read_fd(fd, limit)
        except OSError as exc:
            raise AccessDenied("source cannot be securely opened") from exc
        finally:
            for fd in reversed(handles):
                os.close(fd)
    # On Windows os.open cannot guarantee no-follow against concurrent junction
    # replacement; this fallback is preflight only, not a hostile-host boundary.
    current = root
    for part in relative.parts:
        current = current / part
        _no_reparse(current)
    try:
        fd = os.open(current, os.O_RDONLY | nofollow | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise AccessDenied("source cannot be opened") from exc
    try:
        return _read_fd(fd, limit)
    finally:
        os.close(fd)


def _load_manifest(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ContractError("manifest must be a real file")
    _no_reparse(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        if os.name != "nt" and nofollow and hasattr(os, "O_DIRECTORY"):
            fd = _open_posix_absolute(path, os.O_RDONLY)
        else:
            fd = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise AccessDenied("manifest cannot be securely opened") from exc
    try:
        return _read_fd(fd, MAX_MANIFEST_BYTES)
    finally:
        os.close(fd)


def _passages(text: str) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    start = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not buffer:
                start = lineno
            buffer.append(line)
            if len(buffer) == 12:
                chunks.append((start, lineno, "\n".join(buffer)))
                buffer = []
        elif buffer:
            chunks.append((start, lineno - 1, "\n".join(buffer)))
            buffer = []
    if buffer:
        chunks.append((start, start + len(buffer) - 1, "\n".join(buffer)))
    return chunks


class C2ReadOnlyRetriever:
    """Fixed capability boundary: exactly one callable tool, `search_docs`."""

    def __init__(self, corpus_root: Path, manifest_path: Path):
        self.root = Path(corpus_root).absolute()
        manifest_raw = _load_manifest(Path(manifest_path))
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ContractError("invalid manifest JSON") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise ContractError("manifest schema mismatch")
        version = manifest.get("corpus_version")
        docs = manifest.get("documents")
        if not isinstance(version, str) or not version.strip():
            raise ContractError("corpus_version required")
        if not isinstance(docs, list) or not 1 <= len(docs) <= MAX_DOCUMENTS:
            raise ContractError("document count outside limits")
        self.corpus_version = version
        self.manifest_sha256 = sha256(manifest_raw)
        self.entries: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        corpus_size = 0
        for doc in docs:
            if not isinstance(doc, dict):
                raise ContractError("invalid manifest document")
            source_id = doc.get("source_id")
            expected_hash = doc.get("sha256")
            if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_id):
                raise ContractError("invalid source_id")
            if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
                raise ContractError("invalid sha256")
            relative = _relative_document_path(doc.get("path"))
            if source_id in seen_ids or str(relative) in seen_paths:
                raise ContractError("duplicate source_id or source path")
            seen_ids.add(source_id)
            seen_paths.add(str(relative))
            raw = _open_declared(self.root, relative, MAX_FILE_BYTES)
            if sha256(raw) != expected_hash:
                raise ContractError(f"source SHA mismatch: {source_id}")
            corpus_size += len(raw)
            if corpus_size > MAX_CORPUS_BYTES:
                raise ContractError("corpus exceeds memory budget")
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ContractError("source must be UTF-8") from exc
            if "\x00" in content:
                raise ContractError("NUL in text source")
            for start, end, passage in _passages(content):
                if len(self.entries) >= MAX_PASSAGES:
                    raise ContractError("too many passages")
                self.entries.append({
                    "source_id": source_id, "path": relative.as_posix(),
                    "document_sha256": expected_hash, "start_line": start,
                    "end_line": end, "passage": passage,
                    "passage_sha256": sha256(passage.encode("utf-8")),
                    "_tokens": _tokens(passage),
                })
        # All retrieval is performed against this immutable in-memory snapshot.
        self.corpus_sha256 = sha256(json.dumps(
            [(e["source_id"], e["document_sha256"]) for e in self.entries],
            ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"))

    def invoke(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name != "search_docs":
            raise AccessDenied("only search_docs is exposed in C2")
        if set(kwargs) - {"query", "top_k"}:
            raise ContractError("unrecognized retrieval arguments")
        return self.search_docs(kwargs.get("query"), kwargs.get("top_k", 3))

    def search_docs(self, query: str, top_k: int = 3) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise ContractError("query must contain 1-2000 characters")
        if type(top_k) is not int or not 1 <= top_k <= 10:
            raise ContractError("top_k must be an integer between 1 and 10")
        query_tokens = _tokens(query)
        ranked = []
        for entry in self.entries:
            overlap = sorted(query_tokens & entry["_tokens"])
            if overlap:
                ranked.append((len(overlap), entry, overlap))
        ranked.sort(key=lambda row: (-row[0], row[1]["source_id"], row[1]["start_line"]))
        hits = []
        for count, entry, terms in ranked[:top_k]:
            hits.append({**{key: value for key, value in entry.items() if key != "_tokens"},
                         "matched_tokens": terms, "lexical_score": count,
                         "trust_label": "UNTRUSTED_RETRIEVED_DOCUMENT",
                         "citation": f"{entry['source_id']}:L{entry['start_line']}-L{entry['end_line']}"})
        return {
            "schema": RECEIPT_SCHEMA, "mode": "C2_RETRIEVAL_ONLY_NO_MODEL_EXECUTION",
            "capability": dict(CAPABILITY), "retrieval_method": "deterministic_lexical_overlap",
            "corpus_version": self.corpus_version, "manifest_sha256": self.manifest_sha256,
            "corpus_sha256": self.corpus_sha256, "query_sha256": sha256(query.encode("utf-8")),
            "retrieval_happened": True, "hits": hits, "no_evidence": not hits,
            "inline_context_is_retrieved_evidence": False,
            "state_tool_calls": 0, "model_calls": 0, "write_model": False,
            "g0_g2": "PENDING", "scientific_status": "PREFLIGHT_ONLY_NOT_CONFIRMATORY",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="JAAM-AI C2 offline document retrieval preflight")
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--tool", default="search_docs")
    args = parser.parse_args()
    try:
        tool = C2ReadOnlyRetriever(args.corpus_root, args.manifest)
        print(json.dumps(tool.invoke(args.tool, query=args.query, top_k=args.top_k),
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (AccessDenied, ContractError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
