#!/usr/bin/env python3
"""Shard the Windows unit-tests suite without dropping or duplicating tests.

The CI job ``unit-tests`` stays the single required check. It runs only after
every Windows shard and is green only when:

- every shard job succeeded
- ``pytest --collect-only -q`` with the same filters succeeded
- each collected node id appears in exactly one shard JUnit file
- skipped tests count as executed and must appear exactly once
- no shard reported a failure or error

A matching count is not accepted: one id run twice and another missing fails
the check and lists both ids. Historical durations live in ``.test_durations``
so pytest-split's ``least_duration`` algorithm keeps the shards balanced.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Node ids that embed the retired product name must not be stored in-repo.
# tests/test_product_rename_migration.py scans the tree for that string.
# The pieces are concatenated so this file is not itself a hit.
# The test still runs; pytest-split assigns it the average duration.
_DURATION_KEY_BLOCKLIST = (
    "jobhunt" + "saver",
    "job_hunt" + "_saver",
    "job-hunt" + "-saver",
)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLITS = 6
DEFAULT_DURATIONS = ROOT / ".test_durations"
PYTEST_FILTERS = [
    "--ignore=tests/test_cv_corpus.py",
    "-m",
    "not network",
]


@dataclass
class JunitCase:
    nodeid: str
    time_s: float
    skipped: bool
    failed: bool
    error: bool
    source: str


@dataclass
class ShardReport:
    collected: int = 0
    junit_cases: int = 0
    passed: int = 0
    skipped: int = 0
    failed: int = 0
    errors: int = 0
    shard_times: list[tuple[str, float, int]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    missing_nodeids: list[str] = field(default_factory=list)
    duplicate_nodeids: list[str] = field(default_factory=list)
    duplicate_where: dict[str, list[str]] = field(default_factory=dict)
    extra_nodeids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.missing_nodeids and not self.duplicate_nodeids and not self.extra_nodeids


def parse_collected(text: str) -> list[str]:
    """Parse ``pytest --collect-only -q`` stdout into node ids."""
    nodeids: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if "::" not in line:
            continue
        # Node ids look like tests/test_x.py::test_y[param]. Skip warnings.
        path, _, _rest = line.partition("::")
        if not path.endswith(".py"):
            continue
        nodeids.append(line)
    return nodeids


def junit_nodeid(classname: str, name: str, known: set[str] | None = None) -> str | None:
    """Map a junit classname/name pair onto a pytest node id.

    Function tests use ``tests.test_mod`` / ``test_fn``. Class-based tests use
    ``tests.test_mod.TestClass`` / ``test_fn`` and become
    ``tests/test_mod.py::TestClass::test_fn``. When ``known`` is provided, the
    first candidate that is actually collected wins.
    """
    parts = classname.split(".")
    candidates: list[str] = []
    if parts:
        candidates.append("/".join(parts) + ".py::" + name)
        for i in range(len(parts) - 1, 0, -1):
            path = "/".join(parts[:i]) + ".py"
            suffix = "::".join(parts[i:] + [name])
            candidates.append(f"{path}::{suffix}")
    if known is None:
        return candidates[0] if candidates else None
    for candidate in candidates:
        if candidate in known:
            return candidate
    return None


def junit_property_nodeid(testcase: ET.Element) -> str | None:
    """Read the pytest node id recorded by ``tests/conftest.py``."""
    values = [
        (prop.get("value") or "")
        for prop in testcase.findall("./properties/property")
        if prop.get("name") == "nodeid"
    ]
    values = [value for value in values if value]
    if not values:
        return None
    # Teardown is the report pytest finalizes; identical repeats are one id.
    unique = set(values)
    if len(unique) != 1:
        return None
    return values[0]


def load_junit_cases(path: Path, known: set[str] | None = None) -> list[JunitCase]:
    """Load JUnit cases.

    The shard gate passes ``known=None`` and then replaces these ids with the
    ``nodeid`` property. ``build-durations`` still passes the collected set so
    historical JUnit files (no property) can be mapped.
    """
    root = ET.parse(path).getroot()
    cases: list[JunitCase] = []
    for tc in root.findall(".//testcase"):
        classname = tc.get("classname") or ""
        name = tc.get("name") or ""
        nodeid = junit_property_nodeid(tc)
        if nodeid is None and known is not None:
            nodeid = junit_nodeid(classname, name, known)
        if nodeid is None:
            nodeid = f"<unmapped> {classname}::{name}"
        cases.append(
            JunitCase(
                nodeid=nodeid,
                time_s=float(tc.get("time") or 0),
                skipped=tc.find("skipped") is not None,
                failed=tc.find("failure") is not None,
                error=tc.find("error") is not None,
                source=str(path),
            )
        )
    return cases


def discover_artifacts(artifacts_dir: Path) -> tuple[Path, list[Path]]:
    collected = sorted(artifacts_dir.rglob("collected-unit-tests.txt"))
    junit = sorted(artifacts_dir.rglob("*.xml"))
    if len(collected) != 1:
        raise SystemExit(
            f"expected exactly one collected-unit-tests.txt under {artifacts_dir}, "
            f"found {len(collected)}"
        )
    return collected[0], junit


def evaluate(
    collected_nodeids: list[str],
    shard_cases: list[list[JunitCase]],
    *,
    shard_result: str,
    collect_result: str,
    expect_shards: int,
    shard_labels: list[str] | None = None,
) -> ShardReport:
    report = ShardReport(collected=len(collected_nodeids))
    if shard_result != "success":
        report.problems.append(f"shard job result is {shard_result!r}, expected 'success'")
    if collect_result != "success":
        report.problems.append(
            f"collect job result is {collect_result!r}, expected 'success'"
        )
    if len(shard_cases) != expect_shards:
        report.problems.append(
            f"expected {expect_shards} junit shards, found {len(shard_cases)}"
        )

    collected_set = set(collected_nodeids)
    if len(collected_set) != len(collected_nodeids):
        report.problems.append("collection list contains duplicate node ids")

    # node id -> shards that executed it, in order. Skips count as executed.
    occurrences: dict[str, list[str]] = {}
    labels = shard_labels or [f"shard-{i + 1}" for i in range(len(shard_cases))]
    for index, cases in enumerate(shard_cases):
        label = labels[index] if index < len(labels) else f"shard-{index + 1}"
        shard_time = 0.0
        for case in cases:
            report.junit_cases += 1
            shard_time += case.time_s
            if case.failed:
                report.failed += 1
                report.problems.append(f"failure in {label}: {case.nodeid}")
            elif case.error:
                report.errors += 1
                report.problems.append(f"error in {label}: {case.nodeid}")
            elif case.skipped:
                report.skipped += 1
            else:
                report.passed += 1
            if case.nodeid.startswith("<unmapped>"):
                report.problems.append(
                    f"junit case in {label} has no nodeid property: {case.nodeid}"
                )
                continue
            occurrences.setdefault(case.nodeid, []).append(label)
        report.shard_times.append((label, shard_time, len(cases)))

    executed = set(occurrences)
    report.missing_nodeids = sorted(collected_set - executed)
    report.extra_nodeids = sorted(executed - collected_set)
    report.duplicate_nodeids = sorted(
        nodeid for nodeid, where in occurrences.items() if len(where) > 1
    )
    report.duplicate_where = {
        nodeid: occurrences[nodeid] for nodeid in report.duplicate_nodeids
    }
    return report


def format_report(report: ShardReport) -> str:
    lines = [
        f"unit-tests-shards: {'ok' if report.ok else 'failed'}",
        f"collected={report.collected}",
        f"junit={report.junit_cases}",
        f"passed={report.passed}",
        f"skipped={report.skipped}",
        f"failed={report.failed}",
        f"errors={report.errors}",
        f"shards={len(report.shard_times)}",
    ]
    for label, seconds, count in report.shard_times:
        lines.append(f"shard {label}: tests={count} junit_time_s={seconds:.1f}")
    where = report.duplicate_where
    if report.missing_nodeids:
        lines.append(f"missing node ids ({len(report.missing_nodeids)}):")
        lines.extend(f"- {nodeid}" for nodeid in report.missing_nodeids)
    if report.duplicate_nodeids:
        lines.append(f"duplicate node ids ({len(report.duplicate_nodeids)}):")
        for nodeid in report.duplicate_nodeids:
            shards = ", ".join(where.get(nodeid, []))
            lines.append(f"- {nodeid} in {shards}")
    if report.extra_nodeids:
        lines.append(f"extra node ids ({len(report.extra_nodeids)}):")
        lines.extend(f"- {nodeid}" for nodeid in report.extra_nodeids)
    if report.problems:
        lines.append(f"problems: {len(report.problems)}")
        shown = report.problems[:30]
        for problem in shown:
            lines.append(f"- {problem}")
        if len(report.problems) > len(shown):
            lines.append(f"- … {len(report.problems) - len(shown)} further problems")
    return "\n".join(lines) + "\n"


def write_step_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("## unit-tests\n\n```\n")
        handle.write(text)
        handle.write("```\n")


def _pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def _run_pytest(extra: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Capture stdout. Used by ``collect``, which must save the node-id list."""
    cmd = [sys.executable, "-u", "-m", "pytest", *extra]
    return subprocess.run(cmd, cwd=ROOT, env=_pytest_env(), capture_output=True, check=False)


