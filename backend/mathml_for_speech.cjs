// Reuse the exact open-source TeX parser used by the board. Never execute TeX.
const fs=require('node:fs');
const katex=require('katex');
const expressions=JSON.parse(fs.readFileSync(0,'utf8'));
if(!Array.isArray(expressions)||expressions.length>200)throw new Error('Invalid formula batch');
const results=expressions.map(tex=>{
 if(typeof tex!=='string'||tex.length>4000)return null;
 try{return katex.renderToString(tex,{output:'mathml',throwOnError:true,trust:false,strict:'ignore',maxExpand:500,maxSize:20});}
 catch{return null;}
});
process.stdout.write(JSON.stringify(results));
