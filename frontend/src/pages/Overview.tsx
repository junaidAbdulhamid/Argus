import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Layers3,
  ListTodo,
  ScanEye,
  ShieldCheck,
  ArrowRight,
  Activity as ActivityIcon,
} from "lucide-react";
import { api, date } from "../api";
import type { Overview as OverviewData } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  MetricCard,
  Skeleton,
  ErrorState,
  Badge,
  SectionLink,
} from "../components/ui";
import { Activity } from "../components/Trace";
export default function Overview() {
  const { project } = useApp();
  const q = useQuery({
    queryKey: ["overview", project],
    queryFn: () =>
      api<OverviewData>(`/overview${project ? `?project_id=${project}` : ""}`),
    refetchInterval: 30000,
  });
  if (q.isPending) return <Skeleton />;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data,
    c = d.counts,
    max = Math.max(1, ...d.throughput.map((x) => x.count));
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE OVERVIEW"
        title="Better agents start with better data."
        description="Your human feedback loop, in focus."
        action={
          <Link className="button secondary" to="/queue">
            Open annotation queue
            <ArrowUpRight size={16} />
          </Link>
        }
      />
      <div className="live-line">
        <span className="live-dot" />
        Live workspace data<span>Updated every 30 seconds</span>
      </div>
      <div className="metrics">
        <MetricCard
          label="Total tasks"
          value={c.total || 0}
          caption="Across selected projects"
          icon={<Layers3 size={17} />}
        />
        <MetricCard
          label="In the queue"
          value={c.QUEUED || 0}
          caption="Ready for human annotation"
          icon={<ListTodo size={17} />}
        />
        <MetricCard
          label="Awaiting review"
          value={c.PENDING_REVIEW || 0}
          caption="Human approval required"
          icon={<ScanEye size={17} />}
        />
        <MetricCard
          label="Approved"
          value={c.APPROVED || 0}
          caption="Eligible for future dataset exports"
          icon={<ShieldCheck size={17} />}
        />
      </div>
      <div className="dashboard-grid">
        <section className="panel throughput">
          <div className="section-heading">
            <div>
              <h2>Annotation throughput</h2>
              <p>Completed assignments over the last 7 days</p>
            </div>
            <Badge>Last 7 days</Badge>
          </div>
          <div className="chart-total">
            {d.completed_this_week}
            <small>completed annotations</small>
          </div>
          <div className="bar-chart" aria-label="Daily completed annotations">
            {d.throughput.map((day) => (
              <div className="bar-column" key={day.date}>
                <span>{day.count}</span>
                <div className="bar-track">
                  <div
                    className="bar"
                    style={{
                      height: `${Math.max(day.count ? 4 : 0, (day.count / max) * 100)}%`,
                    }}
                    title={`${day.date}: ${day.count}`}
                  />
                </div>
                <small>{date(`${day.date}T12:00:00`)}</small>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Task distribution</h2>
              <p>Every stage of your feedback loop</p>
            </div>
            <ActivityIcon size={17} />
          </div>
          <div className="distribution-bar">
            {[
              "INGESTED",
              "QUEUED",
              "ASSIGNED",
              "PENDING_REVIEW",
              "APPROVED",
              "REJECTED",
            ].map((s) => (
              <div
                className={s.toLowerCase()}
                key={s}
                style={{ flex: c[s] || 0 }}
                title={`${s}: ${c[s] || 0}`}
              />
            ))}
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
            ].map((s) => (
              <div key={s}>
                <Badge status={s} />
                <span>
                  {c[s] || 0}
                  <small>
                    {c.total ? Math.round(((c[s] || 0) / c.total) * 100) : 0}%
                  </small>
                </span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel recent">
          <div className="section-heading">
            <div>
              <h2>Recent activity</h2>
              <p>A trail of every meaningful decision</p>
            </div>
            <Link to="/tasks">
              <SectionLink>Explore tasks</SectionLink>
            </Link>
          </div>
          <Activity events={d.activity.slice(0, 6)} compact />
        </section>
        <section className="panel queue-health">
          <div className="section-heading">
            <h2>Queue health</h2>
            <span
              className={`health-pill ${d.queue.redis === "healthy" ? "" : "warning"}`}
            >
              {d.queue.redis === "healthy" ? "Operational" : "Redis degraded"}
            </span>
          </div>
          <div className="queue-number">
            {d.queue.length}
            <span>tasks ready to claim</span>
          </div>
          <div className="health-row">
            <span>Source of truth</span>
            <strong>PostgreSQL</strong>
          </div>
          <div className="health-row">
            <span>Queue accelerator</span>
            <strong>
              {d.queue.redis === "healthy" ? "Connected" : "Database fallback"}
            </strong>
          </div>
          <div className="health-row">
            <span>Oldest queued task</span>
            <strong>
              {d.queue.oldest_queued_at
                ? date(d.queue.oldest_queued_at)
                : "Queue is clear"}
            </strong>
          </div>
          <div className="queue-callout">
            <ShieldCheck size={19} />
            <p>
              Human reviewed. Always.
              <small>
                Annotations require independent approval before becoming
                training data.
              </small>
            </p>
          </div>
          <Link className="text-link" to="/queue">
            Go to annotation workspace
            <ArrowRight size={15} />
          </Link>
        </section>
      </div>
    </>
  );
}
