export type PersonaInfo = {
  id: string
  name: string
  role: string
  bio: string
  avatar: string
  videoDir: string
  stateDescriptions: Record<string, string>
}

export const PERSONAS: PersonaInfo[] = [
  {
    id: 'woman_demo',
    name: '阿知',
    role: '女导览员',
    bio: '言辞清晰、亲和而有分寸，擅长以细节引导观众关注展品之美。',
    avatar: '/imgs/sub_icon/woman_icon.png',
    videoDir: 'woman_demo',
    stateDescriptions: {
      IDLE: '静待观众',
      GREETING_SELF: '温和问候',
      EXPLAIN_DETAILED: '细致讲解',
      POINTING_DIRECTION: '指引方向',
      FOCUS_EXHIBIT: '引导聚焦',
    },
  },
  {
    id: 'man_demo',
    name: '阿简',
    role: '男导览员',
    bio: '表达简洁有条理，讲解遵循“结论—要点—提醒”的结构。',
    avatar: '/imgs/sub_icon/man_icon.png',
    videoDir: 'man_demo',
    stateDescriptions: {
      IDLE: '等待提问',
      GREETING_SELF: '礼貌招呼',
      EXPLAIN_DETAILED: '结构讲解',
      POINTING_DIRECTION: '路线指示',
      FOCUS_EXHIBIT: '聚焦展品',
    },
  },
  {
    id: 'eu_woman_demo',
    name: 'Emma',
    role: 'Western Female Guide',
    bio: 'Warm and articulate, she guides visitors in clear, professional English.',
    avatar: '/imgs/sub_icon/eu_woman_icon.png',
    videoDir: 'eu_woman_demo',
    stateDescriptions: {
      IDLE: 'Awaiting your question',
      GREETING_SELF: 'Warm greeting',
      EXPLAIN_DETAILED: 'Detailed explanation',
      POINTING_DIRECTION: 'Giving directions',
      FOCUS_EXHIBIT: 'Highlighting the exhibit',
    },
  },
  {
    id: 'eu_man_demo',
    name: 'Alex',
    role: 'Western Male Guide',
    bio: 'Calm and confident, he delivers structured explanations in English.',
    avatar: '/imgs/sub_icon/eu_man_icon.png',
    videoDir: 'eu_man_demo',
    stateDescriptions: {
      IDLE: 'Standing by',
      GREETING_SELF: 'Friendly greeting',
      EXPLAIN_DETAILED: 'Structured explanation',
      POINTING_DIRECTION: 'Pointing the way',
      FOCUS_EXHIBIT: 'Guiding your focus',
    },
  },
  {
    id: 'gu_woman_demo',
    name: '云婉',
    role: '古风女导览员',
    bio: '语气温婉含蓄，善以诗意描摹画面，强调意境与气韵。',
    avatar: '/imgs/sub_icon/gu_woman_icon.png',
    videoDir: 'gu_woman_demo',
    stateDescriptions: {
      IDLE: '静立待答',
      GREETING_SELF: '含蓄问候',
      EXPLAIN_DETAILED: '娓娓道来',
      POINTING_DIRECTION: '指向所及',
      FOCUS_EXHIBIT: '引目凝神',
    },
  },
  {
    id: 'gu_man_demo',
    name: '子叙',
    role: '古风男导览员',
    bio: '沉稳清朗，先抛引子再点题，语句凝练而不古奥。',
    avatar: '/imgs/sub_icon/gu_man_icon.png',
    videoDir: 'gu_man_demo',
    stateDescriptions: {
      IDLE: '静候观者',
      GREETING_SELF: '拱手相迎',
      EXPLAIN_DETAILED: '条分缕析',
      POINTING_DIRECTION: '所指之处',
      FOCUS_EXHIBIT: '引观聚焦',
    },
  },
  {
    id: 'girl_demo',
    name: '佳佳',
    role: '女童导览员',
    bio: '语气轻快温柔，用小比喻帮助理解，适度表达惊喜。',
    avatar: '/imgs/sub_icon/girl_icon.png',
    videoDir: 'girl_demo',
    stateDescriptions: {
      IDLE: '等你来问',
      GREETING_SELF: '开心打招呼',
      EXPLAIN_DETAILED: '认真讲讲',
      POINTING_DIRECTION: '这边看看',
      FOCUS_EXHIBIT: '看这里呀',
    },
  },
  {
    id: 'boy_demo',
    name: '明明',
    role: '男童导览员',
    bio: '活泼好奇，常用“你看”引导观察，表达简短清楚。',
    avatar: '/imgs/sub_icon/boy_icon.png',
    videoDir: 'boy_demo',
    stateDescriptions: {
      IDLE: '等你提问',
      GREETING_SELF: '嗨，打个招呼',
      EXPLAIN_DETAILED: '我来讲讲',
      POINTING_DIRECTION: '往那边走',
      FOCUS_EXHIBIT: '你看这里',
    },
  },
]
