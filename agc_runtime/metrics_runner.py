"""Bounded plan orchestration with verified reuse and shared send reservations.

The host owns a stable private ledger directory and actual user authorization.
A caller-selected new ledger is not a new authorization; this module does not
authenticate the caller or register a production host-wide ledger by itself.
"""
from contextlib import nullcontext

from agc_runtime.metrics_eval import check_authorization, validate_plan, judge_configuration
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_execution import execute_entry, _write, _now
from agc_runtime.metrics_judge_input import build_input
from agc_runtime.metrics_result_reader import verify_saved_step, EvidenceUnavailable
from agc_runtime.metrics_artifact_registry import verify_registration
from agc_runtime.metrics_dependencies import evaluation_dependencies


class _ReservedGateway:
    def __init__(self, gateway, ledger, plan, entry, directory, dependency_digest, require_source_binding):
        self.gateway, self.ledger, self.plan, self.entry = gateway, ledger, plan, entry
        self.directory, self.dependency_digest = directory, dependency_digest
        self.require_source_binding = require_source_binding

    @property
    def configuration(self):
        return self.gateway.configuration

    def evaluate(self, payload):
        root = _root(self.ledger)
        location = root/self.plan['plan_id']
        location.mkdir(exist_ok=True)
        location = _root(location)
        # Reserve before the external call. Failure or interruption cannot return
        # a slot; exclusive creation also arbitrates concurrent output folders.
        _write(location/(self.entry['entry_id']+'.json'), dict(
            schema_version='agc.metrics-send-reservation.v1',
            plan_id=self.plan['plan_id'], entry_id=self.entry['entry_id'],
            authorization_digest=self.plan['authorization_digest'], reserved_at=_now()))
        from agc_runtime.metrics_artifact_registry import register_execution_directory
        register_execution_directory(root, self.directory/self.entry['entry_id'],
            evaluation_dependencies(self.plan, self.entry['entry_id'], dependency_digest=self.dependency_digest),
            require_source_binding=self.require_source_binding)
        return self.gateway.evaluate(payload)


def run_plan(plan, *, directory, ledger_directory, consent_digest, gateway, resolve_case,
             require_source_binding=False,commit_guard=nullcontext):
    if not callable(commit_guard):
        raise ValueError('commit_guard_factory_required')
    checked = validate_plan(plan)
    check_authorization(checked, consent_digest, revoked_refs=[])
    if not callable(resolve_case):
        raise ValueError('live_case_resolver_required')
    if judge_configuration(gateway.configuration) != checked['judge']:
        raise ValueError('execution_configuration_mismatch')
    root, ledger = _root(directory), _root(ledger_directory)
    verified = {}
    rows = []
    for entry in checked['entries']:
        entry_id = entry['entry_id']
        prior = verified.get(entry['depends_on'])
        if entry['depends_on'] is not None and prior is None:
            rows.append(dict(entry_id=entry_id, status='dependency_unavailable'))
            continue
        dependency = prior['result'] if prior else None
        expected_dependencies = evaluation_dependencies(checked, entry_id,
            dependency_digest=dependency['result_digest'] if dependency else None)

        def verify_stored():
            verify_registration(ledger, root/entry_id, expected_dependencies,require_source_binding=require_source_binding)
            stored = verify_saved_step(checked, root, entry_id, resolve_case=resolve_case,
                                       ledger_directory=ledger,require_source_binding=require_source_binding)
            verify_registration(ledger, root/entry_id, expected_dependencies,require_source_binding=require_source_binding)
            return stored

        if (root/entry_id).exists():
            try:
                stored = verify_stored()
                if stored['status'] == 'usable_judgment':
                    verified[entry_id] = stored
                    status = 'reused'
                else:
                    status = 'insufficient_evidence'
            except EvidenceUnavailable:
                status = 'evidence_unavailable'
            except (OSError, ValueError, TypeError, KeyError):
                status = 'existing_attempt_unusable'
            rows.append(dict(entry_id=entry_id, status=status))
            continue

        def current_source():
            source = resolve_case(entry['case_id'])
            check_authorization(checked, consent_digest, revoked_refs=source['revoked_refs'])
            # Revalidate all frozen content identities on every revocation check,
            # not merely a caller-supplied empty list of revoked refs.
            build_input(checked, entry_id, subject=source['subject'], documents=source['documents'],
                        revoked_refs=source['revoked_refs'], dependency=dependency)
            return source

        def check_registration():
            verify_registration(ledger,root/entry_id,expected_dependencies,
                                require_source_binding=require_source_binding)

        try:
            source = current_source()
        except (OSError, ValueError, TypeError, KeyError):
            rows.append(dict(entry_id=entry_id, status='evidence_unavailable'))
            continue
        try:
            terminal = execute_entry(checked, entry_id, directory=root, consent_digest=consent_digest,
                subject=source['subject'], documents=source['documents'],
                revoked_refs=lambda:current_source()['revoked_refs'], dependency=dependency,
                gateway=_ReservedGateway(gateway, ledger, checked, entry, root,
                                         dependency['result_digest'] if dependency else None,
                                         require_source_binding),commit_guard=commit_guard,
                commit_check=check_registration)
            status = terminal['status']
            if status == 'completed':
                stored = verify_stored()
                if stored['status'] == 'usable_judgment':
                    verified[entry_id] = stored
                    status = 'executed'
                else:
                    status = stored['status']
        except EvidenceUnavailable:
            status = 'evidence_unavailable'
        except (OSError, ValueError, TypeError, KeyError):
            status = 'execution_unavailable'
        rows.append(dict(entry_id=entry_id, status=status))
    return dict(plan_id=checked['plan_id'], max_calls=checked['max_calls'], entries=rows)
