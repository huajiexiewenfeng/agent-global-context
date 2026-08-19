import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import strict_read_text


class _Yaml12SafeLoader(yaml.SafeLoader):
    pass


_Yaml12SafeLoader.yaml_implicit_resolvers = {
    key: list(resolvers)
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for _key, _resolvers in list(_Yaml12SafeLoader.yaml_implicit_resolvers.items()):
    _Yaml12SafeLoader.yaml_implicit_resolvers[_key] = [
        (tag, expression)
        for tag, expression in _resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
_Yaml12SafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _construct_unique_mapping(
    loader: _Yaml12SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate YAML key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_Yaml12SafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class RecallConfig:
    overview_token_budget: int
    compact_card_token_budget: int
    default_lifecycle: str


@dataclass(frozen=True)
class HookConfig:
    enabled: bool


@dataclass(frozen=True)
class RunnerConfig:
    concurrency: int
    max_attempts: int
    backoff_seconds: tuple[int, ...]


@dataclass(frozen=True)
class CapsuleConfig:
    target_tokens: int
    max_tokens: int


@dataclass(frozen=True)
class CaptureBudgetsConfig:
    backfill_window_days: int
    backfill_total_tokens: int
    incremental_total_tokens: int | None


@dataclass(frozen=True)
class ExtractorConfig:
    kind: str
    executable: str
    model: str | None


@dataclass(frozen=True)
class ExcludeConfig:
    task_ids: tuple[str, ...]
    project_ids: tuple[str, ...]


@dataclass(frozen=True)
class CaptureConfig:
    schema_version: int
    enabled: bool
    mode: str
    paused: bool
    include_subagents: bool
    sources: tuple[str, ...]
    hook: HookConfig
    runner: RunnerConfig
    capsule: CapsuleConfig
    budgets: CaptureBudgetsConfig
    extractor: ExtractorConfig
    exclude: ExcludeConfig


@dataclass(frozen=True)
class RuntimeConfig:
    schema_version: int
    sensitive_storage: str
    recall: RecallConfig
    capture: CaptureConfig


def default_config_text() -> str:
    return Path(__file__).with_name("default_config.yaml").read_text(
        encoding="utf-8"
    )


def _mapping(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - fields
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    missing = fields - set(value)
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _string(value: Any, name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _source_roots(value: Any, *, active: bool) -> tuple[str, ...]:
    sources = _string_list(value, "capture.sources")
    if not sources:
        return sources
    lexical_identities: set[str] = set()
    for source in sources:
        path = Path(source)
        if not path.is_absolute():
            raise ValueError("capture.sources entries must be an absolute directory")
        # Windows path matching is ASCII case-insensitive for our inert shape
        # check, but Unicode case folding is not a filesystem identity rule:
        # it would collapse distinct NTFS names such as straße/strasse.
        lexical_identity = str(path).translate(
            str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
        )
        if lexical_identity in lexical_identities:
            raise ValueError("capture.sources must not contain duplicate roots")
        lexical_identities.add(lexical_identity)
    if not active:
        # Disabled Capture validates only inert configuration shape. Filesystem
        # identity and the deferred Source contract belong to activation.
        return sources
    identities: set[str] = set()
    from agc_runtime.capture_source import canonical_source_root, source_root_id_for

    for source in sources:
        path = Path(source)
        try:
            canonical_source_root(path)
            identity = source_root_id_for(path)
        except ValueError as error:
            raise ValueError(
                "capture.sources entries must be an existing absolute directory"
            ) from error
        if identity in identities:
            raise ValueError("capture.sources must not contain duplicate physical roots")
        identities.add(identity)
    return sources


def _int_list(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of positive integers")
    return tuple(_positive_int(item, name) for item in value)


def _parse_runtime_config(value: Any) -> RuntimeConfig:
    root = _mapping(
        value,
        "runtime config",
        {"schema_version", "sensitive_storage", "recall", "capture"},
    )
    recall = _mapping(
        root["recall"],
        "recall",
        {
            "overview_token_budget",
            "compact_card_token_budget",
            "default_lifecycle",
        },
    )
    capture = _mapping(
        root["capture"],
        "capture",
        {
            "schema_version",
            "enabled",
            "mode",
            "paused",
            "include_subagents",
            "sources",
            "hook",
            "runner",
            "capsule",
            "budgets",
            "extractor",
            "exclude",
        },
    )
    hook = _mapping(capture["hook"], "capture.hook", {"enabled"})
    runner = _mapping(
        capture["runner"],
        "capture.runner",
        {"concurrency", "max_attempts", "backoff_seconds"},
    )
    capsule = _mapping(
        capture["capsule"], "capture.capsule", {"target_tokens", "max_tokens"}
    )
    budgets = _mapping(
        capture["budgets"],
        "capture.budgets",
        {
            "backfill_window_days",
            "backfill_total_tokens",
            "incremental_total_tokens",
        },
    )
    extractor = _mapping(
        capture["extractor"],
        "capture.extractor",
        {"kind", "executable", "model"},
    )
    exclude = _mapping(
        capture["exclude"], "capture.exclude", {"task_ids", "project_ids"}
    )

    schema_version = _positive_int(root["schema_version"], "schema_version")
    if schema_version != 3:
        raise ValueError("schema_version must be 3")
    sensitive_storage = _string(root["sensitive_storage"], "sensitive_storage")
    if sensitive_storage != "disabled":
        raise ValueError("sensitive_storage must be disabled")
    default_lifecycle = _string(
        recall["default_lifecycle"], "recall.default_lifecycle"
    )
    if default_lifecycle != "active":
        raise ValueError("recall.default_lifecycle must be active")

    capture_schema_version = _positive_int(
        capture["schema_version"], "capture.schema_version"
    )
    if capture_schema_version != 1:
        raise ValueError("capture.schema_version must be 1")
    enabled = _bool(capture["enabled"], "capture.enabled")
    mode = _string(capture["mode"], "capture.mode")
    if mode not in {"off", "scanner_only", "runner"}:
        raise ValueError("capture.mode must be off, scanner_only, or runner")
    if not enabled and mode != "off":
        raise ValueError("disabled capture.mode must be off")
    if enabled and mode not in {"scanner_only", "runner"}:
        raise ValueError("enabled capture.mode must be scanner_only or runner")
    include_subagents = _bool(
        capture["include_subagents"], "capture.include_subagents"
    )
    if include_subagents:
        raise ValueError("capture.include_subagents must be false for schema version 1")
    sources = _source_roots(capture["sources"], active=enabled)
    if enabled and not sources:
        raise ValueError("enabled capture requires at least one capture.sources entry")
    hook_enabled = _bool(hook["enabled"], "capture.hook.enabled")
    if hook_enabled and not enabled:
        raise ValueError("capture.hook.enabled requires capture.enabled")
    incremental = budgets["incremental_total_tokens"]
    if incremental is not None:
        incremental = _positive_int(
            incremental, "capture.budgets.incremental_total_tokens"
        )

    return RuntimeConfig(
        schema_version=schema_version,
        sensitive_storage=sensitive_storage,
        recall=RecallConfig(
            overview_token_budget=_positive_int(
                recall["overview_token_budget"], "recall.overview_token_budget"
            ),
            compact_card_token_budget=_positive_int(
                recall["compact_card_token_budget"], "recall.compact_card_token_budget"
            ),
            default_lifecycle=default_lifecycle,
        ),
        capture=CaptureConfig(
            schema_version=capture_schema_version,
            enabled=enabled,
            mode=mode,
            paused=_bool(capture["paused"], "capture.paused"),
            include_subagents=include_subagents,
            sources=sources,
            hook=HookConfig(enabled=hook_enabled),
            runner=RunnerConfig(
                concurrency=_positive_int(
                    runner["concurrency"], "capture.runner.concurrency"
                ),
                max_attempts=_positive_int(
                    runner["max_attempts"], "capture.runner.max_attempts"
                ),
                backoff_seconds=_int_list(
                    runner["backoff_seconds"], "capture.runner.backoff_seconds"
                ),
            ),
            capsule=CapsuleConfig(
                target_tokens=_positive_int(
                    capsule["target_tokens"], "capture.capsule.target_tokens"
                ),
                max_tokens=_positive_int(
                    capsule["max_tokens"], "capture.capsule.max_tokens"
                ),
            ),
            budgets=CaptureBudgetsConfig(
                backfill_window_days=_positive_int(
                    budgets["backfill_window_days"], "capture.budgets.backfill_window_days"
                ),
                backfill_total_tokens=_positive_int(
                    budgets["backfill_total_tokens"], "capture.budgets.backfill_total_tokens"
                ),
                incremental_total_tokens=incremental,
            ),
            extractor=ExtractorConfig(
                kind=_string(extractor["kind"], "capture.extractor.kind"),
                executable=_string(
                    extractor["executable"], "capture.extractor.executable"
                ),
                model=_string(
                    extractor["model"], "capture.extractor.model", optional=True
                ),
            ),
            exclude=ExcludeConfig(
                task_ids=_string_list(exclude["task_ids"], "capture.exclude.task_ids"),
                project_ids=_string_list(
                    exclude["project_ids"], "capture.exclude.project_ids"
                ),
            ),
        ),
    )


def load_runtime_config(paths: MemoryPaths) -> RuntimeConfig:
    try:
        text = (
            strict_read_text(paths.root / "config.yaml")
            if (paths.root / "config.yaml").exists()
            else default_config_text()
        )
        value = yaml.load(text, Loader=_Yaml12SafeLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid config.yaml: {error}") from error
    return _parse_runtime_config(value)
