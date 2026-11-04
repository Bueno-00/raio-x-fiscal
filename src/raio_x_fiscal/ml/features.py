"""Text features for product descriptions: word + character TF-IDF, float32, sparse.

Word n-grams capture vocabulary ('arroz', 'parafuso canulado'); character n-grams (inside
word boundaries) survive typos, abbreviations and glued units ('2,5mm2', 'desc est'), which
are everywhere in supplier-typed descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer

from raio_x_fiscal.pipeline.normalize import normalize_description


@dataclass
class TextFeaturizer:
    word_max_features: int = 150_000
    char_max_features: int = 250_000
    word_min_df: int = 2
    char_min_df: int = 3
    word: TfidfVectorizer = field(init=False, repr=False)
    char: TfidfVectorizer = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.word = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=self.word_min_df,
            max_features=self.word_max_features,
            sublinear_tf=True,
            dtype=np.float32,
            token_pattern=r"(?u)\b\w+\b",
        )
        self.char = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=self.char_min_df,
            max_features=self.char_max_features,
            sublinear_tf=True,
            dtype=np.float32,
        )

    @staticmethod
    def prepare(texts: list[str] | np.ndarray) -> list[str]:
        """Apply the same normalisation the silver layer applied (idempotent on silver text)."""
        return [normalize_description(t) for t in texts]

    def fit_transform(self, texts: list[str]) -> sp.csr_matrix:
        xw = self.word.fit_transform(texts)
        xc = self.char.fit_transform(texts)
        return sp.hstack([xw, xc], format="csr", dtype=np.float32)

    def transform(self, texts: list[str]) -> sp.csr_matrix:
        xw = self.word.transform(texts)
        xc = self.char.transform(texts)
        return sp.hstack([xw, xc], format="csr", dtype=np.float32)

    @property
    def n_features(self) -> int:
        return len(self.word.vocabulary_) + len(self.char.vocabulary_)
