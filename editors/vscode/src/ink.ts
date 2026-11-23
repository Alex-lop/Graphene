// The text on a filled button, for the graph and Home alike. The theme's own button.foreground where it reads on
// the theme's button (4.5:1); where it does not, white, or near-black on a pale button. Cursor Dark's is near-black
// on a mid blue, 3.4:1: every filled act there looked switched off. Midnight's pale button keeps its dark ink.

type RGB = [number, number, number];

const lum = ([r, g, b]: RGB) => {
  const c = (v: number) => (v / 255 <= 0.03928 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4);
  return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b);
};
export const contrast = (a: RGB, b: RGB) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);

const WHITE: RGB = [255, 255, 255], NEAR_BLACK: RGB = [20, 20, 20];

/** The ink to wear instead of the theme's, or null to keep the theme's. White where it reads better than the theme's
 *  and passes 4.5:1; near-black only where the theme's is under 3:1. WCAG's ratio under-rates white on a saturated
 *  blue (Cursor Light's own white is 3.9:1 and reads as Cursor's buttons do), so a white ink is left at that. */
export function inkFor(bg: RGB, fg: RGB): string | null {
  const now = contrast(bg, fg);
  if (now >= 4.5) return null;
  if (contrast(bg, WHITE) > now && contrast(bg, WHITE) >= 4.5) return "rgb(255, 255, 255)";
  return now < 3 && contrast(bg, NEAR_BLACK) >= 4.5 ? `rgb(${NEAR_BLACK.join(", ")})` : null;
}

/** A CSS colour as the canvas reads it (`#rrggbb`, or `rgba(r, g, b, a)` for one that is not opaque). */
function rgbOf(css: string): RGB | null {
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx || !css.trim()) return null;
  ctx.fillStyle = css.trim();
  const v = String(ctx.fillStyle);
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(v);
  if (hex) return [1, 2, 3].map((i) => parseInt(hex[i]!, 16)) as RGB;
  const n = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(v);
  return n ? [Number(n[1]), Number(n[2]), Number(n[3])] : null;
}

/** Wear it: the theme's button.foreground, overridden on the body where it does not read, again whenever VS Code
 *  changes the theme (it sets the theme's colours on <html>, and its kind as the body's class). */
export function wearInk() {
  const set = () => {
    const root = getComputedStyle(document.documentElement);
    const bg = rgbOf(root.getPropertyValue("--vscode-button-background")), fg = rgbOf(root.getPropertyValue("--vscode-button-foreground"));
    const ink = bg && fg ? inkFor(bg, fg) : null;
    if (ink) document.body.style.setProperty("--vscode-button-foreground", ink);
    else document.body.style.removeProperty("--vscode-button-foreground");
  };
  set();
  const watch = new MutationObserver(set);
  watch.observe(document.documentElement, { attributes: true, attributeFilter: ["style", "class"] });
  watch.observe(document.body, { attributes: true, attributeFilter: ["class"] });
}
