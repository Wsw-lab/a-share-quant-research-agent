# QData research snapshot fixture provenance

- Producer repository: `QData`
- Producer commit: `442b7265c4c04ba56cd189507ad827950e77b4f2`
- Producer command: `python3 examples/build_research_snapshot.py build <output-dir>`
- Contract: `research_snapshot_v1`
- Snapshot ID: `sha256:0b7a9697ceccc81cf74e131b74e9377c106160919da990910725011ad39c342b`
- Scope: deterministic three-session synthetic contract fixture; not market,
  strategy, or performance evidence.

This file deliberately lives outside `qdata_research_snapshot_v1/`, whose
exact contract file set is the manifest plus four CSV datasets.
