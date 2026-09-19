import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, SlidersHorizontal, ArrowUpDown } from "lucide-react";
import { api, date } from "../api";
import type { TaskPage } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  Input,
  Select,
  Table,
  Badge,
  Pagination,
  Skeleton,
  ErrorState,
  EmptyState,
} from "../components/ui";
export default function Tasks({
  projectId,
  embedded = false,
}: {
  projectId?: string;
  embedded?: boolean;
}) {
  const { project } = useApp(),
    selected = projectId || project;
  const [page, setPage] = useState(1),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [priority, setPriority] = useState(""),
    [sort, setSort] = useState("created_at"),
    [direction, setDirection] = useState("desc");
  const params = new URLSearchParams({
    page: String(page),
    page_size: "15",
    sort,
    direction,
    ...(selected ? { project_id: selected } : {}),
    ...(search ? { search } : {}),
    ...(status ? { status } : {}),
    ...(priority ? { priority } : {}),
  });
  const q = useQuery({
    queryKey: ["tasks", params.toString()],
    queryFn: () => api<TaskPage>(`/tasks?${params}`),
  });
  const change = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };
  return (
    <>
      {!embedded && (
        <PageHeading
          eyebrow="DATA OPERATIONS"
          title="Task explorer"
          description="Inspect agent behavior, track ownership, and follow every task to approval."
        />
      )}
      <section className="panel task-panel">
        <div className="table-toolbar">
          <div className="search-input">
            <Search size={16} />
            <Input
              placeholder="Search task ID, external ID, or type…"
              aria-label="Search tasks"
              value={search}
              onChange={(e) => change(setSearch)(e.target.value)}
            />
          </div>
          <div className="filters">
            <SlidersHorizontal size={15} />
            <Select
              aria-label="Filter status"
              value={status}
              onChange={(e) => change(setStatus)(e.target.value)}
            >
              <option value="">All statuses</option>
              {[
                "INGESTED",
                "QUEUED",
                "ASSIGNED",
                "ANNOTATED",
                "PENDING_REVIEW",
                "APPROVED",
                "REJECTED",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
            <Input
              type="number"
              min="0"
              max="100"
              placeholder="Priority"
              aria-label="Filter priority"
              value={priority}
              onChange={(e) => change(setPriority)(e.target.value)}
            />
            <Select
              aria-label="Sort tasks"
              value={sort}
              onChange={(e) => change(setSort)(e.target.value)}
            >
              <option value="created_at">Created date</option>
              <option value="priority">Priority</option>
              <option value="status">Status</option>
            </Select>
            <button
              className="icon-button"
              aria-label="Toggle sort direction"
              onClick={() =>
                change(setDirection)(direction === "desc" ? "asc" : "desc")
              }
            >
              <ArrowUpDown size={16} />
            </button>
          </div>
        </div>
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : !q.data.items.length ? (
          <EmptyState
            title="No matching tasks"
            description="Try another filter, or ingest your first task through the API."
          />
        ) : (
          <Table
            headers={[
              "Task",
              "Type",
              "Status",
              "Priority",
              "Annotator",
              "Created",
            ]}
          >
            {q.data.items.map((t) => (
              <tr key={t.id}>
                <td>
                  <Link className="task-link" to={`/tasks/${t.id}`}>
                    <span className="task-symbol">⌘</span>
                    <span>
                      {t.external_id || t.id.slice(0, 8)}
                      <small>{t.id.slice(0, 8)}</small>
                    </span>
                  </Link>
                </td>
                <td>
                  <span className="type-label">
                    {t.task_type.replaceAll("_", " ")}
                  </span>
                </td>
                <td>
                  <Badge status={t.status} />
                </td>
                <td>
                  <span
                    className={`priority p${t.priority >= 70 ? "high" : "normal"}`}
                  >
                    ▥ <span>{t.priority}</span>
                  </span>
                </td>
                <td>
                  {t.annotator || <span className="muted">Unassigned</span>}
                </td>
                <td className="muted">{date(t.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
        {q.data && (
          <Pagination
            page={page}
            total={q.data.total}
            pageSize={15}
            onChange={setPage}
          />
        )}
      </section>
    </>
  );
}
