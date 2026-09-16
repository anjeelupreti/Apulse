"""The controlled-drug register.

Under the Narcotic Drugs (Control) Act, 2033 a seller of narcotic drugs must keep records in a
prescribed format with the doctor's prescription attached. This is that record, written as the
stock moves rather than made up afterwards from memory, which is how paper registers come to
disagree with the cabinet.

Which drugs it covers is not hard-coded here. A `ScheduleRule` says whether a समूह needs a register
entry, and the rules are dated, so a DDA notice that brings another group into the register applies
from its own date without touching what is already written.

Everything here is append-only in the database. A mistake is corrected by a `CORRECTION` entry that
points at what it corrects and says why — the paper equivalent of a line through an entry with the
original still legible underneath.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import transaction
from django.db.models import Sum

from kernel.tenancy.context import require_current_tenant_id
from shared.errors import DomainError

from . import errors
from .models import (
    MedicineProfile,
    NarcoticRegisterBalance,
    NarcoticRegisterEntry,
    Prescription,
    RegisterEntryType,
)
from .services import rule_for

logger = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- what is controlled
def needs_register_entry(profile: MedicineProfile, *, on_date: date) -> bool:
    """Whether this medicine's समूह required a register entry on that date."""
    rule = rule_for(profile.schedule, on_date=on_date)
    return bool(rule and rule.requires_register_entry)


def controlled_profiles(item_ids: Iterable[Any], *, on_date: date) -> dict[Any, MedicineProfile]:
    """The medicines among these items that belong in the register, keyed by item id."""
    profiles = MedicineProfile.objects.filter(item_id__in=list(item_ids)).select_related("item")
    return {
        profile.item_id: profile
        for profile in profiles
        if needs_register_entry(profile, on_date=on_date)
    }


# --------------------------------------------------------------------------- writing an entry
@transaction.atomic
def record_entry(
    *,
    branch: Any,
    item: Any,
    entry_type: str,
    quantity: Decimal,
    occurred_on: date,
    batch: Any = None,
    location: Any = None,
    **details: Any,
) -> NarcoticRegisterEntry:
    """Append one line to the register and move the running balance with it.

    The balance row is locked for the duration, so two counters dispensing from the same cabinet
    at the same moment cannot both read the same balance and write the same one back.
    """
    if quantity == 0:
        raise DomainError(errors.REGISTER_ENTRY_IS_EMPTY)

    tenant_id = require_current_tenant_id()
    NarcoticRegisterBalance.all_tenants.get_or_create(
        tenant_id=tenant_id,
        branch=branch,
        item=item,
        batch=batch,
        defaults={"quantity": Decimal("0")},
    )
    balance = cast(
        "NarcoticRegisterBalance",
        NarcoticRegisterBalance.all_tenants.select_for_update().get(
            tenant_id=tenant_id, branch=branch, item=item, batch=batch
        ),
    )

    balance.quantity = balance.quantity + quantity
    balance.save(update_fields=["quantity", "updated_at"])

    entry = cast(
        "NarcoticRegisterEntry",
        NarcoticRegisterEntry.objects.create(
            branch=branch,
            location=location,
            item=item,
            batch=batch,
            entry_type=entry_type,
            quantity=quantity,
            balance_after=balance.quantity,
            occurred_on=occurred_on,
            **details,
        ),
    )
    logger.info(
        "narcotic_register_entry",
        entry_type=entry_type,
        item=item.code,
        quantity=str(quantity),
        balance=str(balance.quantity),
    )
    return entry


def _dispenser_details(actor: Any, *, on_date: date) -> dict[str, Any]:
    """Who handed it over, and under which registration.

    A registered pharmacist must dispense a controlled drug personally, so an actor holding no
    valid Pharmacy Council registration is refused. An unattributed call — no actor at all, as in
    an opening-stock import — is allowed through here and gated at the API layer instead, where
    there is always a signed-in user. Refusing it here would block the import that has to happen
    before a pharmacy can dispense anything at all.
    """
    if actor is None:
        return {}

    from kernel.identity.models import CredentialType, UserCredential

    credential = (
        UserCredential.objects.filter(user=actor, type=CredentialType.PHARMACY_COUNCIL)
        .order_by("-expires_on")
        .first()
    )
    if credential is None or not credential.is_valid_on(on_date):
        raise DomainError(
            errors.PHARMACIST_REGISTRATION_REQUIRED,
            "A controlled drug may only be handed over by a registered pharmacist.",
        )
    return {
        "dispensed_by": actor,
        "dispensed_by_name": str(actor)[:200],
        "dispensed_by_registration_number": credential.registration_number,
    }


