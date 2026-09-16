"""Checks that modules add to a sale.

Core cannot import a module — the layering forbids it, and rightly, since a hospital pharmacy and
a dental clinic sell under different rules. So core offers a place to register a check and calls
it; the pharmacy module registers the drug-schedule rules, and core never learns what a drug
schedule is.

A validator raises to refuse the sale. Returning normally allows it.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SalesInvoice

#: Run before an invoice is issued, once the whole bill is known. Deliberately not at line-entry
#: time: a counter scans the items first and captures the prescription afterwards, so a check at
#: line entry would refuse a sale that is about to become perfectly legal.
IssueValidator = Callable[["SalesInvoice"], None]

_issue_validators: list[IssueValidator] = []


def register_issue_validator(validator: IssueValidator) -> IssueValidator:
    if validator not in _issue_validators:
        _issue_validators.append(validator)
    return validator


def unregister_issue_validator(validator: IssueValidator) -> None:
    if validator in _issue_validators:
        _issue_validators.remove(validator)


def run_issue_validators(invoice: "SalesInvoice") -> None:
    for validator in _issue_validators:
        validator(invoice)


def registered_issue_validators() -> tuple[IssueValidator, ...]:
    return tuple(_issue_validators)
