export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@nuxt/content',
    '@nuxtjs/mdc',
    '@nuxt/fonts',
    '@nuxtjs/sitemap'
  ],

  ssr: true,

  devtools: { enabled: true },

  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      title: 'ProTest - Async-First Testing Framework',
      meta: [
        { name: 'description', content: 'ProTest is an async-first Python testing framework with explicit dependency injection.' },
        { name: 'theme-color', content: '#0f172a' },
        { property: 'og:title', content: 'ProTest - Async-First Testing Framework' },
        { property: 'og:description', content: 'ProTest is an async-first Python testing framework with explicit dependency injection.' },
        { property: 'og:type', content: 'website' }
      ]
    }
  },

  css: ['~/assets/css/main.css'],

  site: {
    url: 'https://protest.dev'
  },

  content: {
    build: {
      markdown: {
        highlight: {
          theme: {
            default: 'github-dark',
            dark: 'github-dark'
          },
          langs: ['python', 'bash', 'typescript', 'vue', 'json', 'yaml', 'toml']
        }
      },
      transformers: [
        '~~/transformers/raw-text'
      ]
    }
  },

  compatibilityDate: '2025-01-15',

  nitro: {
    prerender: {
      crawlLinks: true,
      routes: ['/']
    },
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
