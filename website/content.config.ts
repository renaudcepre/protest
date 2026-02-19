import { defineCollection, defineContentConfig } from '@nuxt/content'
import { z } from 'zod'

export default defineContentConfig({
  collections: {
    docs: defineCollection({
      type: 'page',
      source: '**/*.md'
    }),
    examples: defineCollection({
      type: 'data',
      source: '_examples/**',
      schema: z.object({
        raw: z.string()
      })
    })
  }
})
