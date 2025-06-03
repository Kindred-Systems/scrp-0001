import os
import json
import subprocess
import argparse
from pathlib import Path

REPO_PREFIX = "https://github.com/Kindred-Systems/"
DEFAULT_TIER = "unassigned"

def is_git_ignored(path, gitignore_patterns):
    return any(path.match(pattern) for pattern in gitignore_patterns)

def load_gitignore_patterns():
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        return []
    with open(gitignore_path, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def find_component_json_files(root, gitignore_patterns):
    for dirpath, dirnames, filenames in os.walk(root):
        # Remove ignored directories
        dirnames[:] = [d for d in dirnames if not is_git_ignored(Path(dirpath) / d, gitignore_patterns)]
        if "component.json" in filenames:
            yield Path(dirpath) / "component.json"

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def prompt(msg, default="yes", non_interactive=False):
    if non_interactive:
        print(f"{msg} [Y/n] -> yes (non-interactive)")
        return True
    val = input(f"{msg} [Y/n]: ").strip().lower()
    return val in ["", "y", "yes"]

def git(*args, cwd=None):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)

def create_github_repo(repo_name):
    return subprocess.run([
        "gh", "repo", "create", f"Kindred-Systems/{repo_name}", "--public", "--confirm"
    ], capture_output=True, text=True)

def update_component_json(json_path, tier, non_interactive):
    data = load_json(json_path)
    folder = json_path.parent
    repo_name = folder.name

    # Add 'tier' if missing
    if 'tier' not in data and tier:
        print(f"Setting tier='{tier}' in {json_path}")
        data['tier'] = tier

    # Add or confirm 'repo' field
    if 'repo' not in data:
        if prompt(f"{json_path} is missing a repo field. Create a GitHub repo and add it?", non_interactive=non_interactive):
            result = create_github_repo(repo_name)
            if result.returncode != 0:
                print(f"❌ Failed to create GitHub repo for {repo_name}:\n{result.stderr}")
                return
            data['repo'] = REPO_PREFIX + repo_name
            print(f"✅ Created GitHub repo: {data['repo']}")
        else:
            print(f"❌ Skipping repo creation for {json_path}")
            return

    save_json(json_path, data)

    # Ensure the directory is a git repo
    if not (folder / ".git").exists():
        print(f"⚙️ Initializing Git repo in {folder}")
        git("init", cwd=folder)
        git("remote", "add", "origin", data['repo'], cwd=folder)
        git("add", ".", cwd=folder)
        git("commit", "-m", "Initial commit", cwd=folder)
        git("branch", "-M", "main", cwd=folder)
        git("push", "-u", "origin", "main", cwd=folder)

    # Add as submodule to parent repo
    parent = folder.parent
    if (parent / ".git").exists():
        submodule_path = folder.relative_to(parent)
        print(f"🔗 Adding submodule {repo_name} to parent repo at {parent}")
        git("submodule", "add", data['repo'], str(submodule_path), cwd=parent)
        git("commit", "-am", f"Add {repo_name} as submodule", cwd=parent)

def main():
    parser = argparse.ArgumentParser(description="Automate git + repo creation for component.json files.")
    parser.add_argument("--non-interactive", action="store_true", help="Run without prompts")
    parser.add_argument("--tier", type=str, default=DEFAULT_TIER, help="Tier value to assign")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent  # One level above script folder
    os.chdir(root)

    print(f"📂 Walking from: {root}")
    gitignore_patterns = load_gitignore_patterns()

    for json_path in find_component_json_files(root, gitignore_patterns):
        update_component_json(json_path, args.tier, args.non_interactive)

if __name__ == "__main__":
    main()
