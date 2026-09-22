# Mortgage Eligibility Agent

Scrapes current mortgage rate benchmarks and estimates a first-time home
buyer's eligibility across common loan programs: **Conventional 97, FHA,
VA, and USDA**.

There is no single published "first-time buyer rate" — actual rates
depend on the program, credit score, and down payment. This agent
scrapes the national-average 30-year fixed rate from the [Freddie Mac
PMMS survey](https://www.freddiemac.com/pmms) and applies standard
industry rate adjustments per program. If the live source is unreachable
(no network access, or the page layout changed), it automatically falls
back to a bundled static snapshot and clearly reports which source was
used — it never silently breaks the eligibility calculation.

Eligibility rules (minimum credit score, minimum down payment, max
debt-to-income ratios) reflect commonly published agency guidelines.
Actual lender overlays vary — treat results as an estimate, not a loan
commitment.

## Install

```bash
pip install -r requirements.txt
```

## Usage

Show current benchmark and per-program rates:

```bash
python -m mortgage_agent rates
python -m mortgage_agent --offline rates   # skip the live fetch
python -m mortgage_agent --json rates      # machine-readable output
```

Estimate eligibility for an applicant:

```bash
python -m mortgage_agent eligibility \
  --income 95000 \
  --monthly-debts 400 \
  --credit-score 660 \
  --down-payment 12000 \
  --home-price 320000
```

Additional flags: `--veteran` (VA eligibility), `--rural` (USDA property
eligibility), `--area-median-income` (verifies USDA's 115%-of-AMI income
test), `--household-size`, `--offline`, `--json`.

## Programmatic use

```python
from mortgage_agent import Applicant, MortgageEligibilityAgent

applicant = Applicant(
    annual_income=95_000,
    monthly_debts=400,
    credit_score=660,
    down_payment=12_000,
    home_price=320_000,
)
report = MortgageEligibilityAgent().evaluate(applicant)
for result in report.results:
    print(result.program, result.eligible, result.monthly_piti)
```

## Design notes

- `mortgage_agent/rates.py` — `FreddieMacPMMSSource` scrapes the live
  page; `StaticFallbackSource` is the offline fallback. `get_rate_snapshot()`
  tries live first and falls back automatically on any network or parse
  error, so callers never have to special-case connectivity.
- `mortgage_agent/eligibility.py` — program rules (credit score, down
  payment, DTI limits) plus standard loan amortization math.
- `mortgage_agent/agent.py` — `MortgageEligibilityAgent` ties rate
  fetching and eligibility scoring together into one report.
- `mortgage_agent/cli.py` — CLI wrapper (`python -m mortgage_agent`).

## Tests

```bash
python -m pytest tests/ -q
```

Rate-source tests mock HTTP responses, so they run without network
access and don't depend on the live page's current layout.
