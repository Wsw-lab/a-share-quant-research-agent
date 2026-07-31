# Quant Agent Completion Readiness

Readiness ID: `completion_20260731_152221_011`
Generated at: `2026-07-31T15:22:21`
Status: `production_research_ready_no_stable_candidate`
Completion level: 3 / 7
Passed stages: 3 / 7
Hard blockers: 16

| Stage | Status | Passed | Hard blockers | Key metric |
|---|---|---:|---:|---|
| Research MVP | `pass` | yes | 0 | registry_rows=43 |
| Production Data | `pass` | yes | 0 | quote_rows=3894242 |
| Strategy Factory | `pass` | yes | 0 | factory=factory_batch_20260731_150745_106, candidates=0 |
| Stable Paper Candidate | `fail` | no | 3 | candidate_runs=0 |
| Long Paper Validation | `fail` | no | 5 | paper_days=0, trade_days=0 |
| Operations Control | `fail` | no | 2 | health=stale_data, action_open=0 |
| Live Readiness | `blocked_by_compliance_boundary` | no | 6 | broker=none |

## Failed Hard Checks

- `paper_candidate.candidate_count`: Production paper candidates 0; required >= 3.
- `paper_candidate.candidate_days`: Distinct candidate dates 0; required >= 3.
- `paper_candidate.candidate_freshness`: Latest candidate age n/a days; max 30.
- `paper_validation.candidate_gate`: Stable paper candidate stage must pass first.
- `paper_validation.risk_pass_controls`: Risk-passing paper controls 0; required >= 20.
- `paper_validation.calendar_days`: Paper observation days 0; required >= 30.
- `paper_validation.trade_days`: Simulated trade days 0; required >= 5.
- `paper_validation.latest_risk_gate`: Latest paper risk gate must pass.
- `ops.health_state`: Health state must be ok.
- `ops.freshness`: Data freshness gate must pass.
- `live_readiness.all_prior_stages`: Research, data, candidate, paper, and ops stages must all pass.
- `live_readiness.approval_file`: live_readiness/approval.json must exist for live readiness.
- `live_readiness.compliance_approved`: Compliance approval must be explicit.
- `live_readiness.manual_order_only`: Initial live mode must be manual-order-only.
- `live_readiness.kill_switch`: A tested kill switch is required.
- `live_readiness.broker_adapter`: A named broker adapter must be approved.

## Next Actions

- Keep rejected ideas in research_only; do not override the decision gate manually.
- Use failed-window diagnostics to add genuinely new PIT alpha or event data before rerunning Strategy Factory.
- Run the daily pipeline through a stable candidate for the required paper observation window.
- Clear or acknowledge critical paper-control alerts only after the underlying risk issue is fixed.
- Run examples/ops_smoke_test.py, refresh health, and ack or resolve open action-required notifications.
- Do not connect a broker adapter until long paper validation, operator identity, compliance approval, and kill-switch drills are complete.
- When those controls exist, write live_readiness/approval.json with explicit approval fields and rerun this check in --strict live_ready mode.

## Compliance Boundary

This readiness report never enables live trading by itself. Live execution requires a separate approved broker adapter, operator identity, compliance sign-off, and manual kill-switch process.
