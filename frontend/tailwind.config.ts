import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "Instrument Sans",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      colors: {
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        background: "var(--background)",
        foreground: "var(--foreground)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: "var(--destructive)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        ink: "#202422",
        brand: "#4A7C63",
        cta: "#2D5A45",
        clinicalBorder: "#DDE3E0",
        sage: "#8f9f89",
        moss: "#5f725f",
        linen: "#f7f5f0",
        paper: "#fffdf8",
        coral: "#dc4f49",
        gold: "#d4b24c",
        teal: "#368d85",
      },
      boxShadow: {
        soft: "0 18px 48px rgba(32, 36, 34, 0.10)",
        line: "0 0 0 1px rgba(32, 36, 34, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
