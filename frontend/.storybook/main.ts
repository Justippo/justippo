import type { StorybookConfig } from '@storybook/react-vite'
import { mergeConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const config: StorybookConfig = {
  stories: [
    '../src/**/*.stories.@(ts|tsx)',
  ],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-interactions',
    '@storybook/addon-a11y',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  viteFinal: async (config) => {
    return mergeConfig(config, {
      plugins: [react()],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '../src'),
          'next/navigation': path.resolve(__dirname, '__mocks__/next-navigation.ts'),
        },
      },
    })
  },
}

export default config
