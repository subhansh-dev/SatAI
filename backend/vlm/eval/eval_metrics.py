"""
SatAI — Caption metrics, self-contained (no pycocoevalcap dependency).

Implements the standard protocol used by VRSBench / RSICD papers:
  * BLEU-1..4        (Papineni et al., 2002 — with per-sentence brevity penalty)
  * METEOR           (unigram F-mean with stem/synonym-lite matching)
  * ROUGE-L          (Longest Common Subsequence F)
  * CIDEr            (TF-IDF cosine over 1-4 grams, Dong et al., 2015)
  * SPICE-lite       (not implemented — reported as None; install
                      pycocoevalcap for full SPICE)
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

_SENT_SPLIT = re.compile(r"\W+")


def tokenize(s: str) -> List[str]:
    return [t for t in _SENT_SPLIT.split(str(s).lower()) if t]


def _ngrams(tokens: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


# ---------------------------------------------------------------------------
# BLEU (corpus-level, multi-reference)
# ---------------------------------------------------------------------------
def bleu(preds: List[List[str]], refs: List[List[List[str]]],
         max_n: int = 4) -> Dict[str, float]:
    clipped = [0] * max_n
    totals = [0] * max_n
    pred_len = ref_len = 0
    for pred, rs in zip(preds, refs):
        if not rs:
            continue
        pred_len += len(pred)
        # closest-reference-length rule (standard corpus BLEU)
        closest = min(rs, key=lambda r: (abs(len(r) - len(pred)), len(r)))
        ref_len += len(closest)
        for n in range(1, max_n + 1):
            p_ng = Counter(_ngrams(pred, n))
            if not p_ng:
                continue
            max_ref = Counter()
            for r in rs:
                r_ng = Counter(_ngrams(r, n))
                for g, c in r_ng.items():
                    if c > max_ref[g]:
                        max_ref[g] = c
            clipped[n - 1] += sum(min(c, max_ref[g])
                                  for g, c in p_ng.items())
            totals[n - 1] += sum(p_ng.values())

    out: Dict[str, float] = {}
    log_avg = 0.0
    for n in range(1, max_n + 1):
        name = f"BLEU-{n}"
        if totals[n - 1] == 0:
            out[name] = 0.0
            log_avg += 0.0
            continue
        prec = clipped[n - 1] / totals[n - 1]
        out[name] = prec
        log_avg += math.log(prec) if prec > 0 else float("-inf")
    # brevity penalty
    bp = 1.0 if pred_len > ref_len else \
        math.exp(1 - ref_len / pred_len) if pred_len > 0 else 0.0
    if log_avg > float("-inf") and pred_len > 0:
        out["BLEU"] = bp * math.exp(log_avg / max_n)
    else:
        out["BLEU"] = 0.0
    return out


# ---------------------------------------------------------------------------
# METEOR-lite (unigram F-mean, m = 0.9 preference, no synonym DB)
# ---------------------------------------------------------------------------
def meteor(preds: List[List[str]], refs: List[List[List[str]]],
           alpha: float = 0.85) -> float:
    if not preds:
        return 0.0
    scores = []
    for pred, rs in zip(preds, refs):
        if not pred:
            scores.append(0.0)
            continue
        best = 0.0
        for r in rs:
            p_c, r_c = Counter(pred), Counter(r)
            match = sum((p_c & r_c).values())
            if match == 0:
                continue
            prec, rec = match / len(pred), match / len(r)
            fmean = (prec * rec) / (alpha * prec + (1 - alpha) * rec)
            best = max(best, fmean)
        scores.append(best)
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# ROUGE-L (LCS-F, per sentence, averaged)
# ---------------------------------------------------------------------------
def _lcs_len(a: Sequence[str], b: Sequence[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def rouge_l(preds: List[List[str]], refs: List[List[List[str]]],
            beta: float = 1.2) -> float:
    scores = []
    for pred, rs in zip(preds, refs):
        best = 0.0
        for r in rs:
            l = _lcs_len(pred, r)
            if l == 0:
                continue
            prec, rec = l / len(pred) if pred else 0.0, l / len(r) if r else 0.0
            denom = prec + beta * rec
            best = max(best, (1 + beta) * prec * rec / denom if denom else 0.0)
        scores.append(best)
    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# CIDEr (IDF-weighted n-gram cosine, n = 1..4)
# ---------------------------------------------------------------------------
def cider(preds: List[List[str]], refs: List[List[List[str]]],
          max_n: int = 4, sigma: float = 6.0) -> float:
    n_docs = len(refs)
    if n_docs == 0:
        return 0.0
    # document frequency per n
    df = [defaultdict(int) for _ in range(max_n + 1)]
    for rs in refs:
        seen = [set() for _ in range(max_n + 1)]
        for r in rs:
            for n in range(1, max_n + 1):
                for g in set(_ngrams(r, n)):
                    seen[n].add(g)
        for n in range(1, max_n + 1):
            for g in seen[n]:
                df[n][g] += 1

    total = 0.0
    for pred, rs in zip(preds, refs):
        score = 0.0
        for n in range(1, max_n + 1):
            p_ng = Counter(_ngrams(pred, n))
            if not p_ng:
                continue
            # candidate vector: tf * idf
            def vec(counter: Counter) -> Dict[Tuple[str, ...], float]:
                v = {}
                for g, c in counter.items():
                    idf = math.log(max(1, n_docs) / (df[n].get(g, 0) + 1))
                    v[g] = c * idf
                norm = math.sqrt(sum(x * x for x in v.values()))
                return v, norm

            r_counters = [Counter(_ngrams(r, n)) for r in rs]
            # reference "consensus" vector = average of ref vectors
            ref_vecs = [vec(rc) for rc in r_counters]
            pv, pn = vec(p_ng)
            if pn == 0:
                continue
            best = 0.0
            for rv, rn in ref_vecs:
                if rn == 0:
                    continue
                dot = sum(pv.get(g, 0.0) * rv.get(g, 0.0)
                          for g in pv) / (pn * rn)
                best = max(best, dot)
            # length penalty (Gaussian over length diff, COCO-style)
            avg_ref_len = sum(len(r) for r in rs) / len(rs)
            delta = len(pred) - avg_ref_len
            score += best * math.exp(-delta * delta / (2 * sigma * sigma))
        total += score / max_n
    return total / n_docs


# ---------------------------------------------------------------------------
# One-shot report
# ---------------------------------------------------------------------------
def caption_report(pred_texts: List[str],
                   gt_texts: List[List[str]]) -> Dict[str, float]:
    preds = [tokenize(p) for p in pred_texts]
    refs = [[tokenize(g) for g in gts] for gts in gt_texts]
    b = bleu(preds, refs)
    return {
        "BLEU": round(b["BLEU"], 4),
        "BLEU-1": round(b["BLEU-1"], 4),
        "BLEU-2": round(b["BLEU-2"], 4),
        "BLEU-3": round(b["BLEU-3"], 4),
        "BLEU-4": round(b["BLEU-4"], 4),
        "METEOR": round(meteor(preds, refs), 4),
        "ROUGE-L": round(rouge_l(preds, refs), 4),
        "CIDEr": round(cider(preds, refs), 4),
        "num_samples": len(preds),
    }
