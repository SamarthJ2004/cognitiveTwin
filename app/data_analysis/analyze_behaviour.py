"""
analyze_behavioral.py — Hierarchical behavioral analysis pipeline

5-stage pipeline:
  Stage 1 — Knowledge / Curiosity      (browser history)
  Stage 2 — Engineering / Workstyle    (zsh, github, music)
  Stage 3 — Productivity / Attention   (app switching, app usage, typing)
  Stage 4 — Lifestyle / Circadian      (sleep/wake, temporal patterns)
  Stage 5 — Meta Synthesis             (all domain outputs + stated profile)

Contradictions only happen at Stage 5.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-4o-mini"
MAX_TOKENS = 1000


def _call(prompt, max_tokens=MAX_TOKENS):
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _has(data, *keys):
    # Check if data_summary contains at least one of these keys.
    return any(k in data for k in keys)


# ── stage 1: knowledge / curiosity ────────────────────────────────────────────

def analyze_knowledge(data):
    """
    Input:  browser_titles
    Output: topics, learning_style, research_patterns, curiosity_traits
    """
    if not _has(data, "browser_titles"):
        return {}

    # frequency-sort titles if they're dicts, flatten if plain strings
    titles = data["browser_titles"]
    if titles and isinstance(titles[0], dict):
        # already frequency-sorted by collect.py
        title_block = "\n".join(
            f"  ({t['visits']}x) {t['title']}" for t in titles[:80]
        )
    else:
        title_block = "\n".join(f"  {t}" for t in titles[:80])

    prompt = f"""You are analyzing someone's browser history to understand their intellectual curiosity and learning patterns.

Browser page titles (with visit frequency where available):
{title_block}

Focus ONLY on what this reveals about HOW and WHAT they learn.
Return ONLY a JSON object:
{{
  "topics": ["specific subject areas — precise, not generic"],
  "learning_style": {{
    "depth_vs_breadth": "deep diver | broad scanner | mixed",
    "primary_mode": "reading | video | documentation | forums | mixed",
    "evidence": "one sentence citing specific titles that support this"
  }},
  "research_patterns": [
    "specific patterns in how they research — e.g. 'visits multiple StackOverflow threads on the same error suggesting trial-and-error debugging'"
  ],
  "curiosity_traits": [
    "notable traits — e.g. 'returns to same topics across sessions suggesting obsessive interest in X'"
  ],
  "obsessions": ["topics visited disproportionately often"]
}}

Rules:
- Use actual title examples to support claims
- Distinguish between work-related browsing and personal interest
- Return ONLY valid JSON"""

    return _call(prompt)


# ── stage 2: engineering / workstyle ──────────────────────────────────────────

def analyze_engineering(data):
    """
    Input:  terminal_commands, github
    Output: engineering_traits, workflow_patterns, execution_style, technical_depth_signals
    """
    if not _has(data, "terminal_commands", "github", "music"):
        return {}

    sections = []

    if "terminal_commands" in data:
        cmds = data["terminal_commands"]
        sections.append(f"Terminal commands (last {len(cmds)}):\n" +
                        "\n".join(f"  {c}" for c in cmds[-100:]))

    if "github" in data:
        gh = data["github"]
        sections.append(f"GitHub:\n{json.dumps(gh, indent=2)}")

    if "music" in data:
        music = data["music"]
        sections.append(f"Music:\n{json.dumps(music, indent=2)}")

    prompt = f"""You are analyzing someone's engineering behavior from their terminal history and GitHub activity.

{chr(10).join(sections)}

Focus ONLY on what this reveals about how they build and think as an engineer.
Return ONLY a JSON object:
{{
  "engineering_traits": [
    "specific traits with evidence — e.g. 'heavy git rebase usage suggests preference for clean commit history'"
  ],
  "workflow_patterns": [
    "specific workflow patterns — e.g. 'runs tests immediately after code changes' or 'long gaps between commits suggest batch working'"
  ],
  "execution_style": {{
    "builder_vs_learner": "builder | learner | mixed",
    "experimentation_level": "high | medium | low",
    "systems_area": "backend | frontend | infra | fullstack | data | mixed",
    "evidence": "one sentence citing specific commands or repos"
  }},
  "technical_depth_signals": [
    "signals of depth vs breadth in technical knowledge — cite specific tools or patterns"
  ]
}}

Rules:
- Use actual commands and repo names as evidence
- Distinguish exploratory commands (lots of --help, man pages) from expert usage
- Return ONLY valid JSON"""

    return _call(prompt)


# ── stage 3: productivity / attention ─────────────────────────────────────────

def analyze_productivity(data):
    """
    Input:  app_switching, app_usage, typing_patterns
    Output: focus_patterns, attention_traits, context_switching_profile, productivity_style
    """
    if not _has(data, "app_switching", "app_usage", "typing_patterns"):
        return {}

    sections = []
    if "app_switching" in data:
        sections.append(f"App switching:\n{json.dumps(data['app_switching'], indent=2)}")
    if "app_usage" in data:
        sections.append(f"App usage (time spent):\n{json.dumps(data['app_usage'], indent=2)}")
    if "typing_patterns" in data:
        sections.append(f"Typing patterns:\n{json.dumps(data['typing_patterns'], indent=2)}")

    prompt = f"""You are analyzing someone's focus and productivity patterns from their app usage, switching behavior, and typing data.

{chr(10).join(sections)}

