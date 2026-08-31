import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, className = "", ...props }: InputProps) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-sm text-white/60">{label}</span>}
      <input
        className={`w-full rounded-xl border border-night-700 bg-night-900 px-4 py-3 text-white placeholder:text-white/30 outline-none focus:border-brand ${className}`}
        {...props}
      />
    </label>
  );
}
