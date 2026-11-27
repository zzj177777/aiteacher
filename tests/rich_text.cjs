const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const componentModule = {exports:require('./load_ts.cjs')('src/RichText.tsx')};
const render = text => renderToStaticMarkup(React.createElement(componentModule.exports.default,{text}));
assert.match(render('这是**重点**，再看**第二点**。'), /<strong>重点<\/strong>，再看<strong>第二点<\/strong>/);
assert.equal(render('尚未闭合的**强调'), '尚未闭合的**强调');
assert.match(render('使用 `f(x)`'), /<code>f\(x\)<\/code>/);
const hostile=render('**<img src=x onerror=alert(1)>**');
assert.ok(!hostile.includes('<img'));
assert.ok(hostile.includes('&lt;img'));
console.log('RichText rendering checks passed (emphasis, code, unmatched markers, escaped HTML).');
for(const text of [String.raw`行内 \(x^2+\frac{1}{2}\)`,String.raw`独立 \[\int_0^1 x^2\,dx=\frac13\]`,String.raw`$a_1$ 与 $$\sum_{i=1}^n i$$`]){
 const html=render(text);assert.ok(html.includes('class="katex"'));assert.ok(html.includes('<math'));
}
assert.ok(render(String.raw`\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\]`).includes('katex-display'));
assert.match(render(String.raw`**重点 \(x^2\)**`), /<strong>重点 <span class="formula-inline">/);
assert.ok(render('`$x$`').includes('class="katex"'));
assert.ok(render('```latex\n$x$\n```').includes('class="katex"'));
assert.ok(render(String.raw`错误 \(\frac{\)`).includes('formula-fallback'));
assert.ok(!render(String.raw`\(\href{javascript:alert(1)}{x}\)`).includes('href="javascript:'));
console.log('Math rendering checks passed (inline, display, matrix, nested emphasis, code isolation, fallback, untrusted links).');

// The exact reported matrix must render identically to correctly escaped TeX.
const correct=String.raw`$\begin{pmatrix}1&2\\0&1\end{pmatrix}$`;
const doubled=String.raw`$\\begin{pmatrix}1&2\\\\0&1\\end{pmatrix}$`;
assert.equal(render(doubled),render(correct));
assert.equal(render('`'+doubled+'`'),render(correct));
const reported='`'+doubled+'`；第 1 行减去第 2 行的 2 倍，得 `'+String.raw`$\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}=E$`+'`。确实化成了单位矩阵。';
assert.equal((render(reported).match(/class="katex"/g)||[]).length,2);
assert.ok(!render(reported).includes('formula-fallback'));
assert.ok(render(String.raw`\\(\\frac{1}{2}\\)`).includes('class="katex"'));
assert.equal(render(String.raw`$\\frac{1}{2}$`),render(String.raw`$\frac{1}{2}$`));
assert.ok(render('```python\nprint("$x$")\n```').includes('<code>'));
assert.ok(!render('```python\nprint("$x$")\n```').includes('class="katex"'));
assert.equal(render('文件 C:\\temp\\file 与 `\\begin`'), '文件 C:\\temp\\file 与 <code>\\begin</code>');
console.log('Regression checks passed (double escaping, matrix rows, math code wrappers, programming code preservation).');

const annotate=(text,quote)=>renderToStaticMarkup(React.createElement(componentModule.exports.default,{text,annotations:[{id:'annotation-1',index:0,start:text.indexOf(quote),end:text.indexOf(quote)+quote.length}]}));
const splitBold=annotate('这里的**分母**表示平均分的份数。','**分母**表示平均分的份数');
assert.match(splitBold,/<strong><mark[^>]+>分母<\/mark><\/strong>/);
assert.ok((splitBold.match(/data-plain-ids="annotation-1"/g)||[]).length>=2);
const mathText=String.raw`先看 $\frac{1}{4}$，再理解整体。`;
const annotatedMath=annotate(mathText,String.raw`$\frac{1}{4}$`);
assert.equal((annotatedMath.match(/class="katex"/g)||[]).length,1);
assert.ok(annotatedMath.includes('plain-quote-anchor'));
assert.ok(!annotatedMath.includes('formula-fallback'));
const unsafe=annotate('解释 <img onerror=alert(1)>','<img onerror=alert(1)>');
assert.ok(!unsafe.includes('<img'));assert.ok(unsafe.includes('&lt;img'));
assert.ok(annotate('第一行\n第二行','第一行\n第二行').includes('data-plain-ids="annotation-1"'));
console.log('Annotation checks passed (cross-bold source spans, intact formulas, multiline quotes, escaped HTML).');

