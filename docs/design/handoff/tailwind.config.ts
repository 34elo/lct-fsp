import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#402FFF", deep: "#201880", mid: "#A9A1FF" },
        tint: { 50: "#F4F3FF", 100: "#E6E4FF", 200: "#CDC9FF" },
        signal: "#D4152D",
        ink: "#1B1C21",
        muted: "#5B5D66",
        hairline: "#E1E1E5",
        page: "#FAFAFC",
        "card-dark": "#22232A",
      },
      fontFamily: { sans: ["Onest", "system-ui", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "monospace"] },
      borderRadius: { sm: "6px", md: "8px", lg: "10px", xl: "12px" },
    },
  },
} satisfies Config;
