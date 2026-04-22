import { describe, it, expect } from 'vitest'
import { PLATFORM_NAME, INNOVATION_TAGLINE, THESIS_TITLE_FULL } from './branding'

describe('branding constants', () => {
  it('平台名/副标题为非空字符串', () => {
    expect(typeof PLATFORM_NAME).toBe('string')
    expect(PLATFORM_NAME.length).toBeGreaterThan(0)
    expect(typeof INNOVATION_TAGLINE).toBe('string')
    expect(INNOVATION_TAGLINE.length).toBeGreaterThan(0)
  })

  it('论文标题提到 Flaky 与自适应执行策略关键词', () => {
    expect(THESIS_TITLE_FULL).toMatch(/Flaky/)
    expect(THESIS_TITLE_FULL).toMatch(/自适应执行策略/)
  })
})
