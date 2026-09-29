const { app, BrowserWindow } = require("electron");

app.whenReady().then(() => {
  const window = new BrowserWindow({ width: 480, height: 240, show: true });
  window.loadURL(
    "data:text/html,<meta charset='utf-8'><textarea aria-label='测试输入框' autofocus style='width:95%;height:140px'></textarea>",
  );
});
app.on("window-all-closed", () => app.quit());
