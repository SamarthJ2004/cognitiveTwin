import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", ""))
)


def ensure_user(session, user_id):
    session.run("MERGE (u:User {id: $uid})", uid=user_id)


def save_answer(session, user_id, q_id, question, answer, category):
    # storing user's raw answer to get an idea of their tone
    session.run("""
    MATCH (u:User {id: $uid})
    MERGE (a:Answer {question_id: $qid})
    SET a.question = $question,
        a.text = $answer,
        a.category = $category
    MERGE (u)-[:ANSWERED]->(a)
    """, uid=user_id, qid=q_id, question=question, answer=answer, category=category)


def save_belief(session, user_id, text, self_type, confidence=0.7, date=None):
    # Belief is something the person claims to think or value.
    # self_type: "stated" | "behavioral" | "projected"
    session.run("""
    MATCH (u:User {id: $uid})
    MERGE (b:Belief {text: $text})
    SET b.self_type = $self_type,
        b.confidence= $confidence,
        b.date = $date
    """, uid=user_id, text=text, self_type=self_type, confidence=confidence, date=date)


def save_pattern(session, user_id, text, self_type, source=None, date=None):
    # Pattern : a ruccuring behaviour or acitivity, how he does and not what he thinks
    session.run("""
    MATCH (u:User {id: $uid})
    MERGE (p:Patter {text: $text})
    SET p.self_type = $self_type,
        p.source = $source,
        p.date = $date
    MERGE (u)-[:SHOWS]->(p)
    """, uid=user_id, text=text, source=source, date=date, self_type=self_type)


def save_topic(session, user_id, name, self_type, date=None):
    # Topic : any subject one engages with.
    # Same topic can exist across multiple self types
    # eg: if someone shows the same topic in all self_types, then it is very strong
    session.run("""
        MATCH (u:User {id: $uid})
        MERGE (t:Topic {name: $name, self_type: $self_type})
        SET t.date = $date
        MERGE (u)-[:ENGAGES_WITH]->(t)
    """, uid=user_id, name=name, self_type=self_type, date=date)


def save_emotion(session, user_id, name, self_type, trigger=None, date=None):
    # Emotion : emotional states and triggers.
    session.run("""
        MATCH (u:User {id: $uid})
        MERGE (e:Emotion {name: $name, self_type: $self_type})
        SET e.trigger = $trigger,
            e.date    = $date
        MERGE (u)-[:FEELS]->(e)
    """, uid=user_id, name=name, self_type=self_type,
                trigger=trigger, date=date)


def save_contradiction(session, user_id, text, self_a, self_b,
                       confidence=0.6, date=None):
    # Contradiction is a detected gap between two self types.
    # eg: difference in what you believe vs what you do
    # This is the most valuable node as it reveals blind spots.
    session.run("""
        MATCH (u:User {id: $uid})
        MERGE (c:Contradiction {text: $text})
        SET c.self_a      = $self_a,
            c.self_b      = $self_b,
            c.confidence  = $confidence,
            c.date        = $date
        MERGE (u)-[:HAS]->(c)
    """, uid=user_id, text=text, self_a=self_a, self_b=self_b,
                confidence=confidence, date=date)


def get_profile(session, user_id):
    result = session.run("""
        MATCH (u:User {id: $uid})
        OPTIONAL MATCH (u)-[:HOLDS]->(b:Belief)
        OPTIONAL MATCH (u)-[:SHOWS]->(p:Pattern)
        OPTIONAL MATCH (u)-[:ENGAGES_WITH]->(t:Topic)
        OPTIONAL MATCH (u)-[:FEELS]->(e:Emotion)
        OPTIONAL MATCH (u)-[:HAS]->(c:Contradiction)
        RETURN
            collect(DISTINCT {text: b.text, self_type: b.self_type, confidence: b.confidence}) as beliefs,
            collect(DISTINCT {text: p.text, self_type: p.self_type, source: p.source}) as patterns,
            collect(DISTINCT {name: t.name, self_type: t.self_type}) as topics,
            collect(DISTINCT {name: e.name, self_type: e.self_type, trigger: e.trigger}) as emotions,
            collect(DISTINCT {text: c.text, self_a: c.self_a, self_b: c.self_b}) as contradictions
    """, uid=user_id)

    record = result.single()
    if not record:
        return None

    # filter out empty nodes (OPTIONAL MATCH returns nulls)
    def clean(lst, key):
        return [x for x in lst if x.get(key)]

    return {
        "beliefs": clean(record["beliefs"], "text"),
        "patterns": clean(record["patterns"], "text"),
        "topics": clean(record["topics"], "name"),
        "emotions": clean(record["emotions"], "name"),
        "contradictions": clean(record["contradictions"], "text"),
    }


def get_raw_answers(session, user_id):
    result = session.run("""
        MATCH (u:User {id: $uid})-[:ANSWERED]->(a:Answer)
        RETURN a.question as question, a.text as answer, a.category as category
        ORDER BY a.category
    """, uid=user_id)

    return [
        {"question": r["question"], "answer": r["answer"],
            "category": r["category"]}
        for r in result
    ]


def format_profile(profile):
    # all are grouped by the self type so that relation can be made for the same trait found in various selves
    if not profile:
        return "No profile data yet."

    lines = []

    # beliefs grouped by self
    for self_type in ["stated", "behavioral", "projected"]:
        subset = [b for b in profile["beliefs"]
                  if b.get("self_type") == self_type]
        if subset:
            lines.append(f"\n{self_type.upper()} beliefs:")
            for b in subset:
                conf = b.get("confidence", 0)
                lines.append(f"  - {b['text']}  (confidence: {conf:.0%})")

    # patterns
    if profile["patterns"]:
        lines.append("\nBehavioral patterns:")
        for p in profile["patterns"]:
            lines.append(f"  - {p['text']}")

    # topics
    stated_topics = {t["name"]
                     for t in profile["topics"] if t.get("self_type") == "stated"}
    behavioral_topics = {t["name"] for t in profile["topics"] if t.get(
        "self_type") == "behavioral"}
    projected_topics = {t["name"] for t in profile["topics"]
                        if t.get("self_type") == "projected"}

    if stated_topics:
        lines.append(f"\nStated interests: {', '.join(stated_topics)}")
    if behavioral_topics:
        lines.append(f"Actual interests (behavior): {
                     ', '.join(behavioral_topics)}")
    if projected_topics:
        lines.append(f"Projected interests (social): {
                     ', '.join(projected_topics)}")

    # emotions
    if profile["emotions"]:
        lines.append("\nEmotional patterns:")
        for e in profile["emotions"]:
            trigger = f" — triggered by: {
                e['trigger']}" if e.get("trigger") else ""
            lines.append(f"  - {e['name']}{trigger}")

    # contradictions — very very important
    if profile["contradictions"]:
        lines.append("\n!! CONTRADICTIONS (gaps between selves):")
        for c in profile["contradictions"]:
            lines.append(f"  ⚡ [{c.get('self_a', '?')} vs {
                         c.get('self_b', '?')}] {c['text']}")

    return "\n".join(lines)
