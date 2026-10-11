import { describe, expect, it } from "vitest";

import { offerCardData } from "./offer-cards";
import type { CandidateOffer } from "./offer-model";

const offer = (demo: boolean) =>
  ({
    id: "o1", status: "sent", created_at: "2026-10-02T10:00:00Z", expires_at: "2026-10-16T10:00:00Z",
    vacancy: null, title: "Приглашение", salary_from: 200000, salary_to: 250000, salary_basis: "gross",
    below_candidate_min: false, match_snapshot: null, decline: null,
    company: { id: "c1", name: "Северный код", responsibility_score: 4.6, verified: true, demo },
  }) as unknown as CandidateOffer;

describe("пометка демо-компании", () => {
  it("реальный кандидат видит «демо» рядом с названием демо-компании", () => {
    expect(offerCardData(offer(true)).company).toBe("Северный код · демо");
  });
  it("у обычной компании пометки нет", () => {
    expect(offerCardData(offer(false)).company).toBe("Северный код");
  });
});
