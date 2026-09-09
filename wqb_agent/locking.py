"""Process-lifetime owner lock shared by production and maintenance tools."""

import hashlib
import json
import os
import socket
import time

from .artifacts import atomic_write_json_if_changed

_LOCK_HANDLES = {}


def acquire_single_instance_lock(state_dir, operation="run-proposals"):
    """Acquire the OS owner lock and write human-readable metadata."""
    os.makedirs(state_dir, exist_ok=True)
    lock_path = os.path.join(state_dir, "run.lock")
    handle = _acquire_os_lock(lock_path)
    if handle is None:
        old_pid, started = "?", "?"
        try:
            with open(lock_path, encoding="utf-8-sig") as handle_file:
                data = json.load(handle_file)
            old_pid = data.get("pid", "?")
            started = data.get("started_at", "?")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        print(
            f"[LOCK] 已有研究实例 PID={old_pid} 在运行（启动于 {started}）。\n"
            "       单实例纪律：请等待其完成，不要并行启动第二个实例。"
        )
        return None
    _LOCK_HANDLES[lock_path] = handle
    try:
        atomic_write_json_if_changed(lock_path, {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "operation": operation,
        })
    except Exception:
        _release_os_lock(_LOCK_HANDLES.pop(lock_path))
        raise
    return lock_path


def _acquire_os_lock(lock_path):
    """Acquire a process-lifetime OS lock; stale metadata is not ownership."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        digest = hashlib.sha256(
            os.path.abspath(lock_path).lower().encode("utf-8")
        ).hexdigest()
        handle = create_mutex(None, True, f"Local\\WQBAlpha_{digest}")
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return ("win", handle)
    import fcntl

    guard_path = lock_path + ".guard"
    fd = os.open(guard_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return ("posix", fd)


def _release_os_lock(handle):
    kind, value = handle
    if kind == "win":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex(value)
        kernel32.CloseHandle(value)
        return
    import fcntl

    fcntl.flock(value, fcntl.LOCK_UN)
    os.close(value)


def acquire_os_owner_lock(lock_path):
    """Acquire only the OS owner primitive for maintenance tools.

    Unlike ``acquire_single_instance_lock`` this does not rewrite the
    human-readable ``run.lock`` metadata.  It is the narrow public boundary
    for scripts that must coordinate with the production owner.
    """
    return _acquire_os_lock(lock_path)


def release_os_owner_lock(handle):
    """Release a handle returned by :func:`acquire_os_owner_lock`."""
    if handle is not None:
        _release_os_lock(handle)


def release_single_instance_lock(lock_path):
    if not lock_path:
        return
    try:
        with open(lock_path, encoding="utf-8") as handle_file:
            data = json.load(handle_file)
        if int(data.get("pid") or 0) == os.getpid():
            os.remove(lock_path)
    except Exception:
        pass
    handle = _LOCK_HANDLES.pop(lock_path, None)
    if handle is not None:
        _release_os_lock(handle)
