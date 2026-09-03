import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  fullWidth?: boolean;
}

export function Button({ variant = "primary", fullWidth, className = "", ...props }: ButtonProps) {
  const base = "rounded-xl px-5 py-3 font-semibold transition active:scale-[0.98] disabled:opacity-40";
  const variants = {
    primary: "bg-brand hover:bg-brand-dark text-white",
    secondary: "bg-night-700 hover:bg-night-700/80 text-white",
    ghost: "bg-transparent border border-night-700 text-white hover:bg-night-900",
  };

  return (
    <button
      className={`${base} ${variants[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
      {...props}
    />
  );
}
