from __future__ import annotations

import asyncio
import json
import math
from inspect import isawaitable
from pathlib import Path

from code_rag.apps.eval.eval_case import EvalCase, EvalDataset
from code_rag.apps.retrieval.retrieval_service import RetrievalService
from code_rag.domain.models import SearchHit, SearchRequest


class RetrievalEvaluator:
    """Scores a retrieval service against a golden dataset.

    Computes the standard ranking metrics (recall@k, precision@k, MRR, nDCG@k,
    hit-rate) per case and as macro-averages, so changes to retrieval — graph
    expansion, rerankers, community summaries — can be measured rather than
    eyeballed.
    """

    def __init__(self, service: RetrievalService, k: int = 10) -> None:
        self.service = service
        self.k = k

    def load(self, path: Path) -> EvalDataset:
        return EvalDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def evaluate(self, dataset: EvalDataset) -> dict:
        return asyncio.run(self.aevaluate(dataset))

    async def aevaluate(self, dataset: EvalDataset) -> dict:
        per_case: list[dict] = []
        for case in dataset.cases:
            result = self.service.search(
                SearchRequest(
                    query=case.query,
                    user_id=case.user_id,
                    allowed_project_ids=case.allowed_project_ids,
                    branch=case.branch,
                    repo_path_with_namespace=case.repo_path_with_namespace,
                    top_k=self.k,
                )
            )
            response = await result if isawaitable(result) else result
            per_case.append(self._score_case(case, response.hits))
        return {
            "k": self.k,
            "cases": per_case,
            "aggregate": self._aggregate(per_case),
        }

    def _score_case(self, case: EvalCase, hits: list[SearchHit]) -> dict:
        relevant = set(case.relevant)
        total_relevant = len(relevant)
        ranked = hits[: self.k]
        flags = [self._is_relevant(hit, relevant) for hit in ranked]
        retrieved_relevant = sum(flags)
        first_rank = next((index + 1 for index, flag in enumerate(flags) if flag), 0)
        return {
            "query": case.query,
            "recall_at_k": retrieved_relevant / total_relevant if total_relevant else 0.0,
            "precision_at_k": retrieved_relevant / self.k if self.k else 0.0,
            "mrr": 1.0 / first_rank if first_rank else 0.0,
            "ndcg_at_k": self._ndcg(flags, total_relevant),
            "hit_at_k": 1.0 if retrieved_relevant else 0.0,
            "num_relevant": total_relevant,
            "num_retrieved_relevant": retrieved_relevant,
        }

    def _is_relevant(self, hit: SearchHit, relevant: set[str]) -> bool:
        return bool(relevant & {hit.chunk_id, hit.file_path, hit.symbol_fqn or ""})

    def _ndcg(self, flags: list[bool], total_relevant: int) -> float:
        if not total_relevant:
            return 0.0
        dcg = sum(1.0 / math.log2(index + 2) for index, flag in enumerate(flags) if flag)
        ideal_hits = min(total_relevant, len(flags))
        idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
        return dcg / idcg if idcg else 0.0

    def _aggregate(self, per_case: list[dict]) -> dict:
        if not per_case:
            return {
                "recall_at_k": 0.0,
                "precision_at_k": 0.0,
                "mrr": 0.0,
                "ndcg_at_k": 0.0,
                "hit_at_k": 0.0,
                "num_cases": 0,
            }
        metrics = ["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "hit_at_k"]
        aggregate = {
            metric: sum(case[metric] for case in per_case) / len(per_case) for metric in metrics
        }
        aggregate["num_cases"] = len(per_case)
        return aggregate
