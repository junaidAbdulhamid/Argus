import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Pagination, Tabs, ErrorState } from "./ui";
describe("navigation controls", () => {
  it("disables pagination at both boundaries", () => {
    const change = vi.fn();
    const { rerender } = render(
      <Pagination page={1} total={21} pageSize={20} onChange={change} />,
    );
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(change).toHaveBeenCalledWith(2);
    rerender(
      <Pagination page={2} total={21} pageSize={20} onChange={change} />,
    );
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByText("21–21 of 21 tasks")).toBeInTheDocument();
  });
  it("exposes tab selection and change actions", () => {
    const change = vi.fn();
    render(
      <Tabs
        tabs={["Trajectory", "Audit log"]}
        value="Trajectory"
        onChange={change}
      />,
    );
    expect(screen.getByRole("tab", { name: "Trajectory" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Audit log" }));
    expect(change).toHaveBeenCalledWith("Audit log");
  });
  it("offers retry without hiding the API error", () => {
    const retry = vi.fn();
    render(
      <ErrorState error={new Error("Assignment expired")} retry={retry} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Assignment expired");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
