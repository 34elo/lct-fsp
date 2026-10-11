/** Разбор CSV для импорта в реестр ФСП: разделитель «,» или «;», кавычки, заголовок необязателен. */
export function parseCsv(text: string): string[][] {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const first = src.split(/\r?\n/, 1)[0] ?? "";
  const delim = (first.match(/;/g)?.length ?? 0) >= (first.match(/,/g)?.length ?? 0) && first.includes(";") ? ";" : ",";
  const rows: string[][] = [];
  let row: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]!;
    if (quoted) {
      if (ch === '"' && src[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delim) {
      row.push(cur.trim());
      cur = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(cur.trim());
      cur = "";
      if (row.some(Boolean)) rows.push(row);
      row = [];
    } else cur += ch;
  }
  row.push(cur.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}

/** Первая строка — заголовок, если в ней нет значения нужного вида (дата, число). */
export const dropHeader = (rows: string[][], looksLikeData: (r: string[]) => boolean): string[][] =>
  rows.length > 0 && !looksLikeData(rows[0]!) ? rows.slice(1) : rows;
