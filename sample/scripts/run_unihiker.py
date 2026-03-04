"""Python wrapper for the UNIHIKER receiver launch script.

Calls ``sample/scripts/run_unihiker.sh`` via :func:`subprocess.run`,
allowing Python code to start the UNIHIKER receiver without invoking
the shell directly.

Usage from Python::

    from sample.scripts.run_unihiker import run_unihiker

    run_unihiker()
    run_unihiker(debug=True, log_dir="/var/log/ble-agent")

Usage from CLI::

    python sample/scripts/run_unihiker.py [--debug] [--log-dir DIR]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _resolve_script_path() -> Path:
    """Resolve the absolute path to ``run_unihiker.sh``.

    Returns:
        Absolute path to the shell script.

    Raises:
        FileNotFoundError: If the shell script does not exist.
    """
    script = Path(__file__).resolve().parent / "run_unihiker.sh"
    if not script.exists():
        raise FileNotFoundError(f"Shell script not found: {script}")
    return script


def run_unihiker(
    debug: bool = False,
    log_dir: str = "/tmp/ble-key-agent",
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Launch the UNIHIKER receiver by running ``run_unihiker.sh``.

    Args:
        debug: Pass ``--debug`` flag to enable DEBUG level logging.
        log_dir: Log file output directory.
        extra_args: Additional CLI arguments to forward to the script.

    Returns:
        Completed process result.

    Raises:
        FileNotFoundError: If ``run_unihiker.sh`` is missing.
        subprocess.CalledProcessError: If the script exits with non-zero.
    """
    script = _resolve_script_path()

    cmd: list[str] = [str(script)]
    if debug:
        cmd.append("--debug")
    cmd.extend(["--log-dir", log_dir])
    if extra_args:
        cmd.extend(extra_args)

    return subprocess.run(cmd, check=True)


def main() -> None:
    """Entry point for direct CLI execution."""
    parser = argparse.ArgumentParser(
        description="Python wrapper for run_unihiker.sh"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG level logging on console",
    )
    parser.add_argument(
        "--log-dir",
        default="/tmp/ble-key-agent",
        help="Directory for log files (default: /tmp/ble-key-agent)",
    )
    args, remaining = parser.parse_known_args()

    try:
        run_unihiker(
            debug=args.debug,
            log_dir=args.log_dir,
            extra_args=remaining if remaining else None,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
