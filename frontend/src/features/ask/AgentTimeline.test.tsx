import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentTimeline } from "./AgentTimeline";
import type { AgentActionItem } from "../../types";

const mockSteps: AgentActionItem[] = [
  {
    step: 1,
    tool: "inspect_schema",
    arguments: { table: "users" },
    status: "ok",
    duration_ms: 12.3,
    summary: "Inspected users schema.",
  },
  {
    step: 2,
    tool: "execute_readonly_query",
    arguments: { sql: "SELECT * FROM orders WHERE bad_col = 1;" },
    status: "error",
    duration_ms: 4.5,
    summary: "Column 'bad_col' does not exist.",
  },
  {
    step: 3,
    tool: "validate_sql",
    arguments: { sql: "DROP TABLE users;" },
    status: "rejected",
    duration_ms: 1.1,
    summary: "Drop statement prohibited.",
  },
];

describe("AgentTimeline component", () => {
  it("renders steps, tool names, and status badges", () => {
    render(<AgentTimeline steps={mockSteps} />);

    expect(screen.getByText(/Agent Reasoning Timeline/i)).toBeInTheDocument();
    expect(screen.getByText("inspect_schema")).toBeInTheDocument();
    expect(screen.getByText("execute_readonly_query")).toBeInTheDocument();
    expect(screen.getByText("validate_sql")).toBeInTheDocument();

    // Verify badges
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText("rejected")).toBeInTheDocument();
  });

  it("expands step details and arguments when clicked", () => {
    render(<AgentTimeline steps={mockSteps} />);

    // Initially summary is hidden
    expect(screen.queryByText("Inspected users schema.")).toBeNull();

    // Click step 1 to expand
    fireEvent.click(screen.getByText("inspect_schema"));

    // Summary and arguments now visible
    expect(screen.getByText("Inspected users schema.")).toBeInTheDocument();
    expect(screen.getByText(/"table": "users"/)).toBeInTheDocument();
  });

  it("triggers reload run callback when reload button clicked", () => {
    const reloadFn = vi.fn();
    render(
      <AgentTimeline
        steps={mockSteps}
        runId="run-uuid-12345678"
        onReloadRun={reloadFn}
      />
    );

    const reloadBtn = screen.getByTitle(/Reload full audit log/i);
    expect(reloadBtn).toBeInTheDocument();
    fireEvent.click(reloadBtn);
    expect(reloadFn).toHaveBeenCalledWith("run-uuid-12345678");
  });
});
