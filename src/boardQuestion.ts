export type Choice={id:string;text:string};
export type ChoiceQuestion={prompt:string;options:Choice[];multiple:boolean};

// Existing saved questions contain inline A/B/C options. Keep the original
// Markdown/LaTeX intact and never treat letters inside formulas or code as labels.
export function parseChoiceQuestion(question:string):ChoiceQuestion|null{
 const masked=question.replace(/(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\{1,2}\[[\s\S]+?\\{1,2}\]|\\{1,2}\([\s\S]+?\\{1,2}\)|(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$(?![\d$]))/g,token=>'#'.repeat(token.length)).replace(/\\[nr]/g,'  ');
 const markers=[...masked.matchAll(/(^|[\s，,；;。！？?!：:])(?:\*\*)?(?:([A-FＡ-Ｆ])[.．、:：)）]|[（(]([A-FＡ-Ｆ])[)）])(?:\*\*)?[ \t]*/g)];
 if(markers.length<2||markers.length>6)return null;
 const options:Choice[]=[];
 for(let i=0;i<markers.length;i++){
  const match=markers[i],letter=(match[2]||match[3]).normalize('NFKC');
  if(letter!==String.fromCharCode(65+i))return null;
  const start=match.index!+match[0].length;
  const end=i+1<markers.length?markers[i+1].index!+markers[i+1][1].length:question.length;
  const text=question.slice(start,end).trim();
  if(!text)return null;
  options.push({id:letter,text});
 }
 const prompt=question.slice(0,markers[0].index!+markers[0][1].length).trim();
 if(!prompt)return null;
 return {prompt,options,multiple:/多选|可多项|不止一个|所有符合|所有正确|选择所有/.test(prompt)};
}

export function selectedChoices(options:Choice[],answer:string):string[]{
 return options.filter(({id,text})=>{
  const block=`${id}. ${text}`;
  return answer.trim()===id||answer===block||answer.startsWith(block+'\n')||answer.endsWith('\n'+block)||answer.includes('\n'+block+'\n');
 }).map(o=>o.id);
}

export function choiceAnswer(options:Choice[],selected:string[]):string{
 return options.filter(o=>selected.includes(o.id)).map(o=>`${o.id}. ${o.text}`).join('\n');
}
