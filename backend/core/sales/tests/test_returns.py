"""Credit notes: the only lawful way money comes back off a bill."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from core.inventory.models import MovementType, StockBalance, StockLedgerEntry
from core.sales.models import (
    CreditNoteKind,
    InvoiceStatus,
    ReturnDestination,
    ReturnReason,
)
from core.sales.returns import (
    add_return_line,
    credit_notes_for,
    credit_whole_invoice,
    creditable_quantity,
    credited_amount,
    is_copy,
    issue_credit_note,
    record_print,
    start_credit_note,
)
from core.sales.services import add_line, cancel_invoice, issue_invoice, start_invoice
from kernel.tenancy.models import Location
from shared.errors import DomainError

from .conftest import TODAY, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture
def quarantine(branch):
    return Location.objects.get(branch=branch, code="QUARANTINE")


def at(item, location) -> Decimal:
    """What is physically sitting in one place, saleable or not."""
    total = StockBalance.objects.filter(item=item, location=location).aggregate(
        total=Sum("quantity")
    )["total"]
    return total or Decimal("0")


def sold(paracetamol, branch, counter, *, strips="4"):
    """One issued bill for four strips of paracetamol."""
    stock_up(paracetamol, branch, counter, 1000)
    invoice = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(invoice, item=paracetamol, quantity=Decimal(strips))
    return issue_invoice(invoice).invoice


# --------------------------------------------------------------------------- the document
def test_a_return_is_numbered_in_its_own_series(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Customer changed their mind")
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))

    issued = issue_credit_note(note)
    assert issued.credit_note.number
    assert issued.credit_note.number != invoice.number
    assert issued.credit_note.fiscal_year == invoice.fiscal_year


def test_a_credit_note_needs_a_reason(paracetamol, branch, counter):
    """An unexplained credit note is the shape a till is emptied in."""
    invoice = sold(paracetamol, branch, counter)
    with pytest.raises(DomainError) as caught:
        start_credit_note(invoice, reason="   ")
    assert caught.value.error.code == "CREDIT_NOTE_NEEDS_A_REASON"


def test_a_draft_bill_cannot_be_credited(paracetamol, branch, counter):
    """Nobody has been given it, so there is nothing to take back. Change the draft instead."""
    stock_up(paracetamol, branch, counter, 100)
    draft = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(draft, item=paracetamol, quantity=Decimal("1"))

    with pytest.raises(DomainError) as caught:
        start_credit_note(draft, reason="Mistake")
    assert caught.value.error.code == "CREDIT_NOTE_NEEDS_AN_ISSUED_INVOICE"


def test_an_issued_credit_note_cannot_be_changed(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Changed their mind")
    line = invoice.lines.first()
    add_return_line(note, invoice_line=line, quantity=Decimal("1"))
    issue_credit_note(note)

    with pytest.raises(DomainError) as caught:
        add_return_line(note, invoice_line=line, quantity=Decimal("1"))
    assert caught.value.error.code == "CREDIT_NOTE_NOT_EDITABLE"


def test_an_empty_credit_note_is_refused(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Nothing on it")

    with pytest.raises(DomainError) as caught:
        issue_credit_note(note)
    assert caught.value.error.code == "CREDIT_NOTE_HAS_NO_LINES"


def test_a_refused_credit_note_consumes_no_number(paracetamol, branch, counter):
    from kernel.numbering.services import preview_next

    invoice = sold(paracetamol, branch, counter)
    before = preview_next(document_type="sales.credit_note", branch=branch, on_date=TODAY)

    with pytest.raises(DomainError):
        issue_credit_note(start_credit_note(invoice, reason="Nothing on it"))

    assert preview_next(document_type="sales.credit_note", branch=branch, on_date=TODAY) == before


# --------------------------------------------------------------------------- how much
def test_you_cannot_return_more_than_was_sold(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter, strips="4")
    note = start_credit_note(invoice, reason="Changed their mind")

    with pytest.raises(DomainError) as caught:
        add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("5"))
    assert caught.value.error.code == "CREDIT_EXCEEDS_WHAT_WAS_SOLD"


def test_two_half_returns_cannot_add_up_to_more_than_the_whole(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter, strips="4")
    line = invoice.lines.first()

    first = start_credit_note(invoice, reason="Half back")
    add_return_line(first, invoice_line=line, quantity=Decimal("3"))
    issue_credit_note(first)

    assert creditable_quantity(line) == Decimal("1")

    second = start_credit_note(invoice, reason="The rest")
    with pytest.raises(DomainError) as caught:
        add_return_line(second, invoice_line=line, quantity=Decimal("2"))
    assert caught.value.error.code == "CREDIT_EXCEEDS_WHAT_WAS_SOLD"


def test_an_unfinished_draft_does_not_block_a_return(paracetamol, branch, counter):
    """A draft is somebody's unfinished intention, not a claim on the stock."""
    invoice = sold(paracetamol, branch, counter, strips="4")
    line = invoice.lines.first()

    abandoned = start_credit_note(invoice, reason="Started and left")
    add_return_line(abandoned, invoice_line=line, quantity=Decimal("4"))

    assert creditable_quantity(line) == Decimal("4")


