"""E14 Analysis — Mathematical validation + anomaly scoring.

Mathematical validation rules:
  1. Sum check: candidate_sum + blank + null + unmarked = total
  2. Non-negative: all counts >= 0
  3. 3-digit max: all counts <= 999
  4. Overvote: total > registered_voters (if available)
  5. Undervote: total < candidate_sum

Anomaly scoring:
  Combines signature risk + mathematical anomalies + OCR confidence
  into a 0-100 risk score with classification: CRITICAL / HIGH / MEDIUM / LOW
"""

from dataclasses import dataclass
from typing import Optional

from .ocr_engine import OcrResult
from .signature_detector import SignatureValidationResult
from .config import RISK_WEIGHTS


@dataclass(frozen=True)
class Anomaly:
    """A detected anomaly."""
    rule        : str          # e.g. "SUM_MISMATCH"
    severity    : str          # CRITICAL | HIGH | MEDIUM | LOW
    message     : str
    confidence  : float        # detection confidence 0-1
    page        : int          # which page (1, 2, 3)
    details     : Optional[dict] = None


@dataclass(frozen=True)
class ValidationResult:
    """Result of mathematical validation."""
    valid           : bool
    anomalies       : tuple[Anomaly, ...]
    anomaly_count   : int


def validate_mathematics(
    page1: OcrResult,
    page2: OcrResult,
    registered_voters: Optional[int] = None,
) -> ValidationResult:
    """Validate mathematical consistency of OCR results.

    Checks all rules and returns a ValidationResult with any anomalies.
    """
    anomalies: list[Anomaly] = []

    # Gather all votes
    all_candidate_votes = {}
    for cand in page1.candidates:
        all_candidate_votes[cand.candidate_number] = _votes_from_candidate(cand)
    for cand in page2.candidates:
        all_candidate_votes[cand.candidate_number] = _votes_from_candidate(cand)

    candidate_sum = sum(all_candidate_votes.values())

    # Page 2 summary
    if page2.summary:
        blank = page2.summary.blank_votes
        null  = page2.summary.null_votes
        unmarked = page2.summary.unmarked_votes
        total = page2.summary.total_votes
    else:
        blank = null = unmarked = total = 0

    # ── Rule 1: Sum check ──────────────────────────────────────────────────────
    computed_total = candidate_sum + blank + null + unmarked
    if total != computed_total:
        diff = abs(total - computed_total)
        anomalies.append(Anomaly(
            rule="SUM_MISMATCH",
            severity="CRITICAL",
            message=f"Total ({total}) != sum of votes ({computed_total}), diff={diff}",
            confidence=0.95,
            page=2,
            details={
                "declared_total": total,
                "computed_total": computed_total,
                "difference": diff,
                "candidate_sum": candidate_sum,
                "blank": blank,
                "null": null,
                "unmarked": unmarked,
            },
        ))

    # ── Rule 2: Non-negative ───────────────────────────────────────────────────
    for cand_num, votes in all_candidate_votes.items():
        if votes < 0:
            anomalies.append(Anomaly(
                rule="NEGATIVE_VOTES",
                severity="CRITICAL",
                message=f"Candidate {cand_num} has negative votes: {votes}",
                confidence=1.0,
                page=1 if cand_num <= 7 else 2,
                details={"candidate": cand_num, "votes": votes},
            ))

    if blank < 0 or null < 0 or unmarked < 0:
        anomalies.append(Anomaly(
            rule="NEGATIVE_SUMMARY",
            severity="CRITICAL",
            message=f"Negative summary: blank={blank}, null={null}, unmarked={unmarked}",
            confidence=1.0,
            page=2,
        ))

    # ── Rule 3: 3-digit max ───────────────────────────────────────────────────
    for cand_num, votes in all_candidate_votes.items():
        if votes > 999:
            anomalies.append(Anomaly(
                rule="EXCEEDS_3_DIGITS",
                severity="HIGH",
                message=f"Candidate {cand_num} has {votes} votes (exceeds 999)",
                confidence=0.9,
                page=1 if cand_num <= 7 else 2,
                details={"candidate": cand_num, "votes": votes},
            ))

    # ── Rule 4: Overvote ──────────────────────────────────────────────────────
    if registered_voters and total > registered_voters:
        anomalies.append(Anomaly(
            rule="OVERVOTE",
            severity="CRITICAL",
            message=f"Total votes ({total}) exceeds registered voters ({registered_voters})",
            confidence=0.95,
            page=2,
            details={"total": total, "registered": registered_voters},
        ))

    # ── Rule 5: Undervote (total < candidate sum) ─────────────────────────────
    if total > 0 and candidate_sum > total:
        anomalies.append(Anomaly(
            rule="UNDERVOTE",
            severity="MEDIUM",
            message=f"Candidate sum ({candidate_sum}) > total ({total})",
            confidence=0.8,
            page=2,
            details={"candidate_sum": candidate_sum, "total": total},
        ))

    # ── Rule 6: OCR confidence check ─────────────────────────────────────────
    avg_conf = (page1.overall_confidence + page2.overall_confidence) / 2
    if avg_conf < 0.7:
        anomalies.append(Anomaly(
            rule="LOW_OCR_CONFIDENCE",
            severity="MEDIUM",
            message=f"Low OCR confidence: {avg_conf:.1%}",
            confidence=1.0,
            page=1,
            details={"page1_conf": page1.overall_confidence, "page2_conf": page2.overall_confidence},
        ))

    return ValidationResult(
        valid=len(anomalies) == 0,
        anomalies=tuple(anomalies),
        anomaly_count=len(anomalies),
    )


