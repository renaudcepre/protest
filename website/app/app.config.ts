export default defineAppConfig({
  ui: {
    colors: {
      primary: 'brand',
      neutral: 'dark'
    }
  },
  seo: {
    siteName: 'ProTest'
  },
  header: {
    title: '',
    to: '/',
    search: true,
    colorMode: false,
    links: [{
      'icon': 'i-lucide-github',
      'to': 'https://github.com/renaudcepre/protest',
      'target': '_blank',
      'aria-label': 'GitHub'
    }]
  },
  footer: {
    credits: 'ProTest — Async-first testing for Python',
    colorMode: false,
    links: [{
      'icon': 'i-lucide-github',
      'to': 'https://github.com/renaudcepre/protest',
      'target': '_blank',
      'aria-label': 'GitHub'
    }]
  },
  toc: {
    title: 'Table of Contents',
    bottom: {
      title: '',
      edit: '',
      links: []
    }
  }
})
