"""AGC-owned offline experiment bridges to optional evidence/knowledge providers.

No default stores, model clients, home discovery, automatic initialization or
production writes. Callers explicitly supply isolated services and Wiki scope.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agc_runtime.capture_experiment import _check_run, _copy, _digest, validate_suite


def _check_digest(record, field):
    if not isinstance(record, dict) or record.get(field) != _digest({k: v for k, v in record.items() if k != field}):
        raise ValueError("experiment_record_digest_mismatch")


class _Resolver:
    def __init__(self, reference, content):
        self.reference, self.content = _copy(reference), _copy(content)

    def resolve(self, reference):
        if reference != self.reference:
            raise ValueError("experiment_unknown_evidence")
        return _copy(self.content)


class _BoundJudge:
    def __init__(self, delegate):
        self.delegate = delegate
        self.judge_id = delegate.judge_id
        # Avoid reusing evaluations cached before this boundary guard existed.
        self.judge_version = "agc-bound-v1-" + _digest(delegate.judge_version)[7:39]

    def evaluate(self, *, case, profile, evidence):
        allowed = {r["ref"] for r in case["evidence_refs"]}
        result = self.delegate.evaluate(case=_copy(case), profile=_copy(profile), evidence=_copy(evidence))
        for item in (*result.dimensions, *result.findings):
            refs = item.get("evidence")
            if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                raise ValueError("experiment_invalid_citation")
            if len(refs) != len(set(refs)) or not set(refs) <= allowed:
                raise ValueError("experiment_evidence_outside_case")
        return result


def _emit(service, trace_id, event_type, payload):
    from agent_trace_runtime.models import PrincipalRef, TraceEvent

    service.emit(TraceEvent(
        schema_version="trace.v0.1", event_id="evt_" + uuid4().hex,
        trace_id=trace_id, span_id=trace_id, parent_span_id=None,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        event_type=event_type,
        source="principal" if event_type.startswith("agc.") else "runtime",
        principal_ref=PrincipalRef("agc.improvement-experiment", "harness"),
        payload=payload,
    ))


def evaluate_batch(run, cases, *, profile, judge, eval_service, eval_store, trace_service):
    """Evaluate a completed synthetic batch; trace only this evaluation stage."""
    _check_run(run)
    validate_suite(cases)
    selected = sorted((_copy(c) for c in cases if c["split"] == run["split"]), key=lambda c: c["case_id"])
    if _digest(selected) != run["dataset_digest"] or any(i["status"] != "completed" for i in run["items"]):
        raise ValueError("experiment_evidence_not_ready")
    run, profile = _copy(run), _copy(profile)
    guarded = _BoundJudge(judge)
    trace_id = "tr_" + uuid4().hex
    common = {"operation": "offline-evaluation", "run_id": run["run_id"]}
    _emit(trace_service, trace_id, "trace.root.started", common)
    records = []
    try:
        for source, item in zip(selected, run["items"]):
            if source["case_id"] != item["case_id"]:
                raise ValueError("experiment_case_alignment")
            content = {"input": source["input"], "output": item["output"], "case_id": item["case_id"]}
            reference = dict(schema_version="eval.evidence-ref.v0.1", provider="agc", kind="experiment-item",
                ref=item["output_ref"], digest=_digest(content), version="1")
            case_id = "evc_" + _digest([run["run_id"], item["case_id"]])[7:]
            case = dict(schema_version="eval.case.v0.1", case_id=case_id,
                subject=dict(principal_ref=dict(id="agc.improvement-experiment", kind="harness"),
                    capability="capture", operation="offline-experiment", implementation_version=run["identity"]["agc_version"]),
                profile_ref=dict(id=profile["profile_id"], version=profile["profile_version"]),
                evidence_refs=[reference], trace_snapshot=None, reference=None,
                metadata=dict(run_id=run["run_id"], sample_reason="synthetic-offline-integration"))
            result = eval_service.evaluate(case=case, profile=profile, resolver=_Resolver(reference, content), judge=guarded, store=eval_store)
            record = {"case_id": item["case_id"], "eval_case_id": case_id, "result_id": result["result_id"], "status": result["status"]}
            records.append(record)
            _emit(trace_service, trace_id, "agc.experiment.item.evaluated", {**common, **record})
        failed = any(r["status"] not in ("pass", "fail") for r in records)
        _emit(trace_service, trace_id, "trace.root.failed" if failed else "trace.root.completed",
            {**common, "evaluated_count": len(records), "error_code": "evaluation_error" if failed else None})
    except Exception:
        _emit(trace_service, trace_id, "trace.root.failed", {**common, "error_code": "experiment_evaluation_failed"})
        raise ValueError("experiment_evaluation_failed") from None
    batch = {"run_id": run["run_id"], "trace_id": trace_id, "profile_digest": _digest(profile),
        "items": records, "result_ids": [r["result_id"] for r in records], "claim": "provider-integration-only"}
    batch["batch_id"] = _digest(batch)
    return batch


def save_round(receipt, report, *, evaluation_batches, eval_store, trace_service, scope_root, profile_path):
    """Write one verified-reference, create-only Wiki record, never raw outputs.

