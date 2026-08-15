"""Tests for genome and tradition_dna — ported from the Rust test suites
in genome.rs and tradition_dna.rs."""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from genome import N_GENES, MusicalGenome
from tradition_dna import (
    TRADITION_GENOMES,
    TRADITION_NAMES,
    decode_tradition,
    encode_tradition,
)


def _make_rng():
    return random.Random(42)


# --- genome.rs tests ---


def test_new_valid():
    genes = [i * 0.2 for i in range(25)]
    g = MusicalGenome(genes)
    assert len(g.genes) == 25


def test_new_wrong_length():
    with pytest.raises(ValueError):
        MusicalGenome([1.0] * 10)


def test_clamping():
    genes = [10.0] * 25
    g = MusicalGenome(genes)
    assert all(v <= 5.0 for v in g.genes)


def test_dial_position():
    g = MusicalGenome.zeros()
    h, r, s = g.dial_position()
    assert abs(h - 0.0) < 1e-10
    assert abs(r - 0.0) < 1e-10
    assert abs(s - 0.0) < 1e-10


def test_gene_blocks():
    genes = [0.0] * 25
    genes[0:8] = [1.0] * 8
    genes[8:16] = [2.0] * 8
    genes[16:24] = [3.0] * 8
    genes[24] = 4.0
    g = MusicalGenome(genes)
    assert all(abs(v - 1.0) < 1e-10 for v in g.harmonic_genes())
    assert all(abs(v - 2.0) < 1e-10 for v in g.rhythmic_genes())
    assert all(abs(v - 3.0) < 1e-10 for v in g.spectral_genes())
    assert abs(g.metadata_gene() - 4.0) < 1e-10


def test_fitness():
    genes = [0.0] * 25
    genes[0:8] = [2.5] * 8
    genes[8:16] = [2.5] * 8
    genes[16:24] = [2.5] * 8
    g = MusicalGenome(genes)
    f = g.fitness((2.5, 2.5, 2.5))
    assert f < 1e-10, f"fitness should be ~0, got {f}"


def test_from_tradition():
    g = MusicalGenome.from_tradition("Jazz", _make_rng())
    h, r, s = g.dial_position()
    # Should be roughly around (3.2, 2.8, 2.5)
    assert 2.0 < h < 4.5, f"h={h}"
    assert 1.5 < r < 4.0, f"r={r}"


def test_from_unknown_tradition():
    with pytest.raises(ValueError):
        MusicalGenome.from_tradition("NonExistent", _make_rng())


def test_random():
    g = MusicalGenome.random(_make_rng())
    assert all(0.0 <= v <= 5.0 for v in g.genes)


def test_copy():
    import copy

    g = MusicalGenome.zeros()
    g2 = copy.copy(g)
    assert g == g2


def test_display():
    g = MusicalGenome.zeros()
    assert "MusicalGenome" in str(g)


# --- tradition_dna.rs tests ---


def test_encode_tradition():
    g = encode_tradition("Test", (2.5, 2.5, 2.5), 0.3, _make_rng())
    h, r, s = g.dial_position()
    # Should be roughly near (2.5, 2.5, 2.5)
    assert 1.0 < h < 4.0


def test_decode_tradition():
    g = MusicalGenome.zeros()
    info = decode_tradition(g)
    assert len(info.harmonic_genes) == 8
    assert len(info.rhythmic_genes) == 8
    assert len(info.spectral_genes) == 8


def test_tradition_genomes():
    assert "Jazz" in TRADITION_GENOMES
    assert "NonExistent" not in TRADITION_GENOMES
    assert len(TRADITION_GENOMES) == 10


def test_tradition_names():
    assert len(TRADITION_NAMES) == 10
    assert "Jazz" in TRADITION_NAMES


def test_tradition_genomes_dial_positions():
    # Each pre-built genome should sit near its documented dial centre.
    from genome import TRADITION_CENTRES

    for name, centre in TRADITION_CENTRES:
        pos = TRADITION_GENOMES[name].dial_position()
        for got, want in zip(pos, centre):
            assert abs(got - want) < 1.0, f"{name}: {got} vs {want}"


def test_metadata_gene_is_deterministic():
    g1 = encode_tradition("Jazz", (3.2, 2.8, 2.5), 0.3, random.Random(7))
    g2 = encode_tradition("Jazz", (3.2, 2.8, 2.5), 0.3, random.Random(99))
    # Metadata gene derives from the name hash, not the rng.
    assert g1.metadata_gene() == g2.metadata_gene()
    assert 0.0 <= g1.metadata_gene() <= 5.0
