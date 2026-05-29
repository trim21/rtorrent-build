"""Shared subprocess wrapper."""

import os
import shlex
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path


class CmdError(subprocess.CalledProcessError):
    pass


class Commander:
    """Runs shell commands, prints them, and logs full output to a file.

    stdout and stderr are merged (like ``2>&1``) and streamed in real time to
    both the console and the log file, giving terminal-like behaviour.
    """

    def __init__(self, log_path: Path, jobs: int | None = None) -> None:
        self.log_path = log_path
        self._jobs = jobs if jobs is not None else (os.cpu_count() or 1)

    def nproc_args(self) -> list[str]:
        jobs = os.environ.get("RTORRENT_JOBS") or str(self._jobs)
        return ["-j", jobs]

    def _log_header(self, f, cmd_str: str) -> None:
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        f.write("=" * 70 + "\n")
        f.write(f"TIME: {ts}\n")
        f.write(f"CMD:  {cmd_str}\n")
        f.write("-" * 70 + "\n")

    @staticmethod
    def _log_footer(f, exit_code: int) -> None:
        f.write("\n" + "-" * 70 + "\n")
        f.write(f"EXIT: {exit_code}\n")
        f.write("=" * 70 + "\n\n")

    def run(
        self,
        args: Sequence[str | Path],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        desc: str = "",
    ) -> None:
        cmd_str = shlex.join(str(a) for a in args)
        if desc:
            print(f"$ {cmd_str}  # {desc}")
        else:
            print(f"$ {cmd_str}")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            self._log_header(f, cmd_str)

            proc = subprocess.Popen(
                [str(a) for a in args],
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            assert proc.stdout is not None
            chunks: list[bytes] = []
            for chunk in proc.stdout:
                chunks.append(chunk)
                f.write(chunk.decode())

            proc.stdout.close()
            proc.wait()

            self._log_footer(f, proc.returncode)

        output = b"".join(chunks)
        if proc.returncode != 0:
            raise CmdError(
                proc.returncode,
                list(args),
                output=output.decode(errors="replace"),
                stderr=None,
            )
