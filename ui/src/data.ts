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
