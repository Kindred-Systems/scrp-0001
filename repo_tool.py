import os
import sys
import json
import subprocess
import argparse
import requests
from pathlib import Path
from urllib.parse import quote
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
        if "component.json" in filenames or "project.json" in filenames:
            yield current_path

def load_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(json_path, data):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def validate_and_prompt_labels(data, is_project, non_interactive):
    changed = False
    labels = REQUIRED_LABELS if not is_project else ["code", "name"]
    for label in labels:
        if label not in data:
            value = prompt(f"Missing `{label}`. Please enter value", non_interactive)
            if value:
                data[label] = int(value) if label == "tier" and value.isdigit() else value
                changed = True
    return changed

def ensure_git_repo(path):
    subprocess.run(["git", "init"], cwd=path)
    subprocess.run(["git", "add", "."], cwd=path)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True)
    if status.stdout.strip():
        result = subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️ Git commit warning in {path}: {result.stderr.strip()}")
        else:
            print(f"✅ Git repo initialized and committed in {path}")
    else:
        print(f"ℹ️ Git repo already clean in {path}")

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
    print(f"📡 Creating Gitea repo: {repo_name}")
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        return f"{GIT_BASE_URL}/{GIT_DEFAULT_ORG}/{repo_name}.git"
    elif response.status_code == 409:
        print(f"⚠️ Repo `{repo_name}` already exists.")
        return f"{GIT_BASE_URL}/{GIT_DEFAULT_ORG}/{repo_name}.git"
    else:
        print(f"❌ Failed to create repo `{repo_name}`: {response.text}")
        return None

def push_to_gitea(path, repo_url):
    # Token-authenticated remote URL
    safe_user = quote(GIT_ADMIN_USER)
    safe_token = quote(GIT_ADMIN_TOKEN)
    auth_url = repo_url.replace("http://", f"http://{safe_user}:{safe_token}@")

    # Overwrite or add remote
    result = subprocess.run(["git", "remote"], cwd=path, capture_output=True, text=True)
    if "origin" in result.stdout:
        subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=path)
    else:
        subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=path)

    subprocess.run(["git", "checkout", "-B", "main"], cwd=path)

    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            print(f"❌ Git push failed:\n{result.stderr.strip()}")
        else:
            print("✅ Successfully pushed to Gitea.")
    except subprocess.TimeoutExpired:
        print("❌ Git push timed out — likely authentication or remote problem.")

def is_project_dir(path: Path):
    return (path / "project.json").exists()

def is_component_dir(path: Path):
    return (path / "component.json").exists()

def add_submodule_to_parents(child_path: Path, repo_url: str):
    current = child_path.parent
    while current != current.anchor and current != current.parent:
        if is_component_dir(current):
            if not is_component_dir(child_path):
                print(f"❌ Skipping: Cannot add project {child_path} to component repo {current}")
                return
        elif not is_project_dir(current):
            current = current.parent
            continue

        submodule_path = os.path.relpath(child_path, current)
        print(f"🔗 Adding submodule in {current}: {submodule_path}")
        # Skip if already added
        gitmodules = current / ".gitmodules"
        if gitmodules.exists() and submodule_path in gitmodules.read_text():
            print(f"⚠️ Submodule {submodule_path} already present in {current}, skipping.")
        else:
            subprocess.run(["git", "submodule", "add", repo_url, submodule_path], cwd=current)
            subprocess.run(["git", "commit", "-am", f"Add {repo_url} as submodule"], cwd=current)

        current = current.parent

def check_gitea_connection():
    try:
        resp = requests.get(f"{GIT_API_URL}/version", headers={"Authorization": f"token {GIT_ADMIN_TOKEN}"})
        if resp.status_code == 200:
            print("✅ Connected to Gitea:", resp.json().get("version"))
        else:
            print("⚠️ Gitea responded but not OK:", resp.status_code)
    except Exception as e:
        print("❌ Failed to connect to Gitea:", str(e))
        sys.exit(1)

def process_components(root_path, non_interactive=False, tier_filter=None):
    check_gitea_connection()
    ignored_paths = read_gitignore(root_path)
    found = list(walk_components(root_path, ignored_paths))
    if not found:
        print("⚠️ No component or project repositories found.")
        return

    for repo_path in found:
        json_path = repo_path / ("component.json" if is_component_dir(repo_path) else "project.json")
        is_project = json_path.name == "project.json"
        data = load_json(json_path)

        if validate_and_prompt_labels(data, is_project, non_interactive):
            save_json(json_path, data)

        code = data.get("code")
        tier = data.get("tier")
        if not code or (not is_project and not tier):
            print(f"❌ Skipping invalid repo in: {json_path}")
            continue

        if not is_project and tier_filter is not None and str(tier) != str(tier_filter):
            continue

        if "repo" not in data:
            print(f"\n📦 Creating repo for `{code}` at {repo_path}")
            ensure_git_repo(repo_path)
            repo_url = create_gitea_repo(code)
            if repo_url:
                push_to_gitea(repo_path, repo_url)
                add_submodule_to_parents(repo_path, repo_url)
                data["repo"] = repo_url
                save_json(json_path, data)
                print(f"✅ Repo created and added: {repo_url}")
            else:
                print(f"❌ Failed to create repo for: {code}")
        else:
            print(f"✔️ Repo already present for {code}: {data['repo']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize missing Gitea repos from component/project JSON files")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt user")
    parser.add_argument("--tier", type=int, help="Only apply to components with this tier")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent.resolve()

    process_components(project_root, non_interactive=args.non_interactive, tier_filter=args.tier)
