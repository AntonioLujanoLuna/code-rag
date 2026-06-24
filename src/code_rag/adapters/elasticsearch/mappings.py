from __future__ import annotations

_SETTINGS = {"number_of_shards": 1, "number_of_replicas": 0}


def chunks_mapping(embedding_dimension: int) -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "tenant_id": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "repo_path_with_namespace": {"type": "keyword"},
                "repo_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "team_owner": {"type": "keyword"},
                "business_domain": {"type": "keyword"},
                "service_name": {"type": "keyword"},
                "slack_channel": {"type": "keyword"},
                "jira_project": {"type": "keyword"},
                "service_type": {"type": "keyword"},
                "deployment_name": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "commit_sha": {"type": "keyword"},
                "active_snapshot": {"type": "boolean"},
                "file_path": {"type": "keyword"},
                "file_path_text": {"type": "text"},
                "language": {"type": "keyword"},
                "chunk_kind": {"type": "keyword"},
                "symbol_role": {"type": "keyword"},
                "symbol_name": {"type": "keyword"},
                "symbol_name_text": {"type": "text"},
                "symbol_fqn": {"type": "keyword"},
                "symbol_fqn_text": {"type": "text"},
                "text": {"type": "text"},
                "summary": {"type": "text"},
                "imports": {"type": "keyword"},
                "defines_symbols": {"type": "keyword"},
                "references_symbols": {"type": "keyword"},
                "calls_symbols": {"type": "keyword"},
                "secret_findings_count": {"type": "integer"},
                "secret_redactions_count": {"type": "integer"},
                "secret_high_confidence_count": {"type": "integer"},
                "secret_types": {"type": "keyword"},
                "embedding_input_hash": {"type": "keyword"},
                "embedding_dense": {
                    "type": "dense_vector",
                    "dims": embedding_dimension,
                    "index": True,
                    "similarity": "cosine",
                },
                "embedding_late_interaction": {"type": "object", "enabled": False},
                "indexed_at": {"type": "date"},
            },
        },
    }


def symbols_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "tenant_id": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "repo_path_with_namespace": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "commit_sha": {"type": "keyword"},
                "language": {"type": "keyword"},
                "symbol_name": {"type": "keyword"},
                "symbol_name_text": {"type": "text"},
                "symbol_fqn": {"type": "keyword"},
                "symbol_fqn_text": {"type": "text"},
                "symbol_kind": {"type": "keyword"},
                "definition_file_path": {"type": "keyword"},
                "signature": {"type": "text"},
                "indexed_at": {"type": "date"},
            },
        },
    }


def edges_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "tenant_id": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "commit_sha": {"type": "keyword"},
                "source_symbol_fqn": {"type": "keyword"},
                "source_symbol_text": {"type": "text"},
                "target_symbol_fqn": {"type": "keyword"},
                "target_symbol_text": {"type": "text"},
                "source_repo_project_id": {"type": "keyword"},
                "source_repo_path_with_namespace": {"type": "keyword"},
                "source_file_path": {"type": "keyword"},
                "target_file_path": {"type": "keyword"},
                "edge_type": {"type": "keyword"},
                "confidence": {"type": "float"},
                "indexed_at": {"type": "date"},
            },
        },
    }


def communities_mapping(embedding_dimension: int) -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "community_id": {"type": "keyword"},
                "tenant_id": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "repo_path_with_namespace": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "commit_sha": {"type": "keyword"},
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "summary": {"type": "text"},
                "size": {"type": "integer"},
                "dominant_language": {"type": "keyword"},
                "member_symbol_fqns": {"type": "keyword"},
                "member_chunk_ids": {"type": "keyword"},
                "member_file_paths": {"type": "keyword"},
                "representative_chunk_id": {"type": "keyword"},
                "representative_gitlab_url": {"type": "keyword"},
                "edge_count": {"type": "integer"},
                "embedding_dense": {
                    "type": "dense_vector",
                    "dims": embedding_dimension,
                    "index": True,
                    "similarity": "cosine",
                },
                "indexed_at": {"type": "date"},
            },
        },
    }


def files_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "tenant_id": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "repo_path_with_namespace": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "commit_sha": {"type": "keyword"},
                "file_path": {"type": "keyword"},
                "language": {"type": "keyword"},
                "file_hash": {"type": "keyword"},
                "team_owner": {"type": "keyword"},
                "business_domain": {"type": "keyword"},
                "service_name": {"type": "keyword"},
                "secret_findings_count": {"type": "integer"},
                "secret_redactions_count": {"type": "integer"},
                "defined_symbols": {"type": "keyword"},
                "chunk_ids": {"type": "keyword"},
            },
        },
    }


def repos_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "repo_id": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "repo_path_with_namespace": {"type": "keyword"},
                "repo_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "indexed_branch": {"type": "keyword"},
                "active_commit_sha": {"type": "keyword"},
                "team_owner": {"type": "keyword"},
                "business_domain": {"type": "keyword"},
                "service_name": {"type": "keyword"},
                "slack_channel": {"type": "keyword"},
                "jira_project": {"type": "keyword"},
                "primary_language": {"type": "keyword"},
                "service_type": {"type": "keyword"},
                "deployment_name": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "index_status": {"type": "keyword"},
                "last_successful_index_at": {"type": "date"},
            },
        },
    }


def jobs_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "job_id": {"type": "keyword"},
                "job_type": {"type": "keyword"},
                "gitlab_project_id": {"type": "keyword"},
                "branch": {"type": "keyword"},
                "status": {"type": "keyword"},
                "started_at": {"type": "date"},
                "finished_at": {"type": "date"},
            },
        },
    }


def job_status_mapping() -> dict:
    return {
        "settings": _SETTINGS,
        "mappings": {
            "dynamic": True,
            "properties": {
                "job_id": {"type": "keyword"},
                "job_type": {"type": "keyword"},
                "status": {"type": "keyword"},
                "submitted_at": {"type": "date"},
                "started_at": {"type": "date"},
                "finished_at": {"type": "date"},
            },
        },
    }
