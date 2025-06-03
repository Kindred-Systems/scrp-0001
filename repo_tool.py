#!/usr/bin/env python3

import os
import json
import subprocess
import argparse
from pathlib import Path
from typing import Iterable
from pathspec import PathSpec

REPO_PREFIX = "https://github.com/Kindred-Systems/"
METADATA_FILENAME = "component.json"


def load_gitignore() -> PathSpec:
    """Return PathSpec for the repository .gitignore."""
    path = Path(".gitignore")
    if not path.exists():
        return PathSpec.from_lines("gitwildmatch", [])
    with path.open() as f:
        return PathSpec.from_lines("gitwildmatch", f.read().splitlines())


def find_metadata_files(root: Path, pathspec: PathSpec) -> Iterable[Path]:
    """Yield component.json files under root honoring .gitignore."""
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if pathspec.match_file(rel_dir):
            dirnames[:] = []
            continue
        if METADATA_FILENAME in filenames:
            yield Path(dirpath) / METADATA_FILENAME


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with path.open("w") as f:
        json.dump(data, f, indent=2)


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def create_github_repo(name: str) -> subprocess.CompletedProcess:
    return subprocess.run([
        "gh", "repo", "create", f"Kindred-Systems/{name}", "--public", "--confirm"
    ], capture_output=True, text=True)


def ensure_repo_field(json_path: Path, tier: str, non_interactive: bool) -> None:
    data = load_json(json_path)
    folder = json_path.parent
    repo_name = folder.name

    if "tier" not in data and tier:
        data["tier"] = tier

    if "repo" not in data:
        msg = f"{json_path} missing repo field"
        if non_interactive:
            print(f"❌ {msg}")
            return
        confirm = input(f"{msg}. Create GitHub repo and add it? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("Skipping")
            return
        result = create_github_repo(repo_name)
        if result.returncode != 0:
            print(f"❌ Failed to create repo: {result.stderr}")
            return
        data["repo"] = REPO_PREFIX + repo_name
        print(f"✅ Created repo {data['repo']}")

    save_json(json_path, data)

    if not (folder / ".git").exists():
        git("init", cwd=folder)
        git("remote", "add", "origin", data["repo"], cwd=folder)
        git("add", ".", cwd=folder)
        git("commit", "-m", "Initial commit", cwd=folder)
        git("branch", "-M", "main", cwd=folder)
        git("push", "-u", "origin", "main", cwd=folder)

    parent = folder.parent
    if (parent / ".git").exists():
        submodule_path = folder.relative_to(parent)
        git("submodule", "add", data["repo"], str(submodule_path), cwd=parent)
        git("commit", "-am", f"Add {repo_name} as submodule", cwd=parent)


def add_nested_components(parent_path: Path, all_paths: Iterable[Path]) -> None:
    parent_json = load_json(parent_path)
    parent_abs = parent_path.resolve()
    parent_dir = parent_abs.parent
    parent_json["components"] = []

    for child_path in all_paths:
        child_abs = child_path.resolve()
        if parent_abs == child_abs:
            continue
        if parent_abs in child_abs.parents:
            child_json = load_json(child_path)
            if child_json.get("type") == "project":
                raise ValueError(
                    f"Invalid dependency: {parent_path} cannot include project {child_path}"
                )
            rel_path = str(child_abs.relative_to(parent_dir))
            child_json["__file"] = rel_path
            parent_json["components"].append(child_json)

    save_json(parent_path, parent_json)


def validate_repositories(paths: Iterable[Path]) -> bool:
    valid = True
    for path in paths:
        data = load_json(path)
        repo = data.get("repo") or data.get("repository")
        if not repo:
            print(f"❌ {path} missing repository field")
            valid = False
            continue
        if not repo.startswith(REPO_PREFIX):
            print(f"❌ {path} repository '{repo}' does not match prefix {REPO_PREFIX}")
            valid = False
        else:
            print(f"✅ {path} repository OK")
    return valid


def main() -> None:
    parser = argparse.ArgumentParser(description="AES repository management tool")
    subparsers = parser.add_subparsers(dest="command")

    p_walk = subparsers.add_parser("walk", help="Embed nested component metadata")

    p_update = subparsers.add_parser("update", help="Ensure repo fields and init git")
    p_update.add_argument("--tier", default="Tier 2", help="Tier value to set when missing")
    p_update.add_argument("--non-interactive", action="store_true", help="Run without prompts")

    subparsers.add_parser("validate", help="Validate repository signifiers")

    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    pathspec = load_gitignore()
    metadata_files = list(find_metadata_files(root, pathspec))

    if args.command == "walk":
        for p in metadata_files:
            try:
                add_nested_components(p, metadata_files)
            except ValueError as e:
                print(f"Skipping due to validation: {e}")
    elif args.command == "update":
        for p in metadata_files:
            ensure_repo_field(p, args.tier, args.non_interactive)
    else:  # validate is default
        success = validate_repositories(metadata_files)
        if not success:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
