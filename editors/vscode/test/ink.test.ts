// A filled button's words: the theme's own ink where it reads on the theme's button, else white or near-black.
import assert from "node:assert/strict";
import { test } from "node:test";
import { contrast, inkFor } from "../src/ink.ts";

const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];

test("Cursor Dark's near-black on its mid blue turns white; themes whose ink reads keep it", () => {
  assert.ok(contrast(hex("#1372da"), hex("#191919")) < 4.5, "Cursor Dark's own ink is below 4.5:1");
  assert.equal(inkFor(hex("#1372da"), hex("#191919")), "rgb(255, 255, 255)");
  assert.equal(inkFor(hex("#0e639c"), hex("#ffffff")), null, "Default Dark+");
  assert.equal(inkFor(hex("#88c0d0"), hex("#191c22")), null, "Midnight's pale button keeps its dark ink");
  assert.equal(inkFor(hex("#005fb8"), hex("#ffffff")), null, "Light Modern");
});

test("a pale button with white ink takes near-black; Cursor Light's white on its blue stays", () => {
  assert.equal(inkFor(hex("#9cdcfe"), hex("#ffffff")), "rgb(20, 20, 20)");
  assert.equal(inkFor(hex("#1680f3"), hex("#ffffff")), null, "3.9:1 by WCAG, and as Cursor's own buttons draw it");
});
