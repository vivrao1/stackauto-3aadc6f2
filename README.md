# Mortgage Eligibility Agent (Australia)

Fetches the RBA cash rate and estimates a first home buyer's eligibility
across a standard home loan and the Australian Government's **Home
Guarantee Scheme**: First Home Guarantee, Regional First Home Buyer
Guarantee, and Family Home Guarantee. It also gives an indicative state
**First Home Owner Grant (FHOG)** estimate.

There's no single published "first home buyer rate" in Australia —
lenders price off the cash rate with their own margins, and the Home
Guarantee Scheme changes *which costs apply* (it waives Lenders Mortgage
Insurance) rather than the rate itself. This agent scrapes the [RBA's
published cash rate target](https://www.rba.gov.au/statistics/cash-rate/)
and applies standard industry lender margins to approximate current
owner-occupier rates. If the live source is unreachable (no network
access, or the page layout changed), it automatically falls back to a
bundled static snapshot and clearly reports which source was used — it
never silently breaks the eligibility calculation.

**Scheme thresholds (income caps, property price caps, max LVR) are
reviewed periodically by government and change.** `POLICY_SNAPSHOT_DATE`
in `mortgage_agent/eligibility.py` records when these figures were last
checked — verify current settings at
[housingaustralia.gov.au](https://www.housingaustralia.gov.au/) and with
the relevant state revenue office before relying on this for a real
purchase.

## Install

```bash
pip install -r requirements.txt
```

## Usage

Show the RBA cash rate and derived indicative home loan rates:

```bash
python -m mortgage_agent rates
python -m mortgage_agent --offline rates   # skip the live fetch
python -m mortgage_agent --json rates      # machine-readable output
```

Estimate eligibility for an applicant:

```bash
python -m mortgage_agent eligibility \
  --income 140000 --couple \
  --monthly-living-expenses 2200 \
  --monthly-other-debts 300 \
  --deposit 60000 \
  --home-price 700000 \
  --state NSW \
  --new-home
```

Other flags: `--single-parent` (Family Home Guarantee), `--regional`
(Regional First Home Buyer Guarantee + regional price caps/grant rules),
`--not-first-home-buyer`, `--investment` (not owner-occupied),
`--not-citizen-or-pr`, `--dependents`, `--offline`, `--json`.

## Programmatic use

```python
from mortgage_agent import Applicant, MortgageEligibilityAgent

applicant = Applicant(
    annual_income=140_000,
    monthly_living_expenses=2_200,
    monthly_other_debts=300,
    deposit=60_000,
    home_price=700_000,
    state="NSW",
    is_couple=True,
)
report = MortgageEligibilityAgent().evaluate(applicant)
for result in report.results:
    print(result.scheme, result.eligible, result.monthly_repayment)
```

## Design notes

- `mortgage_agent/rates.py` — `RBACashRateSource` scrapes the live RBA
  page; `StaticFallbackSource` is the offline fallback.
  `get_rate_snapshot()` tries live first and falls back automatically on
  any network or parse error, so callers never have to special-case
  connectivity.
- `mortgage_agent/tax.py` — a simplified Australian resident income tax +
  Medicare levy estimate, used to approximate take-home pay for
  serviceability (ignores HECS, offsets, and the Medicare levy low-income
  reduction — see its docstring).
- `mortgage_agent/eligibility.py` — scheme rules (LVR limits, income caps,
  indicative property price caps) plus APRA-buffer serviceability
  (current rate + 3 percentage points) and standard loan amortization
  math. This is a simplification of the HEM-based calculators lenders
  actually use.
- `mortgage_agent/grants.py` — indicative, state-by-state First Home
  Owner Grant estimate. Separate from the Commonwealth guarantee schemes;
  each state sets its own amount, price cap, and new-vs-established rules.
- `mortgage_agent/agent.py` — `MortgageEligibilityAgent` ties rate
  fetching, scheme scoring, and the grant estimate together into one
  report, and recommends the eligible scheme with the lowest effective
  cost (preferring an LMI waiver, then lowest premium, then lowest
  repayment).
- `mortgage_agent/cli.py` — CLI wrapper (`python -m mortgage_agent`).

## Tests

```bash
python -m pytest tests/ -q
```

Rate-source tests mock HTTP responses, so they run without network access
and don't depend on the live page's current layout.
