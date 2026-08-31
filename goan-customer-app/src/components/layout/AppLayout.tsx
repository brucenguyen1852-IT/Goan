import { NavLink, Outlet } from "react-router-dom";

const TABS = [
  { to: "/", label: "Đặt xe", icon: "🚗" },
  { to: "/history", label: "Lịch sử", icon: "🕑" },
  { to: "/profile", label: "Tài khoản", icon: "👤" },
];

export function AppLayout() {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col bg-night-950">
      <div className="flex-1 pb-20">
        <Outlet />
      </div>

      <nav className="fixed bottom-0 left-1/2 w-full max-w-md -translate-x-1/2 border-t border-night-700 bg-night-950/95 backdrop-blur">
        <div className="flex justify-around py-2">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.to === "/"}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 px-4 py-1 text-xs ${
                  isActive ? "text-brand" : "text-white/40"
                }`
              }
            >
              <span className="text-lg">{tab.icon}</span>
              {tab.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
