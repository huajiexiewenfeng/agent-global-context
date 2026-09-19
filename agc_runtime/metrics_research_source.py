"""Scoped Codex historical input/final evidence; no scanner or current-memory read.

Caller supplies authorized native revision bindings. Capture exclusion/forget
checks are mandatory; they do not grant consent or infer historical background.
"""
import json
from dataclasses import asdict

from agc_runtime.capture_capsule import CapsulePolicy
from agc_runtime.capture_contracts import RevisionRef
from agc_runtime.capture_safety import (
    _record_message, _record_matches_turn, _has_subagent_provenance,
    _scrub_known_secrets, _WINDOWS_PATH, _UNIX_PRIVATE_PATH,
)
from agc_runtime.codex_source_adapter import CodexSourceAdapter, _session_project_scope
from agc_runtime.metrics_models import canonical, digest, instant, opaque
from agc_runtime.metrics_research_access import CaptureResearchAccess


def _task_ref(ref):
    return opaque(canonical(dict(adapter=ref.key.adapter_id,root=ref.key.source_root_id,
                                 task=ref.key.task_id)))


class CodexResearchSource:
    def __init__(self,adapter,references,*,policy,access):
        if not isinstance(adapter,CodexSourceAdapter) or not isinstance(policy,CapsulePolicy):
            raise ValueError('research_source_binding_invalid')
        if not isinstance(references,(list,tuple)) or len(references)>10000:
            raise ValueError('research_source_reference_count')
        if not isinstance(access,CaptureResearchAccess):
            raise ValueError('research_access_binding_required')
        self._access=access
        self._adapter=adapter
        self._policy=policy
        self._references={}
        for reference in references:
            if not isinstance(reference,RevisionRef):
                raise ValueError('research_native_reference_required')
            ref=RevisionRef.from_mapping(reference.to_mapping())
            adapter._validate_ref(ref)
            key=_task_ref(ref)
            if key in self._references:
                raise ValueError('research_task_revision_ambiguous')
            self._references[key]=ref

    def _load(self,ref):
        if self._references.get(_task_ref(ref))!=ref:
            raise ValueError('research_source_outside_binding')
        try:
            self._access.check(ref)
            records=list(self._adapter._iter_target_turn_records(ref))
            project_scope=_session_project_scope(tuple(records))
            self._access.check(ref,project_scope=project_scope,content_loaded=True)
            messages={'task_input':[],'task_output':[]}
            for record in records:
                payload=record.get('payload',{})
                # Native Codex provenance can mark a child by a mapping key,
                # while the shared text gate detects marker values only.
                if _has_subagent_provenance(record) or any(isinstance(container.get(field),dict) and 'subagent' in container[field]
                       for container in (record,payload)
                       for field in ('source','provenance','origin','thread_source')):
                    continue
                if any(container.get('channel') in ('analysis','commentary')
                       or container.get('phase') in ('analysis','commentary') for container in (record,payload)):
                    continue
                kind=payload.get('type')
                candidate=(record.get('type')=='response_item' and kind=='message') or (
                    record.get('type')=='event_msg' and kind in ('user_message','agent_message','assistant_message'))
                if candidate and not _record_matches_turn(record,ref.key.revision_id):
                    raise ValueError('research_message_turn_conflict')
                message=_record_message(record)
                if message is None:
                    role=payload.get('role',record.get('role'))
                    is_user=role=='user' or kind=='user_message'
                    is_final=payload.get('phase')=='final' or payload.get('is_final') is True
                    if candidate and (is_user or is_final):
                        raise ValueError('research_message_shape_unsupported')
                    continue
                if instant(record['timestamp'])>instant(ref.completed_at):
                    raise ValueError('research_message_after_delivery')
                role,text,_=message
                if not text.strip() or len(text.encode('utf-8'))>262144:
                    raise ValueError('research_message_empty_or_oversized')
                cleaned,count=_scrub_known_secrets(text,self._policy.sensitive_labels)
                if count or _WINDOWS_PATH.search(cleaned) or _UNIX_PRIVATE_PATH.search(cleaned):
                    # Do not silently score a truncated/redacted substitute as
                    # the delivered answer. Report unavailable to the sample layer.
                    raise ValueError('research_message_requires_safe_projection')
                key='task_input' if role=='user' else 'task_output'
                if cleaned not in messages[key]:
                    messages[key].append(cleaned)
            if not messages['task_input'] or len(messages['task_output'])!=1:
                raise ValueError('research_input_or_unique_final_missing')
            if len(canonical(messages).encode('utf-8'))>524288:
                raise ValueError('research_task_too_large')
            version=digest(dict(reference=ref.to_mapping(),records_digest=digest(records),
                                policy=asdict(self._policy),transform='codex-research-input-final.v1'))
            task_ref=_task_ref(ref)
            documents=[dict(ref=opaque(task_ref+':'+role),version=version,role=role,
                            content=dict(messages=content)) for role,content in messages.items()]
            self._access.check(ref,project_scope=project_scope,content_loaded=True)
            return dict(task_ref=task_ref,revision=version,documents=documents)
        except (OSError,UnicodeError,KeyError,TypeError,ValueError) as error:
            raise ValueError('research_historical_evidence_unavailable') from error

    def describe_task(self,reference):
        if not isinstance(reference,RevisionRef):
            raise ValueError('research_native_reference_required')
        value=self._load(reference)
        return dict(task_ref=value['task_ref'],revision=value['revision'],
                    delivered_at=reference.completed_at,evidence_status='available')

    def classification_input(self,reference):
        if not isinstance(reference,RevisionRef):
            raise ValueError('research_native_reference_required')
        value=self._load(reference)
        document=next(d for d in value['documents'] if d['role']=='task_input')
        return dict(task_ref=value['task_ref'],revision=value['revision'],
                    delivered_at=reference.completed_at,document=document)

    def prepare(self,reference):
        if not isinstance(reference,dict) or set(reference)!={'task_ref','revision'}:
            raise ValueError('research_reference_invalid')
        if not isinstance(reference['task_ref'],str) or reference['task_ref'] not in self._references:
            raise ValueError('research_source_outside_binding')
        value=self._load(self._references[reference['task_ref']])
        if value['revision']!=reference['revision']:
            raise ValueError('research_historical_evidence_changed')
        return json.loads(canonical(value))
