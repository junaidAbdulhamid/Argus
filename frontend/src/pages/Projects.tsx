import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Plus, FolderKanban, ArrowUpRight, MoreHorizontal } from "lucide-react";
import { api, send } from "../api";
import type { Project, Overview, User } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  Button,
  Modal,
  Input,
  ErrorState,
  Skeleton,
  EmptyState,
  Badge,
  Tabs,
  MetricCard,
  Dropdown,
} from "../components/ui";
import { Activity } from "../components/Trace";
import Tasks from "./Tasks";
export default function Projects() {
  const { user, notify } = useApp(),
    qc = useQueryClient(),
    [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const q = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const create = useMutation({
    mutationFn: () => send<Project>("/projects", { name, description }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      setName("");
      setDescription("");
      notify("Project created");
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE"
        title="Projects"
        description="Organize agent evaluations into focused feedback loops."
        action={
          user.role === "ADMIN" && (
            <Button onClick={() => setOpen(true)}>
              <Plus size={16} />
              New project
            </Button>
          )
        }
      />
      {q.isPending ? (
        <Skeleton />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data.length ? (
        <EmptyState
          title="Create your first project"
          description="A project brings tasks, trajectories, and human feedback together."
        />
      ) : (
        <div className="project-grid">
          {q.data.map((p) => (
            <Link
              key={p.id}
              className="panel project-card"
              to={`/projects/${p.id}`}
            >
              <div className="project-card-top">
                <div className="project-icon">
                  <FolderKanban size={22} />
                </div>
                <Badge status={p.status} />
                <ArrowUpRight size={17} />
              </div>
              <h2>{p.name}</h2>
              <p>{p.description || "No description yet."}</p>
              <div className="project-progress">
                <span
                  style={{
                    width: `${p.counts.total ? ((p.counts.APPROVED || 0) / p.counts.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <footer>
                <span>
                  <strong>{p.counts.total || 0}</strong> tasks
                </span>
                <span>
                  <strong>{p.counts.PENDING_REVIEW || 0}</strong> awaiting
                  review
                </span>
              </footer>
            </Link>
          ))}
        </div>
      )}
      {open && (
        <Modal title="Create project" onClose={() => setOpen(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label>
              Project name
              <Input
                autoFocus
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Research agent evaluation"
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What behavior are you improving?"
              />
            </label>
            {create.error && <ErrorState error={create.error} />}
            <Button disabled={create.isPending}>Create project</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
export function ProjectDetail() {
  const { id } = useParams(),
    { user, notify } = useApp(),
    qc = useQueryClient(),
    navigate = useNavigate(),
    [tab, setTab] = useState("Overview"),
    [confirm, setConfirm] = useState(false),
    [editing, setEditing] = useState(false),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const q = useQuery({
    queryKey: ["project", id],
    queryFn: () => api<Project>(`/projects/${id}`),
  });
  const stats = useQuery({
    queryKey: ["overview", id],
    queryFn: () => api<Overview>(`/overview?project_id=${id}`),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });
  const mutate = useMutation({
    mutationFn: (data: object) => send(`/projects/${id}`, data, "PATCH"),
    onSuccess: () => {
      qc.invalidateQueries();
      setEditing(false);
      notify("Project updated");
    },
  });
  const remove = useMutation({
    mutationFn: () => send(`/projects/${id}`, undefined, "DELETE"),
    onSuccess: () => {
      qc.invalidateQueries();
      navigate("/projects");
      notify("Project deleted");
    },
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const p = q.data;
  return (
    <>
      <PageHeading
        eyebrow="PROJECT"
        title={p.name}
        description={p.description}
        action={
          user.role === "ADMIN" && (
            <Dropdown label="Manage project">
              <Link className="button ghost" to={`/projects/${id}/quality`}>
                Schemas & quality gates
              </Link>
              <Button
                variant="ghost"
                onClick={() => {
                  setName(p.name);
                  setDescription(p.description);
                  setEditing(true);
                }}
              >
                Edit details
              </Button>
              <Button
                variant="ghost"
                onClick={() =>
                  mutate.mutate({
                    status: p.status === "ACTIVE" ? "ARCHIVED" : "ACTIVE",
                  })
                }
              >
                {p.status === "ACTIVE" ? "Archive" : "Activate"}
              </Button>
              <Button variant="danger" onClick={() => setConfirm(true)}>
                Delete project
              </Button>
            </Dropdown>
          )
        }
      />
      {mutate.error && <ErrorState error={mutate.error} />}
      <Tabs
        tabs={["Overview", "Tasks", "Annotators", "Activity"]}
        value={tab}
        onChange={setTab}
      />
      {tab === "Tasks" ? (
        <Tasks projectId={id} embedded />
      ) : tab === "Activity" ? (
        <section className="panel">
          {stats.data ? (
            <Activity events={stats.data.activity} />
          ) : stats.error ? (
            <ErrorState error={stats.error} />
          ) : (
            <Skeleton />
          )}
        </section>
      ) : tab === "Annotators" ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Available workspace annotators</h2>
          </div>
          {users.error ? (
            <ErrorState error={users.error} />
          ) : users.isPending ? (
            <Skeleton />
          ) : users.data.filter((u) => u.role === "ANNOTATOR").length ? (
            users.data
              .filter((u) => u.role === "ANNOTATOR")
              .map((u) => (
                <div className="member-row" key={u.id}>
                  <span className="avatar">{u.full_name.slice(0, 1)}</span>
                  <div>
                    <strong>{u.full_name}</strong>
                    <p>{u.email}</p>
                  </div>
                  <Badge status={u.role} />
                </div>
              ))
          ) : (
            <EmptyState
              title="No annotators yet"
              description="An administrator can create annotator accounts in Settings."
            />
          )}
        </section>
      ) : (
        <>
          <div className="metrics">
            {["total", "QUEUED", "PENDING_REVIEW", "APPROVED"].map((k) => (
              <MetricCard
                key={k}
                label={k.replaceAll("_", " ")}
                value={p.counts[k] || 0}
                caption="Project tasks"
                icon={<MoreHorizontal size={17} />}
              />
            ))}
          </div>
          <section className="panel" style={{ marginBottom: 24 }}>
            <div className="section-heading">
              <h2>Task status distribution</h2>
              <Badge status={p.status} />
            </div>
            <div className="distribution-list">
              {[
                "INGESTED",
                "QUEUED",
                "ASSIGNED",
                "ANNOTATED",
                "PENDING_REVIEW",
                "APPROVED",
                "REJECTED",
              ].map((status) => (
                <div key={status}>
                  <Badge status={status} />
                  <span>
                    {p.counts[status] || 0}
                    <small>
                      {p.counts.total
                        ? Math.round(
                            ((p.counts[status] || 0) / p.counts.total) * 100,
                          )
                        : 0}
                      %
                    </small>
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>Project activity</h2>
              <span>
                {stats.data?.completed_this_week || 0} annotations this week
              </span>
            </div>
            {stats.data ? (
              <Activity events={stats.data.activity} compact />
            ) : stats.error ? (
              <ErrorState error={stats.error} />
            ) : (
              <Skeleton />
            )}
          </section>
        </>
      )}
      {editing && (
        <Modal title="Edit project" onClose={() => setEditing(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutate.mutate({ name, description });
            }}
          >
            <label>
              Name
              <Input
                value={name}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <Button disabled={mutate.isPending}>Save changes</Button>
          </form>
        </Modal>
      )}
      {confirm && (
        <Modal title="Delete project?" onClose={() => setConfirm(false)}>
          <p>
            This permanently deletes this project, its tasks, runs, assignments,
            and annotations. Audit events are retained.
          </p>
          {remove.error && <ErrorState error={remove.error} />}
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Delete {p.name}
          </Button>
        </Modal>
      )}
    </>
  );
}
