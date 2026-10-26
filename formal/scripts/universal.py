#!/usr/bin/env python3
"""Run the Lean of one validator, or of all of them, for the justfile. Run from formal/.

  universal.py run <folder> <validator> <blueprint> [arg] [--counterexamples] [--from-log]
      no arg      the hand-written proofs: lake build of <folder>.lean
      a check     one family of universal checks, such as doubleSatisfaction, with someAccepted
      other       one file of the hand-written proofs: lake build of <folder>/<arg>.lean
  universal.py verify <blueprint> <validator>...   copy each validator's code, then lake build
  universal.py build <module>                      lake build of <module>

Before anything that reads compiled code, `aiken build` runs in the blueprint's folder when it has
an aiken.toml, and the validator's compiledCode is copied to Scripts/<module>.<validator>.cbor.
The copy is rewritten only when its bytes change; then the Lake build files of every module that
reads it are deleted, because Lake does not know that `#import_uplc` reads the file.

A family of universal checks runs with `lake env lean` on <folder>/Blueprint/Checks.lean, stopped
after 5 minutes. Its output is shown and saved to logs/<folder below Formal>/<check>.log. Each
theorem gets a status from the messages at its lines only: proved (Blaster's `blasterProven`
warning), counterexample (`Falsified`), error (another error), or no result (nothing, for example
because the time limit came first). Then each check gets one line, by section:
  holds            proved, and its `_applies` check proved, when it has one
  does not apply   proved, but its `_applies` check has a counterexample: no changed transaction
                   of the kind exists, so the check says nothing
  FAILS            a counterexample
  error, no result as for the theorem
--counterexamples prints each counterexample; --from-log summarises the saved log without running Lean.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_blueprint import FAMILIES, SECTIONS  # noqa: E402

SCRIPTS = Path("Scripts")
LIMIT = 300
ANNOTATE = "scripts/annotate-blaster-logs.awk"
PROCESS = "scripts/process_blueprint.py"
LOCATION = re.compile(r"([A-Za-z0-9_./-]+\.lean):(\d+):(\d+):")


def fail(msg):
    sys.exit(f"universal: {msg}")


def module_of(folder):
    """`Formal/Vesting/Linear` -> `Formal.Vesting.Linear`."""
    parts = Path(folder).parts
    if not parts or parts[0] != "Formal":
        fail(f"the folder `{folder}` is not under Formal/")
    for p in parts:
        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", p):
            fail(f"`{p}` in `{folder}` is not a Lean module name")
    return ".".join(parts)


def lake_build(targets):
    cmd = f"set -o pipefail; lake build {' '.join(targets)} 2>&1 | awk -f {ANNOTATE}"
    if subprocess.run(["bash", "-c", cmd]).returncode != 0:
        fail(" ".join(["lake build", *targets, "failed"]))


def heads(plutus):
    """The `module.validator` names in the blueprint."""
    bp = json.loads(Path(plutus).read_text())
    return sorted({".".join(v["title"].split(".")[:2]) for v in bp.get("validators", [])})


def aiken_build(plutus):
    folder = Path(plutus).parent
    if (folder / "aiken.toml").exists():
        print(f"aiken build in {folder}", flush=True)
        if subprocess.run(["aiken", "build"], cwd=folder).returncode != 0:
            fail(f"aiken build in {folder} failed")
    if not Path(plutus).exists():
        fail(f"no blueprint at {plutus}")


def check_validator(plutus, validator):
    names = heads(plutus)
    if not any(h == validator or h.split(".")[1] == validator for h in names):
        fail(f"no validator `{validator}` in {plutus}; it has: {', '.join(names)}")


def copy_cbor(plutus, validator):
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-I", PROCESS, plutus, validator, "--cbor-only", "--scripts", tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail(r.stderr.strip())
        written = Path(r.stdout.strip())
        out = SCRIPTS / written.name
        if out.exists() and out.read_bytes() == written.read_bytes():
            print(f"  {out} (unchanged)")
            return
        print(f"  {out} (changed)")
        SCRIPTS.mkdir(exist_ok=True)
        shutil.move(written, out)
    for lean in Path("Formal").rglob("*.lean"):
        if f"Scripts/{out.name}" not in lean.read_text():
            continue
        mod = lean.with_suffix("").as_posix()
        print(f"    invalidate the Lake build files of {mod}")
        for suffix in [".olean", ".olean.hash", ".ilean", ".ilean.hash", ".trace"]:
            Path(f".lake/build/lib/lean/{mod}{suffix}").unlink(missing_ok=True)
        for suffix in [".c", ".c.hash", ".setup.json"]:
            Path(f".lake/build/ir/{mod}{suffix}").unlink(missing_ok=True)


def prepare(plutus, validator):
    aiken_build(plutus)
    check_validator(plutus, validator)
    copy_cbor(plutus, validator)


def theorems(path):
    """[(name, first line, last line)], each theorem running up to the line before the next one."""
    lines = Path(path).read_text().splitlines()
    starts = [(i + 1, re.match(r"theorem\s+(\S+)", l).group(1))
              for i, l in enumerate(lines) if re.match(r"theorem\s", l)]
    return [(name, start, starts[k + 1][0] - 1 if k + 1 < len(starts) else len(lines))
            for k, (start, name) in enumerate(starts)]


def statuses(lean_file, log):
    """{theorem: status} and {theorem: [message lines]}, from the log."""
    thms = theorems(lean_file)
    status = {n: "no result" for n, _, _ in thms}
    details = {n: [] for n, _, _ in thms}
    target = Path(lean_file).as_posix()
    current = None
    for raw in Path(log).read_text(errors="replace").splitlines():
        line = raw.replace("\r", "")
        m = LOCATION.search(line)
        where = Path(m.group(1)).as_posix() if m else ""
        if m and (where.endswith(target) or target.endswith(where)):
            lineno = int(m.group(2))
            current = next((n for n, s, e in thms if s <= lineno <= e), None)
            if current is None:
                continue
            if "blasterProven" in line and status[current] == "no result":
                status[current] = "proved"
            elif "Falsified" in line:
                status[current] = "counterexample"
            elif "error" in line and status[current] != "counterexample":
                status[current] = "error"
            details[current].append(line[m.end():].strip())
        elif m:
            current = None
        elif current is not None and line.strip():
            details[current].append(line.strip())
    return status, details


def reading(main, applies):
    if main == "counterexample":
        return "FAILS: counterexample"
    if main != "proved":
        return main
    if applies in (None, "proved"):
        return "holds"
    if applies == "counterexample":
        return "does not apply"
    return f"holds (applies: {applies})"


def summarise(lean_file, log, timed_out, counterexamples):
    status, details = statuses(lean_file, log)
    rows = {}
    for name in status:
        if name.endswith("_applies"):
            continue
        family = name.split("_")[0]
        rows.setdefault(family, []).append(
            (name[len(family) + 1:], reading(status[name], status.get(name + "_applies")), name))
    width = max((len(f) for f in rows), default=10)
    rest = max((len(r) for rs in rows.values() for r, _, _ in rs), default=10)
    print()
    print(f"Summary of {lean_file}" + (" (stopped by the time limit)" if timed_out else ""))
    counts = {}
    for _, title, families in SECTIONS:
        present = [f for f in families if f in rows]
        if not present:
            continue
        print(f"  {title}")
        for f in present:
            for r, read, name in rows[f]:
                print(f"    {f:<{width}}  {r:<{rest}}  {read}")
                key = read.split(":")[0].split(" (")[0]
                counts[key] = counts.get(key, 0) + 1
                if counterexamples and read.startswith("FAILS"):
                    for d in details[name]:
                        print(f"        {d}")
    print("  " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))


def run_lean(lean_file, log):
    """`lake env lean`, shown and saved to `log`, stopped after LIMIT seconds. True if stopped."""
    print(f"universal checks: {lean_file}", flush=True)
    start = time.time()
    proc = subprocess.Popen(["lake", "env", "lean", str(lean_file)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stopped = threading.Event()

    def stop():
        stopped.set()
        proc.kill()
    timer = threading.Timer(LIMIT, stop)
    timer.start()
    with open(log, "wb") as f:
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
            f.write(line)
    proc.wait()
    timer.cancel()
    print(f"  {time.time() - start:.0f} s" + (f", stopped by the {LIMIT // 60}-minute limit" if stopped.is_set()
                                            else f", lean exited with status {proc.returncode}"))
    return stopped.is_set()


def universal_checks(folder, validator, plutus, check, counterexamples, from_log):
    blueprint = Path(folder) / "Blueprint"
    tx = blueprint / "Tx.lean"
    had_tx = tx.exists()
    r = subprocess.run([sys.executable, "-I", PROCESS, plutus, validator, "--out", str(blueprint),
                        "--scripts", str(SCRIPTS), "--check", check])
    if r.returncode != 0:
        sys.exit(r.returncode)
    if not had_tx:
        fail(f"wrote the stub {tx}: write the honest transactions there, then run again")
    lean_file = blueprint / "Checks.lean"
    log = Path("logs", *Path(folder).parts[1:], f"{check}.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    if from_log:
        if not log.exists():
            fail(f"no log at {log}: run the check first")
        summarise(lean_file, log, False, counterexamples)
        return
    prefix = module_of(blueprint)
    lake_build(["Formal.Universal", f"{prefix}.Types", f"{prefix}.Tx"])
    timed_out = run_lean(lean_file, log)
    summarise(lean_file, log, timed_out, counterexamples)


def run(args):
    flags = {a for a in args if a.startswith("--")}
    rest = [a for a in args if not a.startswith("--")]
    unknown = flags - {"--counterexamples", "--from-log"}
    if unknown or not 3 <= len(rest) <= 4:
        fail("usage: run <folder> <validator> <blueprint> [check | file] [--counterexamples] [--from-log]")
    folder, validator, plutus = rest[:3]
    arg = rest[3] if len(rest) == 4 else ""
    module = module_of(folder)
    universal = arg in FAMILIES
    if arg[:1].islower() and not universal:
        fail(f"no check `{arg}`; the checks are: {', '.join(FAMILIES)}")
    if not (universal and "--from-log" in flags):
        prepare(plutus, validator)
    if universal:
        universal_checks(folder, validator, plutus, arg, "--counterexamples" in flags, "--from-log" in flags)
    elif arg == "":
        if not Path(folder + ".lean").exists():
            fail(f"{folder} has no hand-written proofs ({folder}.lean)")
        lake_build([module])
    else:
        if not (Path(folder) / f"{arg}.lean").exists():
            files = sorted(p.stem for p in Path(folder).glob("*.lean"))
            fail(f"no {folder}/{arg}.lean; the argument is a check, such as doubleSatisfaction, or one of: "
                 f"{', '.join(files) or 'none'}")
        lake_build([f"{module}.{arg}"])


def main():
    if len(sys.argv) < 2:
        fail("usage: universal.py run | verify | build ...")
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "run":
        run(args)
    elif cmd == "verify" and len(args) >= 1:
        plutus, validators = args[0], args[1:]
        aiken_build(plutus)
        for v in validators:
            check_validator(plutus, v)
            copy_cbor(plutus, v)
        lake_build([])
    elif cmd == "build" and len(args) == 1:
        lake_build(args)
    else:
        fail("usage: universal.py run | verify <blueprint> <validator>... | build <module>")


if __name__ == "__main__":
    main()
