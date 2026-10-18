"""Where the generator may write: inside the project, never across a link.

Every file the generator writes or deletes goes through :func:`safe_target` first. A path is
refused when any part of it that already exists is a symlink or, on Windows, a reparse point
(junctions included), or when it resolves outside the project root.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional


def is_link(path: Path) -> bool:
    """A symlink, or on Windows any reparse point (junctions included). Unreadable → True."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def inside(root: Path, path: Path) -> bool:
    """``path`` resolves to ``root`` or below it (``root`` already resolved)."""
    try:
        path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def safe_target(root: Path, rel: str) -> Optional[Path]:
    """``root / rel`` if ``rel`` is a plain relative path, no existing part of it is a link,
    and it resolves inside ``root``; otherwise ``None``. Parts that do not exist yet are
    allowed — the path may be about to be written. ``root`` must be resolved."""
    if not rel or PureWindowsPath(rel).drive or PureWindowsPath(rel).is_absolute():
        return None
    parts = PurePosixPath(rel.replace("\\", "/")).parts
    if not parts or parts[0] in ("/", "") or ".." in parts:
        return None
    current = root
    for part in parts:
        current = current / part
        if not os.path.lexists(current):
            break
        if is_link(current):
            return None
    target = root.joinpath(*parts)
    if not inside(root, target):
        return None
    return target
