export type MarkdownCell={text:string;start:number};
export type MarkdownTable={start:number;end:number;header:MarkdownCell[];rows:MarkdownCell[][];align:('left'|'center'|'right')[]};

// Keep source coordinates intact: pipes inside code or TeX are not column separators.
export function markdownTables(text:string):MarkdownTable[]{
 const mask=text.replace(/(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\{1,2}\[[\s\S]+?\\{1,2}\]|\\{1,2}\([\s\S]+?\\{1,2}\)|(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$(?![\d$]))/g,value=>value.replace(/[^\r\n]/g,'#'));
 const lines:{start:number;end:number}[]=[];let cursor=0;
 for(const match of mask.matchAll(/\r\n|\n|(?<!\\)\\(?:r\\n|n)(?![a-zA-Z])/g)){
  lines.push({start:cursor,end:match.index!});cursor=match.index!+match[0].length;
 }
 lines.push({start:cursor,end:text.length});
 function cells(line:{start:number;end:number}):MarkdownCell[]|null{
  const pipes:number[]=[];
  for(let i=line.start;i<line.end;i++){
   if(mask[i]!=='|')continue;
   let slashes=0;for(let j=i-1;j>=line.start&&text[j]==='\\';j--)slashes++;
   if(slashes%2===0)pipes.push(i);
  }
  if(!pipes.length)return null;
  const boundaries=[line.start-1,...pipes,line.end];
  const result=boundaries.slice(0,-1).map((point,i)=>{
   const raw=text.slice(point+1,boundaries[i+1]),leading=raw.length-raw.trimStart().length;
   return {text:raw.trim(),start:point+1+leading};
  });
  if(!result[0].text)result.shift();
  if(result.length&&!result[result.length-1].text)result.pop();
  return result.length?result:null;
 }
 const result:MarkdownTable[]=[];
 for(let i=0;i<lines.length-1;i++){
  const header=cells(lines[i]),separator=cells(lines[i+1]);
  if(!header||!separator||header.length!==separator.length||!separator.every(cell=>/^:?-{3,}:?$/.test(cell.text)))continue;
  const align=separator.map(cell=>cell.text.endsWith(':')?(cell.text.startsWith(':')?'center':'right'):'left') as MarkdownTable['align'];
  const rows:MarkdownCell[][]=[];let last=i+1;
  for(let j=i+2;j<lines.length;j++){
   const row=cells(lines[j]);if(!row||row.length!==header.length)break;
   rows.push(row);last=j;
  }
  result.push({start:lines[i].start,end:lines[last].end,header,rows,align});i=last;
 }
 return result;
}
