"""Fixed per-user metrics host binding, separate from Capture model settings."""
from pathlib import Path

from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_result_reader import _read


def _host_root():
    return Path.home()/'.agent-global-context'/'metrics'


def _source(config):
    from agc_runtime.capture_eval_adapter import AGCCaptureEvidenceResolver
    from agc_runtime.codex_source_adapter import CodexSourceAdapter
    from agc_runtime.metrics_capture_source import CaptureMetricsSource
    from agc_runtime.paths import MemoryPaths
    return CaptureMetricsSource(AGCCaptureEvidenceResolver(
        paths=MemoryPaths.from_root(Path(config['memory_root'])),
        adapters=tuple(CodexSourceAdapter(Path(p)) for p in config['source_roots'])))


def _gateway(config):
    from agc_runtime.metrics_gateway import MetricsGateway
    return MetricsGateway(executable=tuple(config['executable']),model=config['model'],
                          reasoning_effort=config['reasoning_effort'],timeout_seconds=config['timeout_seconds'])


class _ResearchSources:
    def __init__(self,sources,deliveries):
        self._sources=sources
        self._deliveries=deliveries
        self.task_refs=frozenset(sources)

    def validate_cohort(self,cohort):
        from agc_runtime.metrics_models import utc
        if self.task_refs!=set(cohort['selected_task_refs']):
            raise ValueError('research_selected_source_mismatch')
        for row in cohort['tasks']:
            if row['selection_status']=='selected' and utc(row['delivered_at'])!=self._deliveries[row['task_ref']]:
                raise ValueError('research_delivery_time_mismatch')

    def prepare(self,reference):
        if not isinstance(reference,dict) or reference.get('task_ref') not in self._sources:
            raise ValueError('research_reference_outside_host_binding')
        return self._sources[reference['task_ref']].prepare(reference)

    def classification_input(self,reference):
        from agc_runtime.capture_contracts import RevisionRef
        from agc_runtime.metrics_research_source import _task_ref
        ref=RevisionRef.from_mapping(reference)
        if _task_ref(ref) not in self._sources:
            raise ValueError('research_reference_outside_host_binding')
        return self._sources[_task_ref(ref)].classification_input(ref)


def _research_source(config,references):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_contracts import RevisionRef
    from agc_runtime.codex_source_adapter import CodexSourceAdapter
    from agc_runtime.metrics_research_access import CaptureResearchAccess
    from agc_runtime.metrics_research_source import CodexResearchSource, _task_ref
    from agc_runtime.paths import MemoryPaths
    from agc_runtime.metrics_models import utc
    if not isinstance(references,list) or len(references)>5:
        raise ValueError('research_reference_count_invalid')
    adapters={}
    for path in config['source_roots']:
        adapter=CodexSourceAdapter(_root(path))
        descriptor=adapter.describe()
        adapters[(descriptor.adapter_id,descriptor.source_root_id)]=adapter
    access=CaptureResearchAccess(MemoryPaths.from_root(_root(config['memory_root'])))
    sources={}; deliveries={}
    for value in references:
        ref=RevisionRef.from_mapping(value)
        binding=(ref.key.adapter_id,ref.key.source_root_id)
        if binding not in adapters or _task_ref(ref) in sources:
            raise ValueError('research_reference_outside_host_or_duplicate')
        sources[_task_ref(ref)]=CodexResearchSource(adapters[binding],[ref],
                                                   policy=CapsulePolicy(),access=access)
        deliveries[_task_ref(ref)]=utc(ref.completed_at)
    return _ResearchSources(sources,deliveries)


class _CountingGateway:
    def __init__(self, gateway, *, before_send=None):
        self._gateway=gateway
        self._before_send=before_send
        self.call_attempts=0

    @property
    def configuration(self):
        return self._gateway.configuration

    def evaluate(self, payload):
        if self._before_send is not None: self._before_send()
        self.call_attempts+=1
        return self._gateway.evaluate(payload)


