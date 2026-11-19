#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
"""Preflight-only retrieval evaluation. Not a confirmatory experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from c2_retrieval import C2ReadOnlyRetriever, ContractError

SCHEMA = "jaam.ai.c2.synthetic_eval.v1"


def evaluate(retriever: C2ReadOnlyRetriever, cases: list[dict[str, Any]], top_k: int = 3) -> dict[str, Any]:
    if not isinstance(cases, list) or not cases or len(cases) > 200:
        raise ContractError("expected 1..200 synthetic evaluation cases")
    details = []
    recall_sum = 0.0
    reciprocal_sum = 0.0
    empty_correct = 0
    total_relevant = 0
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("task_id"), str):
            raise ContractError("each task requires an ID")
        targets = case.get("expected_source_ids")
        if not isinstance(targets, list) or len(targets) > 10 or any(not isinstance(t, str) for t in targets):
            raise ContractError("invalid expected document IDs")
        receipt = retriever.search_docs(case.get("query"), top_k)
        # Recall@k here is document-level; repeated passages from one document
        # count as one retrieved source (passage-level top-k remains unchanged).
        predicted = list(dict.fromkeys(item["source_id"] for item in receipt["hits"]))
        relevant = set(targets)
        matched = len(set(predicted) & relevant)
        recall = matched / len(relevant) if relevant else None
        first_rank = next((index for index, item in enumerate(predicted, 1) if item in relevant), None)
        reciprocal = (1 / first_rank) if first_rank is not None else 0.0
        if relevant:
            recall_sum += recall
            reciprocal_sum += reciprocal
            total_relevant += 1
        else:
            empty_correct += int(not predicted)
        details.append({"task_id": case["task_id"], "expected_source_ids": sorted(relevant),
                        "retrieved_source_ids": predicted, "recall_at_k": recall,
                        "reciprocal_rank": reciprocal if relevant else None,
                        "correct_abstention": (not predicted) if not relevant else None})
    negatives = len(cases) - total_relevant
    return {"schema": SCHEMA, "status": "SYNTHETIC_PREFLIGHT_ONLY",
            "n_cases": len(cases), "n_positive": total_relevant, "n_negative": negatives,
            "top_k": top_k, "mean_recall_at_k": recall_sum / total_relevant if total_relevant else None,
            "mrr_at_k": reciprocal_sum / total_relevant if total_relevant else None,
            "negative_abstention_rate": empty_correct / negatives if negatives else None,
            "model_calls": 0, "state_tool_calls": 0, "g0_g2": "PENDING", "cases": details}


def main() -> int:
    parser = argparse.ArgumentParser(description="C2 synthetic preflight retrieval evaluation")
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    try:
        tool = C2ReadOnlyRetriever(args.corpus_root, args.manifest)
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        result = evaluate(tool, cases, args.top_k)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
