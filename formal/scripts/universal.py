#!/usr/bin/env python3
"""Run one installed candidate generator against a compiled blueprint snapshot.

Adapts the workflow and theorem-local reporting in sayyadirfanali's PR #44
(99a5734). Expected-result and waiver handling follows the distinction in
Jonathan's PR #47 (0dde8ae). Property statements stay in process_blueprint.py.
"""
import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import process_blueprint as blueprint


@dataclass(frozen=True)
class Family:
    property_id: str
    generator: str
    expected: str = "Valid"
    requires_applicability: bool = False


# Expectations belong to the implementation, not the waiver configuration.
FAMILIES = {
    "otherPurpose": Family("UP-001", "other_purpose_checks"),
    "malformedRedeemer": Family("UP-005", "malformed_redeemer_checks"),
    "returnDatum": Family("UP-006", "return_datum_checks"),
}
LOCATION = re.compile(r"^(.*?\.lean):(\d+):(\d+):\s*(error|warning|info):\s*(.*)$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FALSIFIED = {"❌ Falsified", "✅ Expected Falsified"}


class WorkflowError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def theorem_ranges(source):
    """Names and line ranges, adapted from #44's `theorems`."""
    lines = source.splitlines()
    starts = [(m.group(1), i + 1) for i, line in enumerate(lines)
              if (m := re.match(r"theorem\s+([A-Za-z0-9_]+)\b", line))]
    if len({name for name, _ in starts}) != len(starts):
        raise WorkflowError("duplicate generated theorem names")
    return [(name, start, starts[i + 1][1] - 1 if i + 1 < len(starts) else len(lines))
            for i, (name, start) in enumerate(starts)]


def parse_results(source, target, formal, output):
    """Read only diagnostics belonging to each generated theorem; retain all evidence."""
    ranges = theorem_ranges(source)
    messages = {name: [] for name, _, _ in ranges}
    problems = []
    error_count = 0
    for raw in ANSI.sub("", output).splitlines():
        match = LOCATION.match(raw)
        if match is None:
            if re.match(r"(?:error|fatal error):", raw):
                problems.append(raw)
            continue
        path, line, col, level, message = match.groups()
        error_count += level == "error"
        where = (formal / path).resolve()
        name = next((n for n, start, end in ranges if start <= int(line) <= end), None)
        if where != target.resolve() or name is None:
            if level == "error":
                problems.append(raw)
            continue
        messages[name].append((level, message, (int(line), int(col))))

    results = {}
    for name, diagnostics in messages.items():
        observed = set()
        falsified_at = {pos for _, msg, pos in diagnostics if msg in FALSIFIED}
        invalid = False
        for level, msg, pos in diagnostics:
            if msg in FALSIFIED:
                observed.add("Falsified")
            elif msg in ("✅ Valid", "❌ Unexpected Valid") or (
                    level == "warning" and msg.startswith("declaration uses 'blasterProven'")):
                observed.add("Valid")
            elif level == "error":
                # These are the pinned Blaster's counterexample details, not extra failures.
                detail = msg == "Counterexample:" or msg.startswith("- ") or msg == (
                    "Tactic `blaster` failed: Goal was falsified (see counterexample above)")
                if not (pos in falsified_at and detail):
                    invalid = True
            elif "sorry" in msg or "Undetermined" in msg:
                invalid = True
        verdict = "Error" if invalid or len(observed) > 1 else next(iter(observed), "NoResult")
        results[name] = {"verdict": verdict, "solver_results": sorted(observed),
                         "diagnostics": [msg for _, msg, _ in diagnostics]}
    return results, problems, error_count


def interpret(main, expected, applies=None, requires_applicability=False):
    if main not in ("Valid", "Falsified"):
        return "INCONCLUSIVE"
    if requires_applicability or applies is not None:
        if applies not in ("Valid", "Falsified"):
            return "INCONCLUSIVE"
        if applies == "Falsified":
            return "NOT_APPLICABLE" if main == "Valid" else "INCONCLUSIVE"
    return "PASS" if main == expected else "FAIL"


def load_waivers(path):
    if path is None:
        return {}
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise WorkflowError("waivers must be an object keyed by module.validator")
    fields = {"blueprint_sha256", "reason", "owner", "until"}
    for validator, checks in config.items():
        if not isinstance(validator, str) or not isinstance(checks, dict):
            raise WorkflowError("invalid validator waiver entry")
        for check, item in checks.items():
            if not isinstance(check, str) or not isinstance(item, dict) or set(item) != fields:
                raise WorkflowError("each waiver needs blueprint_sha256, reason, owner, and until")
            if any(not isinstance(v, str) or not v.strip() for v in item.values()):
                raise WorkflowError("waiver fields must be nonempty strings")
            if not re.fullmatch(r"[0-9a-f]{64}", item["blueprint_sha256"]):
                raise WorkflowError("waiver blueprint_sha256 must be 64 lowercase hex digits")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["until"]):
                raise WorkflowError("waiver until must be YYYY-MM-DD")
            date.fromisoformat(item["until"])
    return config


