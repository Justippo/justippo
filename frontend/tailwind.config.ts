import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        "on-primary": "var(--color-on-primary)",
        "primary-container": "var(--color-primary-container)",
        error: "var(--color-error)",
        "on-error": "var(--color-on-primary)",
        warning: "var(--color-warning)",
        "on-warning": "var(--color-on-surface)",
        success: "var(--color-success)",
        "on-success": "var(--color-on-primary)",
        surface: "var(--color-surface)",
        "on-surface": "var(--color-on-surface)",
        "on-surface-variant": "var(--color-on-surface-variant)",
        outline: "var(--color-outline)",
        "outline-variant": "var(--color-outline-variant)",
        focus: "var(--color-focus)",

        /* Legacy stitch role aliases — map to canonical tokens */
        secondary: "var(--stitch-secondary)",
        "on-secondary": "var(--stitch-on-secondary)",
        "secondary-container": "var(--stitch-secondary-container)",
        "on-secondary-container": "var(--stitch-on-secondary-container)",
        tertiary: "var(--stitch-tertiary)",
        "on-tertiary": "var(--stitch-on-tertiary)",
        "tertiary-container": "var(--stitch-tertiary-container)",
        "on-tertiary-container": "var(--stitch-on-tertiary-container)",
        "error-container": "var(--stitch-error-container)",
        "on-error-container": "var(--stitch-on-error-container)",
        "surface-dim": "var(--stitch-surface-dim)",
        "surface-bright": "var(--stitch-surface-bright)",
        "surface-container-lowest": "var(--stitch-surface-container-lowest)",
        "surface-container-low": "var(--stitch-surface-container-low)",
        "surface-container": "var(--stitch-surface-container)",
        "surface-container-high": "var(--stitch-surface-container-high)",
        "surface-container-highest": "var(--stitch-surface-container-highest)",
        "surface-variant": "var(--stitch-surface-variant)",
        "surface-tint": "var(--stitch-surface-tint)",
        "inverse-surface": "var(--stitch-inverse-surface)",
        "inverse-on-surface": "var(--stitch-inverse-on-surface)",
        "border-subtle": "var(--stitch-border-subtle)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        "headline-xl": [
          "var(--text-headline-xl)",
          {
            lineHeight: "var(--leading-headline-xl)",
            fontWeight: "700",
          },
        ],
        "headline-lg": [
          "var(--text-headline-lg)",
          {
            lineHeight: "var(--leading-headline-lg)",
            fontWeight: "700",
          },
        ],
        "headline-md": [
          "var(--text-headline-md)",
          {
            lineHeight: "var(--leading-headline-md)",
            fontWeight: "700",
          },
        ],
        "body-lg": [
          "var(--text-body-lg)",
          {
            lineHeight: "var(--leading-body-lg)",
            fontWeight: "400",
          },
        ],
        "body-md": [
          "var(--text-body-md)",
          {
            lineHeight: "var(--leading-body-md)",
            fontWeight: "400",
          },
        ],
        "label-md": [
          "var(--text-label-md)",
          {
            lineHeight: "var(--leading-label-md)",
            fontWeight: "700",
          },
        ],
        "label-sm": [
          "var(--text-label-sm)",
          {
            lineHeight: "var(--leading-label-sm)",
            fontWeight: "400",
          },
        ],
        code: [
          "var(--text-code)",
          {
            lineHeight: "var(--leading-code)",
            fontWeight: "400",
          },
        ],
      },
      spacing: {
        xs: "var(--space-xs)",
        sm: "var(--space-sm)",
        md: "var(--space-md)",
        lg: "var(--space-lg)",
        xl: "var(--space-xl)",
        "2xl": "var(--space-2xl)",
        "stitch-unit": "var(--stitch-unit)",
        "stitch-xs": "var(--stitch-spacing-xs)",
        "stitch-sm": "var(--stitch-spacing-sm)",
        "stitch-md": "var(--stitch-spacing-md)",
        "stitch-lg": "var(--stitch-spacing-lg)",
        "stitch-xl": "var(--stitch-spacing-xl)",
      },
      maxWidth: {
        "container-max": "var(--container-max)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        full: "var(--radius-full)",
        stitch: "var(--stitch-radius)",
        "stitch-lg": "var(--stitch-radius-lg)",
        "stitch-xl": "var(--stitch-radius-xl)",
        "stitch-full": "var(--stitch-radius-full)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      backdropBlur: {
        glass: "var(--glass-blur-amount)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
