import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ShieldCheck,
  AlertTriangle,
  Check,
  Database,
  ArrowRight,
} from "lucide-react";
import { api, send, time, human } from "../api";
import type { Task, Run, User } from "../types";
import type { QualityDetail, GateResult, Consensus } from "../quality-types";
import { useApp } from "../context";
import {
  PageHeading,
  Button,
  Table,
  Badge,
  ErrorState,
  Skeleton,
  EmptyState,
  Select,
  Input,
  JsonViewer,
} from "../components/ui";
import { Trace } from "../components/Trace";
export default function ReviewQueue() {
  const { project } = useApp(),
    [status, setStatus] = useState("");
  const q = useQuery({
    queryKey: ["review-queue", project, status],
    queryFn: () =>
      api<(Task & { consensus: Consensus; project_name: string })[]>(
        `/review/queue?${new URLSearchParams({ ...(project ? { project_id: project } : {}), ...(status ? { status } : {}) })}`,
      ),
  });
  return (
    <>
      <PageHeading
        eyebrow="HUMAN QUALITY GATE"
        title="Review queue"
        description="Independent judgments, inspectable evidence, and explicit decisions."
        action={
          <Link className="button secondary" to="/escalations">
            <AlertTriangle size={15} />
            Escalation inbox
          </Link>
        }
      />
      <section className="panel">
        <div className="section-heading">
          <h2>{q.data?.length || 0} tasks need attention</h2>
          <Select
            aria-label="Review status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All review states</option>
            <option value="PENDING_REVIEW">Pending review</option>
            <option value="ESCALATED">Escalated</option>
            <option value="CHANGES_REQUESTED">Changes requested</option>
          </Select>
        </div>
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data.length ? (
          <EmptyState
            title="The review queue is clear"
            description="Tasks arrive here after their configured independent annotations are complete."
          />
        ) : (
          <Table
            headers={[
              "Task",
              "Project",
              "Annotations",
              "Agreement",
              "State",
              "",
            ]}
          >
            {q.data.map((t) => (
              <tr key={t.id}>
                <td>
                  <Link to={`/review/${t.id}`} className="text-link">
                    {t.external_id || t.id.slice(0, 8)}
                  </Link>
                </td>
                <td>{t.project_name}</td>
                <td>
                  {t.consensus.completed} / {t.consensus.required}
                </td>
                <td>
                  {t.consensus.labels.raw_agreement === null
                    ? "Insufficient evidence"
                    : `${Math.round(t.consensus.labels.raw_agreement * 100)}%`}
                  {t.consensus.conflicting && (
                    <AlertTriangle size={12} className="inline-warning" />
                  )}
                </td>
                <td>
                  <Badge status={t.status} />
                </td>
                <td>
                  <Link to={`/review/${t.id}`}>
                    <ArrowRight size={15} />
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </section>
    </>
  );
}
export function ReviewWorkspace() {
  const { id } = useParams(),
    { user, notify } = useApp(),
    qc = useQueryClient(),
    [decision, setDecision] = useState("APPROVED"),
    [comments, setComments] = useState(""),
    [chosen, setChosen] = useState(""),
    [rejected, setRejected] = useState(""),
    [rationale, setRationale] = useState("");
  const task = useQuery({
      queryKey: ["task", id],
      queryFn: () => api<Task>(`/tasks/${id}`),
    }),
    quality = useQuery({
      queryKey: ["quality", id],
      queryFn: () => api<QualityDetail>(`/tasks/${id}/quality`),
    }),
    users = useQuery({
      queryKey: ["users"],
      queryFn: () => api<User[]>("/users"),
    }),
    runs = useQuery({
      queryKey: ["trajectory", id],
      queryFn: () => api<Run[]>(`/tasks/${id}/trajectory`),
    });
  const review = useMutation({
      mutationFn: () => send(`/tasks/${id}/reviews`, { decision, comments }),
      onSuccess: () => {
        qc.invalidateQueries();
        notify("Review decision recorded");
        setComments("");
      },
    }),
    gate = useMutation({
      mutationFn: () => send<GateResult>(`/tasks/${id}/quality-gate`),
    }),
    promote = useMutation({
      mutationFn: () => send(`/tasks/${id}/training-examples`),
      onSuccess: () => {
        qc.invalidateQueries();
        notify("Training example created with full provenance");
      },
    }),
    pair = useMutation({
      mutationFn: () =>
        send(`/tasks/${id}/preference`, {
          chosen_run_id: chosen,
          rejected_run_id: rejected,
          rationale,
        }),
      onSuccess: () => notify("Reviewer preference recorded"),
    });
  if (task.isPending || quality.isPending) return <Skeleton />;
  if (task.error || quality.error)
    return <ErrorState error={task.error || quality.error} />;
  const t = task.data,
    q = quality.data;
  const activeAnnotations =
    t.annotations?.filter((a) =>
      t.assignments?.some(
        (s) =>
          s.id === a.assignment_id &&
          s.round === t.annotation_round &&
          s.status === "COMPLETED",
      ),
    ) || [];
  return (
    <>
      <Link className="back-link" to="/review">
        <ArrowLeft size={14} />
        Review queue
      </Link>
      <PageHeading
        eyebrow={`INDEPENDENT REVIEW · ROUND ${t.annotation_round}`}
        title={t.external_id || t.id.slice(0, 8)}
        description={`${t.project?.name} · ${q.consensus.completed} independent annotations`}
        action={<Badge status={t.status} />}
      />
      <div className="review-layout">
        <section className="panel review-trace">
          <div className="section-heading">
            <h2>Agent trajectory</h2>
            <Link className="text-link" to={`/tasks/${id}`}>
              Full task
            </Link>
          </div>
          <Trace taskId={id!} />
        </section>
        <section className="panel review-annotations">
          <div className="section-heading">
            <h2>Independent annotations</h2>
            {q.consensus.conflicting && (
              <Badge status="REJECTED">Disagreement</Badge>
            )}
          </div>
          <div className="padded">
            <div className="consensus-summary">
              <span>
                Raw agreement
                <strong>
                  {q.consensus.labels.raw_agreement === null
                    ? "—"
                    : `${Math.round(q.consensus.labels.raw_agreement * 100)}%`}
                </strong>
              </span>
              <span>
                Mean score
                <strong>{q.consensus.scores.mean?.toFixed(2) || "—"}</strong>
              </span>
              <span>
                Std. deviation
                <strong>
                  {q.consensus.scores.standard_deviation?.toFixed(2) || "—"}
                </strong>
              </span>
            </div>
            <p className="form-note">{q.consensus.interpretation}</p>
            {activeAnnotations.map((a) => (
              <article
                className={`annotation-comparison ${q.consensus.conflicting ? "conflict" : ""}`}
                key={a.id}
              >
                <header>
                  <span className="avatar">
                    {users.data
                      ?.find((u) => u.id === a.annotator_id)
                      ?.full_name.slice(0, 1) || "A"}
                  </span>
                  <strong>
                    {users.data?.find((u) => u.id === a.annotator_id)
                      ?.full_name || a.annotator_id.slice(0, 8)}
                  </strong>
                  <span>{a.score}/5</span>
                </header>
                <Badge status={a.label} />
                <p>{a.feedback}</p>
                {Object.entries(a.values || {}).map(([key, value]) => (
                  <div className="answer-row" key={key}>
                    <span>
                      {q.schema?.fields.find((f) => f.key === key)?.label ||
                        key}
                    </span>
                    <strong>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </strong>
                  </div>
                ))}
              </article>
            ))}
            {!activeAnnotations.length && (
              <p className="muted">No completed annotations in this round.</p>
            )}
            <details>
              <summary>Field-level consensus metrics</summary>
              <JsonViewer value={q.consensus.fields} />
              <p className="form-note">{q.consensus.kappa_note}</p>
            </details>
            <details>
              <summary>Previous review history ({q.reviews.length})</summary>
              {q.reviews.map((r) => (
                <article className="review-history" key={r.id}>
                  <Badge status={r.decision} />
                  <p>{r.comments}</p>
                  <small>
                    {r.reviewer} · Round {r.round} · {time(r.created_at)}
                  </small>
                </article>
              ))}
            </details>
          </div>
        </section>
        <aside className="panel review-controls">
          <div className="section-heading">
            <h2>Review decision</h2>
            <ShieldCheck size={17} />
          </div>
          <form
            className="padded"
            onSubmit={(e) => {
              e.preventDefault();
              review.mutate();
            }}
          >
            <label>
              Decision
              <Select
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
              >
                <option value="APPROVED">Approve</option>
                <option value="REJECTED">Reject</option>
                <option value="REQUEST_CHANGES">Request changes</option>
                <option value="ESCALATED">Escalate</option>
              </Select>
            </label>
            <label>
              Comments
              <textarea
                required
                rows={5}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Explain the evidence behind your decision."
              />
            </label>
            {q.escalations.some((e) => e.status === "OPEN") && (
              <div className="quality-warning">
                <AlertTriangle size={16} />
                <Link to="/escalations">
                  Resolve open escalations before approval.
                </Link>
              </div>
            )}
            {review.error && <ErrorState error={review.error} />}
            <Button
              disabled={
                review.isPending ||
                !["PENDING_REVIEW", "APPROVED", "ESCALATED"].includes(t.status)
              }
            >
              <Check size={15} />
              Record decision
            </Button>
          </form>
          <div className="padded gate-panel">
            <h3>Dataset eligibility</h3>
            <p className="form-note">
              Approval is one gate. Every configured requirement must pass.
            </p>
            <Button
              variant="secondary"
              disabled={gate.isPending}
              onClick={() => gate.mutate()}
            >
              Evaluate quality gates
            </Button>
            {gate.error && <ErrorState error={gate.error} />}{" "}
            {gate.data && (
              <>
                <Badge status={gate.data.eligible ? "APPROVED" : "REJECTED"}>
                  {gate.data.eligible ? "Eligible" : "Blocked"}
                </Badge>
                {gate.data.reasons.map((reason) => (
                  <p key={reason} className="gate-reason">
                    {human(reason)}
                  </p>
                ))}
              </>
            )}
            {user.role === "ADMIN" && (
              <Button
                variant="secondary"
                disabled={promote.isPending}
                onClick={() => promote.mutate()}
              >
                <Database size={15} />
                Create training example
              </Button>
            )}
            {promote.error && <ErrorState error={promote.error} />}
            <details>
              <summary>Configured gates</summary>
              <JsonViewer value={q.policy} />
            </details>
          </div>
          {(runs.data?.length || 0) > 1 && (
            <form
              className="padded"
              onSubmit={(e) => {
                e.preventDefault();
                pair.mutate();
              }}
            >
              <h3>Human preference pair</h3>
              <p className="form-note">
                Select two real responses to enable DPO export.
              </p>
              <label>
                Chosen run
                <Select
                  required
                  value={chosen}
                  onChange={(e) => setChosen(e.target.value)}
                >
                  <option value="">Choose…</option>
                  {runs.data?.map((r) => (
                    <option value={r.id} key={r.id}>
                      {r.model_name} · {r.id.slice(0, 8)}
                    </option>
                  ))}
                </Select>
              </label>
              <label>
                Rejected run
                <Select
                  required
                  value={rejected}
                  onChange={(e) => setRejected(e.target.value)}
                >
                  <option value="">Choose…</option>
                  {runs.data?.map((r) => (
                    <option value={r.id} key={r.id}>
                      {r.model_name} · {r.id.slice(0, 8)}
                    </option>
                  ))}
                </Select>
              </label>
              <label>
                Preference rationale
                <Input
                  required
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                />
              </label>
              {pair.error && <ErrorState error={pair.error} />}
              <Button
                variant="secondary"
                disabled={pair.isPending || chosen === rejected}
              >
                Record preference
              </Button>
            </form>
          )}
        </aside>
      </div>
    </>
  );
}
