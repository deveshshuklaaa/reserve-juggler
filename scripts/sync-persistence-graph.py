"""Augment the existing Graphify output using a migrated PostgreSQL schema.

Documentation generation only: this script reads PostgreSQL and source files;
it never applies migrations or writes to the database. Run after graphify update.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.persistence.models import Base, SCHEMA


def main():
    engine = create_engine(os.environ["PERSISTENCE_TEST_DATABASE_URL"])
    if engine.dialect.name != "postgresql":
        raise ValueError("Graph schema verification requires PostgreSQL")
    graph_path = ROOT / "graphify-out" / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    # Refresh, rather than accumulate, schema relationships on each run.
    graph["nodes"] = [n for n in graph["nodes"] if n.get("_origin") != "postgres_verified"]
    graph["links"] = [e for e in graph["links"] if e.get("_origin") != "postgres_verified"]
    nodes = {node["id"]: node for node in graph["nodes"]}

    # Preserve M1's verified CSV/provenance and explicitly planned replay annotations.
    previous = json.loads(subprocess.check_output(
        ["git", "show", "HEAD:graphify-out/graph.json"], cwd=ROOT, encoding="utf-8"))
    for node in previous["nodes"]:
        if node.get("_origin") == "manual_verified":
            nodes.setdefault(node["id"], node)
    source = nodes["organizer_treasury_csv_source"]
    source["sha256"] = hashlib.sha256((ROOT / source["source_file"]).read_bytes()).hexdigest()
    edge_keys = {(e["source"], e["target"], e.get("relation")) for e in graph["links"]}
    for edge in previous["links"]:
        key = (edge["source"], edge["target"], edge.get("relation"))
        if edge.get("_origin") == "manual_verified" and key not in edge_keys:
            if edge["source"] in nodes and edge["target"] in nodes:
                graph["links"].append(edge)
                edge_keys.add(key)

    def node(identifier, label, source_file, **extra):
        nodes[identifier] = dict(id=identifier, label=label, source_file=source_file,
                                 file_type="concept", _origin="postgres_verified", **extra)

    def edge(source, target, relation, context):
        graph["links"].append(dict(source=source, target=target, relation=relation,
            context=context, _origin="postgres_verified", confidence="EXTRACTED",
            confidence_score=1.0, weight=1.0, source_file="database/migrations/003_four_tier_persistence.sql"))

    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names(schema=SCHEMA))
    if not set(t.name for t in Base.metadata.tables.values()).issubset(table_names):
        raise ValueError("Database is missing persistence tables; migrate the disposable test database first")
    migration_id = "persistence_migration_003"
    node(migration_id, "003: four-tier persistence (storage only)",
         "database/migrations/003_four_tier_persistence.sql", owner="Member 2")
    mapped = {mapper.local_table.name: mapper.class_.__name__ for mapper in Base.registry.mappers}
    for name in table_names:
        identifier = "persistence_table_" + name
        definition = "003_four_tier_persistence.sql" if name in mapped else "002_member2_contract.sql"
        node(identifier, f"{SCHEMA}.{name}", "database/migrations/" + definition,
             schema=SCHEMA, table=name, status="persisted; no execution implied")
        if name in mapped:
            model_id = "backend_app_persistence_models_" + mapped[name].lower()
            if model_id not in nodes:
                raise ValueError(f"Graphify model node missing: {model_id}")
            nodes[model_id]["owner"] = "Member 2"
            edge(model_id, identifier, "maps_table", f"SQLAlchemy mapping: {mapped[name]}")
            edge(migration_id, identifier, "creates_or_extends", "Verified after applying migration chain 001/002/003")
        grouped = {}
        for fk in inspector.get_foreign_keys(name, schema=SCHEMA):
            if fk["referred_schema"] == SCHEMA:
                grouped.setdefault(fk["referred_table"], []).append(
                    f"{','.join(fk['constrained_columns'])} -> {','.join(fk['referred_columns'])}")
        for target, constraints in sorted(grouped.items()):
            edge(identifier, "persistence_table_" + target, "foreign_key", "; ".join(sorted(constraints)))
    graph["nodes"] = list(nodes.values())
    identifiers = set(nodes)
    assert all(e["source"] in identifiers and e["target"] in identifiers for e in graph["links"])
    graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    engine.dispose()
    print(f"Verified {len(table_names)} PostgreSQL tables; graph: {len(nodes)} nodes, {len(graph['links'])} relationships")


if __name__ == "__main__":
    main()
