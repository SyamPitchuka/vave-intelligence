/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#0b1726",
          900: "#12263a",
          800: "#1b334d",
          700: "#274864",
        },
        canvas: "#f3f5f7",
        ink: "#1c2834",
        muted: "#5c6b7a",
        line: "#d9e0e7",
        accent: {
          50: "#eef4f9",
          100: "#d7e5f2",
          600: "#1f4e79",
          700: "#173d60",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(18, 38, 58, 0.04)",
      },
    },
  },
  plugins: [],
};
