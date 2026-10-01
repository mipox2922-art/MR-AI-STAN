import { useEffect, useRef, useState } from "react";

export default function CreativeStudio() {
  const canvasRef = useRef(null);
  const [title, setTitle] = useState("MR AI STUDIO");
  const [subtitle, setSubtitle] = useState("Editable design workspace");
  const [bg, setBg] = useState("#06131b");
  const [image, setImage] = useState(null);

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

    if (image) {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min((width - 160) / img.width, 620 / img.height);
        const w = img.width * scale;
        const h = img.height * scale;
        ctx.drawImage(img, (width - w) / 2, 120, w, h);
        drawText(ctx);
      };
      img.src = image;
    } else {
      drawText(ctx);
    }

    function drawText(context) {
      context.textAlign = "center";
      context.fillStyle = "#dffcff";
      context.font = "bold 64px Inter, sans-serif";
      context.fillText(title || " ", width / 2, 930);
      context.fillStyle = "#8fcbd3";
      context.font = "34px Inter, sans-serif";
      context.fillText(subtitle || " ", width / 2, 1000);
      context.strokeStyle = "#22d3ee";
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(260, 1050);
      context.lineTo(820, 1050);
      context.stroke();
      context.fillStyle = "#22d3ee";
      context.font = "bold 26px Inter, sans-serif";
      context.fillText("MR AI CREATIVE STUDIO", width / 2, 1130);
    }
  }, [title, subtitle, bg, image]);

  function handleImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result);
    reader.readAsDataURL(file);
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
        <div className="panel-title">CREATIVE STUDIO — EDITABLE CANVAS</div>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Title" />
        <input value={subtitle} onChange={e => setSubtitle(e.target.value)} placeholder="Subtitle" />
        <label>BACKGROUND <input type="color" value={bg} onChange={e => setBg(e.target.value)} /></label>
        <label>IMAGE <input type="file" accept="image/*" onChange={handleImage} /></label>
        <button onClick={exportPng}>EXPORT PNG</button>
      </div>
      <div className="canvas-wrap">
        <canvas ref={canvasRef} width={1080} height={1350} />
      </div>
    </section>
  );
}
