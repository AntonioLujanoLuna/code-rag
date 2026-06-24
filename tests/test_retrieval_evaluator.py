from __future__ import annotations

import json
from pathlib import Path

from code_rag.apps.eval.retrieval_evaluator import RetrievalEvaluator
from code_rag.domain import QueryType, SearchHit, SearchResponse


def _hit(chunk_id: str, file_path: str) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=1.0,
        repo_path_with_namespace="group/payments",
        file_path=file_path,
        line_start=1,
        line_end=3,
        language="python",
        chunk_kind="function_definition",
        symbol_name="PaymentService",
        symbol_fqn="group.payments.PaymentService",
        gitlab_blob_url="https://gitlab.example.com/x",
        text="code",
    )


class FakeService:
    def __init__(self, hits_by_query: dict[str, list[SearchHit]]) -> None:
        self.hits_by_query = hits_by_query

    def search(self, request) -> SearchResponse:
        return SearchResponse(
            query=request.query,
            query_type=QueryType.DEFINITION_LOOKUP,
            identifiers=[],
            hits=self.hits_by_query.get(request.query, []),
            context="",
        )


def test_perfect_ranking_scores_one() -> None:
    service = FakeService({"q": [_hit("c1", "service.py"), _hit("c2", "other.py")]})
    evaluator = RetrievalEvaluator(service, k=5)

    report = evaluator.evaluate(_dataset([{"query": "q", "relevant": ["service.py"]}]))

    case = report["cases"][0]
    assert case["mrr"] == 1.0
    assert case["hit_at_k"] == 1.0
    assert case["recall_at_k"] == 1.0
    assert case["ndcg_at_k"] == 1.0
    assert report["aggregate"]["num_cases"] == 1


def test_relevant_at_rank_two_halves_mrr() -> None:
    service = FakeService({"q": [_hit("c1", "wrong.py"), _hit("c2", "service.py")]})
    evaluator = RetrievalEvaluator(service, k=5)

    report = evaluator.evaluate(_dataset([{"query": "q", "relevant": ["service.py"]}]))

    case = report["cases"][0]
    assert case["mrr"] == 0.5
    assert case["recall_at_k"] == 1.0
    assert case["hit_at_k"] == 1.0


def test_missing_relevant_scores_zero() -> None:
    service = FakeService({"q": [_hit("c1", "wrong.py")]})
    evaluator = RetrievalEvaluator(service, k=5)

    report = evaluator.evaluate(_dataset([{"query": "q", "relevant": ["service.py"]}]))

    case = report["cases"][0]
    assert case["mrr"] == 0.0
    assert case["hit_at_k"] == 0.0
    assert case["recall_at_k"] == 0.0


def test_load_reads_dataset_file(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({"cases": [{"query": "q", "relevant": ["a.py"]}]}), encoding="utf-8")
    evaluator = RetrievalEvaluator(FakeService({}), k=3)

    dataset = evaluator.load(path)

    assert dataset.cases[0].query == "q"
    assert dataset.cases[0].relevant == ["a.py"]


def _dataset(cases: list[dict]):
    from code_rag.apps.eval.eval_case import EvalDataset

    return EvalDataset.model_validate({"cases": cases})
