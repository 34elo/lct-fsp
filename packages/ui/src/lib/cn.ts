import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/* Шкала текста из токенов (`text-11` … `text-48`) — это размеры, а не цвета: иначе tailwind-merge
   считает `text-11` цветом и выкидывает его рядом с `text-muted`. */
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["11", "12", "13", "14", "16", "20", "24", "32", "48"] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
