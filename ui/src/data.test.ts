import { expect, test } from "vitest";

test("the contract file is importable", async () => {
  expect(await import("./types")).toBeDefined();
});