Focus ONLY on attention quality, focus depth, and working style.
Return ONLY a JSON object:
{{
  "focus_patterns": [
    "specific patterns — e.g. 'average app session of 45s suggests inability to maintain focus' or 'VS Code sessions average 20min = genuine deep work'"
  ],
  "attention_traits": [
    "traits with evidence — e.g. 'high correction rate (18%) combined with fast WPM suggests impulsive typing style'"
  ],
  "context_switching_profile": {{
    "fragmentation_level": "high | medium | low",
    "peak_focus_hours": "hours where switching frequency drops",
    "worst_fragmentation_hours": "hours with most switches",
    "evidence": "cite specific numbers from the data"
  }},
  "productivity_style": {{
    "primary_mode": "deep work | reactive | mixed",
    "flow_state_evidence": "whether the data shows flow-state behavior or not",
    "distraction_pattern": "what they switch to when distracted"
  }}
}}

Return ONLY valid JSON"""

    return _call(prompt)


# ── stage 4: lifestyle / circadian ────────────────────────────────────────────

def analyze_lifestyle(data):
    """
    Input:  sleep_wake, + temporal signals from app_switching/typing
    Output: chronotype, stability_patterns, energy_cycles, lifestyle_traits
    """
    if not _has(data, "sleep_wake"):
        return {}

    sections = [f"Sleep/wake data:\n{json.dumps(data['sleep_wake'], indent=2)}"]

    # pull temporal signals from other datasets if available
    if "app_switching" in data and "switches_by_hour" in data["app_switching"]:
        sections.append(
            f"App activity by hour: {json.dumps(data['app_switching']['switches_by_hour'], indent=2)}"
        )

    prompt = f"""You are analyzing someone's lifestyle and circadian patterns.

{chr(10).join(sections)}

Focus ONLY on temporal behavior, energy rhythms, and lifestyle stability.
Return ONLY a JSON object:
{{
  "chronotype": "night owl | early riser | average | irregular",
  "stability_patterns": [
    "e.g. 'sleep time varies by 2+ hours — irregular schedule likely indicates reactive lifestyle or poor sleep hygiene'"
  ],
  "energy_cycles": [
    "e.g. 'peak activity window 22:00-01:00 based on app switching data — nocturnal productivity pattern'"
  ],
  "lifestyle_traits": [
    "higher-order traits — e.g. 'consistent late sleep + irregular wake = low sleep discipline despite potentially high cognitive output'"
  ],
  "burnout_signals": [
    "any signals of overwork, sleep deprivation, or unsustainable patterns — or empty array if none"
  ]
}}

Return ONLY valid JSON"""

    return _call(prompt)


# ── stage 5: meta synthesis ────────────────────────────────────────────────────

def synthesize(domain_outputs, stated_profile_text):
    """
    Input: structured outputs from stages 1-4 + stated profile
    Output: beliefs, contradictions, meta_patterns, summary
    """
    domain_block = json.dumps(
        {k: v for k, v in domain_outputs.items() if v},
        indent=2
    )

    prompt = f"""You are synthesizing a person's cognitive identity from domain behavioral analyses and their stated self-profile.

STATED PROFILE (what they say about themselves):
{stated_profile_text}

BEHAVIORAL DOMAIN ANALYSES (what their behavior reveals):
{domain_block}

Your job:
1. Find behavioral beliefs — what their actions imply about their worldview
2. Find contradictions — ONLY between stated profile and behavioral findings
3. Find meta-patterns — higher-order traits visible across multiple domains
4. Write a behavioral narrative — who is this person based on what they DO

Return ONLY a JSON object:
{{
  "beliefs": [
    {{
      "text": "a belief their behavior implies — specific, not generic",
      "confidence": 0.0-1.0,
      "evidence": "which domain analysis supports this"
    }}
  ],
  "patterns": [
    "cross-domain behavioral pattern — something visible in 2+ domain analyses"
  ],
  "topics": ["subject areas they actually engage with — from knowledge analysis"],
  "emotions": [
    {{
      "name": "inferred emotional state",
      "trigger": "what behavioral pattern correlates with it"
    }}
  ],
  "contradictions": [
    {{
      "text": "specific conflict between stated profile and behavioral finding — name both sides",
      "self_a": "stated",
      "self_b": "behavioral",
      "confidence": 0.0-1.0
    }}
  ],
  "meta_patterns": [
    "higher-order trait visible across multiple behavioral domains"
  ],
  "summary": "3 sentences — who this person is based purely on their behavior, what they say vs what they do, and the most important non-obvious insight"
}}

Rules:
- Contradictions ONLY between stated profile and behavioral evidence — not between domains
- Use actual evidence from domain analyses, not generic statements
- Meta-patterns must appear in at least 2 domains
- Return ONLY valid JSON"""

    return _call(prompt, max_tokens=1500)


def run_pipeline(data_summary, stated_profile_text):
    print("    stage 1 — knowledge / curiosity...", end=" ", flush=True)
    knowledge = analyze_knowledge(data_summary)
    print("✓" if knowledge else "–")

    print("    stage 2 — engineering / workstyle...", end=" ", flush=True)
    engineering = analyze_engineering(data_summary)
    print("✓" if engineering else "–")

    print("    stage 3 — productivity / attention...", end=" ", flush=True)
    productivity = analyze_productivity(data_summary)
    print("✓" if productivity else "–")

    print("    stage 4 — lifestyle / circadian...", end=" ", flush=True)
    lifestyle = analyze_lifestyle(data_summary)
    print("✓" if lifestyle else "–")

    domain_outputs = {
        "knowledge": knowledge,
        "engineering": engineering,
        "productivity": productivity,
        "lifestyle": lifestyle,
    }

    print("    stage 5 — meta synthesis...", end=" ", flush=True)
    synthesis = synthesize(domain_outputs, stated_profile_text)
    print("✓")

    synthesis["_domains"] = domain_outputs
    return synthesis
