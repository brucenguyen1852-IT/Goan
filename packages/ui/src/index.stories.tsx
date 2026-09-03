/**
 * Storybook cho bộ thành phần dùng chung.
 *
 *     pnpm --filter @goan/ui storybook
 *
 * Mục đích không phải để "xem cho đẹp": đây là chỗ duy nhất thấy được mọi trạng thái của một
 * thành phần cạnh nhau — nhãn ok/cảnh báo/lỗi, nút đang bị khoá, bảng rỗng. Trong ứng dụng
 * thật, trạng thái lỗi và trạng thái rỗng là hai thứ khó dựng lại nhất, nên cũng là hai thứ
 * hay bị bỏ quên nhất.
 */
import type { Meta, StoryObj } from "@storybook/react";
import { Badge, Button, Card, Empty, ErrorText, Table } from "./index";

const meta: Meta = { title: "GoAn/Bộ thành phần" };
export default meta;

export const NhanTrangThai: StoryObj = {
  name: "Nhãn trạng thái",
  render: () => (
    <Card title="Nhãn trạng thái">
      <Badge kind="ok">Đã duyệt</Badge>
      <Badge kind="warn">Chờ duyệt</Badge>
      <Badge kind="bad">Từ chối</Badge>
      <Badge kind="muted">Không sửa được</Badge>
    </Card>
  ),
};

export const Nut: StoryObj = {
  name: "Nút",
  render: () => (
    <Card title="Nút" action={<Button>Ở tiêu đề</Button>}>
      <div className="actions">
        <Button>Mặc định</Button>
        <Button kind="primary">Chính</Button>
        <Button kind="danger">Nguy hiểm</Button>
        <Button disabled>Đang xử lý</Button>
      </div>
    </Card>
  ),
};

export const Bang: StoryObj = {
  name: "Bảng",
  render: () => (
    <Card title="Bảng có dữ liệu">
      <Table head={["Tài xế", "Trạng thái", "Số chuyến"]}>
        <tr>
          <td>Nguyễn *** An</td>
          <td>
            <Badge kind="ok">Sẵn sàng</Badge>
          </td>
          <td>128</td>
        </tr>
        <tr>
          <td>Trần *** Bình</td>
          <td>
            <Badge kind="warn">Đang chạy</Badge>
          </td>
          <td>54</td>
        </tr>
      </Table>
    </Card>
  ),
};

export const TrangThaiRongVaLoi: StoryObj = {
  name: "Trạng thái rỗng và lỗi",
  render: () => (
    <Card title="Hai trạng thái hay bị quên">
      <ErrorText>Không tải được danh sách: hết phiên đăng nhập</ErrorText>
      <Empty>Không có hồ sơ nào ở trạng thái này.</Empty>
    </Card>
  ),
};
