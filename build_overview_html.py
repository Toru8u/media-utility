#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

HTML_HEAD = '''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Bildergalerie Übersicht</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { background:#181822; color:#eee; margin:0; font-family:system-ui,sans-serif; overflow-x:hidden; }
h1 { text-align:center; margin:0; padding:24px 0 8px; font-size:2rem; background:#232336; letter-spacing:0.06em; }
#overview, #gallery { display:none; transition:.3s; }
#overview.active, #gallery.active { display:block; }
.overview-grid { display: flex; flex-wrap: wrap; gap:1.5rem; justify-content: center; padding:1.5rem; }
.folder-tile { background:#242446; border-radius:12px; overflow:hidden; box-shadow:0 2px 16px #0003; width:240px; cursor:pointer; text-align:center; transition:transform .13s; position:relative;}
.folder-tile:hover { transform:scale(1.04); }
.folder-tile img { width:100%; height:160px; object-fit:cover; display:block; }
.folder-label { background:#19192c; color:#fff; font-size:1.14em; padding:12px 0; border-top:1px solid #2a2a43; }
.gallery-bar {display:flex;align-items:center;justify-content:space-between;background:#111; padding:8px 24px;}
.gallery-back {font-size:1.6em;cursor:pointer;padding-right:15px;color:#ddd;}
.gallery-folder-title { font-size:1.15em;}
.gallery-row {display:flex;flex-wrap:wrap;gap:1.2rem;justify-content:center;padding:2rem;}
.gallery-thumb {flex:0 1 220px;max-width:220px;border-radius:8px;overflow:hidden;cursor:pointer;box-shadow:0 1px 8px #0004;transition:transform .16s;}
.gallery-thumb:hover {transform:scale(1.03);}
.gallery-thumb img { width:100%; height:140px;object-fit:cover; }
.viewer { display:none; align-items:center; justify-content:center; position:fixed;inset:0;background:#181822ee; z-index:999; transition:.3s;}
.viewer.active {display:flex;}
.viewer-inner{display:flex; flex-direction:column; align-items:center; width:100%;}
.viewer-img {max-width:96vw;max-height:86vh;border-radius:10px;border:3px solid #232336;box-shadow:0 2px 40px #2227;background:#000;}
.viewer-nav {font-size:2.4em;color:#eee;position:absolute;top:50%;transform:translateY(-50%);cursor:pointer;user-select:none;}
.viewer-prev {left:22px;}
.viewer-next {right:22px;}
.viewer-close {position:absolute;top:16px;right:36px;font-size:2.6em;cursor:pointer;color:#f34;}
.viewer-caption {
    padding:20px 0 0;
    text-align:center;
    font-size:1.12em;
    color:#888;
    letter-spacing:0.06em;
    user-select:all;
}
@media (max-width:900px) {
  .overview-grid, .gallery-row {gap:1rem;}
  .folder-tile, .gallery-thumb { width:160px; }
  .gallery-thumb img, .folder-tile img { height:92px; }
  .viewer-img {max-width:98vw;max-height:65vh;}
}
</style>
</head>
<body>
<h1>Bildergalerie Übersicht</h1>
<div id="overview" class="active">
  <div class="overview-grid" id="folderGrid"></div>
</div>
<div id="gallery">
  <div class="gallery-bar">
    <span class="gallery-back" id="backBtn">⮌ Übersicht</span>
    <span class="gallery-folder-title" id="galleryTitle"></span>
  </div>
  <div class="gallery-row" id="galleryGrid"></div>
</div>
<!-- Viewer/Lightbox -->
<div class="viewer" id="viewer">
  <span class="viewer-nav viewer-prev" id="viewerPrev">❮</span>
  <div class="viewer-inner">
    <img class="viewer-img" id="viewerImg"/>
    <div class="viewer-caption" id="viewerCaption"></div>
  </div>
  <span class="viewer-nav viewer-next" id="viewerNext">❯</span>
  <span class="viewer-close" id="viewerClose">×</span>
</div>
<script>
'''

