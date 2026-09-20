import type { Payload } from "./types";

// An exported file carries its data inline and fetches nothing; the served page asks its own server.
export async function load(search: string = window.location.search): Promise<Payload> {
  const inline = document.getElementById("graphene-data");
  if (inline?.textContent) return JSON.parse(inline.textContent) as Payload;
  const response = await fetch(`./api/graph${search}`);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as Payload;
}

export const exported = (): boolean => document.getElementById("graphene-data") !== null;

/** One plan edit, made by the person at this page. The token is this run of `graphene ui`'s, and
 * what comes back when the server says no is its own sentence, thrown whole for the page to print. */
export async function send(op: string, body: unknown, token: string | null): Promise<void> {
  const response = await fetch(`./api/plan/${op}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { "X-Graphene-Token": token } : {}) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const said = (await response.text()).trim();
    throw new Error(said || `the server answered ${response.status}`);
  }
}
