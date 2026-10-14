import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HistoryPanel } from "./HistoryPanel";

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("HistoryPanel component", () => {
  it("renders history items and allows filtering by status", async () => {
    const selectSqlFn = vi.fn();
    renderWithClient(<HistoryPanel onSelectSql={selectSqlFn} />);

    await waitFor(() => {
      expect(screen.getByText("SELECT id, name FROM users LIMIT 10;")).toBeInTheDocument();
    });

    expect(screen.getByText("SELECT * FROM orders WHERE status = 'delivered';")).toBeInTheDocument();

    // Filter by rejected
    const rejectedTab = screen.getByRole("button", { name: "rejected" });
    fireEvent.click(rejectedTab);

    // Only rejected item remains visible
    expect(screen.getByText("SELECT * FROM orders WHERE status = 'delivered';")).toBeInTheDocument();
    expect(screen.queryByText("SELECT id, name FROM users LIMIT 10;")).toBeNull();
  });

  it("calls onSelectSql when Load to Editor button is clicked", async () => {
    const selectSqlFn = vi.fn();
    renderWithClient(<HistoryPanel onSelectSql={selectSqlFn} />);

    await waitFor(() => {
      expect(screen.getByText("SELECT id, name FROM users LIMIT 10;")).toBeInTheDocument();
    });

    const loadButtons = screen.getAllByRole("button", { name: /Load to Editor/i });
    fireEvent.click(loadButtons[0]);

    expect(selectSqlFn).toHaveBeenCalledWith("SELECT id, name FROM users LIMIT 10;");
  });
});

