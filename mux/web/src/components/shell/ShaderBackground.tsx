'use client';

import React, { useEffect, useRef } from 'react';

// The stitch "live wallpaper": glowing blue/cyan waves over a faint dot grid.
// Ported from the ANIMATION_71 shader in the stitch screens.
const VERTEX = `attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const FRAGMENT = `precision highp float;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_mouse;   // pixels, same space as gl_FragCoord
uniform float u_hover;  // 0..1, eased in JS

void main() {
  vec2 uv = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
  vec2 m = (u_mouse * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
  float md = length(uv - m);
  float near = exp(-md * md * 3.0) * u_hover;
  float t = u_time * 0.3;
  vec3 col = vec3(0.04, 0.06, 0.09);

  for (float i = 1.0; i < 4.0; i++) {
    uv.y += sin(uv.x * (i + 1.5) + t + i * 2.0) * 0.2;
    float d = abs(uv.y);
    float glow = 0.003 / (d + 0.015);
    vec3 waveCol = mix(vec3(0.23, 0.51, 0.96), vec3(0.0, 0.84, 0.74), sin(t + i) * 0.5 + 0.5);
    col += waveCol * glow * (2.0 / i) * (1.0 + near * 2.5);
  }

  // Soft light that follows the cursor
  col += vec3(0.23, 0.51, 0.96) * near * 0.18;

  vec2 grid = abs(fract(uv * 8.0 - t * 0.1) - 0.5);
  float dotGrid = smoothstep(0.05, 0.0, length(grid));
  col += vec3(0.23, 0.51, 0.96) * dotGrid * 0.25;

  col *= 1.0 - length(uv) * 0.35;
  gl_FragColor = vec4(col, 1.0);
}`;

interface ShaderBackgroundProps {
  className?: string;
  // Light up the waves around the cursor
  interactive?: boolean;
}

export function ShaderBackground({ className = '', interactive = false }: ShaderBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl');
    if (!gl) return;

    const compile = (type: number, src: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      return shader;
    };
    const program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'a_position');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const uTime = gl.getUniformLocation(program, 'u_time');
    const uRes = gl.getUniformLocation(program, 'u_resolution');
    const uMouse = gl.getUniformLocation(program, 'u_mouse');
    const uHover = gl.getUniformLocation(program, 'u_hover');

    // Render at half resolution; the glow is soft so it isn't noticeable and it keeps the GPU cool
    const syncSize = () => {
      const w = Math.max(1, Math.floor(canvas.clientWidth / 2));
      const h = Math.max(1, Math.floor(canvas.clientHeight / 2));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    };
    const resizeObserver = new ResizeObserver(syncSize);
    resizeObserver.observe(canvas);
    syncSize();

    // Cursor position eases toward the target so the light glides instead of snapping
    const mouse = { x: 0, y: 0, tx: 0, ty: 0, hover: 0, targetHover: 0 };
    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const inside = e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
      mouse.targetHover = inside ? 1 : 0;
      mouse.tx = ((e.clientX - rect.left) / rect.width) * canvas.width;
      mouse.ty = (1 - (e.clientY - rect.top) / rect.height) * canvas.height;
    };
    const onLeave = () => { mouse.targetHover = 0; };
    if (interactive) {
      window.addEventListener('mousemove', onMove, { passive: true });
      document.addEventListener('mouseleave', onLeave);
    }

    const draw = (ms: number) => {
      mouse.x += (mouse.tx - mouse.x) * 0.08;
      mouse.y += (mouse.ty - mouse.y) * 0.08;
      mouse.hover += (mouse.targetHover - mouse.hover) * 0.05;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(uTime, ms * 0.001);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform2f(uMouse, mouse.x, mouse.y);
      gl.uniform1f(uHover, mouse.hover);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };

    // Only animate while the canvas is on screen and the tab is visible
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    let onScreen = true;
    const loop = (ms: number) => {
      draw(ms);
      frame = requestAnimationFrame(loop);
    };
    const updateRunning = () => {
      cancelAnimationFrame(frame);
      if (onScreen && !document.hidden) frame = requestAnimationFrame(loop);
    };
    const visibility = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      updateRunning();
    });
    if (reduceMotion) {
      draw(4000);
    } else {
      visibility.observe(canvas);
      document.addEventListener('visibilitychange', updateRunning);
      updateRunning();
    }

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      visibility.disconnect();
      document.removeEventListener('visibilitychange', updateRunning);
      window.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseleave', onLeave);
    };
  }, [interactive]);

  return (
    <div className={`pointer-events-none overflow-hidden ${className}`} aria-hidden="true">
      <canvas ref={canvasRef} className="block w-full h-full" />
    </div>
  );
}
