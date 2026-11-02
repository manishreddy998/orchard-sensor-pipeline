"""Cited pesticide-label Q&A over public EPA label PDFs.

Every answer is a verbatim quote from the label with the PDF page it came from. If the product,
the crop section or the rule cannot be found on the label, the assistant refuses instead of guessing.

The answerer is extractive on purpose: label rules (pre-harvest interval, re-entry interval,
seasonal maximums) are legal text, so the quote itself is the answer. A language model can be
placed on top to phrase the reply, but it never supplies the number.
"""
import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache

import pdfplumber

from src.config import LABELS, PUBLIC

SECTION_LINES = 150

CROP_HEADERS = {
    # specific headers first, then the shared pome fruit crop group
    "apple": [r"^APPLES\b", r"^(Fruit, Pome|Pome Fruits?) \(Crop Group 11-10\)"],
    "pear": [r"^PEARS\b", r"^(Fruit, Pome|Pome Fruits?) \(Crop Group 11-10\)"],
}
CROP_WORDS = {"apple": r"\bapples?\b", "pear": r"\bpears?\b"}

INTENTS = {
    # intent: (question pattern, label pattern, scope)
    "pre_harvest_interval": (r"pre-?harvest|PHI|before harvest|days? (of|before) harvest",
                             r"within \d+ days of\s*harvest|not apply within \d+ days\b", "crop"),
    "max_applications": (r"how many (applications|sprays|times)|number of applications|max(imum)? applications",
                         r"Maximum Number of Applications|more than (\w+|\d+)\s*applications( of [\w ]+)? per (acre per )?(calendar )?(year|season)", "crop"),
    "max_total_per_year": (r"total|how much .* (per|a) (year|season)|maximum (amount|rate) per (year|season)",
                           r"more than (a total of )?\d[\d /]*\s*(oz|fl|lb).*per acre per (crop season|year)|"
                           r"total of \d[\d /]*\s*(fl|oz|lb)", "crop"),
    "retreatment_interval": (r"re-?treat|days apart|between (applications|sprays)|spray interval",
                             r"Re-?[Tt]reatment\s*Interval|less than \d+ days apart|Interval: \d+ days", "crop"),
    "degree_day_timing": (r"degree.?days?|\bDD\b|when (should|do) I (spray|apply)|timing",
                          r"degree-days|\d+ DD\b|\bDD, base", "crop"),
    "hand_harvest": (r"hand.?harvest|pick by hand|harvest crews?",
                     r"Hand-Harvesting is prohibited", "crop"),
    "u_pick": (r"u-?pick|pick-your-own|public",
               r"pick-your-own|U-pick", "crop"),
    "mating_disruption": (r"mating disruption|pheromone",
                          r"mating disruption", "crop"),
    "resistance": (r"resistance|consecutive|in a row",
                   r"consecutive applications", "crop"),
    "restricted_entry_interval": (r"re-?entry|REI\b|restricted.entry|go back in|workers? (back|enter)",
                                  r"restricted.entry interval \(REI\) of \d+", "crop_then_label"),
}


@dataclass
class Answer:
    question: str
    status: str  # answered | refused
    product: str | None = None
    crop: str | None = None
    intent: str | None = None
    quote: str | None = None
    pdf_page: int | None = None
    label_file: str | None = None
    quote_verified: bool = False
    reason: str | None = None


def _clean(t: str) -> str:
    return t.replace("(cid:120)", "•").replace("\u00a0", " ")


@lru_cache(maxsize=None)
def load_label(product: str) -> list[tuple[int, str]]:
    """Return every non-empty line on the label as (pdf_page, text)."""
    path = PUBLIC / "labels" / LABELS[product]["file"]
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            for line in _clean(page.extract_text() or "").splitlines():
                if line.strip():
                    out.append((i, line.strip()))
    return out


@lru_cache(maxsize=None)
def page_text(product: str, page: int) -> str:
    return "\n".join(t for p, t in load_label(product) if p == page)


def detect_product(q: str) -> str | None:
    for name in LABELS:
        base = name.split()[0]
        if re.search(rf"\b{re.escape(base)}\b", q, re.I):
            return name
    return None


def detect_crop(q: str) -> str | None:
    for crop, pat in CROP_WORDS.items():
        if re.search(pat, q, re.I):
            return crop
    return None


def detect_intent(q: str) -> str | None:
    for intent, (qpat, _, _) in INTENTS.items():
        if re.search(qpat, q, re.I):
            return intent
    return None


def crop_section(product: str, crop: str, pattern: str | None = None) -> list[tuple[int, str]] | None:
    """Lines under the crop's use-directions header.

    A crop name can also appear in a crop list or table of contents, so when a rule pattern is given
    the first header whose section actually contains that rule wins.
    """
    lines = load_label(product)
    found = None
    for pat in CROP_HEADERS[crop]:
        for idx, (_, text) in enumerate(lines):
            if re.search(pat, text):
                section = lines[idx: idx + SECTION_LINES]
                found = found or section
                if pattern is None or any(True for _ in _windows(section, pattern)):
                    return section
    return found


def _windows(lines, pattern):
    """Yield the shortest quote (one line, else two lines) that matches at each position."""
    for i in range(len(lines)):
        if re.search(pattern, lines[i][1], re.I):
            yield lines[i: i + 1]
        elif i + 1 < len(lines) and re.search(pattern, lines[i][1] + " " + lines[i + 1][1], re.I):
            yield lines[i: i + 2]


def find(lines, pattern, prefer: str | None = None):
    hits = list(_windows(lines, pattern))
    if prefer:
        preferred = [w for w in hits if re.search(prefer, " ".join(t for _, t in w), re.I)]
        hits = preferred or hits
    return hits[0] if hits else None


def answer(question: str) -> Answer:
    a = Answer(question=question, status="refused")
    a.product = detect_product(question)
    if not a.product:
        a.reason = "product is not one of the indexed labels"
        return a
    a.intent = detect_intent(question)
    if not a.intent:
        a.reason = "question is not about a rule printed on the label"
        return a
    a.crop = detect_crop(question)
    _, pattern, scope = INTENTS[a.intent]
    prefer = r"West of the Rockies" if re.search(r"west|british columbia|\bBC\b|okanagan", question, re.I) else None

    hit = None
    if a.crop:
        section = crop_section(a.product, a.crop, pattern)
        if section is None:
            a.reason = f"no {a.crop} section on the {a.product} label"
            return a
        hit = find(section, pattern, prefer)
    elif scope == "crop":
        a.reason = "crop not given; label rules differ by crop"
        return a
    if hit is None and scope == "crop_then_label":
        hit = find(load_label(a.product), pattern, prefer)
    if hit is None:
        a.reason = "rule not found on the label"
        return a

    a.status = "answered"
    a.pdf_page = hit[0][0]
    a.quote = " ".join(t for _, t in hit)
    a.label_file = LABELS[a.product]["file"]
    # every quoted line must exist verbatim on the cited page(s)
    a.quote_verified = all(t in page_text(a.product, p) for p, t in hit)
    return a


if __name__ == "__main__":
    import sys
    print(json.dumps(asdict(answer(" ".join(sys.argv[1:]))), indent=2))
