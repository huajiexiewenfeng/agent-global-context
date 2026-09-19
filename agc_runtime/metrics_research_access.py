"""Read-only, live Capture exclusion/forget checks for historical research input.

This is a deny gate, not a grant of consent. No Capture receipt is required for
an otherwise allowed task: sampling must not depend on whether Capture ran.
"""
import hashlib
import yaml

from agc_runtime.capture_contracts import RevisionRef
from agc_runtime.capture_store import CaptureStore
from agc_runtime.metrics_evidence import _root, _linked
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import _Yaml12SafeLoader, _parse_runtime_config, strict_read_text


class CaptureResearchAccess:
    def __init__(self,paths):
        if not isinstance(paths,MemoryPaths):
            raise ValueError('research_memory_binding_required')
        self.paths=paths

    def check(self,reference,*,project_scope=None,content_loaded=False):
        if not isinstance(reference,RevisionRef):
            raise ValueError('research_native_reference_required')
        try:
            _root(self.paths.root)
            _root(self.paths.capture.root)
            config_path=self.paths.root/'config.yaml'
            if not config_path.is_file() or _linked(config_path):
                raise ValueError('research_config_unavailable')
            # Unlike normal initialization, this deny gate must never fall back
            # to defaults when the configured policy disappears during loading.
            config=_parse_runtime_config(yaml.load(strict_read_text(config_path),Loader=_Yaml12SafeLoader))
            exclude=config.capture.exclude
            if reference.key.task_id in exclude.task_ids:
                raise ValueError('research_task_excluded')
            if content_loaded and exclude.project_ids and (
                    project_scope is None or project_scope in exclude.project_ids):
                raise ValueError('research_project_excluded_or_unknown')
            snapshot=CaptureStore(self.paths).read_snapshot(read_workers=8)
            if snapshot.integrity_state!='healthy':
                raise ValueError('research_capture_integrity_degraded')
            key=reference.key
            if any(t.capture_key==key for t in snapshot.tombstones):
                raise ValueError('research_revision_forgotten')
            if any(r.key==key and (r.redacted_by_forget or r.status in ('excluded','quarantined'))
                   for r in snapshot.receipts):
                raise ValueError('research_revision_excluded_or_redacted')
            if any((q.adapter_id,q.source_root_id)==(key.adapter_id,key.source_root_id)
                   for q in snapshot.source_quarantines):
                raise ValueError('research_source_quarantined')
            source_digest=hashlib.sha256(f'{key.adapter_id}\0{key.source_root_id}'.encode('utf-8')).hexdigest()
            if source_digest in snapshot.source_conflict_digests:
                raise ValueError('research_source_conflict')
        except (OSError,RuntimeError,TypeError,ValueError,yaml.YAMLError) as error:
            raise ValueError('research_access_unavailable_or_denied') from error
