"""
Gold cases for the clinical regression eval suite (architecture doc
section 13: "Clinical regression | Gold cases for DDI, allergy,
contraindication, duplicate therapy, organ impairment, pregnancy, labs").

Coverage note: only DDI-pair, drug-allergy, and duplicate-ingredient rules
are implemented (Phase 3 scope). Contraindication, organ-impairment,
pregnancy, and lab-based rules are NOT yet built — there is no gold case
for them because there is nothing to regress-test yet. Do not treat their
absence here as "passing"; it means "not implemented."

Each case:
    name              : str
    ingredients       : list[str]   — prescribed ingredients for this case
    allergies         : list[str]
    seed_rules        : list[dict]  — ClinicalRule rows to seed before running
    expected_findings : list[dict]  — shaped like clinical_rules finding dicts
                                       (only type/severity/patient_factors matter
                                       for matching — see eval_metrics._finding_key)
"""

from enums import FindingType, RuleStatus, Severity

GOLD_CASES = [
    {
        "name": "ddi_major_aspirin_warfarin",
        "ingredients": ["aspirin", "warfarin"],
        "allergies": [],
        "seed_rules": [{
            "pair_key": "aspirin||warfarin", "ingredient_a": "aspirin", "ingredient_b": "warfarin",
            "clinical_effect": "increases bleeding risk", "severity": Severity.MAJOR,
            "status": RuleStatus.APPROVED, "rule_version": "gold-v1",
        }],
        "expected_findings": [
            {"type": FindingType.DDI, "severity": Severity.MAJOR,
             "patient_factors": {"ingredient_a": "aspirin", "ingredient_b": "warfarin"}},
        ],
    },
    {
        "name": "allergy_critical_penicillin",
        "ingredients": ["penicillin"],
        "allergies": ["penicillin"],
        "seed_rules": [],
        "expected_findings": [
            {"type": FindingType.ALLERGY, "severity": Severity.CRITICAL,
             "patient_factors": {"ingredient": "penicillin"}},
        ],
    },
    {
        "name": "duplicate_caution_ibuprofen",
        "ingredients": ["ibuprofen", "ibuprofen"],
        "allergies": [],
        "seed_rules": [],
        "expected_findings": [
            {"type": FindingType.DUPLICATE, "severity": Severity.CAUTION,
             "patient_factors": {"ingredient": "ibuprofen"}},
        ],
    },
    {
        "name": "true_negative_safe_combination",
        "ingredients": ["acetaminophen", "cetirizine"],
        "allergies": ["penicillin"],
        "seed_rules": [],
        "expected_findings": [],  # nothing should fire — a true negative
    },
    {
        "name": "unreviewed_pair_is_not_silently_safe",
        "ingredients": ["drugx", "drugy"],
        "allergies": [],
        "seed_rules": [{
            "pair_key": "drugx||drugy", "ingredient_a": "drugx", "ingredient_b": "drugy",
            "clinical_effect": "candidate interaction, not yet reviewed", "severity": Severity.UNKNOWN,
            "status": RuleStatus.DRAFT, "rule_version": "gold-v1",
        }],
        "expected_findings": [
            {"type": FindingType.UNKNOWN, "severity": Severity.UNKNOWN,
             "patient_factors": {"ingredient_a": "drugx", "ingredient_b": "drugy"}},
        ],
    },
    {
        "name": "combined_duplicate_and_ddi",
        "ingredients": ["aspirin", "warfarin", "warfarin"],
        "allergies": [],
        "seed_rules": [{
            "pair_key": "aspirin||warfarin", "ingredient_a": "aspirin", "ingredient_b": "warfarin",
            "clinical_effect": "increases bleeding risk", "severity": Severity.MAJOR,
            "status": RuleStatus.APPROVED, "rule_version": "gold-v1",
        }],
        "expected_findings": [
            {"type": FindingType.DDI, "severity": Severity.MAJOR,
             "patient_factors": {"ingredient_a": "aspirin", "ingredient_b": "warfarin"}},
            {"type": FindingType.DUPLICATE, "severity": Severity.CAUTION,
             "patient_factors": {"ingredient": "warfarin"}},
        ],
    },
]
