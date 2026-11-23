// The previews' theme (media/preview-themes.css): ?theme=light, hc, cursor, midnight or plus puts that theme's
// variables on the page, and the body class VS Code would set; none is Dark Modern.
const THEMES: Record<string, string> = { light: "vscode-light", hc: "vscode-high-contrast", cursor: "vscode-dark", midnight: "vscode-dark", plus: "vscode-dark" };

export function wearTheme(theme: string | null) {
  const kind = (theme && THEMES[theme]) || "vscode-dark";
  if (theme && THEMES[theme]) document.documentElement.classList.add(theme);
  document.body.classList.add(kind);
}
