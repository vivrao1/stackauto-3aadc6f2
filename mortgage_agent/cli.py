"""Command-line interface for the Australian mortgage eligibility agent."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from mortgage_agent.agent import MortgageEligibilityAgent
from mortgage_agent.eligibility import APRA_SERVICEABILITY_BUFFER_PERCENT
from mortgage_agent.models import AU_STATES, Applicant
from mortgage_agent.rates import get_rate_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mortgage-agent",
        description="Fetch the RBA cash rate and estimate Australian first home buyer loan eligibility.",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Skip the live RBA fetch and use bundled fallback data."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rates", help="Show the RBA cash rate and derived indicative home loan rates.")

    elig = subparsers.add_parser(
        "eligibility", help="Estimate Home Guarantee Scheme eligibility for an applicant."
    )
    elig.add_argument(
        "--income", type=float, required=True, help="Gross annual household income (combined, if a couple)."
    )
    elig.add_argument(
        "--monthly-living-expenses", type=float, required=True, help="Estimated monthly living expenses."
    )
    elig.add_argument(
        "--monthly-other-debts", type=float, required=True,
        help="Other monthly debt repayments (credit cards, car loans, etc).",
    )
    elig.add_argument("--deposit", type=float, required=True, help="Cash deposit available.")
    elig.add_argument("--home-price", type=float, required=True, help="Target property price.")
    elig.add_argument(
        "--state", required=True, choices=sorted(AU_STATES), help="Property state/territory."
    )
    elig.add_argument("--couple", action="store_true", help="Applying as a couple (raises the FHBG income cap).")
    elig.add_argument(
        "--single-parent", action="store_true",
        help="Applicant is a single parent/legal guardian (Family Home Guarantee).",
    )
    elig.add_argument("--regional", action="store_true", help="Property is in a regional area.")
    elig.add_argument(
        "--not-first-home-buyer", action="store_true", help="Applicant has owned property in Australia before."
    )
    elig.add_argument("--investment", action="store_true", help="Property will not be owner-occupied.")
    elig.add_argument(
        "--not-citizen-or-pr", action="store_true", help="Applicant is not an Australian citizen or permanent resident."
    )
    elig.add_argument(
        "--new-home", action="store_true", help="Property is a new or substantially renovated home (for the FHOG estimate)."
    )
    elig.add_argument("--dependents", type=int, default=0)

    return parser


def _print_rates(offline: bool, as_json: bool) -> None:
    snapshot = get_rate_snapshot(offline=offline)
    data = {
        "as_of": snapshot.as_of.isoformat(),
        "source": snapshot.source,
        "is_live": snapshot.is_live,
        "cash_rate_target_percent": snapshot.cash_rate_percent,
        "indicative_variable_rate_percent": snapshot.variable_rate_percent,
        "indicative_3yr_fixed_rate_percent": snapshot.fixed_3yr_rate_percent,
    }
    if as_json:
        print(json.dumps(data, indent=2))
        return

    print(f"RBA cash rate as of {data['as_of']} (source: {data['source']}, live={data['is_live']})")
    print(f"  Cash rate target: {data['cash_rate_target_percent']:.2f}%")
    print(f"  Indicative owner-occupier variable rate: {data['indicative_variable_rate_percent']:.2f}%")
    print(f"  Indicative owner-occupier 3-yr fixed rate: {data['indicative_3yr_fixed_rate_percent']:.2f}%")


def _print_eligibility(args: argparse.Namespace) -> None:
    applicant = Applicant(
        annual_income=args.income,
        monthly_living_expenses=args.monthly_living_expenses,
        monthly_other_debts=args.monthly_other_debts,
        deposit=args.deposit,
        home_price=args.home_price,
        state=args.state,
        is_couple=args.couple,
        is_single_parent=args.single_parent,
        is_regional=args.regional,
        is_first_home_buyer=not args.not_first_home_buyer,
        is_owner_occupier=not args.investment,
        is_australian_citizen_or_pr=not args.not_citizen_or_pr,
        is_new_home=args.new_home,
        dependents=args.dependents,
    )
    report = MortgageEligibilityAgent().evaluate(applicant, offline=args.offline)

    if args.json:
        payload = {
            "rate_as_of": report.rate_as_of.isoformat(),
            "rate_source": report.rate_source,
            "cash_rate_percent": report.cash_rate_percent,
            "variable_rate_percent": report.variable_rate_percent,
            "fixed_3yr_rate_percent": report.fixed_3yr_rate_percent,
            "results": [{**asdict(r), "scheme": r.scheme.value} for r in report.results],
            "best_scheme": report.best_scheme.scheme.value if report.best_scheme else None,
            "estimated_fhog": asdict(report.estimated_fhog) if report.estimated_fhog else None,
        }
        print(json.dumps(payload, indent=2))
        return

    print(f"RBA cash rate as of {report.rate_as_of} (source: {report.rate_source})")
    print(f"Indicative owner-occupier variable rate: {report.variable_rate_percent:.2f}%\n")

    for result in report.results:
        status = "ELIGIBLE" if result.eligible else "NOT ELIGIBLE"
        print(f"[{status}] {result.scheme.value}")
        print(f"  Rate: {result.interest_rate_percent:.2f}%  LVR: {result.lvr_percent:.1f}%")
        if result.requires_lmi:
            print(f"  Requires LMI: estimated premium ${result.estimated_lmi_premium:,.2f}")
        print(f"  Monthly repayment (P&I): ${result.monthly_repayment:,.2f}")
        print(
            f"  Assessed at +{APRA_SERVICEABILITY_BUFFER_PERCENT:.1f}pp APRA buffer "
            f"(${result.assessed_monthly_repayment:,.2f}/mo): surplus ${result.monthly_surplus_at_assessed_rate:,.2f}/mo"
        )
        if result.loan_to_income_ratio is not None:
            print(f"  Loan-to-income ratio: {result.loan_to_income_ratio:.1f}x")
        if result.max_affordable_home_price is not None:
            print(f"  Max affordable property price under this scheme: ${result.max_affordable_home_price:,.2f}")
        for reason in result.reasons:
            print(f"  - {reason}")
        print()

    if report.best_scheme:
        print(f"Recommended scheme: {report.best_scheme.scheme.value}")
    else:
        print("No scheme is currently eligible based on the inputs provided.")

    if report.estimated_fhog:
        grant = report.estimated_fhog
        status = "eligible" if grant.eligible else "not eligible"
        print(f"\nEstimated First Home Owner Grant ({grant.state}): ${grant.amount:,.0f} ({status})")
        for note in grant.notes:
            print(f"  - {note}")


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
