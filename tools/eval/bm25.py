"""BM25 (Okapi) без зависимостей: базовое решение «поиск по ключевым словам» (evaluation.md §5)."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def score(self, query: Sequence[str], i: int) -> float:
        tf, dl = self.tf[i], self.len[i]
        total = 0.0
        for w in query:
            f = tf.get(w, 0)
            if not f:
                continue
            norm = f + self.k1 * (1 - self.b + self.b * dl / self.avg) if self.avg else f
            total += self.idf.get(w, 0.0) * f * (self.k1 + 1) / norm
        return total

    def scores(self, query: Sequence[str]) -> list[float]:
        return [self.score(query, i) for i in range(len(self.tf))]
