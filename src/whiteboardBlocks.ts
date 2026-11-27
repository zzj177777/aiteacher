import {markdownTables} from './markdownTables';

export type BoardBlock={text:string;start:number};

// Split prose at real teaching pauses; keep whole formulas and code together.
export function whiteboardBlocks(text:string):BoardBlock[]{
 let protectedText=text.replace(/(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\{1,2}\[[\s\S]+?\\{1,2}\]|\\{1,2}\([\s\S]+?\\{1,2}\)|(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$(?![\d$])|\*\*[\s\S]+?\*\*)/g,value=>'#'.repeat(value.length));
 for(const table of markdownTables(text))protectedText=protectedText.slice(0,table.start)+'#'.repeat(table.end-table.start)+protectedText.slice(table.end);
 const ends=[...protectedText.matchAll(/\\(?:r\\n|n)(?![a-zA-Z])|\n+|[。；！？]/g)].map(m=>m.index!+m[0].length);
 ends.push(text.length);let cursor=0;const result:BoardBlock[]=[];
 for(const end of ends){
  const raw=text.slice(cursor,end),leading=raw.length-raw.trimStart().length;
  if(raw.trim())result.push({text:raw.trim(),start:cursor+leading});
  cursor=end;
 }
 // A lone “注意” or “定义：” is a label, not a useful teaching reveal.
 // Keep such labels attached to the following explanation.
 const grouped:BoardBlock[]=[];let pending:BoardBlock|undefined;
 for(const block of result){
  const plain=block.text.replace(/\*\*/g,'');
  const heading=plain.length<=14&&!/[。；！？$\\`]/.test(plain)&&!/^[-\d]/.test(plain);
  if(!pending&&heading){pending=block;continue;}
  const combined=pending?{text:text.slice(pending.start,block.start+block.text.length),start:pending.start}:block;
  if(heading){pending=combined;continue;}
  grouped.push(combined);pending=undefined;
 }
 if(pending)grouped.push(pending);
 return grouped.length?grouped:[{text,start:0}];
}
