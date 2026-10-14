import type { NextConfig } from "next";
import { withWorkflow } from "workflow/next";

const nextConfig: NextConfig = {
  // The Part A bundle is read at runtime with fs, so ship it with every function
  // that writes it into a sandbox: the spike route and the workflow step routes.
  outputFileTracingIncludes: { "/api/spike": ["./.bundle/**"], "/.well-known/workflow/**": ["./.bundle/**"] },
  // The harness spawns and talks to sandbox processes; keep it out of the bundler.
  serverExternalPackages: ["@ai-sdk/harness", "@ai-sdk/harness-claude-code", "@ai-sdk/sandbox-vercel"],
};

export default withWorkflow(nextConfig);
