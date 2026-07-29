import re
from collections.abc import Mapping
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


FRONTMATTER_BOUNDARY = "---"
BODY_HEADINGS = (
    "Memory Card",
    "Full Meaning",
    "Application Boundary",
    "Rationale",
)
_HEADING_PATTERN = re.compile(r"^## ([^\r\n]+)\s*$", re.MULTILINE)


def _reject_duplicate_yaml_keys(node: Node | None) -> None:
    if node is None:
        return
    if isinstance(node, MappingNode):
        seen: set[str] = set()
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode):
                raise ValueError("invalid YAML frontmatter: mapping keys must be scalars")
            key = key_node.value
            if key in seen:
                raise ValueError(f"duplicate YAML key: {key}")
            seen.add(key)
            _reject_duplicate_yaml_keys(value_node)
        return
    if isinstance(node, SequenceNode):
        for item in node.value:
            _reject_duplicate_yaml_keys(item)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    if not lines or lines[0] != FRONTMATTER_BOUNDARY:
        raise ValueError("Markdown must start with YAML frontmatter")
    try:
        boundary_index = lines.index(FRONTMATTER_BOUNDARY, 1)
    except ValueError as error:
        raise ValueError("YAML frontmatter is not closed") from error

    source = "\n".join(lines[1:boundary_index])
    try:
        node = yaml.compose(source, Loader=yaml.SafeLoader)
        _reject_duplicate_yaml_keys(node)
        loaded = yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML frontmatter: {error}") from error
    if not isinstance(loaded, Mapping):
        raise ValueError("YAML frontmatter must be a mapping")

    body = "\n".join(lines[boundary_index + 1 :]).lstrip("\n")
    return dict(loaded), body


def parse_body_sections(body: str) -> dict[str, str]:
    matches = list(_HEADING_PATTERN.finditer(body))
    headings = tuple(match.group(1) for match in matches)
    if headings != BODY_HEADINGS:
        raise ValueError(
            "body headings must appear exactly once and in canonical order: "
            + ", ".join(BODY_HEADINGS)
        )

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[start:end].strip()
    return sections


def render_markdown(frontmatter: Mapping[str, Any], sections: Mapping[str, str]) -> str:
    yaml_text = yaml.safe_dump(
        dict(frontmatter),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).rstrip()
    body = "\n\n".join(
        f"## {heading}\n\n{sections[heading].strip()}" for heading in BODY_HEADINGS
    )
    return f"---\n{yaml_text}\n---\n{body}\n"
