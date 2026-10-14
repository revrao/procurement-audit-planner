// The two human gates write into the same files the auditor edits by hand in
// Part A: the decision table in outputs/auditor-comments.md (gate 1) and the
// sign-off block at the end of outputs/review.md (gate 2).
import type { Gate1Payload, Gate2Payload, GateRisk } from "@/lib/run-types";

const DECISIONS = ["approve", "amend", "reject"];
const cells = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const isSeparator = (c: string[]) => c.every((x) => /^:?-{3,}:?$/.test(x));

/** The decision table: header indices plus each risk row's line number. */
function table(md: string) {
  const lines = md.split("\n");
  let header: string[] | null = null;
  const rows: { line: number; c: string[] }[] = [];
  lines.forEach((l, i) => {
    if (!l.trim().startsWith("|")) return void (header = rows.length ? header : null);
    const c = cells(l);
    const low = c.map((x) => x.toLowerCase());
    if (low.includes("risk id") && low.includes("decision")) header = low;
    else if (header && !isSeparator(c) && /^R-\d{2,}$/.test(c[0])) rows.push({ line: i, c });
  });
  return { lines, header: header as string[] | null, rows };
}

export function parseRisks(md: string): GateRisk[] {
  const { header, rows } = table(md);
  if (!header) return [];
  const col = (c: string[], name: string) => c[header.indexOf(name)] ?? "";
  return rows.map(({ c }) => ({
    id: col(c, "risk id"),
    risk: col(c, "risk"),
    likelihood: col(c, "likelihood"),
    impact: col(c, "impact"),
    score: col(c, "score"),
    band: col(c, "band"),
  }));
}

const oneLine = (s: string) => s.replace(/\s+/g, " ").trim();

export function applyGate1(md: string, p: Gate1Payload): { content: string; errors: string[] } {
  const { lines, header, rows } = table(md);
  const errors: string[] = [];
  if (!header) return { content: md, errors: ["auditor-comments.md has no decision table"] };
  const di = header.indexOf("decision"), ci = header.indexOf("comment");
  if (!oneLine(p.reviewer ?? "")) errors.push("Reviewer is required");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(p.date ?? "")) errors.push("Date must be YYYY-MM-DD");
  for (const { line, c } of rows) {
    const id = c[0];
    const d = p.decisions?.[id];
    const decision = String(d?.decision ?? "").toLowerCase();
    const comment = oneLine(d?.comment ?? "");
    if (!DECISIONS.includes(decision)) errors.push(`${id}: choose approve, amend or reject`);
    if (decision !== "approve" && decision && !comment) errors.push(`${id}: ${decision} needs a comment saying what to change or why`);
    if (comment.includes("|")) errors.push(`${id}: the comment cannot contain the | character`);
    const next = [...c];
    next[di] = decision;
    if (ci >= 0) next[ci] = comment;
    lines[line] = `| ${next.join(" | ")} |`;
  }
  const unknown = Object.keys(p.decisions ?? {}).filter((id) => !rows.some((r) => r.c[0] === id));
  if (unknown.length) errors.push(`decisions for risks not in the register: ${unknown.join(", ")}`);
  if (errors.length) return { content: md, errors };

  let out = lines.join("\n");
  out = setField(out, "Reviewer", oneLine(p.reviewer));
  out = setField(out, "Date", p.date);
  const general = (p.general ?? "").trim();
  if (general) {
    out = out.replace(/(^## General comments\s*\n)([\s\S]*?)(?=^## |$(?![\s\S]))/m, (_m, head: string, body: string) => {
      const keep = (body.match(/<!--[\s\S]*?-->/g) ?? []).join("\n");
      return `${head}\n${keep ? keep + "\n\n" : ""}${general}\n`;
    });
  }
  return { content: out, errors };
}

/** Sets a `Name: value` line, adding it if the file has none. */
function setField(md: string, name: string, value: string) {
  const re = new RegExp(`^${name}:[ \\t]*.*$`, "m");
  return re.test(md) ? md.replace(re, `${name}: ${value}`) : md;
}

/** The verdict in review.md's `## Verdict` section (the Runs table also mentions BLOCKED). */
export function reviewVerdict(md: string) {
  const section = /^## Verdict[ \t]*\n([\s\S]*?)(?=^## |(?![\s\S]))/m.exec(md)?.[1] ?? "";
  return /READY FOR SIGN-OFF|BLOCKED/.exec(section)?.[0] ?? null;
}

export function applyGate2(md: string, p: Gate2Payload): { content: string; errors: string[] } {
  const errors: string[] = [];
  const at = md.search(/^## Auditor sign-off\s*$/m);
  if (at < 0) errors.push("review.md has no '## Auditor sign-off' block");
  if (!["sign off", "return to the team"].includes(p.decision)) errors.push("Decision must be 'sign off' or 'return to the team'");
  if (!oneLine(p.reviewer ?? "")) errors.push("Reviewer is required");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(p.date ?? "")) errors.push("Date must be YYYY-MM-DD");
  if (p.decision === "sign off" && reviewVerdict(md) !== "READY FOR SIGN-OFF") errors.push("Sign off only on a READY FOR SIGN-OFF review");
  if (p.decision === "return to the team" && !oneLine(p.comments ?? "")) errors.push("Say in Comments what the team should change");
  if (errors.length) return { content: md, errors };

  let block = md.slice(at);
  for (const [k, v] of [["Decision", p.decision], ["Reviewer", oneLine(p.reviewer)], ["Date", p.date], ["Comments", oneLine(p.comments ?? "")]]) {
    const re = new RegExp(`^${k}:.*$`, "m");
    block = re.test(block) ? block.replace(re, `${k}: ${v}`) : `${block.trimEnd()}\n${k}: ${v}\n`;
  }
  return { content: md.slice(0, at) + block, errors };
}
