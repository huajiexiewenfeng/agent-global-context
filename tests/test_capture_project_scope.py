import pytest

from agc_runtime.capture_project_scope import project_scope_from_cwd


def test_project_scope_normalizes_equivalent_windows_cwd_without_exposing_it():
    drive = "C:"
    left = project_scope_from_cwd(drive + r"\Synthetic\XPublisher\.")
    right = project_scope_from_cwd("c:/synthetic/xpublisher")

    assert left == right
    assert left is not None
    assert left.startswith("project:cwd:")
    assert len(left) == len("project:cwd:") + 64
    assert "synthetic" not in left.casefold()


def test_project_scope_distinguishes_projects_and_supports_posix_paths():
    drive = "C:"
    assert project_scope_from_cwd(drive + r"\Synthetic\XPublisher") != project_scope_from_cwd(
        drive + r"\Synthetic\AgentGlobalContext"
    )
    assert project_scope_from_cwd("/work/x-publisher") == project_scope_from_cwd(
        "/work/./x-publisher"
    )


@pytest.mark.parametrize(
    "value",
    (
        None,
        "",
        "relative/project",
        "/",
        "C:" + "\\",
        " " + "C:" + r"\synthetic",
        "C:" + "\\bad\npath",
        "\ud800",
        "x" * 4097,
    ),
)
def test_project_scope_rejects_ambiguous_or_unsafe_cwd(value):
    assert project_scope_from_cwd(value) is None
