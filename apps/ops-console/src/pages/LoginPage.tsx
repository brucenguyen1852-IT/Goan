import { useState, type FormEvent } from "react";
import { useAuth } from "@/auth/useAuth";
import { Button, ErrorText } from "@/components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password, totp);
    } catch (err) {
      // Backend cố tình trả cùng một thông điệp cho email lạ / sai mật khẩu / sai mã,
      // nên hiện nguyên văn là đủ và không lộ email nào có thật.
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-box" onSubmit={submit}>
        <h1>GoAn Console</h1>
        <p className="muted">Chỉ dành cho nhân sự nội bộ. Mọi thao tác đều được ghi nhật ký.</p>

        <label>
          Email công ty
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Mật khẩu
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          Mã xác thực hai lớp
          <input
            value={totp}
            onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            placeholder="6 chữ số"
            autoComplete="one-time-code"
            required
          />
        </label>

        <ErrorText>{error}</ErrorText>
        <Button type="submit" kind="primary" disabled={busy}>
          {busy ? "Đang kiểm tra…" : "Đăng nhập"}
        </Button>
        <p className="hint">Sai 5 lần liên tiếp, tài khoản bị khoá tạm thời 15 phút.</p>
      </form>
    </div>
  );
}
