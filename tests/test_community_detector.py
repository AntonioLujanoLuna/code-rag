from __future__ import annotations

from code_rag.apps.communities.community_detector import CommunityDetector
from code_rag.config.settings import Settings
from code_rag.domain import CodeEdge, CodeSymbol, EdgeType


def _symbol(fqn: str, *, kind: str = "function", docstring: str | None = None) -> CodeSymbol:
    name = fqn.rsplit(".", 1)[-1]
    return CodeSymbol(
        symbol_id=f"id-{fqn}",
        tenant_id="default",
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        branch="develop",
        commit_sha="cafe",
        language="python",
        symbol_name=name,
        symbol_fqn=fqn,
        symbol_kind=kind,
        definition_file_path=f"{fqn.split('.')[2]}.py",
        definition_line_start=1,
        definition_line_end=10,
        definition_chunk_id=f"chunk-{fqn}",
        definition_gitlab_url=f"https://gitlab.example.com/{fqn}",
        docstring=docstring,
    )


def _edge(source: str, target: str) -> CodeEdge:
    return CodeEdge(
        edge_id=f"edge-{source}-{target}",
        tenant_id="default",
        branch="develop",
        commit_sha="cafe",
        source_symbol_fqn=source,
        source_repo_project_id="123",
        source_repo_path_with_namespace="group/payments",
        source_file_path="f.py",
        source_line_start=1,
        target_symbol_fqn=target,
        edge_type=EdgeType.CALLS,
    )


def test_detects_two_disconnected_communities() -> None:
    settings = Settings(community_min_size=3)
    detector = CommunityDetector(settings)
    payments = ["g.p.pay.Charge", "g.p.pay.Refund", "g.p.pay.Ledger"]
    billing = ["g.p.bill.Invoice", "g.p.bill.LineItem", "g.p.bill.Tax"]
    symbols = [_symbol(fqn, docstring="Handles money.") for fqn in payments + billing]
    edges = [
        _edge("g.p.pay.Charge", "g.p.pay.Refund"),
        _edge("g.p.pay.Refund", "g.p.pay.Ledger"),
        _edge("g.p.bill.Invoice", "g.p.bill.LineItem"),
        _edge("g.p.bill.LineItem", "g.p.bill.Tax"),
    ]

    communities = detector.detect("123", "group/payments", "develop", "cafe", symbols, edges)

    assert len(communities) == 2
    member_sets = sorted([sorted(c.member_symbol_fqns) for c in communities])
    assert member_sets == [sorted(billing), sorted(payments)]
    for community in communities:
        assert community.size == 3
        assert community.dominant_language == "python"
        assert "Key symbols" in community.summary
        assert community.representative_chunk_id in [
            f"chunk-{fqn}" for fqn in community.member_symbol_fqns
        ]


def test_drops_communities_below_min_size() -> None:
    settings = Settings(community_min_size=3)
    detector = CommunityDetector(settings)
    symbols = [_symbol("g.p.a.One"), _symbol("g.p.a.Two")]
    edges = [_edge("g.p.a.One", "g.p.a.Two")]

    assert detector.detect("123", "group/payments", "develop", "cafe", symbols, edges) == []


def test_resolves_targets_by_short_name() -> None:
    settings = Settings(community_min_size=3)
    detector = CommunityDetector(settings)
    symbols = [_symbol("g.p.pay.Charge"), _symbol("g.p.pay.Refund"), _symbol("g.p.pay.Ledger")]
    # Targets given as bare names should still resolve to the unique symbol.
    edges = [_edge("g.p.pay.Charge", "Refund"), _edge("g.p.pay.Refund", "Ledger")]

    communities = detector.detect("123", "group/payments", "develop", "cafe", symbols, edges)

    assert len(communities) == 1
    assert sorted(communities[0].member_symbol_fqns) == [
        "g.p.pay.Charge",
        "g.p.pay.Ledger",
        "g.p.pay.Refund",
    ]
