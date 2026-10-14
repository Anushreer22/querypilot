import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResultsTable } from "./ResultsTable";

describe("ResultsTable component", () => {
  it("renders table with columns and formatted cell values", () => {
    render(
      <ResultsTable
        columns={["id", "name", "price", "is_active", "created_at", "optional_field"]}
        rows={[
          {
            id: 42,
            name: "Mechanical Keyboard",
            price: 129.99,
            is_active: true,
            created_at: "2026-01-15T10:30:00Z",
            optional_field: null,
          },
        ]}
        rowCount={1}
        durationMs={15.4}
      />
    );

    // Verify headers
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("price")).toBeInTheDocument();

    // Verify formatted values
    expect(screen.getByText("Mechanical Keyboard")).toBeInTheDocument();
    expect(screen.getByText("129.99")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText("NULL")).toBeInTheDocument();
    expect(screen.getByText("15.40 ms")).toBeInTheDocument();
  });

  it("CRITICAL SECURITY TEST: renders malicious HTML strings strictly as raw text without executing", () => {
    const maliciousPayload = '<img src=x onerror=alert("pwned")>';

    const { container } = render(
      <ResultsTable
        columns={["id", "user_input"]}
        rows={[{ id: 1, user_input: maliciousPayload }]}
      />
    );

    // 1. Literal text must be present as text content
    expect(screen.getByText(maliciousPayload)).toBeInTheDocument();

    // 2. An <img> HTML element must NOT exist in the DOM
    const imgElement = container.querySelector("img");
    expect(imgElement).toBeNull();
  });

  it("renders truncation alert banner when truncated is true", () => {
    render(
      <ResultsTable
        columns={["id"]}
        rows={[{ id: 1 }]}
        truncated={true}
        rowCount={1000}
      />
    );

    expect(screen.getByText(/truncated at/i)).toBeInTheDocument();
    expect(screen.getByText(/1,000 rows/i)).toBeInTheDocument();
  });

  it("renders LIMIT injected badge when limitInjected is true", () => {
    render(
      <ResultsTable
        columns={["id"]}
        rows={[{ id: 1 }]}
        limitInjected={true}
      />
    );

    expect(screen.getByText(/LIMIT injected/i)).toBeInTheDocument();
  });
});
