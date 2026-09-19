"""Explicit, bounded frontend inputs for classification; no LLM calls or writes.

Only task input is exposed to avoid selecting cases by answer quality. The
returned inputs are private content, not material for public reports or Git.
"""
import json
from collections import Counter

from agc_runtime.capture_contracts import RevisionRef
from agc_runtime.metrics_models import canonical,digest,instant,utc,validate_batch
from agc_runtime.metrics_research_source import _task_ref


def prepare_research_inputs(batch,references,*,source_factory):
    batch=validate_batch(batch)
    if not isinstance(references,list) or len(references)>100:
        raise ValueError('research_preparation_reference_count')
    refs=[RevisionRef.from_mapping(value) for value in references]
    refs.sort(key=lambda r:(instant(r.completed_at),_task_ref(r),canonical(r.to_mapping())))
    start=instant(batch['window']['start']); end=instant(batch['window']['end'])
    counts=Counter(_task_ref(r) for r in refs if start<=instant(r.completed_at)<end)
    entries=[]; inputs=[]; input_bytes=2  # JSON list delimiters.
    for ref in refs:
        task_ref=_task_ref(ref)
        entry=dict(task_ref=task_ref,native_reference_digest=digest(ref.to_mapping()),
                   delivered_at=utc(ref.completed_at),revision=None,input_ref=None,status='evidence_unavailable')
        if not start<=instant(ref.completed_at)<end:
            entry['status']='outside_window'
        elif counts[task_ref]>1:
            entry['status']='ambiguous_revision'
        else:
            try:
                source=source_factory([ref.to_mapping()])
                value=source.classification_input(ref.to_mapping())
                document=value['document']
                if (value['task_ref']!=task_ref or utc(value['delivered_at'])!=utc(ref.completed_at)
                        or document['role']!='task_input' or document['version']!=value['revision']):
                    raise ValueError('research_classification_source_mismatch')
                candidate=dict(task_ref=task_ref,document=document)
                candidate_bytes=len(canonical(candidate).encode('utf-8'))+int(bool(inputs))
                entry.update(revision=value['revision'],input_ref=dict(
                    ref=document['ref'],version=document['version'],digest=digest(document)))
                if input_bytes+candidate_bytes>2*1024*1024:
                    entry['status']='input_budget_exceeded'
                else:
                    entry['status']='ready'
                    inputs.append(candidate)
                    input_bytes+=candidate_bytes
            except (OSError,ValueError,TypeError,KeyError):
                pass
        entries.append(entry)
    statuses=Counter(e['status'] for e in entries)
    manifest=dict(schema_version='agc.research-preparation.v1',batch_id=batch['batch_id'],
                  window=batch['window'],coverage='explicit_native_references_not_full_population',
                  classification_status='not_classified',entries=entries,
                  counts={k:statuses[k] for k in ('ready','outside_window','ambiguous_revision','evidence_unavailable','input_budget_exceeded')})
    manifest['preparation_id']='mrprep_'+digest(manifest)
    return json.loads(canonical(dict(manifest=manifest,inputs=inputs)))
