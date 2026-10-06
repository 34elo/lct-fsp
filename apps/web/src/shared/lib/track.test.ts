import { describe, expect, it, vi } from "vitest";

import { createTracker, MAX_BATCH, SESSION_IDLE_MS, setRunId } from "./track";

const readBlob = (b: Blob) =>
  new Promise<string>((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.readAsText(b);
  });

const setup = (extra: Parameters<typeof createTracker>[0] = {}) => {
  const send = vi.fn().mockResolvedValue(undefined);
  const beacon = vi.fn().mockReturnValue(true);
  let t = 1_700_000_000_000;
  const tracker = createTracker({ send, beacon, now: () => t, getToken: () => "tok", ...extra });
  return { tracker, send, beacon, advance: (ms: number) => (t += ms) };
};

describe("tracker", () => {
  it("батчит события и отправляет раз в 5 секунд", async () => {
    vi.useFakeTimers();
    const { tracker, send } = setup();
    tracker.track("card_dwell", { seconds: 2, skip: undefined });
    tracker.track("graph_opened", { nodes: 5 });
    expect(send).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5000);
    expect(send).toHaveBeenCalledTimes(1);
    const body = JSON.parse(send.mock.calls[0][1]);
    expect(body.events).toHaveLength(2);
    expect(body.events[0].props).toEqual({ seconds: 2 });
    expect(body.batch_id).toBeTruthy();
    expect(body.access_token).toBeUndefined();
    vi.useRealTimers();
  });

  it("не больше 50 событий в запросе", async () => {
    const { tracker, send } = setup();
    for (let i = 0; i < MAX_BATCH + 5; i++) tracker.track("card_dwell", { seconds: i });
    await tracker.flush();
    const sizes = send.mock.calls.map((c) => JSON.parse(c[1]).events.length);
    expect(sizes).toEqual([50, 5]);
  });

  it("при уходе со страницы шлёт sendBeacon с токеном в теле", async () => {
    const { tracker, beacon, send } = setup();
    tracker.track("card_dwell", { seconds: 1 });
    tracker.flushBeacon();
    expect(send).not.toHaveBeenCalled();
    expect(beacon).toHaveBeenCalledTimes(1);
    const blob = beacon.mock.calls[0][1] as Blob;
    expect(blob.type).toBe("application/json");
    const body = JSON.parse(await readBlob(blob));
    expect(body.access_token).toBe("tok");
    expect(body.events).toHaveLength(1);
    expect(tracker.size()).toBe(0);
  });

  it("сеть упала: ошибка не пробрасывается", async () => {
    const send = vi.fn().mockRejectedValue(new Error("offline"));
    const { tracker } = setup({ send });
    tracker.track("card_dwell", { seconds: 1 });
    await expect(tracker.flush()).resolves.toBeUndefined();
  });

  it("новая сессия после 30 минут бездействия", async () => {
    const { tracker, send, advance } = setup();
    tracker.track("a", {});
    advance(60_000);
    tracker.track("b", {});
    advance(SESSION_IDLE_MS + 1);
    tracker.track("c", {});
    await tracker.flush();
    const ev = JSON.parse(send.mock.calls[0][1]).events;
    expect(ev[0].session_id).toBe(ev[1].session_id);
    expect(ev[2].session_id).not.toBe(ev[0].session_id);
  });

  it("ставит run_id живого прогона на события, пока он задан", async () => {
    const { tracker, send } = setup();
    tracker.track("card_dwell", { seconds: 1 });
    setRunId("11111111-1111-4111-8111-111111111111");
    tracker.track("card_dwell", { seconds: 2 });
    setRunId(null);
    tracker.track("card_dwell", { seconds: 3 });
    await tracker.flush();
    const ids = JSON.parse(send.mock.calls[0][1]).events.map((e: { run_id?: string }) => e.run_id);
    expect(ids).toEqual([undefined, "11111111-1111-4111-8111-111111111111", undefined]);
  });
});
