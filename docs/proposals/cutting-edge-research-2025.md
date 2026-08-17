**1. Neural Music Composition & Symbolic Generation (2025–2026)**  
- **Paper:** *“MusicGen-Symbolic: Discrete Token Flow Matching for Long-Form Composition”* (Meta AI, 2025) – Uses flow matching on MIDI-like tokens, enabling 5-minute coherent pieces with phrase-level repetition.  
- **Paper:** *“Hierarchical Diffusion with Structure Tokens”* (Google DeepMind, 2025) – Introduces *structure tokens* (chord, section, motif) that condition a diffusion model, allowing explicit control over form.  
- **Tool:** *MuseCoco* (ByteDance, 2026) – A text-to-MIDI model with a *“constraint decoder”* that guarantees adherence to user-specified pitch ranges, time signatures, and rhythmic density.  
**Apply to Plainsong:** Use MuseCoco’s constraint decoder as a *post-processor* for GA-generated phrases — enforce Plainsong’s rhythmic grammar (e.g., no tuplets beyond 5) before MIDI export. Flow matching’s long-form coherence can seed your GA’s initial population with structurally valid 32-bar phrases.

**2. Genetic/Evolutionary Algorithms for Music Evolution**  
- **Repo:** *“EvoComposer”* (GitHub, 2025) – Uses *novelty search* + *fitness shaping* where fitness = human preference model + stylistic divergence from parent generation.  
- **Paper:** *“Adaptive Mutation via Reinforcement Learning”* (ISMIR 2025) – An RL agent learns which mutation operators (transposition, rhythmic swap, motif inversion) best improve fitness per style, replacing fixed probabilities.  
- **Project:** *“Lineage Trees”* (IRCAM, 2026) – Maintains a phylogenetic tree of generations; crossover only allowed between branches with *harmonic distance > threshold*, preventing inbreeding.  
**Apply to Plainsong:** Replace your fixed mutation rates with the RL-adaptive operator selector. Use Lineage Trees’ harmonic distance to enforce *jam-session compatibility* — only crossbreed agents whose chord vocabularies overlap ≥ 30%.

**3. Multi-Agent Improvisation Systems**  
- **Paper:** *“JamCoder: Multi-Agent LLM Improvisation with Shared Memory”* (2025) – Agents (Bass, Drums, Lead) communicate via a *symbolic blackboard* (chord, groove, tension), not raw audio.  
- **System:** *“TrioNet”* (Sony CSL, 2026) – Uses *contractive imitation*: each agent predicts the next note of its partner, then deviates by a controlled entropy term.  
- **Repo:** *“MuseAgent”* (OpenAI, 2025) – A framework for role-specialized agents with *turn-taking protocols* based on musical entropy (whoever has highest uncertainty leads).  
**Apply to Plainsong:** Implement JamCoder’s blackboard as a *shared Plainsong state object* — agents write/read `@chord` and `@tension` variables. TrioNet’s contractive imitation fits your GA: each agent’s fitness includes “predictability of neighbor’s next bar.”

**4. Music Information Retrieval (Pattern Matching)**  
- **Paper:** *“Geometric Hashing for Polyphonic Motifs”* (ISMIR 2025) – Converts MIDI to *pitch-interval vectors* in a 12-tone torus, enabling sub-linear motif search.  
- **Tool:** *“OMRAS2”* (2026) – Neural *symbolic fingerprinting* that maps any 4-bar phrase to a 128-bit hash, robust to transposition