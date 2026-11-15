"""ETF fees (net expense ratio) → src/dh/fees.json, for the existing-portfolio review (workshop slide 13: "frais").

    .venv/bin/python scripts/build_fees.py        # needs internet (Yahoo Finance, already used for prices)

Source: Yahoo Finance `netExpenseRatio` (in %, e.g. 0.09 = 0.09% a year), fetched on the date written in the file.
It is Yahoo's copy of the issuer's figure, not the issuer's document: check a fund's own page before quoting it in a
deliverable. Covers our ETFs and every stand-in fund (dh.standins), so XSP.TO's own fee is used, not SPY's.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dh import fees, standins  # noqa: E402
from dh.agents.rules import ETFS  # noqa: E402


def main() -> None:
    import yfinance as yf
    out = {"_source": "Yahoo Finance netExpenseRatio (copy of the issuer's figure)", "_fetched": date.today().isoformat()}
    for t in sorted(set(ETFS) | set(standins.STAND_INS)):
        try:
            v = yf.Ticker(t).info.get("netExpenseRatio")
        except Exception as e:  # noqa: BLE001
            print(f"{t}: {type(e).__name__}")
            continue
        if isinstance(v, (int, float)) and 0 <= v < 5:
            out[t] = round(v / 100, 6)
            print(f"{t:8} {v:.3f}%")
        else:
            print(f"{t:8} no figure")
    fees.FILE.write_text(json.dumps(out, indent=1) + "\n")
    print(f"written {fees.FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
