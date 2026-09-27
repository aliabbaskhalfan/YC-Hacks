# synthetic (generated, gitignored)

The 90-day fleet history that gives fleet intelligence something real to find
(BUILD_SPEC.md Section 8). Regenerate rather than hand-edit — the same seed
reproduces the dataset byte for byte:

```bash
python -m sim.synth.build_registry     --seed 7   # once; writes data/registry/
python -m sim.synth.generate_incidents --seed 7
python -m sim.synth.verify_patterns               # confirm the patterns survived
```

Contents:

- `incidents.jsonl` — ~485 incidents across 40 units / 6 sites / 90 days. Each
  line carries the anomaly event the robot raised, a telemetry summary, the
  tech's fix note, the `RepairRecord` the real extractor pulled out of that
  note, and the outcome (including whether the fault came back).
- `telemetry/inc-XXXX.csv` — the 8-second window behind each anomaly, 30Hz.
- `ground_truth.json` — the answer key for the three hidden patterns, with
  both the planted multipliers and what actually came out. **Nothing in the
  pipeline reads this**; it exists so pattern discovery can be checked rather
  than assumed.

The patterns are never written into an incident field. They live only in the
hazard rates, so they have to be mined back out of incident counts joined
against `data/registry/`.
