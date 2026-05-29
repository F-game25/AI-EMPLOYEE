import { Platform } from 'react-native'

export const Fonts = {
  mono: Platform.select({ ios: 'Courier New', android: 'monospace', default: 'monospace' }),
  sans: Platform.select({ ios: 'System', android: 'Roboto', default: 'System' }),
}

export const TextStyles = {
  pageTitle: {
    fontFamily: Fonts.mono,
    fontSize: 11,
    letterSpacing: 2.5,
    textTransform: 'uppercase' as const,
  },
  sectionLabel: {
    fontFamily: Fonts.mono,
    fontSize: 9,
    letterSpacing: 1.5,
    textTransform: 'uppercase' as const,
  },
  kpiValue: {
    fontFamily: Fonts.mono,
    fontSize: 28,
    fontWeight: '700' as const,
    lineHeight: 32,
  },
  body: {
    fontFamily: Fonts.sans,
    fontSize: 13,
    lineHeight: 20,
  },
  bodyMono: {
    fontFamily: Fonts.mono,
    fontSize: 11,
  },
  caption: {
    fontFamily: Fonts.mono,
    fontSize: 9,
    letterSpacing: 0.5,
  },
}
