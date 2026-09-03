/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Xanh đêm làm màu chủ đạo (an toàn, tin cậy, gợi "về nhà ban đêm")
        night: {
          950: "#0B1220",
          900: "#111C33",
          700: "#1E2E4F",
        },
        brand: {
          DEFAULT: "#16A34A", // xanh lá — an toàn, "về nhà an tâm"
          dark: "#15803D",
        },
        accent: {
          DEFAULT: "#F59E0B", // vàng hổ phách — cảnh báo/CTA phụ (giá, ưu đãi)
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
