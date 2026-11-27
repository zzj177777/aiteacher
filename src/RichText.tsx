import React from 'react';
import katex from 'katex';
import {markdownTables} from './markdownTables';

// Normalize only complete math tokens, never dialogue text or programming code.
// A second JSON-style escaping layer doubles every slash, including matrix rows.
function normalizeMath(tex:string){
 for(let layer=0;layer<2;layer++){
  const runs=[...tex.matchAll(/\\+/g)];
  if(!/\\\\[a-zA-Z]+/.test(tex)||runs.some(m=>m[0].length%2!==0))break;
  tex=tex.replace(/\\+/g,slashes=>slashes.slice(0,slashes.length/2));
 }
 return tex;
}

function mathToken(source:string):{tex:string;display:boolean}|null{
 const pairs=[['$$','$$',true],['\\\\[','\\\\]',true],['\\[','\\]',true],['\\\\(','\\\\)',false],['\\(','\\)',false],['$','$',false]] as const;
 for(const [open,close,display] of pairs){
  if(source.startsWith(open)&&source.endsWith(close)&&source.length>open.length+close.length){
   return {tex:normalizeMath(source.slice(open.length,-close.length)),display};
  }
 }
 return null;
}

function Formula({source,tex,display}:{source:string;tex:string;display:boolean}){
 try{
  const html=katex.renderToString(normalizeMath(tex),{displayMode:display,throwOnError:true,trust:false,strict:'ignore',maxExpand:1000,maxSize:20});
  return <span className={display?'formula-block':'formula-inline'} dangerouslySetInnerHTML={{__html:html}}/>;
 }catch{
  return <code className="formula-fallback" title="公式暂无法排版，保留原文">{source}</code>;
 }
}

export type TextAnnotation={id:string;index:number;start:number;end:number};

// Source offsets refer to the original Markdown/LaTeX, never to KaTeX's internal HTML.
function highlightOpaque(node:React.ReactNode,start:number,end:number,annotations:TextAnnotation[],block=false){
 const matches=annotations.filter(item=>item.start<end&&item.end>start);
 if(!matches.length)return node;
 return <mark tabIndex={-1} className={`plain-quote-anchor plain-quote-color-${matches[0].index%3}${block?' plain-quote-block':''}`} data-plain-ids={matches.map(item=>item.id).join(' ')} data-plain-indexes={matches.map(item=>item.index).join(' ')}>{node}</mark>;
}

function highlightText(text:string,start:number,annotations:TextAnnotation[]){
 const end=start+text.length,matches=annotations.filter(item=>item.start<end&&item.end>start);
 if(!matches.length)return text;
 const points=Array.from(new Set([start,end,...matches.flatMap(item=>[Math.max(start,item.start),Math.min(end,item.end)])])).sort((a,b)=>a-b);
 return points.slice(0,-1).map((point,index)=><React.Fragment key={point}>{highlightOpaque(text.slice(point-start,points[index+1]-start),point,points[index+1],matches)}</React.Fragment>);
}

// Some model responses escape line breaks a second time inside tool arguments.
// Decode only standalone prose escapes, after code/math have been tokenized.
// Keep raw source offsets so quote annotations still point to the right words.
function proseText(text:string,start:number,annotations:TextAnnotation[]){
 const breaks=Array.from(text.matchAll(/(?<!\\)\\(?:r\\n|n)(?![a-zA-Z])|(?<!\\)\\\|/g));
 if(!breaks.length)return highlightText(text,start,annotations);
 let cursor=0;
 return <>{breaks.map(match=>{
  const index=match.index!,before=cursor;cursor=index+match[0].length;
  return <React.Fragment key={index}>{highlightText(text.slice(before,index),start+before,annotations)}{highlightOpaque(match[0].endsWith('|')?'|':'\n',start+index,start+cursor,annotations)}</React.Fragment>;
 })}{highlightText(text.slice(cursor),start+cursor,annotations)}</>;
}

// Only KaTeX-generated HTML is inserted. Model HTML remains escaped React text.
type RichTextProps={text:string;annotations?:TextAnnotation[];sourceOffset?:number};
function InlineRichText({text,annotations=[],sourceOffset=0}:RichTextProps){
 const parts=text.split(/(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\{1,2}\[[\s\S]+?\\{1,2}\]|\\{1,2}\([\s\S]+?\\{1,2}\)|(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$(?![\d$])|\*\*[\s\S]+?\*\*)/g);
 let cursor=sourceOffset;
 return <>{parts.map((part,i)=>{
  const start=cursor,end=start+part.length;cursor=end;
  const wrap=(node:React.ReactNode,block=false)=><React.Fragment key={i}>{highlightOpaque(node,start,end,annotations,block)}</React.Fragment>;
  if(part.startsWith('```')&&part.endsWith('```')){
   const match=part.slice(3,-3).match(/^([^\n]*)\n([\s\S]*)$/);
   const language=match?.[1].trim().toLowerCase();
   const body=match?.[2].trim()??part.slice(3,-3);
   if(language&&['latex','tex','math'].includes(language)){
    const math=mathToken(body)??{tex:normalizeMath(body),display:true};
    return wrap(<Formula source={part} {...math}/>,math.display);
   }
   return wrap(<span className="code-block"><code>{part.slice(3,-3).replace(/^[a-zA-Z0-9_-]*\n/,'')}</code></span>,true);
  }
  if(part.startsWith('`')&&part.endsWith('`')){
   const math=mathToken(part.slice(1,-1).trim());
   return wrap(math?<Formula source={part} {...math}/>:<code>{part.slice(1,-1)}</code>,math?.display);
  }
  const math=mathToken(part);
  if(math)return wrap(<Formula source={part} {...math}/>,math.display);
  if(part.startsWith('**')&&part.endsWith('**'))return <strong key={i}><InlineRichText text={part.slice(2,-2)} annotations={annotations} sourceOffset={start+2}/></strong>;
  return <React.Fragment key={i}>{proseText(part,start,annotations)}</React.Fragment>;
 })}</>;
}

export default function RichText({text,annotations=[],sourceOffset=0}:RichTextProps){
 const tables=markdownTables(text);
 if(!tables.length)return <InlineRichText text={text} annotations={annotations} sourceOffset={sourceOffset}/>;
 const parts:React.ReactNode[]=[];let cursor=0;
 for(const table of tables){
  if(cursor<table.start)parts.push(<InlineRichText key={`text-${cursor}`} text={text.slice(cursor,table.start)} annotations={annotations} sourceOffset={sourceOffset+cursor}/>);
  parts.push(<div key={`table-${table.start}`} className="rich-table-wrap" role="region" aria-label="教学表格" tabIndex={0}><table className="rich-table">
   <thead><tr>{table.header.map((cell,i)=><th key={i} scope="col" style={{textAlign:table.align[i]}}><InlineRichText text={cell.text} annotations={annotations} sourceOffset={sourceOffset+cell.start}/></th>)}</tr></thead>
   <tbody>{table.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j} style={{textAlign:table.align[j]}}><InlineRichText text={cell.text} annotations={annotations} sourceOffset={sourceOffset+cell.start}/></td>)}</tr>)}</tbody>
  </table></div>);
  cursor=table.end;
 }
 if(cursor<text.length)parts.push(<InlineRichText key={`text-${cursor}`} text={text.slice(cursor)} annotations={annotations} sourceOffset={sourceOffset+cursor}/>);
 return <>{parts}</>;
}
