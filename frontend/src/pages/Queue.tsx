import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCheck, Save, Keyboard, ScanEye } from "lucide-react";
import { api, send, time } from "../api";
import type { Assignment, Annotation, Task, Overview } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  Button,
  Badge,
  Select,
  ErrorState,
  Skeleton,
  EmptyState,
  Input,
} from "../components/ui";
import { Trace } from "../components/Trace";
export default function Queue() {
  const { user, project, notify } = useApp(),
    qc = useQueryClient(),
    [selected, setSelected] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["assignments"],
    queryFn: () => api<Assignment[]>("/annotation/assignments"),
    enabled: user.role !== "REVIEWER",
  });
  const stats = useQuery({
    queryKey: ["overview", project],
    queryFn: () =>
      api<Overview>(`/overview${project ? `?project_id=${project}` : ""}`),
  });
  const claim = useMutation({
    mutationFn: () =>
      send<Assignment>(
        `/annotation/next${project ? `?project_id=${project}` : ""}`,
      ),
    onSuccess: async (a) => {
      await send(`/assignments/${a.id}/start`);
      setSelected(a.id);
      qc.invalidateQueries({ queryKey: ["assignments"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      notify("Assignment ready");
    },
  });
  const active =
    selected ||
    q.data?.find((a) => ["ASSIGNED", "STARTED"].includes(a.status))?.id;
  if (user.role === "REVIEWER")
    return (
      <>
        <PageHeading
          eyebrow="HUMAN OVERSIGHT"
          title="Review queue"
          description="Inspect annotations and record an independent approval decision."
        />
        <EmptyState
          title={`${stats.data?.counts.PENDING_REVIEW || 0} tasks await review`}
          description="Open a task in the explorer, inspect its trace and annotations, then select Review task."
          action={
            <Link className="button primary" to="/tasks">
              Open task explorer
              <ArrowRight size={16} />
            </Link>
          }
        />
      </>
    );
  return (
    <>
      <PageHeading
        eyebrow="HUMAN IN THE LOOP"
        title="Annotation workspace"
        description="Turn agent behavior into high-quality human feedback."
        action={
          <div className="actions">
            <Badge>{stats.data?.queue.length || 0} in queue</Badge>
            <Button onClick={() => claim.mutate()} disabled={claim.isPending}>
              <ArrowRight size={16} />
              {active ? "Resume assignment" : "Claim next task"}
            </Button>
          </div>
        }
      />
      {claim.error && <ErrorState error={claim.error} />}
      <div className="workspace-status">
        <span>
          <span className="live-dot" />{" "}
          {active
            ? "Assignment reserved for you"
            : "Ready for your next assignment"}
        </span>
        <span>
          <Keyboard size={14} />
          Tab to navigate · ⌘/Ctrl + Enter to save
        </span>
      </div>
      {q.isPending ? (
        <Skeleton />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : active ? (
        <AssignmentWorkspace
          key={active}
          id={active}
          onComplete={() => {
            setSelected(null);
            qc.invalidateQueries();
            notify("Annotation submitted for independent review");
          }}
        />
      ) : (
        <EmptyState
          title="A fresh perspective makes better agents."
          description="Claim a task to review the complete trajectory and contribute your feedback."
          action={
            <Button onClick={() => claim.mutate()} disabled={claim.isPending}>
              Start annotating
              <ArrowRight size={16} />
            </Button>
          }
        />
      )}
      <section className="panel assignment-history">
        <div className="section-heading">
          <h2>Your recent assignments</h2>
          <span>
            {q.data?.filter((a) => a.status === "COMPLETED").length || 0}{" "}
            completed
          </span>
        </div>
        {q.data?.length ? (
          q.data.slice(0, 5).map((a) => (
            <div className="member-row" key={a.id}>
              <ScanEye size={17} />
              <Link to={`/tasks/${a.task_id}`}>
                <code>{a.task_id.slice(0, 8)}</code>
              </Link>
              <time>{time(a.assigned_at)}</time>
              <Badge status={a.status} />
            </div>
          ))
        ) : (
          <p className="padded muted">
            Your annotation history will appear here.
          </p>
        )}
      </section>
    </>
  );
}
function AssignmentWorkspace({
  id,
  onComplete,
}: {
  id: string;
  onComplete: () => void;
}) {
  const q = useQuery({
    queryKey: ["assignment", id],
    queryFn: () => api<Assignment>(`/annotation/assignments/${id}`),
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  return <Editor assignment={q.data} onComplete={onComplete} />;
}
function Editor({
  assignment,
  onComplete,
}: {
  assignment: Assignment;
  onComplete: () => void;
}) {
  const { notify } = useApp(),
    qc = useQueryClient(),
    [label, setLabel] = useState(assignment.annotation?.label || "SUCCESS"),
    [score, setScore] = useState(assignment.annotation?.score || 3),
    [feedback, setFeedback] = useState(assignment.annotation?.feedback || ""),
    [structured, setStructured] = useState(
      JSON.stringify(assignment.annotation?.structured_payload || {}, null, 2),
    ),
    [saved, setSaved] = useState(assignment.annotation?.id),
    [dirty, setDirty] = useState(false);
  const task = useQuery({
    queryKey: ["task", assignment.task_id],
    queryFn: () => api<Task>(`/tasks/${assignment.task_id}`),
  });
  const save = useMutation({
    mutationFn: async () => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(structured);
      } catch {
        throw new Error("Structured fields must contain valid JSON");
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Structured fields must be a JSON object");
      await send(`/assignments/${assignment.id}/start`);
      return send<Annotation>(
        saved
          ? `/annotations/${saved}`
          : `/assignments/${assignment.id}/annotations`,
        { label, score, feedback, structured_payload: parsed },
        saved ? "PATCH" : "POST",
      );
    },
    onSuccess: (a) => {
      setSaved(a.id);
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["assignment", assignment.id] });
      notify("Annotation draft saved");
    },
  });
  const complete = useMutation({
    mutationFn: () => send(`/assignments/${assignment.id}/complete`),
    onSuccess: onComplete,
  });
  const changed = () => setDirty(true);
  return (
    <div className="annotation-layout">
      <section className="panel trace-main">
        <div className="section-heading">
          <div>
            <h2>{task.data?.external_id || assignment.task_id.slice(0, 8)}</h2>
            <p>Read the complete trajectory before scoring</p>
          </div>
          <Link className="text-link" to={`/tasks/${assignment.task_id}`}>
            Full details
            <ArrowRight size={14} />
          </Link>
        </div>
        {task.error && <ErrorState error={task.error} />}
        <Trace taskId={assignment.task_id} />
      </section>
      <aside className="panel annotation-form">
        <div className="section-heading">
          <div>
            <h2>Your evaluation</h2>
            <p>Assignment {assignment.id.slice(0, 8)}</p>
          </div>
          <span className="step-count">{saved ? "2" : "1"} / 2</span>
        </div>
        <div className="form-progress">
          <span style={{ width: saved ? "100%" : "50%" }} />
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              if (!save.isPending) save.mutate();
            }
          }}
        >
          <fieldset disabled={save.isPending || complete.isPending}>
            <label>
              Outcome label
              <Select
                value={label}
                onChange={(e) => {
                  setLabel(e.target.value);
                  changed();
                }}
              >
                <option value="SUCCESS">Success — task fully resolved</option>
                <option value="PARTIAL">Partial — room for improvement</option>
                <option value="FAILURE">Failure — task not resolved</option>
                <option value="UNSAFE">Unsafe — concerning behavior</option>
              </Select>
            </label>
            <label>
              Quality score
              <span className="score-selector">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={score === n ? "selected" : ""}
                    aria-label={`Score ${n}`}
                    aria-pressed={score === n}
                    onClick={() => {
                      setScore(n);
                      changed();
                    }}
                  >
                    {n}
                  </button>
                ))}
              </span>
              <span className="score-labels">
                <span>Poor</span>
                <span>Excellent</span>
              </span>
            </label>
            <label>
              Written feedback
              <textarea
                rows={5}
                value={feedback}
                onChange={(e) => {
                  setFeedback(e.target.value);
                  changed();
                }}
                placeholder="What did the agent do well? What should change?"
              />
            </label>
            <label>
              Structured fields <small>JSON object</small>
              <textarea
                className="code-input"
                rows={4}
                value={structured}
                onChange={(e) => {
                  setStructured(e.target.value);
                  changed();
                }}
                spellCheck={false}
              />
            </label>
            <label className="sr-only">
              Assignment
              <Input readOnly value={assignment.id} />
            </label>
            {save.error && <ErrorState error={save.error} />}
            <Button variant="secondary" type="submit" disabled={save.isPending}>
              <Save size={15} />
              {save.isPending
                ? "Saving…"
                : saved
                  ? "Update draft"
                  : "Save draft"}
            </Button>
          </fieldset>
        </form>
        <div className="complete-section">
          <p>
            {dirty
              ? "Save your changes before submitting."
              : "Completed annotations go to an independent reviewer."}
          </p>
          {complete.error && <ErrorState error={complete.error} />}
          <Button
            disabled={!saved || dirty || save.isPending || complete.isPending}
            onClick={() => complete.mutate()}
          >
            <CheckCheck size={16} />
            {complete.isPending ? "Submitting…" : "Complete assignment"}
          </Button>
        </div>
      </aside>
    </div>
  );
}
