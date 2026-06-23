"""MVP Pipeline — Mathematical validation + risk scoring."""

from dataclasses import dataclass

from .ocr import OcrResult


@dataclass(frozen=True)
class Anomaly:
    rule: str
    severity: str    # CRITICAL | HIGH | MEDIUM | LOW
    message: str
    confidence: float
    page: int
    details: dict | None = None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    anomalies: tuple[Anomaly, ...]
    anomaly_count: int


RISK_WEIGHTS = {
    "SUM_MISMATCH": 40.0,
    "NEGATIVE_VOTES": 40.0,
    "EXCEEDS_3_DIGITS": 15.0,
    "OVERVOTE": 35.0,
    "UNDERVOTE": 20.0,
    "LOW_OCR_CONFIDENCE": 15.0,
    "signature_empty": 50.0,
    "signature_incomplete": 30.0,
}


@dataclass(frozen=True)
class RiskScore:
    score: float       # 0-100
    level: str         # CRITICAL | HIGH | MEDIUM | LOW
    breakdown: dict
    anomaly_count: int


def _votes_from_candidate(cand) -> int:
    digits = [str(s.digit) if s.digit is not None else '0' for s in cand.slots]
    return int(''.join(digits)) if digits else 0


def validate_mathematics(page1: OcrResult, page2: OcrResult) -> ValidationResult:
    anomalies = []

    # Gather all votes
    votes_by_cand = {}
    for cand in page1.candidates:
        votes_by_cand[cand.candidate_number] = _votes_from_candidate(cand)
    for cand in page2.candidates:
        votes_by_cand[cand.candidate_number] = _votes_from_candidate(cand)

    candidate_sum = sum(votes_by_cand.values())

    # Summary
    if page2.summary:
        blank = page2.summary.blank_votes
        null  = page2.summary.null_votes
        unmarked = page2.summary.unmarked_votes
        total = page2.summary.total_votes
    else:
        blank = null = unmarked = total = 0

    # Rule 1: Sum check
    computed = candidate_sum + blank + null + unmarked
    if total != computed:
        anomalies.append(Anomaly(
            rule="SUM_MISMATCH",
            severity="CRITICAL",
            message=f"Total declared ({total}) != computed ({computed}), diff={abs(total - computed)}",
            confidence=0.95,
            page=2,
            details={"declared_total": total, "computed_total": computed},
        ))

    # Rule 2: Non-negative
    for cnum, votes in votes_by_cand.items():
        if votes < 0:
            anomalies.append(Anomaly(
                rule="NEGATIVE_VOTES",
                severity="CRITICAL",
                message=f"Candidate {cnum} has negative votes: {votes}",
                confidence=1.0,
                page=1 if cnum <= 7 else 2,
                details={"candidate": cnum, "votes": votes},
            ))

    if blank < 0 or null < 0 or unmarked < 0:
        anomalies.append(Anomaly(
            rule="NEGATIVE_SUMMARY",
            severity="CRITICAL",
            message=f"Negative summary: blank={blank}, null={null}, unmarked={unmarked}",
            confidence=1.0,
            page=2,
        ))

    # Rule 3: 3-digit max
    for cnum, votes in votes_by_cand.items():
        if votes > 999:
            anomalies.append(Anomaly(
                rule="EXCEEDS_3_DIGITS",
                severity="HIGH",
                message=f"Candidate {cnum} has {votes} votes (exceeds 999)",
                confidence=0.9,
                page=1 if cnum <= 7 else 2,
                details={"candidate": cnum, "votes": votes},
            ))

    # Rule 4: Undervote
    if total > 0 and candidate_sum > total:
        anomalies.append(Anomaly(
            rule="UNDERVOTE",
            severity="MEDIUM",
            message=f"Candidate sum ({candidate_sum}) > total ({total})",
            confidence=0.8,
            page=2,
            details={"candidate_sum": candidate_sum, "total": total},
        ))

    # Rule 5: Low OCR confidence
    avg_conf = (page1.overall_confidence + page2.overall_confidence) / 2
    if avg_conf < 0.6:
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


def calculate_risk_score(sig_result, math_result: ValidationResult, ocr_confidence: float) -> RiskScore:
    breakdown = {}

    # Signature contribution (up to 50)
    if sig_result.overall_status == "COMPLETE":
        sig_score = 0.0
    elif sig_result.overall_status == "EMPTY":
        sig_score = 50.0
    else:
        empty = sum(1 for b in sig_result.boxes if b.status == "EMPTY")
        indet = sum(1 for b in sig_result.boxes if b.status == "INDETERMINATE")
        sig_score = empty * 15.0 + indet * 5.0
    breakdown["signatures"] = sig_score

    # Mathematical anomalies (up to 40)
    math_score = sum(RISK_WEIGHTS.get(a.rule, 5.0) for a in math_result.anomalies)
    math_score = min(math_score, 40.0)
    breakdown["mathematical"] = math_score

    # OCR confidence (up to 15)
    ocr_score = max(0.0, (1.0 - ocr_confidence) * 15.0)
    breakdown["ocr_confidence"] = ocr_score

    total = min(100.0, sig_score + math_score + ocr_score)

    if total >= 80:
        level = "CRITICAL"
    elif total >= 50:
        level = "HIGH"
    elif total >= 20:
        level = "MEDIUM"
    else:
        level = "LOW"

    return RiskScore(
        score=round(total, 2),
        level=level,
        breakdown={k: round(v, 2) for k, v in breakdown.items()},
        anomaly_count=math_result.anomaly_count + (0 if sig_result.overall_status == "COMPLETE" else 1),
    )