"""The pharmacy module manifest."""

from kernel.entitlements.manifest import FeatureKind, FeatureSpec, ModuleManifest, register

PHARMACY = register(
    ModuleManifest(
        code="pharmacy",
        name_en="Pharmacy",
        name_ne="फार्मेसी",
        description="Dispensing, drug schedules, prescriptions and the registers DDA inspects.",
        version="1.0.0",
        depends_on=("platform",),
        features=(
            FeatureSpec(
                code="pharmacy.dispensing",
                name_en="Dispensing",
                name_ne="औषधि वितरण",
                default=True,
                description="Drug schedule rules and prescription capture at the counter.",
            ),
            FeatureSpec(
                code="pharmacy.narcotic_register",
                name_en="Narcotic register",
                name_ne="लागूऔषध अभिलेख",
                default=True,
                description="The register required for Samuha Ka medicines.",
            ),
            FeatureSpec(
                code="pharmacy.offline_pos",
                name_en="Offline counter",
                name_ne="अफलाइन काउन्टर",
                kind=FeatureKind.BOOLEAN,
                default=False,
            ),
        ),
    )
)
