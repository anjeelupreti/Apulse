"""The pharmacy module: what makes this a pharmacy rather than a shop.

Medicines carry a drug schedule — समूह क, ख or ग — and the schedule decides what has to happen
before a medicine may be handed over. Those rules come from the Department of Drug Administration
and change by notice, so they are **versioned data with effective dates**, not conditions written
into code. A DDA notice becomes a data update, not a release.

What the research corrected (see docs/research/nepal-regulatory-findings.md): **both समूह क and
समूह ख require a prescription**, and समूह ग is supplied on a pharmacist's advice. The BRD had
treated ख as the prescription tier and ग as unrestricted.
"""
