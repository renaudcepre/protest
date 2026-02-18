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

const ansiHtml = ref('')
const plainText = ref('')
const sourceMarkdown = ref('')
const hasSource = ref(false)
const sourceOpen = ref(props.open)
const outputOpen = ref(props.openOutput)
const copied = ref(false)
const loaded = ref(false)

onMounted(async () => {
  const { AnsiUp } = await import('ansi_up')

  // Fetch ANSI output
  const raw = await $fetch<string>(`/_outputs/${props.id}.ansi`, {
    responseType: 'text',
  })
  const converter = new AnsiUp()
  converter.use_classes = false
  ansiHtml.value = converter.ansi_to_html(raw)
  plainText.value = raw.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')

  // Fetch source file if specified
  if (props.source) {
    try {
      const source = await $fetch<string>(`/_outputs/sources/${props.source}`, {
        responseType: 'text',
      })
      sourceMarkdown.value = '```python\n' + source.trimEnd() + '\n```'
      hasSource.value = true
    }
    catch {
      // Source file not found
    }
  }

  loaded.value = true
})

async function copyToClipboard() {
  await navigator.clipboard.writeText(plainText.value.trim())
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}
</script>

<template>
  <div class="my-6 flex flex-col gap-1.5">
    <!-- Collapsible source code -->
    <div
      v-if="hasSource"
      class="panel overflow-hidden rounded-lg border border-white/10"
      :class="sourceOpen ? 'panel--source-open' : ''"
    >
      <button
        class="panel-header w-full flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-white/10 cursor-pointer"
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
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        :class="sourceOpen ? 'max-h-[28rem]' : 'max-h-0'"
      >
        <div class="overflow-y-auto max-h-96">
          <MDC :value="sourceMarkdown" />
        </div>
      </div>
    </div>

    <!-- Collapsible terminal output -->
    <div class="panel overflow-hidden rounded-lg border border-white/10">
      <button
        class="panel-header w-full flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-white/10 cursor-pointer"
        @click="outputOpen = !outputOpen"
      >
        <div class="flex items-center gap-2">
          <span
            class="chevron inline-block transition-transform duration-200 text-[var(--color-dark-500)]"
            :class="outputOpen ? 'rotate-90' : ''"
          >
            &#9656;
          </span>
          <img src="/logo-icon.svg" alt="" class="h-4 w-auto opacity-50">
          <span v-if="title" class="text-sm font-mono text-[var(--color-dark-400)]">{{ title }}</span>
        </div>
        <span
          class="text-xs text-[var(--color-dark-500)] hover:text-[var(--color-dark-300)] transition-colors"
          role="button"
          @click.stop="copyToClipboard"
        >
          {{ copied ? 'Copied!' : 'Copy' }}
        </span>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        :class="outputOpen ? 'max-h-[40rem]' : 'max-h-0'"
      >
        <div class="overflow-y-auto max-h-[38rem]">
          <pre
            v-if="loaded"
            class="px-4 py-3 text-sm leading-relaxed overflow-x-auto font-mono bg-transparent"
            v-html="ansiHtml"
          />
          <div
            v-else
            class="px-4 py-6 text-[var(--color-dark-500)] text-sm font-mono animate-pulse"
          >
            Loading...
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: linear-gradient(
    135deg,
    rgba(15, 23, 42, 0.85) 0%,
    rgba(15, 23, 42, 0.75) 50%,
    rgba(15, 23, 42, 0.85) 100%
  );
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

/* Subtle purple glow on source when open */
.panel--source-open {
  border-color: rgba(168, 85, 247, 0.2);
  box-shadow: 0 0 20px -5px rgba(168, 85, 247, 0.1);
}

.panel :deep(pre) {
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
  background: transparent !important;
}
</style>
