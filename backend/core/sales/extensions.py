"""Where a module joins in when a bill is issued.

Core cannot import a module — the layering forbids it, and rightly, since a hospital pharmacy and
a dental clinic sell under different rules. So core offers places to register a callback and calls
them; the pharmacy module registers the drug-schedule rules and the narcotic register, and core
never learns what a drug schedule is.

Three points, deliberately distinct:

* a **validator** runs before anything is committed and raises to refuse the sale;
* an **issued hook** runs after the sale is final, inside the same transaction, for the records
  that must exist because the sale happened;
* a **cancelled hook** runs when an issued invoice is cancelled.

The hooks run inside the caller's transaction on purpose. A narcotic that left the shelf without
its register entry is the failure the register exists to prevent, so if the entry cannot be
written the sale must not stand either.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import SalesInvoice

#: Run before an invoice is issued, once the whole bill is known. Deliberately not at line-entry
#: time: a counter scans the items first and captures the prescription afterwards, so a check at
#: line entry would refuse a sale that is about to become perfectly legal.
IssueValidator = Callable[["SalesInvoice"], None]

#: Run after the number is taken and the stock has moved. Receives the invoice and everything the
#: sale produced, so a hook does not have to re-read the ledger to find out which batch went out.
IssuedHook = Callable[..., None]

#: Run when an issued invoice is cancelled, after the stock has been put back.
CancelledHook = Callable[..., None]

_issue_validators: list[IssueValidator] = []
_issued_hooks: list[IssuedHook] = []
_cancelled_hooks: list[CancelledHook] = []


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


def register_issued_hook(hook: IssuedHook) -> IssuedHook:
    if hook not in _issued_hooks:
        _issued_hooks.append(hook)
    return hook


def unregister_issued_hook(hook: IssuedHook) -> None:
    if hook in _issued_hooks:
        _issued_hooks.remove(hook)


def run_issued_hooks(invoice: "SalesInvoice", *, entries: list[Any], actor: Any = None) -> None:
    for hook in _issued_hooks:
        hook(invoice, entries=entries, actor=actor)


def register_cancelled_hook(hook: CancelledHook) -> CancelledHook:
    if hook not in _cancelled_hooks:
        _cancelled_hooks.append(hook)
    return hook


def unregister_cancelled_hook(hook: CancelledHook) -> None:
    if hook in _cancelled_hooks:
        _cancelled_hooks.remove(hook)


def run_cancelled_hooks(
    invoice: "SalesInvoice", *, reason: str, actor: Any = None, entries: list[Any] | None = None
) -> None:
    for hook in _cancelled_hooks:
        hook(invoice, reason=reason, actor=actor, entries=entries or [])
