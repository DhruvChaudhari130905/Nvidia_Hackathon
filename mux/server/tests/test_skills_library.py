"""Reading SKILL.md folders, and spotting skills written for Claude Code's own tools."""

import os
from pathlib import Path

from mux.skills.compat import claude_code_issues
from mux.skills.library import SkillLibrary, load_skill


def write_skill(root: Path, folder: str, text: str, files: dict[str, str] | None = None) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(text)
    for name, content in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(content)
    return path


def test_loads_frontmatter_body_and_files(tmp_path):
    folder = write_skill(tmp_path, "frontend-design", "---\nname: frontend-design\ndescription: Make distinctive UIs\n---\n# Body\nUse bold type.",
                         {"examples/card.html": "<div></div>", ".hidden": "x"})
    skill = load_skill(folder, "server")
    assert skill is not None
    assert (skill.name, skill.description, skill.source) == ("frontend-design", "Make distinctive UIs", "server")
    assert skill.body == "# Body\nUse bold type." and skill.files == ["examples/card.html"] and skill.compatible


def test_name_defaults_to_the_folder_and_bad_skills_are_skipped(tmp_path):
    assert load_skill(write_skill(tmp_path, "Clean-Code", "---\ndescription: Tidy\n---\nbody"), "server").name == "clean-code"  # type: ignore[union-attr]
    assert load_skill(write_skill(tmp_path, "nodesc", "---\nname: nodesc\n---\nbody"), "server") is None
    assert load_skill(write_skill(tmp_path, "badyaml", "---\nname: x\ndescription: a: b: [\n---\nbody"), "server") is None
    assert load_skill(write_skill(tmp_path, "nofront", "just text"), "server") is None
    assert load_skill(write_skill(tmp_path, "bad name!", "---\ndescription: d\n---\nb"), "server") is None
    big = write_skill(tmp_path, "big", "---\ndescription: d\n---\n" + "x" * 210_000)
    assert load_skill(big, "server") is None


def test_symlinks_are_not_supporting_files(tmp_path):
    folder = write_skill(tmp_path, "s", "---\ndescription: d\n---\nb", {"ok.md": "fine"})
    (tmp_path / "outside.txt").write_text("secret")
    os.symlink(tmp_path / "outside.txt", folder / "link.txt")
    assert load_skill(folder, "server").files == ["ok.md"]  # type: ignore[union-attr]


def test_library_first_root_wins_and_reload_picks_up_new_skills(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_skill(a, "tdd", "---\ndescription: from a\n---\nA")
    write_skill(b, "tdd", "---\ndescription: from b\n---\nB")
    lib = SkillLibrary([(a, "server"), (b, "plugin"), (tmp_path / "missing", "server")])
    assert lib.skills()["tdd"].description == "from a"
    write_skill(a, "review", "---\ndescription: r\n---\nR")
    assert "review" not in lib.skills()
    lib.reload()
    assert set(lib.skills()) == {"tdd", "review"}


def test_claude_code_issues():
    assert claude_code_issues("Write the failing test first, then make it pass.") == []
    issues = claude_code_issues("Use TodoWrite for each step. Dispatch a subagent with the Task tool. Run git worktree add.")
    assert issues == ["uses Claude Code sub-agents", "uses Claude Code's task list", "uses git worktrees"]
    assert claude_code_issues("Call EnterPlanMode") == ["uses Claude Code's plan mode"]
    assert claude_code_issues("use the Bash tool") == ["runs shell commands"]
