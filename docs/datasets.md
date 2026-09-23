# Datasets and training exports

Only tasks passing current human quality gates can produce a `TrainingExample`. A training example is a frozen record, not a pointer to whichever annotation happens to be current later. Dataset finalization rechecks all gates and source evidence before admitting any selected example.

## Build a version

1. Create a dataset as admin and open its builder.
2. Use **Prepare approved examples** to evaluate approved tasks and materialize eligible snapshots. The action reports blocked tasks and processes at most 500 tasks per request; individual task materialization is also available through review/API.
3. Filter by project (workspace selector), task type, model, task creation date, minimum baseline score, annotation label, or exact top-level task metadata values. Human approval is mandatory; the reviewer-decision filter supports APPROVED only.
4. Select eligible examples, inspect their previews, and create a draft. The API accepts at most 10,000 unique examples, with at most one example per originating task.
5. Finalize. The service locks policies/tasks, runs current gates, verifies exact annotation and review IDs and round, records finalization evidence, and calculates the version checksum. Any failing example leaves the whole version DRAFT with explicit reasons.
6. Request a format/container and inspect Export History. Downloads become available only after the background worker completes the job.

Preview evaluations are audited. The score filter and project score gate both require every annotation's baseline score to meet the minimum; preview tables display the mean for comparison. Changed policy, new gold failures, new review decisions, or escalation can make an old snapshot ineligible for a new version. Finalized historical versions remain immutable and exportable according to their recorded admission evidence. To change membership or configuration, create another version.

## Provenance and immutability

Each snapshot retains project/task data, every original run and ordered trajectory step, current completed annotations, the approving human review evidence, pinned annotation schema, optional human preference pair, and its successful source gate. Foreign keys retain the original relational sources. Lineage UI links the dataset versions, training example, task, runs, trajectories, annotations, review, source gate, and per-version finalization gate.

Training snapshots and finalized versions cannot be updated/deleted in PostgreSQL: migration-installed triggers reject mutations. Finalized membership cannot be inserted, changed, moved, or deleted. APIs provide no mutation route for frozen evidence. Projects with retained training/calibration/preference evidence cannot be deleted.

Versions store an increasing dataset-local number, creator, creation/finalization timestamps, example count, recorded filters, schema version (`argus.training.v1`), metadata, and SHA-256 checksum. The checksum covers canonical serialized snapshots, filters, metadata, schema version, and finalization evidence. It identifies this exact admission event; rebuilding the same selection later may produce a different version checksum because evaluation IDs/timestamps differ. Dataset-file checksums instead identify the exact exported bytes.

## Supported formats

All formats support JSON arrays and JSONL. Missing required source evidence fails the entire job explicitly; no row is silently fabricated or omitted.

| Format | Record | Source requirements |
| --- | --- | --- |
| SFT | `{"messages":[{"role":"user","content":"…"},{"role":"assistant","content":"…"}]}` | Source prompt and final answer; one run, or a reviewer-selected chosen run. |
| DPO | `{"prompt":"…","chosen":"…","rejected":"…"}` | Explicit reviewer-validated pair of distinct actual runs with different final responses. |
| Reward | `{"prompt":"…","response":"…","score":0.75}` | Source prompt, selected final response, and human baseline scores. |
| Trajectory | `{"task":{…},"trajectory":[…],"reward":0.75,"metadata":{…}}` | Full preserved runs/steps plus annotation, review, and gate evidence. |

Prompt selection uses task `input_payload.prompt` or `question`, then the first source user-message step. Response selection uses the last nonempty `final_answer`. SFT exports prompt/final-answer pairs; it does not invent a conversation or embed all tool steps as chat messages. Full traces remain in trajectory format and frozen lineage. Reward is `(mean human baseline score - 1) / 4`, mapping the 1–5 scale to 0–1; it is an explicit normalization, not a calibrated probability.

Reviewers/admins record a preference through `POST /tasks/{id}/preference`, supplying `chosen_run_id`, `rejected_run_id`, and rationale. Both runs must belong to that task; a task annotator cannot supply its preference decision. Record the pair before materializing a snapshot intended for DPO. Existing immutable snapshots do not acquire later preference decisions. The seeded second dataset version contains two real paired examples.

## Jobs and artifacts

`POST /dataset-versions/{id}/exports` returns 202 with a PENDING job. HTTP does not scan/serialize the dataset. The Redis-backed worker checks compatibility and generates artifacts while holding the job row lock. States are PENDING, RUNNING, COMPLETED, FAILED. Failed jobs preserve an explicit error; request a new job after selecting a supported source/version/format. Redis outages are tolerated through database polling, and abandoned RUNNING jobs can be reclaimed after 15 minutes. Active work is protected from concurrent recovery by its row lock.

Each completed job provides:

- `dataset.jsonl` or `dataset.json`: deterministic ordered training records.
- `manifest.json`: job/version/schema identifiers, count, format, creation timestamp, file names, dataset byte size, and SHA-256 checksums for data/schema/provenance.
- `schema.json`: record field contract, format/container, reward normalization, and SFT policy.
- `provenance.json`: row index, training example/task/run/annotation/review IDs, snapshot checksum, source gate ID, and finalization gate ID/evidence.

Downloads use authenticated `GET /exports/{id}/files/{dataset|manifest|schema|provenance}` and are organization-scoped. Dataset rows stream through a temporary file followed by atomic replacement; incomplete jobs cannot expose artifacts. Provenance is currently collected in memory, and downloads use the shared local export directory. Compose mounts `export_data` into both API and worker; local development must point both at the same `EXPORT_DIRECTORY`. Back up this volume with PostgreSQL for artifact retention. External object storage and Parquet are not part of Phase 2.
