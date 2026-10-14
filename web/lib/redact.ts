// Defence in depth: everything a run writes for the browser passes through
// here, so a secret an agent happened to print (e.g. by running `env`) never
// reaches the UI. The UI itself never reads environment variables.
const PATTERNS: [RegExp, string][] = [
  [/sk-ant-[A-Za-z0-9_-]{8,}/g, "[redacted]"], // Anthropic keys
  [/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, "[redacted]"], // JWTs, e.g. Vercel OIDC tokens
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{16,}/gi, "Bearer [redacted]"],
  [/\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)=\S+/g, "$1=[redacted]"], // NAME=value lines from env dumps
];

function secretValues() {
  return Object.entries(process.env)
    .filter(([k, v]) => /KEY|TOKEN|SECRET|PASSWORD/i.test(k) && typeof v === "string" && v.length >= 8)
    .map(([, v]) => v as string);
}

export function redactText(s: string): string {
  let out = s;
  for (const v of secretValues()) out = out.split(v).join("[redacted]");
  for (const [re, by] of PATTERNS) out = out.replace(re, by);
  return out;
}

export function redact<T>(value: T): T {
  if (typeof value === "string") return redactText(value) as T;
  if (Array.isArray(value)) return value.map(redact) as T;
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, redact(v)])) as T;
  return value;
}
