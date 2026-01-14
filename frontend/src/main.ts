import './style.css'
import {
  renderApp,
  getUI,
  showCaption,
  hideCaption,
  updateStatus,
} from './app/ui'
import { createController } from './app/controller'
import { ASRClient } from './net/ASRClient'

window.addEventListener('DOMContentLoaded', () => {
  const app = document.getElementById('app')
  if (!app) return

  renderApp(app)
  document.body.insertAdjacentHTML(
    'beforeend',
    `
      <footer class="chatbar">
        <div class="caption" id="caption">
          <p id="captionText"></p>
        </div>
        <div class="chat-inner">
          <button id="startGuide" class="chat-start">开始导览</button>

          <input
            id="input"
            class="chat-input"
            placeholder="围绕当前展品继续探索"
          />

          <button id="voice" class="chat-voice" title="语音输入">
            <span class="voice-dot"></span>
            <span class="voice-wave">
              <i></i><i></i><i></i><i></i>
            </span>
          </button>

          <button id="send" class="chat-send">发送</button>
        </div>
      </footer>
    `
  )

  const ui = getUI()
  const controller = createController(ui)

  const pages: Record<string, HTMLElement | null> = {
    home: ui.homePage,
    route: ui.routePage,
    collections: ui.collectionsPage,
  }

  let collectionsLoaded = false
  let routeLoaded = false

  const renderCollections = (data: any) => {
    const zones = (data.zones || []).filter(
      (z: any) => z.visibility?.collections !== false
    )
    return zones.map((z: any) => {
      const loc = z.location || {}
      const locParts = [loc.floor, loc.area].filter(Boolean).join(' · ')
      const exhibits = (z.exhibits || []).map((e: any) => {
        const alias = (e.aliases || []).slice(0, 3).join(' / ')
        const img = e.image ? `<img class="exhibit-thumb" src="${e.image}" alt="${e.name}" />` : ''
        return `
          <div class="exhibit-card">
            ${img}
            <div class="exhibit-title">${e.name}</div>
            <div class="exhibit-meta">${[e.era, e.origin, e.material].filter(Boolean).join(' · ')}</div>
            <div class="exhibit-desc">${e.description || ''}</div>
            ${alias ? `<div class="exhibit-alias">别名：${alias}</div>` : ''}
          </div>
        `
      }).join('')

      return `
        <section class="zone-card">
          <div class="zone-header">
            <div class="zone-name">${z.name}</div>
            <div class="zone-loc">${locParts}</div>
          </div>
          <div class="zone-intro">${z.intro || ''}</div>
          <div class="exhibit-grid">${exhibits}</div>
        </section>
      `
    }).join('')
  }

  const loadCollections = async () => {
    if (collectionsLoaded || !ui.collectionsRoot) return
    const res = await fetch('http://127.0.0.1:8000/api/domain_prior')
    const data = await res.json()
    ui.collectionsRoot.innerHTML = renderCollections(data)
    collectionsLoaded = true
  }

  const floorOrder = (floor: string) => {
    if (!floor) return 99
    if (floor.includes('展馆二层')) return -100
    if (floor.includes('展馆一层')) return -90
    if (floor.includes('地下一层')) return 10
    if (floor.includes('地下二层')) return 20
    const match = floor.match(/B(\\d+)/i)
    if (match) return -parseInt(match[1], 10)
    const level = floor.match(/(\\d+)/)
    if (level) return parseInt(level[1], 10)
    return 50
  }

  type RouteNode = { zone: any; floor: string; area: string }

  const renderRoute = (data: any) => {
    const zones = (data.zones || []).filter(
      (z: any) => z.visibility?.route !== false
    )
    const withLoc: RouteNode[] = zones.map((z: any) => {
      const loc = z.location || {}
      return {
        zone: z,
        floor: loc.floor || '未标注楼层',
        area: loc.area || '未标注区域',
      }
    })

    withLoc.sort((a, b) => {
      const f = floorOrder(a.floor) - floorOrder(b.floor)
      if (f !== 0) return f
      return a.area.localeCompare(b.area, 'zh-Hans-CN')
    })

    const floors: Record<string, Record<string, any[]>> = {}
    for (const item of withLoc) {
      if (!floors[item.floor]) floors[item.floor] = {}
      if (!floors[item.floor][item.area]) floors[item.floor][item.area] = []
      floors[item.floor][item.area].push(item.zone)
    }

    const floorBlocks = Object.entries(floors).map(([floor, areas]) => {
      const areaNames = Object.keys(areas)
      const areaCols = areaNames.map((area, idx) => {
        const nodes = areas[area].map((z: any) => `
          <div class="map-node">
            <div class="map-node-title">${z.name}</div>
            <div class="map-node-meta">${area}</div>
          </div>
        `).join('')
        return `
          <div class="map-area">
            <div class="map-area-label">${area}</div>
            <div class="map-node-stack">${nodes}</div>
            ${idx < areaNames.length - 1 ? '<div class="map-connector"></div>' : ''}
          </div>
        `
      }).join('')

      return `
        <section class="map-floor">
          <div class="map-floor-label">${floor}</div>
          <div class="map-row">
            ${areaCols}
          </div>
        </section>
      `
    }).join('')

    return `
      <div class="map-shell">
        ${floorBlocks || '<div class="map-empty">暂无路线数据</div>'}
      </div>
    `
  }

  const loadRoute = async () => {
    if (routeLoaded || !ui.routeRoot) return
    const res = await fetch('http://127.0.0.1:8000/api/domain_prior')
    const data = await res.json()
    ui.routeRoot.innerHTML = renderRoute(data)
    routeLoaded = true
  }

  const showPage = async (page: string) => {
    if (page === 'home') {
      document.body.classList.add('mode-home')
    } else {
      document.body.classList.remove('mode-home')
    }
    Object.entries(pages).forEach(([key, el]) => {
      if (!el) return
      if (key === page) {
        el.classList.remove('hidden', 'exiting', 'active')
        // force reflow to restart transition when returning
        void el.offsetWidth
        window.requestAnimationFrame(() => {
          el.classList.add('active')
        })
        return
      }
      if (!el.classList.contains('hidden')) {
        el.classList.remove('active')
        el.classList.add('exiting')
        window.setTimeout(() => {
          el.classList.add('hidden')
          el.classList.remove('exiting')
        }, 360)
      } else {
        el.classList.remove('active', 'exiting')
      }
    })
    ui.navLinks?.forEach(link => {
      link.classList.toggle('active', link.dataset.page === page)
    })
    if (page === 'collections') {
      await loadCollections()
    }
    if (page === 'route') {
      await loadRoute()
    }
  }

  showPage('home')

  ui.navLinks?.forEach(link => {
    link.onclick = async (e) => {
      e.preventDefault()
      const page = link.dataset.page || 'home'
      await showPage(page)
    }
  })

  /* ============================
     键盘输入
     ============================ */
  ui.startGuideBtn.onclick = () => {
    controller.send(controller.getStartGuideCommand())
  }

  ui.sendBtn.onclick = () => {
    const text = ui.input.value.trim()
    if (!text) return

    controller.send(text)
    ui.input.value = ''
  }

  /* ============================
     语音输入（点一下开始，再点一下直接发 LLM）
     ============================ */
  const asr = new ASRClient()
  let recording = false

  ui.voiceBtn.onclick = async () => {
    /* ---------- 开始录音 ---------- */
    if (!recording) {
      recording = true

      console.log('[UI] start recording')

      ui.voiceBtn.classList.add('listening')

      // UI 状态
      updateStatus(ui, 'Listening...', 'listening')
      hideCaption(ui)

      asr.start()
      return
    }

    /* ---------- 停止录音 & 直接送 LLM ---------- */
    recording = false

    console.log('[UI] stop recording')

    ui.voiceBtn.classList.remove('listening')

    updateStatus(ui, 'Recognizing...', 'idle')

    // 🔥 等 ASR 最终文本
    const text = await asr.stopAndGetFinalText()

    console.log('[UI] ASR final text:', text)

    if (!text) {
      updateStatus(ui, 'Idle', 'idle')
      return
    }

    // 1️⃣ 显示字幕（你已经有的 Caption）
    showCaption(ui, text)

    // 2️⃣ 状态反馈
    updateStatus(ui, 'Recognized', 'idle')

    // 3️⃣ 👈 直接发给 LLM（不需要再点发送）
    controller.send(text)
  }
})
