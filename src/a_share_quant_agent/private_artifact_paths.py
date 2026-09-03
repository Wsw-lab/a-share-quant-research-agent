"""Fail-closed location and publication helpers for private research artifacts."""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


class PrivateArtifactPathError(RuntimeError):
    """Raised when a private artifact target is unsafe or cannot be published."""


def entry_exists(path: Path) -> bool:
    """Return true for ordinary entries, symlinks, and broken symlinks."""

    return os.path.lexists(os.fspath(path))


def resolve_artifact_path(value: str | Path | None, *, label: str) -> Path:
    if value is None:
        raise PrivateArtifactPathError(f"{label} is required")
    try:
        return Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PrivateArtifactPathError(f"{label} is invalid") from exc


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path if path.is_dir() else path.parent
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise PrivateArtifactPathError(
                "nearest existing parent for private artifact could not be resolved"
            )
        candidate = parent
    if not candidate.is_dir():
        raise PrivateArtifactPathError(
            "nearest existing parent for private artifact is not a directory"
        )
    return candidate.resolve(strict=True)


def containing_git_worktree(path: str | Path) -> Path | None:
    """Return the containing worktree, including independent/linked checkouts.

    Discovery starts at the nearest existing parent so it also covers a fresh
    nested output path.  Walking upward handles a target under a worktree's
    ``.git`` administration directory, where a direct ``rev-parse`` reports a
    Git directory rather than a working tree.  ``--git-common-dir`` is queried
    with the top-level path so linked worktrees and separate repositories use
    the same verifiable detection route.
    """

    resolved = resolve_artifact_path(path, label="private artifact path")
    anchor = _nearest_existing_directory(resolved)
    for candidate in (anchor, *anchor.parents):
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(candidate),
                    "rev-parse",
                    "--is-inside-work-tree",
                    "--show-toplevel",
                    "--git-common-dir",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise PrivateArtifactPathError(
                "Git worktree location could not be verified"
            ) from exc
        if result.returncode != 0:
            continue
        lines = result.stdout.splitlines()
        if len(lines) != 3 or lines[0].strip() not in {"true", "false"}:
            raise PrivateArtifactPathError(
                "Git worktree location response is invalid"
            )
        if lines[0].strip() == "false":
            continue
        try:
            worktree = Path(lines[1]).expanduser().resolve(strict=True)
            common_dir_entry = Path(lines[2]).expanduser()
            common_dir = (
                common_dir_entry
                if common_dir_entry.is_absolute()
                else candidate / common_dir_entry
            ).resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise PrivateArtifactPathError(
                "Git worktree identity could not be resolved"
            ) from exc
        if not worktree.is_dir() or not common_dir.is_dir():
            raise PrivateArtifactPathError(
                "Git worktree identity is invalid"
            )
        try:
            resolved.relative_to(worktree)
        except ValueError:
            raise PrivateArtifactPathError(
                "Git reported a worktree that does not contain the private artifact"
            )
        return worktree
    return None


def require_outside_any_git_worktree(
    value: str | Path | None, *, label: str
) -> Path:
    resolved = resolve_artifact_path(value, label=label)
    if containing_git_worktree(resolved) is not None:
        raise PrivateArtifactPathError(
            f"{label} must be outside every Git worktree"
        )
    return resolved


def require_new_private_file_target(
    value: str | Path | None, *, label: str
) -> Path:
    destination = require_outside_any_git_worktree(value, label=label)
    if entry_exists(destination):
        raise PrivateArtifactPathError(f"{label} already exists")
    return destination


