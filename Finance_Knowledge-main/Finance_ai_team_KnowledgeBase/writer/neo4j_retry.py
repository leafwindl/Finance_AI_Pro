#!/usr/bin/env python3
"""重试失败的 2 个文档"""
import json, os, sys, time, hashlib
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

os.environ.setdefault("LLM_API_KEY", os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")))

from neo4j import GraphDatabase
from openai import OpenAI

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "")))

with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
    r = session.run("MATCH (d:__Document__)-[:PART_OF]-(c:__Chunk__) WHERE NOT (c)-[:HAS_ENTITY]-() RETURN DISTINCT d.id AS did, d.title AS title")
    docs = [(row["did"], row["title"]) for row in r]
    print(f"Found {len(docs)} docs with empty chunks")

for doc_id, title in docs:
    with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
        r = session.run("MATCH (d:__Document__ {id:$id})-[:PART_OF]-(c:__Chunk__) RETURN c.id AS cid, c.text AS text ORDER BY c.id", id=doc_id)
        chunks = [(row["cid"], row["text"] or "") for row in r]

    text = "\n\n".join(c[1] for c in chunks)
    print(f"\n{title[:55]}: {len(chunks)} chunks, {len(text)} chars")

    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"), timeout=180)
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
            messages=[{"role": "user", "content": '返回纯JSON: {"entities":[...],"relations":[...]}\n\n文本:\n' + text[:8000]}],
            temperature=0.1)
        content = resp.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(content)
        entities = data.get("entities", [])
        relations = data.get("relations", [])
        print(f"  LLM: {time.time()-t0:.0f}s, {len(entities)}e, {len(relations)}r")

        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            entity_names = [e["name"].strip() for e in entities]

            # Clean + MERGE entities
            for i, ent in enumerate(entities):
                name = ent["name"].strip()
                etype = ent["type"].strip().upper()
                desc = ent.get("description", "").strip()
                eid = hashlib.md5(f"{name}:{etype}".encode()).hexdigest()
                session.run("""
                    MERGE (e:__Entity__ {name: $name})
                    ON CREATE SET e.id=$eid, e.type=$type, e.description=$desc
                    ON MATCH SET e.description=CASE WHEN e.description IS NULL OR size(e.description)<size($desc) THEN $desc ELSE e.description END
                """, name=name, eid=eid, type=etype, desc=desc)

            # HAS_ENTITY for all chunks
            for cid, _ in chunks:
                if entity_names:
                    session.run("MATCH (c:__Chunk__ {id:$id}) MATCH (e:__Entity__) WHERE e.name IN $names MERGE (c)-[:HAS_ENTITY]->(e)", id=cid, names=entity_names)

            # RELATED
            for j, rel in enumerate(relations):
                s = rel["source"].strip()
                t = rel["target"].strip()
                if s == t: continue
                rid = hashlib.md5(f"{s}->{t}:{j}".encode()).hexdigest()
                session.run("""
                    MATCH (e1:__Entity__ {name:$s}), (e2:__Entity__ {name:$t})
                    MERGE (e1)-[r:RELATED]->(e2)
                    ON CREATE SET r.id=$rid, r.description=$desc, r.weight=1.0
                    ON MATCH SET r.weight=coalesce(r.weight,1.0)+0.5
                """, s=s, t=t, rid=rid, desc=rel.get("description", "").strip())

        print(f"  Neo4j: OK, {len(chunks)} chunks linked")

    except Exception as e:
        print(f"  ERROR: {e}")

driver.close()

# Final check
with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
    r = session.run("MATCH (c:__Chunk__) WHERE NOT (c)-[:HAS_ENTITY]->() RETURN count(c) as cnt")
    empty = r.single()["cnt"]
    r = session.run("MATCH ()-[x:HAS_ENTITY]->() RETURN count(x) as cnt")
    total = r.single()["cnt"]
    print(f"\nFinal: {empty} empty chunks, {total} HAS_ENTITY total")

driver.close()