def _configuration(base):
    config=_read(base/'host.json')
    fields={'schema_version','memory_root','source_roots','executable','model','reasoning_effort','timeout_seconds'}
    if not isinstance(config,dict) or set(config)!=fields or config['schema_version']!='agc.metrics-host.v1':
        raise ValueError('metrics_host_config_invalid')
    if (not isinstance(config['source_roots'],list) or not 1<=len(config['source_roots'])<=16
            or not isinstance(config['executable'],list) or not 1<=len(config['executable'])<=4):
        raise ValueError('metrics_host_paths_invalid')
    return config


def cleanup_identity(ledger):
    from agc_runtime.metrics_models import digest
    ledger=_root(ledger); info=ledger.stat()
    if not info.st_ino: raise ValueError('metrics_cleanup_ledger_identity_unavailable')
    return dict(location_digest=digest(str(ledger)),device=info.st_dev,inode=info.st_ino)


def _bind_cleanup_host(memory,ledger):
    from agc_runtime.locking import root_write_lock
    from agc_runtime.paths import MemoryPaths
    from agc_runtime.metrics_execution import _write
    from agc_runtime.metrics_models import canonical
    paths=MemoryPaths.from_root(_root(memory))
    with root_write_lock(paths):
        marker=_root(paths.capture.root)/'metrics-host.json'
        expected=dict(schema_version=1,operation='metrics_host_binding',ledger_identity=cleanup_identity(ledger))
        try: _write(marker,expected)
        except FileExistsError: pass
        if canonical(_read(marker))!=canonical(expected):
            raise ValueError('metrics_cleanup_host_binding_changed')


def cleanup_ledger(paths):
    """Read only the fixed host binding; never construct a model or source reader."""
    from agc_runtime.metrics_models import canonical
    marker=paths.capture.root/'metrics-host.json'
    binding=_read(marker) if marker.exists() or marker.is_symlink() else None
    base=_host_root()
    if not base.exists() and not base.is_symlink():
        if binding is not None: raise ValueError('metrics_cleanup_host_missing')
        return None
    base=_root(base)
    path=base/'host.json'
    if not path.exists() and not path.is_symlink():
        raise ValueError('metrics_cleanup_configuration_missing')
    config=_configuration(base)
    if _root(config['memory_root'])!=_root(paths.root):
        if binding is not None: raise ValueError('metrics_cleanup_memory_binding_changed')
        return None
    ledger=_root(base/'send-ledger')
    if binding is not None and canonical(binding)!=canonical(dict(schema_version=1,
            operation='metrics_host_binding',ledger_identity=cleanup_identity(ledger))):
        raise ValueError('metrics_cleanup_host_binding_changed')
    return ledger


def load_host():
    from agc_runtime.locking import root_write_lock
    from agc_runtime.paths import MemoryPaths
    base=_root(_host_root())
    config=_configuration(base)
    memory=_root(config['memory_root'])
    sources=[_root(p) for p in config['source_roots']]
    ledger=_root(base/'send-ledger')
    # No CLI/environment override for this ledger. Installation must provision
    # it explicitly; evaluation never creates a replacement after it is missing.
    return dict(source=_source(config),gateway=_CountingGateway(_gateway(config),
                before_send=lambda:_bind_cleanup_host(memory,ledger)),ledger=ledger,
                commit_guard=lambda:root_write_lock(MemoryPaths.from_root(_root(memory))),
                research_source_factory=lambda references:_research_source(config,references),
                protected_roots=[memory,*sources,base])


def output_directory(path, context, *, existing):
    path=Path(path).expanduser().absolute()
    parent=_root(path if existing else path.parent)
    checked=parent if existing else parent/path.name
    if any(checked.is_relative_to(root) for root in context['protected_roots']):
        raise ValueError('metrics_output_inside_source_or_host')
    if not existing and checked.exists():
        raise ValueError('metrics_output_exists')
    return checked
