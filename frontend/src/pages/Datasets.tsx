import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  Plus,
  Database,
  ArrowUpRight,
  ArrowLeft,
  LockKeyhole,
  Download,
  GitBranch,
  ShieldCheck,
  Check,
  RefreshCw,
} from "lucide-react";
import { api, send, time, downloadArtifact } from "../api";
import { useApp } from "../context";
import type {
  Dataset,
  DatasetVersion,
  ExamplePreview,
  ExportJob,
  GateResult,
} from "../quality-types";
import type { Task, Run, Annotation } from "../types";
import {
  PageHeading,
  Button,
  Input,
  Select,
  Modal,
  Table,
  Badge,
  ErrorState,
  Skeleton,
  EmptyState,
  JsonViewer,
} from "../components/ui";
export default function Datasets() {
  const { user, notify } = useApp(),
    qc = useQueryClient(),
    navigate = useNavigate(),
    [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const q = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Dataset[]>("/datasets"),
  });
  const create = useMutation({
    mutationFn: () => send<Dataset>("/datasets", { name, description }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      notify("Dataset created");
      navigate(`/datasets/${d.id}/builder`);
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="TRUSTED TRAINING DATA"
        title="Datasets"
        description="Reproducible collections of human-reviewed examples, with provenance intact."
        action={
          <div className="actions">
            <Link className="button secondary" to="/exports">
              <Download size={15} />
              Export history
            </Link>
            {user.role === "ADMIN" && (
              <Button onClick={() => setOpen(true)}>
                <Plus size={16} />
                New dataset
              </Button>
            )}
          </div>
        }
      />
      {q.isPending ? (
        <Skeleton />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data.length ? (
        <EmptyState
          title="Your first trusted dataset starts here."
          description="Create training examples from reviewed tasks, then select them into an immutable dataset version."
          action={
            user.role === "ADMIN" && (
              <Button onClick={() => setOpen(true)}>Create dataset</Button>
            )
          }
        />
      ) : (
        <div className="project-grid">
          {q.data.map((d) => (
            <Link
              to={`/datasets/${d.id}`}
              className="panel project-card"
              key={d.id}
            >
              <div className="project-card-top">
                <div className="project-icon">
                  <Database size={22} />
                </div>
                <Badge>{d.versions.length} versions</Badge>
                <ArrowUpRight size={16} />
              </div>
              <h2>{d.name}</h2>
              <p>
                {d.description ||
                  "A collection of human-reviewed training examples."}
              </p>
              <footer>
                <span>
                  <strong>{d.versions[0]?.example_count || 0}</strong> examples
                  in latest version
                </span>
                <span>
                  {d.versions[0]?.status === "FINALIZED" ? (
                    <LockKeyhole size={13} />
                  ) : (
                    "Draft"
                  )}
                </span>
              </footer>
            </Link>
          ))}
        </div>
      )}
      {open && (
        <Modal title="Create dataset" onClose={() => setOpen(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label>
              Name
              <Input
                required
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="argus-agent-quality"
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            {create.error && <ErrorState error={create.error} />}
            <Button disabled={create.isPending}>
              Create & select examples
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
export function DatasetDetail() {
  const { id } = useParams(),
    { user } = useApp();
  const q = useQuery({
    queryKey: ["dataset", id],
    queryFn: () => api<Dataset>(`/datasets/${id}`),
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <>
      <Link to="/datasets" className="back-link">
        <ArrowLeft size={14} />
        Datasets
      </Link>
      <PageHeading
        eyebrow="DATASET"
        title={d.name}
        description={d.description}
        action={
          user.role === "ADMIN" && (
            <Link className="button primary" to={`/datasets/${id}/builder`}>
              <Plus size={15} />
              Build new version
            </Link>
          )
        }
      />
      <div className="dataset-summary">
        <section className="panel padded">
          <h3>Source projects</h3>
          <div className="tag-list">
            {d.source_projects?.length ? (
              d.source_projects.map((p) => <Badge key={p}>{p}</Badge>)
            ) : (
              <span className="form-note">
                Sources appear when a version is created.
              </span>
            )}
          </div>
        </section>
        <section className="panel padded">
          <h3>Annotation quality distribution</h3>
          <div className="quality-score-bars">
            {Object.entries(d.quality_distribution || {}).map(
              ([score, count]) => (
                <span key={score}>
                  <strong>{count}</strong>
                  <small>Score {score}</small>
                </span>
              ),
            )}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Version history</h2>
          <span>Created {time(d.created_at)}</span>
        </div>
        {!d.versions.length ? (
          <EmptyState
            title="No versions yet"
            description="Choose eligible examples in the dataset builder, then finalize a reproducible snapshot."
          />
        ) : (
          <Table
            headers={[
              "Version",
              "State",
              "Examples",
              "Created",
              "Checksum",
              "",
            ]}
          >
            {d.versions.map((v) => (
              <tr key={v.id}>
                <td>
                  <Link className="text-link" to={`/dataset-versions/${v.id}`}>
                    v{v.version}
                  </Link>
                </td>
                <td>
                  <Badge status={v.status} />
                </td>
                <td>{v.example_count}</td>
                <td>{time(v.created_at)}</td>
                <td>
                  <code>{v.checksum?.slice(0, 16) || "Not finalized"}</code>
                </td>
                <td>
                  <Link to={`/dataset-versions/${v.id}`}>
                    <ArrowUpRight size={15} />
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
export function DatasetBuilder() {
  const { id } = useParams(),
    { project, notify } = useApp(),
    navigate = useNavigate(),
    qc = useQueryClient();
  const [type, setType] = useState(""),
    [model, setModel] = useState(""),
    [label, setLabel] = useState(""),
    [score, setScore] = useState("1"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [metadata, setMetadata] = useState("{}"),
    [selected, setSelected] = useState<string[]>([]);
  let parsed: Record<string, unknown> = {},
    parseError = false;
  try {
    const v: unknown = JSON.parse(metadata);
    if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error();
    parsed = v as Record<string, unknown>;
  } catch {
    parseError = true;
  }
  const filters = {
    ...(project ? { project_id: project } : {}),
    ...(type ? { task_type: type } : {}),
    ...(model ? { model } : {}),
    ...(label ? { annotation_label: label } : {}),
    minimum_score: Number(score),
    reviewer_decision: "APPROVED",
    ...(from ? { date_from: `${from}T00:00:00Z` } : {}),
    ...(to ? { date_to: `${to}T23:59:59Z` } : {}),
    metadata: parsed,
  };
  const q = useQuery({
    queryKey: ["eligible-examples", JSON.stringify(filters)],
    queryFn: () =>
      send<{ items: ExamplePreview[]; eligible_count: number }>(
        "/training-examples/preview",
        filters,
      ),
    enabled: !parseError,
  });
  const materialize = useMutation({
    mutationFn: () =>
      send<{ example_ids: string[]; blocked: unknown[]; scanned: number }>(
        `/training-examples/materialize${project ? `?project_id=${project}` : ""}`,
      ),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["eligible-examples"] });
      notify(
        `${r.example_ids.length} examples ready; ${r.blocked.length} blocked by quality gates`,
      );
    },
  });
  const chosen = selected.filter((x) => q.data?.items.some((e) => e.id === x));
  const build = useMutation({
    mutationFn: () =>
      send<DatasetVersion>(`/datasets/${id}/versions`, {
        example_ids: chosen,
        filters,
      }),
    onSuccess: (v) => {
      qc.invalidateQueries();
      notify("Draft version created");
      navigate(`/dataset-versions/${v.id}`);
    },
  });
  return (
    <>
      <Link to={`/datasets/${id}`} className="back-link">
        <ArrowLeft size={14} />
        Dataset
      </Link>
      <PageHeading
        eyebrow="DATASET BUILDER"
        title="Curate your next training run."
        description="Only examples passing current quality gates appear here. Finalization checks them again."
        action={
          <Button
            variant="secondary"
            disabled={materialize.isPending}
            onClick={() => materialize.mutate()}
          >
            <RefreshCw size={15} />
            {materialize.isPending
              ? "Evaluating…"
              : "Prepare approved examples"}
          </Button>
        }
      />
      <section className="panel builder-filters">
        <div className="form-two">
          <label>
            Task type
            <Input
              value={type}
              onChange={(e) => setType(e.target.value)}
              placeholder="Any task type"
            />
          </label>
          <label>
            Model
            <Input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Any model"
            />
          </label>
          <label>
            Annotation label
            <Select value={label} onChange={(e) => setLabel(e.target.value)}>
              <option value="">Any label</option>
              {["SUCCESS", "PARTIAL", "FAILURE", "UNSAFE"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
          </label>
          <label>
            Minimum annotation score
            <Input
              type="number"
              min={1}
              max={5}
              step={0.1}
              value={score}
              onChange={(e) => setScore(e.target.value)}
            />
          </label>
          <label>
            Created from
            <Input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label>
            Created through
            <Input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        </div>
        <label>
          Task metadata filter · exact top-level key/value match
          <Input
            className="code-input"
            value={metadata}
            onChange={(e) => setMetadata(e.target.value)}
          />
        </label>
        <p className="form-note">
          Project scope follows the global project selector. Reviewer decision
          is restricted to approved human evidence.
        </p>
      </section>
      {materialize.error && <ErrorState error={materialize.error} />}{" "}
      {build.error && <ErrorState error={build.error} />}
      <section className="panel">
        <div className="section-heading">
          <div className="actions">
            <Badge>Eligible examples: {q.data?.eligible_count || 0}</Badge>
            <Badge>Selected examples: {chosen.length}</Badge>
          </div>
          <Button
            disabled={!chosen.length || build.isPending || parseError}
            onClick={() => build.mutate()}
          >
            Create draft version
            <ArrowUpRight size={15} />
          </Button>
        </div>
        {parseError ? (
          <ErrorState
            error={new Error("Metadata must be a valid JSON object")}
          />
        ) : q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data.items.length ? (
          <EmptyState
            title="No eligible examples match these filters"
            description="Prepare approved examples, adjust your filters, or inspect quality gates in the review workspace."
          />
        ) : (
          <>
            <div className="selection-toolbar">
              <Button
                variant="ghost"
                onClick={() => setSelected(q.data.items.map((e) => e.id))}
              >
                Select all
              </Button>
              <Button variant="ghost" onClick={() => setSelected([])}>
                Clear selection
              </Button>
            </div>
            <Table
              headers={[
                "Select",
                "Task",
                "Type",
                "Models",
                "Quality",
                "Labels",
                "Lineage",
              ]}
            >
              {q.data.items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <input
                      className="table-checkbox"
                      type="checkbox"
                      aria-label={`Select ${e.external_id || e.task_id}`}
                      checked={chosen.includes(e.id)}
                      onChange={(event) =>
                        setSelected(
                          event.target.checked
                            ? [...selected, e.id]
                            : selected.filter((x) => x !== e.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link className="text-link" to={`/tasks/${e.task_id}`}>
                      {e.external_id || e.task_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td>{e.task_type}</td>
                  <td>{e.models.join(", ")}</td>
                  <td>{e.score.toFixed(2)} / 5</td>
                  <td>{[...new Set(e.labels)].join(", ")}</td>
                  <td>
                    <Link to={`/lineage/${e.id}`} aria-label="Inspect lineage">
                      <GitBranch size={15} />
                    </Link>
                  </td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </section>
    </>
  );
}
export function VersionDetail() {
  const { id } = useParams(),
    { user, notify } = useApp(),
    qc = useQueryClient(),
    [format, setFormat] = useState("sft"),
    [container, setContainer] = useState("jsonl");
  const q = useQuery({
    queryKey: ["dataset-version", id],
    queryFn: () => api<DatasetVersion>(`/dataset-versions/${id}`),
  });
  const finalize = useMutation({
    mutationFn: () => send(`/dataset-versions/${id}/finalize`),
    onSuccess: () => {
      qc.invalidateQueries();
      notify("Dataset version finalized and locked");
    },
  });
  const exportJob = useMutation({
    mutationFn: () =>
      send(`/dataset-versions/${id}/exports`, { format, container }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["exports"] });
      notify("Export queued for the background worker");
    },
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const v = q.data;
  return (
    <>
      <Link className="back-link" to={`/datasets/${v.dataset_id}`}>
        <ArrowLeft size={14} />
        Dataset
      </Link>
      <PageHeading
        eyebrow="REPRODUCIBLE SNAPSHOT"
        title={`Dataset version ${v.version}`}
        description={`${v.example_count} examples · ${v.schema_version} · Created ${time(v.created_at)}`}
        action={
          <div className="actions">
            <Badge status={v.status} />
            {user.role === "ADMIN" && v.status === "DRAFT" && (
              <Button
                disabled={finalize.isPending}
                onClick={() => finalize.mutate()}
              >
                <LockKeyhole size={15} />
                Finalize version
              </Button>
            )}
          </div>
        }
      />
      {finalize.error && <ErrorState error={finalize.error} />}
      <div className="version-layout">
        <section className="panel">
          <div className="section-heading">
            <h2>Examples & lineage</h2>
            <GitBranch size={17} />
          </div>
          <Table
            headers={[
              "Originating task",
              "Type",
              "Example checksum",
              "Lineage",
            ]}
          >
            {v.examples?.map((e) => (
              <tr key={e.id}>
                <td>
                  <Link className="text-link" to={`/tasks/${e.task_id}`}>
                    {e.external_id || e.task_id.slice(0, 8)}
                  </Link>
                </td>
                <td>{e.task_type}</td>
                <td>
                  <code>{e.checksum.slice(0, 12)}</code>
                </td>
                <td>
                  <Link to={`/lineage/${e.id}`} className="text-link">
                    Trace provenance
                    <ArrowUpRight size={13} />
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        </section>
        <aside className="panel padded version-metadata">
          <h3>
            {v.status === "FINALIZED"
              ? "Immutable version metadata"
              : "Draft metadata"}
          </h3>
          <label>
            SHA-256 checksum
            <code>{v.checksum || "Computed at finalization"}</code>
          </label>
          <details>
            <summary>Recorded filters</summary>
            <JsonViewer value={v.filters} />
          </details>
          <details>
            <summary>Version metadata</summary>
            <JsonViewer value={v.metadata} />
          </details>
          {v.status === "FINALIZED" && user.role === "ADMIN" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                exportJob.mutate();
              }}
            >
              <h3>Export training data</h3>
              <label>
                Training format
                <Select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option value="sft">SFT · messages</option>
                  <option value="dpo">DPO · real preference pairs</option>
                  <option value="reward">
                    Reward model · scored responses
                  </option>
                  <option value="trajectory">
                    Agent trajectory · full traces
                  </option>
                </Select>
              </label>
              <label>
                File format
                <Select
                  value={container}
                  onChange={(e) => setContainer(e.target.value)}
                >
                  <option value="jsonl">JSONL</option>
                  <option value="json">JSON</option>
                </Select>
              </label>
              <p className="form-note">
                Unsupported examples block the export. Missing preference pairs
                are never fabricated.
              </p>
              {exportJob.error && <ErrorState error={exportJob.error} />}
              <Button disabled={exportJob.isPending}>
                <Download size={15} />
                Queue export
              </Button>
            </form>
          )}
        </aside>
      </div>
      <ExportHistory versionId={id} embedded />
    </>
  );
}
export function ExportHistory({
  versionId,
  embedded = false,
}: {
  versionId?: string;
  embedded?: boolean;
}) {
  const [error, setError] = useState<Error | null>(null);
  const q = useQuery({
    queryKey: ["exports", versionId],
    queryFn: () =>
      api<ExportJob[]>(
        `/exports${versionId ? `?version_id=${versionId}` : ""}`,
      ),
    refetchInterval: 3000,
  });
  async function download(job: ExportJob, artifact: string) {
    try {
      await downloadArtifact(
        `/exports/${job.id}/files/${artifact}`,
        artifact === "dataset"
          ? `dataset.${job.container}`
          : `${artifact}.json`,
      );
    } catch (e) {
      setError(e as Error);
    }
  }
  return (
    <>
      {!embedded && (
        <PageHeading
          eyebrow="BACKGROUND EXPORTS"
          title="Export history"
          description="Versioned artifacts, checksums, schema information, and row-level provenance."
        />
      )}
      <section className="panel export-history">
        <div className="section-heading">
          <h2>Export jobs</h2>
          <span>Refreshes every 3 seconds</span>
        </div>
        {error && <ErrorState error={error} />}{" "}
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data.length ? (
          <EmptyState
            title="No exports yet"
            description="Finalize a dataset version to generate its training artifacts."
          />
        ) : (
          <Table
            headers={["Requested", "Format", "Status", "Artifacts", "Details"]}
          >
            {q.data.map((j) => (
              <tr key={j.id}>
                <td>{time(j.created_at)}</td>
                <td>
                  {j.format.toUpperCase()} / {j.container.toUpperCase()}
                </td>
                <td>
                  <Badge status={j.status} />
                </td>
                <td>
                  {j.status === "COMPLETED" ? (
                    <div className="artifact-buttons">
                      {["dataset", "manifest", "schema", "provenance"].map(
                        (a) => (
                          <Button
                            variant="ghost"
                            key={a}
                            onClick={() => download(j, a)}
                          >
                            <Download size={12} />
                            {a}
                          </Button>
                        ),
                      )}
                    </div>
                  ) : j.error ? (
                    <span className="export-error">{j.error}</span>
                  ) : (
                    <span className="muted">
                      {j.status === "PENDING"
                        ? "Waiting for worker"
                        : "Generating artifacts…"}
                    </span>
                  )}
                </td>
                <td>
                  <details>
                    <summary>Manifest</summary>
                    <JsonViewer value={j.manifest} />
                  </details>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </section>
    </>
  );
}
interface LineageData {
  example: {
    id: string;
    task_id: string;
    checksum: string;
    created_at: string;
    snapshot: {
      task: Task;
      project: { name: string };
      runs: Run[];
      annotations: Annotation[];
      reviews: {
        id: string;
        decision: string;
        comments: string;
        reviewer_id: string;
      }[];
      quality_gate: GateResult;
      annotation_schema: unknown;
      preference_pair: unknown;
    };
  };
  versions: { version: DatasetVersion; finalization_gate: GateResult | null }[];
}
export function Lineage() {
  const { id } = useParams();
  const q = useQuery({
    queryKey: ["lineage", id],
    queryFn: () => api<LineageData>(`/training-examples/${id}/lineage`),
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const e = q.data.example,
    s = e.snapshot;
  return (
    <>
      <PageHeading
        eyebrow="END-TO-END PROVENANCE"
        title="Every example has a history."
        description={`${s.project.name} · ${s.task.external_id || s.task.id} · Frozen source evidence`}
      />
      <div className="lineage-flow">
        {[
          {
            title: "Dataset versions",
            icon: Database,
            content: (
              <>
                {q.data.versions.map((v) => (
                  <div key={v.version.id}>
                    <Link
                      className="text-link"
                      to={`/dataset-versions/${v.version.id}`}
                    >
                      Version {v.version.version} · {v.version.status}
                    </Link>
                    {v.finalization_gate && (
                      <details>
                        <summary>Finalization quality gate</summary>
                        <JsonViewer value={v.finalization_gate} />
                      </details>
                    )}
                  </div>
                ))}
                {!q.data.versions.length && (
                  <p>Not yet included in a version.</p>
                )}
              </>
            ),
          },
          {
            title: "Training example",
            icon: ShieldCheck,
            content: (
              <>
                <code>{e.id}</code>
                <p>Created {time(e.created_at)}</p>
                <small>Evidence checksum</small>
                <code>{e.checksum}</code>
              </>
            ),
          },
          {
            title: "Originating task",
            icon: GitBranch,
            content: (
              <>
                <Link className="text-link" to={`/tasks/${e.task_id}`}>
                  {s.task.external_id || e.task_id}
                  <ArrowUpRight size={14} />
                </Link>
                <JsonViewer value={s.task.input_payload} />
              </>
            ),
          },
          {
            title: "Agent runs & complete trajectories",
            icon: GitBranch,
            content: (
              <>
                {s.runs.map((r) => (
                  <details key={r.id}>
                    <summary>
                      {r.model_name} · {r.steps.length} steps ·{" "}
                      {r.id.slice(0, 8)}
                    </summary>
                    <JsonViewer value={r} />
                  </details>
                ))}
              </>
            ),
          },
          {
            title: "Independent human annotations",
            icon: Check,
            content: (
              <>
                {s.annotations.map((a) => (
                  <details key={a.id}>
                    <summary>
                      {a.label} · {a.score}/5 · annotator{" "}
                      {a.annotator_id.slice(0, 8)}
                    </summary>
                    <JsonViewer value={a} />
                  </details>
                ))}
              </>
            ),
          },
          {
            title: "Human review evidence",
            icon: ShieldCheck,
            content: (
              <>
                {s.reviews.map((r) => (
                  <article key={r.id}>
                    <Badge status={r.decision} />
                    <p>{r.comments}</p>
                    <code>Reviewer {r.reviewer_id}</code>
                  </article>
                ))}
                {s.preference_pair && (
                  <details>
                    <summary>Preference evidence</summary>
                    <JsonViewer value={s.preference_pair} />
                  </details>
                )}
              </>
            ),
          },
          {
            title: "Admission quality gate",
            icon: LockKeyhole,
            content: (
              <>
                <Badge
                  status={s.quality_gate.eligible ? "APPROVED" : "REJECTED"}
                >
                  {s.quality_gate.eligible
                    ? "All configured gates passed"
                    : "Blocked"}
                </Badge>
                <JsonViewer value={s.quality_gate} />
                <details>
                  <summary>Pinned annotation schema</summary>
                  <JsonViewer value={s.annotation_schema} />
                </details>
              </>
            ),
          },
        ].map((node, i) => (
          <section className="lineage-node" key={node.title}>
            <div className="lineage-node-icon">
              <node.icon size={19} />
            </div>
            <div className="panel">
              <div className="section-heading">
                <h2>{node.title}</h2>
                <span>{String(i + 1).padStart(2, "0")}</span>
              </div>
              <div className="padded">{node.content}</div>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
