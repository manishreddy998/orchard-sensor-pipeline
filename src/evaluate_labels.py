"""Score the label assistant on a hand-labelled question set (data/public/label_gold.csv)."""
import json
import time

import pandas as pd

from src.config import RESULTS
from src.label_qa import answer, load_label, LABELS


def run() -> dict:
    gold = pd.read_csv("data/public/label_gold.csv").fillna("")
    for p in LABELS:
        load_label(p)  # parse PDFs once, outside the timing
    rows, t0 = [], time.perf_counter()
    for g in gold.itertuples():
        a = answer(g.question)
        ok_status = a.status == g.expected_status
        if g.expected_status == "answered":
            ok_page = ok_status and a.pdf_page == int(g.expected_page)
            ok_text = ok_status and g.expected_contains.lower() in (a.quote or "").lower()
            correct = ok_page and ok_text and a.quote_verified
        else:
            ok_page = ok_text = correct = ok_status
        rows.append({"question": g.question, "expected": g.expected_status, "got": a.status,
                     "pdf_page": a.pdf_page, "expected_page": g.expected_page, "quote": a.quote,
                     "verified": a.quote_verified, "reason": a.reason, "correct": correct})
    elapsed = time.perf_counter() - t0
    df = pd.DataFrame(rows)
    ans = df[df.expected == "answered"]
    ref = df[df.expected == "refused"]
    answered = df[df.got == "answered"]
    stats = {
        "labels_indexed": len(LABELS),
        "label_pages_indexed": int(sum(max(p for p, _ in load_label(x)) for x in LABELS)),
        "questions": len(df),
        "answerable_questions": len(ans),
        "unanswerable_questions": len(ref),
        "answer_correct_with_exact_page": int(ans.correct.sum()),
        "answer_accuracy": round(float(ans.correct.mean()), 4),
        "correct_refusals": int(ref.correct.sum()),
        "wrong_answers_given": int(((df.got == "answered") & ~df.correct).sum()),
        "quotes_verified_on_page": int(answered.verified.sum()),
        "quotes_given": len(answered),
        "avg_ms_per_question": round(1000 * elapsed / len(df), 2),
    }
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / "label_qa_answers.csv", index=False)
    (RESULTS / "label_qa_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    s = run()
    print(json.dumps(s, indent=2))
    df = pd.read_csv(RESULTS / "label_qa_answers.csv")
    print(df[~df.correct][["question", "got", "pdf_page", "expected_page", "quote", "reason"]].to_string())
