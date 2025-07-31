from pathlib import Path
import json
from app.supplement_engine import generate_supplement_plan
from app.generate_mock_users import create_mock_user  # adjust import if needed

def run_mock_test():
    user = create_mock_user()
    output = generate_supplement_plan(user, structured_output=True)

    print(f"Supplement Recommendations for user {user.user_id}:\n")

    for rec in output.recommendations:
        print(f"- {rec.name}: {rec.dosage} {rec.unit}")
        print(f"  Reason: {rec.reason}")
        print(f"  Explanation (concise): {rec.explanation}")

        if hasattr(rec, "structured_explanation"):
            print("  Explanation (structured):")
            print(json.dumps(rec.structured_explanation, indent=4))

        if rec.validation_flags:
            print(f"  тЪая╕П Warnings: {', '.join(rec.validation_flags)}")

        if rec.contraindications:
            print(f"  ЁЯЪл Contraindications: {', '.join(rec.contraindications)}")

        print()

if __name__ == "__main__":
    run_mock_test()