def _patient_details(invoice: Any) -> dict[str, Any]:
    """The patient and prescriber columns, copied in as text as well as linked.

    Copied because a register page has to read a year later exactly as it read on the day. A
    practitioner record corrected in 2027 must not quietly rewrite what a 2026 page says.
    """
    prescription = (
        Prescription.objects.filter(invoice=invoice)
        .select_related("prescriber")
        .order_by("-prescribed_on")
        .first()
    )
    if prescription is None:
        return {"patient_name": invoice.customer_name}

    prescriber = prescription.prescriber
    return {
        "prescription": prescription,
        "patient_name": prescription.patient_name or invoice.customer_name,
        "patient_identity_number": prescription.patient_phone,
        "prescriber": prescriber,
        "prescriber_name": prescriber.name,
        "prescriber_registration_number": prescriber.registration_number,
        "signature_reference": prescription.attachment_reference,
    }


# --------------------------------------------------------------------------- the hooks
def record_dispensing(invoice: Any, *, entries: Sequence[Any], actor: Any = None) -> None:
    """Called by core.sales once a bill is issued.

    Driven off the stock movements rather than the invoice lines, because the movements say which
    batch actually left the cabinet — and a register naming the wrong batch cannot be reconciled
    against the shelf.
    """
    controlled = controlled_profiles(
        {entry.item_id for entry in entries}, on_date=invoice.invoice_date
    )
    if not controlled:
        return

    patient = _patient_details(invoice)
    dispenser = _dispenser_details(actor, on_date=invoice.invoice_date)

    for entry in entries:
        if entry.item_id not in controlled:
            continue
        record_entry(
            branch=entry.branch,
            location=entry.location,
            item=entry.item,
            batch=entry.batch,
            entry_type=RegisterEntryType.DISPENSED,
            quantity=entry.quantity,  # already negative: stock leaving the cabinet
            occurred_on=entry.occurred_on,
            document_type=entry.document_type,
            document_id=entry.document_id,
            document_number=entry.document_number,
            **patient,
            **dispenser,
        )


def record_sale_cancellation(
    invoice: Any,
    *,
    reason: str,
    actor: Any = None,  # noqa: ARG001 — part of the hook contract; a correction is attributed
    entries: Sequence[Any] = (),  # to the cancelled document, not to whoever pressed the button
) -> None:
    """A cancelled bill puts the stock back, so the register has to say so too."""
    _record_reversals(
        entries,
        on_date=invoice.invoice_date,
        reason=reason or f"Invoice {invoice.number} cancelled",
    )


def record_receipt_cancellation(
    receipt: Any,
    *,
    reason: str,
    actor: Any = None,  # noqa: ARG001 — as above
    entries: Sequence[Any] = (),
) -> None:
    """A cancelled delivery takes the stock back out, and the register says so."""
    _record_reversals(
        entries,
        on_date=receipt.received_on,
        reason=reason or f"Receipt {receipt.number} cancelled",
    )


def _record_reversals(entries: Sequence[Any], *, on_date: date, reason: str) -> None:
    controlled = controlled_profiles({entry.item_id for entry in entries}, on_date=on_date)
    for entry in entries:
        if entry.item_id not in controlled:
            continue
        record_entry(
            branch=entry.branch,
            location=entry.location,
            item=entry.item,
            batch=entry.batch,
            entry_type=RegisterEntryType.CORRECTION,
            quantity=entry.quantity,
            occurred_on=entry.occurred_on,
            document_type=entry.document_type,
            document_id=entry.document_id,
            document_number=entry.document_number,
            corrects=_entry_being_corrected(entry),
            reason=reason,
        )


