import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _call(prompt, max_tokens=800):
    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def analyze_answer(question, answer, category):
    """
    Given a psych question + the user's answer, extract cognitive signals.
    Returns a dict that db.py functions can consume directly.

    What we extract:
    - beliefs: things they claim to think or value (stated self)
    - patterns: behavioral habits visible in HOW they answered (stated self but inferred)
    - topics: subject areas they engaged with
    - emotions: emotional states revealed in the answer
    - contradictions: internal conflicts within this single answer
    """
    prompt = f"""You are building a cognitive profile. Analyze this psychological question and answer.

Category: {category}
Question: {question}
Answer: {answer}

Extract cognitive signals. Return ONLY a JSON object:
{{
  "beliefs": [
    {{"text": "specific belief this reveals", "confidence": 0.0-1.0}}
  ],
  "patterns": [
    "a recurring behavioral or thinking habit visible in HOW they answered, not just WHAT they said"
  ],
  "topics": ["subject areas they engaged with"],
  "emotions": [
    {{"name": "emotion name", "trigger": "what seems to trigger it or null"}}
  ],
  "contradictions": [
    "any internal conflict within this single answer — e.g. they say they value X but describe doing the opposite"
  ],
  "summary": "one sentence — the single most revealing cognitive insight from this answer"
}}

Rules:
- beliefs should be specific, not generic. Not "values honesty" but "believes honesty matters more than avoiding conflict even in close relationships"
- patterns are about HOW they think, not WHAT they think. Look at: did they give examples or stay abstract? Did they hedge or commit? Did they turn it back on themselves?
- contradictions only if genuinely present — leave array empty if not
- Return ONLY valid JSON, no markdown"""

    return _parse_json(_call(prompt))


def generate_checkin_questions(profile_text):
    """
    Given the current profile, generates 3 targeted questions.
    Each question probes a different gap in the graph.
    """
    prompt = f"""You are building a cognitive profile of a person over time.

Here is what you already know about them:
{profile_text}

Generate exactly 3 short check-in questions for today's session.

Question 1: situational — something that happened today or recently (a decision, interaction, reaction)
Question 2: probe a gap — look at the profile above and ask about something underrepresented or unclear
Question 3: go deeper — pick one belief or pattern already in the profile and probe one level further

Rules:
- Casual, conversational tone — not clinical
- One sentence each
- Do NOT repeat topics already well-covered in the profile
- Return ONLY a JSON array of 3 strings, no markdown

Example format: ["question one", "question two", "question three"]"""

    return _parse_json(_call(prompt, max_tokens=300))


def ask_twin(user_id, question, profile_text, raw_answers):
    """
    The core twin function.
    Claude answers a new question AS the user, using:
    - their raw answers (actual words, voice, rhythm)
    - their structured profile (beliefs, patterns, contradictions)
    """

    # build a condensed version of what they actually said
    answers_block = ""
    for a in raw_answers:
        answers_block += f"Q: {a['question']}\nThey said: {a['answer']}\n\n"

    prompt = f"""You are roleplaying as the cognitive twin of {user_id}.
You ARE them. Speak in first person.

Here is what they actually said during their psychological assessment:
{answers_block}

Here is their cognitive profile (beliefs, patterns, contradictions across three selves):
{profile_text}

Now answer this question exactly as {user_id} would:
"{question}"

Rules:
- First person only — "I think...", "For me...", "Honestly..."
- Match their vocabulary and sentence rhythm from the actual answers above
- Reference their specific beliefs or contradictions where relevant
- Show internal conflict if the profile suggests it exists on this topic
- If the profile has no signal on this topic, say "honestly I'm not sure about this one" — never invent
- NO headers, NO bullet points, NO "in summary"
- Under 150 words — a real person thinking out loud, not a lecture
- If there's a contradiction in their profile relevant to this question, surface it: "part of me thinks X but I also..."
"""

    return _call(prompt, max_tokens=500)


def generate_insight(profile_text):
    """
    After a check-in, generates one non-obvious insight about the user
    based on their full profile. Not a summary — an interpretation.
    """
    prompt = f"""Based on this cognitive profile, write one short paragraph (3-4 sentences).

{profile_text}

Rules:
- Give a non-obvious interpretation — something the person might not see about themselves
- Focus on the gaps between their stated beliefs and behavioral patterns if any exist
- Be direct, not flattering
- Do NOT summarize the data — interpret it
- Plain prose, no headers or bullets"""

    return _call(prompt, max_tokens=250)


def detect_contradictions(old_profile_text, new_answer, question):
    """
    After storing a new answer, check if it conflicts
    with anything already in the profile.
    Called after each answer during assessment and check-ins.
    """
    prompt = f"""You are watching a cognitive profile being built over time.

Existing profile:
{old_profile_text}

New answer just given:
Question: {question}
Answer: {new_answer}

Does this new answer contradict anything in the existing profile?

Return ONLY a JSON object:
{{
  "has_contradiction": true or false,
  "contradictions": [
    {{
      "text": "describe the conflict clearly — what the profile says vs what this answer reveals",
      "self_a": "stated" or "behavioral" or "projected",
      "self_b": "stated" or "behavioral" or "projected",
      "confidence": 0.0-1.0
    }}
  ]
}}

Only flag real contradictions. If nothing conflicts, return has_contradiction: false and empty array.
Return ONLY valid JSON."""

    result = _parse_json(_call(prompt, max_tokens=400))
    return result if result.get("has_contradiction") else {"has_contradiction": False, "contradictions": []}
