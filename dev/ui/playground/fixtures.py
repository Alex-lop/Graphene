"""The owner's pasted diagram, as data: a causal loop with feedback and two-way arrows. This is a stress test
for the layout, and a look at what an *intent* graph would be. The edges are my reading of his ASCII art
(a line with an arrowhead at both ends is a two-way edge); where the art is ambiguous I took the simplest
reading."""

from flowlayout import GEdge, GNode

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
