import { vi, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppContext } from "../context";
import Queue from "./Queue";
const fetchMock = vi.fn();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});
it("requires a saved draft and submits completion for independent review", async () => {
  const calls: string[] = [];
  fetchMock.mockImplementation(async (path: string, options?: RequestInit) => {
    calls.push(`${options?.method || "GET"} ${path}`);
    let result: unknown = {};
    if (path === "/api/annotation/assignments")
      result = [
        {
          id: "assignment-1",
          task_id: "task-1",
          annotator_id: "u1",
          status: "STARTED",
          assigned_at: "2026-09-19T12:00:00Z",
        },
      ];
    if (path === "/api/annotation/assignments/assignment-1")
      result = {
        id: "assignment-1",
        task_id: "task-1",
        status: "STARTED",
        annotation: null,
      };
    if (path === "/api/tasks/task-1")
      result = { id: "task-1", external_id: "ARG-1001" };
    if (path.endsWith("/trajectory")) result = [];
    if (path === "/api/overview") result = { counts: {}, queue: { length: 1 } };
    if (
      path.endsWith("/annotations") ||
      path === "/api/annotations/annotation-1"
    )
      result = { id: "annotation-1" };
    return { ok: true, status: 200, json: async () => result };
  });
  const notify = vi.fn(),
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppContext.Provider
          value={{
            user: {
              id: "u1",
              full_name: "Maya",
              role: "ANNOTATOR",
              email: "maya@example.com",
              organization_id: "o1",
            },
            project: "",
            setProject: vi.fn(),
            notify,
            logout: vi.fn(),
          }}
        >
          <Queue />
        </AppContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const complete = await screen.findByRole("button", {
    name: "Complete assignment",
  });
  expect(complete).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/Structured fields/), {
    target: { value: "invalid json" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  expect(
    await screen.findByText("Structured fields must contain valid JSON"),
  ).toBeInTheDocument();
  expect(calls.some((c) => c.endsWith("/annotations"))).toBe(false);
  fireEvent.change(screen.getByLabelText(/Structured fields/), {
    target: { value: '{"grounded":true}' },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(complete).toBeEnabled());
  fireEvent.change(screen.getByLabelText("Written feedback"), {
    target: { value: "Accurate answer" },
  });
  expect(complete).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Update draft" }));
  await waitFor(() => expect(complete).toBeEnabled());
  fireEvent.click(complete);
  await waitFor(() =>
    expect(calls).toContain("POST /api/assignments/assignment-1/complete"),
  );
  expect(calls).not.toContain("POST /api/tasks/task-1/review");
});
