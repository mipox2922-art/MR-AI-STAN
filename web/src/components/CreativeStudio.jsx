import { useEffect, useRef, useState } from "react";

export default function CreativeStudio() {
  const canvasRef = useRef(null);
  const [title, setTitle] = useState("MR AI STUDIO");
  const [subtitle, setSubtitle] = useState("Editable design workspace");
  const [bg, setBg] = useState("#06131b");
  const [image, setImage] = useState(null);
  const [layers, setLayers] = useState({
    title: { x: 540, y: 930 },
    subtitle: { x: 540, y: 1000 },
  });
  const drag = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = 1080;
    const height = 1350;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#0c3f4c");
    gradient.addColorStop(1, bg);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 4;
    ctx.strokeRect(45, 45, width - 90, height - 90);

    const drawText = () => {
      ctx.textAlign = "center";
      ctx.fillStyle = "#dffcff";
      ctx.font = "bold 64px Inter, sans-serif";
      ctx.fillText(title || " ", layers.title.x, layers.title.y);

      ctx.fillStyle = "#8fcbd3";
      ctx.font = "34px Inter, sans-serif";
      ctx.fillText(subtitle || " ", layers.subtitle.x, layers.subtitle.y);

      ctx.strokeStyle = "#22d3ee";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(260, 1050);
      ctx.lineTo(820, 1050);
      ctx.stroke();

      ctx.fillStyle = "#22d3ee";
      ctx.font = "bold 26px Inter, sans-serif";
      ctx.fillText("MR AI CREATIVE STUDIO", 540, 1130);
    };

    if (!image) {
      drawText();
      return;
    }

    const img = new Image();
    img.onload = () => {
      const scale = Math.min((width - 160) / img.width, 620 / img.height);
      const w = img.width * scale;
      const h = img.height * scale;
      ctx.drawImage(img, (width - w) / 2, 120, w, h);
      drawText();
    };
    img.src = image;
  }, [title, subtitle, bg, image, layers]);

  function handleImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result);
    reader.readAsDataURL(file);
  }

  function pointerPosition(event) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    };
  }

  function hitTest(point) {
    const titleBox = {
      x: layers.title.x - 330,
      y: layers.title.y - 70,
      w: 660,
      h: 90,
    };
    const subtitleBox = {
      x: layers.subtitle.x - 320,
      y: layers.subtitle.y - 42,
      w: 640,
      h: 60,
    };
    if (point.x >= titleBox.x && point.x <= titleBox.x + titleBox.w && point.y >= titleBox.y && point.y <= titleBox.y + titleBox.h) {
      return "title";
    }
    if (point.x >= subtitleBox.x && point.x <= subtitleBox.x + subtitleBox.w && point.y >= subtitleBox.y && point.y <= subtitleBox.y + subtitleBox.h) {
      return "subtitle";
    }
    return null;
  }

  function onPointerDown(event) {
    const point = pointerPosition(event);
    const layer = hitTest(point);
    if (!layer) return;
    drag.current = { layer, dx: point.x - layers[layer].x, dy: point.y - layers[layer].y };
    canvasRef.current.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    if (!drag.current) return;
    const point = pointerPosition(event);
    const { layer, dx, dy } = drag.current;
    setLayers(prev => ({
      ...prev,
      [layer]: {
        x: Math.max(100, Math.min(980, point.x - dx)),
        y: Math.max(120, Math.min(1220, point.y - dy)),
      }
    }));
  }

  function onPointerUp() {
    drag.current = null;
  }

  function exportPng() {
    const link = document.createElement("a");
    link.download = "mr-ai-design.png";
    link.href = canvasRef.current.toDataURL("image/png");
    link.click();
  }

  return (
    <section className="studio">
      <div className="studio-controls">
        <div className="panel-title">CREATIVE STUDIO — REAL CANVAS</div>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Title" />
        <input value={subtitle} onChange={e => setSubtitle(e.target.value)} placeholder="Subtitle" />
        <label>
          BACKGROUND
          <input type="color" value={bg} onChange={e => setBg(e.target.value)} />
        </label>
        <label>
          IMAGE
          <input type="file" accept="image/*" onChange={handleImage} />
        </label>
        <button onClick={exportPng}>EXPORT PNG</button>
        <div className="notice">Drag the title or subtitle directly on the canvas.</div>
      </div>

      <div className="canvas-wrap">
        <canvas
          ref={canvasRef}
          width={1080}
          height={1350}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      </div>
    </section>
  );
}
