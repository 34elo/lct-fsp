import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
  Field,
  FieldInput,
  Input,
  NotFound,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Progress,
  RadioGroup,
  RadioGroupItem,
  SegmentedControl,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
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
  Toaster,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../index";

describe("Button", () => {
  it("по умолчанию type=button и роль button", () => {
    render(<Button>Отправить</Button>);
    expect(screen.getByRole("button", { name: "Отправить" })).toHaveAttribute("type", "button");
  });
  it("loading: aria-busy, блокировка и индикатор", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Отправка
      </Button>,
    );
    const b = screen.getByRole("button", { name: "Отправка" });
    expect(b).toHaveAttribute("aria-busy", "true");
    expect(b).toBeDisabled();
    fireEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });
  it("destructive и link рендерятся", () => {
    render(
      <>
        <Button variant="destructive">Удалить</Button>
        <Button variant="link">Ссылка</Button>
      </>,
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });
});

describe("Поля формы", () => {
  it("Field связывает подпись, подсказку и ошибку", () => {
    render(
      <Field label="Вилка" error="от > до">
        <FieldInput />
      </Field>,
    );
    const input = screen.getByLabelText("Вилка");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("от > до");
    expect(input.getAttribute("aria-describedby")).toBe(screen.getByRole("alert").id);
  });
  it("Field с подсказкой без ошибки", () => {
    render(
      <Field label="Город" hint="Необязательно">
        <FieldInput />
      </Field>,
    );
    expect(screen.getByLabelText("Город")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByText("Необязательно")).toBeInTheDocument();
  });
  it("Input loading помечен aria-busy", () => {
    render(<Input loading aria-label="Поиск" />);
    expect(screen.getByRole("textbox", { name: "Поиск" })).toHaveAttribute("aria-busy", "true");
  });
  it("Textarea", () => {
    render(<Textarea aria-label="О себе" disabled />);
    expect(screen.getByRole("textbox", { name: "О себе" })).toBeDisabled();
  });
  it("Checkbox переключается и отдаёт aria-checked", () => {
    render(<Checkbox aria-label="Согласен" />);
    const c = screen.getByRole("checkbox", { name: "Согласен" });
    expect(c).toHaveAttribute("aria-checked", "false");
    fireEvent.click(c);
    expect(c).toHaveAttribute("aria-checked", "true");
  });
  it("RadioGroup", () => {
    render(
      <RadioGroup defaultValue="a" aria-label="Режим">
        <RadioGroupItem value="a" aria-label="А" />
        <RadioGroupItem value="b" aria-label="Б" />
      </RadioGroup>,
    );
    expect(screen.getByRole("radiogroup", { name: "Режим" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "А" })).toHaveAttribute("aria-checked", "true");
  });
  it("Switch", () => {
    render(<Switch aria-label="Уведомления" />);
    const s = screen.getByRole("switch", { name: "Уведомления" });
    fireEvent.click(s);
    expect(s).toHaveAttribute("aria-checked", "true");
  });
  it("Slider: два ползунка с подписями", () => {
    render(<Slider defaultValue={[10, 90]} />);
    const thumbs = screen.getAllByRole("slider");
    expect(thumbs.map((t) => t.getAttribute("aria-label"))).toEqual(["От", "До"]);
    expect(thumbs[0]).toHaveAttribute("aria-valuenow", "10");
  });
});

