import {whiteboardBlocks,type BoardBlock} from './whiteboardBlocks';

export type TeachingMark={id:string;quote:string;start:number;end:number;style:'circle'|'underline'|'highlight';kind:'key_point'|'pitfall'|'difficulty';explanation:string;evidence_quote:string};

export function attentionSentences(text:string):BoardBlock[]{
 const result:BoardBlock[]=[];
 for(const block of whiteboardBlocks(text)){
  const previous=result[result.length-1];
  const end=previous?previous.text.replace(/\*\*/g,'').trim():'';
  const nextBullet=/^(?:[-*]\s|\d+[.、．])/.test(block.text);
  // A definition followed by a display formula is one thought, not three clicks.
  if(previous&&!/[。！？；!?;](?:\\n)?$/.test(end)&&(!nextBullet||/[:：]$/.test(end))){
   previous.text=text.slice(previous.start,block.start+block.text.length);
  }else result.push({...block});
 }
 return result;
}

export function attentionCues(unit:BoardBlock,marks:TeachingMark[]):TeachingMark[]{
 // Display only exact model-authored anchors wholly within this reading unit.
 // No word lists, first-formula heuristics, legacy focus, or fabricated fallback.
 return marks.filter(mark=>Number.isInteger(mark.start)&&Number.isInteger(mark.end)&&mark.start>=unit.start&&mark.end<=unit.start+unit.text.length&&mark.end>mark.start&&unit.text.slice(mark.start-unit.start,mark.end-unit.start)===mark.quote);
}

export function attentionDelay(text:string):number{
 const plain=text.replace(/\\[a-zA-Z]+|[${}*_`]/g,'');
 return Math.min(9000,Math.max(2800,plain.length*130+1200));
}
