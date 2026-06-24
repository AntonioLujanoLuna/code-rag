from __future__ import annotations

from collections import Counter, defaultdict

from code_rag.config.settings import Settings
from code_rag.domain.ids import stable_id
from code_rag.domain.models import CodeCommunity, CodeEdge, CodeSymbol


class CommunityDetector:
    """Cluster a repository's symbol/edge graph into communities.

    Uses deterministic synchronous label propagation over the undirected graph
    whose nodes are defined symbols and whose links are code edges resolved to
    known symbols. Each resulting cluster gets an extractive summary so global,
    architecture-level questions can retrieve a cluster overview.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect(
        self,
        gitlab_project_id: str,
        repo_path_with_namespace: str,
        branch: str,
        commit_sha: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> list[CodeCommunity]:
        if not symbols:
            return []
        by_fqn = {symbol.symbol_fqn: symbol for symbol in symbols if symbol.symbol_fqn}
        if not by_fqn:
            return []
        adjacency = self._adjacency(by_fqn, edges)
        labels = self._label_propagation(sorted(by_fqn), adjacency)
        groups: dict[str, list[str]] = defaultdict(list)
        for fqn, label in labels.items():
            groups[label].append(fqn)
        communities: list[CodeCommunity] = []
        for members in groups.values():
            if len(members) < self.settings.community_min_size:
                continue
            community = self._build_community(
                gitlab_project_id,
                repo_path_with_namespace,
                branch,
                commit_sha,
                sorted(members),
                by_fqn,
                adjacency,
            )
            communities.append(community)
        return communities

    def _adjacency(
        self, by_fqn: dict[str, CodeSymbol], edges: list[CodeEdge]
    ) -> dict[str, set[str]]:
        # Resolve edge targets (raw call/import/reference names) to known symbols
        # by exact FQN or trailing symbol-name match, then link both endpoints.
        name_index: dict[str, list[str]] = defaultdict(list)
        for fqn in by_fqn:
            name_index[fqn.rsplit(".", 1)[-1]].append(fqn)
        adjacency: dict[str, set[str]] = {fqn: set() for fqn in by_fqn}
        for edge in edges:
            source = edge.source_symbol_fqn
            if source not in by_fqn:
                continue
            target = edge.target_symbol_fqn
            if not target:
                continue
            resolved = self._resolve(target, by_fqn, name_index)
            if resolved and resolved != source:
                adjacency[source].add(resolved)
                adjacency[resolved].add(source)
        return adjacency

    def _resolve(
        self,
        target: str,
        by_fqn: dict[str, CodeSymbol],
        name_index: dict[str, list[str]],
    ) -> str | None:
        if target in by_fqn:
            return target
        candidates = name_index.get(target.rsplit(".", 1)[-1])
        if candidates and len(candidates) == 1:
            return candidates[0]
        return None

    def _label_propagation(
        self, nodes: list[str], adjacency: dict[str, set[str]], max_iterations: int = 20
    ) -> dict[str, str]:
        labels = {node: node for node in nodes}
        for _ in range(max_iterations):
            changed = False
            for node in nodes:
                neighbors = adjacency.get(node) or set()
                if not neighbors:
                    continue
                counts = Counter(labels[neighbor] for neighbor in neighbors)
                # Most frequent neighbour label; ties break to the smallest label
                # string so the result is deterministic across runs.
                best = min(counts, key=lambda label: (-counts[label], label))
                if labels[node] != best:
                    labels[node] = best
                    changed = True
            if not changed:
                break
        return labels

    def _build_community(
        self,
        gitlab_project_id: str,
        repo_path_with_namespace: str,
        branch: str,
        commit_sha: str,
        members: list[str],
        by_fqn: dict[str, CodeSymbol],
        adjacency: dict[str, set[str]],
    ) -> CodeCommunity:
        ranked = sorted(
            members,
            key=lambda fqn: (-len(adjacency.get(fqn, set())), fqn),
        )[: self.settings.community_max_members]
        top = ranked[: self.settings.community_summary_max_symbols]
        symbols = [by_fqn[fqn] for fqn in ranked]
        languages = Counter(symbol.language for symbol in symbols if symbol.language)
        dominant_language = languages.most_common(1)[0][0] if languages else None
        file_paths = sorted({symbol.definition_file_path for symbol in symbols})
        representative = by_fqn[ranked[0]]
        label = self._label(ranked, by_fqn)
        community_id = stable_id(
            "community",
            self.settings.tenant_id,
            gitlab_project_id,
            branch,
            ranked[0],
        )
        return CodeCommunity(
            community_id=community_id,
            tenant_id=self.settings.tenant_id,
            gitlab_project_id=gitlab_project_id,
            repo_path_with_namespace=repo_path_with_namespace,
            branch=branch,
            commit_sha=commit_sha,
            label=label,
            summary=self._summary(label, repo_path_with_namespace, top, by_fqn, file_paths),
            size=len(members),
            dominant_language=dominant_language,
            member_symbol_fqns=ranked,
            member_chunk_ids=[by_fqn[fqn].definition_chunk_id for fqn in ranked],
            member_file_paths=file_paths[:50],
            representative_chunk_id=representative.definition_chunk_id,
            representative_gitlab_url=representative.definition_gitlab_url,
            edge_count=sum(len(adjacency.get(fqn, set())) for fqn in members) // 2,
        )

    def _label(self, ranked: list[str], by_fqn: dict[str, CodeSymbol]) -> str:
        prefix = self._common_module(ranked)
        head = by_fqn[ranked[0]].symbol_name
        if prefix:
            return f"{prefix} ({head} cluster)"
        return f"{head} cluster"

    def _common_module(self, members: list[str]) -> str | None:
        parts = [fqn.split(".") for fqn in members]
        common: list[str] = []
        for pieces in zip(*parts, strict=False):
            first = pieces[0]
            if all(piece == first for piece in pieces):
                common.append(first)
            else:
                break
        if len(common) >= 2:
            return ".".join(common[:-1]) if len(common) > 2 else ".".join(common)
        return None

    def _summary(
        self,
        label: str,
        repo_path_with_namespace: str,
        top: list[str],
        by_fqn: dict[str, CodeSymbol],
        file_paths: list[str],
    ) -> str:
        lines = [
            f"Code community '{label}' in {repo_path_with_namespace}.",
            f"Key symbols ({len(top)} shown):",
        ]
        for fqn in top:
            symbol = by_fqn[fqn]
            descriptor = f"- {symbol.symbol_kind} {symbol.symbol_name} ({fqn})"
            if symbol.docstring:
                first_line = symbol.docstring.strip().splitlines()[0]
                descriptor += f": {first_line}"
            elif symbol.signature:
                descriptor += f": {symbol.signature}"
            lines.append(descriptor)
        if file_paths:
            lines.append("Files: " + ", ".join(file_paths[:15]))
        return "\n".join(lines)
