// Packs the Part A repository into web/.bundle/ so the deployment carries its
// own copy of Part A and writes it into each sandbox. Runs before dev/build.
// Part A files are read, never modified.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(WEB, "..");
const OUT = path.join(WEB, ".bundle");

// What the sandbox gets. outputs/ is limited to rules.json: it is the output of
// the human-invoked /extract-rules and the input every later stage starts from.
const INCLUDE = ["CLAUDE.md", "README.md", "requirements.txt", ".claude", "scripts", "data", "outputs/rules.json"];
const EXCLUDE = ["__pycache__", "*.pyc", ".DS_Store", "settings.local.json"];

for (const p of INCLUDE) {
  if (!existsSync(path.join(ROOT, p))) {
    console.error(`bundle-repo: missing ${p} in ${ROOT}`);
    process.exit(1);
  }
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const tarball = path.join(OUT, "repo.tar.gz");
execFileSync("tar", [...EXCLUDE.flatMap((e) => ["--exclude", e]), "-czf", tarball, "-C", ROOT, ...INCLUDE], {
  env: { ...process.env, COPYFILE_DISABLE: "1" }, // no macOS ._ files
  stdio: "inherit",
});

// The committed analytics.json is the reference the spend-analyst run is compared with.
copyFileSync(path.join(ROOT, "outputs/analytics.json"), path.join(OUT, "reference-analytics.json"));

// Team probe inputs: the committed outputs as they stand after the auditor gate
// (step 4), without anything the planner/challenger/qa-reviewer produce. Kept
// out of repo.tar.gz so the sandbox snapshot hash does not change.
const TEAM_INPUTS = ["outputs/analytics.json", "outputs/analytics-full", "outputs/history.json", "outputs/risk-ratings.json",
  "outputs/risk-register.md", "outputs/auditor-comments.md"];
execFileSync("tar", [...EXCLUDE.flatMap((e) => ["--exclude", e]), "-czf", path.join(OUT, "team-inputs.tar.gz"), "-C", ROOT, ...TEAM_INPUTS], {
  env: { ...process.env, COPYFILE_DISABLE: "1" },
  stdio: "inherit",
});

// Seeded runs (web app): the committed stage 1-2 outputs, restored into the sandbox
// in place of re-running extract-rules and the two analysts. Their validators
// still run on them in the sandbox.
const SEED_ANALYSIS = ["outputs/analytics.json", "outputs/analytics-full", "outputs/history.json"];
execFileSync("tar", [...EXCLUDE.flatMap((e) => ["--exclude", e]), "-czf", path.join(OUT, "seed-analysis.tar.gz"), "-C", ROOT, ...SEED_ANALYSIS], {
  env: { ...process.env, COPYFILE_DISABLE: "1" },
  stdio: "inherit",
});

const skills = readdirSync(path.join(ROOT, ".claude/skills"), { withFileTypes: true })
  .filter((d) => d.isDirectory() && existsSync(path.join(ROOT, ".claude/skills", d.name, "SKILL.md")))
  .map((d) => d.name)
  .sort();
const agents = readdirSync(path.join(ROOT, ".claude/agents"))
  .filter((f) => f.endsWith(".md"))
  .map((f) => f.replace(/\.md$/, ""))
  .sort();
const settings = JSON.parse(readFileSync(path.join(ROOT, ".claude/settings.json"), "utf8"));
const claudeMdTitle = readFileSync(path.join(ROOT, "CLAUDE.md"), "utf8").split("\n").find((l) => l.startsWith("# ")) ?? "";

// The hash keys the sandbox snapshot, so it covers the bundled files' paths and
// contents only: the tarball's own bytes change with every build (gzip header
// time, file mtimes after a git checkout), which would rebuild the snapshot.
const contentHash = createHash("sha256");
const members = execFileSync("tar", ["-tzf", tarball], { encoding: "utf8", maxBuffer: 64 << 20 })
  .split("\n")
  .filter((f) => f && !f.endsWith("/"))
  .sort();
for (const f of members) contentHash.update(`${f}\0`).update(readFileSync(path.join(ROOT, f))).update("\0");

const manifest = {
  sha256: contentHash.digest("hex"),
  bytes: readFileSync(tarball).length,
  include: INCLUDE,
  expected: { claudeMdTitle: claudeMdTitle.replace(/^# /, ""), skills, agents, settingsEnv: settings.env ?? {} },
};
writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`bundle-repo: ${(manifest.bytes / 1e6).toFixed(1)} MB, sha256 ${manifest.sha256.slice(0, 12)}`);
