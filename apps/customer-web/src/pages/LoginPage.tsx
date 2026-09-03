import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { requestOtp } from "@/api/auth";

export function LoginPage() {
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const phoneRegex = /^0\d{9,10}$/;
    if (!phoneRegex.test(phone)) {
      setError("Số điện thoại không hợp lệ. Vui lòng nhập đúng định dạng (vd: 0912345678).");
      return;
    }

    setLoading(true);
    try {
      await requestOtp(phone);
      navigate("/otp", { state: { phone } });
    } catch {
      setError("Không gửi được mã OTP. Vui lòng thử lại sau.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col justify-center px-6">
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold text-brand">GoAn</h1>
        <p className="mt-2 text-white/60">Lái hộ an toàn — Về nhà an tâm</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Số điện thoại"
          type="tel"
          inputMode="numeric"
          placeholder="0912345678"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          autoFocus
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <Button type="submit" fullWidth disabled={loading}>
          {loading ? "Đang gửi mã..." : "Tiếp tục"}
        </Button>
      </form>

      <p className="mt-6 text-center text-xs text-white/40">
        Bằng việc tiếp tục, bạn đồng ý với Điều khoản dịch vụ và Chính sách bảo mật của GoAn.
      </p>
    </div>
  );
}
