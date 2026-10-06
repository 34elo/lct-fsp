/** Тексты админки ФСП: дашборд (F1) и модерация (F3). */
export const T = {
  dash: {
    title: "Дашборд ФСП",
    lead: "Воронка кандидатов: регистрация, тест, категория, приглашение. Значения меньше порога скрыты, чтобы не раскрывать отдельных людей.",
    period: (days: number) => `За ${days} дн.`,
    daysLabel: "Период",
    funnel: "Воронка",
    ofRegistered: (pct: number) => `${pct}% от регистраций`,
    ofPrevious: (pct: number) => `${pct}% от предыдущего шага`,
    fspShare: "Доля кандидатов с ФСП",
    navigator: "Навигатор → соревнование",
    ratio: (count: number | null, of: number | null, pct: number | null) =>
      `${count ?? "—"}${of !== null ? ` из ${of}` : ""}${pct !== null ? ` (${pct}%)` : ""}`,
    hiddenHint: (min: number) => `Меньше ${min} человек: значение скрыто.`,
  },
  hidden: "< 5",
  mod: {
    title: "Модерация",
    companies: "Компании",
    complaints: "Жалобы",
    statusAll: "Все",
    noCompanies: "Компаний с таким статусом нет.",
    noComplaints: "Жалоб с таким статусом нет.",
    verify: "Подтвердить",
    reject: "Отклонить",
    resolve: "Принять",
    dismiss: "Отклонить жалобу",
    inn: "ИНН",
    offer: "оффер",
    company: "Компания",
    error: "Не удалось выполнить действие. Попробуйте ещё раз.",
  },
  companyStatus: { pending: "На проверке", verified: "Подтверждена", rejected: "Отклонена", blocked: "Заблокирована" } as Record<string, string>,
  complaintStatus: { open: "Открыта", resolved: "Принята", dismissed: "Отклонена" } as Record<string, string>,
};

/** Скрытая ячейка (count = null или hidden) показывается как «< 5». */
export function cell(count: number | null, hidden: boolean): string {
  return hidden || count === null ? T.hidden : String(count);
}
