#!/usr/bin/env python3
"""
Config-driven launcher for seamless_robustness.py.

Reads run-config.json, resolves per-network parameters, validates everything
that can be checked up front (unknown keys, out-of-range values, missing
input files), prints the exact command(s) that will run, and executes them
sequentially. Designed to make human error in preparing a run unlikely:
typos in config keys are rejected, edge lists are checked to exist before
any run starts, and the full plan is shown for confirmation before anything
is executed.

Usage:
    ./run-seamless.sh                       # confirm, then run every enabled network
    ./run-seamless.sh --list                # show the resolved plan and exit
    ./run-seamless.sh --dry-run             # print the commands, run nothing
    ./run-seamless.sh --only eu_railways    # run a single network
    ./run-seamless.sh --only a,b --yes      # run several, skip confirmation
    ./run-seamless.sh --force               # recompute even if already done
    ./run-seamless.sh --config other.json   # use a different config file
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
SEAMLESS_INPUT_DIR = DATA_DIR / "seamless_input"
SEAMLESS_SCRIPT = SCRIPT_DIR / "seamless_robustness.py"
DEFAULT_CONFIG = SCRIPT_DIR / "run-config.json"

VALID_PROTOCOLS = {"random", "degree", "adap_degree", "betweenness", "adap_betweenness", "seamless"}
VALID_ENGINES = {"networkx", "networkit"}

GLOBAL_KEYS = {
    "python", "seed", "n_attacks", "p_step_nodes", "m_min", "m_max", "m_step",
    "btw_update", "btw_k", "engine", "protocols", "force", "run_order", "networks",
}
NETWORK_KEYS = {
    "label", "enabled", "edge_file", "outdir", "seed", "n_attacks", "p_step_nodes",
    "m_min", "m_max", "m_step", "btw_update", "btw_k", "engine", "protocols", "force",
}
TUNABLE_KEYS = NETWORK_KEYS - {"label", "enabled", "edge_file", "outdir"}


class ConfigError(RuntimeError):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open() as f:
            cfg = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    unknown = set(cfg.keys()) - GLOBAL_KEYS
    if unknown:
        raise ConfigError(
            f"{path}: unknown top-level key(s) {sorted(unknown)}. "
            f"Allowed: {sorted(GLOBAL_KEYS)}"
        )
    if "networks" not in cfg or not isinstance(cfg["networks"], dict) or not cfg["networks"]:
        raise ConfigError(f"{path}: 'networks' must be a non-empty object.")

    for slug, entry in cfg["networks"].items():
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: networks.{slug} must be an object.")
        unknown = set(entry.keys()) - NETWORK_KEYS
        if unknown:
            raise ConfigError(
                f"{path}: unknown key(s) {sorted(unknown)} in networks.{slug}. "
                f"Allowed: {sorted(NETWORK_KEYS)}"
            )
        if "label" not in entry or not str(entry["label"]).strip():
            raise ConfigError(f"{path}: networks.{slug} is missing a non-empty 'label'.")

    return cfg


def merged_params(cfg: dict, slug: str) -> dict:
    """Global defaults overridden by any per-network keys, for the tunable keys only."""
    entry = cfg["networks"][slug]
    out = {k: cfg[k] for k in TUNABLE_KEYS if k in cfg}
    for k in TUNABLE_KEYS:
        if k in entry:
            out[k] = entry[k]
    return out


def validate_params(slug: str, p: dict) -> None:
    required = TUNABLE_KEYS
    missing = required - set(p.keys())
    if missing:
        raise ConfigError(f"{slug}: missing required parameter(s) {sorted(missing)} "
                           f"(set at top level or per-network).")

    if not isinstance(p["seed"], int):
        raise ConfigError(f"{slug}: 'seed' must be an integer.")
    if not isinstance(p["n_attacks"], int) or p["n_attacks"] < 1:
        raise ConfigError(f"{slug}: 'n_attacks' must be an integer >= 1.")
    if not isinstance(p["p_step_nodes"], int) or p["p_step_nodes"] < 1:
        raise ConfigError(f"{slug}: 'p_step_nodes' must be an integer >= 1.")
    for k in ("m_min", "m_max", "m_step"):
        if not isinstance(p[k], int) or p[k] < 1:
            raise ConfigError(f"{slug}: '{k}' must be an integer >= 1.")
    if p["m_max"] < p["m_min"]:
        raise ConfigError(f"{slug}: m_max ({p['m_max']}) must be >= m_min ({p['m_min']}).")
    if not isinstance(p["btw_update"], int) or p["btw_update"] < 1:
        raise ConfigError(f"{slug}: 'btw_update' must be an integer >= 1.")
    if p["btw_k"] is not None and (not isinstance(p["btw_k"], int) or p["btw_k"] < 1):
        raise ConfigError(f"{slug}: 'btw_k' must be null or an integer >= 1.")
    if p["engine"] not in VALID_ENGINES:
        raise ConfigError(f"{slug}: 'engine' must be one of {sorted(VALID_ENGINES)}, got {p['engine']!r}.")
    if not isinstance(p["protocols"], list) or not p["protocols"]:
        raise ConfigError(f"{slug}: 'protocols' must be a non-empty list.")
    bad = set(p["protocols"]) - VALID_PROTOCOLS
    if bad:
        raise ConfigError(f"{slug}: unknown protocol(s) {sorted(bad)}. Allowed: {sorted(VALID_PROTOCOLS)}")
    if not isinstance(p["force"], bool):
        raise ConfigError(f"{slug}: 'force' must be true or false.")

    if p["btw_update"] == 1 and "adap_betweenness" in p["protocols"]:
        print(
            f"  WARNING [{slug}]: btw_update=1 with adap_betweenness recomputes exact "
            f"betweenness after every single node removal. On networks beyond a few "
            f"hundred nodes this is intractable (can be hundreds to thousands of hours). "
            f"Confirm this is intentional.",
            file=sys.stderr,
        )


def resolve_edge_file(cfg: dict, slug: str) -> Path:
    entry = cfg["networks"][slug]
    if "edge_file" in entry:
        p = Path(entry["edge_file"])
        return p if p.is_absolute() else (SEAMLESS_INPUT_DIR / p)
    return SEAMLESS_INPUT_DIR / slug / f"{slug}_edgelist.txt"


def resolve_outdir(cfg: dict, slug: str) -> str:
    entry = cfg["networks"][slug]
    return entry.get("outdir", f"seamless_output/{slug}")


def read_edgelist_header(path: Path) -> Optional[tuple[int, int]]:
    """Best-effort N/E read from the '# N=.. E=..' header line written by
    prepare_seamless_inputs.py, used only for the informational cost estimate."""
    try:
        with path.open() as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                m = re.match(r"#\s*N=(\d+)\s+E=(\d+)", line.strip())
                if m:
                    return int(m.group(1)), int(m.group(2))
    except OSError:
        return None
    return None


def build_command(python_exe: str, label: str, edge_file: Path, outdir: str, p: dict) -> list[str]:
    cmd = [
        python_exe, str(SEAMLESS_SCRIPT),
        "--edge-file", str(edge_file),
        "--label", label,
        "--outdir", outdir,
        "--seed", str(p["seed"]),
        "--n-attacks", str(p["n_attacks"]),
        "--p-step-nodes", str(p["p_step_nodes"]),
        "--m-min", str(p["m_min"]),
        "--m-max", str(p["m_max"]),
        "--m-step", str(p["m_step"]),
        "--btw-update", str(p["btw_update"]),
        "--engine", p["engine"],
        "--protocols", *p["protocols"],
    ]
    if p["btw_k"] is not None:
        cmd += ["--btw-k", str(p["btw_k"])]
    if p["force"]:
        cmd += ["--force"]
    return cmd


def ordered_slugs(cfg: dict) -> list[str]:
    all_slugs = list(cfg["networks"].keys())
    order = cfg.get("run_order")
    if not order:
        return all_slugs
    unknown = set(order) - set(all_slugs)
    if unknown:
        raise ConfigError(f"run_order references unknown network(s) {sorted(unknown)}.")
    missing = set(all_slugs) - set(order)
    return list(order) + [s for s in all_slugs if s in missing]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to run-config.json.")
    parser.add_argument("--only", type=str, default=None,
                         help="Comma-separated list of network slugs to run (default: all enabled).")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument("--list", action="store_true", help="Print the resolved plan and exit.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument("--force", action="store_true", help="Force --force on every selected network.")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        slugs = ordered_slugs(cfg)

        if args.only:
            requested = [s.strip() for s in args.only.split(",") if s.strip()]
            unknown = set(requested) - set(slugs)
            if unknown:
                raise ConfigError(f"--only references unknown network(s) {sorted(unknown)}. "
                                   f"Available: {sorted(slugs)}")
            slugs = [s for s in slugs if s in requested]
        else:
            slugs = [s for s in slugs if cfg["networks"][s].get("enabled", True)]

        if not slugs:
            raise ConfigError("No networks selected (check 'enabled' flags / --only).")

        python_exe = cfg.get("python", "python3")
        if not SEAMLESS_SCRIPT.exists():
            raise ConfigError(f"seamless_robustness.py not found at {SEAMLESS_SCRIPT}")

        plan: list[tuple[str, str, Path, str, list[str]]] = []
        for slug in slugs:
            entry = cfg["networks"][slug]
            label = entry["label"]
            p = merged_params(cfg, slug)
            validate_params(slug, p)
            if args.force:
                p["force"] = True

            edge_file = resolve_edge_file(cfg, slug)
            outdir = resolve_outdir(cfg, slug)

            if not edge_file.exists():
                raise ConfigError(
                    f"{slug}: edge list not found at {edge_file}\n"
                    f"  Run prepare_seamless_inputs.py first to generate SEAMLESS inputs."
                )

            cmd = build_command(python_exe, label, edge_file, outdir, p)
            plan.append((slug, label, edge_file, outdir, cmd))
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("=" * 78)
    print(f"Config:      {args.config}")
    print(f"Data dir:    {DATA_DIR}")
    print(f"Networks:    {len(plan)} selected -> {[s for s, *_ in plan]}")
    print("=" * 78)
    for slug, label, edge_file, outdir, cmd in plan:
        header = read_edgelist_header(edge_file)
        size_str = f"N={header[0]:,} E={header[1]:,}" if header else "(size unknown)"
        print(f"\n[{slug}] {label}  {size_str}")
        print(f"  edge file: {edge_file}")
        print(f"  outdir:    {DATA_DIR / outdir if not Path(outdir).is_absolute() else outdir}")
        print(f"  command:   {shlex.join(cmd)}")
    print()

    if args.list:
        return 0

    if args.dry_run:
        print("Dry run: no commands executed.")
        return 0

    if not args.yes:
        reply = input(f"Proceed running {len(plan)} network(s) sequentially? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted.")
            return 1

    for i, (slug, label, edge_file, outdir, cmd) in enumerate(plan, start=1):
        print("\n" + "#" * 78)
        print(f"# [{i}/{len(plan)}] {slug} ({label})")
        print("#" * 78)
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(
                f"\nERROR: run for '{slug}' exited with code {result.returncode}. Stopping.\n"
                f"Partial results are preserved under 'partial/' and this launcher is "
                f"resumable: re-run the same command to continue from where it left off.",
                file=sys.stderr,
            )
            return result.returncode

    print("\nAll selected networks completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
