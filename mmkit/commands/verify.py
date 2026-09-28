"""Check every address in market.json against the chain."""

import typer

from mmkit import checks
from mmkit.common import Json, emit
from mmkit.config import load


def main(as_json: Json = False) -> None:
    """Check every address in market.json on chain. Run this first."""
    cfg = load()
    result = checks.run(cfg)
    emit([{"check": k, "ok": "ok" if v else "FAIL"} for k, v in result.items()], as_json, cfg.name)
    if failed := [k for k, v in result.items() if not v]:
        raise SystemExit(f"{len(failed)} failed: {', '.join(failed)}")


if __name__ == "__main__":
    typer.run(main)
