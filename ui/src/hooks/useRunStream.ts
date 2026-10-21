import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Run, RunEvent, StreamState } from "../types";

const EVENT_NAMES = [
  "run",
  "run.updated",
  "status",
  "status.changed",
  "plan",
  "plan.updated",
  "finding",
  "finding.created",
  "action",
  "approval.required",
  "tool.started",
  "tool.completed",
  "message",
  "error",
];

interface UseRunStreamOptions {
  runId?: string;
  onRun: (run: Run) => void;
  onRefresh: () => void;
}

export function useRunStream({
  runId,
  onRun,
  onRefresh,
}: UseRunStreamOptions) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  const refreshRef = useRef(onRefresh);
  const runRef = useRef(onRun);

  refreshRef.current = onRefresh;
  runRef.current = onRun;

  useEffect(() => {
    setEvents([]);
    if (!runId) return;

    let disposed = false;
    let source: EventSource | undefined;
    let reconnectTimer: number | undefined;
    let pollingTimer: number | undefined;
    let refreshTimer: number | undefined;
    let failureCount = 0;

    const poll = async () => {
      try {
        const run = await api.runs.get(runId);
        if (!disposed) {
          runRef.current(run);
          refreshRef.current();
        }
      } catch {
        // A transient polling failure is surfaced by the regular page refresh.
      }
    };

    const beginPolling = () => {
      if (pollingTimer || disposed) return;
      setState("polling");
      void poll();
      pollingTimer = window.setInterval(() => void poll(), 5_000);
    };

    const stopPolling = () => {
      if (pollingTimer) window.clearInterval(pollingTimer);
      pollingTimer = undefined;
    };

    const queueRefresh = () => {
      if (refreshTimer) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        void poll();
      }, 350);
    };

    const receive = (message: MessageEvent<string>, eventType?: string) => {
      try {
        const parsed = JSON.parse(message.data) as
          | RunEvent
          | { event?: RunEvent; run?: Run };
        const event =
          "event" in parsed && parsed.event ? parsed.event : (parsed as RunEvent);
        if ("run" in parsed && parsed.run) runRef.current(parsed.run);
        if (event && typeof event === "object") {
          const normalized: RunEvent = {
            id: event.id ?? `${Date.now()}-${Math.random()}`,
            run_id: event.run_id ?? runId,
            type: event.type ?? eventType ?? "message",
            created_at: event.created_at ?? new Date().toISOString(),
            payload: event.payload ?? parsed,
          };
          setEvents((current) => {
            if (current.some((item) => item.id === normalized.id)) return current;
            return [...current, normalized].slice(-250);
          });
        }
        queueRefresh();
      } catch {
        const normalized: RunEvent = {
          id: `${Date.now()}-${Math.random()}`,
          run_id: runId,
          type: eventType ?? "message",
          created_at: new Date().toISOString(),
          payload: message.data,
        };
        setEvents((current) => [...current, normalized].slice(-250));
      }
    };

    const connect = () => {
      if (disposed) return;
      setState(failureCount ? "reconnecting" : "connecting");
      source = new EventSource(api.runs.eventsUrl(runId));
      source.onopen = () => {
        failureCount = 0;
        stopPolling();
        setState("live");
      };
      source.onmessage = (event) => receive(event);
      EVENT_NAMES.forEach((name) => {
        if (name !== "message" && name !== "error") {
          source?.addEventListener(name, (event) =>
            receive(event as MessageEvent<string>, name),
          );
        }
      });
      source.onerror = () => {
        source?.close();
        source = undefined;
        failureCount += 1;
        beginPolling();
        const delay = Math.min(1_000 * 2 ** Math.min(failureCount, 4), 15_000);
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      source?.close();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (pollingTimer) window.clearInterval(pollingTimer);
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [runId]);

  return { events, state };
}
