import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  maybeSingle,
  select,
  eq,
  single,
  insert,
  update,
  order,
  from,
} = vi.hoisted(() => {
  const maybeSingle = vi.fn();
  let select: ReturnType<typeof vi.fn>;
  const eq = vi.fn(() => ({ maybeSingle, select }));
  const single = vi.fn();
  select = vi.fn((columns?: string) => {
    if (columns === "id") {
      return { eq };
    }
    return { single };
  });
  const insert = vi.fn(() => ({ select }));
  const update = vi.fn(() => ({ eq, select }));
  const order = vi.fn();
  const from = vi.fn((table: string) => {
    if (table === "position_entry_profiles") {
      return {
        select,
        insert,
        update,
      };
    }
    return {
      select: vi.fn(() => ({
        order,
      })),
    };
  });

  return {
    maybeSingle,
    select,
    eq,
    single,
    insert,
    update,
    order,
    from,
  };
});

vi.mock("../lib/supabase", () => ({
  supabase: {
    from,
  },
}));

import { savePositionEntryProfile } from "../lib/api";

describe("savePositionEntryProfile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    from.mockImplementation((table: string) => {
      if (table === "position_entry_profiles") {
        return {
          select,
          insert,
          update,
        };
      }
      return {
        select: vi.fn(() => ({
          order,
        })),
      };
    });
  });

  it("keeps position_id in the insert payload for new profiles", async () => {
    maybeSingle.mockResolvedValueOnce({ data: null, error: null });
    single.mockResolvedValueOnce({
      data: { id: "profile-1", position_id: "pos-1" },
      error: null,
    });

    await savePositionEntryProfile("pos-1", {
      thesis_summary: " Thesis ",
      why_bought: " Why ",
      key_risks: "",
      target_price: 123,
      target_price_currency: " usd ",
      expected_holding_period: "",
      confidence_level: "high",
      catalysts: " Catalyst ",
      invalidation_criteria: "",
    });

    expect(insert).toHaveBeenCalledWith({
      position_id: "pos-1",
      thesis_summary: "Thesis",
      why_bought: "Why",
      key_risks: null,
      target_price: 123,
      target_price_currency: "USD",
      expected_holding_period: null,
      confidence_level: "high",
      catalysts: "Catalyst",
      invalidation_criteria: null,
    });
  });

  it("does not send position_id in the update payload for existing profiles", async () => {
    maybeSingle.mockResolvedValueOnce({
      data: { id: "profile-1" },
      error: null,
    });
    single.mockResolvedValueOnce({
      data: { id: "profile-1", position_id: "pos-1" },
      error: null,
    });

    await savePositionEntryProfile("pos-1", {
      thesis_summary: " Thesis ",
      why_bought: " Updated thesis ",
      key_risks: " Risk ",
      target_price: 150,
      target_price_currency: " usd ",
      expected_holding_period: " 3 years ",
      confidence_level: "medium",
      catalysts: " Catalyst ",
      invalidation_criteria: " Invalidate ",
    });

    expect(update).toHaveBeenCalledWith({
      thesis_summary: "Thesis",
      why_bought: "Updated thesis",
      key_risks: "Risk",
      target_price: 150,
      target_price_currency: "USD",
      expected_holding_period: "3 years",
      confidence_level: "medium",
      catalysts: "Catalyst",
      invalidation_criteria: "Invalidate",
    });
    expect(update).not.toHaveBeenCalledWith(
      expect.objectContaining({
        position_id: "pos-1",
      }),
    );
  });
});
