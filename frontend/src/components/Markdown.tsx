import { Fragment, type ReactNode } from "react";

/**
 * Tiny safe Markdown renderer for agent answers: paragraphs, headings, bullet/numbered lists,
 * GFM tables, fenced code, inline **bold**, *italic*, `code`. Everything becomes React text nodes
 * (auto-escaped); there is no raw HTML and no dangerouslySetInnerHTML. Links are rendered as text.
 */

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s][^*\n]*\*)/g;

function inline(text: string, key = ""): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(INLINE)) {
    const s = m[0];
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const k = `${key}i${i++}`;
    if (s.startsWith("`")) out.push(<code key={k} className="md-code">{s.slice(1, -1)}</code>);
    else if (s.startsWith("**") || s.startsWith("__")) out.push(<strong key={k} className="font-semibold">{s.slice(2, -2)}</strong>);
    else out.push(<em key={k}>{s.slice(1, -1)}</em>);
    last = at + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const isTableSep = (l: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const cells = (l: string) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const UL = /^\s*[-*•]\s+(.*)$/;
const OL = /^\s*(\d{1,3})[.)]\s+(.*)$/;
const H = /^\s*(#{1,4})\s+(.*)$/;

type Block =
  | { t: "p"; lines: string[] }
  | { t: "h"; level: number; text: string }
  | { t: "ul"; items: string[] }
  | { t: "ol"; start: number; items: string[] }
  | { t: "code"; text: string }
  | { t: "table"; head: string[]; rows: string[][] };

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    if (/^\s*```/.test(l)) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      blocks.push({ t: "code", text: buf.join("\n") });
      continue;
    }
    if (l.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(l);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push({ t: "table", head, rows });
      continue;
    }
    const h = H.exec(l);
    if (h) { blocks.push({ t: "h", level: h[1].length, text: h[2] }); i++; continue; }
    if (UL.test(l)) {
      const items: string[] = [];
      while (i < lines.length && UL.test(lines[i])) items.push(UL.exec(lines[i++])![1]);
      blocks.push({ t: "ul", items });
      continue;
    }
    const o = OL.exec(l);
    if (o) {
      const items: string[] = [];
      while (i < lines.length && OL.test(lines[i])) items.push(OL.exec(lines[i++])![2]);
      blocks.push({ t: "ol", start: Number(o[1]), items });
      continue;
    }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !UL.test(lines[i]) && !OL.test(lines[i]) && !H.test(lines[i]) && !/^\s*```/.test(lines[i])
      && !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))) buf.push(lines[i++]);
    blocks.push({ t: "p", lines: buf });
  }
  return blocks;
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div className="md space-y-2.5">
      {parse(text).map((b, bi) => {
        const k = `b${bi}`;
        switch (b.t) {
          case "h":
            return <p key={k} className={`font-semibold ${b.level <= 2 ? "text-[16px]" : "text-[15px]"}`}>{inline(b.text, k)}</p>;
          case "ul":
            return <ul key={k} className="list-disc pl-5 space-y-1">{b.items.map((it, j) => <li key={j}>{inline(it, `${k}-${j}`)}</li>)}</ul>;
          case "ol":
            return <ol key={k} start={b.start} className="list-decimal pl-5 space-y-1">{b.items.map((it, j) => <li key={j}>{inline(it, `${k}-${j}`)}</li>)}</ol>;
          case "code":
            return <pre key={k} className="font-mono text-[12.5px] leading-[1.6] rounded-lg bg-[#F1F3F6] p-3 overflow-x-auto whitespace-pre">{b.text}</pre>;
          case "table":
            return (
              <div key={k} className="overflow-x-auto border border-line rounded-lg">
                <table className="md-table w-full border-collapse text-[13.5px]">
                  <thead><tr>{b.head.map((c, j) => <th key={j} className="text-left font-medium px-3 py-2 bg-[#FAFBFC] border-b border-line whitespace-nowrap">{inline(c, `${k}h${j}`)}</th>)}</tr></thead>
                  <tbody>{b.rows.map((r, ri) => <tr key={ri}>{b.head.map((_, j) => <td key={j} className="px-3 py-2 border-b border-line/60 whitespace-nowrap num">{inline(r[j] ?? "", `${k}r${ri}c${j}`)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            );
          default:
            return <p key={k}>{b.lines.map((ln, j) => <Fragment key={j}>{j > 0 && <br />}{inline(ln, `${k}-${j}`)}</Fragment>)}</p>;
        }
      })}
    </div>
  );
}
