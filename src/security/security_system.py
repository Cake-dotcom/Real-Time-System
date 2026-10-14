
from src.security.risk_engine import RiskEngine
from src.security.auth_policy import choose_auth_action
from src.scheduler.scheduler import schedule_tasks

engine = RiskEngine()


def evaluate_login(event):
    risk = engine.assess(event)
    action = choose_auth_action(
        risk["risk_level"],
        event["failed_attempts_last_5min"],
    )

    task = {
        "name": "Login security processing",
        "execution_time": 2,
        "risk_level": risk["risk_level"],
        "deadline": 6,
    }

    schedule_result = schedule_tasks([task])

    return {
        "risk": risk,
        "security_action": action,
        "schedule": schedule_result,
    }


if __name__ == "__main__":
    test_event = {
        "failed_attempts_last_5min": 35,
        "login_attempts_last_1min": 25,
        "unique_accounts_targeted": 2,
        "time_since_last_login_seconds": 20,
        "unusual_login_time": 1,
        "new_ip_for_user": 1,
        "successful_login": 0,
    }

    print(evaluate_login(test_event))
