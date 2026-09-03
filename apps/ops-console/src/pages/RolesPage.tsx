import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, ErrorText, Table } from "@goan/ui";
import { api } from "@/api/client";
import { useAuth } from "@/auth/useAuth";

/** API trả về hình dạng lạ (proxy chèn trang lỗi, gateway trả HTML) không được làm trắng
 * màn hình Console. Thà hiện danh sách rỗng còn hơn để người vận hành nhìn tab trắng. */
function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}


interface Role {
  code: string;
  name: string;
  permissions: string[];
}

interface Permission {
  code: string;
  description: string;
}

export function RolesPage() {
  const { can } = useAuth();
  const [roles, setRoles] = useState<Role[]>([]);
  const [catalog, setCatalog] = useState<Permission[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setRoles(asList<Role>(await api.get("/ops/roles")));
      if (can("iam:role:write"))
        setCatalog(asList<Permission>(await api.get("/ops/permissions")));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được vai trò");
    }
  }, [can]);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(role: Role) {
    setEditing(role.code);
    setChosen(new Set(role.permissions));
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    try {
      await api.put(`/ops/roles/${editing}/permissions`, { permissions: [...chosen] });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không lưu được");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Card title="Ma trận vai trò và quyền">
        <ErrorText>{error}</ErrorText>
        <p className="muted">
          Vai trò chỉ là tập hợp quyền, lưu trong cơ sở dữ liệu. Sửa quyền có hiệu lực ngay, không
          cần deploy lại hệ thống. Vai trò quản trị hệ thống không sửa được — đó là đường thoát
          hiểm cuối cùng nếu ai đó lỡ tay gỡ hết quyền của chính mình.
        </p>
        <Table head={["Vai trò", "Mã", "Quyền", ""]}>
          {roles.map((r) => (
            <tr key={r.code}>
              <td>{r.name}</td>
              <td className="mono">{r.code}</td>
              <td className="perm-list">
                {r.permissions.map((p) => (
                  <code key={p}>{p}</code>
                ))}
              </td>
              <td>
                {can("iam:role:write") && r.code !== "super_admin" && (
                  <Button onClick={() => startEdit(r)}>Sửa quyền</Button>
                )}
                {r.code === "super_admin" && <Badge kind="muted">Không sửa được</Badge>}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {editing && (
        <Card
          title={`Sửa quyền cho vai trò ${editing}`}
          action={<Button onClick={() => setEditing(null)}>Huỷ</Button>}
        >
          <div className="perm-grid">
            {catalog.map((p) => (
              <label key={p.code} className="inline">
                <input
                  type="checkbox"
                  checked={chosen.has(p.code)}
                  onChange={(e) => {
                    const next = new Set(chosen);
                    if (e.target.checked) next.add(p.code);
                    else next.delete(p.code);
                    setChosen(next);
                  }}
                />
                <span>
                  <code>{p.code}</code>
                  <span className="muted small"> — {p.description}</span>
                </span>
              </label>
            ))}
          </div>
          <Button kind="primary" disabled={saving} onClick={() => void save()}>
            {saving ? "Đang lưu…" : `Lưu ${chosen.size} quyền`}
          </Button>
        </Card>
      )}
    </>
  );
}