Assessment counts remain external judgments. Provider scores are linked as
separate evidence, not silently converted into those counts or release approval.
"""
    from llm_wiki_runtime.runtime import write_record
    from llm_wiki_runtime.profile import load_active_profile

    active_profile = load_active_profile(Path(scope_root), Path(profile_path))
    rule = active_profile.write_rules.get("experiment_round")
    if (active_profile.id != "agc-improvement-experiment" or rule is None
            or rule.mode != "create_only"
            or rule.path != "domains/agc-improvement/rounds/{receipt_id}.json"):
        raise ValueError("experiment_wiki_profile_mismatch")

    _check_digest(receipt, "receipt_id")
    _check_digest(report, "report_id")
    if receipt.get("report_id") != report["report_id"] or receipt.get("production_authorized") is not False:
        raise ValueError("experiment_receipt_report_mismatch")
    expected = {report["baseline_run_id"], report["candidate_run_id"]}
    if len(evaluation_batches) != 2 or {b.get("run_id") for b in evaluation_batches} != expected:
        raise ValueError("experiment_evaluation_coverage")
    if len({b.get("profile_digest") for b in evaluation_batches}) != 1:
        raise ValueError("experiment_profile_mismatch")
    for batch in evaluation_batches:
        _check_digest(batch, "batch_id")
        items = batch.get("items", [])
        expected_cases = {item["case_id"] for item in report["case_deltas"]}
        if (len(items) != report["case_count"] or {item["case_id"] for item in items} != expected_cases
                or batch.get("result_ids") != [item["result_id"] for item in items]):
            raise ValueError("experiment_item_coverage")
        events = trace_service.events(batch["trace_id"])
        for item in batch["items"]:
            result = eval_store.get(item["result_id"])
            if result is None or result["case_id"] != item["eval_case_id"] or result["status"] != item["status"]:
                raise ValueError("experiment_missing_eval_result")
            if not any(e.event_type == "agc.experiment.item.evaluated" and e.payload.get("run_id") == batch["run_id"]
                       and e.payload.get("result_id") == item["result_id"] for e in events):
                raise ValueError("experiment_missing_trace_evidence")
    content = json.dumps({"schema": "agc.experiment.knowledge.v1", "receipt": receipt, "report": report,
        "evaluation_batches": evaluation_batches, "knowledge_status": "provisional", "production_authorized": False},
        ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    # Runtime owns Wiki paths/locks/writes. Only staging content lives outside it.
    scope_root = Path(scope_root)
    with tempfile.TemporaryDirectory(prefix="agc-round-", dir=scope_root) as staging:
        content_file = Path(staging) / "record.json"
        content_file.write_text(content, encoding="utf-8")
        saved = write_record(scope_root, Path(profile_path), "experiment_round",
            {"receipt_id": receipt["receipt_id"][7:]}, {}, content_file)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if saved.get("status") not in ("ok", "already_exists") or saved.get("checksum") != checksum:
        raise ValueError("experiment_wiki_conflict_or_write_failed")
    return saved
