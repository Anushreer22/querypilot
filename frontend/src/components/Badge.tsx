import React from "react";

export type BadgeVariant =
  | "success"
  | "error"
  | "warning"
  | "info"
  | "measured"
  | "estimated"
  | "neutral";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({
  variant = "neutral",
  children,
  className = "",
  size = "sm",
}) => {
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";

  const variantClasses: Record<BadgeVariant, string> = {
    success: "bg-emerald-950/80 text-emerald-300 border-emerald-700/60",
    error: "bg-rose-950/80 text-rose-300 border-rose-700/60",
    warning: "bg-amber-950/80 text-amber-300 border-amber-700/60",
    info: "bg-sky-950/80 text-sky-300 border-sky-700/60",
    measured:
      "bg-emerald-900/90 text-emerald-100 border-emerald-500 font-bold tracking-wider shadow-sm",
    estimated:
      "bg-amber-900/90 text-amber-100 border-amber-500 font-bold tracking-wider shadow-sm",
    neutral: "bg-slate-800 text-slate-300 border-slate-700",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 font-medium rounded-md border ${sizeClasses} ${variantClasses[variant]} ${className}`}
    >
      {variant === "measured" && (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      )}
      {variant === "estimated" && (
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
      )}
      {children}
    </span>
  );
};

