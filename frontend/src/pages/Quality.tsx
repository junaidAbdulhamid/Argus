import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ScanEye,
  AlertTriangle,
  CheckCheck,
  Users,
  ShieldCheck,
} from "lucide-react";
import { api, send, time } from "../api";
import { useApp } from "../context";
import type {
  QualityDashboard,
  Escalation,
  AnnotatorProfile,
} from "../quality-types";
import {
  PageHeading,
  MetricCard,
  Skeleton,
  ErrorState,
  Table,
  Badge,
  Input,
  Button,
  Select,
  EmptyState,
  Modal,
  JsonViewer,
} from "../components/ui";
const percent = (v: number | null) =>
  v === null ? "Not enough data" : `${(v * 100).toFixed(1)}%`;
export default function Quality() {
  const { project, user } = useApp(),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [selected, setSelected] = useState<AnnotatorProfile | null>(null);
  const params = new URLSearchParams({
    ...(project ? { project_id: project } : {}),
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: `${to}T23:59:59` } : {}),
  });
  const q = useQuery({
    queryKey: ["quality-dashboard", params.toString()],
    queryFn: () => api<QualityDashboard>(`/quality/dashboard?${params}`),
  });
  return (
    <>
      <PageHeading
        eyebrow="QUALITY INTELLIGENCE"
        title="Confidence, with evidence."
        description="Inspect consistency, human decisions, and calibration without reducing people to one score."
        action={
          <div className="actions">
            {user.role === "ADMIN" && (
              <Link className="button secondary" to="/gold">
                Gold reference tasks
              </Link>
            )}
            <Link className="button secondary" to="/review">
              <ScanEye size={16} />
              Open review queue
            </Link>
          </div>
        }
      />
      <div className="quality-filters">
        <label>
          From
          <Input
            aria-label="Quality start date"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          Through
          <Input
            aria-label="Quality end date"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <span>Filtered by task creation date</span>
      </div>
      {q.isPending ? (
        <Skeleton />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <>
          <div className="metrics">
            <MetricCard
              label="Pending reviews"
              value={q.data.pending_reviews}
              caption="Awaiting independent judgment"
              icon={<ScanEye size={17} />}
            />
            <MetricCard
              label="Open escalations"
              value={q.data.open_escalations}
              caption="Unresolved quality concerns"
              icon={<AlertTriangle size={17} />}
            />
            <MetricCard
              label="Annotations completed"
              value={q.data.annotations_completed}
              caption="Across selected tasks"
              icon={<CheckCheck size={17} />}
            />
            <MetricCard
              label="Gold attempts"
              value={q.data.gold_attempts}
              caption="Against reference answers"
              icon={<ShieldCheck size={17} />}
            />
          </div>
          <div className="quality-rate-grid">
            {[
              [
                "Approval rate",
                percent(q.data.approval_rate),
                "Latest decision per reviewed task",
              ],
              [
                "Disagreement rate",
                percent(q.data.disagreement_rate),
                `${q.data.agreement_task_count} tasks with multiple annotations`,
              ],
              [
                "Gold accuracy",
                percent(q.data.gold_accuracy),
                "Mean field accuracy across reference attempts",
              ],
              [
                "Dataset eligibility",
                percent(q.data.eligibility_rate),
                `${q.data.eligibility_evaluated_tasks} tasks with recorded evaluations`,
              ],
            ].map(([label, value, note]) => (
              <section className="panel quality-rate" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>{note}</small>
              </section>
            ))}
          </div>
          <section className="panel quality-cohort">
            <div className="section-heading">
              <h2>Agreement across the cohort</h2>
              <Badge>Consistency ≠ correctness</Badge>
            </div>
            <div className="form-two padded">
              <div>
                <h3>Cohen’s kappa · paired annotators</h3>
                {q.data.cohen_kappa.length ? (
                  <Table headers={["Annotator pair", "Tasks", "Kappa"]}>
                    {q.data.cohen_kappa.map((pair) => (
                      <tr key={pair.annotator_ids.join(":")}>
                        <td>{pair.annotator_names.join(" / ")}</td>
                        <td>{pair.tasks}</td>
                        <td>{pair.kappa?.toFixed(3) ?? "Undefined"}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <p className="form-note">
                    Requires the same pair of annotators on at least two tasks.
                  </p>
                )}
              </div>
              <div>
                <h3>Fleiss’ kappa · equal-rater cohorts</h3>
                {q.data.fleiss_kappa.length ? (
                  <Table headers={["Raters per task", "Tasks", "Kappa"]}>
                    {q.data.fleiss_kappa.map((cohort) => (
                      <tr key={cohort.raters_per_task}>
                        <td>{cohort.raters_per_task}</td>
                        <td>{cohort.tasks}</td>
                        <td>{cohort.kappa?.toFixed(3) ?? "Undefined"}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <p className="form-note">
                    Requires multiple tasks with the same number of ratings.
                  </p>
                )}
              </div>
            </div>
            <p className="padded form-note">
              Kappa is undefined when ratings have no variation.{" "}
              {q.data.eligibility_note}
            </p>
          </section>
          {user.role === "ADMIN" && (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Annotator quality profiles</h2>
                  <p>
                    Click a person to inspect denominators, throughput, and
                    reference results
                  </p>
                </div>
                <Users size={18} />
              </div>
              <Table
                headers={[
                  "Annotator",
                  "Completed",
                  "Median time",
                  "Peer agreement",
                  "Gold accuracy",
                  "Rejections",
                  "Revisions",
                ]}
              >
                {q.data.annotators.map((a) => (
                  <tr key={a.user_id}>
                    <td>
                      <button
                        className="text-link"
                        onClick={() => setSelected(a)}
                      >
                        {a.name}
                      </button>
                    </td>
                    <td>{a.tasks_completed}</td>
                    <td>
                      {a.median_minutes === null
                        ? "—"
                        : `${a.median_minutes.toFixed(1)} min`}
                    </td>
                    <td>{percent(a.agreement_with_others)}</td>
                    <td>{percent(a.rolling_gold_accuracy)}</td>
                    <td>{percent(a.rejection_rate)}</td>
                    <td>{percent(a.revision_rate)}</td>
                  </tr>
                ))}
              </Table>
            </section>
          )}
        </>
      )}
      {selected && (
        <Modal title={selected.name} onClose={() => setSelected(null)}>
          <p>
            {selected.agreement_samples} comparisons against a unique peer
            majority. {selected.reviewed_tasks} reviewed tasks. Rolling gold
            accuracy uses the latest 20 attempts; {selected.recent_failures}{" "}
            recent imperfect results.
          </p>
          <h3>Annotation throughput</h3>
          <JsonViewer value={selected.throughput} />
          <h3>Recent gold quality trend</h3>
          <JsonViewer value={selected.quality_trend} />
        </Modal>
      )}
    </>
  );
}
export function Escalations() {
  const { project, notify } = useApp(),
    qc = useQueryClient(),
    [status, setStatus] = useState("OPEN"),
    [selected, setSelected] = useState<Escalation | null>(null),
    [resolution, setResolution] = useState(""),
    [outcome, setOutcome] = useState("RESOLVED");
  const q = useQuery({
    queryKey: ["escalations", project, status],
    queryFn: () =>
      api<Escalation[]>(
        `/escalations?${new URLSearchParams({ status, ...(project ? { project_id: project } : {}) })}`,
      ),
  });
  const resolve = useMutation({
    mutationFn: () =>
      send(`/escalations/${selected?.id}/resolve`, {
        status: outcome,
        resolution,
      }),
    onSuccess: () => {
      qc.invalidateQueries();
      setSelected(null);
      setResolution("");
      notify("Escalation resolution recorded");
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="HUMAN ADJUDICATION"
        title="Escalation inbox"
        description="Resolve uncertainty explicitly. Every resolution remains in the audit trail."
      />
      <section className="panel">
        <div className="section-heading">
          <h2>{q.data?.length || 0} escalations</h2>
          <Select
            aria-label="Escalation status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {["OPEN", "RESOLVED", "DISMISSED"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </div>
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data.length ? (
          <EmptyState
            title="No escalations in this view"
            description="Annotator questions and disagreement concerns arrive here for human adjudication."
          />
        ) : (
          <div className="escalation-list">
            {q.data.map((e) => (
              <article key={e.id}>
                <div>
                  <Badge status={e.status} />
                  <span>{e.source}</span>
                  <time>{time(e.created_at)}</time>
                </div>
                <h3>{e.reason}</h3>
                {e.resolution && <p>{e.resolution}</p>}
                <footer>
                  <Link to={`/review/${e.task_id}`} className="text-link">
                    Inspect task {e.task_id.slice(0, 8)}
                  </Link>
                  {e.status === "OPEN" && (
                    <Button variant="secondary" onClick={() => setSelected(e)}>
                      Resolve escalation
                    </Button>
                  )}
                </footer>
              </article>
            ))}
          </div>
        )}
      </section>
      {selected && (
        <Modal title="Resolve escalation" onClose={() => setSelected(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              resolve.mutate();
            }}
          >
            <p className="form-note">{selected.reason}</p>
            <label>
              Outcome
              <Select
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                <option>RESOLVED</option>
                <option>DISMISSED</option>
              </Select>
            </label>
            <label>
              Resolution
              <textarea
                required
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
            </label>
            {resolve.error && <ErrorState error={resolve.error} />}
            <Button disabled={resolve.isPending}>Record resolution</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
