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
} from "./brand";
