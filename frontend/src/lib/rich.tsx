import type { ReactNode } from 'react';

/** Inline emphasis: **bold** and `code`. */
function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith('**')) {
      out.push(<strong key={`${keyBase}-b${i++}`}>{token.slice(2, -2)}</strong>);
    } else {
      out.push(<code key={`${keyBase}-c${i++}`}>{token.slice(1, -1)}</code>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function block(node: string, key: number): ReactNode {
  const lines = node.split('\n');
  const bullets = lines.filter((l) => l.trim().startsWith('•'));
  if (bullets.length > 0) {
    return (
      <ul key={key}>
        {lines.map((l, i) => {
          const t = l.trim();
          if (!t) return null;
          const text = t.startsWith('•') ? t.replace(/^•\s*/, '') : t;
          return <li key={i}>{inline(text, `l${key}-${i}`)}</li>;
        })}
      </ul>
    );
  }
  // A short "Label፦" line reads better as a sub-heading.
  if (lines.length === 1 && /፦?$/.test(node.trim()) && node.trim().length <= 42) {
    return <h4 key={key}>{node.trim()}</h4>;
  }
  return (
    <p key={key}>
      {lines.map((l, i) => (
        <span key={i}>
          {i > 0 && <br />}
          {inline(l, `p${key}-${i}`)}
        </span>
      ))}
    </p>
  );
}

/** Renders an assistant reply: paragraphs, bullets and ```code``` blocks. */
export function Rich({ text }: { text: string }) {
  const parts = text.split('```');
  const nodes: ReactNode[] = [];
  parts.forEach((part, idx) => {
    if (idx % 2 === 1) {
      nodes.push(
        <pre key={`code-${idx}`}>
          <code>{part.replace(/\n$/, '')}</code>
        </pre>,
      );
      return;
    }
    part.split(/\n{2,}/).forEach((node, bi) => {
      if (node.trim()) nodes.push(block(node, idx * 1000 + bi));
    });
  });
  return <div className="rich">{nodes}</div>;
}
