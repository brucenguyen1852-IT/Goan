import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card, ErrorText, Table } from "@/components/ui";

interface Role {
  code: string;
  name: string;
  permissions: string[];
}

export function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Role[]>("/ops/roles")
      .then(setRoles)
      .catch((err) => setError(err instanceof Error ? err.message : "Không tải được vai trò"));
  }, []);

  return (
    <Card title="Ma trận vai trò và quyền">
      <ErrorText>{error}</ErrorText>
      <p className="muted">
        Vai trò chỉ là tập hợp quyền, lưu trong cơ sở dữ liệu. Sửa quyền của một vai trò không cần
        deploy lại hệ thống.
      </p>
      <Table head={["Vai trò", "Mã", "Quyền"]}>
        {roles.map((r) => (
          <tr key={r.code}>
            <td>{r.name}</td>
            <td className="mono">{r.code}</td>
            <td className="perm-list">
              {r.permissions.map((p) => (
                <code key={p}>{p}</code>
              ))}
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}
