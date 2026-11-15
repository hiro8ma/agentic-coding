import { describe, expect, it } from "vitest";
import { canReturn, returnShippingFee } from "./returns";

describe("返品", () => {
  it("RET-1 受け取りから30日目までは返品できる", () => {
    expect(canReturn({ daysSinceDelivery: 30, onSale: false })).toBe(true);
  });

  it("RET-3 返品の送料は店が持つ", () => {
    expect(returnShippingFee()).toBe(0);
  });
});
