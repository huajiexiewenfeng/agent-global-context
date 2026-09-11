"""Offline, synthetic-only AGC experiment records; no storage or model clients.

Metrics are supplied by an external adjudicator, never inferred here. Content
hashes establish consistency, not authenticity or evidence of semantic quality.
This development harness cannot execute holdouts or authorize production changes.
"""

from __future__ import annotations

import hashlib
import json
from time import monotonic
from typing import Callable


METRICS = (
    "long_term_errors",
    "durable_omissions",
    "unsupported_claims",
    "classification_errors",
)
IDENTITY_FIELDS = {
    "model", "model_config", "schema", "profile", "agc_version", "prompt"
}


def _copy(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError("experiment_invalid_json") from error


def _digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _identity(value) -> None:
    if not isinstance(value, dict) or set(value) != IDENTITY_FIELDS or not all(_text(v) for v in value.values()):
        raise ValueError("experiment_invalid_identity")


def validate_suite(cases: list[dict]) -> None:
    """Reject exact-content and declared-family split leakage before execution."""
    if not isinstance(cases, list) or not cases:
        raise ValueError("experiment_empty_suite")
    ids, families, contents = set(), {}, {}
    for case in cases:
        if not isinstance(case, dict) or not all(_text(case.get(k)) for k in ("case_id", "family_id", "input")):
            raise ValueError("experiment_invalid_case")
        split = case.get("split")
        if split not in ("development", "validation", "holdout") or case.get("synthetic") is not True:
            raise ValueError("experiment_invalid_case")
        if case["case_id"] in ids:
            raise ValueError("experiment_duplicate_case")
        ids.add(case["case_id"])
        for registry, key in ((families, case["family_id"]), (contents, case["input"].strip())):
            if key in registry and registry[key] != split:
                raise ValueError("experiment_split_leakage")
            registry[key] = split
    _copy(cases)


def run_batch(cases: list[dict], *, split: str, identity: dict, extractor: Callable) -> dict:
    """Execute only explicitly supplied synthetic inputs, with no answer labels."""
    validate_suite(cases)
    _identity(identity)
    identity = _copy(identity)
    if split not in ("development", "validation"):
        raise ValueError("experiment_holdout_requires_independent_boundary")
    selected = sorted((_copy(c) for c in cases if c["split"] == split), key=lambda c: c["case_id"])
    if not selected:
        raise ValueError("experiment_empty_split")
    items = []
    for case in selected:
        started = monotonic()
        try:
            output = extractor({"case_id": case["case_id"], "input": case["input"]})
            if not isinstance(output, dict):
                raise ValueError("invalid_output")
            output = _copy(output)
            status = "completed"
        except Exception:
            output, status = None, "execution_error"
        elapsed = (monotonic() - started) * 1000
        item = {"case_id": case["case_id"], "status": status, "output": output}
        item["output_ref"] = _digest(item)
        item["duration_ms"] = elapsed
        item["usage"] = None  # No known usage: never pretend a failed call was free.
        items.append(item)
    record = {
        "schema": "agc.experiment.offline.v1",
        "claim": "offline-record-only",
        "split": split,
        "dataset_digest": _digest(selected),
        "identity": _copy(identity),
        "items": items,
    }
    record["run_id"] = _digest(record)
    return record


def _check_run(run: dict) -> None:
    if not isinstance(run, dict):
        raise ValueError("experiment_invalid_run")
    if run.get("run_id") != _digest({k: v for k, v in run.items() if k != "run_id"}):
        raise ValueError("experiment_run_digest_mismatch")
    _identity(run.get("identity"))
    if run.get("schema") != "agc.experiment.offline.v1" or run.get("claim") != "offline-record-only":
        raise ValueError("experiment_invalid_run")
    items = run.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("experiment_invalid_run")
    ids = set()
    for item in items:
        if not isinstance(item, dict) or not _text(item.get("case_id")) or item["case_id"] in ids:
            raise ValueError("experiment_invalid_item")
        ids.add(item["case_id"])
        if item.get("status") not in ("completed", "execution_error"):
            raise ValueError("experiment_invalid_item")
        if item.get("output_ref") != _digest({k: item.get(k) for k in ("case_id", "status", "output")}):
            raise ValueError("experiment_output_digest_mismatch")


def compare_runs(baseline: dict, candidate: dict, assessments: list[dict]) -> dict:
    """Compare explicitly adjudicated counts; even improvement requires a rerun.

Assessments must cover every output on each side exactly once and cite that
output. These structural checks cannot certify a reviewer or semantic labels.
"""
    for run in (baseline, candidate):
        _check_run(run)
    for field in ("split", "dataset_digest"):
        if baseline.get(field) != candidate.get(field):
            raise ValueError("experiment_noncomparable_runs")
    for field in IDENTITY_FIELDS - {"prompt"}:
        if baseline["identity"][field] != candidate["identity"][field]:
            raise ValueError("experiment_noncomparable_runs")
    if [i["case_id"] for i in baseline["items"]] != [i["case_id"] for i in candidate["items"]]:
        raise ValueError("experiment_noncomparable_cases")
    report = {
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "dataset_digest": baseline["dataset_digest"],
        "split": baseline["split"],
        "production_authorized": False,
        "semantic_validation": "external-adjudication-required",
        "case_count": len(baseline["items"]),
        "totals": None,
        "case_deltas": [],
        "context_digest": _digest({
            "dataset": baseline["dataset_digest"],
            "split": baseline["split"],
            "conditions": {k: baseline["identity"][k] for k in IDENTITY_FIELDS - {"prompt"}},
        }),
    }
    if any(item["status"] != "completed" for run in (baseline, candidate) for item in run["items"]):
        report.update(recommendation="inconclusive", reason="execution_error")
    else:
        if baseline["run_id"] == candidate["run_id"]:
            raise ValueError("experiment_distinct_runs_required")
        expected = {(run["run_id"], item["case_id"]): item for run in (baseline, candidate) for item in run["items"]}
        checked = {}
        if not isinstance(assessments, list):
            raise ValueError("experiment_invalid_assessment")
        for row in assessments:
            if not isinstance(row, dict) or not all(_text(row.get(f)) for f in ("run_id", "case_id", "reviewer", "rationale")):
                raise ValueError("experiment_invalid_assessment")
            key = row["run_id"], row["case_id"]
            if key not in expected or key in checked:
                raise ValueError("experiment_assessment_coverage")
            if row.get("evidence_refs") != [expected[key]["output_ref"]]:
                raise ValueError("experiment_evidence_outside_case")
            metrics = row.get("metrics")
            if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
                raise ValueError("experiment_invalid_metrics")
            if any(type(v) is not int or v < 0 for v in metrics.values()):
                raise ValueError("experiment_invalid_metrics")
            checked[key] = metrics
        if set(checked) != set(expected):
            raise ValueError("experiment_assessment_coverage")
        totals = {side: {m: 0 for m in METRICS} for side in ("baseline", "candidate")}
        for item in baseline["items"]:
            case_id = item["case_id"]
            left, right = (checked[(r["run_id"], case_id)] for r in (baseline, candidate))
            report["case_deltas"].append({"case_id": case_id, "delta": {m: right[m] - left[m] for m in METRICS}})
            for m in METRICS:
                totals["baseline"][m] += left[m]
                totals["candidate"][m] += right[m]
        report["totals"] = totals
        report["assessment_digest"] = _digest(sorted(assessments, key=lambda r: (r["run_id"], r["case_id"])))
        if any(totals["candidate"][m] > totals["baseline"][m] for m in METRICS):
            report.update(recommendation="reject", reason="regression")
        elif totals["candidate"]["long_term_errors"] < totals["baseline"]["long_term_errors"]:
            report.update(recommendation="rerun_required", reason="target_improved_once")
        else:
            report.update(recommendation="inconclusive", reason="no_target_improvement")
    report["report_id"] = _digest(report)
    return report


def round_receipt(report: dict, *, proposal_ref: str, lesson: str, previous: dict | None = None) -> dict:
    """Build an idempotent artifact, not a persisted decision or a release gate."""
    if not _text(proposal_ref) or not _text(lesson):
        raise ValueError("experiment_proposal_and_lesson_required")
    if not isinstance(report, dict) or report.get("report_id") != _digest({k: v for k, v in report.items() if k != "report_id"}):
        raise ValueError("experiment_report_digest_mismatch")
    previous_id = None
    if previous is not None:
        if not isinstance(previous, dict) or previous.get("receipt_id") != _digest({k: v for k, v in previous.items() if k != "receipt_id"}):
            raise ValueError("experiment_previous_receipt_invalid")
        if previous.get("context_digest") != report.get("context_digest"):
            raise ValueError("experiment_previous_context_mismatch")
        previous_id = previous["receipt_id"]
    receipt = {
        "proposal_ref": proposal_ref,
        "report_id": report["report_id"],
        "recommendation": report["recommendation"],
        "lesson": lesson,
        "previous_receipt_id": previous_id,
        "context_digest": report["context_digest"],
        "production_authorized": False,
        "persistence": "not-written",
    }
    receipt["receipt_id"] = _digest(receipt)
    return receipt
