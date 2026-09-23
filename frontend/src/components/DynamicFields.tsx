import type { AnnotationSchema } from "../quality-types";
import { Input, Select } from "./ui";
export function DynamicFields({
  schema,
  values,
  onChange,
}: {
  schema: AnnotationSchema;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}) {
  const set = (key: string, value: unknown) =>
    onChange({ ...values, [key]: value });
  return (
    <div className="dynamic-fields">
      <div className="schema-caption">
        {schema.name}
        <span>v{schema.version}</span>
      </div>
      {schema.fields.map((f) => {
        const value = values[f.key];
        const label = `${f.label}${f.required ? " *" : ""}`;
        return (
          <label key={f.key}>
            {label}
            {f.description && <small>{f.description}</small>}
            {f.field_type === "boolean" ? (
              <Select
                aria-label={f.label}
                required={f.required}
                value={value === undefined ? "" : String(value)}
                onChange={(e) =>
                  set(
                    f.key,
                    e.target.value === ""
                      ? undefined
                      : e.target.value === "true",
                  )
                }
              >
                <option value="">Select…</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </Select>
            ) : f.field_type === "single_select" ? (
              <Select
                aria-label={f.label}
                required={f.required}
                value={String(value ?? "")}
                onChange={(e) => set(f.key, e.target.value)}
              >
                <option value="">Select…</option>
                {f.options.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </Select>
            ) : f.field_type === "multi_select" ? (
              <div className="multi-options">
                {f.options.map((o) => (
                  <label key={o}>
                    <input
                      type="checkbox"
                      checked={Array.isArray(value) && value.includes(o)}
                      onChange={(e) =>
                        set(
                          f.key,
                          e.target.checked
                            ? [...(Array.isArray(value) ? value : []), o]
                            : (Array.isArray(value) ? value : []).filter(
                                (x) => x !== o,
                              ),
                        )
                      }
                    />
                    {o}
                  </label>
                ))}
              </div>
            ) : ["integer_rating", "continuous_score"].includes(
                f.field_type,
              ) ? (
              <Input
                aria-label={f.label}
                required={f.required}
                type="number"
                step={f.field_type === "integer_rating" ? 1 : "any"}
                min={f.constraints.minimum}
                max={f.constraints.maximum}
                value={typeof value === "number" ? value : ""}
                onChange={(e) =>
                  set(
                    f.key,
                    e.target.value === "" ? undefined : Number(e.target.value),
                  )
                }
              />
            ) : f.field_type === "json" ? (
              <JsonField
                label={f.label}
                value={value}
                required={f.required}
                onChange={(v) => set(f.key, v)}
              />
            ) : (
              <textarea
                aria-label={f.label}
                required={f.required}
                minLength={f.constraints.min_length}
                maxLength={f.constraints.max_length}
                value={String(value ?? "")}
                onChange={(e) => set(f.key, e.target.value)}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}
function JsonField({
  label,
  value,
  required,
  onChange,
}: {
  label: string;
  value: unknown;
  required: boolean;
  onChange: (v: unknown) => void;
}) {
  return (
    <textarea
      className="code-input"
      aria-label={label}
      required={required}
      defaultValue={value === undefined ? "" : JSON.stringify(value, null, 2)}
      onChange={(e) => {
        if (!e.target.value) {
          e.target.setCustomValidity(required ? "JSON is required" : "");
          onChange(undefined);
          return;
        }
        try {
          const parsed: unknown = JSON.parse(e.target.value);
          if (!parsed || typeof parsed !== "object") throw new Error();
          e.target.setCustomValidity("");
          onChange(parsed);
        } catch {
          e.target.setCustomValidity("Enter a valid JSON object or array");
          onChange(e.target.value);
        }
      }}
    />
  );
}