def write_private_bytes_atomic_exclusive(
    value: str | Path,
    payload: bytes,
    *,
    label: str,
) -> Path:
    """Atomically publish complete bytes with mode 0600 and no replacement."""

    if not isinstance(payload, bytes):
        raise PrivateArtifactPathError(f"{label} payload must be bytes")
    destination = require_new_private_file_target(value, label=label)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PrivateArtifactPathError(
            f"{label} parent directory could not be created"
        ) from exc
    # Re-resolve after parent creation and immediately before staging.  This
    # catches a newly introduced repository or changed symlink parent.
    destination = require_new_private_file_target(destination, label=label)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if stat.S_IMODE(temporary_path.stat().st_mode) != 0o600:
            raise PrivateArtifactPathError(
                f"{label} staging permissions are not 0600"
            )
        destination = require_new_private_file_target(destination, label=label)
        try:
            os.link(temporary_path, destination, follow_symlinks=False)
        except FileExistsError as exc:
            raise PrivateArtifactPathError(f"{label} already exists") from exc
        if stat.S_IMODE(destination.stat().st_mode) != 0o600:
            raise PrivateArtifactPathError(f"{label} permissions are not 0600")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(destination.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except PrivateArtifactPathError:
        raise
    except OSError as exc:
        raise PrivateArtifactPathError(
            f"{label} could not be atomically created"
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        # If publication succeeded but a later durability check failed, keep
        # the complete destination.  Never remove a possibly authoritative
        # record in a way that would make the same path silently reusable.
    return destination


def publish_private_directory_atomic_exclusive(
    staging: str | Path,
    destination: str | Path,
    *,
    label: str,
) -> Path:
    """Atomically publish one complete directory without replacing any entry.

    Plain POSIX ``rename`` is unsafe for this purpose: it may silently replace
    an empty destination directory that appears after a caller's existence
    check.  Stage-2 runs therefore use the operating system's exclusive rename
    primitive and fail closed on platforms that do not expose one.
    """

    source = Path(staging)
    target = Path(destination)
    if not source.is_absolute() or not target.is_absolute():
        raise PrivateArtifactPathError(f"{label} paths must be absolute")
    if not source.is_dir() or source.is_symlink():
        raise PrivateArtifactPathError(f"{label} staging directory is invalid")
    if source.parent != target.parent:
        raise PrivateArtifactPathError(
            f"{label} staging and destination must share one parent"
        )

    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    result: int
    if sys.platform == "darwin":
        library = ctypes.CDLL(None, use_errno=True)
        try:
            rename_exclusive = library.renamex_np
        except AttributeError as exc:
            raise PrivateArtifactPathError(
                f"{label} exclusive directory publication is unavailable"
            ) from exc
        rename_exclusive.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        # Darwin's RENAME_EXCL makes the rename fail with EEXIST rather than
        # replacing an entry that won the race for the destination name.
        result = rename_exclusive(source_bytes, target_bytes, 0x00000004)
    elif sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        try:
            rename_exclusive = library.renameat2
        except AttributeError as exc:
            raise PrivateArtifactPathError(
                f"{label} exclusive directory publication is unavailable"
            ) from exc
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        # Linux RENAME_NOREPLACE has the same destination-exclusion contract.
        result = rename_exclusive(-100, source_bytes, -100, target_bytes, 1)
    elif os.name == "nt":
        # Python's Windows rename uses MoveFile semantics and does not replace
        # an existing destination.  Keep this branch explicit rather than
        # falling back to replacement-capable POSIX rename elsewhere.
        try:
            os.rename(source, target)
        except FileExistsError as exc:
            raise PrivateArtifactPathError(f"{label} already exists") from exc
        except OSError as exc:
            raise PrivateArtifactPathError(
                f"{label} could not be atomically published"
            ) from exc
        result = 0
    else:
        raise PrivateArtifactPathError(
            f"{label} exclusive directory publication is unavailable"
        )

    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise PrivateArtifactPathError(f"{label} already exists")
        raise PrivateArtifactPathError(
            f"{label} could not be atomically published"
        ) from OSError(error_number, os.strerror(error_number))

    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(target.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        # Publication has already happened.  Never remove or replace the
        # authoritative directory merely because the durability check failed.
        raise PrivateArtifactPathError(
            f"{label} was published but its parent could not be synchronized"
        ) from exc
    return target


__all__ = [
    "PrivateArtifactPathError",
    "containing_git_worktree",
    "entry_exists",
    "publish_private_directory_atomic_exclusive",
    "require_new_private_file_target",
    "require_outside_any_git_worktree",
    "resolve_artifact_path",
    "write_private_bytes_atomic_exclusive",
]
