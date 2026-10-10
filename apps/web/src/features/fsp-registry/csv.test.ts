import { dropHeader, parseCsv } from "./csv";

test("разделитель «;» и «,», кавычки, BOM и пустые строки", () => {
  expect(parseCsv("﻿a;b;c\n\n1;2;3\r\n")).toEqual([["a", "b", "c"], ["1", "2", "3"]]);
  expect(parseCsv('x,"y, z",w')).toEqual([["x", "y, z", "w"]]);
  expect(parseCsv('"он ""сам""";2')).toEqual([['он "сам"', "2"]]);
});

test("заголовок отбрасывается, если строка не похожа на данные", () => {
  const rows = [["Название", "Дата"], ["Кубок", "2026-05-01"]];
  expect(dropHeader(rows, (r) => /^\d{4}-/.test(r[1] ?? ""))).toEqual([["Кубок", "2026-05-01"]]);
  expect(dropHeader(rows.slice(1), (r) => /^\d{4}-/.test(r[1] ?? ""))).toEqual([["Кубок", "2026-05-01"]]);
});
