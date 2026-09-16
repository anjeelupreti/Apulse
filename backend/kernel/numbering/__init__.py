"""Document numbers: invoice series, credit note series, and everything else a document carries.

IRD inspects invoice numbering directly. The requirements that shape this package:

* **Sequential and gapless** within a branch and fiscal year.
* **Never reissued** — a number identifies exactly one document, permanently.
* **Reset at the fiscal year**, which in Nepal begins on Shrawan 1.
* **Usable offline**, because a counter with no internet still has to hand a customer a bill.

The last two pull against the first, which is why offline devices lease ranges and why
CR-IRD-06 asks IRD whether leased ranges are acceptable before this goes near a real pharmacy.
"""
