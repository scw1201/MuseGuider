// frontend/src/app/controller.ts

import { AudioEngine } from '../audio/AudioEngine'
import { TTSClient } from '../net/TTSClient'
import { VideoEngine } from '../video/VideoEngine'
import { updateStatus, showCaption, hideCaption, renderSuggestedActions } from './ui'
import type { getUI } from './ui'
import { PERSONAS, type PersonaInfo } from './personas'
import type { PCMChunk, LLMResponse, SuggestedAction } from '../net/types'

type UI = ReturnType<typeof getUI>

type DomainExhibit = {
  id: string
  name: string
  image?: string
}

type DomainZone = {
  id: string
  name: string
  exhibits: DomainExhibit[]
  previewImage?: string
}

const PROGRESS_ZONE_IDS = new Set([
  'zone_chinese_origins',
  'zone_calligraphy_painting',
  'zone_world_classics',
  'zone_children_exploration',
])

export function createController(ui: UI) {
  const audio = new AudioEngine(24000)
  const tts = new TTSClient()
  const video = new VideoEngine(ui.video)
  const zoneLocationMap = new Map<string, { floor?: string; area?: string }>()
  const zoneBgMap = new Map<string, string>()
  const zoneNameToId = new Map<string, string>()
  const exhibitNameToId = new Map<string, string>()
  const exhibitIdToImage = new Map<string, string>()
  const zoneIdToPreviewImage = new Map<string, string>()
  const progressZones: DomainZone[] = []
  const visitedZoneIds = new Set<string>()
  const visitedExhibitIds = new Set<string>()
  let currentZoneId = ''
  let currentExhibitId = ''
  let currentBgId = 'zone_front_desk'
  let bgTimer: number | null = null

  const personaMap = new Map<string, PersonaInfo>(
    PERSONAS.map(p => [p.id, p])
  )
  const startGuideTextMap = new Map<string, string>(
    PERSONAS.map(p => [p.id, p.startGuideText || '开始导览'])
  )

  let currentPersonaId = 'woman_demo'
  let hasConversationStarted = false
  const sessionId =
    globalThis.crypto?.randomUUID?.() ||
    `sid_${Date.now()}_${Math.random().toString(16).slice(2)}`

  function renderPersonaList() {
    if (!ui.personaList) return
    ui.personaList.innerHTML = PERSONAS.map(p => `
      <button class="persona-item" data-id="${p.id}">
        <img src="${p.avatar}" class="persona-item-avatar" />
        <div class="persona-item-meta">
          <div class="persona-item-name">${p.name}</div>
          <div class="persona-item-role">${p.role}</div>
        </div>
      </button>
    `).join('')

    ui.personaList
      .querySelectorAll<HTMLButtonElement>('.persona-item')
      .forEach((btn: HTMLButtonElement) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.id
          if (!id) return
          setPersona(id)
        })
      })
  }

  function trimContext(text: string, max = 36) {
    if (!text) return '—'
    const clean = text.replace(/\s+/g, ' ').trim()
    if (clean.length <= max) return clean
    return `${clean.slice(0, max)}…`
  }

  function formatZoneDisplay(
    zoneName: string,
    venue?: string,
    floor?: string,
    area?: string
  ) {
    const name = zoneName || '展馆前台'
    const loc = zoneLocationMap.get(name) || {}
    const resolvedVenue = venue || '中华世纪坛'
    const resolvedFloor = floor || loc.floor || ''
    const resolvedArea = area || loc.area || ''
    const parts = [resolvedVenue, resolvedFloor, resolvedArea, name].filter(Boolean)
    return parts.join(' · ')
  }

  function floorKeyFromLabel(label: string) {
    const value = (label || '').trim()
    if (!value) return ''
    if (value.includes('地下二层') || value === 'B2') return 'b2'
    if (value.includes('地下三层') || value === 'B3') return 'b3'
    if (value.includes('地下一层') || value === 'B1') return 'b1'
    if (value.includes('展馆二层') || value === 'F2' || value === '2F') return 'f2'
    if (value.includes('展馆一层') || value === 'F1' || value === '1F') return 'f1'
    return ''
  }

  function updateContextMap(floorLabel: string) {
    if (!ui.contextMap) return
    const key = floorKeyFromLabel(floorLabel)
    if (!key) {
      ui.contextMap.style.display = 'none'
      return
    }
    ui.contextMap.src = `/imgs/floor/${key}.png`
    ui.contextMap.style.display = 'block'
  }

  async function loadZoneFloors() {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/domain_prior')
      const data = await res.json()
      for (const zone of data.zones || []) {
        const loc = zone.location || {}
        const floor = loc.floor
        const area = loc.area
        const name = zone.name
        const id = zone.id
        if (name) {
          zoneLocationMap.set(name, { floor, area })
          if (id) {
            zoneNameToId.set(String(name), String(id))
          }
          if (String(name).includes('前台')) {
            zoneLocationMap.set('展馆前台', { floor, area })
            zoneBgMap.set('展馆前台', 'zone_front_desk')
          }
          if (id) {
            zoneBgMap.set(name, id)
          }
        }
        if (id) {
          zoneBgMap.set(id, id)
          zoneIdToPreviewImage.set(String(id), `/bgs/${id}.png`)
        }
        if (!PROGRESS_ZONE_IDS.has(String(id || ''))) {
          continue
        }
        const exhibits: DomainExhibit[] = (zone.exhibits || []).map((exhibit: any) => {
          const exhibitId = String(exhibit.id || '')
          const exhibitName = String(exhibit.name || '')
          const exhibitImage = String(exhibit.image || '')
          if (exhibitName && exhibitId) {
            exhibitNameToId.set(exhibitName, exhibitId)
          }
          if (exhibitId && exhibitImage) {
            exhibitIdToImage.set(exhibitId, exhibitImage)
          }
          return {
            id: exhibitId,
            name: exhibitName,
            image: exhibitImage,
          }
        })
        progressZones.push({
          id: String(id || ''),
          name: String(name || ''),
          exhibits,
          previewImage: id ? `/bgs/${id}.png` : '',
        })
      }
      renderTourProgress()
      renderProgressPreview()
    } catch {
      // ignore failures; fall back to zone name only
    }
  }

  function renderTourProgress() {
    if (!ui.progressRoot) return
    ui.progressRoot.innerHTML = progressZones.map(zone => {
      const zoneVisited = visitedZoneIds.has(zone.id)
      const zoneCurrent = currentZoneId === zone.id
      const exhibitItems = zone.exhibits.map(exhibit => {
        const visited = visitedExhibitIds.has(exhibit.id)
        const current = currentExhibitId === exhibit.id
        return `
          <div class="progress-exhibit ${current ? 'current' : visited ? 'visited' : 'pending'}">
            <span class="progress-dot"></span>
            <span class="progress-name">${exhibit.name}</span>
          </div>
        `
      }).join('')

      return `
        <section class="progress-zone ${zoneCurrent ? 'current' : zoneVisited ? 'visited' : 'pending'}">
          <div class="progress-zone-header">
            <span class="progress-zone-dot"></span>
            <span class="progress-zone-name">${zone.name}</span>
          </div>
          <div class="progress-exhibit-list">
            ${exhibitItems}
          </div>
        </section>
      `
    }).join('')
  }

  function resetTourProgress() {
    visitedZoneIds.clear()
    visitedExhibitIds.clear()
    currentZoneId = ''
    currentExhibitId = ''
    renderTourProgress()
    renderProgressPreview()
  }

  function updateTourProgress(zoneName?: string, exhibitName?: string) {
    const zoneId = zoneName ? zoneNameToId.get(zoneName) : ''
    const exhibitId = exhibitName ? exhibitNameToId.get(exhibitName) : ''
    currentZoneId = zoneId || ''
    currentExhibitId = exhibitId || ''
    if (zoneId) {
      visitedZoneIds.add(zoneId)
    }
    if (exhibitId) {
      visitedExhibitIds.add(exhibitId)
    }
    renderTourProgress()
    renderProgressPreview()
  }

  function syncTourProgressFromResponse(data: LLMResponse) {
    const visitedZoneNames = data.visited_zones || []
    const visitedExhibitNames = data.visited_exhibits || []
    visitedZoneIds.clear()
    visitedExhibitIds.clear()

    for (const zoneName of visitedZoneNames) {
      const zoneId = zoneNameToId.get(zoneName)
      if (zoneId) visitedZoneIds.add(zoneId)
    }
    for (const exhibitName of visitedExhibitNames) {
      const exhibitId = exhibitNameToId.get(exhibitName)
      if (exhibitId) visitedExhibitIds.add(exhibitId)
    }

    currentZoneId = data.current_zone ? (zoneNameToId.get(data.current_zone) || '') : ''
    currentExhibitId = data.current_exhibit ? (exhibitNameToId.get(data.current_exhibit) || '') : ''

    if (!visitedZoneNames.length && !visitedExhibitNames.length) {
      updateTourProgress(data.guide_zone, data.focus_exhibit)
      return
    }
    renderTourProgress()
    renderProgressPreview()
  }

  function renderProgressPreview() {
    if (!ui.progressPreviewTitle || !ui.progressPreviewImage || !ui.progressPreviewEmpty) return

    const exhibitImage = currentExhibitId ? exhibitIdToImage.get(currentExhibitId) || '' : ''
    const zoneImage = currentZoneId ? zoneIdToPreviewImage.get(currentZoneId) || '' : ''
    const previewImage = currentExhibitId ? exhibitImage : zoneImage

    const currentZoneName =
      progressZones.find(zone => zone.id === currentZoneId)?.name || '尚未进入展区'
    const currentExhibitName =
      progressZones
        .flatMap(zone => zone.exhibits)
        .find(exhibit => exhibit.id === currentExhibitId)?.name || ''

    ui.progressPreviewTitle.textContent = currentExhibitName || currentZoneName

    if (previewImage) {
      ui.progressPreviewImage.src = previewImage
      ui.progressPreviewImage.classList.remove('hidden')
      ui.progressPreviewEmpty.classList.add('hidden')
      return
    }

    ui.progressPreviewImage.removeAttribute('src')
    ui.progressPreviewImage.classList.add('hidden')
    ui.progressPreviewEmpty.classList.remove('hidden')
  }

  function updateStageBg(zoneKey: string) {
    if (!ui.avatarFrame) return
    const bgId = zoneBgMap.get(zoneKey || '') || 'zone_front_desk'
    if (bgId === currentBgId) return
    currentBgId = bgId
    if (bgTimer) window.clearTimeout(bgTimer)
    ui.avatarFrame.classList.add('bg-fade')
    bgTimer = window.setTimeout(() => {
      ui.avatarFrame.style.setProperty('--stage-bg', `url('/bgs/${bgId}.png')`)
      ui.avatarFrame.classList.remove('bg-fade')
    }, 180)
  }

  function setSidebarPanel(panel: 'personas' | 'progress') {
    ui.personaTab?.classList.toggle('active', panel === 'personas')
    ui.progressTab?.classList.toggle('active', panel === 'progress')
    ui.personaSidebarPanel?.classList.toggle('active', panel === 'personas')
    ui.progressSidebarPanel?.classList.toggle('active', panel === 'progress')
  }

  function setPersona(id: string) {
    const persona = personaMap.get(id)
    if (!persona) return

    ui.stageCard?.classList.add('persona-changing')
    ui.personaPanel?.classList.add('persona-changing')
    ui.avatarFrame?.classList.add('persona-changing')

    window.setTimeout(() => {
      currentPersonaId = id
      video.setPersona(persona.videoDir, persona.videoDir)
      video.setState('IDLE')

      if (ui.personaAvatar) ui.personaAvatar.src = persona.avatar
    if (ui.personaName) ui.personaName.textContent = persona.name
    if (ui.personaRole) ui.personaRole.textContent = persona.role
    if (ui.personaBio) ui.personaBio.textContent = persona.bio
    if (ui.badgeDesc) ui.badgeDesc.textContent = persona.stateDescriptions.IDLE
    if (ui.badgeText) ui.badgeText.textContent = ''
    if (ui.contextUser) ui.contextUser.textContent = '等待咨询'
    if (ui.contextAnchor) ui.contextAnchor.textContent = '未确定'
    if (ui.contextZone) {
      ui.contextZone.textContent = formatZoneDisplay('展馆前台').replace(/^中华世纪坛 · /, '')
    }
    updateContextMap('展馆一层')
    updateStageBg('展馆前台')
    if (ui.contextStage) ui.contextStage.textContent = '准备阶段'
    if (ui.contextPathHint) ui.contextPathHint.textContent = '—'
    if (ui.contextHint) ui.contextHint.style.display = 'none'
    if (ui.startGuideBtn) {
      ui.startGuideBtn.textContent =
        startGuideTextMap.get(id) || persona.startGuideText || '开始导览'
    }
    hasConversationStarted = false
    resetTourProgress()
    renderSuggestionButtons([])

    ui.personaList
        ?.querySelectorAll<HTMLButtonElement>('.persona-item')
        .forEach((item: HTMLButtonElement) => {
        item.classList.toggle('active', item.getAttribute('data-id') === id)
      })

      window.setTimeout(() => {
        ui.stageCard?.classList.remove('persona-changing')
        ui.personaPanel?.classList.remove('persona-changing')
        ui.avatarFrame?.classList.remove('persona-changing')
      }, 320)
    }, 240)
  }

  if (ui.personaToggle && ui.personaSidebar) {
    ui.personaToggle.onclick = () => {
      ui.personaSidebar.classList.toggle('collapsed')
      ui.stageCard?.classList.toggle('sidebar-collapsed')
    }
  }

  ui.personaTab?.addEventListener('click', () => setSidebarPanel('personas'))
  ui.progressTab?.addEventListener('click', () => setSidebarPanel('progress'))

  renderPersonaList()
  setSidebarPanel('personas')
  setPersona(currentPersonaId)
  loadZoneFloors()
  loadPersonaCopy()

  function renderSuggestionButtons(actions: SuggestedAction[]) {
    if (!hasConversationStarted && !actions.length) {
      renderSuggestedActions(ui, [])
      return
    }
    renderSuggestedActions(ui, actions)
    ui.suggestionRow
      ?.querySelectorAll<HTMLButtonElement>('.suggestion-chip')
      .forEach((button: HTMLButtonElement) => {
        button.addEventListener('click', () => {
          const text = button.dataset.text?.trim()
          if (!text) return
          submitUserInput(text, 'chip')
        })
      })
  }

  function normalizeUserInput(text: string) {
    return text.replace(/\s+/g, ' ').trim()
  }

  async function requestLLM(text: string) {
    const res = await fetch('http://127.0.0.1:8000/api/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        persona_id: currentPersonaId,
        session_id: sessionId,
      }),
    })

    if (!res.ok) {
      throw new Error(`LLM request failed with ${res.status}`)
    }

    return (await res.json()) as LLMResponse
  }

  function applyLLMResponse(data: LLMResponse) {
    if (data.video_dir || data.video_prefix) {
      const dir = data.video_dir || 'woman_demo'
      const prefix = data.video_prefix || data.video_dir || dir
      console.log('[Persona] from API', {
        video_dir: data.video_dir,
        video_prefix: data.video_prefix,
        resolved: { dir, prefix },
      })
      video.setPersona(dir, prefix)
    }

    if (data.tts_text) {
      showCaption(ui, data.tts_text, 'final')
    }

    if (ui.contextZone) {
      const zoneName = data.current_zone || data.guide_zone || '展馆前台'
      const floor = data.guide_floor || ''
      const area = data.guide_area || ''
      const parts = [floor, area, zoneName].filter(Boolean)
      ui.contextZone.textContent = trimContext(parts.join(' · '), 26)
      updateContextMap(floor)
      updateStageBg(zoneName)
    }

    if (ui.contextStage) {
      ui.contextStage.textContent = trimContext(data.guide_stage || '准备阶段', 16)
    }

    if (ui.contextAnchor) {
      ui.contextAnchor.textContent = trimContext(data.current_exhibit || data.focus_exhibit || '未确定', 20)
    }

    if (ui.contextUser) {
      ui.contextUser.textContent = trimContext(data.user_intent || '了解信息', 20)
    }

    syncTourProgressFromResponse(data)

    if (ui.contextHint && ui.contextPathHint) {
      ui.contextHint.style.display = 'none'
    }

    hasConversationStarted = true
    renderSuggestionButtons(data.suggested_actions || [])

    if (data.video_state) {
      const persona = personaMap.get(currentPersonaId)
      const desc = persona?.stateDescriptions[data.video_state] || ''
      updateStatus(ui, 'speaking…', undefined, desc)
      video.setState(data.video_state)
    }

    if (data.tts_text) {
      tts.stream(
        data.tts_text,
        () => {},
        (pcm: PCMChunk) => audio.enqueuePCM(pcm),
        data.tts_voice_type
      )
    } else {
      video.setState('IDLE')
      const persona = personaMap.get(currentPersonaId)
      const desc = persona?.stateDescriptions.IDLE || '静待观众'
      updateStatus(ui, 'idle', undefined, desc)
    }
  }

  audio.onFinish = () => {
    const persona = personaMap.get(currentPersonaId)
    const desc = persona?.stateDescriptions.IDLE || '静待观众'
    updateStatus(ui, 'idle', undefined, desc)
    video.setState('IDLE')
    hideCaption(ui)
  }

  async function submitUserInput(rawText: string, source: 'text' | 'voice' | 'chip' | 'start' = 'text') {
    const text = normalizeUserInput(rawText)
    if (!text) return

    await audio.resume()
    showCaption(ui, text, 'partial')
    updateStatus(ui, source === 'voice' ? 'Recognizing...' : 'Thinking...', undefined)

    try {
      const data = await requestLLM(text)
      applyLLMResponse(data)
    } catch {
      const persona = personaMap.get(currentPersonaId)
      const desc = persona?.stateDescriptions.IDLE || '静待观众'
      updateStatus(ui, 'idle', undefined, desc)
      video.setState('IDLE')
      renderSuggestionButtons([])
    }
  }

  async function loadPersonaCopy() {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/personas')
      const data = await res.json()
      Object.entries(data || {}).forEach(([id, info]: any) => {
        if (!id || !info) return
        if (info.start_guide_text) {
          startGuideTextMap.set(id, String(info.start_guide_text))
        }
      })
      setPersona(currentPersonaId)
    } catch {
      // ignore failures; keep defaults from frontend
    }
  }

  function getStartGuideCommand() {
    const persona = personaMap.get(currentPersonaId)
    return startGuideTextMap.get(currentPersonaId) || persona?.startGuideText || '开始导览'
  }

  return { send: submitUserInput, submitUserInput, getStartGuideCommand }
}
