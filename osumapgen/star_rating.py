"""Star-rating estimation with rosu-pp (a Rust port of osu!'s official
difficulty calculator, kept in sync with the game's algorithm)."""

from __future__ import annotations

from dataclasses import dataclass

from .infra import UserFacingError


@dataclass
class StarResult:
    stars: float            # lazer algorithm (primary)
    stars_stable: float     # osu!stable slider handling
    aim: float
    speed: float
    max_combo: int
    n_objects: int
    calculator: str


def _rosu():
    try:
        import rosu_pp_py
        return rosu_pp_py
    except Exception as e:
        raise UserFacingError("The difficulty calculator (rosu-pp-py) is not installed. "
                              'Double-click "Setup or Repair.bat" to fix this.') from e


def calculator_version() -> str:
    try:
        from importlib.metadata import version
        return f"rosu-pp-py {version('rosu-pp-py')}"
    except Exception:
        return "rosu-pp-py"


def calculate(osu_text: str) -> StarResult:
    r = _rosu()
    try:
        bm = r.Beatmap(content=osu_text)
    except Exception as e:
        raise ValueError(f"Difficulty calculator could not parse the map: {e}") from e
    d = r.Difficulty()
    d.set_lazer(True)
    a = d.calculate(bm)
    s = r.Difficulty()
    s.set_lazer(False)
    b = s.calculate(bm)
    return StarResult(stars=float(a.stars), stars_stable=float(b.stars), aim=float(a.aim or 0.0),
                      speed=float(a.speed or 0.0), max_combo=int(a.max_combo or 0),
                      n_objects=int((a.n_circles or 0) + (a.n_sliders or 0) + (a.n_spinners or 0)),
                      calculator=calculator_version())
