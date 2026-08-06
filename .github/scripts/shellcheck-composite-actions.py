"""Shellcheck every bash `run:` block in this repo's composite actions.

actionlint does not read action.yml at all, so without this the composite
actions — including the OpenBao token exchange — are never linted.

Run: uv run --no-project --with pyyaml --with shellcheck-py python .github/scripts/shellcheck-composite-actions.py
"""

import pathlib
import subprocess
import sys

import yaml

failed = 0
actions_found = 0
steps_checked = 0
for path in sorted(pathlib.Path(".github/actions").glob("*/action.yml")):
    actions_found += 1
    doc = yaml.safe_load(path.read_text())
    if not isinstance(doc, dict):
        failed = 1
        print(f"::error file={path}::action.yml did not parse to a mapping")
        continue

    bash_steps = [
        (index, step)
        for index, step in enumerate(doc.get("runs", {}).get("steps") or [])
        if "run" in step and step.get("shell") == "bash"
    ]
    print(f"considered: {path} ({len(bash_steps)} bash step(s))")

    for index, step in bash_steps:
        steps_checked += 1
        result = subprocess.run(
            ["shellcheck", "-s", "bash", "-"],
            input="#!/bin/bash\n" + step["run"],
            capture_output=True,
            text=True,
            check=False,
        )
        label = step.get("name", f"step {index}")
        if result.returncode:
            failed = 1
            print(f"::error file={path}::{label}")
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
        else:
            print(f"ok: {path} [{label}]")

print(f"summary: {actions_found} action file(s) found, {steps_checked} bash step(s) checked")
sys.exit(failed)
