"""Explicit binding from metrics execution to the optional Codex adapter.

Fingerprints identify local command files and loaded adapter methods; they are
not signatures, provenance guarantees, or an atomic OS executable attestation.
"""
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace, CodeType

from agc_runtime.metrics_eval import judge_configuration
from agc_runtime.metrics_evidence import _linked
from agc_runtime.metrics_models import canonical, digest


def _file_hash(path):
    path=Path(path)
    if not path.is_absolute() or not path.is_file() or any(_linked(p) for p in (path,*path.parents)):
        raise ValueError('gateway_file_invalid')
    before=path.stat()
    result=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            result.update(block)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('gateway_file_changed_during_read')
    return result.hexdigest()


def _code_identity(code):
    def constant(value):
        if isinstance(value,CodeType): return _code_identity(value)
        if isinstance(value,tuple): return [constant(item) for item in value]
        if isinstance(value,frozenset): return sorted((constant(item) for item in value),key=canonical)
        return dict(type=type(value).__name__,value=repr(value))
    return dict(bytecode=code.co_code.hex(),constants=[constant(c) for c in code.co_consts],
        names=code.co_names,variables=code.co_varnames,free=code.co_freevars,cells=code.co_cellvars,
        args=code.co_argcount,posonly=code.co_posonlyargcount,kwonly=code.co_kwonlyargcount,flags=code.co_flags,
        exceptions=getattr(code,'co_exceptiontable',b'').hex())


class MetricsGateway:
    def __init__(self,*,executable,model='gpt-6-astra',provider='openai',reasoning_effort='medium',
                 timeout_seconds=120,adapter_type=None):
        if not isinstance(executable,tuple) or not 1<=len(executable)<=4:
            raise ValueError('gateway_command_invalid')
        for path in executable:
            _file_hash(path)
        if adapter_type is None:
            try:
                from agent_eval_codex import CodexStructuredJudge
            except ImportError as error:
                raise ValueError('structured_adapter_unavailable') from error
            adapter_type=CodexStructuredJudge
        self._command=executable
        self._adapter_type=adapter_type
        executable_identity,adapter_identity=self._identities()
        self._configuration=judge_configuration(dict(provider=provider,model=model,
            reasoning_effort=reasoning_effort,timeout_seconds=timeout_seconds,
            executable_identity=executable_identity,adapter_identity=adapter_identity))

    def _identities(self):
        command=digest([dict(argument=path,sha256=_file_hash(path)) for path in self._command])
        methods={name:digest(_code_identity(method.__code__))
                 for name,method in inspect.getmembers(self._adapter_type,inspect.isfunction)}
        source=inspect.getsourcefile(self._adapter_type)
        if not source or not methods:
            raise ValueError('adapter_identity_unavailable')
        adapter=digest(dict(adapter_source=_file_hash(Path(source).resolve()),methods=methods,
                            gateway_source=_file_hash(Path(__file__).resolve())))
        return command,adapter

    @property
    def configuration(self):
        executable,adapter=self._identities()
        if (executable!=self._configuration['executable_identity']
                or adapter!=self._configuration['adapter_identity']):
            raise ValueError('gateway_binding_changed')
        return json.loads(canonical(self._configuration))

    def evaluate(self,payload):
        configuration=self.configuration
        if not isinstance(payload,dict) or set(payload)!={'case','profile','evidence','instruction','output_schema'}:
            raise ValueError('gateway_payload_invalid')
        adapter=self._adapter_type(executable=self._command,model=configuration['model'],provider=configuration['provider'],
            reasoning_effort=configuration['reasoning_effort'],timeout_seconds=configuration['timeout_seconds'],
            output_schema=payload['output_schema'],instruction=payload['instruction'])
        outcome=adapter.evaluate(case=payload['case'],profile=payload['profile'],evidence=payload['evidence'])
        # Detect replacement while the call was running; do not accept its result.
        _=self.configuration
        return SimpleNamespace(output=outcome.output,usage=outcome.usage,
                               observed_configuration=adapter.observed_configuration)
