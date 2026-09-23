import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DynamicFields } from "./DynamicFields";
import type { AnnotationSchema } from "../quality-types";
const schema: AnnotationSchema = {
  id: "s1",
  name: "Quality rubric",
  version: 2,
  fields: [
    {
      key: "grounded",
      label: "Grounded",
      field_type: "boolean",
      description: "Check source evidence",
      required: true,
      constraints: {},
      options: [],
    },
    {
      key: "rating",
      label: "Rating",
      field_type: "integer_rating",
      description: "",
      required: true,
      constraints: { minimum: 1, maximum: 5 },
      options: [],
    },
    {
      key: "issues",
      label: "Issues",
      field_type: "multi_select",
      description: "",
      required: false,
      constraints: {},
      options: ["citation", "tool"],
    },
    {
      key: "evidence",
      label: "Evidence",
      field_type: "json",
      description: "",
      required: true,
      constraints: {},
      options: [],
    },
  ],
};
function Harness() {
  const [values, setValues] = useState<Record<string, unknown>>({});
  return (
    <form>
      <DynamicFields schema={schema} values={values} onChange={setValues} />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </form>
  );
}
describe("versioned dynamic annotation fields", () => {
  it("preserves false booleans, numeric ratings, and independent option choices", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Grounded", { exact: true }), {
      target: { value: "false" },
    });
    fireEvent.change(screen.getByLabelText("Rating", { exact: true }), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByLabelText("citation"));
    expect(JSON.parse(screen.getByTestId("values").textContent!)).toEqual({
      grounded: false,
      rating: 4,
      issues: ["citation"],
    });
    expect(screen.getByText("v2")).toBeInTheDocument();
  });
  it("blocks invalid structured JSON and marks its changed value", () => {
    render(<Harness />);
    const field = screen.getByLabelText("Evidence", { exact: true });
    fireEvent.change(field, { target: { value: "not json" } });
    expect(field).toBeInvalid();
    expect(screen.getByTestId("values")).toHaveTextContent("not json");
    fireEvent.change(field, { target: { value: '{"source":3}' } });
    expect(field).toBeValid();
    expect(
      JSON.parse(screen.getByTestId("values").textContent!).evidence,
    ).toEqual({ source: 3 });
  });
});
