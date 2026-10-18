"""The cockpit's graph layout: pure functions over nodes and edges, tested on the owner's pasted causal loop
(ten nodes, thirteen edges, a long feedback edge and four two-way arrows), the hardest graph asked of it."""

from graphene_map.cockpit import flowlayout as F
from graphene_map.cockpit.flowlayout import GEdge, GNode

PASTED_NODES = [
    GNode("ai", "Industrial AI Output", "plain"),
    GNode("proof", "Proof Abundance", "plain"),
    GNode("mining", "Strip-Mining Problems", "plain"),
    GNode("junior", "Junior Pipeline Collapse", "plain"),
    GNode("culture", "Cultural Shift: Team-Based / Process Math", "plain"),
    GNode("heroic", "Loss of Heroic Era", "plain"),
    GNode("labs", "Incentive Misalignment: Labs", "plain"),
    GNode("synth", "Synthetic Knowledge / Unchecked Proofs", "plain"),
    GNode("deficit", "Deficit of Human Understanding", "plain"),
    GNode("risk", "Real-World Systemic Risk (Grids/Safety)", "plain"),
]
PASTED_EDGES = [
    GEdge("ai", "proof", "two"),
    GEdge("ai", "mining"),
    GEdge("mining", "junior"),
    GEdge("junior", "culture"),
    GEdge("culture", "heroic"),
    GEdge("heroic", "labs", "two"),
    GEdge("ai", "labs", "two"),
    GEdge("proof", "synth"),
    GEdge("synth", "deficit"),
    GEdge("proof", "deficit", "two"),
    GEdge("deficit", "risk"),
    GEdge("labs", "risk"),
    GEdge("deficit", "ai"),  # the long loop down the right side and back to the top
]


def test_the_pasted_graph_lays_out_with_every_node_and_edge_drawn():
    lay = F.layout(PASTED_NODES, PASTED_EDGES, label_w=12)
    assert len(lay.rects) == 10
    boxes = list(lay.rects.values())
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1], "two boxes overlap"
    text = lay.text()
    assert text.count("▶") + text.count("◀") >= len(PASTED_EDGES), "every edge has an arrowhead"
    assert len(lay.back) >= 1, "the feedback edge is a back edge"
    assert lay.width <= 150


def test_the_layout_is_deterministic_and_a_state_change_does_not_move_a_node():
    lay = F.layout(PASTED_NODES, PASTED_EDGES, label_w=12)
    assert F.layout(PASTED_NODES, PASTED_EDGES, label_w=12).text() == lay.text()
    recoloured = [GNode(n.id, n.label, "running", "fox") for n in PASTED_NODES]
    assert F.layout(recoloured, PASTED_EDGES, label_w=12).rects == lay.rects


def test_a_neighbourhood_fits_where_the_whole_does_not():
    lay = F.layout(PASTED_NODES, PASTED_EDGES, label_w=12)
    near_nodes, near_edges = F.neighbourhood(PASTED_NODES, PASTED_EDGES, "ai", 1)
    narrow = F.layout(near_nodes, near_edges, label_w=12)
    assert len(near_nodes) < 10 and narrow.width < lay.width


def test_a_cycle_among_plain_edges_becomes_one_back_edge():
    ring = [GNode(x, x) for x in "abc"]
    lay = F.layout(ring, [GEdge("a", "b"), GEdge("b", "c"), GEdge("c", "a")], label_w=8)
    assert len(lay.rects) == 3 and len(lay.back) == 1
