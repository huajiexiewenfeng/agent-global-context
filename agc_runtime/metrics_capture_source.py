"""Metrics projection over the existing read-only Capture evidence resolver.

Bundles contain private evidence and are intended for in-memory use. Do not
persist them in Trace, Git or a public report. No source scanner or repair here.
"""
import json

from agc_runtime.capture_eval_adapter import AGCCaptureEvidenceResolver, _valid_reference
from agc_runtime.capture_eval_evidence import canonical_sha256
from agc_runtime.metrics_eval import _case
from agc_runtime.metrics_models import canonical, digest


class CaptureMetricsSource:
    def __init__(self,resolver):
        if not isinstance(resolver,AGCCaptureEvidenceResolver):
            raise ValueError('capture_metrics_resolver_required')
        self._resolver=resolver

    def prepare(self,reference):
        if not _valid_reference(reference):
            raise ValueError('capture_metrics_reference_invalid')
        try:
            content=self._resolver.resolve(reference)
            if canonical_sha256(content)!=reference['digest'] or content['schema_version']!='agc.capture-evidence.v1':
                raise ValueError('source_digest_mismatch')
            observations=content['decision']['observations']
            scenario=content['decision']['outcome']
            if not isinstance(observations,list) or scenario not in ('collected','zero'):
                raise ValueError('capture_metrics_content_invalid')
            if (scenario=='zero') != (len(observations)==0):
                raise ValueError('capture_metrics_outcome_conflict')
            version=digest(dict(source=reference,runtime=content['runtime']))
            documents=[]
            for role,value in (('safe_input',content['capsule']),('candidate',dict(observations=observations))):
                documents.append(dict(ref='id_'+digest(dict(source=reference,role=role)),version=version,
                                      role=role,content=value))
            subject=dict(stage='observation',version=version,evidence_roles={d['ref']:d['role'] for d in documents})
            case=dict(case_id='id_'+digest(dict(source=reference,stage='observation')),scenario=scenario,
                subject_digest=digest(subject),evidence_refs=[dict(ref=d['ref'],version=d['version'],digest=digest(d)) for d in documents])
            _case(case)
            return json.loads(canonical(dict(case=case,subject=subject,documents=documents,source_reference=reference)))
        except Exception as error:
            raise ValueError('capture_metrics_evidence_unavailable_or_changed') from error

    def resolve(self,bundle):
        try:
            if not isinstance(bundle,dict) or set(bundle)!={'case','subject','documents','source_reference'}:
                raise ValueError('invalid_bundle')
            expected=self.prepare(bundle['source_reference'])
            if canonical(expected)!=canonical(bundle):
                raise ValueError('frozen_bundle_changed')
            return expected
        except Exception as error:
            raise ValueError('capture_metrics_evidence_unavailable_or_changed') from error

    def revoked_refs(self,bundle):
        """Return invalidated refs; unavailability is not a claim of deliberate forget.

        Re-resolve every time, no positive cache. The caller must use this callback
        immediately before/after execution and whenever reusing derived results.
        """
        checked=_case(bundle['case'])
        try:
            self.resolve(bundle)
            return []
        except ValueError:
            return [r['ref'] for r in checked['evidence_refs']]