JS_CORE = '''
let currentFolder = null, currentImages = [], currentImgIndex = 0;

// Build overview grid
function showOverview() {
  currentFolder = null;
  document.getElementById('overview').classList.add('active');
  document.getElementById('gallery').classList.remove('active');
  let grid = document.getElementById('folderGrid');
  grid.innerHTML = '';
  for (let [folder, imgs] of Object.entries(data.folders)) {
    let thumb = `${folder}/${imgs[0]}`;
    let el = document.createElement('div');
    el.className = 'folder-tile';
    el.innerHTML = `<img src="${thumb}" alt="${folder}"><span class="folder-label">${folder}</span>`;
    el.onclick = ()=>showGallery(folder, imgs);
    grid.appendChild(el);
  }
}

// Build gallery grid for folder (no caption here)
function showGallery(folder, imgs) {
  currentFolder = folder;
  currentImages = imgs;
  document.getElementById('overview').classList.remove('active');
  document.getElementById('gallery').classList.add('active');
  document.getElementById('galleryTitle').textContent = folder;
  let grid = document.getElementById('galleryGrid');
  grid.innerHTML = '';
  imgs.forEach((img,i)=>{
    let src = `${folder}/${img}`;
    let el = document.createElement('div');
    el.className = 'gallery-thumb';
    el.innerHTML = `<img src="${src}" alt="Bild">`;
    el.onclick = ()=>openViewer(i);
    grid.appendChild(el);
  });
}

// Viewer popup logic
function openViewer(idx) {
  currentImgIndex = idx;
  let src = `${currentFolder}/${currentImages[idx]}`;
  let cap = currentImages[idx];
  document.getElementById('viewerImg').src = src;
  document.getElementById('viewerImg').alt = cap;
  document.getElementById('viewerCaption').textContent = cap;
  document.getElementById('viewer').classList.add('active');
}
function closeViewer() {
  document.getElementById('viewer').classList.remove('active');
}
function nextViewer(delta) {
  let len = currentImages.length;
  currentImgIndex = (currentImgIndex + delta + len) % len;
  openViewer(currentImgIndex);
}

// Event listeners
document.getElementById('backBtn').onclick = showOverview;
document.getElementById('viewerPrev').onclick = ()=>nextViewer(-1);
document.getElementById('viewerNext').onclick = ()=>nextViewer(1);
document.getElementById('viewerClose').onclick = closeViewer;
document.getElementById('viewer').onclick = (e)=>{
  if (e.target===e.currentTarget) closeViewer();
};
document.addEventListener('keydown', e=>{
  let v=document.getElementById('viewer').classList.contains('active');
  // In Viewer: ←/→/ESC/↑
  if (v) {
    if (e.key==='ArrowLeft') nextViewer(-1);
    else if (e.key==='ArrowRight') nextViewer(1);
    else if (e.key==='Escape'||e.key==='ArrowUp') closeViewer();
  } else if(currentFolder) {
    // In Galerie: ↑ geht zurück zur Übersicht
    if (e.key==="ArrowUp") showOverview();
  }
});

showOverview();
</script>
</body>
</html>
'''

def build_media_index(base_dir):
    index = {"folders": {}}
    for root, dirs, files in os.walk(base_dir):
        folder = Path(root)
        if folder == base_dir:  # Hauptordner auslassen
            continue
        images = [f for f in sorted(files) if Path(f).suffix.lower() in IMAGE_EXTENSIONS]
        if images:
            index["folders"][folder.relative_to(base_dir).as_posix()] = images
    return index

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Verwendung: python build_overview_html.py <BASISORDNER>")
        sys.exit(1)
    base_dir = Path(sys.argv[1]).expanduser().resolve()
    idx = build_media_index(base_dir)

    out_file = base_dir / "overview.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(HTML_HEAD)
        f.write("let data = ")
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.write(";")
        f.write(JS_CORE)

    print(f"overview.html erzeugt: {out_file}")
