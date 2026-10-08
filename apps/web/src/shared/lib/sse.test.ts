import { QueryClient } from "@tanstack/react-query";

import { createEventStream, invalidateFor } from "./sse";

class FakeES {
  static all: FakeES[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  listeners: Record<string, (e: MessageEvent<string>) => void> = {};
  constructor(public url: string) {
    FakeES.all.push(this);
  }
  addEventListener(t: string, l: (e: MessageEvent<string>) => void) {
    this.listeners[t] = l;
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeES.all = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

const make = (token: () => string | null, onMessage = vi.fn()) => ({
  onMessage,
  stop: createEventStream({
    url: "/s",
    getToken: token,
    onMessage,
    create: (u) => new FakeES(u) as unknown as EventSource,
  }),
});

test("доставляет события и подставляет токен", () => {
  const { onMessage } = make(() => "a b");
  expect(FakeES.all[0].url).toBe("/s?access_token=a%20b");
  FakeES.all[0].listeners["offer.updated"]({ data: '{"offer_id":"1"}' } as MessageEvent<string>);
  expect(onMessage).toHaveBeenCalledWith({ type: "offer.updated", data: { offer_id: "1" } });
});

test("переподключается с растущей паузой и свежим токеном", () => {
  let tok = "t1";
  make(() => tok);
  FakeES.all[0].onerror?.();
  expect(FakeES.all[0].closed).toBe(true);
  tok = "t2";
  vi.advanceTimersByTime(999);
  expect(FakeES.all).toHaveLength(1);
  vi.advanceTimersByTime(1);
  expect(FakeES.all).toHaveLength(2);
  expect(FakeES.all[1].url).toContain("t2");
  FakeES.all[1].onerror?.();
  vi.advanceTimersByTime(1999);
  expect(FakeES.all).toHaveLength(2);
  vi.advanceTimersByTime(1);
  expect(FakeES.all).toHaveLength(3);
});

test("stop закрывает поток и отменяет переподключение", () => {
  const { stop } = make(() => null);
  FakeES.all[0].onerror?.();
  stop();
  vi.advanceTimersByTime(60000);
  expect(FakeES.all).toHaveLength(1);
});

test("profile.updated инвалидирует профиль", () => {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  invalidateFor(qc, { type: "profile.updated", data: {} });
  expect(spy).toHaveBeenCalledWith({ queryKey: ["profile"] });
});
