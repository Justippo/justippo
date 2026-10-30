import { describe, it, expect } from "vitest";
import { parseEurostatResponse, type EurostatResponse } from "@/lib/eurostat";

function makeMultiGeoResponse(): EurostatResponse {
  return {
    id: ["freq", "citizen", "sex", "age", "unit", "geo", "time"],
    size: [1, 1, 1, 1, 1, 3, 1],
    dimension: {
      freq: { category: { index: { A: 0 }, label: { A: "Annual" } } },
      citizen: {
        category: { index: { FOR_STLS: 0 }, label: { FOR_STLS: "Foreign citizens and stateless" } },
      },
      sex: { category: { index: { T: 0 }, label: { T: "Total" } } },
      age: { category: { index: { TOTAL: 0 }, label: { TOTAL: "Total" } } },
      unit: { category: { index: { NR: 0 }, label: { NR: "Number" } } },
      geo: {
        category: {
          index: { DE: 0, FR: 1, EU27_2020: 2 },
          label: { DE: "Germany", FR: "France", EU27_2020: "EU27 (2020)" },
        },
      },
      time: { category: { index: { 2023: 0 }, label: { 2023: "2023" } } },
    },
    value: { "0": 12108988, "1": 5226942, "2": 43006349 },
  };
}

function makeSingleGeoResponse(): EurostatResponse {
  return {
    id: ["freq", "citizen", "sex", "age", "unit", "geo", "time"],
    size: [1, 1, 1, 1, 1, 1, 1],
    dimension: {
      freq: { category: { index: { A: 0 }, label: { A: "Annual" } } },
      citizen: {
        category: { index: { FOR_STLS: 0 }, label: { FOR_STLS: "Foreign citizens and stateless" } },
      },
      sex: { category: { index: { T: 0 }, label: { T: "Total" } } },
      age: { category: { index: { TOTAL: 0 }, label: { TOTAL: "Total" } } },
      unit: { category: { index: { NR: 0 }, label: { NR: "Number" } } },
      geo: {
        category: {
          index: { DE: 0 },
          label: { DE: "Germany" },
        },
      },
      time: { category: { index: { 2023: 0 }, label: { 2023: "2023" } } },
    },
    value: { "0": 12108988 },
  };
}

function makeResponseWithNulls(): EurostatResponse {
  return {
    id: ["freq", "citizen", "sex", "age", "unit", "geo", "time"],
    size: [1, 1, 1, 1, 1, 3, 1],
    dimension: {
      freq: { category: { index: { A: 0 }, label: { A: "Annual" } } },
      citizen: {
        category: { index: { FOR_STLS: 0 }, label: { FOR_STLS: "Foreign citizens and stateless" } },
      },
      sex: { category: { index: { T: 0 }, label: { T: "Total" } } },
      age: { category: { index: { TOTAL: 0 }, label: { TOTAL: "Total" } } },
      unit: { category: { index: { NR: 0 }, label: { NR: "Number" } } },
      geo: {
        category: {
          index: { DE: 0, FR: 1, EU27_2020: 2 },
          label: { DE: "Germany", FR: "France", EU27_2020: "EU27 (2020)" },
        },
      },
      time: { category: { index: { 2023: 0 }, label: { 2023: "2023" } } },
    },
    value: { "0": 12108988, "1": null, "2": 43006349 },
  };
}

describe("parseEurostatResponse", () => {
  it("correctly maps multi-geo response to country stats", () => {
    const result = parseEurostatResponse(makeMultiGeoResponse());

    expect(result.total).toBe(43006349);
    expect(result.countries).toHaveLength(2);
    expect(result.countries[0].code).toBe("DE");
    expect(result.countries[0].count).toBe(12108988);
    expect(result.countries[1].code).toBe("FR");
    expect(result.countries[1].count).toBe(5226942);
    expect(result.year).toBe("2023");
  });

  it("handles single-geo response correctly", () => {
    const result = parseEurostatResponse(makeSingleGeoResponse());

    expect(result.countries).toHaveLength(1);
    expect(result.countries[0].code).toBe("DE");
    expect(result.countries[0].count).toBe(12108988);
    expect(result.total).toBe(0); // No EU27_2020 in single-geo
  });

  it("handles null values gracefully (no crash, no NaN)", () => {
    const result = parseEurostatResponse(makeResponseWithNulls());

    expect(result.countries).toHaveLength(1); // FR is null, skipped
    expect(result.countries[0].code).toBe("DE");
    expect(result.countries[0].count).toBe(12108988);
    expect(result.total).toBe(43006349);
  });

  it("returns empty result when no geo dimension", () => {
    const data = {
      id: ["freq"],
      size: [1],
      dimension: { freq: { category: { index: { A: 0 }, label: { A: "Annual" } } } },
      value: { "0": 100 },
    } as unknown as EurostatResponse;

    const result = parseEurostatResponse(data);
    expect(result.total).toBe(0);
    expect(result.countries).toHaveLength(0);
  });
});
