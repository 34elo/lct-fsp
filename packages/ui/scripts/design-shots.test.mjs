import { screenList } from "./design-shots.mjs";

test("список макетов: размеры из screens.json, иначе ширина из имени", () => {
  const meta = [{ file: "screens/v2_me__before_1440.html", width: 1440, height: 936 }];
  const list = screenList(["v2_me__before_1440.html", "v2_me__before_375.html", "notes.txt", "v2_components.html"], meta);
  expect(list.map((s) => [s.png, s.width, s.height])).toEqual([
    ["v2_components.png", 1440, 800],
    ["v2_me__before_1440.png", 1440, 936],
    ["v2_me__before_375.png", 375, 800],
  ]);
});
