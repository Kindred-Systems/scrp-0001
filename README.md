Automation scripts for repository management.

These are eventually automated by Go backend (svc-0002 for example)

For now, they exist as run-as-needed python scripts and a virtual environment is recommended before execution.

## repo_tool.py

`repo_tool.py` combines the earlier `auto_git.py` and `metadata_walker.py` utilities. It provides a single command line interface to:

- validate `component.json` files contain a valid `repo` field
- embed nested component metadata (`walk` command)
- optionally initialise new repositories (`update` command)

Run `python repo_tool.py --help` for usage information.
