// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ChatMessage } from './ChatMessage'
import type { Chat } from './chat'

let root: Root, container: HTMLDivElement
const citations: Chat['citations'] = [
  { refId: 'approved-objective', title: 'Approved objective', source: 'foundry', locator: 'Curriculum / objective', excerpt: 'Interpret graph axes and trends.' },
  { refId: 'team-discussion', title: 'Informal planning discussion', source: 'work', locator: 'Planning note', excerpt: 'Start with axis labels.' },
]
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  container = document.createElement('div'); document.body.append(container)
  root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove(); vi.unstubAllGlobals()
})
async function render(message: string) {
  await act(async () => root.render(<ChatMessage message={message} citations={citations} />))
}

it('renders lesson headings, model bullet characters, emphasis, ordered lists and responsive tables', async () => {
  await render('## Proposed groups\n\n\u2022 **Graph-reading conference:** model the axes.\n\u2022 Evidence bridge: connect a number to a claim.\n\n### Exit ticket\n\n1. Read the scale.\n2. Explain the trend.\n\n| Minutes | Activity |\n| --- | --- |\n| 0–3 | Launch |\n| 3–8 | Teacher model |')
  expect(container.querySelector('.chat-answer h3')?.textContent).toBe('Proposed groups')
  expect(container.querySelector('.chat-answer h4')?.textContent).toBe('Exit ticket')
  expect(container.querySelectorAll('ul > li')).toHaveLength(2)
  expect(container.querySelector('li strong')?.textContent).toBe('Graph-reading conference:')
  expect(container.querySelectorAll('ol > li')).toHaveLength(2)
  expect(container.querySelector('.answer-table[tabindex="0"] tbody')?.children).toHaveLength(2)
  expect(container.querySelector('.chat-answer')?.textContent).not.toContain('##')
})

it('replaces only known references with numbered links that reveal the matching source, without hiding unknown refs or code', async () => {
  await render('Approved requirement [approved-objective; team-discussion].\n\nUnknown [missing-ref]. Code `[approved-objective]`.\n\n```text\n\u2022 [approved-objective]\n```')
  const links = container.querySelectorAll<HTMLAnchorElement>('.citation-link')
  expect([...links].map(link => link.textContent)).toEqual(['1', '2'])
  expect(links[1].getAttribute('aria-label')).toBe('Source 2: Informal planning discussion')
  const detail = document.getElementById(links[1].hash.slice(1)) as HTMLDetailsElement
  expect(detail.open).toBe(false)
  await act(async () => links[1].click())
  expect(detail.open).toBe(true)
  expect(document.activeElement).toBe(detail.querySelector('summary'))
  expect(detail.textContent).toContain('Start with axis labels.')
  expect(detail.textContent).toContain('Planning note')
  expect(container.querySelector('.chat-answer')?.textContent).toContain('[missing-ref]')
  expect(container.querySelector('p code')?.textContent).toBe('[approved-objective]')
  expect(container.querySelector('pre code')?.textContent).toBe('\u2022 [approved-objective]\n')
})

it('keeps source targets unique across messages and does not execute HTML, unsafe links, or remote images', async () => {
  await act(async () => root.render(<>
    <ChatMessage message={'[approved-objective]\n\n<script>alert(1)</script>\n\n<img src="https://tracker.example/pixel" onerror="alert(1)">\n\n![tracking](https://tracker.example/image)\n\n[unsafe](javascript:alert%281%29)\n\n[resource](https://school.example/resource)'} citations={citations} />
    <ChatMessage message="[approved-objective]" citations={citations} />
  </>))
  const links = container.querySelectorAll<HTMLAnchorElement>('.citation-link')
  expect(links[0].hash).not.toBe(links[1].hash)
  expect(container.querySelector('script, img')).toBeNull()
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
  const external = container.querySelector('a[href="https://school.example/resource"]')
  expect(external?.getAttribute('rel')).toBe('noopener noreferrer')
})
