// The spread of a sample, so a before and an after compare whole distributions, not one median of five.
import { loadavg } from "node:os";

/** n, min, p50, p90, max and mean of `xs`; the percentiles by nearest rank. */
export function summary(xs) {
  const s = [...xs].sort((a, b) => a - b), n = s.length;
  const q = (p) => s[Math.max(0, Math.ceil(p * n) - 1)];
  return { n, min: s[0], p50: q(0.5), p90: q(0.9), max: s[n - 1], mean: Math.round(s.reduce((a, b) => a + b, 0) / n) };
}

/** One line: `n 20: p50 338 ms, p90 509, max 582, mean 300, min 27 (load 5.9)`. */
export function line(xs, unit = "ms") {
  const t = summary(xs);
  return `n ${t.n}: p50 ${t.p50} ${unit}, p90 ${t.p90}, max ${t.max}, mean ${t.mean}, min ${t.min} (load ${loadavg()[0].toFixed(1)})`;
}