def _entry_being_corrected(reversal: Any) -> NarcoticRegisterEntry | None:
    """The register line the reversed stock movement produced, if it is findable."""
    original = getattr(reversal, "reverses", None)
    if original is None:
        return None
    return NarcoticRegisterEntry.objects.filter(
        item_id=original.item_id,
        batch_id=original.batch_id,
        document_type=original.document_type,
        document_id=original.document_id,
        quantity=original.quantity,
    ).first()


def record_receipt(
    receipt: Any,
    *,
    entries: Sequence[Any],
    actor: Any = None,  # noqa: ARG001 — a delivery is signed for by the receipt, not the register
) -> None:
    """Called by core.purchasing once a delivery is posted.

    Also where the locked cabinet is enforced. A controlled drug put away on an open shelf is a
    finding on its own, and the moment it is received is the one moment somebody is looking at it.
    """
    controlled = controlled_profiles(
        {entry.item_id for entry in entries}, on_date=receipt.received_on
    )
    if not controlled:
        return

    _require_locked_storage(receipt.location, controlled)

    for entry in entries:
        if entry.item_id not in controlled:
            continue
        record_entry(
            branch=entry.branch,
            location=entry.location,
            item=entry.item,
            batch=entry.batch,
            entry_type=RegisterEntryType.RECEIPT,
            quantity=entry.quantity,
            occurred_on=entry.occurred_on,
            supplier_name=receipt.supplier.name,
            supplier_invoice_number=receipt.supplier_invoice_number,
            document_type=entry.document_type,
            document_id=entry.document_id,
            document_number=entry.document_number,
        )


def _require_locked_storage(location: Any, controlled: dict[Any, MedicineProfile]) -> None:
    from kernel.tenancy.models import LocationType

    if location is not None and location.type == LocationType.LOCKED_CABINET:
        return

    names = ", ".join(sorted(profile.item.name for profile in controlled.values()))
    where = location.name if location is not None else "an unspecified place"
    raise DomainError(
        errors.CONTROLLED_DRUG_NEEDS_LOCKED_STORAGE,
        f"{names} must go into a locked cabinet, not {where}.",
    )


# --------------------------------------------------------------------------- corrections
@transaction.atomic
def correct_entry(
    entry: NarcoticRegisterEntry, *, quantity: Decimal, reason: str, actor: Any = None
) -> NarcoticRegisterEntry:
    """Correct an earlier line without touching it.

    A reason is required. An unexplained correction in a narcotics register is worse than the
    error it corrects, because it is the shape a diversion takes.
    """
    if not reason.strip():
        raise DomainError(errors.REGISTER_CORRECTION_NEEDS_REASON)

    return record_entry(
        branch=entry.branch,
        location=entry.location,
        item=entry.item,
        batch=entry.batch,
        entry_type=RegisterEntryType.CORRECTION,
        quantity=quantity,
        occurred_on=entry.occurred_on,
        corrects=entry,
        reason=reason,
        **_dispenser_details(actor, on_date=entry.occurred_on),
    )


@transaction.atomic
def record_count(
    *,
    branch: Any,
    item: Any,
    counted_quantity: Decimal | int | str,
    occurred_on: date,
    witness_name: str,
    reason: str,
    batch: Any = None,
    actor: Any = None,
) -> NarcoticRegisterEntry | None:
    """Record a physical count of the cabinet, and whatever difference it found.

    A witness is required. Counting controlled stock alone and writing the number down is not a
    control, which is why every paper narcotics procedure asks for a second signature. Returns
    None when the count agrees with the register: there is nothing to write.
    """
    if not witness_name.strip():
        raise DomainError(errors.REGISTER_COUNT_NEEDS_WITNESS)
    if not reason.strip():
        raise DomainError(errors.REGISTER_CORRECTION_NEEDS_REASON)
    _require_a_batch_to_count(branch=branch, item=item, batch=batch)

    expected = balance_of(branch=branch, item=item, batch=batch)
    difference = Decimal(str(counted_quantity)) - expected
    if difference == 0:
        return None

    return record_entry(
        branch=branch,
        item=item,
        batch=batch,
        entry_type=RegisterEntryType.ADJUSTMENT,
        quantity=difference,
        occurred_on=occurred_on,
        witness_name=witness_name,
        reason=reason,
        **_dispenser_details(actor, on_date=occurred_on),
    )


