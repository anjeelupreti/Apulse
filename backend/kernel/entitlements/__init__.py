"""Modules, the features they contain, and which of them each account is entitled to.

Modules are declared in code (a `module.py` manifest per app) and synced into the database so the
control plane can attach them to plans. What a tenant may actually use is resolved from:

    installed module  +  granted feature  +  no kill switch  +  rollout applies

Plans and subscriptions live in the control plane; when a subscription changes it *projects* the
plan's features into grants here. That keeps billing out of the request path: resolving what a
pharmacy may do never has to reason about invoices.
"""
