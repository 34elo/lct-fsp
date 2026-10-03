import type { ParsedResume } from "@/api/model";

/** Предупреждения парсера (ml.md §2.7) человеческим языком; неизвестные коды не показываем. */
export function warningText(w: string): string | null {
  if (w === "text_truncated") return "Резюме очень длинное: прочитали только начало.";
  if (w === "taxonomy_unavailable") return "Справочник навыков был недоступен: навыки ниже ждут сопоставления.";
  if (w === "experience_period_invalid") return "Не поняли даты на одном из мест работы. Поправьте при необходимости.";
  const [code, raw] = w.split(/:(.*)/s);
  if (code === "quote_not_found" || code === "skill_not_in_quote") {
    return `«${raw}» не нашли в тексте резюме, поэтому не засчитали.`;
  }
  return null;
}

export function failureText(code: string | null | undefined): string {
  switch (code) {
    case "scanned_pdf":
      return "Похоже, это скан без текста. Загрузите PDF или DOCX с текстом либо заполните профиль вручную.";
    case "bad_file":
      return "Не получилось прочитать файл. Проверьте, что это PDF или DOCX.";
    default:
      return "Не получилось разобрать резюме. Попробуйте ещё раз или заполните профиль вручную.";
  }
}

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

/** Итоговые строки лога после разбора: только то, что реально нашли. */
export function summaryLines(p: ParsedResume): string[] {
  const exp = p.experience?.length ?? 0;
  const edu = p.education?.length ?? 0;
  const sk = p.skills?.length ?? 0;
  return [
    `Нашёл ${exp} ${plural(exp, "место работы", "места работы", "мест работы")}`,
    `Нашёл образование: ${edu}`,
    `Нашёл ${sk} ${plural(sk, "навык", "навыка", "навыков")}`,
  ];
}
