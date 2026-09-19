import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  UserRound,
  Wrench,
  CheckCheck,
  Terminal,
  Clock3,
} from "lucide-react";
import { api, time, human } from "../api";
import type { Run, Audit } from "../types";
import { Skeleton, ErrorState, EmptyState, JsonViewer } from "./ui";
export function Trace({ taskId }: { taskId: string }) {
  const q = useQuery({
    queryKey: ["trajectory", taskId],
    queryFn: () => api<Run[]>(`/tasks/${taskId}/trajectory`),
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data.length)
    return (
      <EmptyState
        title="No trajectory yet"
        description="Ingest an agent run to inspect its execution trace."
      />
    );
  return (
    <div className="runs">
      {q.data.map((run) => (
        <section key={run.id}>
          <div className="run-heading">
            <span>
              <Bot size={16} />
              {run.model_name}
              <small>{run.model_version}</small>
            </span>
            <small>
              <Clock3 size={13} />
              {time(run.started_at)}
            </small>
          </div>
          <div className="timeline">
            {run.steps.map((step) => {
              const tool =
                step.step_type === "tool_call" ||
                step.step_type === "tool_result";
              const Icon =
                step.step_type === "user_message"
                  ? UserRound
                  : tool
                    ? Wrench
                    : step.step_type === "final_answer"
                      ? CheckCheck
                      : step.step_type === "observation"
                        ? Terminal
                        : Bot;
              return (
                <article
                  className={`trace-step ${step.step_type}`}
                  key={step.id}
                >
                  <div className="trace-icon">
                    <Icon size={16} />
                  </div>
                  <div className="step-body">
                    <header>
                      <strong>{human(step.step_type)}</strong>
                      <span>{step.tool_name}</span>
                      <small>
                        #{String(step.sequence_number).padStart(2, "0")}
                      </small>
                    </header>
                    {step.content && <p>{step.content}</p>}
                    {tool && (
                      <details open={step.step_type === "tool_call"}>
                        <summary>
                          {step.step_type === "tool_call"
                            ? "Arguments & response"
                            : "Tool output"}
                        </summary>
                        {step.tool_input && (
                          <JsonViewer value={step.tool_input} />
                        )}{" "}
                        {step.tool_output && (
                          <JsonViewer value={step.tool_output} />
                        )}
                      </details>
                    )}
                    {Object.keys(step.metadata).length > 0 && (
                      <details>
                        <summary>Execution metadata</summary>
                        <JsonViewer value={step.metadata} />
                      </details>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
export function Activity({
  events,
  compact = false,
}: {
  events: Audit[];
  compact?: boolean;
}) {
  return events.length ? (
    <div className={`activity ${compact ? "compact" : ""}`}>
      {events.map((e) => (
        <div className="activity-row" key={e.id}>
          <span className="activity-dot" />
          <div>
            <strong>{human(e.event_type)}</strong>
            <p>
              {e.actor}
              {e.task_id && (
                <>
                  {" "}
                  <span>·</span> <code>{e.task_id.slice(0, 8)}</code>
                </>
              )}
            </p>
            {!compact && Object.keys(e.payload).length > 0 && (
              <details>
                <summary>Event details</summary>
                <JsonViewer value={e.payload} />
              </details>
            )}
          </div>
          <time>{time(e.timestamp)}</time>
        </div>
      ))}
    </div>
  ) : (
    <EmptyState
      title="No activity yet"
      description="Project and task events will appear here as your team works."
    />
  );
}
