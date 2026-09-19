import { test, expect } from "@playwright/test";
const password = process.env.SEED_PASSWORD || "Argus-demo-2026!";
test("seeded dashboard, task explorer, trace, and responsive navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@argus.dev");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Better agents start with better data.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Operational", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/overview.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: "Tasks", exact: true }).click();
  await page.getByLabel("Filter status").selectOption("QUEUED");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.locator("tbody .task-link").first().click();
  await expect(page.getByRole("tab", { name: "Trajectory" })).toBeVisible();
  await expect(page.getByText("final answer", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/trajectory.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("tab", { name: "Audit log" }).click();
  await expect(page.getByText("task created", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Better agents start with better data.",
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("human annotation completion requires an independent review", async ({
  page,
  request,
}) => {
  const unique = Date.now(),
    adminEmail = `browser-admin-${unique}@example.com`,
    annotatorEmail = `browser-annotator-${unique}@example.com`,
    reviewerEmail = `browser-reviewer-${unique}@example.com`;
  const register = await request.post("/api/auth/register", {
    data: {
      email: adminEmail,
      password,
      full_name: "Browser Admin",
      organization_name: "Browser verification",
    },
  });
  expect(register.status()).toBe(201);
  const auth = await register.json(),
    headers = { Authorization: `Bearer ${auth.access_token}` };
  const project = await (
    await request.post("/api/projects", {
      headers,
      data: {
        name: "Browser workflow",
        description: "Isolated end-to-end verification",
      },
    })
  ).json();
  let taskId = "";
  try {
    for (const [email, role] of [
      [annotatorEmail, "ANNOTATOR"],
      [reviewerEmail, "REVIEWER"],
    ])
      expect(
        (
          await request.post("/api/users", {
            headers,
            data: { email, password, full_name: role, role },
          })
        ).status(),
      ).toBe(201);
    const task = await (
      await request.post(`/api/projects/${project.id}/tasks`, {
        headers,
        data: {
          external_id: `browser-${unique}`,
          task_type: "research",
          priority: 80,
          input_payload: { prompt: "Verify the sample evidence" },
        },
      })
    ).json();
    taskId = task.id;
    expect(
      (
        await request.post(`/api/tasks/${task.id}/runs`, {
          headers,
          data: {
            model_name: "browser-agent",
            steps: [
              {
                sequence_number: 0,
                step_type: "user_message",
                content: "Verify the sample evidence",
              },
              {
                sequence_number: 1,
                step_type: "tool_call",
                tool_name: "lookup",
                tool_input: { id: 42 },
              },
              {
                sequence_number: 2,
                step_type: "tool_result",
                tool_name: "lookup",
                tool_output: { verified: true },
              },
              {
                sequence_number: 3,
                step_type: "final_answer",
                content: "The evidence is verified.",
              },
            ],
          },
        })
      ).status(),
    ).toBe(201);
    expect(
      (await request.post(`/api/tasks/${task.id}/queue`, { headers })).ok(),
    ).toBe(true);
    await page.goto("/");
    await page.getByLabel("Email address").fill(annotatorEmail);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page
      .getByRole("link", { name: "Annotation Queue", exact: true })
      .click();
    await page.getByRole("button", { name: "Claim next task" }).click();
    await expect(
      page.getByRole("heading", { name: "Your evaluation" }),
    ).toBeVisible();
    await expect(page.getByText("0 in queue", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Complete assignment" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Score 5", exact: true }).click();
    await page
      .getByLabel("Written feedback")
      .fill("The response is grounded in the tool result.");
    await page.getByLabel(/Structured fields/).fill('{"grounded":true}');
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(
      page.getByRole("button", { name: "Complete assignment" }),
    ).toBeEnabled();
    await page.screenshot({
      path: "../docs/screenshots/annotation.png",
      fullPage: true,
      animations: "disabled",
    });
    await page.getByRole("button", { name: "Complete assignment" }).click();
    await expect(page.getByRole("status")).toContainText("independent review");
    expect(
      (await (await request.get(`/api/tasks/${task.id}`, { headers })).json())
        .status,
    ).toBe("PENDING_REVIEW");
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByLabel("Email address").fill(reviewerEmail);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", {
        name: "Better agents start with better data.",
      }),
    ).toBeVisible();
    await page.goto(`/tasks/${taskId}`);
    await page.getByRole("tab", { name: "Annotations" }).click();
    await expect(
      page.getByText("The response is grounded in the tool result."),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Review task", exact: true })
      .click();
    await page
      .getByLabel("Review rationale")
      .fill("Independently verified the evidence and annotation.");
    await page.getByRole("button", { name: "Submit review" }).click();
    await expect(page.getByRole("status")).toContainText("Review recorded");
    expect(
      (await (await request.get(`/api/tasks/${taskId}`, { headers })).json())
        .status,
    ).toBe("APPROVED");
  } finally {
    await request.delete(`/api/projects/${project.id}`, { headers });
  }
});
