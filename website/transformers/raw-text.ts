import { defineTransformer } from '@nuxt/content'

export default defineTransformer({
  name: 'raw-text',
  extensions: ['.py', '.ansi'],
  parse(file: { id: string, body: string }) {
    return {
      id: file.id,
      raw: file.body
    }
  }
})
