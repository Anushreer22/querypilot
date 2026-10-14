import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { OptimizerPanel } from "./OptimizerPanel";

describe("OptimizerPanel component", () => {
  it("runs fast plan analysis and displays findings and suggestions", async () => {
    render(<OptimizerPanel sql="SELECT id FROM orders WHERE created_at >= '2026-01-01';" />);

    const analyzeBtn = screen.getByRole("button", { name: /Analyze Plan/i });
    fireEvent.click(analyzeBtn);

    // Wait for findings and suggestions to load
    await waitFor(() => {
      expect(screen.getByText(/Detected Bottlenecks/i)).toBeInTheDocument();
    });

    expect(screen.getByText("seq_scan_large_table")).toBeInTheDocument();
    expect(screen.getByText("ix_orders_created_at")).toBeInTheDocument();
    // Default without benchmark is ESTIMATED
    expect(screen.getByText("ESTIMATED")).toBeInTheDocument();
  });

  it("handles 409 benchmark lock conflict gracefully", async () => {
    render(<OptimizerPanel sql="SELECT * FROM orders LOCKED;" />);

    const analyzeBtn = screen.getByRole("button", { name: /Analyze Plan/i });
    fireEvent.click(analyzeBtn);

    await waitFor(() => {
      expect(screen.getByText(/Benchmark Conflict/i)).toBeInTheDocument();
      expect(screen.getByText(/already running/i)).toBeInTheDocument();
    });
  });

  it("handles 503 benchmark database offline gracefully", async () => {
    render(<OptimizerPanel sql="SELECT * FROM orders OFFLINE;" />);

    const analyzeBtn = screen.getByRole("button", { name: /Analyze Plan/i });
    fireEvent.click(analyzeBtn);

    await waitFor(() => {
      expect(screen.getByText(/Service Unavailable/i)).toBeInTheDocument();
    });
  });
});
