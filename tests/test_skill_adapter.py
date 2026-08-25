import copy
import json
import re
from pathlib import Path

from agc_runtime.contracts import SourceKey
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.schema import validate_memory_item
from agc_runtime.store import MemoryStore
from agc_runtime.write_service import dispatch_write


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"
MAIN_SKILL = SKILLS_ROOT / "agent-global-context" / "SKILL.md"
TOOL_CONTRACT = (
    SKILLS_ROOT
    / "agent-global-context"
    / "references"
    / "tool-contract.md"
)
CAPTURE_OPERATIONS = REPOSITORY_ROOT / "docs" / "capture-operations.md"


def _skill_text() -> str:
    return MAIN_SKILL.read_text(encoding="utf-8")


def _frontmatter_description(text: str) -> str:
    match = re.match(
        r"\A---\s*\n.*?^description:\s*(.+?)\s*$.*?^---\s*$",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "SKILL.md must have YAML frontmatter"
    return match.group(1)


def _normalized_skill_text() -> str:
    return " ".join(_skill_text().casefold().split())


def _guidance_text() -> str:
    skill_root = MAIN_SKILL.parent
    paths = [MAIN_SKILL, *sorted((skill_root / "references").glob("*.md"))]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _request_examples() -> dict[str, dict]:
    examples = {}
    text = TOOL_CONTRACT.read_text(encoding="utf-8")
    for action, payload in re.findall(
        r"^\| `([a-z_]+)` \| `(\{.*\})` \|$",
        text,
        flags=re.MULTILINE,
    ):
        examples[action] = json.loads(payload)
    return examples


def _fenced_example(title: str, language: str) -> str:
    text = TOOL_CONTRACT.read_text(encoding="utf-8")
    match = re.search(
        rf"^#### {re.escape(title)}\s*\n+```{language}\n(.*?)\n```",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing documented example: {title}"
    return match.group(1)


def test_only_one_public_agent_global_context_skill_remains():
    public_skills = sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in SKILLS_ROOT.glob("agent-global-context*/SKILL.md")
    )

    assert public_skills == ["skills/agent-global-context/SKILL.md"]


def test_guidance_has_exactly_three_tools_without_alpha_load_commands():
    text = _guidance_text()

    assert set(re.findall(r"\bagc\.[a-z][a-z0-9_.-]*", text)) == {
        "agc.read",
        "agc.write",
        "agc.admin",
    }
    assert re.search(r"\bP[01]\b", text) is None
    assert "index.md" not in text


def test_capability_description_is_thin_and_contains_no_personal_fact():
    description = _frontmatter_description(_skill_text())

    assert len(description.split()) <= 80
    assert re.search(
        r"\b(?:my|the user's)\s+(?:name|employer|location|identity|preference)\b",
        description,
        flags=re.IGNORECASE,
    ) is None
    assert "@" not in description


def test_capability_description_names_recall_triggers_and_exclusions():
    description = _frontmatter_description(_skill_text()).casefold()
    expected_triggers = (
        "important decision",
        "personalized writing",
        "collaboration",
        "learning",
        "research",
        "growth review",
        "cross-task continuation",
    )

    assert all(trigger in description for trigger in expected_triggers)
    assert re.search(
        r"skip.*(?:self-contained|factual|mechanical)", description
    )


def test_research_relevance_is_an_explicit_recall_trigger():
    description = _frontmatter_description(_skill_text()).casefold()
    text = _normalized_skill_text()

    assert "project or technology" in description
    assert "research direction" in description
    assert "project, repository, tool, or technology" in text
    assert "research, learning, or long-term goals" in text
    assert re.search(r"generic (?:explanation|overview).*do not call", text)


def test_ordinary_recall_is_small_and_value_gated():
    raw = _skill_text()
    text = _normalized_skill_text()

    assert re.search(r'\{\s*"action"\s*:\s*"overview"\s*\}', raw)
    assert re.search(r"search.*filters.*limit.*5", text)
    assert all(
        filter_name in text
        for filter_name in (
            "`kind`",
            "`scopes`",
            "`decision_impact`",
            "`sensitivity`",
            "`exposure`",
            "`confidence`",
        )
    )
    assert '{"scopes":["research"]}' in raw
    assert "literal substring" in text
    assert re.search(
        r"tool-contract\.md.*(?:write|admin)", text
    )
    assert "decision, expression, continuity, or growth support" in text
    assert re.search(r"no material change.*discard", text)


def test_skill_makes_recall_and_application_llm_choices_explicit():
    text = _normalized_skill_text()

    assert "materially improve" in text
    assert re.search(r"llm.*decides.*relevance.*application", text)
    assert re.search(r"(?:small|self-contained).*do not call.*agc\.read", text)
    assert "overview → search → get → history/evidence" in text
    assert all(mode in text for mode in ("`adapt`", "`continue`", "`grow`"))
    assert "current instructions" in text
    assert re.search(r"current instructions.*(?:win|outrank)", text)


def test_skill_is_failure_open_and_separates_write_from_admin():
    text = _normalized_skill_text()

    assert re.search(r"agc\.read.*fail.*continue.*main task", text)
    assert re.search(r"(?:a )?failed write.*not.*(?:saved|succeeded)", text)
    assert re.search(r"durable.*non-sensitive.*agc\.write", text)
    assert re.search(r"agc\.admin.*maintenance.*migration", text)
    assert re.search(r"agc\.admin.*not.*ordinary recall", text)


def test_capture_guidance_is_thin_evidence_only_and_links_operations():
    skill = _normalized_skill_text()
    contract = TOOL_CONTRACT.read_text(encoding="utf-8")

    assert "capture observations are evidence, not formal memory" in skill
    assert "not automatically injected" in skill
    assert "capture-operations.md" in skill
    assert all(
        action in contract
        for action in (
            "`capture_overview`",
            "`capture_search`",
            "`capture_get`",
            "`capture_status`",
            "`capture_forget`",
        )
    )
    assert "does not add a fourth mcp tool" in contract.casefold()


def test_capture_operations_documents_safe_activation_and_rollback_contract():
    text = CAPTURE_OPERATIONS.read_text(encoding="utf-8")
    normalized = " ".join(text.casefold().split())

    assert "capture.enabled=false" in text
    assert "capture.mode=off" in text
    assert "scanner_only" in text
    assert "runner" in text
    assert "7-day" in normalized
    assert "100,000" in text
    assert "provider" in normalized
    assert "exclude.task_ids" in text
    assert "include_subagents" in text
    assert "hook" in normalized
    assert "fallback" in normalized
    assert "pause" in normalized and "disable" in normalized
    assert "rollback" in normalized
    assert "after capture data exists" in normalized
    assert "binary downgrade" in normalized
    assert "does not delete" in normalized
    assert "explicit_user_request" in text
    assert "not formal memory" in normalized
    assert "not automatically promoted" in normalized
    assert "background" in normalized and "cost" in normalized


def test_readmes_link_capture_operations_without_overclaiming():
    english = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (REPOSITORY_ROOT / "README.zh.md").read_text(encoding="utf-8")

    assert "[Capture operations](docs/capture-operations.md)" in english
    assert "[Capture 操作手册](docs/capture-operations.md)" in chinese
    combined = (english + "\n" + chinese).casefold()
    assert "every task becomes memory" not in combined
    assert "zero cost" not in combined


def test_tool_contract_has_a_request_example_for_every_action():
    examples = _request_examples()
    expected_fields = {
        "overview": {"action"},
        "search": {"action", "query", "filters", "limit"},
        "get": {"action", "id"},
        "history": {"action", "id"},
        "evidence": {"action", "id"},
        "capture_overview": {"action"},
        "capture_search": {"action", "filters", "limit", "include_reviewed"},
        "capture_get": {"action", "observation_id"},
        "observe": {"action", "observation", "memory_markdown"},
        "observe_batch": {"action", "items"},
        "propose": {"action", "observation"},
        "confirm": {"action", "observation", "memory_markdown"},
        "update": {"action", "observation", "memory_markdown"},
        "supersede": {"action", "observation", "memory_id"},
        "archive": {"action", "observation", "memory_id"},
        "reject": {"action", "candidate_id"},
        "forget": {
            "action",
            "memory_id",
            "authorization",
            "suppression_scope",
            "verification_terms",
        },
        "capture_forget": {"action", "authorization", "target"},
        "capture_review": {"action", "observation_ids", "outcome"},
        "init": {"action"},
        "validate": {"action"},
        "rebuild_catalog": {"action"},
        "backup": {"action"},
        "restore": {"action", "backup_path"},
        "migrate": {"action"},
        "capture_status": {"action"},
    }

    assert set(examples) == set(expected_fields)
    for action, required_fields in expected_fields.items():
        assert examples[action]["action"] == action
        assert required_fields <= set(examples[action])


def test_quality_first_formalization_workflow_is_bounded_and_user_confirmed():
    guidance = _guidance_text()
    text = guidance.casefold()
    assert "formalization-workflow.md" in _skill_text()
    assert "gpt-5.6-sol" in text
    assert "include_reviewed" in text
    assert "capture_observation_ids" in text
    assert "needs_context" in text and "discard" in text and "draft" in text
    assert "1–20" in guidance
    assert "raw codex session" in text
    assert "do not" in text
    assert "explicit user confirmation" in text
    assert "该 skill" in guidance


def test_formalization_groups_receipts_and_expands_exact_project_scope():
    guidance = _guidance_text()
    text = guidance.casefold()

    assert "same receipt" in text
    assert "filters.project" in text
    assert "exact non-null project_scope" in text
    assert "at most 20" in text
    assert "different non-null project scopes" in text
    assert "null project_scope" in text


def test_x_publishing_golden_case_is_one_project_proposal():
    guidance = _guidance_text()

    assert "X 发文开源项目" in guidance
    assert "规划文章的整体路线" in guidance
    assert "每篇文章撰写摘要" in guidance
    assert "参与开源项目" in guidance
    assert "one coherent project proposal" in guidance


def test_golden_six_observations_have_exact_expected_review_results():
    text = _guidance_text()
    assert "Codex 自动完成发布" in text and "人工只确认发布" in text
    assert "使用 1Panel" in text
    assert "最终目标保持不变" in text
    assert "Docker Desktop 数据放在 D 盘" in text
    assert "该 skill 调用当前本地 harness" in text
    assert "24" in text


def test_tool_contract_rejects_unknown_search_filter_names():
    text = TOOL_CONTRACT.read_text(encoding="utf-8")

    assert "Unknown filter names are rejected" in text


def test_tool_contract_defines_the_reusable_write_schemas():
    text = TOOL_CONTRACT.read_text(encoding="utf-8")
    required_paths = {
        "observation_id",
        "source.ref",
        "source.revision",
        "source.content_hash",
        "source.observed_at",
        "assertion.subject",
        "assertion.mode",
        "assertion.modality",
        "proposal.disposition",
        "proposal.match_memory_id",
        "proposal.kind",
        "proposal.scopes",
        "proposal.temporal_type",
        "proposal.sensitivity",
        "proposal.rationale",
        "proposal.requested_confidence",
        "evidence.count",
        "evidence.distinct_sessions",
        "evidence.time_span_days",
        "memory_markdown",
    }

    assert all(f"`{path}`" in text for path in required_paths)
    assert "Host binds the memory root" in text
    assert "LLM chooses" in text


def test_complete_documented_memory_items_pass_runtime_validation():
    expected = {
        "Complete principle Memory Item": "principle",
        "Complete interest Memory Item": "interest",
        "Complete capability Memory Item": "capability",
    }

    items = {}
    for title, kind in expected.items():
        item = MemoryItem.from_markdown(_fenced_example(title, "markdown"))
        validate_memory_item(item)
        assert item.kind == kind
        items[kind] = item

    assert (
        items["interest"].topic,
        items["interest"].intensity,
        items["interest"].trend,
        items["interest"].motivation,
    ) == (
        "reliable AI systems",
        "high",
        "rising",
        "Improve correctness in agent workflows.",
    )
    assert (
        items["capability"].domain,
        items["capability"].polarity,
        items["capability"].current_level,
    ) == (
        "distributed systems debugging",
        "growth_area",
        "developing",
    )
    assert items["capability"].recall.exposure in {
        "core_card",
        "scoped_card",
    }
    assert items["capability"].goal_refs


def test_documented_transition_requests_enforce_equal_match_id(tmp_path):
    item = MemoryItem.from_markdown(
        _fenced_example("Complete principle Memory Item", "markdown")
    )
    paths = MemoryPaths.from_root(tmp_path / "memory")
    MemoryStore(paths).create_memory(
        item,
        SourceKey("doc-example:seed", "r1", "a" * 64),
    )
    supersede = json.loads(
        _fenced_example("Complete supersede request", "json")
    )
    archive = json.loads(_fenced_example("Complete archive request", "json"))

    missing_match = copy.deepcopy(supersede)
    missing_match["observation"]["proposal"]["match_memory_id"] = None
    rejected = dispatch_write(paths, missing_match)
    assert rejected.status == "failed"
    assert rejected.error["message"] == (
        "memory_id must match proposal.match_memory_id"
    )

    superseded = dispatch_write(paths, supersede)
    archived = dispatch_write(paths, archive)

    assert superseded.status == "accepted"
    assert superseded.data["lifecycle"] == "superseded"
    assert archived.status == "accepted"
    assert archived.data["lifecycle"] == "historical"
