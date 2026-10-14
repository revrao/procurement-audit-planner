// One slice of a Claude Code turn in the run's sandbox. A Vercel Function on
// Hobby lives at most 300 s, and a stage can take 10-30 minutes, so each
// workflow step consumes the turn for SLICE_MS and then suspends it: the bridge
// in the sandbox keeps the turn running and buffers its events, and the next
// step reattaches from the saved cursor (HarnessAgent suspendTurn /
// createSession({ continueFrom }) / continueStream).
//
// For the agent team this carries over the spike's team-live protocol
// (lib/team-live.ts): host keep-alive steers hold the lead's turn open until
// PLANNER DONE, CHALLENGER DONE and QA DONE have reached it. A keep-alive is also
// sent just before each suspend, so the lead has a queued message across the gap
// between two slices.
import { getAgent, type SandboxSession } from "@/lib/spike";
import { DONE, KEEPALIVE, KEEPALIVE_EVERY_MS, MAX_KEEPALIVES, TEAMMATES, type DoneKey } from "@/lib/team-live";

/** Time one step consumes the turn. Well under 300 s, leaving room for sandbox resume and the workflow's own work. */
export const SLICE_MS = Number(process.env.SLICE_SECONDS || 150) * 1000;
/** A stage's whole Claude turn; inside the 45-minute sandbox session. */
export const STAGE_DEADLINE_MS = 42 * 60 * 1000;

const FINAL_STEER = "[host] All three DONE lines were sent to you. Finish steps 4 and 5 and end with the TEAM_RUN line.";

export type TeamTrack = {
  done: Partial<Record<DoneKey, { minute: number; to: string; message: string }>>;
  started: boolean;
  finalSent: boolean;
  steers: number;
  steerFailures: number;
  leadTurnEnds: number;
  spawned: string[];
};

export type Track = {
  startedAt: number;
  slices: number;
  toolCalls: number;
  subagentToolCalls: number;
  delegatedTo: string[];
  textTail: string;
  endedBy?: "stream-ended" | "complete" | "deadline" | "error";
  error?: string;
  team?: TeamTrack;
};

export type Continuation = { sessionId: string; state: unknown };
export type SliceResult = { done: boolean; cont?: Continuation; track: Track };
export type Emit = (by: string, text: string) => void;

export function newTrack(team: boolean): Track {
  return {
    startedAt: Date.now(),
    slices: 0,
    toolCalls: 0,
    subagentToolCalls: 0,
    delegatedTo: [],
    textTail: "",
    ...(team ? { team: { done: {}, started: false, finalSent: false, steers: 0, steerFailures: 0, leadTurnEnds: 0, spawned: [] } } : {}),
  };
}

export const allDone = (t: TeamTrack) => (Object.keys(DONE) as DoneKey[]).every((k) => t.done[k]);

