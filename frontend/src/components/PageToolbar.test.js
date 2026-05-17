import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PageToolbar from './PageToolbar.vue'

describe('PageToolbar', () => {
  it('renders left and right action areas', () => {
    const wrapper = mount(PageToolbar, {
      slots: {
        left: '<h1>Cases</h1>',
        right: '<button>Refresh</button>',
      },
    })

    expect(wrapper.text()).toContain('Cases')
    expect(wrapper.text()).toContain('Refresh')
    expect(wrapper.find('.page-toolbar-right').exists()).toBe(true)
  })

  it('adds the vertical centering class only when requested', () => {
    const wrapper = mount(PageToolbar, {
      props: { centerY: true },
    })

    expect(wrapper.classes()).toContain('page-toolbar-center')

    const plain = mount(PageToolbar)
    expect(plain.classes()).not.toContain('page-toolbar-center')
  })
})
