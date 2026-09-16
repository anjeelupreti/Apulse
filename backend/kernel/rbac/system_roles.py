"""Built-in roles seeded into every tenant.

Explicit permission lists are written against permissions that exist today; the two sentinels keep
the open-ended roles correct as modules are added:

* ``ALL`` — the Owner, who can always do everything in their own account.
* ``READ_ONLY`` — every registered read-only permission, so a new module cannot accidentally give
  an auditor or a DDA inspector the ability to change records.
"""

from dataclasses import dataclass
from typing import Literal

from . import registry

ALL: Literal["*all*"] = "*all*"
READ_ONLY: Literal["*read-only*"] = "*read-only*"

PermissionSpec = tuple[str, ...] | Literal["*all*", "*read-only*"]


@dataclass(frozen=True, slots=True)
class SystemRole:
    code: str
    name_en: str
    name_ne: str
    description: str
    permissions: PermissionSpec

    def resolve(self) -> frozenset[str]:
        if self.permissions == ALL:
            return registry.all_codes()
        if self.permissions == READ_ONLY:
            return registry.read_only_codes()
        # Ignore permissions belonging to modules that are not installed in this deployment.
        return frozenset(code for code in self.permissions if registry.exists(code))


OWNER = "owner"
ADMINISTRATOR = "administrator"
PHARMACIST_IN_CHARGE = "pharmacist_in_charge"
PHARMACIST = "pharmacist"
ASSISTANT_PHARMACIST = "assistant_pharmacist"
COUNTER_STAFF = "counter_staff"
STORE_KEEPER = "store_keeper"
PURCHASE_OFFICER = "purchase_officer"
ACCOUNTANT = "accountant"
AUDITOR = "auditor"
DDA_INSPECTOR = "dda_inspector"
DELIVERY_STAFF = "delivery_staff"

_VIEW_ORGANISATION = ("tenancy.branch.view", "tenancy.location.view")

SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        code=OWNER,
        name_en="Owner",
        name_ne="मालिक",
        description="Full access to everything in this account.",
        permissions=ALL,
    ),
    SystemRole(
        code=ADMINISTRATOR,
        name_en="Administrator",
        name_ne="प्रशासक",
        description="Runs the account day to day: staff, branches and settings.",
        permissions=(
            "tenancy.branch.view",
            "tenancy.branch.manage",
            "tenancy.legal_entity.view",
            "tenancy.location.view",
            "tenancy.location.manage",
            "identity.user.view",
            "identity.user.manage",
            "identity.credential.view",
            "identity.login_attempt.view",
            "rbac.role.view",
            "rbac.assignment.view",
            "rbac.assignment.manage",
        ),
    ),
    SystemRole(
        code=PHARMACIST_IN_CHARGE,
        name_en="Pharmacist in charge",
        name_ne="प्रमुख फार्मासिस्ट",
        description="The registered pharmacist responsible for the branch and its registers.",
        permissions=(
            *_VIEW_ORGANISATION,
            "tenancy.location.manage",
            "identity.user.view",
            "identity.credential.view",
            "identity.credential.verify",
        ),
    ),
    SystemRole(
        code=PHARMACIST,
        name_en="Pharmacist",
        name_ne="फार्मासिस्ट",
        description="Dispenses medicines and counsels patients.",
        permissions=(*_VIEW_ORGANISATION, "identity.credential.view"),
    ),
    SystemRole(
        code=ASSISTANT_PHARMACIST,
        name_en="Assistant pharmacist",
        name_ne="सहायक फार्मासिस्ट",
        description="Assists with dispensing within the limits of their registration.",
        permissions=_VIEW_ORGANISATION,
    ),
    SystemRole(
        code=COUNTER_STAFF,
        name_en="Counter staff",
        name_ne="काउन्टर कर्मचारी",
        description="Serves customers and takes payment at the counter.",
        permissions=_VIEW_ORGANISATION,
    ),
    SystemRole(
        code=STORE_KEEPER,
        name_en="Store keeper",
        name_ne="भण्डार प्रमुख",
        description="Receives goods and looks after stock and storage.",
        permissions=(*_VIEW_ORGANISATION, "tenancy.location.manage"),
    ),
    SystemRole(
        code=PURCHASE_OFFICER,
        name_en="Purchase officer",
        name_ne="खरिद अधिकृत",
        description="Orders from suppliers and manages purchasing.",
        permissions=_VIEW_ORGANISATION,
    ),
    SystemRole(
        code=ACCOUNTANT,
        name_en="Accountant",
        name_ne="लेखापाल",
        description="Handles the books, tax returns and payments.",
        permissions=(*_VIEW_ORGANISATION, "tenancy.legal_entity.view"),
    ),
    SystemRole(
        code=AUDITOR,
        name_en="Auditor",
        name_ne="लेखापरीक्षक",
        description="Reads everything, changes nothing.",
        permissions=READ_ONLY,
    ),
    SystemRole(
        code=DDA_INSPECTOR,
        name_en="DDA inspector",
        name_ne="औषधि व्यवस्था विभाग निरीक्षक",
        description=(
            "Read-only access for a regulatory inspection. Grant with an expiry covering the visit."
        ),
        permissions=READ_ONLY,
    ),
    SystemRole(
        code=DELIVERY_STAFF,
        name_en="Delivery staff",
        name_ne="डेलिभरी कर्मचारी",
        description="Delivers orders to customers.",
        permissions=(),
    ),
)

BY_CODE: dict[str, SystemRole] = {role.code: role for role in SYSTEM_ROLES}
