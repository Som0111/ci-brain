"""One LLM call per failure cluster, producing a short plain-English
root-cause hypothesis.

Deliberately a single call with no retries/agent loop/RAG - the roadmap's
locked scope for this phase is "single-call LLM summarization," with full
RAG over failure history explicitly a stretch goal to cut first if needed.
This module is that one call and nothing more: it builds a grounded prompt
from real evidence in a cluster and returns the model's text, unmodified.

Grounded in what's actually true about the cluster, not hidden knowledge of
which bug was seeded: the prompt gives the model exactly what a real CI
system would have (test names, files touched, one representative failure
message) and asks it to hypothesize, not asserts the answer. Whether the
hypothesis matches the real seeded bug is a validation question, checked
separately in `scripts/verify_summaries.py` - the model is not told the
ground truth.
"""
from dataclasses import dataclass

from app.analysis.clustering import FailureCluster
from app.config import settings

MODEL = "gemini-3.5-flash"

PROMPT_TEMPLATE = """You are helping a developer triage a CI test failure cluster.

{count} test(s) failed together, all touching these source file(s): {files}
{hint_line}
Representative failure ({test_name}):
{message}

Other tests in this cluster: {other_tests}

In 2-3 sentences, give your best hypothesis for the likely root cause. Be
specific about what kind of bug this looks like (off-by-one, wrong return
value, dropped data, etc.) based on the evidence shown - don't just restate
the failure. If the evidence is too thin to guess confidently, say so rather
than inventing a cause."""


class SummarizerNotConfigured(RuntimeError):
    pass


@dataclass
class ClusterSummary:
    hypothesis: str
    model: str


def build_prompt(cluster: FailureCluster) -> str:
    rep = cluster.representative
    other = sorted({f.node_id for f in cluster.failures if f.node_id != rep.node_id})
    hint_line = f"pytest identified the directly-involved function as: {cluster.call_hint}()\n" if cluster.call_hint else ""
    return PROMPT_TEMPLATE.format(
        count=cluster.size,
        files=", ".join(sorted(cluster.covered_files)) or "(no coverage data recorded for these tests)",
        hint_line=hint_line,
        test_name=rep.node_id,
        message=rep.message.strip()[:1000],
        other_tests=", ".join(other[:10]) + (f", +{len(other) - 10} more" if len(other) > 10 else "") if other else "(none)",
    )


def summarize_cluster(cluster: FailureCluster) -> ClusterSummary:
    if not settings.gemini_api_key:
        raise SummarizerNotConfigured("GEMINI_API_KEY is not set (check .env)")

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(model=MODEL, contents=build_prompt(cluster))
    return ClusterSummary(hypothesis=response.text.strip(), model=MODEL)
