"use strict";
function showPairQR(canvas, url) {
  const qr = qrcode(0, "M");
  qr.addData(url);
  qr.make();
  const count = qr.getModuleCount(), scale = 8, border = 4;
  canvas.width = canvas.height = (count + border * 2) * scale;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#221e2b";
  for (let y = 0; y < count; y++)
    for (let x = 0; x < count; x++)
      if (qr.isDark(y, x)) ctx.fillRect((x + border) * scale, (y + border) * scale, scale, scale);
}
if (document.getElementById("pair-page")) {
  const code = location.hash.slice(1);
  const status = document.getElementById("pair-status");
  if (/^[a-zA-Z0-9_-]{24}$/.test(code) && location.protocol === "https:") {
    const canvas = document.querySelector("canvas");
    showPairQR(canvas, location.href);
    canvas.hidden = false;
    const link = document.getElementById("connect-phone");
    link.href = "intent://pair?site=" + encodeURIComponent(location.origin) + "&code=" + code +
      "#Intent;scheme=para-clock;package=ru.para.wake;end";
    link.hidden = false;
    status.textContent = "На HONOR нажми кнопку ниже. Если открыл страницу на другом устройстве, отсканируй QR камерой телефона.";
  }
}
