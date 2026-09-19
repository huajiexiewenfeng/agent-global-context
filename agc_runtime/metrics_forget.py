"""Post-commit cleanup intents owned by the existing Capture forget transaction.

Call only while holding root_write_lock AND capture_write_lock. No model, source
session read, arbitrary path in intent, or independent authorization mechanism.
Source invalidation commits before any external deletion. Failed cleanup retains
its intent; recovery verifies source invalidation and the original ledger identity.
"""
from contextlib import nullcontext
from itertools import islice
import re

from agc_runtime.capture_contracts import CaptureReceipt,CaptureSuppressionTombstone,receipt_id_for
from agc_runtime.capture_transaction import safe_unlink
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_host import cleanup_ledger,cleanup_identity
from agc_runtime.metrics_models import canonical
from agc_runtime.metrics_result_reader import _read


def _identity(ledger):
    return cleanup_identity(ledger)


def prepare_intent(paths,receipt_id):
    if receipt_id is None: return None
    if not re.fullmatch(r'cr_[a-f0-9]{64}',receipt_id): raise ValueError('metrics_cleanup_receipt_invalid')
    ledger=cleanup_ledger(paths)
    if ledger is None: return None
    value=dict(schema_version=1,operation='metrics_cleanup',receipt_id=receipt_id,
               ledger_identity=_identity(ledger),authorization='explicit_user_request')
    return paths.capture.root/'metrics-cleanup'/(receipt_id+'.json'),value


def _source_invalidated(paths,receipt_id):
    # Caller already holds Capture's write lock; read_snapshot would re-enter it.
    # Read only validated receipt/tombstone metadata, never observation content.
    receipt_path=_root(paths.capture.receipts)/(receipt_id+'.json')
    if receipt_path.exists() or receipt_path.is_symlink():
        receipt=CaptureReceipt.from_mapping(_read(receipt_path))
        if receipt.receipt_id!=receipt_id: raise ValueError('cleanup_receipt_binding_invalid')
        if receipt.redacted_by_forget: return True
    tombstones=list(islice(_root(paths.capture.tombstones).iterdir(),10001))
    if len(tombstones)>10000: raise ValueError('cleanup_tombstones_oversized')
    for path in tombstones:
        item=CaptureSuppressionTombstone.from_mapping(_read(path))
        if path.name!=item.tombstone_id+'.json': raise ValueError('cleanup_tombstone_binding_invalid')
        if receipt_id_for(item.capture_key)==receipt_id: return True
    return False


def recover_pending(paths):
    """Finish previously committed intents; False means deferred, never complete."""
    root=paths.capture.root/'metrics-cleanup'
    if not root.exists() and not root.is_symlink(): return True
    root=_root(root)
    intents=list(islice(root.iterdir(),1001))
    if len(intents)>1000 or any(not re.fullmatch(r'cr_[a-f0-9]{64}\.json',p.name) for p in intents):
        raise ValueError('metrics_cleanup_intent_inventory_invalid')
    if not intents: return True
    ledger=cleanup_ledger(paths)
    if ledger is None: return False
    for path in sorted(intents):
        value=_read(path)
        expected=dict(schema_version=1,operation='metrics_cleanup',receipt_id=path.stem,
                      ledger_identity=_identity(ledger),authorization='explicit_user_request')
        if canonical(value)!=canonical(expected) or not _source_invalidated(paths,path.stem):
            return False
        try:
            registry=ledger/'artifact-registry'
            bindings=ledger/'source-bindings'
            reports=ledger/'report-registry'
            if (not registry.exists() and not registry.is_symlink()
                    and not bindings.exists() and not bindings.is_symlink()
                    and not reports.exists() and not reports.is_symlink()):
                # A provisioned host which has never prepared or executed a plan.
                safe_unlink(path)
                continue
            from agc_runtime.metrics_cleanup_candidates import cleanup_candidates
            from agc_runtime.metrics_cleanup_apply import apply_cleanup
            candidates=cleanup_candidates(ledger,path.stem)
            result=apply_cleanup(ledger=ledger,snapshot=candidates,
                                 authorization='explicit_user_request',commit_guard=nullcontext)
            if result['status']!='selected_artifacts_removed': return False
            from agc_runtime.metrics_report_artifacts import cleanup_reports
            cleanup_reports(ledger,path.stem)
            safe_unlink(path)
        except (OSError,ValueError,KeyError,TypeError):
            return False
    return True
