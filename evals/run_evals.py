"""AI evals for the Mastercard Spec Advisor RAG pipeline.

Three kinds of checks, from most to least rigorous:

1. RBAC leakage (deterministic, hard pass/fail). For every "restricted"
   category question: a general_user retrieval must NEVER include a chunk
   tagged sensitivity=restricted, while a compliance_officer retrieval
   should be able to. This is a security invariant, not a quality
   judgment — a failure here means the access-control filter itself is
   broken, not that an answer was merely mediocre. The script exits
   non-zero if this ever fails, so it can gate CI.

2. Faithfulness (LLM-as-judge, 1-5). For every question, Claude grades
   whether the generated answer is actually supported by the retrieved
   context, i.e. whether the model is hallucinating beyond what it
   retrieved.

3. Abstention (LLM-as-judge, pass/fail). For "out_of_scope" questions
   (content this knowledge base doesn't cover), checks that the assistant
   said so rather than fabricating a confident-sounding answer.

Usage:
    python evals/run_evals.py

Writes evals/report.md and prints a summary. Exits 1 if any RBAC leakage
is detected.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
import rag  # noqa: E402

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

TESTSET_PATH = Path(__file__).parent / "testset.jsonl"
REPORT_PATH = Path(__file__).parent / "report.md"

JUDGE_MODEL = rag.GENERATION_MODEL  # same cost-effective model; see README note

FAITHFULNESS_PROMPT = """You are grading whether an AI assistant's answer is faithful to the provided context (no hallucination, no claims unsupported by the context).

CONTEXT:
{context}

QUESTION:
{question}

ANSWER TO GRADE:
{answer}

Respond with ONLY a JSON object, no markdown fences, no prose:
{{"faithfulness_score": <int 1-5>, "cites_pages": <true|false>, "reasoning": "<one sentence>"}}

Scoring guide: 5 = every claim directly supported by context with accurate citations. 3 = mostly supported but some vague/unsupported claims. 1 = largely fabricated or ignores context."""

ABSTENTION_PROMPT = """You are grading whether an AI assistant appropriately recognized it lacks sufficient information to answer, rather than fabricating an answer not supported by the context.

CONTEXT PROVIDED TO THE ASSISTANT:
{context}

QUESTION:
{question}

ANSWER TO GRADE:
{answer}

Respond with ONLY a JSON object, no markdown fences, no prose:
{{"abstained": <true|false>, "reasoning": "<one sentence>"}}"""


def load_testset():
    with open(TESTSET_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def judge(prompt: str) -> dict:
    client = rag.get_claude_client()
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            text = rest if first_line.lower().startswith("json") else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "unparsable_judge_output", "raw": text}


def run():
    testset = load_testset()
    results = []
    leakage_failures = []
    mistargeted_restricted = []

    for item in testset:
        qid, question, category = item["id"], item["question"], item["category"]
        print(f"[{qid}] ({category}) {question}")

        general_results, general_hidden = rag.retrieve(question, allow_restricted=False)
        compliance_results, _ = rag.retrieve(question, allow_restricted=True)

        general_sensitivities = [m.get("sensitivity") for m in general_results["metadatas"][0]]
        compliance_sensitivities = [m.get("sensitivity") for m in compliance_results["metadatas"][0]]

        if category == "restricted":
            if "restricted" in general_sensitivities:
                leakage_failures.append(qid)
            if "restricted" not in compliance_sensitivities:
                # Test-design issue, not a product bug: this question didn't
                # actually hit restricted content, so the leakage check for
                # it is vacuous.
                mistargeted_restricted.append(qid)

        context = rag.format_context(compliance_results)
        try:
            answer = rag.generate_answer(question, context)
        except Exception as e:
            answer = f"[generation error: {e}]"

        record = {
            "id": qid,
            "category": category,
            "question": question,
            "answer": answer,
            "general_hidden_count": general_hidden,
            "general_sensitivities": general_sensitivities,
            "compliance_sensitivities": compliance_sensitivities,
        }

        record["faithfulness"] = judge(
            FAITHFULNESS_PROMPT.format(context=context, question=question, answer=answer)
        )

        if category == "out_of_scope":
            record["abstention"] = judge(
                ABSTENTION_PROMPT.format(context=context, question=question, answer=answer)
            )

        results.append(record)

    write_report(results, leakage_failures, mistargeted_restricted)

    if mistargeted_restricted:
        print(
            f"\nNote: {len(mistargeted_restricted)} 'restricted' test question(s) "
            f"didn't retrieve any restricted content even at full access: "
            f"{mistargeted_restricted}. Consider revising those questions in testset.jsonl."
        )

    if leakage_failures:
        print(f"\nFAILED: RBAC leakage detected on {len(leakage_failures)} question(s): {leakage_failures}")
        sys.exit(1)

    print("\nAll RBAC leakage checks passed.")


def write_report(results, leakage_failures, mistargeted_restricted):
    faithfulness_scores = [
        r["faithfulness"].get("faithfulness_score")
        for r in results
        if isinstance(r["faithfulness"].get("faithfulness_score"), (int, float))
    ]
    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else None

    out_of_scope = [r for r in results if r["category"] == "out_of_scope"]
    abstained_count = sum(1 for r in out_of_scope if r.get("abstention", {}).get("abstained") is True)

    lines = [
        f"# Eval Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- Questions evaluated: {len(results)}",
        f"- RBAC leakage failures: {len(leakage_failures)} {'FAIL' if leakage_failures else 'PASS (none)'}",
        f"- Mistargeted 'restricted' test questions (no restricted content found even at full access): {len(mistargeted_restricted)}",
        (
            f"- Average faithfulness score (1-5): {avg_faithfulness:.2f}"
            if avg_faithfulness is not None
            else "- Average faithfulness score: N/A"
        ),
        f"- Correct abstention on out-of-scope questions: {abstained_count}/{len(out_of_scope)}",
        "",
        "| ID | Category | Question | Faithfulness | Abstained? | RBAC leak? |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        faith = r["faithfulness"].get("faithfulness_score", "?")
        abst = r.get("abstention", {}).get("abstained", "-")
        leak = "FAIL" if r["id"] in leakage_failures else ("-" if r["category"] != "restricted" else "pass")
        question_short = r["question"][:60].replace("|", "/")
        lines.append(f"| {r['id']} | {r['category']} | {question_short} | {faith} | {abst} | {leak} |")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    run()
