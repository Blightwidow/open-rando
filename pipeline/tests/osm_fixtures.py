"""Write small .osm.pbf files with pyosmium, so tests need no real extract."""

from __future__ import annotations

from pathlib import Path


def write_pbf(path: Path, nodes: list[dict], ways: list[dict], relations: list[dict]) -> Path:
    """Write a small .osm.pbf. Node locations are (lon, lat), as osmium wants."""
    import osmium
    from osmium.osm import mutable

    writer = osmium.SimpleWriter(str(path))
    try:
        for node in nodes:
            writer.add_node(mutable.Node(**node))
        for way in ways:
            writer.add_way(mutable.Way(**way))
        for relation in relations:
            writer.add_relation(mutable.Relation(**relation))
    finally:
        writer.close()
    return path