def test_a_line_from_another_invoice_is_refused(paracetamol, branch, counter):
    first = sold(paracetamol, branch, counter)
    second = sold(paracetamol, branch, counter)

    note = start_credit_note(first, reason="Mixed up")
    with pytest.raises(DomainError) as caught:
        add_return_line(note, invoice_line=second.lines.first(), quantity=Decimal("1"))
    assert caught.value.error.code == "CREDIT_LINE_IS_NOT_ON_THIS_INVOICE"


def test_a_return_of_nothing_is_refused(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Nothing")

    with pytest.raises(DomainError) as caught:
        add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("0"))
    assert caught.value.error.code == "CREDIT_QUANTITY_MUST_BE_POSITIVE"


# --------------------------------------------------------------------------- the money
def test_a_full_credit_note_comes_to_exactly_what_the_invoice_did(
    paracetamol, thermometer, branch, counter
):
    """The property that matters for VAT: a credit note reverses the invoice exactly."""
    stock_up(paracetamol, branch, counter, 1000)
    stock_up(thermometer, branch, counter, 10)
    invoice = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(invoice, item=paracetamol, quantity=Decimal("3"))
    add_line(invoice, item=thermometer, quantity=Decimal("1"))
    issued = issue_invoice(invoice).invoice

    note = credit_whole_invoice(issued, reason="Everything back").credit_note

    assert note.gross_amount == issued.gross_amount
    assert note.discount_amount == issued.discount_amount
    assert note.taxable_amount == issued.taxable_amount
    assert note.tax_amount == issued.tax_amount
    assert note.rounding_amount == issued.rounding_amount
    assert note.payable_amount == issued.payable_amount


def test_a_credit_note_is_priced_at_what_was_charged(paracetamol, branch, counter):
    """Crediting at today's price would turn a refund into a discount, or a windfall."""
    invoice = sold(paracetamol, branch, counter)
    line = invoice.lines.first()

    note = start_credit_note(invoice, reason="One strip back")
    credited = add_return_line(note, invoice_line=line, quantity=Decimal("1"))[0]

    assert credited.rate == line.rate
    assert credited.tax_percentage == line.tax_percentage


def test_a_partial_return_credits_only_that_part(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter, strips="4")
    note = start_credit_note(invoice, reason="One of four back")
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issued = issue_credit_note(note).credit_note

    assert issued.payable_amount == invoice.payable_amount / 4
    assert credited_amount(invoice) == issued.payable_amount


# --------------------------------------------------------------------------- the stock
def test_returned_stock_goes_to_quarantine_by_default(paracetamol, branch, counter, quarantine):
    """Nobody can say how a pack was kept once it has left. A pharmacist looks at it first."""
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Changed their mind")
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issue_credit_note(note)

    assert at(paracetamol, quarantine) == Decimal("10")


