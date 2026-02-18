<script setup lang="ts">
const props = withDefaults(defineProps<{
  id: string
  title?: string
  source?: string
  open?: boolean
}>(), {
  open: false,
})

const ansiHtml = ref('')
const plainText = ref('')
const sourceMarkdown = ref('')
const hasSource = ref(false)
const sourceOpen = ref(props.open)
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
  <div class="my-4">
    <!-- Collapsible source code -->
    <div
      v-if="hasSource"
      class="source-block border border-[var(--color-dark-700)] overflow-hidden"
      :class="sourceOpen ? 'rounded-t-lg' : 'rounded-lg mb-0'"
    >
      <button
        class="w-full flex items-center gap-2 px-4 py-2 bg-[var(--color-dark-800)] text-sm font-mono text-[var(--color-dark-400)] hover:text-[var(--color-dark-200)] transition-colors"
        @click="sourceOpen = !sourceOpen"
      >
        <span
          class="inline-block transition-transform duration-200"
          :class="sourceOpen ? 'rotate-90' : ''"
        >
          &#9656;
        </span>
        <span>Source</span>
        <span class="text-xs text-[var(--color-dark-500)]">{{ source }}</span>
      </button>
      <div
        class="source-content overflow-hidden transition-all duration-300 ease-in-out"
        :class="sourceOpen ? 'max-h-96' : 'max-h-0'"
      >
        <div class="overflow-y-auto max-h-80 border-t border-[var(--color-dark-700)]">
          <MDC :value="sourceMarkdown" />
        </div>
      </div>
    </div>

    <!-- Terminal output block -->
    <div
      class="terminal-block overflow-hidden border border-[var(--color-dark-700)]"
      :class="hasSource && sourceOpen ? 'rounded-b-lg border-t-0' : 'rounded-lg'"
    >
      <div
        v-if="title"
        class="terminal-header flex items-center justify-between px-4 py-2 bg-[var(--color-dark-800)] border-b border-[var(--color-dark-700)]"
      >
        <span class="text-sm font-mono text-[var(--color-dark-400)]">{{ title }}</span>
        <button
          class="text-xs text-[var(--color-dark-400)] hover:text-[var(--color-dark-200)] transition-colors"
          @click="copyToClipboard"
        >
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
      </div>
      <div
        v-else
        class="flex justify-end px-4 pt-2 bg-[var(--color-dark-950)]"
      >
        <button
          class="text-xs text-[var(--color-dark-400)] hover:text-[var(--color-dark-200)] transition-colors"
          @click="copyToClipboard"
        >
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
      </div>
      <pre
        v-if="loaded"
        class="terminal-body px-4 py-3 bg-[var(--color-dark-950)] text-sm leading-relaxed overflow-x-auto font-mono"
        v-html="ansiHtml"
      />
      <div
        v-else
        class="px-4 py-6 bg-[var(--color-dark-950)] text-[var(--color-dark-500)] text-sm font-mono animate-pulse"
      >
        Loading...
      </div>
    </div>
  </div>
</template>

<style scoped>
.source-block :deep(pre) {
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
}
</style>
