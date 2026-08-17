"""
Web UI dashboard and mini controller for NetEase-MusicBox.
Provides a lightweight local web server with zero external dependencies.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

from .daemon import is_daemon_running, send_request, spawn_daemon

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 27124

_HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>MusicBox — 网页播放台</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎵</text></svg>">
  <style>
    :root {
      --bg-primary: #0a0c10;
      --bg-card: rgba(22, 27, 34, 0.75);
      --bg-card-hover: rgba(33, 40, 50, 0.85);
      --bg-accent: rgba(220, 38, 38, 0.15);
      --accent: #e11d48;
      --accent-glow: rgba(225, 29, 72, 0.4);
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --text-sub: #6b7280;
      --border: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(225, 29, 72, 0.5);
      --glass: blur(20px);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", "Helvetica Neue", sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      position: relative;
    }

    /* Dynamic ambient glowing background */
    .ambient-glow {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: radial-gradient(circle at 20% 30%, rgba(225, 29, 72, 0.15) 0%, transparent 60%),
                  radial-gradient(circle at 80% 70%, rgba(99, 102, 241, 0.12) 0%, transparent 60%),
                  radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.08) 0%, transparent 70%);
      pointer-events: none;
      z-index: 0;
      filter: blur(40px);
      transition: opacity 1s ease;
    }

    header {
      position: relative;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 28px;
      background: rgba(10, 12, 16, 0.6);
      backdrop-filter: var(--glass);
      border-bottom: 1px solid var(--border);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .brand-icon {
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #e11d48, #f43f5e);
      border-radius: 9px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px var(--accent-glow);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 500;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
    }

    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }

    .status-dot.offline {
      background: #ef4444;
      box-shadow: 0 0 8px #ef4444;
    }

    main {
      position: relative;
      z-index: 5;
      flex: 1;
      max-width: 1280px;
      width: 100%;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: 1fr 380px;
      gap: 24px;
    }

    @media (max-width: 960px) {
      main {
        grid-template-columns: 1fr;
        padding: 16px;
      }
    }

    .player-card {
      background: var(--bg-card);
      backdrop-filter: var(--glass);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 32px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4);
      min-height: 520px;
    }

    .track-info-section {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 12px 0 24px;
    }

    .cover-art-container {
      width: 220px;
      height: 220px;
      border-radius: var(--radius-md);
      position: relative;
      margin-bottom: 24px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #1e293b, #0f172a);
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .cover-art-container.playing {
      animation: pulse-glow 3s infinite ease-in-out;
    }

    @keyframes pulse-glow {
      0%, 100% { box-shadow: 0 16px 36px rgba(0, 0, 0, 0.5), 0 0 24px rgba(225, 29, 72, 0.2); }
      50% { box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6), 0 0 36px rgba(225, 29, 72, 0.45); }
    }

    .cover-art-icon {
      font-size: 4rem;
      opacity: 0.7;
    }

    .song-title {
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: 8px;
      letter-spacing: -0.01em;
      max-width: 90%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .artist-album {
      font-size: 1rem;
      color: var(--text-muted);
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: center;
    }

    .meta-badges {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: center;
    }

    .meta-pill {
      font-size: 0.7rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
      border: 1px solid var(--border);
    }

    .meta-pill.highlight {
      background: var(--bg-accent);
      color: var(--accent);
      border-color: rgba(225, 29, 72, 0.3);
    }

    /* Lyrics Display */
    .lyrics-container {
      margin: 16px 0;
      height: 90px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      position: relative;
    }

    .lyric-current {
      font-size: 1.15rem;
      font-weight: 600;
      color: #fb7185;
      text-shadow: 0 0 16px rgba(251, 113, 133, 0.4);
      margin-bottom: 6px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      text-align: center;
      max-width: 95%;
    }

    .lyric-next {
      font-size: 0.85rem;
      color: var(--text-sub);
      text-align: center;
      max-width: 90%;
      opacity: 0.7;
    }

    /* Progress Bar */
    .progress-section {
      margin: 16px 0 24px;
    }

    .progress-bar-container {
      width: 100%;
      height: 8px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 4px;
      position: relative;
      cursor: pointer;
      overflow: hidden;
      transition: height 0.15s ease;
    }

    .progress-bar-container:hover {
      height: 10px;
    }

    .progress-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #e11d48, #f43f5e);
      border-radius: 4px;
      width: 0%;
      transition: width 0.15s linear;
      position: relative;
      box-shadow: 0 0 12px var(--accent-glow);
    }

    .time-row {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: var(--text-sub);
      margin-top: 8px;
      font-family: monospace;
      font-weight: 600;
    }

    /* Controls Bar */
    .controls-row {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 18px;
    }

    .btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-main);
      border-radius: 50%;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s ease;
      font-size: 1.1rem;
    }

    .btn:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.25);
      transform: translateY(-2px);
    }

    .btn:active {
      transform: translateY(0);
    }

    .btn-play {
      width: 58px;
      height: 58px;
      background: var(--accent);
      border: none;
      color: #fff;
      font-size: 1.4rem;
      box-shadow: 0 6px 20px var(--accent-glow);
    }

    .btn-play:hover {
      background: #f43f5e;
      box-shadow: 0 8px 24px var(--accent-glow);
    }

    .btn-icon-text {
      border-radius: var(--radius-sm);
      width: auto;
      height: 36px;
      padding: 0 12px;
      font-size: 0.8rem;
      gap: 6px;
    }

    .volume-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 20px;
      justify-content: center;
    }

    .volume-slider {
      -webkit-appearance: none;
      width: 140px;
      height: 5px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.1);
      outline: none;
    }

    .volume-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }

    /* Queue Section */
    .queue-card {
      background: var(--bg-card);
      backdrop-filter: var(--glass);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 24px;
      display: flex;
      flex-direction: column;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4);
      max-height: calc(100vh - 120px);
    }

    .queue-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }

    .queue-title {
      font-size: 1.1rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .queue-count {
      font-size: 0.8rem;
      color: var(--text-sub);
      font-weight: normal;
    }

    .queue-list {
      list-style: none;
      overflow-y: auto;
      flex: 1;
      padding-right: 4px;
    }

    .queue-list::-webkit-scrollbar {
      width: 6px;
    }

    .queue-list::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.15);
      border-radius: 3px;
    }

    .queue-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      border-radius: var(--radius-sm);
      margin-bottom: 4px;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .queue-item:hover {
      background: var(--bg-card-hover);
    }

    .queue-item.active {
      background: var(--bg-accent);
      border-left: 3px solid var(--accent);
    }

    .queue-item-info {
      display: flex;
      flex-direction: column;
      max-width: 80%;
    }

    .queue-item-name {
      font-size: 0.9rem;
      font-weight: 600;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .queue-item.active .queue-item-name {
      color: #fb7185;
    }

    .queue-item-artist {
      font-size: 0.75rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .queue-index {
      font-size: 0.75rem;
      color: var(--text-sub);
      font-family: monospace;
      margin-right: 10px;
    }
  </style>
</head>
<body>
  <div class="ambient-glow" id="ambientGlow"></div>

  <header>
    <div class="brand">
      <div class="brand-icon">♫</div>
      <span>MusicBox Web</span>
    </div>
    <div class="status-badge">
      <div class="status-dot" id="statusDot"></div>
      <span id="statusText">正在同步...</span>
    </div>
  </header>

  <main>
    <!-- Left Column: Player & Lyrics -->
    <section class="player-card">
      <div class="track-info-section">
        <div class="cover-art-container" id="coverContainer">
          <div class="cover-art-icon">🎵</div>
        </div>
        <h1 class="song-title" id="songTitle">未播放歌曲</h1>
        <div class="artist-album" id="artistAlbum">
          <span id="artistName">网易云音乐命令行播放器</span>
        </div>
        <div class="meta-badges">
          <span class="meta-pill highlight" id="modeBadge">顺序播放</span>
          <span class="meta-pill" id="backendBadge">MPV</span>
          <span class="meta-pill" id="stateBadge">已暂停</span>
        </div>
      </div>

      <!-- Sync Lyrics -->
      <div class="lyrics-container">
        <div class="lyric-current" id="lyricCurrent">享受音乐带来的感动</div>
        <div class="lyric-next" id="lyricNext">NetEase MusicBox Web Console</div>
      </div>

      <!-- Progress Section -->
      <div class="progress-section">
        <div class="progress-bar-container" id="progressContainer">
          <div class="progress-bar-fill" id="progressBar"></div>
        </div>
        <div class="time-row">
          <span id="timeCurrent">00:00</span>
          <span id="timeTotal">00:00</span>
        </div>
      </div>

      <!-- Controls -->
      <div class="controls-row">
        <button class="btn" id="btnMode" title="切换模式">🔁</button>
        <button class="btn" id="btnPrev" title="上一首">⏮</button>
        <button class="btn btn-play" id="btnPlay" title="播放/暂停">▶</button>
        <button class="btn" id="btnNext" title="下一首">⏭</button>
        <button class="btn" id="btnRefresh" title="刷新列表">🔄</button>
      </div>

      <!-- Volume -->
      <div class="volume-row">
        <span>🔈</span>
        <input type="range" min="0" max="100" value="60" class="volume-slider" id="volumeSlider">
        <span id="volumeValue" style="font-size:0.75rem; color:var(--text-sub); width:28px;">60%</span>
      </div>
    </section>

    <!-- Right Column: Queue -->
    <section class="queue-card">
      <div class="queue-header">
        <div class="queue-title">
          <span>播放队列</span>
          <span class="queue-count" id="queueCount">(0)</span>
        </div>
        <button class="btn btn-icon-text" id="btnClearQueue">清空</button>
      </div>
      <ul class="queue-list" id="queueList">
        <li class="queue-item" style="color:var(--text-sub); justify-content:center;">队列为空</li>
      </ul>
    </section>
  </main>

  <script>
    let currentState = null;
    let currentLyrics = [];
    let isSeeking = false;
    let pollTimer = null;

    const MODE_NAMES = {
      'ordered': '顺序播放',
      'ordered-loop': '顺序循环',
      'single-loop': '单曲循环',
      'random': '随机播放',
      'random-loop': '随机循环'
    };

    function formatTime(secs) {
      if (!secs || isNaN(secs)) return '00:00';
      secs = Math.max(0, Math.floor(secs));
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }

    async function sendControl(action, params = {}) {
      try {
        const res = await fetch('/api/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, params })
        });
        const data = await res.json();
        if (data.ok) {
          updateStatus(data.data);
        }
      } catch (err) {
        console.error('Control error:', err);
      }
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.ok) {
          document.getElementById('statusDot').className = 'status-dot';
          document.getElementById('statusText').innerText = '已连接';
          updateStatus(data.data);
        } else {
          document.getElementById('statusDot').className = 'status-dot offline';
          document.getElementById('statusText').innerText = '未连接 Daemon';
        }
      } catch (e) {
        document.getElementById('statusDot').className = 'status-dot offline';
        document.getElementById('statusText').innerText = '离线';
      }
    }

    async function fetchQueue() {
      try {
        const res = await fetch('/api/queue');
        const data = await res.json();
        if (data.ok && data.data && data.data.items) {
          renderQueue(data.data.items, data.data.index);
        }
      } catch (e) {
        console.error('Queue fetch error:', e);
      }
    }

    async function fetchLyrics() {
      try {
        const res = await fetch('/api/lyrics');
        const data = await res.json();
        if (data.ok && data.data && data.data.lyric) {
          parseLyrics(data.data.lyric, data.data.tlyric);
        } else {
          currentLyrics = [];
        }
      } catch (e) {
        currentLyrics = [];
      }
    }

    function parseLyrics(lyricList, tlyricList) {
      if (!Array.isArray(lyricList)) return;
      const timeRegex = /\\[(\\d{2}):(\\d{2})\\.(\\d+)\\]/;
      const parsed = [];
      for (const line of lyricList) {
        const match = timeRegex.exec(line);
        if (match) {
          const sec = parseInt(match[1]) * 60 + parseInt(match[2]) + parseFloat('0.' + match[3]);
          const text = line.replace(timeRegex, '').trim();
          if (text) parsed.push({ time: sec, text });
        }
      }
      currentLyrics = parsed.sort((a, b) => a.time - b.time);
    }

    function updateLyrics(position) {
      if (!currentLyrics || currentLyrics.length === 0) return;
      let curIndex = -1;
      for (let i = 0; i < currentLyrics.length; i++) {
        if (position >= currentLyrics[i].time) {
          curIndex = i;
        } else {
          break;
        }
      }
      if (curIndex >= 0) {
        document.getElementById('lyricCurrent').innerText = currentLyrics[curIndex].text;
        document.getElementById('lyricNext').innerText = (curIndex + 1 < currentLyrics.length) ? currentLyrics[curIndex + 1].text : '';
      }
    }

    let lastSongId = null;

    function updateStatus(data) {
      if (!data) return;
      currentState = data;

      const isPlaying = data.state === 'playing';
      document.getElementById('btnPlay').innerText = isPlaying ? '⏸' : '▶';
      document.getElementById('stateBadge').innerText = isPlaying ? '播放中' : '已暂停';
      document.getElementById('coverContainer').className = 'cover-art-container' + (isPlaying ? ' playing' : '');

      const song = data.song || {};
      document.getElementById('songTitle').innerText = song.name || '未在播放';
      const artist = song.artist || '未知歌手';
      const album = song.album ? ` < ${song.album} >` : '';
      document.getElementById('artistAlbum').innerText = artist + album;

      if (song.id !== lastSongId) {
        lastSongId = song.id;
        fetchLyrics();
        fetchQueue();
      }

      document.getElementById('modeBadge').innerText = MODE_NAMES[data.mode] || data.mode;
      document.getElementById('backendBadge').innerText = (data.backend || 'MPV').toUpperCase();

      // Progress
      const pos = data.position || 0;
      const len = data.length || (song.duration || 0);
      document.getElementById('timeCurrent').innerText = formatTime(pos);
      document.getElementById('timeTotal').innerText = formatTime(len);

      if (!isSeeking && len > 0) {
        const pct = Math.min(100, Math.max(0, (pos / len) * 100));
        document.getElementById('progressBar').style.width = pct + '%';
      }

      updateLyrics(pos);

      // Volume
      document.getElementById('volumeSlider').value = data.volume || 60;
      document.getElementById('volumeValue').innerText = (data.volume || 60) + '%';
    }

    function renderQueue(items, activeIndex) {
      const container = document.getElementById('queueList');
      document.getElementById('queueCount').innerText = `(${items.length})`;
      if (!items || items.length === 0) {
        container.innerHTML = '<li class="queue-item" style="color:var(--text-sub); justify-content:center;">播放队列为空</li>';
        return;
      }

      container.innerHTML = items.map((item, idx) => `
        <li class="queue-item ${idx === activeIndex ? 'active' : ''}" onclick="sendControl('play', { index: ${idx} })">
          <div style="display:flex; align-items:center; max-width:85%;">
            <span class="queue-index">${idx + 1}</span>
            <div class="queue-item-info">
              <span class="queue-item-name">${item.name || '未知歌曲'}</span>
              <span class="queue-item-artist">${item.artist || '未知歌手'}</span>
            </div>
          </div>
          ${idx === activeIndex ? '<span style="color:var(--accent); font-size:0.8rem;">♫</span>' : ''}
        </li>
      `).join('');
    }

    // Event Listeners
    document.getElementById('btnPlay').onclick = () => sendControl('toggle');
    document.getElementById('btnNext').onclick = () => sendControl('next');
    document.getElementById('btnPrev').onclick = () => sendControl('prev');
    document.getElementById('btnRefresh').onclick = () => { fetchStatus(); fetchQueue(); fetchLyrics(); };
    document.getElementById('btnClearQueue').onclick = () => sendControl('clear');

    const MODES = ['ordered', 'ordered-loop', 'single-loop', 'random', 'random-loop'];
    document.getElementById('btnMode').onclick = () => {
      if (!currentState) return;
      const curIdx = MODES.indexOf(currentState.mode);
      const nextMode = MODES[(curIdx + 1) % MODES.length];
      sendControl('mode', { mode: nextMode });
    };

    document.getElementById('volumeSlider').oninput = (e) => {
      const val = parseInt(e.target.value);
      document.getElementById('volumeValue').innerText = val + '%';
    };
    document.getElementById('volumeSlider').onchange = (e) => {
      const val = parseInt(e.target.value);
      sendControl('volume', { value: val });
    };

    // Seek Click
    document.getElementById('progressContainer').onclick = (e) => {
      if (!currentState) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      const total = currentState.length || (currentState.song ? currentState.song.duration : 0);
      if (total > 0) {
        const targetSec = Math.floor(pct * total);
        sendControl('seek', { seconds: targetSec, relative: false });
      }
    };

    // Init & Loop
    fetchStatus();
    fetchQueue();
    fetchLyrics();
    pollTimer = setInterval(fetchStatus, 1000);
  </script>
</body>
</html>
"""


class MusicboxWebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler for Musicbox Web Interface & REST API."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Suppress standard logging to keep stdout clean
        pass

    def _send_json(self, data: dict[str, Any], status_code: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            payload = _HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/status":
            try:
                resp = send_request("player.status")
                self._send_json(resp)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/queue":
            try:
                resp = send_request("queue.list")
                self._send_json(resp)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/lyrics":
            try:
                resp = send_request("player.lyrics")
                self._send_json(resp)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/control":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}

            action = data.get("action", "")
            params = data.get("params") or {}

            rpc_map = {
                "toggle": ("player.toggle", {}),
                "pause": ("player.pause", {}),
                "resume": ("player.resume", {}),
                "next": ("player.next", {}),
                "prev": ("player.prev", {}),
                "stop": ("player.stop", {}),
                "volume": ("player.volume", {"value": params.get("value")}),
                "mode": ("player.mode", {"mode": params.get("mode")}),
                "seek": (
                    "player.seek",
                    {
                        "seconds": params.get("seconds", 0),
                        "relative": params.get("relative", False),
                    },
                ),
                "play": ("queue.play", {"index": params.get("index", 0)}),
                "clear": ("queue.clear", {}),
            }

            if action not in rpc_map:
                self._send_json(
                    {"ok": False, "error": f"Unknown action: {action}"}, 400
                )
                return

            method, rpc_params = rpc_map[action]
            try:
                resp = send_request(method, rpc_params)
                self._send_json(resp)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        self.send_response(404)
        self.end_headers()


def run_web_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> int:
    """Start the web server to display now playing and queue."""
    if not is_daemon_running():
        spawn_daemon()

    server_address = (host, port)
    try:
        httpd = http.server.ThreadingHTTPServer(server_address, MusicboxWebHandler)
    except OSError as exc:
        print(f"无法在 {host}:{port} 启动 Web 服务: {exc}", file=sys.stderr)
        return 1

    url = f"http://{host}:{port}/"
    print("=" * 60)
    print(f"  ♫ MusicBox Web 控制台已启动: {url}")
    print("  在浏览器中打开即可查看当前播放进度、歌词与播放列表")
    print("  按 Ctrl + C 停止 Web 服务")
    print("=" * 60)

    if open_browser:
        threading.Thread(
            target=lambda: (time.sleep(0.5), webbrowser.open(url)), daemon=True
        ).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 Web 服务...")
    finally:
        httpd.server_close()
    return 0
