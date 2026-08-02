"""Copy browser assets into Vercel's public CDN directory during build."""

from __future__ import annotations

import shutil
import inspect
from pathlib import Path


def _resolve_root() -> Path:
    file_name = globals().get("__file__")
    if file_name:
        return Path(file_name).resolve().parent
    frame = inspect.currentframe()
    if frame and frame.f_back and frame.f_back.f_code.co_filename:
        return Path(frame.f_back.f_code.co_filename).resolve().parent
    return Path.cwd().resolve()


ROOT = _resolve_root()
SOURCE = ROOT / "app" / "static"
TARGET = ROOT / "public" / "static"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Static source directory does not exist: {SOURCE}")

    if TARGET.exists():
        shutil.rmtree(TARGET)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, TARGET)

    copied = sum(1 for path in TARGET.rglob("*") if path.is_file())
    print(f"Copied {copied} static asset(s) to {TARGET}")


if __name__ == "__main__":
    main()
