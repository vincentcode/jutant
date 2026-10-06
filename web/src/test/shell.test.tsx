import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import type { Feature } from "../api/endpoints";
import { Composer } from "../chat/Composer";
import { HomeScreen, greeting } from "../home/HomeScreen";
import { IconRail } from "../shell/IconRail";
import { KnowledgePanel } from "../shell/KnowledgePanel";
import { SettingsPanel } from "../shell/SettingsPanel";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function serve(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

const FEATURES: Feature[] = [
  {
    id: "transaction_lookup",
    template: "record_lookup",
    title: "Transaction lookup",
    description: "d",
    group: "Look something up",
    examples: ["Why did transfer TX-0002 fail?"],
  },
  {
    id: "policy_qa",
    template: "document_qa",
    title: "Policy Q&A",
    description: "d",
    group: "Policies and documents",
    examples: [],
  },
  {
    id: "code_explainer",
    template: "document_qa",
    title: "Code explainer",
    description: "d",
    group: "Policies and documents",
    examples: [],
  },
];

describe("HomeScreen", () => {
  it("greets by name and starts a feature from a card", () => {
    serve([]);
    const onCard = vi.fn();
    const card = {
      title: "Investigate a transaction",
      description: "Transfers and activity.",
      feature_id: "transaction_lookup",
      icon: "landmark",
      label: "Payments",
    };
    render(
      <HomeScreen
        firstName="Ama"
        cards={[card]}
        onCard={onCard}
        composer={<div>box</div>}
      />,
      { wrapper },
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /^Good (morning|afternoon|evening), Ama$/,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Investigate a transaction/ }),
    );
    expect(onCard).toHaveBeenCalledWith(card);
    expect(
      screen.getByRole("heading", { name: "Recent conversations" }),
    ).toBeInTheDocument();
  });

  it("greets by the time of day", () => {
    expect(greeting(new Date(2026, 9, 6, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 9, 6, 14))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 9, 6, 20))).toBe("Good evening");
  });
});

describe("Composer quick actions", () => {
  const base = {
    busy: false,
    onSend: vi.fn(),
    onStop: vi.fn(),
    onAttach: vi.fn(),
    onDetach: vi.fn(),
  };

  it("picks a kind of help from a chip, and the rest from More", () => {
    const onSelect = vi.fn();
    const quick = [{ label: "Transaction", feature_id: "transaction_lookup" }];
    const { rerender } = render(
      <Composer
        {...base}
        features={FEATURES}
        quickActions={quick}
        selected={undefined}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByRole("button", { name: "Automatic" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Transaction" }));
    expect(onSelect).toHaveBeenLastCalledWith("transaction_lookup");

    rerender(
      <Composer
        {...base}
        features={FEATURES}
        quickActions={quick}
        selected="code_explainer"
        onSelect={onSelect}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Code explainer/ }),
    ).toHaveAttribute("aria-haspopup", "menu");
  });
});

describe("IconRail", () => {
  it("opens panels and starts a new conversation", () => {
    const onToggle = vi.fn();
    const onNew = vi.fn();
    render(<IconRail open="knowledge" onToggle={onToggle} onNew={onNew} />);
    expect(screen.getByRole("button", { name: "Knowledge" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(onToggle).toHaveBeenCalledWith("settings");
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(onNew).toHaveBeenCalled();
  });
});

describe("SettingsPanel", () => {
  it("shows the account read-only, and sets the theme", () => {
    const onTheme = vi.fn();
    const me = {
      id: "S0042",
      username: "ama",
      role: "customer_service",
      display_name: "Ama Mensah",
      attributes: { branch: "ACC-01" },
    };
    render(
      <SettingsPanel
        me={me}
        theme="auto"
        onTheme={onTheme}
        onSignOut={vi.fn()}
      />,
    );
    expect(screen.getByText("ACC-01")).toBeInTheDocument();
    expect(screen.getByText("customer service")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dark"));
    expect(onTheme).toHaveBeenCalledWith("dark");
  });
});

describe("KnowledgePanel", () => {
  it("lists documents by type and asks for a summary", async () => {
    serve([
      {
        id: "d1",
        title: "KYC Policy",
        doc_type: "policy",
        effective_date: null,
        indexed_at: "2026-10-01T10:00:00Z",
      },
      {
        id: "d2",
        title: "Circular 14/2026",
        doc_type: "circular",
        effective_date: null,
        indexed_at: "2026-10-01T10:00:00Z",
      },
    ]);
    const onSummarise = vi.fn();
    render(<KnowledgePanel onSummarise={onSummarise} />, { wrapper });
    expect(
      await screen.findByRole("region", { name: "Policies" }),
    ).toHaveTextContent("KYC Policy");
    expect(screen.getByRole("region", { name: "Circulars" })).toHaveTextContent(
      "Circular 14/2026",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Summarise Circular 14/2026" }),
    );
    await waitFor(() =>
      expect(onSummarise).toHaveBeenCalledWith(
        expect.objectContaining({ id: "d2" }),
      ),
    );
  });
});
