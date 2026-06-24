"""OpenTelemetry tracing helpers.

``opentelemetry-api`` is a hard dependency, but it is a no-op unless an SDK and
exporter are configured by the deployment (e.g. via ``opentelemetry-instrument``
or an OTLP exporter). Importing and creating spans here is therefore safe and
zero-cost out of the box, while giving operators real, named spans around the
retrieval pipeline and Elasticsearch calls the moment they wire up an exporter.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer


def get_tracer(name: str) -> Tracer:
    """Return a tracer for ``name`` (typically a module ``__name__``)."""
    return trace.get_tracer(name)
