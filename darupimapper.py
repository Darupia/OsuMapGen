"""DarupiMapper launcher: the entry point of the packaged app (DarupiMapper.exe).

    DarupiMapper.exe                      -> graphical interface
    DarupiMapper.exe song.mp3 4.5         -> command-line generation (see --help)
    DarupiMapper.exe --check              -> dependency check
    DarupiMapper.exe --selftest out.txt   -> build check: writes the result to out.txt (used by CI)

When run from source it behaves exactly like `python -m osumapgen`.
"""

import os
import sys


def _prepare_frozen_environment() -> None:
    # A windowed exe has no console: give libraries a harmless stdout/stderr instead of None.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    # numba (used by librosa) compiles on first use. The one-file exe unpacks to a fresh temp folder on every
    # launch, so keep the compile cache somewhere that survives between runs.
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    cache = os.path.join(base, "DarupiMapper", "numba_cache")
    try:
        os.makedirs(cache, exist_ok=True)
        os.environ.setdefault("NUMBA_CACHE_DIR", cache)
    except OSError:
        pass


if getattr(sys, "frozen", False):
    _prepare_frozen_environment()

def _selftest(result_path: str) -> int:
    """Check that the packaged app can open its window and load every dependency. A windowed exe prints nothing,
    so the verdict goes to a file."""
    lines, ok = [], True
    try:
        import tkinter as tk
        root = tk.Tk()
        root.update()
        root.destroy()
        lines.append("tkinter window: ok")
    except Exception as e:
        ok = False
        lines.append(f"tkinter window: FAILED {e!r}")
    try:
        import osumapgen.gui  # noqa: F401
        lines.append("gui module: ok")
    except Exception as e:
        ok = False
        lines.append(f"gui module: FAILED {e!r}")
    try:
        from osumapgen.deps import check_dependencies
        rep = check_dependencies()
        ok = ok and rep.ok
        lines.append("dependencies: " + ("ok" if rep.ok else "MISSING " + ", ".join(rep.missing_modules)))
    except Exception as e:
        ok = False
        lines.append(f"dependencies: FAILED {e!r}")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n" + ("SELFTEST PASSED" if ok else "SELFTEST FAILED") + "\n")
    return 0 if ok else 1


from osumapgen.__main__ import main  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        sys.exit(_selftest(sys.argv[2]))
    sys.exit(main())
