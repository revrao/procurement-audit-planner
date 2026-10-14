"use client";
import { Marked } from "marked";
import { useMemo } from "react";

const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// Agent-written Markdown is rendered with raw HTML escaped, never injected.
const marked = new Marked({ gfm: true, renderer: { html: ({ text }) => escape(text) } });

export function Markdown({ source }: { source: string }) {
  const html = useMemo(() => marked.parse(source.replace(/<!--[\s\S]*?-->\n?/g, ""), { async: false }) as string, [source]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
