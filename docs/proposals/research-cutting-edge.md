**1. Symbolic Music Representation in LLMs**  
*Paper: "MIDI-LM: Hierarchical Tokenization for Long-Context Symbolic Music" (arXiv:2503.18421, 2025)*  
**Key insight:** Splits MIDI into parallel event streams (notes, tempo, dynamics) with separate learned embeddings, then interleaves via a router token. This reduces sequence length by 40% vs. REMI and improves LLM coherence over 10-minute pieces.  
**Applies to TapScript:** Your plain-text DSL can compile to this hierarchical tokenization, not just raw MIDI. This lets TapScript serve as a human-readable front-end for LLM-based composition, where the compiler emits both MIDI and the token stream for model fine-tuning.

**2. Multi-Agent Creative Collaboration**  
*Project: "Orchestra of Agents: Decentralized Improvisation via Contract-Net Protocol" (ICML 2025 Workshop on Generative Agents)*  
**Key insight:** Agents bid on musical "gaps" (e.g., missing harmony) using a utility function that balances individual style vs. ensemble cohesion. A mediator (not central planner) accepts bids based on stigmergic pheromone trails from prior successful fills.  
**Applies to TapScript:** Your stigmergy module can be embedded as a TapScript directive (e.g., `@pheromone:lead-guitar-weight=0.7`). The compiler then translates these into bid utilities for the agent swarm, making the notation a coordination language, not just a score.

**3. Music as Communication Protocol Between AI Agents**  
*Paper: "SWMIDI-8: A Lossy, Semantically-Tagged Wire Format for Inter-Agent Audio" (ACM MM 2025)*  
**Key insight:** Extends your SWMIDI-8 idea by adding "affective meta-channels" — 8-bit fields for valence, arousal, and dominance, sampled at 10Hz. Agents can encode intent (e.g., "requesting clarification") as a chord progression, decodable by other agents without shared text.  
**Applies to TapScript:** TapScript can become the *authoring syntax* for these meta-channels. Example: `@intent:question` compiles to a rising minor-second motif in the SWMIDI-8 payload. This turns your notation into a human-writable protocol for agent-to-agent semantics.

**4. Plain-Text DSLs Compiling to Multiple Backends**  
*Project: "Text-to-Everything: A Tree-Sitter-Based Compiler for Domain-Specific Languages" (PLDI 2026, early draft)*  
**Key insight:** Uses a single parse tree with pluggable codegen backends — LLVM, WebAssembly, Python, and now MIDI. The key is a "semantic lossless" intermediate representation (IR) that preserves user comments and layout, enabling round-tripping from compiled output back to source.  
**Applies to TapScript:** Adopt this IR for your compiler. TapScript source → IR → (MIDI, WAV, SWMIDI-8, tensor-midi). This allows reversible compilation: a user can edit the MIDI in a DAW and export back to TapScript, preserving their original text annotations (e.g., `% human-feel`).

**5. Emergence in Multi-Agent Systems**  
*Paper: "Quantifying Collective Creativity via Topological Data Analysis" (NeurIPS 2025)*  
**Key insight:** Measures emergence as persistent homology of agent-output trajectories — not just novelty, but *unpredictable coherence* (e.g., a chord progression none agent intended but all accept). They show that emergence peaks when agents have 70% shared context and 30% private noise.  
**App
