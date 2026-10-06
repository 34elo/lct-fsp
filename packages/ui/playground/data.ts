// Демо-данные из docs/design/pack/docs/DATA.md. Только для playground и тестов, не для экранов.
import type { FspResult, TrustKind, TrustLevel } from "../src";

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
];

export const TEXT_SIZES = [11, 12, 13, 14, 16, 20, 24, 32, 48] as const;

export const RADII = ["sm", "md", "lg", "xl", "2xl"] as const;
