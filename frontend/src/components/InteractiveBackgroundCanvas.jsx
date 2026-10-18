import { useEffect, useRef } from 'react';

export default function InteractiveBackgroundCanvas() {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined' || (navigator && /jsdom/i.test(navigator.userAgent))) return;
    const canvas = canvasRef.current;
    if (!canvas || typeof canvas.getContext !== 'function') return;
    let ctx;
    try {
      ctx = canvas.getContext('2d');
    } catch {
      return;
    }
    if (!ctx) return;

    let animationFrameId;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // Mouse coordinates with smooth interpolation
    let mouse = { x: width * 0.5, y: height * 0.35, targetX: width * 0.5, targetY: height * 0.35 };

    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    const handleMouseMove = (e) => {
      mouse.targetX = e.clientX;
      mouse.targetY = e.clientY;
    };

    // Ambient orbs tuned for light mode
    const orbs = [
      { x: width * 0.25, y: height * 0.3, radius: 360, color: 'rgba(0, 113, 227, 0.10)', vx: 0.3, vy: 0.2 },
      { x: width * 0.75, y: height * 0.45, radius: 420, color: 'rgba(147, 51, 234, 0.08)', vx: -0.25, vy: 0.2 },
      { x: width * 0.5, y: height * 0.7, radius: 380, color: 'rgba(52, 199, 89, 0.07)', vx: 0.2, vy: -0.3 },
      { x: width * 0.85, y: height * 0.15, radius: 300, color: 'rgba(56, 189, 248, 0.09)', vx: -0.15, vy: 0.25 },
    ];

    // Interactive particles
    const particleCount = Math.min(45, Math.floor((width * height) / 32000));
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      radius: Math.random() * 2 + 1,
      alpha: Math.random() * 0.4 + 0.25,
    }));

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let time = 0;
    const render = () => {
      time += 0.008;
      // Smooth mouse damping
      mouse.x += (mouse.targetX - mouse.x) * 0.04;
      mouse.y += (mouse.targetY - mouse.y) * 0.04;

      ctx.clearRect(0, 0, width, height);

      // Render interactive mouse spotlight
      const mouseGrad = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 450);
      mouseGrad.addColorStop(0, 'rgba(0, 113, 227, 0.12)');
      mouseGrad.addColorStop(0.5, 'rgba(147, 51, 234, 0.05)');
      mouseGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = mouseGrad;
      ctx.fillRect(0, 0, width, height);

      // Render ambient breathing orbs
      orbs.forEach((orb, i) => {
        if (!reduceMotion) {
          orb.x += orb.vx + Math.sin(time + i) * 0.3;
          orb.y += orb.vy + Math.cos(time + i * 1.5) * 0.3;

          if (orb.x < -100) orb.x = width + 100;
          if (orb.x > width + 100) orb.x = -100;
          if (orb.y < -100) orb.y = height + 100;
          if (orb.y > height + 100) orb.y = -100;
        }

        const grad = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, orb.radius);
        grad.addColorStop(0, orb.color);
        grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.radius, 0, Math.PI * 2);
        ctx.fill();
      });

      // Render interactive particles
      if (!reduceMotion) {
        particles.forEach((p) => {
          p.x += p.vx;
          p.y += p.vy;

          if (p.x < 0) p.x = width;
          if (p.x > width) p.x = 0;
          if (p.y < 0) p.y = height;
          if (p.y > height) p.y = 0;

          // Mouse attraction/repulsion
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180) {
            const force = (180 - dist) / 180;
            p.x -= (dx / dist) * force * 1.5;
            p.y -= (dy / dist) * force * 1.5;
          }

          ctx.beginPath();
          ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(0, 113, 227, ${p.alpha})`;
          ctx.fill();
        });

        // Connect nearby particles with subtle lines
        ctx.lineWidth = 0.6;
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x;
            const dy = particles[i].y - particles[j].y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 100) {
              const alpha = (1 - dist / 100) * 0.18;
              ctx.strokeStyle = `rgba(0, 113, 227, ${alpha})`;
              ctx.beginPath();
              ctx.moveTo(particles[i].x, particles[i].y);
              ctx.lineTo(particles[j].x, particles[j].y);
              ctx.stroke();
            }
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="interactive-bg-canvas"
      aria-hidden="true"
    />
  );
}
