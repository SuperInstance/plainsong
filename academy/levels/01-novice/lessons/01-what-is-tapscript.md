# TapScript Lesson 01: What is TapScript? (Novice)

## (1) Before You Start
- Know basic Bitcoin: transactions, inputs/outputs, locking scripts (scriptPubKey).
- Know that Bitcoin Script is a stack-based language; TapScript is its Taproot upgrade.
- A running TapScript compiler/simulator at `http://localhost:5557` (POST JSON with `{"script": "..."}`).

## (2) The Concept — Simply
TapScript is Bitcoin Script for **Taproot** — a 2021 upgrade. Think of it as a "smart contract lite": a small, non-Turing-complete program that locks Bitcoin. You write conditions (e.g., "spend only if signed by key X"). Unlike legacy Script, TapScript:
- Uses **32-byte public keys** (Schnorr), not 33-byte.
- Runs under **Taproot's key-path** (simple single-key) or **script-path** (complex conditions, hidden until used).
- Has **no `OP_CHECKSIG` ambiguity** — it uses `OP_CHECKSIG` (not `CHECKSIGVERIFY` variants) and is more restrictive (no `OP_CODESEPARATOR`).
- Is **cheaper** and more private: unused branches are invisible.

For a novice: TapScript = "if-then" rules for spending Bitcoin, written in a stack language, optimized for Taproot.

## (3) Complete Example — Compile at `http://localhost:5557`
```json
{
  "script": "<32-byte-pubkey> OP_CHECKSIG"
}
```
Replace `<32-byte-pubkey>` with a real hex key (e.g., `0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798` — that's 33 bytes; for TapScript use a 32-byte x-only key, e.g., `79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798`).  
This script says: "Spend only if you provide a valid Schnorr signature from this key."  
Post this JSON — the server compiles and shows the TapScript address.


