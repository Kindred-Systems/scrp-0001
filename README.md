Automation scripts for repository management.

These are eventually automated by Go backend (svc-0002 for example)

For now, they exist as run-as-needed python scripts and a virtual environment is recommended before execution.

## repo_tool.py

`repo_tool.py` combines the earlier automation utilities into a single entrypoint for repository management. It can:

- validate `project.json` and `component.json` files contain a valid `repo` field
- embed nested component metadata (`walk` command)
- create missing repositories and initialise them (`update` command)

The `update` command accepts `--create-repos` to automatically create any missing repositories without prompting and `--non-interactive` to suppress all user input.

Run `python repo_tool.py --help` for usage information.
