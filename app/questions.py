"""
Question bank for the stated-self assessment.
Drawn from: Big Five (IPIP), Need for Cognition, Moral Foundations,
            Cognitive Reflection Test, Need for Closure.

Each question is designed to reveal not just WHAT the person thinks
but HOW they think — their reasoning style, not just their opinions.

Categories map directly to graph node types:
- thinking_style  → Pattern nodes
- reasoning       → Pattern nodes + Belief nodes
- values          → Belief nodes
- emotional       → Emotion nodes
- self_concept    → Belief nodes (high confidence, self-reported)
"""

QUESTIONS = [

    # ── thinking style ─────────────────────────────────────────────────────────
    # Reveals: how they process information, deliberate vs intuitive
    {
        "id": "ts_1",
        "category": "thinking_style",
        "question": "When you face a complex problem, what do you actually do first — not what you think you should do, but what you actually do?",
    },
    {
        "id": "ts_2",
        "category": "thinking_style",
        "question": "Do you enjoy thinking through difficult problems even when they have no practical use for you? Be honest.",
    },
    {
        "id": "ts_3",
        "category": "thinking_style",
        "question": "When making a decision, do you prefer having all the information first — or do you act and adjust as you go?",
    },
    {
        "id": "ts_4",
        "category": "thinking_style",
        "question": "How long can you sit with an unanswered question before it bothers you?",
    },

    # ── reasoning (Cognitive Reflection Test style) ────────────────────────────
    # Reveals: intuitive vs analytical, how they handle being wrong
    {
        "id": "r_1",
        "category": "reasoning",
        "question": "A bat and a ball together cost $1.10. The bat costs $1 more than the ball. How much is the ball? Walk me through your thinking — not just the answer.",
        "hint": "(this is less about maths, more about how you reason)"
    },
    {
        "id": "r_2",
        "category": "reasoning",
        "question": "Think of a time you were completely confident about something and turned out to be wrong. What happened in your head when you realized it?",
    },
    {
        "id": "r_3",
        "category": "reasoning",
        "question": "When someone gives you a compelling argument against something you believe, what usually happens — do you update, resist, or something else?",
    },

    # ── values and moral foundations ───────────────────────────────────────────
    # Reveals: what the person actually weighs when making moral judgments
    {
        "id": "v_1",
        "category": "values",
        "question": "What matters more to you: that everyone follows the same rules, or that outcomes are fair — even if the rules have to bend? Give a real example if you can.",
    },
    {
        "id": "v_2",
        "category": "values",
        "question": "Think of something you consider morally wrong that doesn't directly harm anyone. What is it and why does it feel wrong?",
    },
    {
        "id": "v_3",
        "category": "values",
        "question": "When loyalty to someone you care about conflicts with doing what you think is right — what do you actually do? Not what you think you should do.",
    },
    {
        "id": "v_4",
        "category": "values",
        "question": "What's one belief you hold that most people around you would disagree with?",
    },

    # ── openness ───────────────────────────────────────────────────────────────
    # Reveals: tolerance for ambiguity, intellectual curiosity, change
    {
        "id": "o_1",
        "category": "openness",
        "question": "Have you changed your mind about something important in the last two years? What shifted — was it new information, an experience, or something else?",
    },
    {
        "id": "o_2",
        "category": "openness",
        "question": "How do you feel about starting things that might not work out? Not the rational answer — the gut feeling.",
    },

    # ── emotional patterns ─────────────────────────────────────────────────────
    # Reveals: emotional regulation, self-awareness, recurring emotional states
    {
        "id": "e_1",
        "category": "emotional",
        "question": "When something goes badly — failure, rejection, loss — what does the first 24 hours look like internally? What's the loop in your head?",
    },
    {
        "id": "e_2",
        "category": "emotional",
        "question": "Is there a recurring feeling or worry that shows up across different parts of your life? Describe the pattern, not just one instance.",
    },
    {
        "id": "e_3",
        "category": "emotional",
        "question": "How comfortable are you with conflict — do you seek it, avoid it, or does it depend? What does it depend on?",
    },

    # ── self concept ───────────────────────────────────────────────────────────
    # Reveals: self-awareness, blind spots in their self-model
    {
        "id": "sc_1",
        "category": "self_concept",
        "question": "How do you think a close friend who is honest with you would describe the way you think — not your personality, specifically your thinking style?",
    },
    {
        "id": "sc_2",
        "category": "self_concept",
        "question": "What is a pattern in your own thinking or behavior that you have noticed but find hard to change?",
    },
    {
        "id": "sc_3",
        "category": "self_concept",
        "question": "What do you think you are wrong about right now — something you currently believe that future you might look back on and cringe at?",
    },
]


# ── checkin questions (fallback only) ──────────────────────────────────────────
# These are used only if Claude fails to generate dynamic ones.
# Normally generate_checkin_questions() in analyze.py creates personalized ones.

FALLBACK_CHECKIN = [
    "What was the most interesting decision you made today — big or small?",
    "Did anything today surprise you or go differently than you expected?",
    "What are you avoiding right now, and why?",
    "What did you spend time on today that felt genuinely useful?",
    "Did you change your mind about anything today?",
]