def test_putting_it_back_on_the_shelf_is_a_deliberate_choice(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(
        invoice,
        reason="Sealed pack, never left the counter",
        destination=ReturnDestination.SELLABLE,
    )
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issue_credit_note(note)

    assert note.location == counter


def test_the_return_is_a_sale_return_movement_not_a_reversal(paracetamol, branch, counter):
    """The sale happened. The goods came back, which is a different event."""
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(invoice, reason="Changed their mind")
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issued = issue_credit_note(note)

    assert [entry.movement_type for entry in issued.entries] == [MovementType.SALE_RETURN]
    assert issued.entries[0].document_number == issued.credit_note.number


def test_a_return_comes_back_as_the_batch_it_was_sold_as(paracetamol, branch, counter):
    """A recall is answered from the batch record, so it has to stay true."""
    invoice = sold(paracetamol, branch, counter)
    sold_batch = invoice.lines.first().allocations.first().batch

    note = start_credit_note(invoice, reason="Changed their mind")
    line = add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))[0]

    assert line.batch == sold_batch


def test_a_money_only_credit_note_moves_no_stock(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = start_credit_note(
        invoice,
        reason="Overcharged by a rupee",
        kind=CreditNoteKind.ADJUSTMENT,
        reason_code=ReturnReason.RATE_DIFFERENCE,
    )
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issued = issue_credit_note(note)

    assert issued.entries == []
    assert issued.credit_note.payable_amount > 0


# --------------------------------------------------------------------------- cancellation
def test_cancelling_an_invoice_issues_a_credit_note(paracetamol, branch, counter):
    """CR-IRD-04: marking our own record cancelled is not evidence. The note is."""
    invoice = sold(paracetamol, branch, counter)
    cancel_invoice(invoice, reason="Rung up twice")

    notes = credit_notes_for(invoice)
    assert len(notes) == 1
    assert notes[0].kind == CreditNoteKind.CANCELLATION
    assert notes[0].reason == "Rung up twice"
    assert notes[0].number
    assert notes[0].payable_amount == invoice.payable_amount


def test_the_cancellation_note_moves_no_stock_of_its_own(paracetamol, branch, counter):
    """The cancellation reversed the movements already. Doing it twice would double the stock."""
    invoice = sold(paracetamol, branch, counter)
    before = at(paracetamol, counter)
    cancel_invoice(invoice, reason="Rung up twice")

    note = credit_notes_for(invoice)[0]
    assert not StockLedgerEntry.objects.filter(
        document_type="sales.credit_note", document_id=str(note.pk)
    ).exists()
    assert at(paracetamol, counter) == before + Decimal("40")


def test_a_bill_that_was_partly_returned_cannot_be_cancelled(paracetamol, branch, counter):
    """The return already moved stock and credited money. Cancelling would do both again."""
    invoice = sold(paracetamol, branch, counter, strips="4")
    note = start_credit_note(invoice, reason="One back")
    add_return_line(note, invoice_line=invoice.lines.first(), quantity=Decimal("1"))
    issue_credit_note(note)

    with pytest.raises(DomainError) as caught:
        cancel_invoice(invoice, reason="Cancel the lot")
    assert caught.value.error.code == "INVOICE_ALREADY_PARTLY_CREDITED"


def test_cancelling_twice_issues_one_note(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    cancel_invoice(invoice, reason="Rung up twice")
    cancel_invoice(invoice, reason="Rung up twice")

    assert len(credit_notes_for(invoice)) == 1
    assert invoice.status == InvoiceStatus.CANCELLED


# --------------------------------------------------------------------------- printing
def test_a_reprinted_credit_note_is_marked_as_a_copy(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    note = credit_whole_invoice(invoice, reason="All back").credit_note

    assert record_print(note) == 1
    assert not is_copy(note)
    assert record_print(note) == 2
    assert is_copy(note)


def test_the_amount_reads_in_words(paracetamol, branch, counter):
    invoice = sold(paracetamol, branch, counter)
    issued = credit_whole_invoice(invoice, reason="All back")
    assert issued.amount_in_words == "Eighty rupees only"