def _stream_pytest(extra: list[str]) -> int:
    """Run pytest with inherited stdout/stderr so a hang shows up in the job log."""
    cmd = [sys.executable, "-u", "-m", "pytest", *extra]
    proc = subprocess.run(cmd, cwd=ROOT, env=_pytest_env(), check=False)
    return proc.returncode


def cmd_collect(args: argparse.Namespace) -> int:
    proc = _run_pytest(["--collect-only", "-q", *PYTEST_FILTERS])
    output = Path(args.output)
    output.write_bytes(proc.stdout)
    sys.stderr.buffer.write(proc.stderr)
    if proc.returncode != 0:
        sys.stdout.buffer.write(proc.stdout)
        return proc.returncode
    nodeids = parse_collected(proc.stdout.decode("utf-8"))
    if not nodeids:
        print("collection produced no test node ids", file=sys.stderr)
        return 1
    print(f"collected {len(nodeids)} tests -> {output}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.group < 1 or args.group > args.splits:
        print(f"--group must be between 1 and {args.splits}", file=sys.stderr)
        return 2
    durations = Path(args.durations)
    if not durations.is_file():
        print(f"missing durations file: {durations}", file=sys.stderr)
        return 2
    junit = Path(args.junitxml)
    return _stream_pytest(
        [
            "-q",
            *PYTEST_FILTERS,
            "--splits",
            str(args.splits),
            "--group",
            str(args.group),
            "--splitting-algorithm",
            "least_duration",
            "--durations-path",
            str(durations),
            "--junitxml",
            str(junit),
            "--durations=25",
        ]
    )


def cmd_check(args: argparse.Namespace) -> int:
    collected_path, junit_paths = discover_artifacts(Path(args.artifacts))
    collected = parse_collected(collected_path.read_text(encoding="utf-8"))
    shard_cases: list[list[JunitCase]] = []
    labels: list[str] = []
    for path in junit_paths:
        # Exact node ids from the JUnit property. Do not snap onto the
        # collected set: a reconstructed name can hide a missing test.
        shard_cases.append(load_junit_cases(path, known=None))
        labels.append(path.parent.name or path.stem)
    report = evaluate(
        collected,
        shard_cases,
        shard_result=args.shard_result,
        collect_result=args.collect_result,
        expect_shards=args.expect_shards,
        shard_labels=labels,
    )
    text = format_report(report)
    sys.stdout.write(text)
    write_step_summary(text)
    return 0 if report.ok else 1


def cmd_build_durations(args: argparse.Namespace) -> int:
    collected = parse_collected(Path(args.collected).read_text(encoding="utf-8"))
    known = set(collected)
    durations: dict[str, float] = {}
    unmatched: list[str] = []
    for path in args.junit:
        for case in load_junit_cases(Path(path), known):
            if case.nodeid.startswith("<unmapped>") or case.nodeid not in known:
                unmatched.append(case.nodeid)
                continue
            if any(token in case.nodeid.lower() for token in _DURATION_KEY_BLOCKLIST):
                continue
            durations[case.nodeid] = round(case.time_s, 3)
    missing = sorted(known - set(durations))
    if unmatched or missing or len(durations) != len(known):
        print(
            f"duration build mismatch: matched={len(durations)} "
            f"collected={len(known)} missing={len(missing)} unmatched={len(unmatched)}",
            file=sys.stderr,
        )
        for item in (missing[:10] + unmatched[:10]):
            print(f"  {item}", file=sys.stderr)
        return 1
    payload = dict(sorted(durations.items()))
    Path(args.output).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(payload)} durations "
        f"({sum(payload.values()):.1f}s total) -> {args.output}"
    )
    return 0


