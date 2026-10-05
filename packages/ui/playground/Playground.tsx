import { useEffect, useState, type ReactNode } from "react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  ConstellationAvatar,
  FspProtocol,
  GradeBadge,
  SectionLabel,
  TeamSignal,
  VerifiedMark,
  pseudonymLabel,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
  Field,
  FieldInput,
  Input,
  Logo,
  MatchRing,
  NotFound,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Progress,
  RadioGroup,
  RadioGroupItem,
  SegmentedControl,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
  SkillChip,
  Skeleton,
  Slider,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  ThemeScope,
  Toaster,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  TrustDots,
  toast,
  type TrustKind,
} from "../src";
import { DEMO_CANDIDATES, DEMO_FSP, DEMO_SKILLS, RADII, TEXT_SIZES, TOKEN_GROUPS } from "./data";

type Page = "tokens" | "base" | "brand";
const PAGES: { id: Page; title: string }[] = [
  { id: "tokens", title: "Токены" },
  { id: "base", title: "Базовые" },
  { id: "brand", title: "Фирменные" },
];
const KINDS: TrustKind[] = ["verified", "inferred", "adjacent", "claimed", "provisional"];

function readHash(): Page {
  const h = location.hash.replace("#", "");
  return PAGES.some((p) => p.id === h) ? (h as Page) : "tokens";
}

