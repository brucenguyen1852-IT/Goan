import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { logout as logoutRemote } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";

export function ProfilePage() {
  const navigate = useNavigate();
  const phone = useAuthStore((s) => s.phone);
  // Đăng xuất phải gọi backend: chỉ xoá token trong máy thì refresh token vẫn sống 30 ngày
  // ở phía server và ai lấy được vẫn dùng tiếp được.
  async function handleLogout() {
    await logoutRemote();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen px-5 py-6">
      <h1 className="mb-6 text-xl font-bold">Tài khoản</h1>

      <div className="mb-6 rounded-2xl border border-night-700 bg-night-900 p-4">
        <p className="text-sm text-white/60">Số điện thoại</p>
        <p className="font-medium">{phone}</p>
      </div>

      {/* TODO: thêm mục Phương thức thanh toán đã lưu, Hỗ trợ khách hàng, Điều khoản dịch vụ */}

      <Button variant="ghost" fullWidth onClick={handleLogout}>
        Đăng xuất
      </Button>
    </div>
  );
}
