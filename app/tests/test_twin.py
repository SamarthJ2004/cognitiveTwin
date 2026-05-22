"""
test_twin.py — Twin accuracy testing framework

Three test categories:
  1. Verifiable   — questions with a factually correct answer you can check
  2. Interpersonal — things only people close to you would know
  3. Novel        — new situations the twin has to reason through

After answering each twin response, YOU score it 1-5.
At the end: category scores, weak spots, what data is missing.

Run:
    python test_twin.py your_name
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import app.db as db
from app.data_analysis import analyze
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)
RESULTS_FILE = DATA_DIR / "test_results.json"

# ── test questions ─────────────────────────────────────────────────────────────

TESTS = [
    # ── Category 1: Verifiable ─────────────────────────────────────────────────
    # Right answer is checkable — you know the ground truth
    {
        "id": "v1",
        "category": "verifiable",
        "label": "Primary language",
        "question": "What programming languages do you actually use most, day to day?",
        "why": "Tests if behavioral data (GitHub, terminal) made it into the profile"
    },
    {
        "id": "v2",
        "category": "verifiable",
        "label": "Sleep pattern",
        "question": "Are you a morning person or a night person? What time do you usually sleep and wake up?",
        "why": "Tests if sleep/wake data was captured and reflected"
    },
    {
        "id": "v3",
        "category": "verifiable",
        "label": "Work style",
        "question": "When you sit down to work on something technical, how long can you stay focused before you need a break?",
        "why": "Tests if app switching / attention data came through"
    },
    {
        "id": "v4",
        "category": "verifiable",
        "label": "Music while working",
        "question": "Do you listen to music while working? What kind?",
        "why": "Tests if music daemon data is reflected"
    },
    {
        "id": "v5",
        "category": "verifiable",
        "label": "Problem solving",
        "question": "When you hit a bug you can't figure out, what do you actually do? Walk me through it.",
        "why": "Tests terminal history + stated patterns together"
    },

    # ── Category 2: Interpersonal ──────────────────────────────────────────────
    # Things a close friend would know — tests depth of psychological profile
    {
        "id": "i1",
        "category": "interpersonal",
        "label": "Procrastination pattern",
        "question": "What does your procrastination actually look like? What do you do instead of the thing you should be doing?",
        "why": "Tests if stated self + behavioral self contradiction about productivity came through"
    },
    {
        "id": "i2",
        "category": "interpersonal",
        "label": "Conflict response",
        "question": "Someone criticises something you built or wrote. What happens inside you in that moment?",
        "why": "Tests conflict avoidance pattern + emotional baseline"
    },
    {
        "id": "i3",
        "category": "interpersonal",
        "label": "Stress behavior",
        "question": "When you're really stressed, what does that look like from the outside? What do people around you notice?",
        "why": "Tests emotional pattern + self-awareness accuracy"
    },
    {
        "id": "i4",
        "category": "interpersonal",
        "label": "Decision making",
        "question": "You need to make an important decision but you don't have all the information yet. What do you do?",
        "why": "Tests stated belief about thorough preparation vs behavioral patterns"
    },
    {
        "id": "i5",
        "category": "interpersonal",
        "label": "Relationship with failure",
        "question": "Tell me about the last time something you worked on failed. How did you handle it?",
        "why": "Tests emotional pattern around failure + resilience beliefs"
    },

    # ── Category 3: Novel situations ───────────────────────────────────────────
    # The real test — situations not in the training data
    {
        "id": "n1",
        "category": "novel",
        "label": "Career dilemma",
        "question": "Two internship offers: one at a big company, safe, decent pay. One at a 3-person startup, risky, more responsibility. Which do you take and why?",
        "why": "Tests risk tolerance + career beliefs + stated vs actual values"
    },
    {
        "id": "n2",
        "category": "novel",
        "label": "Social obligation",
        "question": "Your friend asks you to come to a social event you really don't want to attend. How do you handle it?",
        "why": "Tests conflict avoidance + loyalty vs preference contradiction"
    },
    {
        "id": "n3",
        "category": "novel",
        "label": "Feedback delivery",
        "question": "A friend shows you a project they worked hard on and asks for honest feedback. It has serious problems. What do you say?",
        "why": "Tests honesty vs harmony tension — one of the key contradictions"
    },
    {
        "id": "n4",
        "category": "novel",
        "label": "Learning choice",
        "question": "You have 3 free months. No obligations. What do you actually do with that time?",
        "why": "Tests stated interests vs behavioral interests gap"
    },
    {
        "id": "n5",
        "category": "novel",
        "label": "Identity under pressure",
        "question": "Someone smart tells you that a core belief you hold is completely wrong and makes a good argument. What happens?",
        "why": "Tests the 'initial resistance then openness' pattern from stated profile"
    },
]


# ── display ────────────────────────────────────────────────────────────────────

def header(text):
    print(f"\n{'─' * 56}")
    print(f"  {text}")
    print(f"{'─' * 56}")


def dim(text):
    print(f"  \033[90m{text}\033[0m")


def bold(text):
    print(f"  \033[1m{text}\033[0m")


# ── scoring ────────────────────────────────────────────────────────────────────

SCORE_LABELS = {
    1: "completely wrong — doesn't sound like me at all",
    2: "mostly wrong — got some surface things right",
    3: "partial — right direction, missing important nuance",
    4: "mostly right — sounds like me, minor gaps",
    5: "accurate — I would actually say something like this",
}


def get_score():
    while True:
        print("\n  How accurate was that response?")
        for k, v in SCORE_LABELS.items():
            print(f"  \033[90m{k}\033[0m — {v}")
        raw = input("\n  Score (1-5): ").strip()
        try:
            score = int(raw)
            if 1 <= score <= 5:
                return score
        except ValueError:
            pass
        print("  Enter a number 1-5")


def get_notes():
    note = input("  What was wrong / what did it miss? (Enter to skip): ").strip()
    return note if note else None


# ── results analysis ───────────────────────────────────────────────────────────

def analyze_results(results):
    """
    Break down scores by category and surface specific weak points.
    """
    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    header("Test Results")

    overall = sum(r["score"] for r in results) / len(results)
    print(f"\n  Overall accuracy: \033[1m{overall:.1f}/5\033[0m  ({len(results)} questions)\n")

    cat_labels = {
        "verifiable": "Verifiable (behavioral data accuracy)",
        "interpersonal": "Interpersonal (psychological depth)",
        "novel": "Novel situations (reasoning quality)",
    }

    cat_scores = {}
    for cat, cat_results in by_category.items():
        avg = sum(r["score"] for r in cat_results) / len(cat_results)
        cat_scores[cat] = avg
        bar = "█" * int(avg) + "░" * (5 - int(avg))
        label = cat_labels.get(cat, cat)
        print(f"  {label}")
        print(f"  {bar}  {avg:.1f}/5\n")

    # weak spots — questions scoring 1 or 2
    weak = [r for r in results if r["score"] <= 2]
    if weak:
        print("\n  \033[91mWeak spots (scored 1-2):\033[0m")
        for r in weak:
            print(f"  ✗ [{r['label']}] — {r.get('notes', 'no notes')}")
            print(f"    → \033[90m{r['why']}\033[0m")

    # what the scores tell us about missing data
    print("\n  \033[93mDiagnosis:\033[0m")

    if cat_scores.get("verifiable", 5) < 3:
        print("  → Behavioral data not making it into the twin.")
        print("    Run collect.py and collect_api.py, check neo4j has behavioral nodes.")

    if cat_scores.get("interpersonal", 5) < 3:
        print("  → Psychological profile is shallow.")
        print("    Do more check-ins. The profile needs more answer depth.")

    if cat_scores.get("novel", 5) < 3:
        print("  → Twin is not reasoning from your patterns, just summarising them.")
        print("    The ask_twin prompt needs work, or CoreProfile is needed.")

    if overall >= 4:
        print("  → Strong baseline. Ready to share with someone who knows you.")
    elif overall >= 3:
        print("  → Decent but not convincing yet. More data + check-ins needed.")
    else:
        print("  → Needs significant improvement before sharing.")

    return overall, cat_scores


# ── save results ───────────────────────────────────────────────────────────────

def save_results(user_id, results, overall, cat_scores):
    """Save test run to file so you can track improvement over time."""
    existing = []
    if RESULTS_FILE.exists():
        try:
            existing = json.loads(RESULTS_FILE.read_text())
        except Exception:
            pass

    run = {
        "user_id": user_id,
        "date": datetime.now().isoformat(),
        "overall": overall,
        "by_category": cat_scores,
        "results": results,
    }
    existing.append(run)
    RESULTS_FILE.write_text(json.dumps(existing, indent=2))

    # show improvement over time if multiple runs exist
    if len(existing) > 1:
        prev = existing[-2]["overall"]
        diff = overall - prev
        direction = "▲" if diff > 0 else "▼" if diff < 0 else "="
        print(f"\n  vs last run: {direction} {abs(diff):.1f} "
              f"({existing[-2]['date'][:10]})")


# ── main ───────────────────────────────────────────────────────────────────────

def run_tests(user_id, category_filter=None):
    header(f"Twin Accuracy Test — {user_id}")
    dim("The twin will answer each question. You score each response 1-5.")
    dim("Be honest — this is diagnostic, not flattering.\n")

    # load profile
    with db.driver.session() as session:
        profile = db.get_profile(session, user_id)
        raw_answers = db.get_raw_answers(session, user_id)

        if not profile or not profile["beliefs"]:
            print("  No profile yet. Run the assessment first.\n")
            return

        profile_text = db.format_profile(profile)

        # filter tests if requested
        tests = TESTS
        if category_filter:
            tests = [t for t in TESTS if t["category"] == category_filter]

        results = []

        for i, test in enumerate(tests, 1):
            cat_display = {
                "verifiable": "\033[94mVERIFIABLE\033[0m",
                "interpersonal": "\033[93mINTERPERSONAL\033[0m",
                "novel": "\033[91mNOVEL\033[0m",
            }.get(test["category"], test["category"])

            print(f"\n{'─' * 56}")
            print(f"  [{i}/{len(tests)}] {cat_display}  ·  {test['label']}")
            print(f"  \033[90mTesting: {test['why']}\033[0m")
            print(f"\n  Q: {test['question']}\n")

            input("  Press Enter to get the twin's response...")

            print(f"\n  \033[90mThinking...\033[0m\n")

            try:
                response = analyze.ask_twin(
                    user_id,
                    test["question"],
                    profile_text,
                    raw_answers,
                )
                print(f"  \033[93m{user_id} (twin):\033[0m")
                # indent each line of response
                for line in response.strip().split("\n"):
                    print(f"  {line}")

            except Exception as e:
                print(f"  Error: {e}")
                continue

            score = get_score()
            notes = get_notes()

            results.append({
                "id": test["id"],
                "category": test["category"],
                "label": test["label"],
                "question": test["question"],
                "why": test["why"],
                "response": response,
                "score": score,
                "notes": notes,
                "date": datetime.now().isoformat(),
            })

            # running average after each answer
            running_avg = sum(r["score"] for r in results) / len(results)
            dim(f"Running average: {running_avg:.1f}/5")

        # final analysis
        if results:
            overall, cat_scores = analyze_results(results)
            save_results(user_id, results, overall, cat_scores)
            print(f"\n  Results saved to: {RESULTS_FILE}\n")


def show_history(user_id):
    """Show score history across test runs."""
    if not RESULTS_FILE.exists():
        print("  No test history yet.\n")
        return

    runs = json.loads(RESULTS_FILE.read_text())
    user_runs = [r for r in runs if r.get("user_id") == user_id]

    if not user_runs:
        print(f"  No test history for {user_id}.\n")
        return

    header(f"Test History — {user_id}")
    for run in user_runs:
        date = run["date"][:10]
        overall = run["overall"]
        bar = "█" * int(overall) + "░" * (5 - int(overall))
        print(f"  {date}  {bar}  {overall:.1f}/5")
    print()


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else input("  Your name: ").strip()
    if not user_id:
        sys.exit(1)

    print("\n  1. Run full test (15 questions)")
    print("  2. Run verifiable only (5 questions — quick)")
    print("  3. Run interpersonal only (5 questions)")
    print("  4. Run novel situations only (5 questions)")
    print("  5. View score history")

    choice = input("\n> ").strip()

    if choice == "1":
        run_tests(user_id)
    elif choice == "2":
        run_tests(user_id, category_filter="verifiable")
    elif choice == "3":
        run_tests(user_id, category_filter="interpersonal")
    elif choice == "4":
        run_tests(user_id, category_filter="novel")
    elif choice == "5":
        show_history(user_id)
    else:
        run_tests(user_id)

    db.driver.close()
