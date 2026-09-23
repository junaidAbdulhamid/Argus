import { test, expect } from "@playwright/test";
const password = process.env.SEED_PASSWORD || "Argus-demo-2026!";
async function login(
  page: import("@playwright/test").Page,
  email = "admin@argus.dev",
) {
  await page.goto("/");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Better agents start with better data.",
    }),
  ).toBeVisible();
}
test("Phase 2 seeded quality, review, datasets, lineage, and downloadable exports", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("link", { name: "Quality", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Confidence, with evidence." }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Riley Patel" })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/quality.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: "Human Review", exact: true }).click();
  await page.getByRole("link", { name: "EVAL-2113", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Independent annotations" }),
  ).toBeVisible();
  await expect(page.getByText("Riley Patel", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/review.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Evaluate quality gates" }).click();
  await expect(
    page.getByText("requires reviewer approval", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Datasets", exact: true }).click();
  await page
    .getByRole("link")
    .filter({
      has: page.getByRole("heading", { name: "argus-agent-reliability" }),
    })
    .click();
  await page.getByRole("link", { name: "v1", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Dataset version 1" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/dataset-version.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: "Trace provenance" }).first().click();
  await expect(
    page.getByRole("heading", { name: "Every example has a history." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Human review evidence" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/lineage.png",
    fullPage: true,
    animations: "disabled",
  });
  const auth = await (
      await request.post("/api/auth/login", {
        data: { email: "admin@argus.dev", password },
      })
    ).json(),
    headers = { Authorization: `Bearer ${auth.access_token}` };
  const jobs = await (await request.get("/api/exports", { headers })).json();
  expect(
    jobs.some(
      (j: { status: string; format: string }) =>
        j.status === "COMPLETED" && j.format === "dpo",
    ),
  ).toBe(true);
  const job = jobs.find((j: { status: string }) => j.status === "COMPLETED");
  const manifest = await (
    await request.get(`/api/exports/${job.id}/files/manifest`, { headers })
  ).json();
  expect(manifest.files.dataset.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(errors).toEqual([]);
});
test("schema, annotation, dataset finalization, and background export work end to end", async ({
  page,
  request,
}) => {
  const unique = Date.now(),
    email = `schema-admin-${unique}@example.com`;
  const registration = await (
      await request.post("/api/auth/register", {
        data: {
          email,
          password,
          full_name: "Schema Admin",
          organization_name: "Schema browser test",
        },
      })
    ).json(),
    headers = { Authorization: `Bearer ${registration.access_token}` };
  const project = await (
    await request.post("/api/projects", {
      headers,
      data: { name: "Schema browser project" },
    })
  ).json();
  try {
    await login(page, email);
    await page.goto(`/projects/${project.id}/quality`);
    await page.getByLabel("Key", { exact: true }).fill("grounded");
    await page.getByLabel("Label", { exact: true }).fill("Source verified");
    await page.getByRole("button", { name: "Publish schema version" }).click();
    await expect(page.getByRole("status")).toContainText(
      "New schema version published",
    );
    const task = await (
      await request.post(`/api/projects/${project.id}/tasks`, {
        headers,
        data: { task_type: "research", external_id: "SCHEMA-01" },
      })
    ).json();
    await request.post(`/api/tasks/${task.id}/runs`, {
      headers,
      data: {
        model_name: "agent",
        steps: [
          {
            sequence_number: 0,
            step_type: "user_message",
            content: "Verify evidence",
          },
          {
            sequence_number: 1,
            step_type: "final_answer",
            content: "Verified.",
          },
        ],
      },
    });
    await request.post(`/api/tasks/${task.id}/queue`, { headers });
    await page
      .getByRole("link", { name: "Annotation Queue", exact: true })
      .click();
    await page.getByRole("button", { name: "Claim next task" }).click();
    await expect(
      page.getByLabel("Source verified", { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Source verified", { exact: true })
      .selectOption("true");
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(
      page.getByRole("button", { name: "Complete assignment" }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "Complete assignment" }).click();
    await expect(page.getByRole("status")).toContainText("independent review");
    const reviewerEmail = `schema-reviewer-${unique}@example.com`;
    expect(
      (
        await request.post("/api/users", {
          headers,
          data: {
            email: reviewerEmail,
            password,
            full_name: "Independent reviewer",
            role: "REVIEWER",
          },
        })
      ).status(),
    ).toBe(201);
    const reviewer = await (
      await request.post("/api/auth/login", {
        data: { email: reviewerEmail, password },
      })
    ).json();
    expect(
      (
        await request.post(`/api/tasks/${task.id}/reviews`, {
          headers: { Authorization: `Bearer ${reviewer.access_token}` },
          data: {
            decision: "APPROVED",
            comments: "Checked source evidence and the independent annotation.",
          },
        })
      ).status(),
    ).toBe(201);
    await page.getByRole("link", { name: "Datasets", exact: true }).click();
    await page.getByRole("button", { name: "New dataset" }).click();
    await page
      .getByLabel("Name", { exact: true })
      .fill("Browser verified dataset");
    await page
      .getByRole("button", { name: "Create & select examples" })
      .click();
    await page
      .getByRole("button", { name: "Prepare approved examples" })
      .click();
    await page.getByLabel("Select SCHEMA-01", { exact: true }).check();
    await page.getByRole("button", { name: "Create draft version" }).click();
    await page.getByRole("button", { name: "Finalize version" }).click();
    await expect(
      page.getByRole("heading", { name: "Immutable version metadata" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Queue export" }).click();
    await expect(
      page.getByRole("button", { name: "dataset", exact: true }),
    ).toBeVisible({ timeout: 20000 });
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "dataset", exact: true }).click();
    expect((await download).suggestedFilename()).toBe("dataset.jsonl");
    // Finalized provenance intentionally remains in this isolated test organization.
    expect(
      (
        await request.delete(`/api/projects/${project.id}`, { headers })
      ).status(),
    ).toBe(409);
  } finally {
    await request.delete(`/api/projects/${project.id}`, { headers });
  }
});