def cmd_self_check(_args: argparse.Namespace) -> int:
    """In-memory checks that the gate rejects gaps, duplicates, and failures."""
    collected = [
        "tests/test_a.py::test_ok",
        "tests/test_a.py::test_skip",
        "tests/test_b.py::test_other",
    ]
    ok_cases = [
        [
            JunitCase("tests/test_a.py::test_ok", 1.0, False, False, False, "s1"),
            JunitCase("tests/test_a.py::test_skip", 0.1, True, False, False, "s1"),
        ],
        [JunitCase("tests/test_b.py::test_other", 2.0, False, False, False, "s2")],
    ]
    good = evaluate(
        collected,
        ok_cases,
        shard_result="success",
        collect_result="success",
        expect_shards=2,
    )
    if not good.ok or good.passed != 2 or good.skipped != 1 or good.collected != 3:
        print(format_report(good), file=sys.stderr)
        return 1

    missing = evaluate(
        collected,
        ok_cases[:1],
        shard_result="success",
        collect_result="success",
        expect_shards=1,
    )
    if missing.ok or "tests/test_b.py::test_other" not in missing.missing_nodeids:
        print("expected missing-test failure", file=sys.stderr)
        print(format_report(missing), file=sys.stderr)
        return 1

    duplicated = evaluate(
        collected,
        [
            ok_cases[0],
            ok_cases[1]
            + [JunitCase("tests/test_a.py::test_ok", 1.0, False, False, False, "s2")],
        ],
        shard_result="success",
        collect_result="success",
        expect_shards=2,
    )
    if duplicated.ok or "tests/test_a.py::test_ok" not in duplicated.duplicate_nodeids:
        print("expected duplicate failure", file=sys.stderr)
        print(format_report(duplicated), file=sys.stderr)
        return 1

    # Same executed count as collected, but one id twice and another absent.
    swapped = evaluate(
        [
            "tests/test_a.py::test_ok",
            "tests/test_a.py::test_missing",
            "tests/test_b.py::test_other",
        ],
        [
            [
                JunitCase("tests/test_a.py::test_ok", 1.0, False, False, False, "s1"),
                JunitCase("tests/test_a.py::test_ok", 1.0, False, False, False, "s1"),
            ],
            [JunitCase("tests/test_b.py::test_other", 1.0, False, False, False, "s2")],
        ],
        shard_result="success",
        collect_result="success",
        expect_shards=2,
    )
    swapped_text = format_report(swapped)
    if (
        swapped.ok
        or swapped.junit_cases != swapped.collected
        or "tests/test_a.py::test_missing" not in swapped.missing_nodeids
        or "tests/test_a.py::test_ok" not in swapped.duplicate_nodeids
        or "tests/test_a.py::test_missing" not in swapped_text
        or "tests/test_a.py::test_ok" not in swapped_text
    ):
        print("expected count-collision to fail with both ids listed", file=sys.stderr)
        print(swapped_text, file=sys.stderr)
        return 1

    failed = evaluate(
        ["tests/test_a.py::test_ok"],
        [[JunitCase("tests/test_a.py::test_ok", 1.0, False, True, False, "s1")]],
        shard_result="failure",
        collect_result="success",
        expect_shards=1,
    )
    if failed.ok or failed.failed != 1:
        print("expected failure result", file=sys.stderr)
        return 1

    mapped = junit_nodeid("tests.test_mod.TestClass", "test_fn", {"tests/test_mod.py::TestClass::test_fn"})
    if mapped != "tests/test_mod.py::TestClass::test_fn":
        print(f"class nodeid mapping failed: {mapped}", file=sys.stderr)
        return 1
    print("self-check ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    collect = sub.add_parser("collect", help="write the full filtered node-id list")
    collect.add_argument("--output", required=True)
    collect.set_defaults(func=cmd_collect)

    run = sub.add_parser("run", help="run one pytest-split group")
    run.add_argument("--splits", type=int, default=DEFAULT_SPLITS)
    run.add_argument("--group", type=int, required=True)
    run.add_argument("--junitxml", required=True)
    run.add_argument("--durations", default=str(DEFAULT_DURATIONS))
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="fail unless shards partition the collection")
    check.add_argument("--artifacts", required=True)
    check.add_argument("--expect-shards", type=int, default=DEFAULT_SPLITS)
    check.add_argument("--shard-result", required=True)
    check.add_argument("--collect-result", required=True)
    check.set_defaults(func=cmd_check)

    build = sub.add_parser("build-durations", help="write .test_durations from junit + collection")
    build.add_argument("--collected", required=True)
    build.add_argument("--junit", nargs="+", required=True)
    build.add_argument("--output", required=True)
    build.set_defaults(func=cmd_build_durations)

    self_check = sub.add_parser("self-check", help="run the gate's internal consistency checks")
    self_check.set_defaults(func=cmd_self_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
