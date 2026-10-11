import { initialForm, localErrors, type FormState } from "./model";

export interface TaskTemplate {
  id: string;
  name: string;
  hint: string;
  form: FormState;
}

const v = (id: number, name: string, p: Partial<FormState["vars"][number]>): FormState["vars"][number] => ({
  id, name, type: "range", min: "", max: "", step: "", list: "", expr: "", ...p,
});

/** Три шаблона для работодателя: Backend, Frontend, AI Engineer. */
export const TEMPLATES: TaskTemplate[] = [
  {
    id: "backend",
    name: "Backend",
    hint: "Нагрузка и воркеры: одно число",
    form: {
      ...initialForm(),
      title: "Сколько воркеров нужно сервису",
      skill: "system_design",
      level: 3,
      timeLimit: "120",
      kind: "exact",
      stem: "Сервис получает {{rps}} запросов в секунду, обработка одного занимает {{ms}} мс на одном воркере. Сколько воркеров нужно, чтобы выдержать нагрузку без очереди?",
      vars: [v(1, "rps", { min: "50", max: "500", step: "50" }), v(2, "ms", { type: "values", list: "20, 40, 50, 100" })],
      answer: "rps * ms / 1000",
      precision: "1",
    },
  },
  {
    id: "frontend",
    name: "Frontend",
    hint: "Найти ошибку в компоненте",
    form: {
      ...initialForm(),
      title: "Ошибка в эффекте React",
      skill: "react",
      level: 3,
      timeLimit: "120",
      kind: "find_bug",
      stem: "Компонент должен загружать данные один раз при открытии, но запрашивает их бесконечно. Укажите строку с ошибкой.",
      lines: "function Users() {\n  const [list, setList] = useState([]);\n  useEffect(() => {\n    fetch('/api/users').then(r => r.json()).then(setList);\n  });\n  return <ul>{list.map(u => <li key={u.id}>{u.name}</li>)}</ul>;\n}",
      bugLines: "3",
    },
  },
  {
    id: "ai",
    name: "AI Engineer",
    hint: "Открытый ответ с критериями",
    form: {
      ...initialForm(),
      title: "Оценка качества RAG",
      skill: "rag",
      level: 4,
      timeLimit: "300",
      kind: "open",
      stem: "Ответы вашего RAG-ассистента стали хуже после смены модели эмбеддингов. Опишите, как вы найдёте причину и как проверите исправление.",
      rubric: "Разделяет качество поиска и качество генерации\nСобирает размеченный набор вопросов\nСчитает метрики до и после (recall@k, доля верных ответов)\nНазывает риск утечки тестового набора",
    },
  },
];

export const GUIDE_STEPS = 5;

/** Ошибки полей по шагам: шаг → поля формы, которые обязательны на нём. */
export function stepErrors(f: FormState, step: number): Record<string, string> {
  const e = localErrors(f);
  const fields: Record<number, string[]> = { 1: ["title", "skill"], 3: ["stem"], 5: ["title", "skill", "stem"] };
  const out: Record<string, string> = {};
  for (const k of fields[step] ?? []) if (e[k]) out[k] = e[k];
  return out;
}

/** Шаг, где исправить ошибку поля. */
export const FIELD_STEP: Record<string, number> = { title: 1, skill: 1, stem: 3 };

/** Подставляет в условие первые значения переменных; вычисляемые поля помечены. */
export function sampleStem(f: FormState): string {
  const vals: Record<string, string> = {};
  for (const r of f.vars) {
    const n = r.name.trim();
    if (!n) continue;
    if (r.type === "range") vals[n] = r.min.trim() || "?";
    else if (r.type === "values") vals[n] = r.list.split(",")[0]?.trim() || "?";
    else vals[n] = "…";
  }
  return f.stem
    .replace(/\{\{\s*=\s*([^}]*)\}\}/g, "…")
    .replace(/\{\{\s*(\w+)\s*\}\}/g, (m, k: string) => vals[k] ?? m);
}
