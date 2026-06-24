# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately rather than opening a public
issue. Use GitHub's [private vulnerability reporting][gh-report] for this
repository, or contact the maintainer directly.

Include enough detail to reproduce the issue (affected endpoint or component,
configuration, and steps). We aim to acknowledge reports within a few business
days.

[gh-report]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability

## Security-relevant configuration

This service handles source code and access-control data. When deploying:

- **Set `CODE_RAG_API_KEYS`.** When empty, the API runs in development mode
  with no authentication and trusts request-supplied user IDs. Always configure
  API keys in production.
- **Keep `CODE_RAG_ALLOW_REQUEST_SUPPLIED_PERMISSIONS=false`** (the default) so
  authorization is resolved server-side from the permission cache rather than
  trusting the request body.
- **Set `CODE_RAG_GITLAB_WEBHOOK_SECRET`** so the webhook endpoint validates the
  `X-Gitlab-Token` header.
- **Leave secret scanning enabled** (`CODE_RAG_SECRET_SCANNING_ENABLED=true`) so
  high-risk tokens are redacted before embedding/indexing. Consider
  `CODE_RAG_SKIP_CHUNKS_WITH_HIGH_CONFIDENCE_SECRETS=true` for stricter handling.
- **Enable rate limiting** (`CODE_RAG_RATE_LIMIT_REQUESTS_PER_MINUTE`) on
  internet-facing deployments to bound load on Elasticsearch and the answer
  backend.
- Protect the Elasticsearch instance and the answer/embedding backends behind
  network controls and credentials; do not expose them publicly.
