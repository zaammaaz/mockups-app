// Rasterize selected Lucide icons to white PNGs under assets/icons/.
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const ICONS = "node_modules/lucide-static/icons";
const OUT = "assets/icons";
const map = {
  logo: "image",
  artwork: "palette",
  video: "circle-play",
  client: "user",
  image: "image",
  palette: "palette",
  box: "box",
  folder: "folder",
  search: "search",
  rocket: "rocket",
  help: "circle-help",
  theme: "moon",
  status: "activity",
  log: "file-text",
  clear: "trash-2",
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const [name, lucide] of Object.entries(map)) {
    const src = path.join(ICONS, lucide + ".svg");
    if (!fs.existsSync(src)) {
      console.error("MISSING", lucide);
      continue;
    }
    await sharp(src, { density: 384 })
      .resize(48)
      .negate({ alpha: false }) // black strokes -> white, keep transparency
      .png()
      .toFile(path.join(OUT, name + ".png"));
    console.log("ok", name);
  }
})();
