import { useId } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { findAndReplace } from 'mdast-util-find-and-replace'
import type { PhrasingContent, Root } from 'mdast'
import type { Chat } from './chat'

function normalizeBullets(message: string): string {
  let fence = ''
  return message.split('\n').map(line => {
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line)
    if (marker) {
      if (!fence) fence = marker[1]
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = ''
      return line
    }
    return fence ? line : line.replace(/^( {0,3})\u2022[ \t]+/, '$1- ')
  }).join('\n')
}

function citationLinks(options: { citations: Chat['citations']; prefix: string }) {
  return (tree: Root) => {
    findAndReplace(tree, [/\[([^\]\n]+)\]/g, (_match: string, refs: string) => {
      const indexes = refs.split(/[;,]/).map(ref => options.citations.findIndex(c => c.refId === ref.trim()))
      if (indexes.some(index => index < 0)) return false
      return indexes.flatMap((index, i): PhrasingContent[] => [
        ...(i ? [{ type: 'text' as const, value: ' ' }] : []),
        { type: 'link', url: `#${options.prefix}-${index + 1}`, children: [{ type: 'text', value: `${index + 1}` }] },
      ])
    }], { ignore: ['link', 'linkReference', 'code', 'inlineCode', 'html'] })
  }
}

export function ChatMessage({ message, citations }: { message: string; citations: Chat['citations'] }) {
  const prefix = `source-${useId().replace(/:/g, '')}`
  return <>
    <div className="chat-answer">
      <Markdown skipHtml disallowedElements={['img']} remarkPlugins={[remarkGfm, [citationLinks, { citations, prefix }]]} components={{
        h1: ({ children }) => <h3>{children}</h3>,
        h2: ({ children }) => <h3>{children}</h3>,
        h3: ({ children }) => <h4>{children}</h4>,
        h4: ({ children }) => <h5>{children}</h5>,
        h5: ({ children }) => <h6>{children}</h6>,
        table: ({ children }) => <div className="answer-table" role="region" aria-label="Response table" tabIndex={0}><table>{children}</table></div>,
        a: ({ href, children }) => {
          const citation = citations.findIndex((_, index) => href === `#${prefix}-${index + 1}`)
          return citation >= 0
            ? <a className="citation-link" href={href} title={citations[citation].title}
              aria-label={`Source ${citation + 1}: ${citations[citation].title}`}
              onClick={() => {
                const detail = document.getElementById(`${prefix}-${citation + 1}`)
                if (detail instanceof HTMLDetailsElement) {
                  detail.open = true
                  detail.querySelector('summary')?.focus()
                }
              }}>{children}</a>
            : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        },
      }}>{normalizeBullets(message)}</Markdown>
    </div>
    {!!citations.length && <section className="message-sources" aria-label="Message sources">
      <h3>Sources <span className="source-count">{citations.length}</span></h3>
      {citations.map((citation, index) => <details id={`${prefix}-${index + 1}`} key={citation.refId}>
        <summary><span className="source-number">{index + 1}</span><span>{citation.title}</span></summary>
        <dl><div><dt>Source</dt><dd>{citation.source}</dd></div><div><dt>Reference</dt><dd>{citation.refId}</dd></div><div><dt>Location</dt><dd>{citation.locator}</dd></div></dl>
        <blockquote>{citation.excerpt}</blockquote>
      </details>)}
    </section>}
  </>
}
