# registry (track: fleet-data)

The **observable** fleet facts — everything a miner is allowed to join
incidents against. Both files are generated and committed:

```bash
python -m sim.synth.build_registry --seed 7
```

- `parts.json` — all 35 part_ids from BUILD_SPEC.md Section 4.2, each with the
  `mesh_nodes` the 3D viewer highlights. Motors also carry `supplier_lots`.
- `fleet.json` — 6 sites and 40 units (Section 4.4). Each unit has its site,
  `ambient_class`, commissioning date, a `usage_factor`, and the supplier lot
  fitted to each of its 12 motors.

Anything that would give away a hidden root cause outright — a site's abrasive
ground, say — deliberately does **not** live here. It belongs in
`data/synthetic/ground_truth.json`, which nothing in the pipeline reads.
Read these through `server.fleet.registry.Registry` rather than parsing them
directly, so the generator and fleet intelligence agree on every lookup.
