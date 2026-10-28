import assert from "node:assert/strict";
import { test } from "node:test";

import { createOrder, Inventory } from "../src/index.ts";

test("both modules validate SKUs the same way, as SPEC.md says", () => {
  const inv = new Inventory();
  for (const bad of ["bolt-1", "B1", "1BOLT", "BOLT_1", "ABCDEFGHIJKLM"]) {
    assert.throws(() => inv.add(bad, 1), new RegExp(`invalid SKU: ${bad}`));
    assert.throws(
      () => createOrder([{ sku: bad, qty: 1, priceCents: 1, currency: "EUR" }], "EUR", inv, { EUR: 1 }),
      new RegExp(`invalid SKU: ${bad}`),
    );
  }
  inv.add("BOLT-1", 2);
  inv.add("ABCDEFGHIJKL", 1);
  assert.equal(inv.available("BOLT-1"), 2);
});