def review_result(row, config, validator, snapshot, today):
    row = dict(row, waived=False)
    item = config.get(validator, {}).get(row["check"])
    if item is None:
        return row
    row["waiver"] = item
    if item["blueprint_sha256"] != snapshot:
        row["waiver_note"] = "different blueprint snapshot"
    elif date.fromisoformat(item["until"]) < today:
        row["waiver_note"] = "expired"
    elif row["result"] in ("FAIL", "NOT_APPLICABLE"):
        row["waived"] = True
    else:
        row["waiver_note"] = "does not apply to this result"
    return row


def exit_code(rows, problems):
    if problems or not rows or any(r["result"] == "INCONCLUSIVE" or (
            r["result"] == "NOT_APPLICABLE" and not r["waived"]) for r in rows):
        return 2
    if any(r["result"] == "FAIL" and not r["waived"] for r in rows):
        return 1
    return 0


def command(args, cwd, deadline, log):
    """One shared wall-clock budget; stop the child process group on timeout."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WorkflowError("time limit reached before starting the next command")
    with log.open("w") as output:
        child = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        stopped = False
        try:
            child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            stopped = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=2)
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=2)
            raise
    return child.returncode, stopped, log.read_text(errors="replace")


def installed_dependencies(formal, deadline, record):
    """Require existing clean dependency checkouts at the lockfile revisions."""
    manifest = json.loads((formal / "lake-manifest.json").read_text())
    for package in manifest["packages"]:
        if package["type"] != "git" or not re.fullmatch(r"[A-Za-z0-9_-]+", package["name"]):
            raise WorkflowError("unsupported dependency entry; prepare the locked environment first")
        directory = formal / manifest["packagesDir"] / package["name"]
        if not directory.is_dir():
            raise WorkflowError(f"locked dependency {package['name']} is missing; prepare it first")
        rc, stopped, head = command(["git", "rev-parse", "HEAD"], directory, deadline,
                                   record / f"dependency-{package['name']}.log")
        if stopped or rc or head.strip() != package["rev"]:
            raise WorkflowError(f"locked dependency {package['name']} has a different revision")
        rc, stopped, changes = command(["git", "status", "--porcelain", "--untracked-files=no"], directory,
                                      deadline, record / f"dependency-{package['name']}-status.log")
        if stopped or rc or changes.strip():
            raise WorkflowError(f"locked dependency {package['name']} has tracked modifications")


def check_file(path, formal, family, output, returncode, stopped):
    raw, problems, errors = parse_results(path.read_text(), path, formal, output)
    if stopped:
        problems.append("time limit reached; partial results are not a completed run")
    elif returncode not in (0, 1) or (returncode == 1 and errors == 0) or (returncode == 0 and errors):
        problems.append(f"unexpected Lean exit status {returncode}")
    rows = []
    for name, evidence in raw.items():
        if name.endswith("_applies"):
            if name[:-8] not in raw:
                problems.append(f"orphan applicability check: {name}")
            continue
        applies = raw.get(name + "_applies")
        result = interpret(evidence["verdict"], family.expected,
                           applies["verdict"] if applies else None, family.requires_applicability)
        rows.append({"check": name, "result": result, "expected": family.expected,
                     "evidence": evidence, "applicability": applies})
    return rows, problems


def run(args, formal):
    deadline = time.monotonic() + args.timeout
    family = FAMILIES[args.check]
    config_path = args.config
    if config_path is None and (formal / "universal.json").exists():
        config_path = formal / "universal.json"
    config = load_waivers(config_path)
    if not callable(getattr(blueprint, family.generator, None)):
        raise WorkflowError(f"{args.check} is not available in this checkout; integrate its candidate generator first")
    snapshot = args.blueprint.read_bytes()
    bp = json.loads(snapshot)
    if not isinstance(bp, dict) or not isinstance(bp.get("preamble"), dict):
        raise WorkflowError("blueprint and preamble must be JSON objects")
    if bp["preamble"].get("plutusVersion") != "v3":
        raise WorkflowError("an explicit Plutus V3 blueprint is required")
    entries = blueprint.find_entries(bp, args.validator)
    validator = ".".join(entries[0]["title"].split(".")[:2])
    code = blueprint.compiled_code(entries)
    if not isinstance(code, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2})+", code):
        raise WorkflowError("compiledCode must be nonempty, even-length hex")
    if not re.fullmatch(r"[A-Za-z0-9_/-]+\.[A-Za-z0-9_]+", validator):
        raise WorkflowError("unsupported blueprint validator name")

    records = formal / ".lake/universal"
    records.mkdir(parents=True, exist_ok=True)
    record = Path(tempfile.mkdtemp(prefix="run-", dir=records))
    saved_blueprint = record / "plutus.json"
    saved_blueprint.write_bytes(snapshot)
    generator_source = Path(blueprint.__file__).read_bytes()
    saved_generator = record / "process_blueprint.py"
    saved_generator.write_bytes(generator_source)
    runner_source = Path(__file__).read_bytes()
    (record / "universal.py").write_bytes(runner_source)
    pins = {name: (formal / name).read_bytes() for name in ("lake-manifest.json", "lakefile.toml", "lean-toolchain")}
    report = {"validator": validator, "property": family.property_id, "family": args.check,
              "blueprint_sha256": sha256(snapshot), "compiled_code_sha256": sha256(bytes.fromhex(code)),
              "generator_sha256": sha256(generator_source),
              "runner_sha256": sha256(runner_source),
              "environment_sha256": {name: sha256(data) for name, data in pins.items()},
              "results": [], "problems": []}
    generated = None
    try:
        installed_dependencies(formal, deadline, record)
        generated = Path(tempfile.mkdtemp(prefix="WorkflowRun", dir=formal / "Formal"))
        out = generated / "Blueprint"
        source = record / "generated"
        scripts = record / "Scripts"
        scripts.mkdir()
        cbor = Path(blueprint.cbor_path_of(entries, str(scripts)))
        cbor.write_text(code)
        rc, stopped, _ = command([sys.executable, "-I", "-B", str(saved_generator),
                                  str(saved_blueprint), validator, "--out", str(out.relative_to(formal)),
                                  "--scripts", str(scripts.relative_to(formal)), "--check", args.check],
                                 formal, deadline, record / "generation.log")
        if stopped or rc:
            raise WorkflowError("generation timed out or failed; no generated check was run")
        checks = out / "Checks.lean"
        if not checks.exists() or not theorem_ranges(checks.read_text()):
            raise WorkflowError("generator produced no check obligations")
        names = [name for name, _, _ in theorem_ranges(checks.read_text())]
        if any(name != args.check and not name.startswith(args.check + "_") for name in names):
            raise WorkflowError("generated obligations do not match the selected check")
        shutil.copytree(out, source)
        report["generated_sha256"] = {p.name: sha256(p.read_bytes()) for p in source.iterdir() if p.is_file()}
        imports = {m.group(1) for path in out.glob("*.lean") for line in path.read_text().splitlines()
                   if (m := re.fullmatch(r"import (Formal\.[A-Za-z0-9_.]+)", line))}
        if not imports:
            raise WorkflowError("generated checks have no declared project dependencies")
        report["tool_versions"] = {}
        for tool in ("lake", "z3"):
            rc, stopped, version = command([tool, "--version"], formal, deadline, record / f"{tool}-version.log")
            if stopped or rc:
                raise WorkflowError(f"{tool} is unavailable; prepare the pinned toolchain first")
            report["tool_versions"][tool] = version.strip()
        # Build helpers and generated types only. The actual checks always run freshly below.
        rc, stopped, _ = command(["lake", "--no-cache", "build", *sorted(imports)], formal,
                                 deadline, record / "build.log")
        if stopped or rc:
            raise WorkflowError("prerequisite build timed out or failed; no check verdict")
        rc, stopped, output = command(["lake", "--no-cache", "env", "lean", str(checks)], formal,
                                      deadline, record / "checks.log")
        rows, problems = check_file(checks, formal, family, output, rc, stopped)
        report["problems"].extend(problems)
        today = datetime.now(timezone.utc).date()
        report["results"] = [review_result(row, config, validator, report["blueprint_sha256"], today) for row in rows]
    except KeyboardInterrupt:
        report["problems"].append("interrupted; no completed run")
    except (WorkflowError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        report["problems"].append(str(error))
    finally:
        if generated is not None:
            shutil.rmtree(generated)
            for directory in (formal / ".lake/build/lib/lean/Formal", formal / ".lake/build/ir/Formal"):
                owned = directory / generated.name
                if owned.exists():
                    shutil.rmtree(owned)
        for name, content in pins.items():
            if not (formal / name).is_file() or (formal / name).read_bytes() != content:
                report["problems"].append(f"{name} changed during the run")
    report["exit_code"] = exit_code(report["results"], report["problems"])
    (record / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in report["results"]:
        annotation = " (waived)" if row["waived"] else ""
        print(f"{row['result']:<15} {family.property_id} {row['check']}{annotation}")
        if row.get("waiver_note"):
            print(f"  waiver ignored: {row['waiver_note']}")
    for problem in report["problems"]:
        print(f"INCONCLUSIVE    {problem}")
    print(f"Report: {record / 'report.json'}")
    return report["exit_code"]


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("validator", help="module.validator or an unambiguous validator name")
    parser.add_argument("--check", required=True, choices=FAMILIES)
    parser.add_argument("--config", type=Path, help="waivers file; defaults to formal/universal.json when present")
    parser.add_argument("--timeout", type=positive_seconds, default=30, help="wall-clock seconds for the whole run (default 30)")
    args = parser.parse_args(argv)
    try:
        return run(args, Path(__file__).resolve().parents[1])
    except (WorkflowError, blueprint.ExtractError, OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        print(f"INCONCLUSIVE    {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
