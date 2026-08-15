"""Tradition DNA — encode/decode musical traditions as genomes.

Ported from flux-genome-rs/src/tradition_dna.rs.
"""

import random
from dataclasses import dataclass, field

from genome import N_GENES, TRADITION_CENTRES, MusicalGenome, clip

# Names of the 10 recognised musical traditions.
TRADITION_NAMES = [name for name, _ in TRADITION_CENTRES]

_MASK64 = 0xFFFFFFFFFFFFFFFF


def _name_hash(name: str) -> int:
    """Wrapping u64 hash of a tradition name (matches the Rust port)."""
    h = 0
    for b in name.encode("utf-8"):
        h = (h * 31 + b) & _MASK64
    return h


def encode_tradition(
    name: str,
    dial_center: tuple,
    spread: float,
    rng: random.Random,
) -> MusicalGenome:
    """Encode a tradition as a MusicalGenome with controlled variation.

    Each 8-gene block is sampled from N(dial_center component, spread),
    clamped to [0, 5].
    """
    arr = [0.0] * N_GENES
    for block_start, c in (
        (0, dial_center[0]),
        (8, dial_center[1]),
        (16, dial_center[2]),
    ):
        for i in range(8):
            arr[block_start + i] = clip(c + rng.gauss(0.0, spread), 0.0, 5.0)
    # Use hash of name for metadata gene (deterministic marker)
    arr[24] = (_name_hash(name) % 500) / 100.0
    return MusicalGenome(arr)


@dataclass
class TraditionInfo:
    """Summary of a decoded tradition genome."""

    dial_position: tuple
    harmonic_genes: list = field(default_factory=list)
    rhythmic_genes: list = field(default_factory=list)
    spectral_genes: list = field(default_factory=list)
    metadata: float = 0.0


def decode_tradition(genome: MusicalGenome) -> TraditionInfo:
    """Decode a genome into a tradition-like summary."""
    return TraditionInfo(
        dial_position=genome.dial_position(),
        harmonic_genes=genome.harmonic_genes(),
        rhythmic_genes=genome.rhythmic_genes(),
        spectral_genes=genome.spectral_genes(),
        metadata=genome.metadata_gene(),
    )


def _build_tradition_genomes() -> dict:
    """Initialise all tradition genomes with deterministic seeds."""
    genomes = {}
    for i, (name, centre) in enumerate(TRADITION_CENTRES):
        rng = random.Random(i)
        genomes[name] = encode_tradition(name, centre, 0.3, rng)
    return genomes


# Pre-built genomes for the 10 traditions.
TRADITION_GENOMES = _build_tradition_genomes()
