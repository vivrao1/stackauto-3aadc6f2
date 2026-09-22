"""Command-line interface for the mortgage eligibility agent."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from mortgage_agent.agent import MortgageEligibilityAgent
from mortgage_agent.models import Applicant
from mortgage_agent.rates import get_rate_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mortgage-agent",
        description="Scrape current mortgage rates and estimate first-time home buyer eligibility.",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Skip the live rate fetch and use bundled fallback data."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rates", help="Show the current benchmark rate and derived per-program rates.")

    elig = subparsers.add_parser("eligibility", help="Estimate loan-program eligibility for an applicant.")
    elig.add_argument("--income", type=float, required=True, help="Gross annual household income.")
    elig.add_argument("--monthly-debts", type=float, required=True, help="Existing monthly debt payments.")
    elig.add_argument("--credit-score", type=int, required=True, help="FICO credit score.")
    elig.add_argument("--down-payment", type=float, required=True, help="Cash available for down payment.")
    elig.add_argument("--home-price", type=float, required=True, help="Target home purchase price.")
    elig.add_argument("--veteran", action="store_true", help="Applicant is VA-loan eligible.")
    elig.add_argument("--rural", action="store_true", help="Property is in a USDA-eligible rural area.")
    elig.add_argument("--household-size", type=int, default=1)
    elig.add_argument(
        "--area-median-income", type=float, default=None, help="Local area median income, for USDA's 115% test."
    )

    return parser


def _print_rates(offline: bool, as_json: bool) -> None:
    snapshot = get_rate_snapshot(offline=offline)
    programs = ["conventional_97", "fha", "va", "usda"]
    data = {
        "as_of": snapshot.as_of.isoformat(),
        "source": snapshot.source,
        "is_live": snapshot.is_live,
        "benchmark_30yr_conventional_percent": snapshot.rate_30yr_percent,
        "program_rates_percent": {p: snapshot.program_rate(p) for p in programs},
    }
    if as_json:
        print(json.dumps(data, indent=2))
        return

    print(f"Rates as of {data['as_of']} (source: {data['source']}, live={data['is_live']})")
    print(f"  30-yr conventional benchmark: {data['benchmark_30yr_conventional_percent']:.3f}%")
    for program, rate in data["program_rates_percent"].items():
        print(f"  {program:<18} {rate:.3f}%")


def _print_eligibility(args: argparse.Namespace) -> None:
    applicant = Applicant(
        annual_income=args.income,
        monthly_debts=args.monthly_debts,
        credit_score=args.credit_score,
        down_payment=args.down_payment,
        home_price=args.home_price,
        is_veteran=args.veteran,
        is_rural_property=args.rural,
        household_size=args.household_size,
        area_median_income=args.area_median_income,
    )
    report = MortgageEligibilityAgent().evaluate(applicant, offline=args.offline)

    if args.json:
        payload = {
            "rates_as_of": report.rates_as_of.isoformat(),
            "rate_source": report.rate_source,
            "results": [
                {**asdict(r), "program": r.program.value} for r in report.results
            ],
            "best_program": report.best_program.program.value if report.best_program else None,
        }
        print(json.dumps(payload, indent=2))
        return

    print(f"Rates as of {report.rates_as_of} (source: {report.rate_source})\n")
    for result in report.results:
        status = "ELIGIBLE" if result.eligible else "NOT ELIGIBLE"
        if result.needs_verification:
            status += " (needs income verification)"
        print(f"[{status}] {result.program.value}")
        if result.interest_rate_percent is not None:
            print(f"  Estimated rate: {result.interest_rate_percent:.3f}%")
        if result.monthly_piti is not None:
            print(f"  Est. monthly payment (PITI): ${result.monthly_piti:,.2f}")
        if result.front_end_dti_percent is not None:
            print(
                f"  Housing DTI: {result.front_end_dti_percent:.1f}%  "
                f"Total DTI: {result.back_end_dti_percent:.1f}%"
            )
        if result.max_affordable_home_price is not None:
            print(f"  Max affordable home price under this program: ${result.max_affordable_home_price:,.2f}")
        for reason in result.reasons:
            print(f"  - {reason}")
        print()

    if report.best_program:
        print(f"Recommended program (lowest monthly payment among eligible): {report.best_program.program.value}")
    else:
        print("No program is currently eligible based on the inputs provided.")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "rates":
        _print_rates(args.offline, args.json)
    elif args.command == "eligibility":
        _print_eligibility(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
