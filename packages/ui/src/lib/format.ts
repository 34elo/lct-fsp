const NBSP = " ";

const num = (n: number) => Math.round(n).toLocaleString("ru-RU").replace(/\s/g, NBSP);

/** Рубли с неразрывными пробелами: 230000 → «230 000 ₽». */
export function formatRub(n: number): string {
  return `${num(n)}${NBSP}₽`;
}

/** Вилка: «200 000 – 250 000 ₽» (знак валюты один, в конце). */
export function formatRubRange(from: number, to: number): string {
  return `${num(from)}${NBSP}–${NBSP}${num(to)}${NBSP}₽`;
}

/** Компактная вилка для канбана: «200–250 тыс. ₽». */
export function formatRubRangeShort(from: number, to: number): string {
  const k = (n: number) => String(Math.round(n / 1000));
  return `${k(from)}–${k(to)}${NBSP}тыс.${NBSP}₽`;
}