describe("Навигация и оверлеи", () => {
  it("Tabs: роли, выбранная вкладка и счётчик", () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a" count={3}>
            Шорт-лист
          </TabsTrigger>
          <TabsTrigger value="b">Офферы</TabsTrigger>
        </TabsList>
        <TabsContent value="a">первая</TabsContent>
        <TabsContent value="b">вторая</TabsContent>
      </Tabs>,
    );
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Шорт-лист/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("первая");
  });
  it("SegmentedControl: выбор и aria-pressed/радио-роль", () => {
    const Demo = () => {
      const [v, setV] = useState("all");
      return (
        <SegmentedControl
          label="Уровень доверия"
          value={v}
          onValueChange={setV}
          options={[
            { value: "all", label: "Все" },
            { value: "verified", label: "Подтверждённые" },
          ]}
        />
      );
    };
    render(<Demo />);
    expect(screen.getByRole("radiogroup", { name: "Уровень доверия" })).toBeInTheDocument();
    const second = screen.getByRole("radio", { name: "Подтверждённые" });
    expect(screen.getByRole("radio", { name: "Все" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(second);
    expect(second).toHaveAttribute("aria-checked", "true");
  });
  it("Dialog: открывается, есть заголовок и кнопка закрытия", () => {
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Открыть</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Отозвать оффер?</DialogTitle>
          <DialogDescription>Действие нельзя отменить.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));
    const d = screen.getByRole("dialog", { name: "Отозвать оффер?" });
    expect(d).toHaveAccessibleDescription("Действие нельзя отменить.");
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeInTheDocument();
  });
  it("Sheet: нижний лист помечен data-side", () => {
    render(
      <Sheet>
        <SheetTrigger asChild>
          <Button>Фильтры</Button>
        </SheetTrigger>
        <SheetContent side="bottom">
          <SheetTitle>Фильтры</SheetTitle>
          <SheetDescription>Параметры поиска</SheetDescription>
        </SheetContent>
      </Sheet>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
    expect(screen.getByRole("dialog")).toHaveAttribute("data-side", "bottom");
  });
  it("Popover: триггер раскрывает содержимое, aria-expanded", () => {
    render(
      <Popover>
        <PopoverTrigger>Откуда навык</PopoverTrigger>
        <PopoverContent>Источники</PopoverContent>
      </Popover>,
    );
    const t = screen.getByRole("button", { name: "Откуда навык" });
    expect(t).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(t);
    expect(t).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Источники")).toBeInTheDocument();
  });
  it("Tooltip: подсказка с role=tooltip при фокусе", async () => {
    render(
      <TooltipProvider>
        <Tooltip defaultOpen>
          <TooltipTrigger>Грейд</TooltipTrigger>
          <TooltipContent>Предварительный</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Предварительный");
  });
  it("DropdownMenu: меню и пункт", () => {
    render(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>Действия</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Открыть профиль</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Открыть профиль" })).toBeInTheDocument();
  });
  it("Toaster монтируется", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeDefined();
  });
});

describe("Отображение", () => {
  it("Skeleton: role=status и aria-busy", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status", { name: "Загрузка" })).toHaveAttribute("aria-busy", "true");
  });
  it("Progress: progressbar с значением", () => {
    render(<Progress value={40} aria-label="Заполнено" />);
    const p = screen.getByRole("progressbar", { name: "Заполнено" });
    expect(p).toHaveAttribute("aria-valuenow", "40");
  });
  it("Separator декоративный и смысловой", () => {
    const { rerender } = render(<Separator data-testid="s" />);
    expect(screen.getByTestId("s")).toHaveAttribute("role", "none");
    rerender(<Separator decorative={false} data-testid="s" />);
    expect(screen.getByTestId("s")).toHaveAttribute("role", "separator");
  });
  it("Table: заголовки столбцов", () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Навык</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Python</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(screen.getByRole("columnheader", { name: "Навык" })).toHaveAttribute("scope", "col");
    expect(screen.getByRole("cell", { name: "Python" })).toBeInTheDocument();
  });
  it("Card и Badge", () => {
    render(
      <Card data-testid="c">
        <Badge variant="success">Сохранено</Badge>
      </Card>,
    );
    expect(screen.getByTestId("c")).toContainElement(screen.getByText("Сохранено"));
  });
});

describe("Состояния экрана", () => {
  it("EmptyState: заголовок и действие", () => {
    render(<EmptyState title="Пока пусто" description="Добавьте навык" action={<Button>Добавить</Button>} />);
    expect(screen.getByText("Пока пусто")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить" })).toBeInTheDocument();
  });
  it("ErrorState: role=alert и повтор", () => {
    const retry = vi.fn();
    render(<ErrorState onRetry={retry} description="Нет связи" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Не загрузилось");
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("NotFound: заголовок h1 и ссылка действия", () => {
    render(<NotFound action={<a href="/">На главную</a>} />);
    expect(screen.getByRole("heading", { level: 1, name: "Страница не найдена" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "На главную" })).toBeInTheDocument();
  });
});
