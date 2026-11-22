
from .loan_eligibility import evaluate_loan_eligibility


class LoanDecision:
    AUTO_APPROVAL_CANDIDATE = "Auto-Approval Candidate"
    MANUAL_REVIEW = "Needs Manual Review"
    NOT_ELIGIBLE = "Not Eligible"


def evaluate_automatic_loan_decision(application):
    """
    Classify a loan application using predefined rules.

    This function does not approve the application,
    create a loan record, or release funds.
    """

    eligibility = evaluate_loan_eligibility(application)

    failed_checks = [
        check["details"]
        for check in eligibility["checks"]
        if not check["passed"]
    ]

    credit_score = application.credit_score
    risk_category = eligibility["risk_category"]
    recommended_rate = eligibility[
        "recommended_interest_rate"
    ]

    # Missing credit history needs manual review.
    if credit_score is None:
        return {
            "decision": LoanDecision.MANUAL_REVIEW,
            "eligibility": eligibility,
            "reasons": failed_checks + [
                "Credit history requires manual assessment."
            ],
        }

    # Failed eligibility requirements prevent auto-approval.
    if not eligibility["eligible"]:
        return {
            "decision": LoanDecision.NOT_ELIGIBLE,
            "eligibility": eligibility,
            "reasons": failed_checks,
        }

    # Eligible low-risk applications may qualify
    # for automatic approval.
    if (
        risk_category == "Low"
        and recommended_rate is not None
    ):
        return {
            "decision": LoanDecision.AUTO_APPROVAL_CANDIDATE,
            "eligibility": eligibility,
            "reasons": [
                "All eligibility requirements passed.",
                "Borrower is classified as Low risk.",
            ],
        }

    # Other applications require additional review.
    return {
        "decision": LoanDecision.MANUAL_REVIEW,
        "eligibility": eligibility,
        "reasons": [
            "Application requires additional risk review."
        ],
    }
