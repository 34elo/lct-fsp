import { useState, type ReactNode } from "react";

import {
  AccountMenu,
  ActivityHeatmap,
  AppBar,
  CandidateCardV2,
  CategoryCard,
  Chips,
  CircuitLine,
  CodeLines,
  EmptyState,
  ErrorBlock,
  ErrorState,
  FeedEvent,
  FeedList,
  GradeScale,
  H1,
  H2,
  MatchRing,
  MetricTile,
  OfferCardV2,
  OptionRow,
  QueryBar,
  ScatterPlot,
  SkillConstellation,
  SkillTag,
  Skeleton,
  StatusTag,
  Switch,
  TabBar,
  Tabs,
  TabsList,
  TabsTrigger,
  TaskHeader,
  ThemeScope,
  TrustDots,
  TypeBar,
} from "../src";
import { V2_CANDIDATE, V2_CATEGORY, V2_CONSTELLATION, V2_FEED, V2_HEATMAP, V2_OFFER, V2_SCATTER, V2_TYPES } from "./data";

/* Доска v2 — повторяет docs/design/v2/screens/v2_components.html (E38-0). */

function Cell({ title, span, fromPackage, children }: { title: string; span: 3 | 4 | 5 | 6 | 12; fromPackage?: boolean; children: ReactNode }) {
  const col = { 3: "lg:col-span-3", 4: "lg:col-span-4", 5: "lg:col-span-5", 6: "lg:col-span-6", 12: "lg:col-span-12" }[span];
  return (
    <section className={`col-span-12 flex min-w-0 flex-col gap-3 rounded-xl border border-hairline bg-card p-4 ${col}`}>
      <div className="flex items-center justify-between gap-2">
        <H2>{title}</H2>
        <StatusTag state={fromPackage ? "claimed" : "confirmed"}>{fromPackage ? "из пакета" : "новый"}</StatusTag>
      </div>
      {children}
    </section>
  );
}

const NAV = [
  { href: "#me", label: "Главная" },
  { href: "#test", label: "Тест и грейд" },
  { href: "#offers", label: "Приглашения", count: 3 },
  { href: "#profile", label: "Профиль" },
];

