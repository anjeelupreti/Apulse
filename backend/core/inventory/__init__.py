"""Batches, the stock ledger, and what is actually on the shelf.

Two rules drive the design:

* **Expired stock is never sold.** The BRD's first measurable target is zero expired drug sales,
  and the only way to mean it is to make expiry a hard stop rather than a warning.
* **Stock movements are history, not state.** Every receipt, sale, adjustment and transfer is an
  entry in an append-only ledger. What is on the shelf is the sum of those entries, kept in a
  balance table for speed and reconcilable against the ledger at any time.
"""
