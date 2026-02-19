<script setup lang="ts">
const props = withDefaults(defineProps<{
  id: string
  title?: string
  source?: string
  open?: boolean
  openOutput?: boolean
}>(), {
  open: false,
  openOutput: true,
})

const { data: ansiData } = await useAsyncData(`output-${props.id}`, async () => {
  const item = await queryCollection('examples')
    .where('stem', '=', `_examples/${props.id}`)
    .where('extension', '=', 'ansi')
    .first()
  if (!item?.raw) return null

  const { AnsiUp } = await import('ansi_up')
  const converter = new AnsiUp()
  converter.use_classes = false
  return {
    html: converter.ansi_to_html(item.raw),
  }
})

interface SourceSegment {
  code: string
  focused: boolean
}

function parseSource(raw: string): { segments: SourceSegment[], hasFocus: boolean } {
  const lines = raw.split('\n')
  const hasMarkers = lines.some(l => l.trim().startsWith('# doc:focus:'))

  if (!hasMarkers) {
    return { segments: [{ code: raw, focused: true }], hasFocus: false }
  }

  const segments: SourceSegment[] = []
  let current: string[] = []
  let inFocus = false

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === '# doc:focus:start') {
      if (current.length) {
        segments.push({ code: current.join('\n'), focused: false })
        current = []
      }
      inFocus = true
      continue
    }
    if (trimmed === '# doc:focus:end') {
      if (current.length) {
        segments.push({ code: current.join('\n'), focused: true })
        current = []
      }
      inFocus = false
      continue
    }
    current.push(line)
  }
  if (current.length) {
    segments.push({ code: current.join('\n'), focused: inFocus })
  }

  return { segments, hasFocus: true }
}

function stripMarkers(raw: string): string {
  return raw.split('\n').filter(l => !l.trim().startsWith('# doc:focus:')).join('\n')
}

const { data: sourceData } = await useAsyncData(
  `source-${props.source ?? 'none'}`,
  async () => {
    if (!props.source) return null
    const stem = props.source.replace(/\.[^.]+$/, '')
    const item = await queryCollection('examples')
      .where('stem', '=', `_examples/${stem}`)
      .where('extension', '=', 'py')
      .first()
    if (!item?.raw) return null

    const { createHighlighter } = await import('shiki')
    const highlighter = await createHighlighter({
      themes: ['github-dark'],
      langs: ['python']
    })
    const highlight = (code: string) => highlighter.codeToHtml(code, { lang: 'python', theme: 'github-dark' })

    const raw = item.raw
    const clean = stripMarkers(raw)
    const { segments, hasFocus } = parseSource(raw)

    return {
      raw,
      hasFocus,
      fullHtml: highlight(clean),
      segments: segments.map(seg => ({
        ...seg,
        html: highlight(seg.code),
        lineCount: seg.code.split('\n').filter(l => l.trim()).length
      }))
    }
  },
)

const ansiHtml = computed(() => ansiData.value?.html ?? '')
const sourceOpen = ref(props.open)
const outputOpen = ref(props.openOutput)
const sourceExpanded = ref(false)
</script>

<template>
  <div
    class="example-unit my-6 rounded-lg border border-white/10 overflow-hidden"
  >
    <!-- Source section -->
    <div v-if="source">
      <button
        class="section-header w-full flex items-center justify-between px-4 py-2.5 bg-white/[0.1] cursor-pointer"
        @click="sourceOpen = !sourceOpen"
      >
        <div class="flex items-center gap-2">
          <span
            class="chevron inline-block transition-transform duration-200 text-[var(--color-dark-500)]"
            :class="sourceOpen ? 'rotate-90' : ''"
          >
            &#9656;
          </span>
          <span class="text-sm font-mono text-[var(--color-dark-400)]">{{ source }}</span>
        </div>
        <span
          v-if="sourceData?.hasFocus && sourceOpen"
          class="text-xs text-[var(--color-dark-500)] hover:text-[var(--color-dark-300)] transition-colors cursor-pointer"
          @click.stop="sourceExpanded = !sourceExpanded"
        >
          {{ sourceExpanded ? 'Focus' : 'Full' }}
        </span>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        :class="sourceOpen ? 'max-h-72' : 'max-h-0'"
      >
        <div class="overflow-y-auto max-h-64 border-t border-white/5">
          <!-- No focus markers → full source -->
          <template v-if="sourceData && !sourceData.hasFocus">
            <div class="source-code" v-html="sourceData.fullHtml" />
          </template>

          <!-- Has focus markers → segment-based rendering -->
          <template v-else-if="sourceData?.hasFocus">
            <template v-for="(seg, i) in sourceData.segments" :key="i">
              <!-- Collapsed: ⋯ N lines -->
              <div
                v-if="!sourceExpanded && !seg.focused && seg.lineCount > 0"
                class="collapsed-line"
                @click="sourceExpanded = true"
              >
                &#x22EF; {{ seg.lineCount }} lines
              </div>
              <!-- Expanded non-focused: dimmed, clickable to re-collapse -->
              <div
                v-else-if="sourceExpanded && !seg.focused"
                class="unfocused-code"
                @click="sourceExpanded = false"
                v-html="seg.html"
              />
              <!-- Focused: always shown normally -->
              <div v-else-if="seg.focused" class="source-code" v-html="seg.html" />
            </template>
          </template>
        </div>
      </div>

      <div class="border-t border-white/10" />
    </div>

    <!-- Output section -->
    <div>
      <button
        class="section-header w-full flex items-center justify-between px-4 py-2.5 bg-white/[0.1] cursor-pointer"
        @click="outputOpen = !outputOpen"
      >
        <div class="flex items-center gap-2">
          <span
            class="chevron inline-block transition-transform duration-200 text-[var(--color-dark-500)]"
            :class="outputOpen ? 'rotate-90' : ''"
          >
            &#9656;
          </span>
          <span v-if="title" class="text-sm font-mono text-[var(--color-dark-400)]">
            {{ title }}
          </span>
        </div>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        :class="outputOpen ? 'max-h-[40rem]' : 'max-h-0'"
      >
        <div class="overflow-y-auto max-h-[38rem] border-t border-white/5">
          <pre
            v-if="ansiData"
            class="px-4 py-3 text-sm leading-relaxed overflow-x-auto font-mono bg-transparent"
            v-html="ansiHtml"
          />
          <div v-else class="px-4 py-4 flex flex-col gap-2">
            <div class="h-3 w-2/3 rounded bg-white/5 animate-pulse" />
            <div class="h-3 w-1/2 rounded bg-white/5 animate-pulse" />
            <div class="h-3 w-3/5 rounded bg-white/5 animate-pulse" />
            <div class="h-3 w-1/3 rounded bg-white/5 animate-pulse" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.example-unit {
  background: var(--color-dark-800);
}

.example-unit :deep(pre) {
  margin: 0 !important;
  padding: 0.75rem 1rem !important;
  border-radius: 0 !important;
  border: none !important;
  background: transparent !important;
  font-size: 0.875rem !important;
  line-height: 1.625 !important;
}

.collapsed-line {
  text-align: center;
  font-size: 0.75rem;
  color: var(--color-dark-500);
  padding: 4px 0;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.02);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.collapsed-line:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-dark-300);
}

.unfocused-code {
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.15s ease;
}

.unfocused-code:hover {
  opacity: 0.65;
}
</style>
