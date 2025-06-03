import os
import sys
import json
import subprocess
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GIT_PROVIDER = os.getenv("GIT_PROVIDER", "gitea")
GIT_BASE_URL = os.getenv("GIT_BASE_URL")
GIT_API_URL = os.getenv("GIT_API_URL")
GIT_ADMIN_USER = os.getenv("GIT_ADMIN_USER")
GIT_ADMIN_TOKEN = os.getenv("GIT_ADMIN_TOKEN")
GIT_DEFAULT_ORG = os.getenv("GIT_DEFAULT_ORG")

REQUIRED_LABELS = ["code", "name", "tier"]

def prompt(msg, non_interactive):
    if non_interactive:
        return None
    return input(f"{msg}: ").strip()

def read_gitignore(root_path):
    gitignore = root_path / ".gitignore"
    ignored_paths = set()
    if gitignore.exists():
        with open(gitignore) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ignored_paths.add((root_path / line).resolve())
    return ignored_paths

def walk_components(root_path, ignored_paths):
    for dirpath, dirnames, filenames in os.walk(root_path):
        current_path = Path(dirpath)
        if any(str(current_path).startswith(str(ignored)) for ignored in ignored_paths):
            continue
        if "component.json" in filenames:
            yield current_path / "component.json"

def load_component_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_component_json(json_path, data):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def validate_and_prompt_labels(data, non_interactive):
    changed = False
    for label in REQUIRED_LABELS:
        if label not in data:
            value = prompt(f"Missing `{label}`. Please enter value", non_interactive)
            if value:
                data[label] = int(value) if label == "tier" and value.isdigit() else value
                changed = True
    return changed

def ensure_git_repo(path):
    subprocess.run(["git", "init"], cwd=path)
    subprocess.run(["git", "add", "."], cwd=path)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path)

def create_gitea_repo(repo_name):
    url = f"{GIT_API_URL}/orgs/{GIT_DEFAULT_ORG}/repos"
    headers = {
        "Authorization": f"token {GIT_ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": repo_name,
        "private": True,
        "auto_init": False
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        return f"{GIT_BASE_URL}/{GIT_DEFAULT_ORG}/{repo_name}.git"
    elif response.status_code == 409:
        print(f"Repo `{repo_name}` already exists.")
        return f"{GIT_BASE_URL}/{GIT_DEFAULT_ORG}/{repo_name}.git"
    else:
        print(f"Failed to create repo `{repo_name}`: {response.text}")
        return None

def push_to_gitea(path, repo_url):
    subprocess.run(["git", "branch", "-M", "main"], cwd=path)
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=path)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=path)

def add_submodule_to_parents(component_path, repo_url):
    current = component_path.parent
    while current != component_path.root:
        parent_json = current / "component.json"
        if parent_json.exists():
            submodule_path = os.path.relpath(component_path, current)
            subprocess.run(["git", "submodule", "add", repo_url, submodule_path], cwd=current)
            subprocess.run(["git", "commit", "-am", f"Add {repo_url} as submodule"], cwd=current)
        current = current.parent

def process_components(root_path, non_interactive=False, tier_filter=None):
    ignored_paths = read_gitignore(root_path)
    for json_path in walk_components(root_path, ignored_paths):
        data = load_component_json(json_path)
        component_dir = json_path.parent

        if validate_and_prompt_labels(data, non_interactive):
            save_component_json(json_path, data)

        code = data.get("code")
        tier = data.get("tier")
        if not code or not tier:
            print(f"❌ Skipping invalid component in: {json_path}")
            continue

        if tier_filter is not None and str(tier) != str(tier_filter):
            continue

        if "repo" not in data:
            print(f"\n📦 Creating repo for component: {code}")
            ensure_git_repo(component_dir)
            repo_url = create_gitea_repo(code)
            if repo_url:
                push_to_gitea(component_dir, repo_url)
                add_submodule_to_parents(component_dir, repo_url)
                data["repo"] = repo_url
                save_component_json(json_path, data)
                print(f"✅ Repo created and added: {repo_url}")
            else:
                print(f"❌ Failed to create repo for: {code}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize missing Gitea repos from component.json files")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt user")
    parser.add_argument("--tier", type=int, help="Only apply to components with this tier")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent.resolve()

    process_components(project_root, non_interactive=args.non_interactive, tier_filter=args.tier)
