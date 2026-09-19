import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ListPlus, ShieldCheck } from "lucide-react";
import { api, send, time } from "../api";
import type { Task, Audit, Run, User } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  Button,
  Badge,
  Tabs,
  JsonViewer,
  Skeleton,
  ErrorState,
  Modal,
  Select,
} from "../components/ui";
import { Trace, Activity } from "../components/Trace";
export default function TaskDetail() {
  const { id } = useParams(),
    { user, notify } = useApp(),
    qc = useQueryClient(),
    [tab, setTab] = useState("Trajectory"),
    [review, setReview] = useState(false),
    [decision, setDecision] = useState("APPROVED"),
    [reason, setReason] = useState("");
  const q = useQuery({
    queryKey: ["task", id],
    queryFn: () => api<Task>(`/tasks/${id}`),
  });
  const audit = useQuery({
    queryKey: ["audit", id],
    queryFn: () => api<Audit[]>(`/tasks/${id}/audit`),
  });
  const runs = useQuery({
    queryKey: ["trajectory", id],
    queryFn: () => api<Run[]>(`/tasks/${id}/trajectory`),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });
  const queue = useMutation({
    mutationFn: () => send(`/tasks/${id}/queue`),
    onSuccess: () => {
      qc.invalidateQueries();
      notify("Task added to annotation queue");
    },
  });
  const approve = useMutation({
    mutationFn: () => send(`/tasks/${id}/review`, { decision, reason }),
    onSuccess: () => {
      qc.invalidateQueries();
      setReview(false);
      notify("Review recorded");
    },
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const t = q.data,
    assignee = users.data?.find(
      (u) => u.id === t.assignments?.[0]?.annotator_id,
    );
  return (
    <>
      <Link className="back-link" to="/tasks">
        <ArrowLeft size={14} />
        Task explorer
      </Link>
      <PageHeading
        eyebrow="TASK INSPECTION"
        title={t.external_id || t.id.slice(0, 8)}
        description={`${t.task_type.replaceAll("_", " ")} · ${t.project?.name}`}
        action={
          <div className="actions">
            <Badge status={t.status} />
            {user.role === "ADMIN" &&
              ["INGESTED", "REJECTED"].includes(t.status) && (
                <Button
                  disabled={queue.isPending}
                  onClick={() => queue.mutate()}
                >
                  <ListPlus size={16} />
                  Enqueue task
                </Button>
              )}
            {["ADMIN", "REVIEWER"].includes(user.role) &&
              t.status === "PENDING_REVIEW" && (
                <Button onClick={() => setReview(true)}>
                  <ShieldCheck size={16} />
                  Review task
                </Button>
              )}
          </div>
        }
      />
      {queue.error && <ErrorState error={queue.error} />}
      <div className="trace-layout">
        <section className="panel trace-main">
          <Tabs
            tabs={["Trajectory", "Input", "Annotations", "Audit log"]}
            value={tab}
            onChange={setTab}
          />
          {tab === "Trajectory" ? (
            <Trace taskId={t.id} />
          ) : tab === "Input" ? (
            <div className="padded">
              <h3>Task input</h3>
              <JsonViewer value={t.input_payload} />
              <h3>Metadata</h3>
              <JsonViewer value={t.metadata} />
            </div>
          ) : tab === "Annotations" ? (
            <div className="padded">
              {t.annotations?.length ? (
                t.annotations.map((a) => (
                  <div className="annotation-card" key={a.id}>
                    <Badge status={a.label} />
                    <strong>{a.score} / 5</strong>
                    <p>{a.feedback || "No written feedback."}</p>
                    <JsonViewer value={a.structured_payload} />
                  </div>
                ))
              ) : (
                <p className="muted">No annotations have been saved.</p>
              )}
            </div>
          ) : audit.data ? (
            <Activity events={audit.data} />
          ) : audit.error ? (
            <ErrorState error={audit.error} />
          ) : (
            <Skeleton />
          )}
        </section>
        <aside className="panel metadata">
          <h3>Task details</h3>
          <dl>
            <dt>Task ID</dt>
            <dd>
              <code>{t.id}</code>
            </dd>
            <dt>Project</dt>
            <dd>
              <Link to={`/projects/${t.project_id}`}>{t.project?.name}</Link>
            </dd>
            <dt>Model</dt>
            <dd>
              {runs.data
                ?.map((r) => `${r.model_name} ${r.model_version}`)
                .join(", ") || "No runs"}
            </dd>
            <dt>Priority</dt>
            <dd>{t.priority} / 100</dd>
            <dt>Annotator</dt>
            <dd>{assignee?.full_name || "Unassigned"}</dd>
            <dt>Created</dt>
            <dd>{time(t.created_at)}</dd>
            <dt>Last updated</dt>
            <dd>{time(t.updated_at)}</dd>
          </dl>
          <div className="metadata-note">
            <ShieldCheck size={18} />
            <p>
              Full provenance retained across every step of the feedback loop.
            </p>
          </div>
        </aside>
      </div>
      {review && (
        <Modal title="Record human review" onClose={() => setReview(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              approve.mutate();
            }}
          >
            <label>
              Decision
              <Select
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
              >
                <option value="APPROVED">Approve for training</option>
                <option value="REJECTED">Reject and allow reannotation</option>
              </Select>
            </label>
            <label>
              Review rationale
              <textarea
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain your decision for the audit trail."
              />
            </label>
            {approve.error && <ErrorState error={approve.error} />}
            <Button disabled={approve.isPending}>Submit review</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
