import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Answers are written by a model from bank records and documents, so their formatting is
// rendered (bold, lists, headings, tables) but nothing in them can run or load: raw HTML is
// dropped, images are not shown, and links open in a new tab without access to this page.
const PROSE = [
  'break-words [&>:first-child]:mt-0 [&>:last-child]:mb-0',
  '[&_p]:mb-2 [&_ul]:mb-2 [&_ol]:mb-2 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5',
  '[&_li+li]:mt-0.5 [&_h1]:mt-3 [&_h2]:mt-3 [&_h3]:mt-3 [&_h1]:mb-1.5 [&_h2]:mb-1.5 [&_h3]:mb-1.5',
  '[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_strong]:font-semibold',
  '[&_table]:mb-2 [&_table]:border-collapse [&_table]:text-sm',
  '[&_th]:border [&_td]:border [&_th]:border-line [&_td]:border-line [&_th]:px-2 [&_td]:px-2',
  '[&_th]:py-1 [&_td]:py-1 [&_th]:text-left [&_th]:font-semibold',
  '[&_code]:rounded [&_code]:bg-hover [&_code]:px-1 [&_code]:text-[0.9em] [&_a]:text-accent [&_a]:underline',
].join(' ')

export function Markdown({ text }: { text: string }) {
  return (
    <div className={PROSE}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={['img']}
        unwrapDisallowed
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
