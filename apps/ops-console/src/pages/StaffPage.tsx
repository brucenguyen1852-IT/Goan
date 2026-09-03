import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/useAuth";
import { Badge, Button, Card, Empty, ErrorText, Table } from "@goan/ui";

/** API trả về hình dạng lạ (proxy chèn trang lỗi, gateway trả HTML) không được làm trắng
 * màn hình Console. Thà hiện danh sách rỗng còn hơn để người vận hành nhìn tab trắng. */
function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}


interface Staff {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  last_login_at: string | null;
  locked_until: string | null;
}

interface Role {
  code: string;
  name: string;
  permissions: string[];
}

export function StaffPage() {
  const { can } = useAuth();
  const [rows, setRows] = useState<Staff[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", roles: [] as string[] });
  const [totpUri, setTotpUri] = useState("");

  const load = useCallback(async () => {
    try {
      const query = showInactive ? "?include_inactive=true" : "";
      setRows(asList<Staff>(await api.get(`/ops/staff${query}`)));
      if (can("iam:role:read")) setRoles(asList<Role>(await api.get("/ops/roles")));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách");
    }
  }, [showInactive, can]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await api.post<{ totp_provisioning_uri: string }>("/ops/staff", form);
      // Bí mật TOTP chỉ trả về ĐÚNG MỘT LẦN. Không có endpoint nào đọc lại được.
      setTotpUri(created.totp_provisioning_uri);
      setForm({ email: "", full_name: "", password: "", roles: [] });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được tài khoản");
    }
  }

  async function deactivate(id: string) {
    const reason = window.prompt("Lý do vô hiệu hoá (ghi vào nhật ký):");
    if (!reason) return;
    try {
      await api.post(`/ops/staff/${id}/deactivate`, { reason });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  async function unlock(id: string) {
    await api.post(`/ops/staff/${id}/unlock`);
    await load();
  }

  return (
    <>
      <Card
        title="Nhân sự nội bộ"
        action={
          <label className="inline">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Hiện cả người đã nghỉ
          </label>
        }
      >
        <ErrorText>{error}</ErrorText>
        {rows.length === 0 ? (
          <Empty>Chưa có tài khoản nào.</Empty>
        ) : (
          <Table head={["Họ tên", "Email", "Vai trò", "Trạng thái", "Đăng nhập gần nhất", ""]}>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>{s.full_name}</td>
                <td className="mono">{s.email}</td>
                <td>{s.roles.join(", ") || "—"}</td>
                <td>
                  {s.is_active ? <Badge kind="ok">Đang làm</Badge> : <Badge kind="bad">Đã nghỉ</Badge>}
                  {s.locked_until && <Badge kind="warn">Đang khoá</Badge>}
                </td>
                <td className="muted small">
                  {s.last_login_at ? new Date(s.last_login_at).toLocaleString("vi-VN") : "chưa bao giờ"}
                </td>
                <td className="actions">
                  {can("iam:staff:write") && s.locked_until && (
                    <Button onClick={() => void unlock(s.id)}>Gỡ khoá</Button>
                  )}
                  {can("iam:staff:write") && s.is_active && (
                    <Button kind="danger" onClick={() => void deactivate(s.id)}>
                      Vô hiệu hoá
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {can("iam:staff:write") && (
        <Card title="Thêm nhân sự">
          <form className="form-row" onSubmit={create}>
            <input
              placeholder="Email công ty"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
            <input
              placeholder="Họ tên"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              required
            />
            <input
              placeholder="Mật khẩu (tối thiểu 12 ký tự)"
              type="password"
              minLength={12}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
            <select
              multiple
              value={form.roles}
              onChange={(e) =>
                setForm({
                  ...form,
                  roles: Array.from(e.target.selectedOptions, (o) => o.value),
                })
              }
            >
              {roles.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.name} ({r.code})
                </option>
              ))}
            </select>
            <Button type="submit" kind="primary">
              Tạo tài khoản
            </Button>
          </form>
          {totpUri && (
            <div className="notice">
              <strong>Chép ngay — chỉ hiện một lần.</strong> Đưa chuỗi này cho người dùng quét vào
              app xác thực; hệ thống không đọc lại được nữa.
              <code className="break">{totpUri}</code>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