def _votes_from_candidate(cand) -> int:
    """Extract vote count from CandidateVotes slots."""
    digits = []
    for slot in cand.slots:
        if slot.digit is not None:
            digits.append(str(slot.digit))
        else:
            digits.append('0')
    return int(''.join(digits)) if digits else 0


# ── Risk Scoring ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskScore:
    """Final risk classification for an E-14."""
    score       : float       # 0-100
    level       : str         # CRITICAL | HIGH | MEDIUM | LOW
    breakdown   : dict[str, float]
    anomaly_count: int
    anomaly_types: tuple[str, ...]


def calculate_risk_score(
    sig_result  : SignatureValidationResult,
    math_result : ValidationResult,
    ocr_confidence: float,
) -> RiskScore:
    """Calculate overall risk score combining all signals.

    Score breakdown:
      - Signature anomalies (0-50)
      - Mathematical anomalies (0-40)
      - OCR confidence (0-15)
    Total capped at 100.
    """
    breakdown: dict[str, float] = {}

    # Signature contribution (up to 50)
    sig_score = signature_risk_score_component(sig_result)
    breakdown["signatures"] = sig_score

    # Mathematical anomalies contribution (up to 40)
    math_score = 0.0
    for anomaly in math_result.anomalies:
        weight = RISK_WEIGHTS.get(anomaly.rule, 5.0)
        math_score += weight
    math_score = min(math_score, 40.0)
    breakdown["mathematical"] = math_score

    # OCR confidence contribution (up to 15)
    ocr_score = max(0.0, (1.0 - ocr_confidence) * 15.0)
    breakdown["ocr_confidence"] = ocr_score

    total = min(100.0, sig_score + math_score + ocr_score)

    # Classification
    if total >= 80:
        level = "CRITICAL"
    elif total >= 50:
        level = "HIGH"
    elif total >= 20:
        level = "MEDIUM"
    else:
        level = "LOW"

    anomaly_types = tuple(set(a.rule for a in math_result.anomalies))
    if sig_result.overall_status != "COMPLETE":
        anomaly_types = ("signature_" + sig_result.overall_status.lower(),) + anomaly_types

    return RiskScore(
        score=round(total, 2),
        level=level,
        breakdown={k: round(v, 2) for k, v in breakdown.items()},
        anomaly_count=math_result.anomaly_count + (0 if sig_result.overall_status == "COMPLETE" else 1),
        anomaly_types=anomaly_types,
    )


def signature_risk_score_component(sig: SignatureValidationResult) -> float:
    """Signature contribution to risk score (0-50)."""
    if sig.overall_status == "COMPLETE":
        return 0.0
    if sig.overall_status == "EMPTY":
        return 50.0
    # INCOMPLETE
    empty = sum(1 for b in sig.boxes if b.status == "EMPTY")
    indeterminate = sum(1 for b in sig.boxes if b.status == "INDETERMINATE")
    return empty * 15.0 + indeterminate * 5.0