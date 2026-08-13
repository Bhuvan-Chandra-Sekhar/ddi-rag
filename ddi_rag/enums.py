"""
enums.py — Shared domain enums for the medication-safety platform.

Values are plain strings (not auto()) so they are stable in the database
across code changes.
"""

from enum import Enum


class UserRole(str, Enum):
    PATIENT        = "patient"
    PHARMACIST     = "pharmacist"
    PRESCRIBER     = "prescriber"
    SAFETY_OFFICER = "safety_officer"
    ADMINISTRATOR  = "administrator"
    SUPPORT        = "support"
    AUDITOR        = "auditor"


class PrescriptionStatus(str, Enum):
    ACTIVE       = "active"
    DISCONTINUED = "discontinued"
    COMPLETED    = "completed"


class SafetyCaseState(str, Enum):
    DRAFT                        = "draft"
    AWAITING_ANALYSIS            = "awaiting_analysis"
    AWAITING_PHARMACIST_REVIEW   = "awaiting_pharmacist_review"
    AWAITING_PRESCRIBER_RESPONSE = "awaiting_prescriber_response"
    ESCALATED                    = "escalated"
    READY_TO_DISPENSE            = "ready_to_dispense"
    HELD_OR_CANCELLED            = "held_or_cancelled"
    CLOSED                       = "closed"


class FindingType(str, Enum):
    DDI             = "ddi"
    ALLERGY         = "allergy"
    CONTRAINDICATION = "contraindication"
    DUPLICATE       = "duplicate"
    DOSE            = "dose"
    MONITORING      = "monitoring"
    UNKNOWN         = "unknown"


class Severity(str, Enum):
    INFORMATIONAL = "informational"
    CAUTION       = "caution"
    MAJOR         = "major"
    CRITICAL      = "critical"
    UNKNOWN       = "unknown"


class ReviewStatus(str, Enum):
    PENDING    = "pending"
    ACCEPTED   = "accepted"
    DISMISSED  = "dismissed"
    OVERRIDDEN = "overridden"
    ESCALATED  = "escalated"
    RESOLVED   = "resolved"


class PrescriberDecision(str, Enum):
    ACCEPT               = "accept"
    CHANGE               = "change"
    STOP                 = "stop"
    CONTINUE_WITH_RATIONALE = "continue_with_rationale"
    REQUEST_MORE_DATA    = "request_more_data"


class DispensingStatus(str, Enum):
    DISPENSED = "dispensed"
    HELD      = "held"
    CANCELLED = "cancelled"


class DeliveryChannel(str, Enum):
    PORTAL    = "portal"
    SMS       = "sms"
    EMAIL     = "email"
    PHONE     = "phone"
    IN_PERSON = "in_person"


class RuleStatus(str, Enum):
    """A rule mined from a raw dataset starts DRAFT and stays clinically
    inert (never drives a confirmed Finding) until a qualified reviewer
    marks it APPROVED. See services/clinical_rules.py."""
    DRAFT    = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
