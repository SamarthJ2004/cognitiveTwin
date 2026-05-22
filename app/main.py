from app.questions import FALLBACK_CHECKIN, QUESTIONS
from datetime import datetime
import sys
import random
from app.data_analysis import analyze
import app.db as db

TODAY = datetime.now().strftime("%Y-%m-%d")


def header(text):
    print(f"\n{'─' * 52}")
    print(f"  {text}")
    print(f"{'─' * 52}")


def dim(text): print(f"  \033[90m{text}\033[0m")
def ok(text): print(f"  \033[92m✓\033[0m  {text}")
def warn(text): print(f"  \033[93m⚡\033[0m {text}")
def err(text): print(f"  \033[91m✗\033[0m  {text}")


def show_question(index, total, q):
    print(f"\n\033[94m[{index}/{total}]\033[0m  {q['question']}")
    if q.get("hint"):
        dim(q["hint"])


def run_assessment(session, user_id):
    header("Full Assessment")
    dim("Answer honestly — not how you think you should, but how you actually feel.")
    dim("Type 'skip' to skip a question.\n")

    total = len(QUESTIONS)

    for i, q in enumerate(QUESTIONS, 1):
        show_question(i, total, q)
        answer = input("> ")

        if not answer or answer.lower() == "skip":
            dim("Skipped.")
            continue

        dim("Analyzing...")

        try:
            db.save_answer(session, user_id, q["id"],
                           q["question"], answer, q["category"])

            signals = analyze.analyze_answer(
                q["question"], answer, q["category"])

            for b in signals.get("beliefs", []):
                db.save_belief(session, user_id,
                               text=b["text"],
                               self_type="stated",
                               confidence=b.get("confidence", 0.7),
                               date=TODAY)

            for p in signals.get("patterns", []):
                db.save_pattern(session, user_id,
                                text=p,
                                self_type="stated",
                                source=q["id"],
                                date=TODAY)

            for t in signals.get("topics", []):
                db.save_topic(session, user_id,
                              name=t,
                              self_type="stated",
                              date=TODAY)

            for e in signals.get("emotions", []):
                db.save_emotion(session, user_id,
                                name=e["name"],
                                self_type="stated",
                                trigger=e.get("trigger"),
                                date=TODAY)

            for c in signals.get("contradictions", []):
                db.save_contradiction(session, user_id,
                                      text=c,
                                      self_a="stated",
                                      self_b="stated",
                                      date=TODAY)

            profile = db.get_profile(session, user_id)
            if profile:
                profile_text = db.format_profile(profile)
                cross = analyze.detect_contradictions(
                    profile_text, answer, q["question"])
                for c in cross.get("contradictions", []):
                    db.save_contradiction(session, user_id,
                                          text=c["text"],
                                          self_a=c.get("self_a", "stated"),
                                          self_b=c.get("self_b", "stated"),
                                          confidence=c.get("confidence", 0.6),
                                          date=TODAY)

            ok(signals.get("summary", "Stored."))

        except Exception as e:
            err(f"Could not analyze: {e}")

    header("Assessment complete")
    dim("Your cognitive profile has been built.")
    dim("Try 'Daily check-in' or 'Ask your twin' next.\n")


def run_checkin(session, user_id):
    profile = db.get_profile(session, user_id)
    if not profile or not profile["beliefs"]:
        dim("Run the full assessment first before check-ins.\n")
        return

    header("Daily Check-in")
    dim("3 quick questions based on your profile. Answer naturally.\n")

    profile_text = db.format_profile(profile)
    dim("Generating today's questions...")

    try:
        questions = analyze.generate_checkin_questions(profile_text)
    except Exception:
        questions = random.sample(FALLBACK_CHECKIN, 3)

    for i, question in enumerate(questions, 1):
        print(f"\n\033[94m[{i}/3]\033[0m  {question}")
        answer = input("> ")

        if not answer or answer.lower() == "skip":
            dim("Skipped.")
            continue

        dim("Storing...")

        try:
            q_id = f"checkin_{TODAY}_{i}"
            db.save_answer(session, user_id, q_id, question, answer, "checkin")

            signals = analyze.analyze_answer(question, answer, "checkin")

            for b in signals.get("beliefs", []):
                db.save_belief(session, user_id, b["text"], "stated",
                               b.get("confidence", 0.6), TODAY)
            for p in signals.get("patterns", []):
                db.save_pattern(session, user_id, p, "stated", q_id, TODAY)
            for t in signals.get("topics", []):
                db.save_topic(session, user_id, t, "stated", TODAY)
            for e in signals.get("emotions", []):
                db.save_emotion(session, user_id, e["name"], "stated",
                                e.get("trigger"), TODAY)

            # contradiction check against full profile
            cross = analyze.detect_contradictions(
                profile_text, answer, question)
            for c in cross.get("contradictions", []):
                db.save_contradiction(session, user_id,
                                      text=c["text"],
                                      self_a=c.get("self_a", "stated"),
                                      self_b=c.get("self_b", "stated"),
                                      confidence=c.get("confidence", 0.6),
                                      date=TODAY)
            ok(signals.get("summary", "Stored."))

        except Exception as e:
            err(f"Could not store: {e}")


def run_twin_query(session, user_id):
    profile = db.get_profile(session, user_id)
    if not profile or not profile["beliefs"]:
        dim("No profile yet. Run the assessment first.\n")
        return

    question = input("> What do you want to ask your twin?\n")
    if not question:
        return

    dim("Thinking as you...")

    try:
        profile_text = db.format_profile(profile)
        raw_answers = db.get_raw_answers(session, user_id)
        response = analyze.ask_twin(
            user_id, question, profile_text, raw_answers)

        print(f"\n\033[93m{user_id}:\033[0m")
        print(f"  {response}\n")
    except Exception as e:
        err(f"Twin query failed: {e}")


def view_profile(session, user_id):
    profile = db.get_profile(session, user_id)
    if not profile or not any(profile.values()):
        dim("No profile yet.\n")
        return

    header(f"Profile — {user_id}")
    print(db.format_profile(profile))

    # surface contradictions prominently if any
    if profile["contradictions"]:
        print(f"\n  \033[91m{len(profile['contradictions'])
                             } contradiction(s) detected\033[0m")
        for c in profile["contradictions"]:
            warn(c["text"])
    print()


def main():
    header("CognitiveTwin")
    user_id = input("User enter your name: ").strip()
    if not user_id:
        print("  Name required.")
        sys.exit(1)

    print(f"\n  Hello, {user_id}.")

    with db.driver.session() as session:
        db.ensure_user(session, user_id)

        while True:
            print("\n  1.  Full assessment")
            print("  2.  Daily check-in")
            print("  3.  Ask your twin")
            print("  4.  View profile")
            print("  5.  Exit")

            choice = input("User enter your choice: ").strip()

            if choice == "1":
                run_assessment(session, user_id)
            elif choice == "2":
                run_checkin(session, user_id)
            elif choice == "3":
                run_twin_query(session, user_id)
            elif choice == "4":
                view_profile(session, user_id)
            elif choice == "5":
                print("\n  Goodbye.\n")
                break

    db.driver.close()


if __name__ == "__main__":
    main()
