
import uuid
from decimal import Decimal


def simulate_payment(amount):
    """
    Simulates a payment provider response.
    This does not transfer real money.
    """

    if amount <= Decimal("0.00"):
        return {
            "status": "FAILED",
            "provider_reference": None,
            "message": "Invalid payment amount."
        }

    # Test-only failure scenario
    if amount == Decimal("13.37"):
        return {
            "status": "FAILED",
            "provider_reference": None,
            "message": "Simulated payment failed."
        }

    return {
        "status": "SUCCESS",
        "provider_reference": (
            "SIM-" + uuid.uuid4().hex[:12].upper()
        ),
        "message": "Simulated payment completed successfully."
    }
