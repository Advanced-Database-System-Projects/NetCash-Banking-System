
import uuid
import random
from decimal import Decimal


def simulate_payment(amount):
    """
    Simulates a payment provider response.
    This does not transfer real money.

    Success probability: 80%
    Failure probability: 20%
    """

    amount = Decimal(str(amount))

    if not amount.is_finite() or amount <= Decimal("0.00"):
        return {
            "status": "FAILED",
            "provider_reference": None,
            "message": "Invalid payment amount."
        }

    # Automatically generate payment result
    payment_successful = True
    #False
    #random.random() < 0.80

    if not payment_successful:
        return {
            "status": "FAILED",
            "provider_reference": None,
            "message": "Simulated payment failed. Please try again."
        }

    return {
        "status": "SUCCESS",
        "provider_reference": (
            "SIM-" + uuid.uuid4().hex[:12].upper()
        ),
        "message": "Simulated payment completed successfully."
    }