/** Тема: `?theme=dark` (для `pnpm shot`) или ключ `fsp-theme`, как в приложении. */
function readTheme(): boolean {
  const q = new URLSearchParams(location.search).get("theme");
  if (q) return q === "dark";
  try {
    return localStorage.getItem("fsp-theme") === "dark";
  } catch {
    return false;
  }
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-hairline bg-card p-5">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Tokens() {
  return (
    <div className="grid gap-5">
      {TOKEN_GROUPS.map((g) => (
        <Section key={g.title} title={g.title}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {g.tokens.map((t) => (
              <div key={t} className="flex flex-col gap-1.5">
                <div className="h-14 rounded-md border border-hairline" style={{ background: `var(--${t})` }} />
                <code className="font-mono text-xs text-muted">--{t}</code>
              </div>
            ))}
          </div>
        </Section>
      ))}
      <Section title="Шрифты">
        <p className="font-sans text-2xl">Onest — ФСП Карьера: доказанные навыки</p>
        <p className="font-mono text-base">JetBrains Mono — Backend #4821 · 275 000 ₽</p>
      </Section>
      <Section title="Шкала текста">
        <div className="grid gap-2">
          {TEXT_SIZES.map((n) => (
            <div key={n} className="flex items-baseline gap-4">
              <code className="w-12 font-mono text-xs text-muted">{n}</code>
              <span style={{ fontSize: `var(--fs-${n})` }}>Доказанные навыки · 275 000 ₽</span>
            </div>
          ))}
          <p className="lbl text-muted">Метка · mono 500 · 11 px · капс</p>
        </div>
      </Section>
      <Section title="Тени и фокус">
        <div className="flex flex-wrap gap-5">
          <div className="h-16 w-28 rounded-xl bg-card shadow-xs" />
          <div className="h-16 w-28 rounded-xl bg-card shadow-card" />
          <div className="h-16 w-28 rounded-xl" style={{ outline: "var(--focus)", outlineOffset: 2 }} />
        </div>
        <p className="mt-3 font-mono text-xs text-muted">--shadow-xs · --shadow-card · --focus</p>
      </Section>
      <Section title="ThemeScope dark">
        <ThemeScope dark className="rounded-xl border border-hairline p-4">
          <p className="lbl text-muted">Тёмная область</p>
          <Button variant="outline" size="sm">Outline</Button>
        </ThemeScope>
      </Section>
      <Section title="Радиусы">
        <div className="flex flex-wrap gap-4">
          {RADII.map((r) => (
            <div key={r} className="flex flex-col items-center gap-1.5">
              <div className="size-16 border border-brand bg-tint-50" style={{ borderRadius: `var(--radius-${r})` }} />
              <code className="font-mono text-xs text-muted">{r}</code>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="grid items-center gap-3 border-b border-hairline py-3 last:border-0 md:grid-cols-[9rem_1fr]">
      <span className="lbl text-muted">{name}</span>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

function Base() {
  const [trust, setTrust] = useState("all");
  const [sheet, setSheet] = useState<"bottom" | "right">("bottom");
  return (
    <TooltipProvider>
      <div className="grid gap-5">
        <Section title="Кнопка">
          <Row name="variant">
            {(["default", "outline", "ghost", "destructive", "link"] as const).map((v) => (
              <Button key={v} variant={v}>
                {v === "destructive" ? "Повторить" : "Отправить"}
              </Button>
            ))}
          </Row>
          <Row name="size">
            {(["sm", "md", "lg"] as const).map((size) => (
              <Button key={size} size={size}>
                Пригласить · {size}
              </Button>
            ))}
          </Row>
          <Row name="состояния">
            <Button disabled>Отправить</Button>
            <Button loading>Отправка</Button>
          </Row>
        </Section>

        <Section title="Поля">
          <Row name="Input">
            <Input placeholder="Значение" className="w-48" aria-label="Значение" />
            <Input disabled placeholder="Значение" className="w-48" aria-label="Недоступно" />
            <Input loading placeholder="..." className="w-48" aria-label="Загрузка" />
          </Row>
          <Row name="Field + error">
            <Field label="Вилка" error="от > до" className="w-56">
              <FieldInput defaultValue="от > до" />
            </Field>
            <Field label="Город" hint="Подсказка" className="w-56">
              <FieldInput placeholder="Подсказка" />
            </Field>
          </Row>
          <Row name="Textarea">
            <Textarea placeholder="О себе" className="w-80" aria-label="О себе" />
          </Row>
          <Row name="Select">
            <Select defaultValue="mid">
              <SelectTrigger className="w-48" aria-label="Грейд">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="jun">Junior</SelectItem>
                <SelectItem value="mid">Middle</SelectItem>
                <SelectItem value="sen">Senior</SelectItem>
              </SelectContent>
            </Select>
          </Row>
          <Row name="Выбор">
            <label className="flex items-center gap-2 text-14">
              <Checkbox defaultChecked /> Согласен
            </label>
            <label className="flex items-center gap-2 text-14">
              <Checkbox disabled /> Недоступно
            </label>
            <RadioGroup defaultValue="a" className="flex gap-4" aria-label="Режим">
              <label className="flex items-center gap-2 text-14">
                <RadioGroupItem value="a" /> Удалённо
              </label>
              <label className="flex items-center gap-2 text-14">
                <RadioGroupItem value="b" /> Офис
              </label>
            </RadioGroup>
            <Switch defaultChecked aria-label="Уведомления" />
            <Slider defaultValue={[40]} className="w-48" />
          </Row>
        </Section>

        <Section title="Навигация">
          <Row name="Tabs">
            <Tabs defaultValue="a" className="w-full">
              <TabsList>
                <TabsTrigger value="a" count={3}>
                  Шорт-лист
                </TabsTrigger>
                <TabsTrigger value="b" count={8}>
                  Офферы
                </TabsTrigger>
                <TabsTrigger value="c" disabled>
                  Архив
                </TabsTrigger>
              </TabsList>
              <TabsContent value="a" className="pt-3 text-14 text-muted">
                Кандидаты в шорт-листе
              </TabsContent>
              <TabsContent value="b" className="pt-3 text-14 text-muted">
                Отправленные офферы
              </TabsContent>
            </Tabs>
          </Row>
          <Row name="Segmented">
            <SegmentedControl
              label="Уровень доверия"
              value={trust}
              onValueChange={setTrust}
              options={[
                { value: "all", label: "Все" },
                { value: "inferred", label: "Выведенные" },
                { value: "verified", label: "Подтверждённые" },
              ]}
            />
          </Row>
        </Section>

        <Section title="Оверлеи">
          <Row name="Dialog">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline">Диалог</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogTitle>Отозвать оффер?</DialogTitle>
                <DialogDescription>Кандидат увидит статус «Отозван».</DialogDescription>
                <div className="mt-4 flex justify-end gap-2">
                  <DialogClose asChild>
                    <Button variant="ghost">Отмена</Button>
                  </DialogClose>
                  <Button variant="destructive">Отозвать</Button>
                </div>
              </DialogContent>
            </Dialog>
          </Row>
          <Row name="Sheet">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" onClick={() => setSheet("bottom")}>
                  Нижний лист
                </Button>
              </SheetTrigger>
              <SheetTrigger asChild>
                <Button variant="outline" onClick={() => setSheet("right")}>
                  Правая панель
                </Button>
              </SheetTrigger>
              <SheetContent side={sheet}>
                <SheetTitle>Фильтры</SheetTitle>
                <SheetDescription>Параметры поиска</SheetDescription>
              </SheetContent>
            </Sheet>
          </Row>
          <Row name="Popover">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline">Откуда навык</Button>
              </PopoverTrigger>
              <PopoverContent>Источники: результат ФСП, репозиторий, тест.</PopoverContent>
            </Popover>
          </Row>
          <Row name="Tooltip">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost">Грейд предварительный</Button>
              </TooltipTrigger>
              <TooltipContent>Нужен тест для подтверждения</TooltipContent>
            </Tooltip>
          </Row>
          <Row name="DropdownMenu">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">Действия</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem>Открыть профиль</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem>В шорт-лист</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </Row>
          <Row name="Toast">
            <Button variant="outline" onClick={() => toast.success("Сохранено")}>
              Сохранено
            </Button>
            <Button variant="outline" onClick={() => toast.error("Ошибка сети")}>
              Ошибка сети
            </Button>
            <Toaster />
          </Row>
        </Section>

        <Section title="Отображение">
          <Row name="Badge">
            <Badge>FastAPI</Badge>
            <Badge variant="muted">muted</Badge>
            <Badge variant="success">Сохранено</Badge>
            <Badge variant="warning">Предварительно</Badge>
            <Badge variant="error">Ошибка</Badge>
            <Badge variant="dashed">FastAPI</Badge>
          </Row>
          <Row name="Skeleton">
            <Skeleton className="h-16 w-48" />
            <Skeleton className="h-4 w-32" />
          </Row>
          <Row name="Progress">
            <Progress value={65} aria-label="Заполнено" className="w-64" />
          </Row>
          <Row name="Separator">
            <Separator />
          </Row>
          <Row name="Card">
            <Card className="w-56">
              <CardHeader>
                <CardTitle>Backend #4821</CardTitle>
              </CardHeader>
              <CardContent className="text-14 text-muted">Middle · Python</CardContent>
            </Card>
          </Row>
          <Row name="Table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Навык</TableHead>
                  <TableHead>Доверие</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>Python</TableCell>
                  <TableCell>
                    <TrustDots level={4} kind="verified" />
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Docker</TableCell>
                  <TableCell>
                    <TrustDots level={2} kind="claimed" />
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Row>
        </Section>

        <Section title="Пусто, ошибка, 404">
          <div className="grid gap-4 md:grid-cols-2">
            <EmptyState title="Пока пусто" description="Добавьте первый навык." action={<Button size="sm">Добавить</Button>} />
            <ErrorState description="Не удалось получить данные." onRetry={() => undefined} />
          </div>
          <NotFound action={<Button variant="outline">На главную</Button>} />
        </Section>
      </div>
    </TooltipProvider>
  );
}

function Brand() {
  return (
    <div className="grid gap-5">
      <Section title="Logo">
        <div className="flex flex-wrap items-center gap-6">
          <Logo />
          <Logo mark />
        </div>
      </Section>
      <Section title="TrustDots">
        <div className="grid gap-2">
          {KINDS.map((k) => (
            <div key={k} className="flex flex-wrap items-center gap-3">
              <code className="w-28 font-mono text-xs text-muted">{k}</code>
              {([1, 2, 3, 4] as const).map((l) => (
                <TrustDots key={l} level={l} kind={k} />
              ))}
            </div>
          ))}
        </div>
      </Section>
      <Section title="SkillChip">
        <div className="flex flex-wrap gap-2">
          {DEMO_SKILLS.map((s) => (
            <SkillChip key={s.name} name={s.name} level={s.level} variant={s.variant} />
          ))}
        </div>
      </Section>
      <Section title="TrustDots с поповером «Откуда навык»">
        <div className="flex flex-wrap items-center gap-4">
          <SkillChip
            name="FastAPI"
            level={3}
            sources={[
              { title: "Код на GitHub", detail: "6 репозиториев с FastAPI, в двух есть тесты", strength: "strong", date: "12 сен 2026" },
              { title: "Адаптивный тест · Python web", detail: "Уровень выше среднего, 18 вопросов", strength: "medium", date: "28 сен 2026" },
              { title: "Указано в резюме", detail: "Не засчитывается в уровень", strength: "none", date: "01 окт 2026" },
            ]}
          />
          <SkillChip name="Kubernetes" level={1} variant="provisional" isNew />
        </div>
      </Section>
      <Section title="GradeBadge">
        <div className="flex flex-wrap items-center gap-3">
          <GradeBadge grade="Middle" role="Backend" stack="Python" />
          <GradeBadge grade="Junior+" role="Backend" stack="Python" preliminary hint="Данных пока мало: нужен тест" />
        </div>
      </Section>
      <Section title="FspProtocol и VerifiedMark">
        <div className="grid gap-3">
          <VerifiedMark />
          <FspProtocol results={DEMO_FSP} />
          <FspProtocol results={[]} />
        </div>
      </Section>
      <Section title="TeamSignal и SectionLabel">
        <div className="grid gap-3">
          <SectionLabel>Командные сигналы</SectionLabel>
          <TeamSignal name="Лидерство" strength="strong" fact="капитан на 2 соревнованиях ФСП" />
          <TeamSignal name="Работа в команде" strength="medium" fact="3 командных соревнования, общий репозиторий с 4 участниками" />
          <TeamSignal name="коммуникабельный" claimed />
        </div>
      </Section>
      <Section title="ConstellationAvatar и MatchRing">
        <div className="mb-3 flex items-end gap-3">
          <ConstellationAvatar seed={pseudonymLabel("backend", 4821)} size={48} signalNode />
          <ConstellationAvatar seed={pseudonymLabel("backend", 1307)} size={32} />
          <ConstellationAvatar seed="Backend #5" size={24} />
        </div>
        <div className="grid gap-3">
          {DEMO_CANDIDATES.map((c) => (
            <div key={c.pseudo} className="flex items-center gap-4 rounded-lg border border-hairline p-3">
              <ConstellationAvatar seed={c.pseudo} />
              <div className="min-w-0 flex-1">
                <b className="font-mono">{c.pseudo}</b>
                <p className="text-sm text-muted">
                  {c.title} · {c.note}
                </p>
              </div>
              <MatchRing value={c.match} />
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

export function Playground() {
  const [page, setPage] = useState<Page>(readHash);
  const [dark, setDark] = useState(readTheme);

  useEffect(() => {
    const on = () => setPage(readHash());
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-bold">@fsp/ui</h1>
        <nav className="flex gap-1" aria-label="Разделы">
          {PAGES.map((p) => (
            <a
              key={p.id}
              href={`#${p.id}`}
              aria-current={page === p.id ? "page" : undefined}
              className="rounded-md px-3 py-1.5 text-sm font-medium hover:bg-tint-50 aria-[current=page]:bg-tint-100"
            >
              {p.title}
            </a>
          ))}
        </nav>
        <Button variant="outline" size="sm" onClick={() => setDark((d) => !d)} aria-pressed={dark}>
          {dark ? "Светлая тема" : "Тёмная тема"}
        </Button>
      </header>
      {page === "tokens" && <Tokens />}
      {page === "base" && <Base />}
      {page === "brand" && <Brand />}
    </div>
  );
}
