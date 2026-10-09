import { useState, type ReactNode } from "react";

import {
  Avatar,
  Button,
  Combobox,
  Field,
  InfoTip,
  Markdown,
  MarkdownEditor,
  MultiSelect,
  NumberInput,
  Roadmap,
  ProfessionInput,
  SalaryRangeInput,
  ScrollTabs,
  Select,
  SkeletonCard,
  SkeletonChart,
  SkeletonLine,
  SkeletonProfile,
  SkeletonTable,
  SkillInput,
  Tabs,
  TabsContent,
  TabsTrigger,
  Term,
  ThemeScope,
  localSkillSource,
  type SalaryRangeValue,
  type SkillValue,
} from "../src";

const PROFESSIONS = [
  { slug: "backend", title: "Backend-разработчик" },
  { slug: "frontend", title: "Frontend-разработчик" },
  { slug: "data_analyst", title: "Аналитик данных" },
  { slug: "ml_engineer", title: "ML-инженер" },
  { slug: "ai_engineer", title: "AI Engineer" },
  { slug: "qa", title: "Тестировщик" },
  { slug: "devops", title: "DevOps-инженер" },
  { slug: "mobile", title: "Мобильный разработчик" },
];
const SKILLS = ["Python", "SQL", "PostgreSQL", "FastAPI", "Django", "Docker", "Kubernetes", "React", "TypeScript", "Go", "Java", "JavaScript", "C", "C#", "Redis", "Kafka"].map((n) => ({
  slug: n.toLowerCase().replace(/[^a-z0-9#]+/g, "-"),
  name: n,
}));
const slowSource = (() => {
  const local = localSkillSource(SKILLS);
  return (q: string, signal: AbortSignal) => new Promise<Awaited<ReturnType<typeof local>>>((ok) => setTimeout(() => !signal.aborted && local(q, signal).then(ok), 300));
})();
const MD = `**Условие.** Найдите медиану по столбцу \`salary\`.

| Грейд | Вилка, ₽ | Кандидатов |
|---|--:|--:|
| Junior | 80 000 – 140 000 | 412 |
| Middle | 160 000 – 260 000 | 287 |
| Senior | 280 000 – 420 000 | 96 |

- [x] таблицы GFM
- [ ] ~~HTML~~ не исполняется

\`\`\`python
print(sorted(xs)[len(xs) // 2])
\`\`\``;

function Cell({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="lbl text-muted">{name}</span>
      {children}
    </div>
  );
}

function Controls() {
  const [grade, setGrade] = useState<string | null>("middle");
  const [prof, setProf] = useState<string | null>(null);
  const [many, setMany] = useState<string[]>(["remote"]);
  const [combo, setCombo] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillValue[]>([
    { value: "python", label: "Python" },
    { value: "Airflow", label: "Airflow", isNew: true },
  ]);
  const [num, setNum] = useState<number | null>(3);
  const [salary, setSalary] = useState<SalaryRangeValue>({ from: 180_000, to: 260_000 });
  const [text, setText] = useState(MD);
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Cell name="Select">
          <Select
            aria-label="Грейд"
            value={grade}
            onChange={setGrade}
            options={[
              { value: "junior", label: "Junior" },
              { value: "middle", label: "Middle" },
              { value: "senior", label: "Senior" },
            ]}
          />
        </Cell>
        <Cell name="Combobox (поиск, очистить)">
          <Combobox aria-label="Город" value={combo} onChange={setCombo} clearable placeholder="Город" options={["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург"].map((c) => ({ value: c, label: c }))} />
        </Cell>
        <Cell name="MultiSelect (чипсы)">
          <MultiSelect
            aria-label="Формат"
            value={many}
            onChange={setMany}
            searchable={false}
            options={[
              { value: "office", label: "Офис" },
              { value: "hybrid", label: "Гибрид" },
              { value: "remote", label: "Удалённо" },
            ]}
          />
        </Cell>
        <Cell name="ProfessionInput">
          <ProfessionInput value={prof} onChange={setProf} professions={PROFESSIONS} clearable />
        </Cell>
        <Cell name="SkillInput (асинхронно, «новый»)">
          <SkillInput value={skills} onChange={setSkills} suggest={slowSource} />
        </Cell>
        <Cell name="NumberInput">
          <NumberInput aria-label="Лет опыта" value={num} onChange={setNum} min={0} max={40} suffix="лет" />
        </Cell>
        <Cell name="Field + Select с ошибкой">
          <Field label="Профессия" error="Выберите профессию">
            <Select value={null} onChange={() => {}} options={PROFESSIONS.map((p) => ({ value: p.slug, label: p.title }))} />
          </Field>
        </Cell>
        <Cell name="Disabled">
          <Select disabled value="a" onChange={() => {}} options={[{ value: "a", label: "Недоступно" }]} aria-label="Недоступно" />
        </Cell>
      </div>
      <Cell name="SalaryRangeInput">
        <SalaryRangeInput value={salary} onChange={setSalary} max={600_000} />
      </Cell>
      <Cell name="InfoTip">
        <p className="text-14">
          <Term tip="Насколько подтверждён навык: ○○○○ — только заявлен, ●●●● — подтверждён тестом и ФСП.">Доверие</Term> · рядом с заголовком{" "}
          <InfoTip title="Категория">Профессия × грейд, которую дал тест.</InfoTip>
        </p>
      </Cell>
      <Cell name="Button danger">
        <div className="flex flex-wrap gap-2">
          <Button variant="danger">Выйти</Button>
          <Button variant="danger" size="sm">
            Удалить
          </Button>
        </div>
      </Cell>
      <Cell name="Avatar">
        <div className="flex items-center gap-3">
          <Avatar name="Анна Смирнова" size={48} />
          <Avatar name="Backend #4821" />
          <Avatar name="Илья" size={28} />
          <Avatar name="Битая ссылка" src="/nope.png" />
        </div>
      </Cell>
      <Cell name="ScrollTabs">
        <Tabs defaultValue="t1" className="max-w-[340px]">
          <ScrollTabs aria-label="Профиль">
            {["Обзор", "Навыки", "Граф доказательств", "Резюме и данные", "ФСП", "Задания", "Настройки"].map((t, i) => (
              <TabsTrigger key={t} value={`t${i + 1}`}>
                {t}
              </TabsTrigger>
            ))}
          </ScrollTabs>
          <TabsContent value="t1" className="pt-3 text-14 text-muted">
            Листается вбок, вертикальной прокрутки нет.
          </TabsContent>
        </Tabs>
      </Cell>
      <div className="grid gap-4 lg:grid-cols-2">
        <Cell name="MarkdownEditor">
          <MarkdownEditor value={text} onChange={setText} aria-label="Условие" maxLength={4000} />
        </Cell>
        <Cell name="Markdown">
          <Markdown>{text}</Markdown>
        </Cell>
      </div>
      <Cell name="Roadmap">
        <Roadmap
          steps={[
            { id: "c", kind: "current", state: "done", eyebrow: "Сейчас", title: "Junior+" },
            { id: "d", kind: "skill", state: "current", eyebrow: "Навык", title: "Docker", uplift: "+64% вакансий", caption: "Навык, который просит рынок", actions: [{ label: "Пройти задание", href: "#" }, { label: "Соревнование ФСП", href: "#", external: true }] },
            { id: "t", kind: "test", state: "future", eyebrow: "Тест", title: "Тест на Middle", actions: [{ label: "Пройти тест", href: "#" }] },
            { id: "g", kind: "goal", state: "future", eyebrow: "Цель", title: "Middle" },
          ]}
        />
      </Cell>
      <Cell name="Скелетоны">
        <div className="grid gap-4 sm:grid-cols-2">
          <SkeletonLine lines={3} />
          <SkeletonCard />
          <SkeletonTable rows={3} />
          <SkeletonChart height={120} />
          <SkeletonProfile />
        </div>
      </Cell>
    </div>
  );
}

/** Доска E39-1: каждый контрол в светлой и тёмной теме рядом. */
export function V3Board() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {(["light", "dark"] as const).map((t) => (
        <ThemeScope key={t} dark={t === "dark"} light={t === "light"} className="rounded-xl border border-hairline p-5">
          <h2 className="mb-4 text-lg font-semibold">{t === "dark" ? "Тёмная тема" : "Светлая тема"}</h2>
          <Controls />
        </ThemeScope>
      ))}
    </div>
  );
}
