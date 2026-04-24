# 云邮宝演示操作教程视频

这是一个独立 Remotion 工程，用于生成“云邮宝怎么使用”的演示视频，不是 Remotion 教程。

当前版本约 48 秒，覆盖：

- 当前 App 主控制台界面结构
- 发件账号池配置
- 测试 Excel 名单导入和列映射
- 空白富文本正文、主题和附件
- 保守发送节奏设置
- 测试邮箱发送流程
- 实时日志、失败导出、上线和 EXE 打包提示

视频中的邮箱和授权码均为脱敏或样例数据，不会展示真实授权码。

## 预览

```bash
cd remotion/yunyoubao-tutorial
npm install
npm run studio
```

## 渲染

```bash
npm run render
```

输出：

```text
remotion/yunyoubao-tutorial/out/yunyoubao-tutorial.mp4
```

## 单帧检查

```bash
npm run still
```