export function V2Board() {
  const [query, setQuery] = useState("Backend на Python, Middle, до 220 тыс., удалёнка");
  const [line, setLine] = useState(0);
  const [opt, setOpt] = useState(true);
  const [sw, setSw] = useState(true);
  const menu = [
    { label: "Настройки", active: true, onSelect: () => {} },
    { label: "Тема", hint: "светлая", onSelect: () => {} },
    { label: "Выйти", separatorBefore: true, onSelect: () => {} },
  ];
  return (
    <div className="grid gap-4">
      <div className="overflow-hidden rounded-xl border border-hairline">
        <AppBar className="static" items={NAV} isCurrent={(i) => i.href === "#me"} aside={<AccountMenu letter="А" items={menu} />} />
        <div className="relative h-[60px] md:hidden">
          <TabBar className="absolute" items={NAV} isCurrent={(i) => i.href === "#me"} />
        </div>
      </div>
      <div className="flex items-baseline gap-3">
        <H1>Новые компоненты</H1>
        <span className="text-13 text-muted">на существующих токенах</span>
      </div>
      <div className="grid grid-cols-12 items-start gap-4">
        <Cell title="MetricTile" span={4}>
          <MetricTile className="border-0 p-0" label="сила" value={64} trend={[8, 12, 10, 20, 18, 28, 32]} />
        </Cell>
        <Cell title="SkillConstellation" span={5}>
          <SkillConstellation nodes={V2_CONSTELLATION} />
        </Cell>
        <Cell title="ScatterPlot «Где ты среди своих»" span={3}>
          <ScatterPlot label="Где ты среди своих" points={V2_SCATTER} you={{ x: 64, y: 10 }} threshold={{ x: 72, label: "порог Middle" }} />
        </Cell>
        <Cell title="ActivityHeatmap" span={4}>
          <ActivityHeatmap label="Просмотры профиля по дням" values={V2_HEATMAP} />
        </Cell>
        <Cell title="GradeScale" span={4}>
          <GradeScale compact value={42} />
        </Cell>
        <Cell title="TypeBar с порогом" span={4}>
          <TypeBar threshold={55} items={V2_TYPES} />
        </Cell>
        <Cell title="CategoryCard" span={4}>
          <CategoryCard href="#v2" c={V2_CATEGORY} />
        </Cell>
        <Cell title="CandidateCard" span={4}>
          <CandidateCardV2 c={V2_CANDIDATE} onOpen={() => {}} />
        </Cell>
        <Cell title="FeedEvent" span={4}>
          <FeedList>
            {V2_FEED.map((e) => (
              <FeedEvent key={e.time} time={e.time}>
                {e.text}
              </FeedEvent>
            ))}
          </FeedList>
        </Cell>
        <Cell title="ErrorBlock" span={6}>
          <ErrorBlock
            skill="SQL"
            title="путаешь LEFT и INNER JOIN"
            code={"SELECT u.name, o.id\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id\nWHERE o.status = 'paid'"}
            marked={[3]}
            onExplain={() => {}}
          />
        </Cell>
        <Cell title="QueryBar" span={6}>
          <QueryBar value={query} onChange={setQuery} onSubmit={() => {}} />
        </Cell>
        <Cell title="MatchRing" span={3} fromPackage>
          <MatchRing value={92} size={56} />
        </Cell>
        <Cell title="TrustDots" span={3} fromPackage>
          <TrustDots level={3} />
        </Cell>
        <Cell title="SkillChip" span={3} fromPackage>
          <Chips>
            <SkillTag name="Python" level={3} />
            <SkillTag name="Git" level={0} state="claimed" />
          </Chips>
        </Cell>
        <Cell title="CircuitLine" span={3} fromPackage>
          <CircuitLine
            steps={[
              { id: "resume", label: "Резюме", state: "done" },
              { id: "test", label: "Тест", state: "current" },
              { id: "category", label: "Категория", state: "future" },
            ]}
          />
        </Cell>
        <Cell title="Switch" span={3}>
          <div className="flex items-center gap-3">
            <Switch checked={sw} onCheckedChange={setSw} aria-label="Показывать ФИО" />
            <Switch aria-label="Показывать регион" />
          </div>
        </Cell>
        <Cell title="OptionRow · choice / order / sjt" span={4}>
          <div className="flex flex-col gap-2">
            <OptionRow selected={opt} onClick={() => setOpt((v) => !v)}>
              LEFT JOIN
            </OptionRow>
            <OptionRow kind="order" index={2}>
              git commit
            </OptionRow>
          </div>
        </Cell>
        <Cell title="CodeLines · выбор строки" span={5}>
          <CodeLines lines={["def add(item, bucket=[]):", "    bucket.append(item)"]} selected={line} onSelect={setLine} />
        </Cell>
        <Cell title="TaskHeader" span={4}>
          <TaskHeader index={7} total={20} secondsLeft={161} />
        </Cell>
        <Cell title="OfferCard" span={4}>
          <OfferCardV2 compact className="border-0 p-0" o={V2_OFFER} />
        </Cell>
        <Cell title="Skeleton" span={4} fromPackage>
          <div className="flex flex-col gap-2">
            <Skeleton className="h-3.5 w-3/5" />
            <Skeleton className="h-3" />
          </div>
        </Cell>
        <Cell title="EmptyState" span={4} fromPackage>
          <EmptyState className="min-h-[100px] p-4" title="Пока пусто" />
        </Cell>
        <Cell title="ErrorState" span={4} fromPackage>
          <ErrorState className="p-3.5" />
        </Cell>
        <Cell title="Tabs · Dialog · Sheet · DropdownMenu · Input" span={4} fromPackage>
          <Tabs defaultValue="skills">
            <TabsList>
              <TabsTrigger value="skills">Навыки</TabsTrigger>
              <TabsTrigger value="fsp">ФСП</TabsTrigger>
            </TabsList>
          </Tabs>
        </Cell>
        <Cell title="Тёмная тема · .dark" span={4} fromPackage>
          <ThemeScope dark className="rounded-[10px] p-3">
            <SkillTag name="Python" level={3} />
          </ThemeScope>
        </Cell>
        <Cell title="GradeScale · экран результата" span={12}>
          <GradeScale value={42} error={5} />
        </Cell>
        <Cell title="OfferCard v2 · полная" span={12}>
          <OfferCardV2 o={V2_OFFER} actions={<StatusTag state="ok">кнопки — на экране</StatusTag>} />
        </Cell>
      </div>
    </div>
  );
}
