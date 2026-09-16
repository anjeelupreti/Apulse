"""Kernel permissions. Vertical modules add their own in their own `permissions.py`."""

from .registry import register

# --- organisation ---------------------------------------------------------
BRANCH_VIEW = register("tenancy.branch.view", "View branches", "शाखा हेर्ने", is_read_only=True)
BRANCH_MANAGE = register("tenancy.branch.manage", "Add and edit branches", "शाखा थप्ने / सम्पादन")
LEGAL_ENTITY_VIEW = register(
    "tenancy.legal_entity.view", "View business details", "व्यवसाय विवरण हेर्ने", is_read_only=True
)
LEGAL_ENTITY_MANAGE = register(
    "tenancy.legal_entity.manage",
    "Edit business and tax registration details",
    "व्यवसाय तथा कर दर्ता विवरण सम्पादन",
    description="PAN, VAT registration and IRD office. Affects every invoice the branch issues.",
)
LOCATION_VIEW = register(
    "tenancy.location.view", "View storage locations", "भण्डारण स्थान हेर्ने", is_read_only=True
)
LOCATION_MANAGE = register(
    "tenancy.location.manage", "Add and edit storage locations", "भण्डारण स्थान व्यवस्थापन"
)

# --- people ---------------------------------------------------------------
USER_VIEW = register("identity.user.view", "View staff", "कर्मचारी हेर्ने", is_read_only=True)
USER_MANAGE = register(
    "identity.user.manage", "Invite, edit and disable staff", "कर्मचारी निम्त्याउने / व्यवस्थापन"
)
CREDENTIAL_VIEW = register(
    "identity.credential.view",
    "View professional registrations",
    "व्यावसायिक दर्ता हेर्ने",
    is_read_only=True,
)
CREDENTIAL_VERIFY = register(
    "identity.credential.verify",
    "Verify professional registrations",
    "व्यावसायिक दर्ता प्रमाणित गर्ने",
    description="Confirming a pharmacist's council registration against the council record.",
)
LOGIN_ATTEMPT_VIEW = register(
    "identity.login_attempt.view",
    "View the sign-in security log",
    "लगइन सुरक्षा अभिलेख हेर्ने",
    is_read_only=True,
)

# --- access control -------------------------------------------------------
ROLE_VIEW = register("rbac.role.view", "View roles", "भूमिका हेर्ने", is_read_only=True)
ROLE_MANAGE = register(
    "rbac.role.manage",
    "Create and edit roles",
    "भूमिका सिर्जना / सम्पादन",
    description="Changing what any member of a role may do.",
)
ASSIGNMENT_VIEW = register(
    "rbac.assignment.view", "View who has which role", "कसलाई कुन भूमिका छ हेर्ने", is_read_only=True
)
ASSIGNMENT_MANAGE = register(
    "rbac.assignment.manage", "Grant and revoke roles", "भूमिका प्रदान / फिर्ता"
)
