import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#202422",
        muted: "#6f7470",
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