export async function runSlice(opts: { s: SandboxSession; prompt: string; cont?: Continuation; track: Track; emit: Emit }): Promise<SliceResult> {
  const { s, emit } = opts;
  const track: Track = structuredClone(opts.track);
  const team = track.team;
  track.slices++;
  const minute = () => +((Date.now() - track.startedAt) / 60000).toFixed(2);

  const a = await getAgent();
  const session = opts.cont
    ? await a.createSession({ sessionId: opts.cont.sessionId, continueFrom: opts.cont.state as never, sandboxSession: s })
    : await a.createSession({ sandboxSession: s });
  const ac = new AbortController();

  let suspending: Promise<unknown> | undefined;
  let lastSteer = 0;
  const steer = async (kind: string, text: string) => {
    if (!team) return;
    lastSteer = Date.now();
    try {
      await a.experimental_steer({ session, text });
      team.steers++;
      emit("host", `steer ${kind} (minute ${minute()})`);
    } catch (e) {
      team.steerFailures++;
      emit("host", `steer ${kind} failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  const suspend = async () => {
    if (suspending || ac.signal.aborted) return;
    if (team && team.started && !team.finalSent && !allDone(team)) await steer("before-suspend", KEEPALIVE);
    suspending = session.suspendTurn().catch(() => null); // rejects when the turn has already finished
  };

  const sliceTimer = setTimeout(() => void suspend(), SLICE_MS);
  const remaining = STAGE_DEADLINE_MS - (Date.now() - track.startedAt);
  const deadline = setTimeout(() => ac.abort(new Error("deadline")), Math.max(remaining, 1000));
  const ticker = setInterval(() => {
    if (team && team.started && !team.finalSent && !allDone(team) && !suspending && team.steers < MAX_KEEPALIVES && Date.now() - lastSteer >= KEEPALIVE_EVERY_MS)
      void steer("keepalive", KEEPALIVE);
  }, 2_000);

  let turnText = "";
  try {
    const result = opts.cont
      ? await a.continueStream({ session, abortSignal: ac.signal })
      : await a.stream({ session, prompt: opts.prompt, abortSignal: ac.signal });
    for await (const part of result.stream as AsyncIterable<any>) {
      if (part.type === "text-delta") {
        turnText += part.text;
        track.textTail = (track.textTail + part.text).slice(-6000);
      } else if (part.type === "tool-call") {
        const input = typeof part.input === "string" ? part.input : JSON.stringify(part.input ?? {});
        track.toolCalls++;
        emit(team ? "lead" : "main", `${part.toolName} ${input.slice(0, 240)}`);
        const sub = /"subagent_type"\s*:\s*"([^"]+)"/.exec(input)?.[1];
        if (sub && !track.delegatedTo.includes(sub)) track.delegatedTo.push(sub);
        if (team) {
          const name = /"name"\s*:\s*"([^"]+)"/.exec(input)?.[1];
          if (/agent|task/i.test(part.toolName) && name && !team.spawned.includes(name)) team.spawned.push(name);
          team.started = true; // keep-alives start once the lead is working
        }
      } else if (part.type === "raw" && part.rawValue?.parent_tool_use_id && part.rawValue?.type === "assistant") {
        for (const b of part.rawValue.message?.content ?? []) {
          if (b?.type !== "tool_use") continue;
          const input = JSON.stringify(b.input ?? {});
          track.subagentToolCalls++;
          emit(team ? "teammate" : "subagent", `${b.name} ${input.slice(0, 240)}`);
          if (!team || !/SendMessage/i.test(b.name)) continue;
          const to = String(b.input?.to ?? b.input?.recipient ?? "");
          if (TEAMMATES.includes(to)) continue; // only DONE lines addressed to the lead count
          for (const k of Object.keys(DONE) as DoneKey[]) {
            if (!team.done[k] && input.includes(DONE[k])) {
              team.done[k] = { minute: minute(), to, message: String(b.input?.message ?? b.input?.content ?? "").slice(0, 200) };
              emit("host", `${DONE[k]} received by the lead (minute ${minute()})`);
            }
          }
        }
      } else if (part.type === "finish-step") {
        if (turnText.trim()) emit(team ? "lead" : "main", `says: ${turnText.trim().slice(-1500)}`);
        turnText = "";
        if (!team) continue;
        team.leadTurnEnds++;
        if (allDone(team) && !team.finalSent) {
          team.finalSent = true;
          void steer("final", FINAL_STEER);
        } else if (!allDone(team) && !team.finalSent) {
          void steer("after-turn-end", KEEPALIVE); // best effort, as in the spike
        } else if (team.finalSent && /TEAM_RUN:/.test(track.textTail)) {
          track.endedBy = "complete";
          ac.abort(new Error("complete"));
        }
      } else if (part.type === "error") {
        track.error = String(part.error?.message ?? part.error);
        emit("error", track.error);
      }
    }
  } catch (e) {
    const reason = ac.signal.reason instanceof Error ? ac.signal.reason.message : undefined;
    if (reason === "deadline") track.endedBy = "deadline";
    else if (reason !== "complete") {
      track.endedBy = "error";
      track.error = e instanceof Error ? e.message : String(e);
      emit("error", track.error);
    }
  } finally {
    clearTimeout(sliceTimer);
    clearTimeout(deadline);
    clearInterval(ticker);
  }

  const state = suspending ? await suspending : null;
  if (state && !track.endedBy) {
    emit("host", `slice ${track.slices} suspended at minute ${minute()}; the turn keeps running in the sandbox`);
    return { done: false, cont: { sessionId: session.sessionId, state }, track };
  }
  if (!suspending) await session.detach().catch(() => {});
  track.endedBy ??= "stream-ended";
  emit("host", `turn ended (${track.endedBy}) at minute ${minute()} after ${track.slices} slice(s)`);
  return { done: true, track };
}
