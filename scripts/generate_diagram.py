#!/usr/bin/env python3
"""
generate_diagram.py — generates orderflow_architecture.drawio from architecture_spec.yaml.

The .drawio file is then exported to .svg by `make diagram` via the
rlespinasse/drawio-export Docker image.

Run: python3 scripts/generate_diagram.py
     make diagram   (runs this script + exports SVG)
"""

import yaml
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILE = REPO_ROOT / "docs" / "architecture" / "architecture_spec.yaml"
OUTPUT_DRAWIO = REPO_ROOT / "docs" / "architecture" / "orderflow_architecture.drawio"


def load_spec() -> dict:
    with open(SPEC_FILE) as f:
        return yaml.safe_load(f)


def make_cell(parent: ET.Element, cell_id: str, **attrs) -> ET.Element:
    cell = ET.SubElement(parent, "mxCell")
    cell.set("id", cell_id)
    for k, v in attrs.items():
        cell.set(k, str(v))
    return cell


def make_geometry(cell: ET.Element, x: int, y: int, w: int, h: int):
    geo = ET.SubElement(cell, "mxGeometry")
    geo.set("x", str(x))
    geo.set("y", str(y))
    geo.set("width", str(w))
    geo.set("height", str(h))
    geo.set("as", "geometry")


def generate_drawio(spec: dict) -> str:
    """Produce draw.io XML from the architecture spec."""
    mxfile = ET.Element("mxfile")
    mxfile.set("host", "app.diagrams.net")

    diagram = ET.SubElement(mxfile, "diagram")
    diagram.set("name", spec["diagram"]["title"])
    diagram.set("id", "orderflow-arch")

    mxgraph = ET.SubElement(diagram, "mxGraphModel")
    mxgraph.set("dx", "1422")
    mxgraph.set("dy", "762")
    mxgraph.set("grid", "1")
    mxgraph.set("gridSize", "10")
    mxgraph.set("guides", "1")
    mxgraph.set("tooltips", "1")
    mxgraph.set("connect", "1")
    mxgraph.set("arrows", "1")
    mxgraph.set("fold", "1")
    mxgraph.set("page", "1")
    mxgraph.set("pageScale", "1")
    mxgraph.set("pageWidth", str(spec["diagram"]["width"]))
    mxgraph.set("pageHeight", str(spec["diagram"]["height"]))
    mxgraph.set("math", "0")
    mxgraph.set("shadow", "0")

    root = ET.SubElement(mxgraph, "root")

    # Required base cells
    make_cell(root, "0")
    base = make_cell(root, "1", parent="0")

    cell_id = 2

    # ── Draw layer containers ─────────────────────────────────────────────────
    for layer in spec.get("layers", []):
        lid = str(cell_id)
        cell_id += 1
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;"
            f"fillColor={layer['color']};"
            f"strokeColor={layer['border_color']};"
            f"verticalAlign=top;fontSize=12;fontStyle=1;"
        )
        c = make_cell(root, lid, value=layer["label"], style=style,
                      vertex="1", parent="1")
        make_geometry(c, layer["x"], layer["y"], layer["width"], layer["height"])

        # Draw nodes inside this layer
        for node in layer.get("nodes", []):
            nid = str(cell_id)
            cell_id += 1
            fc = node.get("font_color", "#000000")
            bg = node.get("color", "#FFFFFF")
            nstyle = (
                f"rounded=1;whiteSpace=wrap;html=1;"
                f"fillColor={bg};strokeColor=#666666;"
                f"fontColor={fc};fontStyle=1;fontSize=10;"
            )
            nc = make_cell(root, nid, value=node["label"].replace("\n", "&#xa;"),
                           style=nstyle, vertex="1", parent="1",
                           id_alias=node["id"])
            make_geometry(nc, node["x"], node["y"], node["width"], node["height"])
            # Store id alias for edge lookup
            nc.set("data-node-id", node["id"])

    # ── Draw standalone nodes ─────────────────────────────────────────────────
    node_cell_map: dict[str, str] = {}

    # First pass: assign cell IDs to all nodes
    for node in spec.get("nodes", []):
        nid = str(cell_id)
        cell_id += 1
        node_cell_map[node["id"]] = nid
        fc = node.get("font_color", "#000000")
        bg = node.get("color", "#FFFFFF")
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;"
            f"fillColor={bg};strokeColor=#666666;"
            f"fontColor={fc};fontStyle=1;fontSize=10;"
        )
        nc = make_cell(root, nid,
                       value=node["label"].replace("\n", "&#xa;"),
                       style=style, vertex="1", parent="1")
        make_geometry(nc, node["x"], node["y"], node["width"], node["height"])

    # Also map layer nodes for edge connections
    for layer in spec.get("layers", []):
        for node in layer.get("nodes", []):
            # these were drawn above; need a consistent id
            # re-scan root to find them
            pass

    # ── Draw connections ─────────────────────────────────────────────────────
    # Rebuild lookup from data-node-id attrs
    node_lookup: dict[str, str] = {}
    for elem in root.iter("mxCell"):
        alias = elem.get("data-node-id")
        if alias:
            node_lookup[alias] = elem.get("id")
    node_lookup.update(node_cell_map)

    for conn in spec.get("connections", []):
        src = node_lookup.get(conn["from"])
        tgt = node_lookup.get(conn["to"])
        if not src or not tgt:
            continue
        eid = str(cell_id)
        cell_id += 1
        label = conn.get("label", "").replace("\n", "&#xa;")
        estyle = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
            "jettySize=auto;exitX=1;exitY=0.5;exitDx=0;exitDy=0;"
            "entryX=0;entryY=0.5;entryDx=0;entryDy=0;"
            f"fontSize=9;"
        )
        ec = make_cell(root, eid, value=label, style=estyle,
                       edge="1", source=src, target=tgt, parent="1")
        ET.SubElement(ec, "mxGeometry").set("relative", "1")
        ET.SubElement(ec, "mxGeometry").set("as", "geometry")

    # ── Serialise ─────────────────────────────────────────────────────────────
    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)


def main():
    print(f"Reading spec from {SPEC_FILE}")
    spec = load_spec()

    xml_str = generate_drawio(spec)

    OUTPUT_DRAWIO.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DRAWIO.write_text(xml_str, encoding="utf-8")

    print(f"Generated: {OUTPUT_DRAWIO}")
    print("Next: run `make diagram` to export SVG via drawio-export Docker image")


if __name__ == "__main__":
    main()
