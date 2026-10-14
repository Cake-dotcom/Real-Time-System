
def choose_auth_action(risk_level, failed_attempts):
    # Prevent unlimited authentication challenges.
    if failed_attempts >= 10:
        return {
            "action": "temporary_block",
            "auth_level": 0,
            "message": "Too many failed attempts. Access temporarily blocked."
        }

    policies = {
        "low": {
            "action": "password",
            "auth_level": 1,
            "message": "Normal authentication."
        },
        "medium": {
            "action": "password_plus_mfa",
            "auth_level": 2,
            "message": "Additional verification required."
        },
        "high": {
            "action": "strong_mfa",
            "auth_level": 3,
            "message": "Strong multi-factor authentication required."
        },
        "critical": {
            "action": "throttle_and_strong_mfa",
            "auth_level": 3,
            "message": "High risk detected. Slow attempts and require strong MFA."
        }
    }

    return policies.get(risk_level, {
        "action": "temporary_block",
        "auth_level": 0,
        "message": "Unknown risk level. Access blocked for safety."
    })


if __name__ == "__main__":
    print(choose_auth_action("low", 0))
    print(choose_auth_action("high", 2))
    print(choose_auth_action("critical", 12))
