import { Fragment, type ReactNode } from 'react';
/** Small, non-executing Markdown subset. React escapes raw HTML; no HTML parser. */
function link(value:string){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function inline(text:string):ReactNode[]{
 const tokens=text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))/g);
 return tokens.map((token,i)=>{if(token.startsWith('`')&&token.endsWith('`'))return <code key={i}>{token.slice(1,-1)}</code>;if(token.startsWith('**')&&token.endsWith('**'))return <strong key={i}>{token.slice(2,-2)}</strong>;const m=token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);if(m){const href=link(m[2]);return href?<a key={i} href={href} target="_blank" rel="noreferrer noopener">{m[1]}</a>:<Fragment key={i}>{m[1]} ({m[2]})</Fragment>;}return <Fragment key={i}>{token}</Fragment>;});
}
function tableRow(value:string):string[]|null {
 const source=value.trim();if(!source.includes('|'))return null;
 const cells:string[]=[];let cell='',code=false;
 for(let i=0;i<source.length;i++){const ch=source[i];if(ch==='\\'&&source[i+1]==='|'){cell+='|';i++;continue;}if(ch==='`')code=!code;if(ch==='|'&&!code){cells.push(cell.trim());cell='';}else cell+=ch;}
 cells.push(cell.trim());if(source.startsWith('|'))cells.shift();if(source.endsWith('|')&&cells[cells.length-1]==='')cells.pop();
 return cells.length?cells:null;
}
function tableHeader(lines:string[],at:number){
 const header=tableRow(lines[at]??''),separator=tableRow(lines[at+1]??'');
 if(!header||!separator||header.length!==separator.length||header.length>32||!separator.every(c=>/^:?-{3,}:?$/.test(c)))return null;
 return{header,alignment:separator.map(c=>c.startsWith(':')&&c.endsWith(':')?'center':c.endsWith(':')?'right':'left') as ('left'|'center'|'right')[]};
}
const horizontal=(line:string)=>/^ {0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line);
const quote=(line:string)=>line.match(/^ {0,3}>\s?(.*)$/);
export function AssistantMarkdown({text}:{text:string}){
 const lines=text.replaceAll('\r\n','\n').split('\n'),nodes:ReactNode[]=[];let i=0;
 while(i<lines.length){const line=lines[i];if(line.startsWith('```')){const language=line.slice(3).trim().replace(/[^\w+-]/g,'').slice(0,32),code:string[]=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);if(i<lines.length)i++;nodes.push(<div className="og-assistant-code" key={'code'+i}><div>{language||'代码'}</div><pre><code>{code.join('\n')}</code></pre></div>);continue;}
  if(horizontal(line)){nodes.push(<hr key={'hr'+i}/>);i++;continue;}
  const table=tableHeader(lines,i);if(table){const start=i; i+=2;const rows:string[][]=[];
   while(i<lines.length&&lines[i].trim()){const cells=tableRow(lines[i]);if(!cells)break;rows.push(cells.length>table.header.length?[...cells.slice(0,table.header.length-1),cells.slice(table.header.length-1).join(' | ')]:cells);i++;}
   nodes.push(<div className="og-assistant-table" key={'table'+start}><table><thead><tr>{table.header.map((cell,j)=><th key={j} scope="col" style={{textAlign:table.alignment[j]}}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row,j)=><tr key={j}>{table.header.map((_,col)=><td key={col} style={{textAlign:table.alignment[col]}}>{inline(row[col]??'')}</td>)}</tr>)}</tbody></table></div>);continue;}
  const heading=line.match(/^(#{1,4})\s+(.+)$/);if(heading){nodes.push(<h3 key={i++}>{inline(heading[2])}</h3>);continue;}
  if(quote(line)){const quoted:string[]=[];while(i<lines.length){const match=quote(lines[i]);if(!match)break;quoted.push(match[1]);i++;}nodes.push(<blockquote key={'quote'+i}>{quoted.map((q,j)=><Fragment key={j}>{j>0&&<br/>}{inline(q)}</Fragment>)}</blockquote>);continue;}
  if(/^\s*([-*]|\d+\.)\s+/.test(line)){const list:ReactNode[]=[];const ordered=/^\s*\d+\./.test(line);while(i<lines.length&&/^\s*([-*]|\d+\.)\s+/.test(lines[i])){list.push(<li key={i}>{inline(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/,''))}</li>);}nodes.push(ordered?<ol key={'list'+i}>{list}</ol>:<ul key={'list'+i}>{list}</ul>);continue;}
  if(!line.trim()){i++;continue;}
  const para:string[]=[];while(i<lines.length&&lines[i].trim()&&!horizontal(lines[i])&&!tableHeader(lines,i)&&!quote(lines[i])&&!/^(#{1,4})\s+.+$|^```|^\s*([-*]|\d+\.)\s+/.test(lines[i]))para.push(lines[i++]);nodes.push(<p key={'p'+i}>{para.map((p,j)=><Fragment key={j}>{j>0&&<br/>}{inline(p)}</Fragment>)}</p>);
 }
 return <div className="og-assistant-markdown">{nodes}</div>;
}
