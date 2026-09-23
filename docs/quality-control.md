# Quality control

ARGUS requires independent human approval and every configured quality gate before it creates a training example. Dataset finalization evaluates those requirements again. Annotation completion, agreement, and an APPROVED badge alone do not bypass the gate service.

## Schemas and assignment rounds

Admins publish project schemas through project quality settings. Publication creates a new version; existing queued tasks keep their pinned version. Supported types are boolean, single select, multi-select, integer rating, continuous score, text, and structured JSON. Fields have keys, labels, descriptions, required flags, options, and numeric/length/item constraints. Both the API and dynamic form validate values. Boolean `false` is a valid answer, not a missing answer. Baseline outcome, 1–5 quality score, feedback, and structured notes remain available alongside project-specific fields.

Queueing pins `required_annotations` and the active schema. Different people claim independent slots; one person cannot fill multiple slots in a round. Completed and active assignments consume slots; expired leases release them. PostgreSQL locks serialize claims and a fresh count under the task lock prevents capacity overflow. Rejected or requested-change tasks can be requeued into a new round. Previous annotations and reviews remain available; only current-round completed answers contribute to current gates.

Annotators see their own answers. Optional `reveal_after_completion` reveals peers only after their own completion and the task reaches review readiness. Gold identity, expected answers, and grading events are omitted from annotator responses. Admins and reviewers can inspect review evidence; only admins manage gold references and worker profiles.

## Decisions and escalations

| Action | Behavior |
| --- | --- |
| Approve | Records a new review, evaluates gates, and marks APPROVED only if they pass. More approvals or evidence may still be needed. |
| Reject | Records rationale and marks REJECTED. Admin can requeue into a new round. |
| Request changes | Records rationale and marks CHANGES_REQUESTED. Admin can requeue into a new round. |
| Escalate | Opens an escalation and marks ESCALATED. |
| Resolve/dismiss escalation | Retains resolution text and actor; the last closed issue returns the task to review or unfinished annotation work. It does not approve it. |

Review rows contain reviewer, task, round, exact annotation IDs, decision, comments, timestamp, and metadata. Decision revisions append rows instead of changing history. A person who annotated the task cannot review it, even with admin privileges. The latest decision per reviewer is counted; a current rejection/request for changes vetoes eligibility. Unresolved escalations block approval and training eligibility. Annotators can escalate assigned tasks, reviewers can escalate from review, and categorical conflicts can automatically open disagreement escalations.

## Quality policy

| Rule | Default | Interpretation |
| --- | --- | --- |
| `required_annotations` | 1 | Independent completed authors; gate uses the greater of current policy and the task's pinned count. |
| `required_reviews` | 1 | Distinct independent approvals covering the exact current annotations; cannot be zero. |
| `minimum_agreement` | 0 | Minimum pairwise agreement for outcome and each categorical field. Positive thresholds require multiple observed values. |
| `minimum_score` | 1 | Every baseline annotation quality score must meet this value. |
| `maximum_variance` | null | If configured, limits population variance for baseline scores and each numeric schema field. |
| `minimum_gold_accuracy` | null | If configured, every author's mean accuracy over their latest 20 reference attempts must pass. |
| `minimum_gold_attempts` | 1 | Minimum history when a gold accuracy requirement is enabled. |
| `gold_every` | 5 | Prefer an unattempted reference at this completed-assignment cadence. |
| `auto_escalate_disagreement` | true | Open an escalation when completed categorical answers conflict. |
| `reveal_after_completion` | false | Permit peer-answer visibility after completion and review readiness. |

Numeric fields may have different scales; a single variance ceiling applies to each field, so configure ranges and thresholds deliberately. The gold gate uses the worker's history across projects in their organization. Its 20-attempt window means a minimum history above 20 cannot pass; the API bounds that setting to 20.

Every evaluation stores its policy, annotation/review IDs, consensus, gold evidence, eligibility, reasons, timestamp, evaluator, and audit event. Reasons include `requires_reviewer_approval`, `insufficient_independent_annotations`, `agreement_below_threshold`, `annotation_quality_below_threshold`, `score_variance_above_threshold`, `unresolved_escalation`, `insufficient_gold_history`, and `gold_accuracy_below_threshold`. Reference tasks always receive `gold_reference_excluded_from_training`.

## Agreement and analytics

For categorical values, raw agreement is the fraction of ordered rater pairs with matching values; disagreement is one minus agreement. Multi-select compares sorted sets of selected options. Numeric summaries report mean, median, population standard deviation, and population variance. Free text and JSON require human interpretation and are not automatically scored for agreement.

A single task does not provide a meaningful chance-corrected kappa. The dashboard computes Cohen's kappa for the same pair on at least two tasks, and Fleiss' kappa across equal-rater-count task cohorts. These cohort calculations use baseline outcome labels. Insufficient data or degenerate expected agreement yields null/“Undefined”, not a perfect score. Agreement describes consistency, not correctness.

Project/date filters select tasks by creation timestamp. Dashboard denominators are explicit:

- Approval rate: latest review decision per reviewed task.
- Disagreement: mean outcome disagreement over tasks with multiple current-round answers.
- Eligibility: latest recorded gate among evaluated tasks; this is historical evidence, not a live guarantee after policy changes.
- Throughput: completed assignments, including gold and earlier rounds, grouped by completion date.
- Median annotation time: started-to-completed duration where both timestamps exist.
- Peer agreement: current-round outcome against a unique majority of the other raters; excludes ties and self-votes.
- Rejection/revision rates: distinct worked tasks ever receiving that decision divided by worked tasks with reviews. These are inspectable historical rates, not necessarily fault attribution to a particular worker.
- Gold accuracy: mean fraction of expected fields matched per attempt. Rolling accuracy and recent failures use the last 20 filtered attempts; recent trend exposes individual comparisons.

## Gold references

Admins designate INGESTED tasks before queueing, with expected baseline label/score and/or schema values. The reference pins its schema. Numeric fields accept an absolute tolerance; multi-select compares sorted options. Grading stores field-level comparisons and accuracy. Each worker attempts a reference once; it remains available for other workers and never enters training datasets. Cadence is a preference: if no regular work exists, available references can be served earlier, and absent reference tasks do not block ordinary work.

The seed demonstrates three annotators, successful/failed reference attempts, conflicting annotations, requested changes, rejection, pending review, and approved examples. No synthetic quality rating replaces the inspectable metrics.
