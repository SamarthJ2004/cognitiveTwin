import os
from openai import OpenAI
from questions import QUESTIONS
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv


load_dotenv()

ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

db = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", ""))
)


def print_header(text):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def print_dim(text):
    print(f"  \033[90m{text}\033[0m")


def print_ok(text):
    print(f"  \033[92m✓\033[0m {text}")


def print_question(index, total, q):
    print(f"\n\033[94m[{index}/{total}]\033[0m {q['question']}")
    if q.get("hint"):
        print_dim(q["hint"])


def analyze_answer(question, answer, category):
    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": f"""You are analyzing a psychological questionnaire response to build a cognitive profile.

Category: {category}
Question: {question}
Answer: {answer}

Extract cognitive patterns and return ONLY a JSON object with these fields:
{{
  "beliefs": ["list of specific belief statements this answer reveals"],
  "reasoning_style": "one of: analytical | intuitive | emotional | pragmatic | mixed",
  "values": ["list of values this answer demonstrates"],
  "traits": {{
    "openness": 0.0-1.0 or null,
    "conscientiousness": 0.0-1.0 or null,
    "agreeableness": 0.0-1.0 or null,
    "neuroticism": 0.0-1.0 or null,
    "need_for_cognition": 0.0-1.0 or null,
    "need_for_closure": 0.0-1.0 or null
  }},
  "heuristics": ["short descriptions of mental shortcuts or patterns this person uses"],
  "summary": "one sentence capturing the key cognitive insight from this answer"
}}

