import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ArrowLeft, ShieldCheck } from "lucide-react";
import { api, send } from "../api";
import { useApp } from "../context";
import type {
  AnnotationSchema,
  SchemaField,
  QualityRules,
} from "../quality-types";
import {
  PageHeading,
  Button,
  Input,
  Select,
  ErrorState,
  Skeleton,
  Badge,
  JsonViewer,
} from "../components/ui";
const fresh = (): SchemaField => ({
  key: "",
  label: "",
  field_type: "boolean",
  description: "",
  required: true,
  constraints: {},
  options: [],
});
export default function SchemaBuilder() {
  const { id } = useParams(),
    { user } = useApp();
  const schemas = useQuery({
    queryKey: ["schemas", id],
    queryFn: () =>
      api<AnnotationSchema[]>(`/projects/${id}/annotation-schemas`),
  });
  const rules = useQuery({
    queryKey: ["rules", id],
    queryFn: () => api<QualityRules>(`/projects/${id}/quality-rules`),
  });
  if (schemas.isPending || rules.isPending) return <Skeleton />;
  if (schemas.error || rules.error)
    return <ErrorState error={schemas.error || rules.error} />;
  return (
    <>
      <Link className="back-link" to={`/projects/${id}`}>
        <ArrowLeft size={14} />
        Project
      </Link>
      <PageHeading
        eyebrow="PROJECT QUALITY CONTROL"
        title="Define what good looks like."
        description="Versioned annotation schemas and explicit human quality requirements."
      />
      <div className="quality-config-grid">
        <SchemaEditor
          key={schemas.data[0]?.id || "new"}
          projectId={id!}
          schemas={schemas.data}
          editable={user.role === "ADMIN"}
        />
        <RulesEditor
          projectId={id!}
          initial={rules.data}
          editable={user.role === "ADMIN"}
        />
      </div>
    </>
  );
}
function SchemaEditor({
  projectId,
  schemas,
  editable,
}: {
  projectId: string;
  schemas: AnnotationSchema[];
  editable: boolean;
}) {
  const [name, setName] = useState(schemas[0]?.name || "Agent quality rubric"),
    [fields, setFields] = useState<SchemaField[]>(
      schemas[0]?.fields || [fresh()],
    ),
    { notify } = useApp(),
    qc = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      send(`/projects/${projectId}/annotation-schemas`, {
        name,
        fields: fields.map(
          ({
            key,
            label,
            field_type,
            description,
            required,
            constraints,
            options,
          }) => ({
            key,
            label,
            field_type,
            description,
            required,
            constraints,
            options,
          }),
        ),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schemas", projectId] });
      notify("New schema version published");
    },
  });
  const update = (index: number, patch: Partial<SchemaField>) =>
    setFields((items) =>
      items.map((f, i) => (i === index ? { ...f, ...patch } : f)),
    );
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Annotation schema</h2>
          <p>Existing tasks retain their pinned schema version</p>
        </div>
        <Badge>
          {schemas.length ? `v${schemas[0].version}` : "Not configured"}
        </Badge>
      </div>
      <form
        className="padded"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset disabled={!editable || save.isPending}>
          <label>
            Schema name
            <Input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          {fields.map((field, i) => (
            <div className="schema-field-card" key={i}>
              <header>
                <strong>Field {i + 1}</strong>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Remove field ${i + 1}`}
                  onClick={() => setFields(fields.filter((_, n) => i !== n))}
                >
                  <Trash2 size={14} />
                </Button>
              </header>
              <div className="form-two">
                <label>
                  Key
                  <Input
                    required
                    pattern="[a-z][a-z0-9_]*"
                    value={field.key}
                    onChange={(e) => update(i, { key: e.target.value })}
                    placeholder="grounded"
                  />
                </label>
                <label>
                  Label
                  <Input
                    required
                    value={field.label}
                    onChange={(e) => update(i, { label: e.target.value })}
                    placeholder="Grounded in evidence"
                  />
                </label>
              </div>
              <label>
                Field type
                <Select
                  value={field.field_type}
                  onChange={(e) =>
                    update(i, {
                      field_type: e.target.value as SchemaField["field_type"],
                      constraints: {},
                      options: [],
                    })
                  }
                >
                  {[
                    "boolean",
                    "single_select",
                    "multi_select",
                    "integer_rating",
                    "continuous_score",
                    "text",
                    "json",
                  ].map((type) => (
                    <option key={type} value={type}>
                      {type.replaceAll("_", " ")}
                    </option>
                  ))}
                </Select>
              </label>
              <label>
                Description
                <Input
                  value={field.description}
                  onChange={(e) => update(i, { description: e.target.value })}
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={(e) => update(i, { required: e.target.checked })}
                />
                Required field
              </label>
              {field.field_type.includes("select") && (
                <label>
                  Options, separated by commas
                  <Input
                    required
                    value={field.options.join(", ")}
                    onChange={(e) =>
                      update(i, {
                        options: e.target.value.split(",").map((x) => x.trim()),
                      })
                    }
                  />
                </label>
              )}
              {[
                "integer_rating",
                "continuous_score",
                "text",
                "multi_select",
              ].includes(field.field_type) && (
                <div className="form-two">
                  {["minimum", "maximum"].map((bound, n) => {
                    const key =
                      field.field_type === "text"
                        ? n
                          ? "max_length"
                          : "min_length"
                        : field.field_type === "multi_select"
                          ? n
                            ? "max_items"
                            : "min_items"
                          : bound;
                    return (
                      <label key={key}>
                        {key.replaceAll("_", " ")}
                        <Input
                          type="number"
                          step={
                            field.field_type === "continuous_score" ? "any" : 1
                          }
                          value={field.constraints[key] ?? ""}
                          onChange={(e) => {
                            const c = { ...field.constraints };
                            if (e.target.value === "") delete c[key];
                            else c[key] = Number(e.target.value);
                            update(i, { constraints: c });
                          }}
                        />
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            onClick={() => setFields([...fields, fresh()])}
          >
            <Plus size={14} />
            Add field
          </Button>
          {save.error && <ErrorState error={save.error} />}
          <Button disabled={!fields.length || save.isPending}>
            Publish schema version
          </Button>
        </fieldset>
      </form>
      {schemas.length > 1 && (
        <details className="padded">
          <summary>Previous immutable schemas ({schemas.length - 1})</summary>
          {schemas.slice(1).map((s) => (
            <div key={s.id}>
              <h3>
                {s.name} · v{s.version}
              </h3>
              <JsonViewer value={s.fields} />
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
function RulesEditor({
  projectId,
  initial,
  editable,
}: {
  projectId: string;
  initial: QualityRules;
  editable: boolean;
}) {
  const [rules, setRules] = useState(initial),
    { notify } = useApp(),
    qc = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      send(`/projects/${projectId}/quality-rules`, rules, "PUT"),
    onSuccess: () => {
      qc.invalidateQueries();
      notify("Quality requirements updated");
    },
  });
  const numbers: [keyof QualityRules, string, number, number, number][] = [
    ["required_annotations", "Independent annotations", 1, 20, 1],
    ["required_reviews", "Independent approvals", 1, 10, 1],
    ["minimum_agreement", "Minimum agreement (0–1)", 0, 1, 0.05],
    ["minimum_score", "Minimum human score (1–5)", 1, 5, 0.1],
    ["maximum_variance", "Maximum score variance (optional)", 0, 100, 0.1],
    [
      "minimum_gold_accuracy",
      "Minimum rolling gold accuracy (optional)",
      0,
      1,
      0.05,
    ],
    ["minimum_gold_attempts", "Minimum gold attempts", 1, 20, 1],
    ["gold_every", "Insert gold work every N completions", 1, 100, 1],
  ];
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Human quality gates</h2>
          <p>All configured gates must pass before dataset admission</p>
        </div>
        <ShieldCheck size={20} />
      </div>
      <form
        className="padded"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset disabled={!editable || save.isPending}>
          {numbers.map(([key, label, min, max, step]) => (
            <label key={key}>
              {label}
              <Input
                type="number"
                min={min}
                max={max}
                step={step}
                required={
                  !["maximum_variance", "minimum_gold_accuracy"].includes(key)
                }
                value={rules[key] === null ? "" : String(rules[key])}
                onChange={(e) =>
                  setRules({
                    ...rules,
                    [key]:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          ))}
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={rules.auto_escalate_disagreement}
              onChange={(e) =>
                setRules({
                  ...rules,
                  auto_escalate_disagreement: e.target.checked,
                })
              }
            />
            Escalate conflicting independent answers
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={rules.reveal_after_completion}
              onChange={(e) =>
                setRules({
                  ...rules,
                  reveal_after_completion: e.target.checked,
                })
              }
            />
            Reveal peer answers after all annotations complete
          </label>
          <p className="form-note">
            At least one independent human review is always required. Agreement
            measures consistency, not correctness. Stricter settings also apply
            to existing examples at finalization.
          </p>
          {save.error && <ErrorState error={save.error} />}
          <Button>Save quality gates</Button>
        </fieldset>
      </form>
    </section>
  );
}
