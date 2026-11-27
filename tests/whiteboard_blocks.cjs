const fs=require('node:fs'),assert=require('node:assert/strict'),ts=require('typescript');
const mod={exports:require('./load_ts.cjs')('src/whiteboardBlocks.ts')};
const blocks=mod.exports.whiteboardBlocks;
const input='先平均分。\n再看 $\\frac{1}{2}$。\n最后读作二分之一。';
const split=blocks(input);
assert.equal(split.length,3);
for(const b of split)assert.equal(input.slice(b.start,b.start+b.text.length),b.text);
const math=String.raw`先看 $$\begin{pmatrix}1&2\\3&4\end{pmatrix}$$。再看 $\text{第一；第二。}=x$。`;
assert.equal(blocks(math).length,2);
assert.ok(blocks(math)[0].text.includes(String.raw`1&2\\3&4`));
assert.equal(blocks('**第一句。\n强调内容。**\n再解释。').length,2);
assert.equal(blocks('运行 `a;b`。\n然后计算。').length,2);
assert.equal(blocks('```js\nconst x=1;\n```\n继续讲解。').length,2);
const escaped=String.raw`第一笔\n第二笔\n公式 $\nabla f\ne0$`;
assert.equal(blocks(escaped).length,3);
assert.ok(blocks(escaped)[2].text.includes(String.raw`\nabla`));
assert.equal(blocks('只有一个要点').length,1);
assert.equal(blocks('**注意**\n不平均，就不能叫二分之一。').length,1);
const labelled='定义：\n平均分：\n分成同样大的两份。\n再看一个例子。';
assert.equal(blocks(labelled).length,2);
for(const b of blocks(labelled))assert.equal(labelled.slice(b.start,b.start+b.text.length),b.text);
assert.equal(blocks('   ').length,1);
console.log('Whiteboard blocks verified: progressive prose, source offsets, complete formulas, code, emphasis and escaped line breaks.');
const table=String.raw`| $x$ | 计算 | $y$ | 点 |
|---|---|---|---|
| $0$ | $2\times0+1$ | $1$ | $(0,1)$ |
| $1$ | $2\times1+1$ | $3$ | $(1,3)$ |
| $-1$ | $2\times(-1)+1$ | $-1$ | $(-1,-1)$ |`;
for(const separator of ['\n','\\n','\r\n']){
 const source='先看例子。'+separator+table.replace(/\n/g,separator)+separator+'这三个点在同一直线上。';
 const units=blocks(source),matched=units.filter(unit=>unit.text.includes('|---|'));
 assert.equal(matched.length,1);
 assert.ok(matched[0].text.includes('(-1,-1)'));
 assert.ok(!units.some(unit=>unit.text.trim()==='|---|---|---|---|'));
 for(const unit of units)assert.equal(source.slice(unit.start,unit.start+unit.text.length),unit.text);
}
console.log('Whole tables preserved through progressive whiteboard reveals, including original source offsets.');
