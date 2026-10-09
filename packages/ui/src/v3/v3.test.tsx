import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "../primitives/button";
import { Tabs, TabsTrigger } from "../primitives/overlay";
import { Combobox, MultiSelect, Select, type ComboOption } from "./combobox";
import { Avatar, InfoTip, Markdown, MarkdownEditor, ScrollTabs, initials } from "./content";
import { NumberInput, ProfessionInput, SalaryRangeInput, SkillInput, groupDigits, localSkillSource, parseDigits, type SalaryRangeValue, type SkillValue } from "./inputs";
import { SkeletonCard, SkeletonChart, SkeletonLine, SkeletonProfile, SkeletonTable } from "./skeletons";

const GRADES: ComboOption[] = [
  { value: "junior", label: "Junior" },
  { value: "middle", label: "Middle", disabled: true },
  { value: "senior", label: "Senior" },
];

function SingleHarness({ onChange = () => {}, searchable }: { onChange?: (v: string | null) => void; searchable?: boolean }) {
  const [v, setV] = useState<string | null>(null);
  return (
    <Select
      aria-label="Грейд"
      value={v}
      searchable={searchable}
      onChange={(x) => {
        setV(x);
        onChange(x);
      }}
      options={GRADES}
    />
  );
}

const box = () => screen.getByRole("combobox");
const key = (k: string) => fireEvent.keyDown(box(), { key: k });

