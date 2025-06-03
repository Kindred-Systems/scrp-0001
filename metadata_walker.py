import os
import json
from pathlib import Path
from pathspec import PathSpec

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"
METADATA_FILENAME = "component.json"

def load_gitignore():
    if not GITIGNORE_PATH.exists():
        return PathSpec.from_lines("gitwildmatch", [])
    with open(GITIGNORE_PATH) as f:
        return PathSpec.from_lines("gitwildmatch", f.readlines())

def find_metadata_files(base_path, pathspec):
    metadata_files = []
    for dirpath, dirnames, filenames in os.walk(base_path):
        rel_dir = os.path.relpath(dirpath, base_path)
        if pathspec.match_file(rel_dir):
            dirnames[:] = []  # Don't descend into ignored directories
            continue
        if METADATA_FILENAME in filenames:
            metadata_files.append(Path(dirpath) / METADATA_FILENAME)
    return metadata_files

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        print(f"Updated: {path}")

def add_nested_components(parent_path, all_metadata_paths):
    parent_json = load_json(parent_path)
    parent_abs = Path(parent_path).resolve()
    parent_dir = parent_abs.parent

    parent_json["components"] = []

    for child_path in all_metadata_paths:
        child_abs = Path(child_path).resolve()
        if parent_abs == child_abs:
            continue  # skip self
        if parent_abs in child_abs.parents:
            # Prevent circular reference
            child_json = load_json(child_path)
            if child_json.get("type") == "project":
                raise ValueError(f"Invalid dependency: {parent_path} cannot include project {child_path}")
            rel_path = str(child_abs.relative_to(parent_dir))
            child_json["__file"] = rel_path
            parent_json["components"].append(child_json)

    save_json(parent_path, parent_json)

def walk_and_update_metadata():
    pathspec = load_gitignore()
    metadata_files = find_metadata_files(PROJECT_ROOT, pathspec)

    for metadata_file in metadata_files:
        try:
            add_nested_components(metadata_file, metadata_files)
        except ValueError as e:
            print(f"Skipping due to validation: {e}")
        except Exception as e:
            print(f"Error processing {metadata_file}: {e}")

if __name__ == "__main__":
    walk_and_update_metadata()
