import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, ShieldCheck } from "lucide-react";
import { api, send } from "../api";
import { useApp } from "../context";
import type { TaskPage } from "../types";
import {
  PageHeading,
  Button,
  Select,
  Input,
  Modal,
  Table,
  Skeleton,
  ErrorState,
  EmptyState,
  JsonViewer,
} from "../components/ui";
interface Gold {
  id: string;
  task_id: string;
  external_id: string;
  expected: Record<string, unknown>;
  tolerance: number;
}
export default function GoldTasks() {
  const { project, notify } = useApp(),
    qc = useQueryClient(),
    [open, setOpen] = useState(false),
    [task, setTask] = useState(""),
    [expected, setExpected] = useState('{"label":"SUCCESS","score":5}'),
    [tolerance, setTolerance] = useState("0");
  const q = useQuery({
      queryKey: ["gold-tasks"],
      queryFn: () => api<Gold[]>("/gold-tasks"),
    }),
    tasks = useQuery({
      queryKey: ["gold-candidates", project],
      queryFn: () =>
        api<TaskPage>(
          `/tasks?status=INGESTED&page_size=100${project ? `&project_id=${project}` : ""}`,
        ),
    });
  const create = useMutation({
    mutationFn: () => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(expected);
      } catch {
        throw new Error("Expected answers must be valid JSON");
      }
      return send(`/tasks/${task}/gold`, {
        expected: parsed,
        tolerance: Number(tolerance),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      setOpen(false);
      notify("Gold reference created; enqueue it from the task explorer");
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="ANNOTATOR CALIBRATION"
        title="Gold reference tasks"
        description="Reference answers stay hidden from annotators. Gold work never enters training datasets."
        action={
          <Button onClick={() => setOpen(true)}>
            <Plus size={15} />
            Designate gold task
          </Button>
        }
      />
      <div className="quality-warning">
        <ShieldCheck size={18} />
        <p>
          Gold accuracy is shown separately from peer agreement and review
          outcomes. Queue insertion follows each project’s configured cadence.
        </p>
      </div>
      <section className="panel">
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data.length ? (
          <EmptyState
            title="No reference tasks yet"
            description="Choose an ingested task, define its expected answers, and enqueue it normally."
          />
        ) : (
          <Table headers={["Task", "Expected answers", "Numeric tolerance"]}>
            {q.data.map((g) => (
              <tr key={g.id}>
                <td>
                  <Link className="text-link" to={`/tasks/${g.task_id}`}>
                    {g.external_id || g.task_id.slice(0, 8)}
                  </Link>
                </td>
                <td>
                  <JsonViewer value={g.expected} />
                </td>
                <td>{g.tolerance}</td>
              </tr>
            ))}
          </Table>
        )}
      </section>
      {open && (
        <Modal title="Designate gold reference" onClose={() => setOpen(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label>
              Ingested task
              <Select
                required
                value={task}
                onChange={(e) => setTask(e.target.value)}
              >
                <option value="">Select task…</option>
                {tasks.data?.items.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.external_id || t.id.slice(0, 8)} · {t.task_type}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              Expected answers · label, score, values
              <textarea
                className="code-input"
                rows={6}
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
              />
            </label>
            <label>
              Numeric tolerance
              <Input
                type="number"
                min={0}
                step="any"
                value={tolerance}
                onChange={(e) => setTolerance(e.target.value)}
              />
            </label>
            {create.error && <ErrorState error={create.error} />}
            <Button disabled={create.isPending || !task}>Save reference</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