const plannerReply=String.raw`你好！目标很明确。我按这个顺序安排：\n1. 回顾因式分解基础\n2. 理解「两个因式乘积为0」的原理\n3. 提公因式型方程（如 `+'`x2−3x=0`'+String.raw`）\n\n每步先讲一小段。`;
assert.equal(render(plannerReply),render(plannerReply.replace(/\\n/g,'\n')));
assert.equal(render(String.raw`第一行\r\n第二行\n\n**重点\n下一句**`),render('第一行\n第二行\n\n**重点\n下一句**'));
assert.equal(render('已有真实换行\n下一行'), '已有真实换行\n下一行');
assert.equal(render(String.raw`命令 \nabla、\neq、\nu 与文件 C:\notes\report.txt`),String.raw`命令 \nabla、\neq、\nu 与文件 C:\notes\report.txt`);
assert.equal(render('`'+String.raw`\n`+'`'),'<code>'+String.raw`\n`+'</code>');
assert.equal(render('```js\n'+String.raw`console.log("\n")`+'\n```'),'<span class="code-block"><code>console.log(&quot;'+String.raw`\n`+'&quot;)\n</code></span>');
const escapedAroundMath=String.raw`先看公式：\n$\nabla f \neq 0$\n再看矩阵 $\begin{pmatrix}1&2\\0&1\end{pmatrix}$`;
const expectedMath='先看公式：\n'+String.raw`$\nabla f \neq 0$`+'\n再看矩阵 '+correct;
assert.equal(render(escapedAroundMath),render(expectedMath));
const escapedAnnotation=annotate(String.raw`第一行\n这里的**分母**表示份数。`,'**分母**表示份数');
assert.ok(escapedAnnotation.includes('第一行\n这里的'));
assert.match(escapedAnnotation,/<strong><mark[^>]+>分母<\/mark><\/strong>/);
assert.ok(escapedAnnotation.includes('data-plain-ids="annotation-1"'));
console.log('Escaped newline checks passed (planner lists, blank lines, emphasis, source offsets, code and LaTeX preservation).');

const reportedTable='以 `y=2x+1` 为例：\n\n| `x` | 计算 | `y` | 点 |\n|---|---|---|---|\n| `0` | `2×0+1` | `1` | `(0,1)` |\n| `1` | `2×1+1` | `3` | `(1,3)` |\n| `−1` | `2×(−1)+1` | `−1` | `(−1,−1)` |';
for(const input of [reportedTable,reportedTable.replace(/\n/g,'\\n'),reportedTable.replace(/\n/g,'\r\n')]){
 const html=render(input);
 assert.equal((html.match(/<table /g)||[]).length,1);
 assert.equal((html.match(/<th /g)||[]).length,4);
 assert.equal((html.match(/<td /g)||[]).length,12);
 assert.ok(html.includes('<code>(−1,−1)</code>'));
 assert.ok(!html.includes('|---|'));
}
const tableMath=String.raw`| **输入** | 输出 |
|:---|---:|
| $|x|$ | $\frac{1}{2}$ |
| a\|b | <img src=x onerror=alert(1)> |`;
const tableHtml=render(tableMath);
assert.equal((tableHtml.match(/class="katex"/g)||[]).length,2);
assert.ok(tableHtml.includes('text-align:right'));
assert.ok(tableHtml.includes('a|b'));
assert.ok(!tableHtml.includes('<img'));assert.ok(tableHtml.includes('&lt;img'));
assert.ok(annotate(reportedTable,'2×(−1)+1').includes('data-plain-ids="annotation-1"'));
assert.equal((render('```markdown\n'+reportedTable+'\n```').match(/<table /g)||[]).length,0);
assert.equal(render('普通文字 A | B，没有分隔行。'),'普通文字 A | B，没有分隔行。');
assert.ok(render('| A | B |\n|---|\n| 1 | 2 |').includes('|---|'));
console.log('Table checks passed (reported function example, newlines, math/code cells, escaped pipes, alignment, annotations, fenced code and escaped HTML).');
