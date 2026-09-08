"""Bridge user-global skills across harnesses on a hop.

The real skill directory stays where it was created. Other providers get a
directory symlink in that provider's matching user-global root. Cursor already
scans Claude, Codex, and ``~/.agents`` trees, so hops *to* Cursor usually need
no extra link. Claude and Codex do not scan Cursor's tree.

System / product skills are out of scope: ``baton``, Claude ``synced``,
``~/.cursor/skills-cursor``, bundled/admin trees. Project-local skills
(``.claude/skills`` and friends) are also out of scope.

Request before linking. Never silently ``ln``, never clobber a name the
destination already owns.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from baton.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR, HARNESS_LABELS
from baton.dirs import (
    agents_user_skills_dir,
    claude_user_skills_dir,
    codex_deprecated_user_skills_dir,
    cursor_user_skills_dir,
)
from baton.style import dim, log

RESERVED_SKILL_NAMES = frozenset({"baton", "synced"})


@dataclass(frozen=True)
class SkillProviderRoots:
    harness: str
    own: Path
    discover: tuple[Path, ...]


@dataclass(frozen=True)
class ProposedLink:
    name: str
    source: Path
    dest: Path


def provider_roots() -> dict[str, SkillProviderRoots]:
    claude = claude_user_skills_dir()
    cursor = cursor_user_skills_dir()
    agents = agents_user_skills_dir()
    codex_old = codex_deprecated_user_skills_dir()
    return {
        HARNESS_CLAUDE: SkillProviderRoots(HARNESS_CLAUDE, claude, (claude,)),
        HARNESS_CURSOR: SkillProviderRoots(
            HARNESS_CURSOR,
            cursor,
            (cursor, claude, agents, codex_old),
        ),
        HARNESS_CODEX: SkillProviderRoots(
            HARNESS_CODEX,
            agents,
            (agents, codex_old),
        ),
    }


def all_user_skill_roots() -> tuple[Path, ...]:
    claude = claude_user_skills_dir()
    cursor = cursor_user_skills_dir()
    agents = agents_user_skills_dir()
    codex_old = codex_deprecated_user_skills_dir()
    return (claude, cursor, agents, codex_old)


def describe_skill_roots() -> list[dict[str, str]]:
    return [
        {
            "harness": HARNESS_CLAUDE,
            "path": str(claude_user_skills_dir()),
            "notes": "user-global; CLAUDE_CONFIG_DIR relocates",
        },
        {
            "harness": HARNESS_CURSOR,
            "path": str(cursor_user_skills_dir()),
            "notes": "user-global; not ~/.cursor/skills-cursor",
        },
        {
            "harness": HARNESS_CODEX,
            "path": str(agents_user_skills_dir()),
            "notes": "official USER root (shared with Cursor)",
        },
        {
            "harness": HARNESS_CODEX,
            "path": str(codex_deprecated_user_skills_dir()),
            "notes": "deprecated USER root; still scanned, not used for new links",
        },
    ]


def collect_user_skills() -> dict[str, Path]:
    """Map skill name → canonical directory. Drop names with two real homes."""
    found: dict[str, Path] = {}
    conflicts: set[str] = set()
    for root in all_user_skill_roots():
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            name = child.name
            if name in RESERVED_SKILL_NAMES or name.startswith("."):
                continue
            if not (child / "SKILL.md").is_file():
                continue
            try:
                canonical = child.resolve()
            except OSError:
                continue
            if not canonical.is_dir():
                continue
            if name in conflicts:
                continue
            previous = found.get(name)
            if previous is None:
                found[name] = canonical
            elif previous != canonical:
                conflicts.add(name)
                del found[name]
    return found


def _resolve_existing(path: Path) -> Path | None:
    try:
        if path.exists():
            return path.resolve()
    except OSError:
        return None
    return None


def already_visible(name: str, canonical: Path, dest: SkillProviderRoots) -> bool:
    try:
        parent = canonical.parent.resolve()
    except OSError:
        parent = canonical.parent
    for root in dest.discover:
        resolved_root = _resolve_existing(root)
        if resolved_root is not None and parent == resolved_root:
            return True
        candidate = _resolve_existing(root / name)
        if candidate is not None and candidate == canonical:
            return True
    return False


def dest_owns(path: Path) -> bool:
    """True when the destination name is already taken (real dir, file, or link)."""
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def missing_links(dest_harness: str) -> list[ProposedLink]:
    dest = provider_roots()[dest_harness]
    out: list[ProposedLink] = []
    for name, canonical in sorted(collect_user_skills().items()):
        dest_path = dest.own / name
        if already_visible(name, canonical, dest):
            continue
        if dest_owns(dest_path):
            continue
        out.append(ProposedLink(name=name, source=canonical, dest=dest_path))
    return out


def apply_links(links: list[ProposedLink]) -> list[ProposedLink]:
    created: list[ProposedLink] = []
    for link in links:
        try:
            if dest_owns(link.dest):
                continue
            link.dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.fspath(link.source), os.fspath(link.dest))
        except OSError as exc:
            log(f"could not link {link.name}: {exc}", kind="error")
            continue
        created.append(link)
    return created


def format_offer(dest_harness: str, links: list[ProposedLink]) -> str:
    label = HARNESS_LABELS.get(dest_harness, dest_harness)
    own = provider_roots()[dest_harness].own
    n = len(links)
    noun = "user skill" if n == 1 else "user skills"
    lines = [f"{n} {noun} not visible to {label}:"]
    for link in links:
        lines.append(f"  {link.name}  →  {link.source}")
    lines.append(f"Link them into {own}? [Y/n]")
    return "\n".join(lines)


def offer_user_skill_links(
    dest_harness: str,
    *,
    interactive: bool | None = None,
) -> list[ProposedLink]:
    """Ask to create missing dest links. Empty if none, declined, or not a tty."""
    links = missing_links(dest_harness)
    if not links:
        return []
    if interactive is None:
        interactive = bool(sys.stdin.isatty() and sys.stdout.isatty())
    label = HARNESS_LABELS.get(dest_harness, dest_harness)
    if not interactive:
        log(
            f"{len(links)} user skill(s) not visible to {label} "
            "(not a tty — skipped linking)"
        )
        return []
    print(dim(format_offer(dest_harness, links), stream=sys.stderr), file=sys.stderr)
    try:
        answer = input().strip().lower()
    except EOFError:
        print()
        return []
    except KeyboardInterrupt:
        print()
        return []
    if answer in {"n", "no", "q"}:
        return []
    created = apply_links(links)
    if created:
        log(
            f"linked {len(created)} user skill(s) into {provider_roots()[dest_harness].own}",
            kind="ok",
        )
    return created