describe("Select — клавиатура", () => {
  it("↓ открывает, ↓ пропускает недоступный вариант, Enter выбирает и закрывает", () => {
    const pick = vi.fn();
    render(<SingleHarness onChange={pick} />);
    expect(box()).toHaveAttribute("aria-expanded", "false");
    key("ArrowDown");
    expect(box()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    // активен первый — Junior
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-0$/);
    key("ArrowDown"); // Middle недоступен → Senior
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-2$/);
    key("Enter");
    expect(pick).toHaveBeenCalledWith("senior");
    expect(box()).toHaveAttribute("aria-expanded", "false");
    expect(box()).toHaveTextContent("Senior");
  });

  it("↑ на первом остаётся, End/Home — края, Esc закрывает без выбора", () => {
    const pick = vi.fn();
    render(<SingleHarness onChange={pick} />);
    key("Enter");
    key("ArrowUp");
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-0$/);
    key("End");
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-2$/);
    key("Home");
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-0$/);
    key("Escape");
    expect(box()).toHaveAttribute("aria-expanded", "false");
    expect(pick).not.toHaveBeenCalled();
  });

  it("пробел открывает и выбирает; клик по варианту выбирает", () => {
    const pick = vi.fn();
    render(<SingleHarness onChange={pick} />);
    key(" ");
    key(" ");
    expect(pick).toHaveBeenLastCalledWith("junior");
    fireEvent.click(box());
    fireEvent.click(screen.getByRole("option", { name: "Senior" }));
    expect(pick).toHaveBeenLastCalledWith("senior");
  });

  it("выбранный вариант помечен aria-selected", () => {
    render(<Select aria-label="Грейд" value="senior" onChange={() => {}} options={GRADES} />);
    key("ArrowDown");
    expect(screen.getByRole("option", { name: "Senior" })).toHaveAttribute("aria-selected", "true");
    expect(box().getAttribute("aria-activedescendant")).toMatch(/opt-2$/);
  });

  it("с поиском: ввод фильтрует, Enter берёт первый найденный", () => {
    const pick = vi.fn();
    render(<SingleHarness onChange={pick} searchable />);
    fireEvent.change(box(), { target: { value: "sen" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    key("Enter");
    expect(pick).toHaveBeenCalledWith("senior");
  });

  it("ничего не найдено — пустой текст", () => {
    render(<SingleHarness searchable />);
    fireEvent.change(box(), { target: { value: "zzz" } });
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("disabled не открывается", () => {
    render(<Select aria-label="x" disabled value={null} onChange={() => {}} options={GRADES} />);
    key("ArrowDown");
    expect(box()).toHaveAttribute("aria-expanded", "false");
  });

  it("Escape в открытом списке не всплывает (диалог не закрывается)", () => {
    const outer = vi.fn((e: { key: string }) => e.key);
    render(
      <div onKeyDown={outer}>
        <SingleHarness />
      </div>,
    );
    key("ArrowDown");
    key("Escape");
    expect(outer.mock.calls.map(([e]) => (e as { key: string }).key)).not.toContain("Escape");
  });
});

describe("Combobox — мультивыбор", () => {
  function Multi({ spy }: { spy?: (v: string[]) => void }) {
    const [v, setV] = useState<string[]>(["office"]);
    return (
      <MultiSelect
        aria-label="Формат"
        value={v}
        onChange={(x) => {
          setV(x);
          spy?.(x);
        }}
        options={[
          { value: "office", label: "Офис" },
          { value: "hybrid", label: "Гибрид" },
          { value: "remote", label: "Удалённо" },
        ]}
      />
    );
  }

  it("чипсы, Enter добавляет и оставляет список открытым, Backspace убирает последний", () => {
    const spy = vi.fn();
    render(<Multi spy={spy} />);
    expect(screen.getByText("Офис")).toBeInTheDocument();
    fireEvent.change(box(), { target: { value: "уд" } });
    key("Enter");
    expect(spy).toHaveBeenLastCalledWith(["office", "remote"]);
    expect(box()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toHaveAttribute("aria-multiselectable", "true");
    key("Backspace");
    expect(spy).toHaveBeenLastCalledWith(["office"]);
  });

  it("повторный выбор снимает значение; крестик чипса убирает", () => {
    const spy = vi.fn();
    render(<Multi spy={spy} />);
    key("ArrowDown");
    key("Enter"); // активен выбранный «Офис» → снять
    expect(spy).toHaveBeenLastCalledWith([]);
    key("Enter");
    expect(spy).toHaveBeenLastCalledWith(["office"]);
    fireEvent.click(screen.getByRole("button", { name: "Убрать Офис" }));
    expect(spy).toHaveBeenLastCalledWith([]);
  });
});

describe("SkillInput", () => {
  const source = localSkillSource([
    { slug: "python", name: "Python" },
    { slug: "postgresql", name: "PostgreSQL" },
    { slug: "java", name: "Java" },
    { slug: "javascript", name: "JavaScript" },
  ]);

  function Harness({ spy }: { spy: (v: SkillValue[]) => void }) {
    const [v, setV] = useState<SkillValue[]>([]);
    return (
      <SkillInput
        value={v}
        suggest={source}
        onChange={(x) => {
          setV(x);
          spy(x);
        }}
      />
    );
  }

  it("подсказки асинхронно, выбор даёт slug и подпись", async () => {
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    fireEvent.change(box(), { target: { value: "jav" } });
    await screen.findByRole("option", { name: "Java" });
    expect(screen.getByRole("option", { name: "JavaScript" })).toBeInTheDocument();
    key("Enter");
    expect(spy).toHaveBeenLastCalledWith([{ value: "java", label: "Java" }]);
  });

  it("своё значение помечено «новый»", async () => {
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    fireEvent.change(box(), { target: { value: "Airflow" } });
    const opt = await screen.findByRole("option", { name: /Добавить «Airflow»/ });
    expect(opt).toHaveAttribute("data-new", "true");
    fireEvent.click(opt);
    expect(spy).toHaveBeenLastCalledWith([{ value: "Airflow", label: "Airflow", isNew: true }]);
    expect(screen.getByText("новый")).toBeInTheDocument();
  });

  it("устаревший запрос отменяется", async () => {
    const seen: string[] = [];
    const aborted: string[] = [];
    const slow = (q: string, signal: AbortSignal) => {
      seen.push(q);
      signal.addEventListener("abort", () => aborted.push(q));
      return Promise.resolve([{ slug: q, name: q }]);
    };
    render(<SkillInput value={[]} onChange={() => {}} suggest={slow} debounceMs={0} />);
    fireEvent.change(box(), { target: { value: "a" } });
    await waitFor(() => expect(seen).toContain("a"));
    fireEvent.change(box(), { target: { value: "ab" } });
    await waitFor(() => expect(seen).toContain("ab"));
    expect(aborted).toContain("a");
  });
});

describe("ProfessionInput", () => {
  it("выбор профессии", () => {
    const pick = vi.fn();
    render(<ProfessionInput value={null} onChange={pick} professions={[{ slug: "backend", title: "Backend" }, { slug: "qa", title: "QA" }]} />);
    key("ArrowDown");
    key("ArrowDown");
    key("Enter");
    expect(pick).toHaveBeenCalledWith("qa");
  });

  it("с suggest варианты приходят с сервера, выбранная подпись берётся из professions", async () => {
    const pick = vi.fn();
    const suggest = vi.fn(async (q: string) => (q ? [{ slug: "ghost", title: "Призрак" }] : []));
    render(<ProfessionInput value={null} onChange={pick} professions={[{ slug: "backend", title: "Backend" }]} suggest={suggest} />);
    fireEvent.change(box(), { target: { value: "призр" } });
    await screen.findByRole("option", { name: "Призрак" });
    key("Enter");
    expect(pick).toHaveBeenCalledWith("ghost");
    expect(suggest).toHaveBeenCalledWith("призр", expect.anything());
  });
});

describe("NumberInput и SalaryRangeInput", () => {
  it("разряды и разбор", () => {
    expect(groupDigits(1234567)).toBe("1 234 567");
    expect(parseDigits("12 000 ₽")).toBe(12000);
    expect(parseDigits("")).toBeNull();
    expect(parseDigits("-5", true)).toBe(-5);
  });

  function Num({ spy }: { spy: (v: number | null) => void }) {
    const [v, setV] = useState<number | null>(3);
    return (
      <NumberInput
        aria-label="Опыт"
        value={v}
        min={0}
        max={5}
        onChange={(x) => {
          setV(x);
          spy(x);
        }}
      />
    );
  }

  it("текстовое поле без type=number, кнопки и стрелки — шаг в пределах", () => {
    const spy = vi.fn();
    render(<Num spy={spy} />);
    const input = screen.getByRole("textbox", { name: "Опыт" });
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("inputmode", "numeric");
    fireEvent.click(screen.getByRole("button", { name: "Больше" }));
    expect(spy).toHaveBeenLastCalledWith(4);
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(spy).toHaveBeenLastCalledWith(5);
    expect(screen.getByRole("button", { name: "Больше" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "9x" } });
    fireEvent.blur(input);
    expect(spy).toHaveBeenLastCalledWith(5);
    expect(input).toHaveValue("5");
  });

  it("вилка форматирует ₽ и помечает «от > до»", () => {
    function H() {
      const [v, setV] = useState<SalaryRangeValue>({ from: null, to: null });
      return <SalaryRangeInput value={v} onChange={setV} fromTestId="f" toTestId="t" />;
    }
    render(<H />);
    fireEvent.change(screen.getByTestId("f"), { target: { value: "250000" } });
    expect(screen.getByTestId("f")).toHaveValue("250 000");
    fireEvent.change(screen.getByTestId("t"), { target: { value: "100000" } });
    expect(screen.getByTestId("f")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("₽")).toHaveLength(2);
    expect(screen.getAllByRole("slider")).toHaveLength(2);
  });
});

describe("InfoTip, Markdown, ScrollTabs, Avatar, Button danger", () => {
  it("InfoTip открывается по нажатию", async () => {
    render(<InfoTip label="Что такое доверие">Насколько подтверждён навык.</InfoTip>);
    fireEvent.click(screen.getByRole("button", { name: "Что такое доверие" }));
    expect(await screen.findByText("Насколько подтверждён навык.")).toBeInTheDocument();
  });

  it("Markdown: таблица GFM в обёртке с прокруткой, HTML не исполняется", () => {
    const { container } = render(<Markdown>{"| a | b |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script><b>x</b>"}</Markdown>);
    expect(container.querySelector("table")).toBeInTheDocument();
    expect(container.querySelector("table")!.parentElement).toHaveClass("overflow-x-auto");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("MarkdownEditor: правка и просмотр", () => {
    function H() {
      const [v, setV] = useState("");
      return <MarkdownEditor value={v} onChange={setV} aria-label="Условие" data-testid="ed" />;
    }
    render(<H />);
    fireEvent.change(screen.getByTestId("ed"), { target: { value: "**жирно**" } });
    fireEvent.click(screen.getByRole("radio", { name: "Просмотр" }));
    expect(screen.getByTestId("ed-preview").querySelector("strong")).toHaveTextContent("жирно");
  });

  it("ScrollTabs: горизонтальная прокрутка без вертикальной", () => {
    render(
      <Tabs defaultValue="a">
        <ScrollTabs aria-label="Вкладки">
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
        </ScrollTabs>
      </Tabs>,
    );
    const list = screen.getByRole("tablist");
    expect(list).toHaveClass("overflow-x-auto", "overflow-y-hidden", "flex-nowrap");
  });

  it("Avatar: инициалы и запасной вариант при битой картинке", () => {
    expect(initials("Анна Смирнова")).toBe("АС");
    expect(initials("backend")).toBe("B");
    expect(initials("")).toBe("?");
    const { container } = render(<Avatar name="Илья Петров" src="/x.png" />);
    fireEvent.error(container.querySelector("img")!);
    expect(screen.getByRole("img", { name: "Илья Петров" })).toHaveTextContent("ИП");
  });

  it("Button danger — красный контур", () => {
    render(<Button variant="danger">Выйти</Button>);
    expect(screen.getByRole("button", { name: "Выйти" })).toHaveClass("text-error");
  });
});

describe("Скелетоны-пресеты", () => {
  it("каждый пресет — одна область «загрузка», полосы скрыты от скринридера", () => {
    for (const el of [<SkeletonLine lines={3} />, <SkeletonCard />, <SkeletonTable rows={2} cols={3} />, <SkeletonChart />, <SkeletonProfile />]) {
      const { unmount, container } = render(el);
      expect(screen.getAllByRole("status")).toHaveLength(1);
      expect(container.querySelectorAll(".skl").length).toBeGreaterThan(1);
      unmount();
    }
  });
});

it("Combobox: асинхронный источник показывает «Ищем…» до ответа", async () => {
  let resolve: (v: ComboOption[]) => void = () => {};
  const load = () => new Promise<ComboOption[]>((r) => (resolve = r));
  render(<Combobox aria-label="x" value={null} onChange={() => {}} loadOptions={load} debounceMs={0} />);
  key("ArrowDown");
  expect(await screen.findByText("Ищем…")).toBeInTheDocument();
  await act(async () => resolve([{ value: "a", label: "Альфа" }]));
  expect(screen.getByRole("option", { name: "Альфа" })).toBeInTheDocument();
});
