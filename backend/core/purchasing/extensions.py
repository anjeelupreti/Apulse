"""Where a module joins in when a delivery is posted.

The same arrangement as `core.sales.extensions`, and for the same reason: core cannot import a
module. The pharmacy module registers the narcotic register here, so a controlled drug is written
into the register on the way in as well as on the way out — a register that only records what
left cannot be reconciled against what is in the cabinet.

The hooks run inside the caller's transaction, so a receipt that cannot be registered does not
become stock.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import GoodsReceipt

PostedHook = Callable[..., None]
CancelledHook = Callable[..., None]

_posted_hooks: list[PostedHook] = []
_cancelled_hooks: list[CancelledHook] = []


def register_posted_hook(hook: PostedHook) -> PostedHook:
    if hook not in _posted_hooks:
        _posted_hooks.append(hook)
    return hook


def unregister_posted_hook(hook: PostedHook) -> None:
    if hook in _posted_hooks:
        _posted_hooks.remove(hook)


def run_posted_hooks(receipt: "GoodsReceipt", *, entries: list[Any], actor: Any = None) -> None:
    for hook in _posted_hooks:
        hook(receipt, entries=entries, actor=actor)


def register_cancelled_hook(hook: CancelledHook) -> CancelledHook:
    if hook not in _cancelled_hooks:
        _cancelled_hooks.append(hook)
    return hook


def unregister_cancelled_hook(hook: CancelledHook) -> None:
    if hook in _cancelled_hooks:
        _cancelled_hooks.remove(hook)


def run_cancelled_hooks(
    receipt: "GoodsReceipt", *, reason: str, actor: Any = None, entries: list[Any] | None = None
) -> None:
    for hook in _cancelled_hooks:
        hook(receipt, reason=reason, actor=actor, entries=entries or [])
