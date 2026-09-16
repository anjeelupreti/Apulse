"""Receiving goods from a supplier.

This is where stock, batches, expiry dates and cost all enter the system, so it is where most of
the data quality is won or lost. The details that matter in Nepal and that generic ERPs get wrong:

* **Bonus quantity.** "10 + 1 free" is the normal shape of a pharmaceutical deal. The free unit is
  not free — it lowers the cost of all eleven, and margin is wrong if it is ignored.
* **MRP per batch.** The printed price differs between lots of the same medicine.
* **Recoverable VAT.** For a VAT-registered pharmacy, input VAT is not part of the cost of stock.
  For one that is not registered, it is.
"""
