"""Selling: the invoice a customer walks out with, and the record IRD inspects.

Three things shape this more than anything else:

* **MRP is a ceiling, not a suggestion.** Selling above the printed maximum retail price is an
  offence, so the system refuses it rather than warning about it.
* **A shelf price already contains its tax.** Nepali pharmacies price in round rupees at MRP, so
  tax is worked backwards out of the price rather than added on top.
* **Which batch went to which customer must be recoverable.** When a batch is recalled, the
  question is "who has it", and the only way to answer is to record the allocation at the time.
"""
