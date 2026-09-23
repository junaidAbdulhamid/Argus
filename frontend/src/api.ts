let accessToken: string | null = sessionStorage.getItem("argus-token");
export function setToken(value: string | null) {
  accessToken = value;
  if (value) sessionStorage.setItem("argus-token", value);
  else sessionStorage.removeItem("argus-token");
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      body?.error?.details
        ?.map(
          (d: { field: string; message: string }) => `${d.field}: ${d.message}`,
        )
        .join("; ") ||
        (typeof body?.error?.message === "object"
          ? `${body.error.message.message}: ${JSON.stringify(body.error.message.reasons || body.error.message.failures || [])}`
          : body?.error?.message) ||
        `Request failed (${response.status})`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function send<T>(path: string, body?: unknown, method = "POST") {
  return api<T>(path, {
    method,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
export const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
export const time = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const human = (value: string) =>
  value.toLowerCase().replaceAll("_", " ");

export async function downloadArtifact(path: string, filename: string) {
  const response = await fetch(`/api${path}`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!response.ok) throw new Error("Artifact download failed");
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
