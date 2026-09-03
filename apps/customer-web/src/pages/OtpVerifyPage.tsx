import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { verifyOtp } from "@/api/auth";
import { apiMessage } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

export function OtpVerifyPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const setTokens = useAuthStore((s) => s.setTokens);

  const state = location.state as { phone?: string; debugOtp?: string | null } | null;
  const phone = state?.phone;
  const [otp, setOtp] = useState(state?.debugOtp ?? "");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!phone) {
    navigate("/login", { replace: true });
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (otp.length !== 6) {
      setError("Mã OTP gồm 6 chữ số.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const tokens = await verifyOtp(phone as string, otp, fullName);
      setTokens(tokens.access_token, tokens.refresh_token, phone as string);
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiMessage(err, "Mã OTP không đúng hoặc đã hết hạn. Vui lòng thử lại."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col justify-center px-6">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold">Nhập mã xác thực</h1>
        <p className="mt-2 text-white/60">Mã 6 số vừa được gửi tới {phone}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Mã OTP"
          type="text"
          inputMode="numeric"
          maxLength={6}
          placeholder="••••••"
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
          autoFocus
        />
        <Input
          label="Họ và tên"
          placeholder="Nguyễn Văn A"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <p className="text-xs text-white/40">Chỉ cần điền khi đăng ký lần đầu.</p>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <Button type="submit" fullWidth disabled={loading}>
          {loading ? "Đang xác thực..." : "Xác nhận"}
        </Button>
      </form>
    </div>
  );
}
