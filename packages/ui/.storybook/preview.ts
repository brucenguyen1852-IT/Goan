import type { Preview } from "@storybook/react";
// Storybook nạp bảng màu của Console để thành phần hiện đúng như lúc chạy thật. Partner Portal
// sau này nạp bảng màu của mình — cùng thành phần, khác thương hiệu.
import "../../../apps/ops-console/src/index.css";

const preview: Preview = {
  parameters: {
    backgrounds: { default: "console" },
    controls: { expanded: true },
  },
  decorators: [
    (Story) => {
      document.documentElement.style.background = "#0f1419";
      return Story();
    },
  ],
};

export default preview;
