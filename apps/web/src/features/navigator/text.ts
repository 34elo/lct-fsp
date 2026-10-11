import { ApiError } from "@/api/mutator";
import type { UpliftConfirm } from "@/api/model";

export const T = {
  title: "Навигатор роста",
  lead: "Что подтвердить, чтобы подойти под больше вакансий и перейти на следующий грейд.",
  loading: "Считаем путь…",
  retry: "Повторить",
  errorTitle: "Не удалось загрузить навигатор",
  forbidden: "Навигатор доступен после согласий и подтверждения email.",
  emptyTitle: "Пока нечего предложить",
  emptyText: "Заполните профиль и выберите направление — навигатор построит путь.",
  emptyAction: "Выбрать направление",
  roadmapLabel: "Роадмап роста",
  stepNow: "Сейчас",
  stepSkill: "Навык",
  stepTest: "Тест",
  stepGoal: "Цель",
  testTitle: "Подтверждающий тест",
  retake: "Пересдать тест",
  doTask: "Пройти задание",
  upliftChip: (pct: number) => `+${pct}% вакансий`,
  pathTitle: "Путь к следующему грейду",
  upliftTitle: "Что подтвердить",
  upliftLead: (total: number) => `Вакансий под вашу профессию: ${total}.`,
  competitionsTitle: "Предстоящие события",
  competitionsLead: "Участие в соревновании подтверждает навыки лучше всего.",
  register: "Записаться",
  takeTest: "Пройти тест",
  testLead: (grade: string) => `Тест на грейд ${grade} подтвердит навыки и откроет следующий уровень.`,
  expired: "Срок грейда истекает: подтвердите его тестом.",
  validUntil: (date: string) => `Грейд действует до ${date}`,
  current: (grade: string) => `Сейчас: ${grade}`,
  nextGrade: (grade: string) => `Цель: ${grade}`,
  pointsNeeded: (n: number) => `не хватает ${n} балла(ов)`,
  gapCaption: "Навык, который просит рынок",
  extra: (n: number) => `+${n} вакансий`,
  salaryDelta: (n: string) => `в среднем на ${n} выше`,
  combo: (skills: string, pct: number) => `Вместе с ${skills}: +${pct}% вакансий`,
  noCompetitions: "Ближайших соревнований, подходящих под ваши навыки, нет.",
  skills: (list: string[]) => `Навыки: ${list.join(", ")}`,
  startsOn: (date: string) => `старт ${date}`,
};

export function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 403) return T.forbidden;
  return T.errorTitle;
}

/** Подсказка в карточке роста: способы подтверждения. */
export function confirmHint(list: UpliftConfirm[], date: (iso: string) => string): string {
  const parts = list.map((c) => {
    if (c.kind === "test") return c.minutes ? `тест, около ${c.minutes} мин` : "тест";
    if (c.kind === "github") return "ссылка на GitHub";
    const when = c.start_date ? `, ${date(c.start_date)}` : "";
    return `соревнование ФСП${c.title ? ` «${c.title}»` : ""}${when}`;
  });
  return parts.length ? `Подтвердить: ${parts.join("; ")}` : "";
}
