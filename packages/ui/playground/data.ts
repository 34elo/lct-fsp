// Демо-данные из пакета макетов v1 (DATA.md). Только для playground и тестов, не для экранов.
import type { CandidateCardV2Data, CategoryCardData, ConstellationNode, FspResult, OfferCardV2Data, ScatterPoint, TrustKind, TrustLevel } from "../src";

export const DEMO_CANDIDATES = [
  { pseudo: "Backend #4821", title: "Backend Middle", match: 92, note: "финал Кубка России 2025, 2 из 40, капитан" },
  { pseudo: "Backend #1307", title: "Middle Backend Go", match: 81, note: "ожидания от 230 000 ₽" },
  { pseudo: "Backend #3342", title: "Junior+", match: 64, note: "медиана Junior+ 150 000 ₽" },
] as const;

export const DEMO_SKILLS: { name: string; level: TrustLevel; variant: TrustKind }[] = [
  { name: "Python", level: 4, variant: "verified" },
  { name: "FastAPI", level: 3, variant: "verified" },
  { name: "PostgreSQL", level: 3, variant: "inferred" },
  { name: "Docker", level: 2, variant: "claimed" },
  { name: "Kafka", level: 1, variant: "adjacent" },
  { name: "Rust", level: 1, variant: "provisional" },
];

export const DEMO_FSP: FspResult[] = [
  { discipline: "Продуктовое программирование", tournament: "Кубок России", stage: "финал", place: 2, total: 40, role: "капитан", year: 2025 },
  { discipline: "Алгоритмы", tournament: "Кубок России", stage: "региональный этап", place: 1, total: 112, year: 2024 },
  { discipline: "Командная разработка", tournament: "отборочный", place: 3, total: 64, role: "участник", year: 2024 },
  { discipline: "Алгоритмы", tournament: "Открытая лига", stage: "этап 2", place: 17, total: 340, year: 2023 },
];

export const TOKEN_GROUPS: { title: string; tokens: string[] }[] = [
  { title: "Бренд", tokens: ["brand", "brand-deep", "brand-mid", "brand-fg", "on-brand", "signal"] },
  { title: "Оттенки", tokens: ["tint-50", "tint-100", "tint-200"] },
  { title: "Поверхности и текст", tokens: ["page", "card", "ink", "muted", "hairline"] },
  {
    title: "Состояния",
    tokens: ["success", "success-bg", "warning", "warning-bg", "warning-border", "warning-fg", "error", "error-bg"],
  },

  {
    title: "v2 — имена макетов (алиасы, docs/design/v2/fsp2.css)",
    tokens: ["deep", "mid", "t50", "t100", "t200", "hair", "ok", "ok-bg", "warn", "warn-bg", "warn-bd", "warn-fg", "err", "err-bg", "err-border", "code-bg", "chip-fg"],
  },
];

export const TEXT_SIZES = [11, 12, 13, 14, 16, 20, 24, 32, 48] as const;

export const RADII = ["sm", "md", "lg", "xl", "2xl"] as const;

/* Доска v2 (docs/design/v2/screens/v2_components.html). */
export const V2_CONSTELLATION: ConstellationNode[] = [
  { name: "Python", level: 3 },
  { name: "SQL", level: 2 },
  { name: "Git", level: 0, state: "claimed" },
  { name: "REST", level: 1, state: "adjacent" },
  { name: "Docker", level: 1, state: "adjacent" },
];

export const V2_SCATTER: ScatterPoint[] = [
  [10, 15], [15, 20], [18, 16], [20, 25], [23, 27], [25, 21], [27, 34], [30, 30], [33, 40], [35, 36], [38, 46], [40, 43],
  [44, 51], [46, 40], [49, 49], [51, 57], [54, 44], [56, 53], [58, 63], [61, 54], [63, 47], [65, 64], [67, 59], [69, 70],
  [74, 67], [77, 61], [83, 80], [86, 69], [89, 77], [92, 83], [96, 74], [8, 7], [11, 9], [22, 11], [28, 17], [38, 29], [46, 31], [53, 37], [61, 41],
].map(([x, y]) => ({ x, y }));

export const V2_HEATMAP: number[] = Array.from({ length: 84 }, (_, i) => [0, 4, 3, 0, 1, 4, 0, 2, 1, 0, 3, 2][i % 12]);

export const V2_TYPES = [
  { label: "Фундамент", value: 62 },
  { label: "Хард", value: 48 },
  { label: "Мышление", value: 55 },
  { label: "Бизнес", value: 30 },
  { label: "Софт", value: 66 },
];

export const V2_CATEGORY: CategoryCardData = {
  title: "Backend · Middle",
  histogram: [2, 4, 6, 9, 10, 8, 5, 3, 2, 1],
  highlight: 4,
  stats: [
    { value: 37, label: "человек" },
    { value: "220 000", label: "медиана ₽" },
    { value: "24 %", label: "с ФСП" },
  ],
};

export const V2_CANDIDATE: CandidateCardV2Data = {
  pseudonym: "Backend #3377",
  match: 94,
  grade: "Middle",
  confirmed: true,
  salary: "190–220 тыс. ₽",
  skills: [
    { name: "Python", level: 3 },
    { name: "PostgreSQL", level: 2 },
    { name: "Docker", level: 2 },
  ],
  meta: "Удалённо · 3 навыка подтверждены",
};

export const V2_FEED = [
  { time: "10:12", text: "Backend #4821 подтвердил Junior" },
  { time: "09:48", text: "В Backend · Junior +2 подтверждённых" },
  { time: "09:30", text: "Backend #2210 заявил Middle" },
];

export const V2_OFFER: OfferCardV2Data = {
  company: "Северный код",
  rating: "4.6 / 5",
  verified: true,
  responseNote: "отвечает в 85 % · 18 ч",
  salary: "150–220 тыс. ₽",
  salaryNote: "до НДФЛ",
  task: "мини-задание · 45 мин · до 12.10",
  reasons: ["Python, SQL — подтверждено тестом", "Финалист ФСП", "Вилка выше твоих ожиданий"],
  deadline: "срок до 14.10",
};
