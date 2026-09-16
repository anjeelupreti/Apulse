"""The platform module: always installed, and home to the account-wide limits plans sell.

Vertical modules (pharmacy, wholesale, hospital pharmacy, …) declare their own `module.py`.
"""

from .manifest import FeatureKind, FeatureSpec, ModuleManifest, register

PLATFORM = register(
    ModuleManifest(
        code="platform",
        name_en="Platform",
        name_ne="प्लेटफर्म",
        description="Accounts, branches, staff, access control and the audit trail.",
        version="1.0.0",
        is_core=True,
        features=(
            FeatureSpec(
                code="platform.branches",
                name_en="Branches",
                name_ne="शाखा",
                kind=FeatureKind.LIMIT,
                unit="branches",
                description="How many branches this account may operate.",
            ),
            FeatureSpec(
                code="platform.users",
                name_en="Staff accounts",
                name_ne="कर्मचारी खाता",
                kind=FeatureKind.LIMIT,
                unit="users",
            ),
            FeatureSpec(
                code="platform.devices",
                name_en="Registered devices",
                name_ne="दर्ता भएका उपकरण",
                kind=FeatureKind.LIMIT,
                unit="devices",
            ),
            FeatureSpec(
                code="platform.custom_domain",
                name_en="Custom domain",
                name_ne="आफ्नै डोमेन",
                kind=FeatureKind.BOOLEAN,
                default=False,
            ),
            FeatureSpec(
                code="platform.api_access",
                name_en="API access",
                name_ne="एपीआई पहुँच",
                kind=FeatureKind.BOOLEAN,
                default=False,
            ),
        ),
    )
)
