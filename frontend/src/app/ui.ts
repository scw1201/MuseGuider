// frontend/src/app/ui.ts

/* ============================
   Render
   ============================ */
export function renderApp(root: HTMLElement) {
  root.innerHTML = `
    <!-- 顶部导航 -->
    <header class="navbar">
      <div class="nav-inner">
        <div class="nav-brand">
          <img src="/logo.png" class="nav-logo" />
          <div class="nav-title">
            <span class="nav-title-main">中华世纪坛</span>
            <span class="nav-title-sub">导览数字人系统</span>
          </div>
        </div>
        <nav class="nav-links">
          <a href="#" class="nav-link active" data-page="home">导览大厅</a>
          <a href="#" class="nav-link" data-page="route">展陈路线</a>
          <a href="#" class="nav-link" data-page="collections">数字典藏</a>
        </nav>
        <div class="nav-meta">开放时间 09:00–17:00</div>
      </div>
    </header>

    <!-- 主舞台区域 -->
    <main class="stage-wrap page" id="homePage">
      <div class="stage-card" id="stageCard">
        <!-- 侧边人物栏 -->
        <aside class="persona-sidebar" id="personaSidebar">
          <div class="persona-header">
            <button class="persona-toggle" id="personaToggle" title="展开/收起">
              ☰
            </button>
            <div class="sidebar-tabs" id="sidebarTabs">
              <button class="sidebar-tab active" id="personaTab" data-panel="personas" type="button">
                人物选择
              </button>
              <button class="sidebar-tab" id="progressTab" data-panel="progress" type="button">
                导览进程
              </button>
            </div>
          </div>
          <div class="sidebar-panel active" id="personaSidebarPanel">
            <div class="persona-list" id="personaList"></div>
          </div>
          <div class="sidebar-panel" id="progressSidebarPanel">
            <div class="progress-root" id="progressRoot"></div>
            <div class="progress-preview" id="progressPreview">
              <div class="progress-preview-label" id="progressPreviewLabel">当前导览预览</div>
              <div class="progress-preview-title" id="progressPreviewTitle">尚未进入展区</div>
              <img class="progress-preview-image hidden" id="progressPreviewImage" alt="当前展区或展品预览" />
              <div class="progress-preview-empty" id="progressPreviewEmpty">开始导览后，这里会显示当前展区或展品图片。</div>
            </div>
          </div>
        </aside>

        <!-- 当前人物信息 -->
        <section class="persona-panel" id="personaPanel">
          <img id="personaAvatar" class="persona-avatar" />
          <div class="persona-meta">
            <div class="persona-name" id="personaName"></div>
            <div class="persona-role" id="personaRole"></div>
            <div class="persona-bio" id="personaBio"></div>
          </div>
        </section>

        <!-- 导览学习情境 -->
        <section class="context-panel" id="contextPanel">
          <div class="context-title">导览学习情境</div>
          <div class="context-line">
            <span class="context-label">当前位置</span>
            <span class="context-text" id="contextZone">展馆前台</span>
          </div>
          <div class="context-line">
            <span class="context-label">导览阶段</span>
            <span class="context-text" id="contextStage">准备阶段</span>
          </div>
          <div class="context-line">
            <span class="context-label">关注展品</span>
            <span class="context-text" id="contextAnchor">—</span>
          </div>
          <div class="context-line">
            <span class="context-label">用户意图</span>
            <span class="context-text" id="contextUser">—</span>
          </div>
          <div class="context-line context-hint" id="contextHint">
            <span class="context-label">路径提示</span>
            <span class="context-text" id="contextPathHint">—</span>
          </div>
          <div class="context-map">
            <img id="contextMap" class="context-map-img" alt="当前位置示意图" />
          </div>
        </section>

        <div class="avatar-frame" id="avatarFrame">
          <video
            id="avatar"
            autoplay
            muted
            loop
            playsinline
          ></video>
        </div>

        <!-- 状态徽标 -->
        <div class="badge idle" id="badge">
          <span class="badge-dot"></span>
          <div class="badge-texts">
            <span id="badgeText"></span>
            <span id="badgeDesc">静待观众</span>
          </div>
        </div>
      </div>
    </main>

    <section class="route-page page hidden" id="routePage">
      <div class="collections-hero">
        <div class="collections-hero-title">展陈路线</div>
        <div class="collections-hero-sub">按空间顺序浏览展区与关键展品</div>
      </div>
      <div class="route-layout">
        <aside class="route-floor">
          <img src="/imgs/floor/floors_all.png" alt="展馆楼层总览" />
        </aside>
        <div class="route-root" id="routeRoot"></div>
      </div>
    </section>

    <section class="collections-page page hidden" id="collectionsPage">
      <div class="collections-hero">
        <div class="collections-hero-title">数字典藏</div>
        <div class="collections-hero-sub">中华世纪坛导览 · 展区与展品总览</div>
      </div>
      <div class="collections-root" id="collectionsRoot"></div>
    </section>

  `
}

/* ============================
   UI Getter
   ============================ */
