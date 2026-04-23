from __future__ import annotations

import io
import logging
import os
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is declared for runtime
    psutil = None

try:
    from winpty import PtyProcess
except ImportError:  # pragma: no cover - non-Windows dev fallback
    PtyProcess = None


LOGGER = logging.getLogger(__name__)


class TerminalBuffer:
    def __init__(self, max_bytes: int = 1_048_576) -> None:
        self.max_bytes = max_bytes
        self._chunks: deque[tuple[int, str, int]] = deque()
        self._size = 0
        self._seq = 0
        self._lock = threading.RLock()

    def append(self, text: str) -> int:
        encoded_size = len(text.encode("utf-8", errors="replace"))
        with self._lock:
            self._seq += 1
            self._chunks.append((self._seq, text, encoded_size))
            self._size += encoded_size
            while self._chunks and self._size > self.max_bytes:
                _, _, chunk_size = self._chunks.popleft()
                self._size -= chunk_size
            return self._seq

    def snapshot(self) -> tuple[int, str]:
        with self._lock:
            return self._seq, "".join(chunk[1] for chunk in self._chunks)

    def chunks_since(self, sequence: int) -> list[tuple[int, str]]:
        with self._lock:
            return [(seq, text) for seq, text, _ in self._chunks if seq > sequence]


class ManagedTerminalProcess:
    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        log_file: Path,
        buffer_bytes: int,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.log_file = log_file
        self.buffer = TerminalBuffer(max_bytes=buffer_bytes)
        preferred_backend = env.get("PYSM_CONSOLE_BACKEND", "pipes").lower()
        self.backend = (
            "conpty"
            if preferred_backend == "conpty" and os.name == "nt" and PtyProcess is not None
            else "pipes"
        )
        self.pid: int | None = None
        self.exit_code: int | None = None
        self._process: object | None = None
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._stopped = threading.Event()

    def start(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if self.backend == "conpty":
            self._process = self._spawn_conpty()
        else:
            self._process = self._spawn_pipe_process()
        self.pid = getattr(self._process, "pid", None)
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _spawn_conpty(self) -> object:
        commandline = subprocess.list2cmdline(self.command)
        LOGGER.info("Starting ConPTY process: %s", commandline)
        try:
            proc = PtyProcess.spawn(commandline, cwd=str(self.cwd), env=self.env)
        except TypeError:
            proc = PtyProcess.spawn(commandline)
        if hasattr(proc, "fileobj"):
            proc.fileobj.settimeout(0.2)
        return proc

    def _spawn_pipe_process(self) -> subprocess.Popen[bytes]:
        LOGGER.info("Starting pipe-backed process: %s", self.command)
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            self.command,
            cwd=str(self.cwd),
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def _read_loop(self) -> None:
        with self.log_file.open("a", encoding="utf-8", errors="replace") as log_handle:
            while not self._stopped.is_set():
                chunk = self._read_once()
                if chunk is None:
                    if not self.is_alive():
                        break
                    time.sleep(0.05)
                    continue
                if not chunk:
                    if not self.is_alive():
                        break
                    continue
                text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace")
                self.buffer.append(text)
                log_handle.write(text)
                log_handle.flush()
        self.exit_code = self.poll()

    def _read_once(self) -> bytes | str | None:
        process = self._process
        if process is None:
            return None
        try:
            if self.backend == "conpty":
                return process.fileobj.recv(200)
            stdout = process.stdout
            if stdout is None:
                return None
            if isinstance(stdout, io.BufferedReader):
                return stdout.read1(4096)
            return stdout.read(4096)
        except socket.timeout:
            return None
        except EOFError:
            return b""
        except OSError:
            return b""

    def write(self, data: str) -> None:
        with self._lock:
            process = self._process
            if process is None:
                raise RuntimeError("process is not running")
            if self.backend == "conpty":
                process.write(data)
                return
            stdin = process.stdin
            if stdin is None:
                raise RuntimeError("stdin is not available")
            stdin.write(data.encode("utf-8"))
            stdin.flush()

    def terminate(self) -> None:
        with self._lock:
            self._stopped.set()
            if self.pid and psutil is not None:
                try:
                    proc = psutil.Process(self.pid)
                    proc.terminate()
                    proc.wait(timeout=5)
                    self.exit_code = 0
                except Exception:  # pragma: no cover - best-effort cleanup
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                            capture_output=True,
                            check=False,
                            text=True,
                        )
                    except OSError:
                        pass
                return
            if isinstance(self._process, subprocess.Popen):
                self._process.terminate()

    def suspend(self) -> None:
        if not self.pid or psutil is None:
            raise RuntimeError("Suspend requires psutil and a live PID")
        psutil.Process(self.pid).suspend()

    def resume(self) -> None:
        if not self.pid or psutil is None:
            raise RuntimeError("Resume requires psutil and a live PID")
        psutil.Process(self.pid).resume()

    def is_alive(self) -> bool:
        if self.pid and psutil is not None:
            try:
                proc = psutil.Process(self.pid)
                return proc.is_running() and proc.status() != getattr(psutil, "STATUS_ZOMBIE", "zombie")
            except psutil.Error:
                return False
        return self.poll() is None

    def poll(self) -> int | None:
        process = self._process
        if process is None:
            return self.exit_code
        if isinstance(process, subprocess.Popen):
            return process.poll()
        if hasattr(process, "isalive") and process.isalive():
            return None
        return getattr(process, "exitstatus", self.exit_code)


def process_metrics(pid: int | None) -> dict[str, float | int | None]:
    if not pid or psutil is None:
        return {"cpu_percent": None, "memory_percent": None}
    try:
        proc = psutil.Process(pid)
        return {
            "cpu_percent": proc.cpu_percent(interval=0.0),
            "memory_percent": proc.memory_percent(),
        }
    except psutil.Error:
        return {"cpu_percent": None, "memory_percent": None}
