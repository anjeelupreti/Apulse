"""The item master: what a pharmacy buys, holds and sells.

Everything is stored in **base units** — a tablet, a millilitre, a gram, a piece. Packs are
conversions on top of that. This is what makes "sell me four tablets out of that strip" and
"receive twenty boxes of ten strips" the same arithmetic, and it is why stock never has to be
reconciled between two different notions of quantity.
"""
