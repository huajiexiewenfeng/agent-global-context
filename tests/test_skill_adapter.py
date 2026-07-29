import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"
MAIN_SKILL = SKILLS_ROOT / "agent-global-context" / "SKILL.md"


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


def test_only_one_public_agent_global_context_skill_remains():
    public_skills = sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in SKILLS_ROOT.glob("agent-global-context*/SKILL.md")
    )

    assert public_skills == ["skills/agent-global-context/SKILL.md"]


def test_main_skill_has_the_three_tools_without_alpha_load_commands():
    text = _skill_text()

    assert {"agc.read", "agc.write", "agc.admin"} <= set(
        re.findall(r"agc\.(?:read|write|admin)", text)
    )
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


def test_skill_makes_recall_and_application_llm_choices_explicit():
    text = _normalized_skill_text()

    assert "materially improve" in text
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
