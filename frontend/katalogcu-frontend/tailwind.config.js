/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      colors: {
        "primary": "#4FD1C5",
        "background-light": "#F7FAFC",
        "background-dark": "#0A2540",
        "text-dark": "#1A202C",
        "text-light": "#F7FAFC",
        "text-muted-dark": "#A0AEC0",
        "text-muted-light": "#4A5568",
        "surface-light": "#FFFFFF",
        "surface-dark": "#1A202C",
        "border-light": "#EDF2F7",
        "border-dark": "#2D3748"
      },
      fontFamily: {
        "display": ["Inter", "sans-serif"]
      },
    },
  },
  plugins: [],
}