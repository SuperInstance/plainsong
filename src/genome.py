"""Musical genome — encoding a tradition's position in dial space.

A genome is a vector of 25 genes (floats in [0, 5]) organized as:
- harmonic genes (indices 0-7): harmonic tension
- rhythmic genes (indices 8-15): rhythmic complexity
- spectral genes (indices 16-23): spectral density
- metadata gene (index 24): generation/parent info

The phenotype (dial position) is ``(h, r, s)`` where each component is the
mean of its 8-gene block.

Ported from flux-genome-rs/src/genome.rs.
"""

# `MusicalGenome.random` is a classmethod, which shadows the `random` module
# for the remainder of the class body -- so a later `rng: random.Random`
# annotation resolves to the classmethod and raises at import. Deferring
# annotations means they are never evaluated there, and the method keeps its
# name.
from __future__ import annotations

import math
import random

# Number of genes in a MusicalGenome.
N_GENES = 25

# Approximate dial centres for the 10 traditions (harmonic, rhythmic, spectral).
TRADITION_CENTRES = [
    ("Jazz", (3.2, 2.8, 2.5)),
    ("Classical", (1.8, 1.2, 1.5)),
    ("Rock", (3.5, 3.8, 3.0)),
    ("Blues", (3.0, 2.5, 2.0)),
    ("Electronic", (3.8, 4.0, 4.5)),
    ("Hindustani", (2.5, 3.2, 1.8)),
    ("Gamelan", (2.0, 3.5, 2.2)),
    ("Gagaku", (1.5, 1.8, 1.0)),
    ("WestAfrican", (2.8, 4.2, 2.8)),
    ("FreeImprovisation", (4.0, 3.5, 3.8)),
]


def clip(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


class MusicalGenome:
    """A genome encoding a musical tradition's position in dial space."""

    def __init__(self, genes) -> None:
        """Create a new genome from a sequence of 25 values, clamped to [0, 5].

        Raises ValueError if ``genes`` does not have exactly 25 elements.
        """
        genes = list(genes)
        if len(genes) != N_GENES:
            raise ValueError(f"genes must have {N_GENES} elements")
        self._genes = [clip(float(g), 0.0, 5.0) for g in genes]

    @classmethod
    def zeros(cls) -> "MusicalGenome":
        """Create a genome with all zeros."""
        g = cls.__new__(cls)
        g._genes = [0.0] * N_GENES
        return g

    @classmethod
    def random(cls, rng: random.Random) -> "MusicalGenome":
        """Create a random genome with values uniformly in [0, 5)."""
        g = cls.__new__(cls)
        g._genes = [rng.uniform(0.0, 5.0) for _ in range(N_GENES)]
        return g

    @classmethod
    def from_tradition(cls, name: str, rng: random.Random) -> "MusicalGenome":
        """Create a genome from a known tradition's dial position.

        Fills each 8-gene block around the tradition's centre with small
        Gaussian variation (sigma = 0.3). Raises ValueError for unknown names.
        """
        centre = None
        for n, c in TRADITION_CENTRES:
            if n == name:
                centre = c
                break
        if centre is None:
            raise ValueError(f"Unknown tradition '{name}'")

        arr = [0.0] * N_GENES
        for block_start, c in ((0, centre[0]), (8, centre[1]), (16, centre[2])):
            for i in range(8):
                arr[block_start + i] = clip(c + rng.gauss(0.0, 0.3), 0.0, 5.0)
        return cls(arr)

    @property
    def genes(self) -> list:
        """Get the full gene array."""
        return list(self._genes)

    def harmonic_genes(self) -> list:
        """Harmonic genes (indices 0-7)."""
        return self._genes[0:8]

    def rhythmic_genes(self) -> list:
        """Rhythmic genes (indices 8-15)."""
        return self._genes[8:16]

    def spectral_genes(self) -> list:
        """Spectral genes (indices 16-23)."""
        return self._genes[16:24]

    def metadata_gene(self) -> float:
        """Metadata gene (index 24)."""
        return self._genes[24]

    def set_metadata_gene(self, value: float) -> None:
        """Set the metadata gene, clamped to [0, 5]."""
        self._genes[24] = clip(value, 0.0, 5.0)

    def dial_position(self) -> tuple:
        """Express genes as a 3D dial position (harmonic, rhythmic, spectral).

        Each component is the mean of its 8-gene block.
        """
        h = sum(self._genes[0:8]) / 8.0
        r = sum(self._genes[8:16]) / 8.0
        s = sum(self._genes[16:24]) / 8.0
        return (h, r, s)

    def fitness(self, target_dial: tuple) -> float:
        """Euclidean distance in dial space to a target dial position.

        Lower is better. f = sqrt((h-ht)^2 + (r-rt)^2 + (s-st)^2)
        """
        pos = self.dial_position()
        dh = pos[0] - target_dial[0]
        dr = pos[1] - target_dial[1]
        ds = pos[2] - target_dial[2]
        return math.sqrt(dh * dh + dr * dr + ds * ds)

    def __eq__(self, other) -> bool:
        if not isinstance(other, MusicalGenome):
            return NotImplemented
        return all(
            abs(a - b) < 1e-10 for a, b in zip(self._genes, other._genes)
        )

    def __repr__(self) -> str:
        h, r, s = self.dial_position()
        return f"MusicalGenome(dial=({h:.2f}, {r:.2f}, {s:.2f}))"

    __str__ = __repr__
