// @fsp/ui — дизайн-система ФСП Карьеры. Пакет без сборки: потребители импортируют исходники.
export { cn } from "./lib/cn";
export { ThemeScope } from "./lib/theme-scope";
export { Button, buttonVariants, type ButtonProps } from "./primitives/button";
export * from "./primitives/display";
export * from "./primitives/form";
export * from "./primitives/overlay";
export {
  ConstellationAvatar,
  Logo,
  MatchRing,
  SkillChip,
  TrustDots,
  constellationPoints,
  hashSeed,
  type TrustKind,
  type TrustLevel,
  type TrustSource,
} from "./brand";
export {
  FspProtocol,
  GradeBadge,
  SectionLabel,
  TeamSignal,
  VerifiedMark,
  pseudonymLabel,
  type FspResult,
} from "./brand/protocol";
export { formatRub, formatRubRange, formatRubRangeShort } from "./lib/format";
export {
  AcceptanceMeter,
  BuildLog,
  CircuitLine,
  MatchWhy,
  OFFER_STATUS_LABEL,
  SalaryRange,
  StatusBadge,
  UpliftCard,
  type AcceptanceLevel,
  type CircuitStep,
  type LogLine,
  type OfferStatus,
  type WhyItem,
  type WhyKind,
} from "./brand/match";
export { CandidateCard, OfferCard, type CandidateCardData, type OfferCardData } from "./brand/cards";
export * from "./icons";
// v2: примитивы, компоненты, каркас страниц.
export * from "./v2/primitives";
export * from "./v2/charts";
export * from "./v2/cards";
export * from "./v2/assessment";
export * from "./v2/shell";
// v3: свои контролы вместо голых HTML-элементов, Markdown, InfoTip, скелетоны-пресеты.
export * from "./v3/combobox";
export * from "./v3/inputs";
export * from "./v3/content";
export * from "./v3/diagram";
export * from "./v3/skeletons";
export * from "./v3/roadmap";
// интерактивный граф доказательств.
export * from "./v3/graph-model";
export * from "./v3/graph";