def _require_a_batch_to_count(*, branch: Any, item: Any, batch: Any) -> None:
    """A count of a drug held in batches has to say which batch it counted.

    The register is kept per batch, so an adjustment naming no batch leaves every batch balance
    still wrong and adds a phantom one that belongs to nothing. Counting the whole cabinet means
    counting each batch in it.
    """
    if batch is not None:
        return
    if (
        NarcoticRegisterBalance.objects.filter(branch=branch, item=item)
        .exclude(batch__isnull=True)
        .exists()
    ):
        raise DomainError(errors.REGISTER_COUNT_IS_PER_BATCH)


# --------------------------------------------------------------------------- reading it back
def balance_of(*, branch: Any, item: Any, batch: Any = None) -> Decimal:
    """What the register says should be in the cabinet."""
    balance = NarcoticRegisterBalance.objects.filter(branch=branch, item=item, batch=batch).first()
    return balance.quantity if balance else Decimal("0")


def total_balance_of(*, branch: object, item: object) -> Decimal:
    """The whole cabinet's balance for one drug, across every batch.

    What a register page's footer shows. `balance_of` answers for one batch, which is what an
    entry needs; a person counting the cabinet is counting the drug.
    """
    total = NarcoticRegisterBalance.objects.filter(branch=branch, item=item).aggregate(
        total=Sum("quantity")
    )["total"]
    return total or Decimal("0")


def register_page(*, branch: Any, item: Any, start: date, end: date) -> list[NarcoticRegisterEntry]:
    """One drug's register for a period, in the order it was written.

    What a printed page and an inspection export are both rendered from. The layout DDA prescribes
    is still to be obtained — CR-DDA-02 — so this returns the lines, not a format.
    """
    return list(
        NarcoticRegisterEntry.objects.filter(
            branch=branch, item=item, occurred_on__gte=start, occurred_on__lte=end
        )
        .select_related("batch", "prescriber", "dispensed_by", "prescription")
        .order_by("occurred_on", "created_at")
    )


@dataclass(frozen=True, slots=True)
class RegisterDiscrepancy:
    branch_id: Any
    item_id: Any
    batch_id: Any
    balance_says: Decimal
    entries_say: Decimal

    @property
    def difference(self) -> Decimal:
        return self.balance_says - self.entries_say


def reconcile_register(*, branch: Any = None) -> list[RegisterDiscrepancy]:
    """Add the register up and compare it with the running balance.

    Reports rather than repairs. A running balance that has drifted from the entries means
    something wrote to the register outside this module, and quietly correcting the number would
    destroy the only evidence that it happened.
    """
    balances = NarcoticRegisterBalance.objects.all()
    entries = NarcoticRegisterEntry.objects.all()
    if branch is not None:
        balances = balances.filter(branch=branch)
        entries = entries.filter(branch=branch)

    totals = {
        (row["branch_id"], row["item_id"], row["batch_id"]): row["total"] or Decimal("0")
        for row in entries.values("branch_id", "item_id", "batch_id").annotate(
            total=Sum("quantity")
        )
    }

    discrepancies: list[RegisterDiscrepancy] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for balance in balances:
        key = (balance.branch_id, balance.item_id, balance.batch_id)
        seen.add(key)
        summed = totals.get(key, Decimal("0"))
        if summed != balance.quantity:
            discrepancies.append(
                RegisterDiscrepancy(*key, balance_says=balance.quantity, entries_say=summed)
            )

    # Entries with no balance row at all: one was deleted, or never created.
    for key, summed in totals.items():
        if key not in seen and summed != 0:
            discrepancies.append(
                RegisterDiscrepancy(*key, balance_says=Decimal("0"), entries_say=summed)
            )
    return discrepancies