Return ONLY valid JSON. No explanation, no markdown."""
            }
        ]
    )

    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def store_profile(session, user_id, q_id, category, analysis):
    session.run("MERGE (u:User {id: $uid})", uid=user_id)

    for belief in analysis.get("beliefs", []):
        session.run("""
        MATCH (u:User {id: $uid})
        MERGE (b:Belief {text: $text})
        SET b.category = $cat
        MERGE (u)-[:HOLDS]->(b)
        """, uid=user_id, text=belief, cat=category)

    for value in analysis.get("values", []):
        session.run("""
        MATCH (u:User {id: $uid})
        MERGE (v:Value {name: $name})
        MERGE (u)-[:VALUES]->(v)
        """, uid=user_id, name=value)

    for heuristic in analysis.get("heuristics", []):
        session.run("""
        MATCH (u:User {id: $uid})
        MERGE (h:Heuristic {description: $desc})
        SET h.source_question = $qid
        MERGE (u)-[:USES]->(h)
        """, uid=user_id, desc=heuristic, qid=q_id)

    style = analysis.get("reasoning_style")
    if style:
        session.run("""
        MATCH (u:User {id: $uid})
        MERGE (r:ReasoningStyle {type: $type})
        MERGE (u)-[:REASONS_WITH {question: $qid}]->(r)
        """, uid=user_id, type=style, qid=q_id)

    traits = {k: v for k, v in analysis.get(
        "traits", {}).items() if v is not None}
    if traits:
        trait_expr = ", ".join([f"u.{k} = ${k}" for k in traits])
        session.run(f"MATCH (u:User {{id: $uid}}) SET {
                    trait_expr}", uid=user_id, **traits)       # **traits : dictionary unpacking


def run_assessment(session, user_id):
    print_header("Cognitive Assessment")
    print_dim("Answer honestly, there is no right or wrong")
    print_dim(
        "Type your answer and press Enter. Type 'skip' if you really want to skip a question\n")

    total = len(QUESTIONS)

    for i, q in enumerate(QUESTIONS, 1):
        print_question(i, total, q)
        answer = input("\n> ").strip()

        if answer.lower() == "skip":
            print_dim("skipped")
            continue

        print_dim("Analyzing........")

        try:
            analysis = analyze_answer(q["question"], answer, q["category"])
            store_profile(session, user_id, q["id"], q["category"], analysis)
            print_ok(analysis.get("summary", "Stored."))

        except Exception as e:
            print(f"  \033[91m✗\033[0m Could not analyze: {e}")

    print_header("Assessment complete")
    print_dim("Your cognitive profile has been built. Try 'Ask your twin' next.\n")


def get_profile(session, user_id):
    result = session.run("""
    MATCH (u:User {id: $uid})
    OPTIONAL MATCH (u)-[:HOLDS]->(b:Belief)
    OPTIONAL MATCH (u)-[:VALUES]->(v:Value)
    OPTIONAL MATCH (u)-[:USES]->(h:Heuristic)
    OPTIONAL MATCH (u)-[:REASONS_WITH]->(r:ReasoningStyle)
    RETURN
        u,
        collect(DISTINCT b.text) as beliefs,
        collect(DISTINCT v.name) as values,
        collect(DISTINCT h.description) as heuristics,
        collect(DISTINCT r.type) as reasoning_styles
    """, uid=user_id)

    record = result.single()
    if not record:
        return None

    user_props = dict(record["u"])
    return {
        "beliefs": record["beliefs"],
        "values": record["values"],
        "heuristics": record["heuristics"],
        "reasoning_styles": list(set(record["reasoning_styles"])),
        "traits": {k: v for k, v in user_props.items() if k != "id"}
    }


def build_profile_text(profile):
    lines = []

    if profile["reasoning_styles"]:
        lines.append(f"Reasoning Styles : {
                     ', '.join(profile['reasoning_styles'])}")

    if profile["traits"]:
        trait_lines = [f"{k}: {round(v, 2)}" for k,
                       v in profile["traits"].items()]
        lines.append(f"Trait scores: {', '.join(trait_lines)}")

    if profile["beliefs"]:
        lines.append("\nCore beliefs:")
        for b in profile["beliefs"]:
            lines.append(f"  - {b}")

    if profile["values"]:
        lines.append("\nValues:")
        for v in profile["values"]:
            lines.append(f"  - {v}")

    if profile["heuristics"]:
        lines.append("\nMental patterns / heuristics:")
        for h in profile["heuristics"]:
            lines.append(f"  - {h}")

    return "\n".join(lines)


def ask_twin(session, user_id, question):
    profile = get_profile(session, user_id)

    if not profile or not any([profile["beliefs"], profile["values"], profile["heuristics"]]):
        print("\n Not enough profile data yet, take the assessment first\n")
        return

    profile_text = build_profile_text(profile)

    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": f"""You are simulating the cog[118;1:3unitive twin of a specific person.
Their psychological profile is:

{profile_text}

Answer the following question exactly as THIS PERSON would — using their specific reasoning style, values, heuristics, and beliefs. Show the thinking process, not just the conclusion. Be specific about HOW they would reason through this.

If the profile doesn't have enough signal on a topic, say so honestly rather than inventing.

Question: {question}"""
            }
        ]
    )

    print("\n\033[93mYour twin says:\033[0m\n")
    print(response.choices[0].message.content)


def show_profile(session, user_id):
    profile = get_profile(session, user_id)

    if not profile or not any([profile["beliefs"], profile["values"]]):
        print("\n  No profile yet. Run the assessment first.\n")
        return

    print_header(f"Cognitive profile: {user_id}")
    print(build_profile_text(profile))
    print()


def main():
    print_header("Cognitive Twin")
    user_id = input("User enter your name: ").strip()

    print(f"\n Hello, {user_id}")

    with db.session() as session:
        while True:
            print("\n  1. Run assessment")
            print("  2. Ask your twin")
            print("  3. View my profile")
            print("  4. Exit")

            choice = input("\n> ").strip()

            if choice == "1":
                run_assessment(session, user_id)

            elif choice == "2":
                question = input(
                    "\n  What do you want to ask your twin?\n> ").strip()
                if question:
                    ask_twin(session, user_id, question)

            elif choice == "3":
                show_profile(session, user_id)

            elif choice == "4":
                print("\n  Goodbye.\n")
                break

    db.close()


if __name__ == "__main__":
    main()