export function getUI() {
  return {
    // video
    video: document.getElementById('avatar') as HTMLVideoElement,
    stageCard: document.getElementById('stageCard') as HTMLDivElement,
    avatarFrame: document.getElementById('avatarFrame') as HTMLDivElement,
    personaSidebar: document.getElementById('personaSidebar') as HTMLDivElement,
    personaToggle: document.getElementById('personaToggle') as HTMLButtonElement,
    personaTab: document.getElementById('personaTab') as HTMLButtonElement,
    progressTab: document.getElementById('progressTab') as HTMLButtonElement,
    personaSidebarPanel: document.getElementById('personaSidebarPanel') as HTMLDivElement,
    progressSidebarPanel: document.getElementById('progressSidebarPanel') as HTMLDivElement,
    personaList: document.getElementById('personaList') as HTMLDivElement,
    progressRoot: document.getElementById('progressRoot') as HTMLDivElement,
    progressPreview: document.getElementById('progressPreview') as HTMLDivElement,
    progressPreviewLabel: document.getElementById('progressPreviewLabel') as HTMLDivElement,
    progressPreviewTitle: document.getElementById('progressPreviewTitle') as HTMLDivElement,
    progressPreviewImage: document.getElementById('progressPreviewImage') as HTMLImageElement,
    progressPreviewEmpty: document.getElementById('progressPreviewEmpty') as HTMLDivElement,
    personaPanel: document.getElementById('personaPanel') as HTMLDivElement,
    personaAvatar: document.getElementById('personaAvatar') as HTMLImageElement,
    personaName: document.getElementById('personaName') as HTMLDivElement,
    personaRole: document.getElementById('personaRole') as HTMLDivElement,
    personaBio: document.getElementById('personaBio') as HTMLDivElement,
    contextPanel: document.getElementById('contextPanel') as HTMLDivElement,
    contextMap: document.getElementById('contextMap') as HTMLImageElement,
    contextZone: document.getElementById('contextZone') as HTMLSpanElement,
    contextStage: document.getElementById('contextStage') as HTMLSpanElement,
    contextAnchor: document.getElementById('contextAnchor') as HTMLSpanElement,
    contextUser: document.getElementById('contextUser') as HTMLSpanElement,
    contextGuide: document.getElementById('contextGuide') as HTMLSpanElement,
    contextHint: document.getElementById('contextHint') as HTMLDivElement,
    contextPathHint: document.getElementById('contextPathHint') as HTMLSpanElement,
    navLinks: document.querySelectorAll('.nav-link') as NodeListOf<HTMLAnchorElement>,
    homePage: document.getElementById('homePage') as HTMLElement,
    routePage: document.getElementById('routePage') as HTMLElement,
    routeRoot: document.getElementById('routeRoot') as HTMLDivElement,
    collectionsPage: document.getElementById('collectionsPage') as HTMLElement,
    collectionsRoot: document.getElementById('collectionsRoot') as HTMLDivElement,

    // input
    input: document.getElementById('input') as HTMLInputElement,
    sendBtn: document.getElementById('send') as HTMLButtonElement,
    startGuideBtn: document.getElementById('startGuide') as HTMLButtonElement,
    suggestionRow: document.getElementById('suggestionRow') as HTMLDivElement,

    // 🎤 voice
    voiceBtn: document.getElementById('voice') as HTMLButtonElement,

    // caption
    caption: document.getElementById('caption') as HTMLDivElement,
    captionText: document.getElementById(
      'captionText'
    ) as HTMLParagraphElement,

    // status
    badge: document.getElementById('badge') as HTMLDivElement,
    badgeText: document.getElementById(
      'badgeText'
    ) as HTMLSpanElement,
    badgeDesc: document.getElementById(
      'badgeDesc'
    ) as HTMLSpanElement,
    statusText: document.getElementById(
      'statusText'
    ) as HTMLSpanElement,
  }
}

/* ============================
   UI Mutators
   ============================ */
export function updateStatus(
  ui: ReturnType<typeof getUI>,
  text: string,
  state?: string,
  desc?: string
) {
  if (ui.statusText) {
    ui.statusText.textContent = text
  }

  if (state && ui.badge && ui.badgeText) {
    ui.badgeText.textContent = state
    ui.badge.className = `badge ${state.toLowerCase()}`
  }

  if (desc && ui.badgeDesc) {
    ui.badgeDesc.textContent = desc
  }
}

export function showCaption(
  ui: ReturnType<typeof getUI>,
  text: string,
  mode: 'partial' | 'final' = 'final'
) {
  if (!ui.caption || !ui.captionText) return

  ui.captionText.textContent = text
  ui.caption.classList.add('show')
  ui.caption.classList.toggle('partial', mode === 'partial')
  ui.caption.classList.toggle('final', mode === 'final')
  const chatbar = ui.caption.closest('.chatbar')
  if (chatbar) {
    chatbar.classList.add('has-caption')
  }
}

export function hideCaption(ui: ReturnType<typeof getUI>) {
  if (!ui.caption) return
  ui.caption.classList.remove('show')
  ui.caption.classList.remove('partial', 'final')
  const chatbar = ui.caption.closest('.chatbar')
  if (chatbar) {
    chatbar.classList.remove('has-caption')
  }
}

export function renderSuggestedActions(
  ui: ReturnType<typeof getUI>,
  actions: Array<{ label: string; text: string }>
) {
  if (!ui.suggestionRow) return

  if (!actions.length) {
    ui.suggestionRow.innerHTML = ''
    ui.suggestionRow.classList.remove('show')
    return
  }

  ui.suggestionRow.innerHTML = actions.map((action, index) => `
    <button
      class="suggestion-chip"
      data-index="${index}"
      data-text="${escapeHtmlAttr(action.text)}"
      type="button"
    >
      ${escapeHtml(action.label)}
    </button>
  `).join('')
  ui.suggestionRow.classList.add('show')
}

function escapeHtml(text: string) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function escapeHtmlAttr(text: string) {
  return escapeHtml(text)
}
