import {parse} from 'mathjs';

const symbols=new Set(['x','pi','e','sin','cos','tan','asin','acos','atan','sinh','cosh','tanh','exp','log','sqrt','abs']);
export function buildFunction(expression:string):(x:number)=>number{
 if(expression.length>200)throw new Error('表达式过长');
 const ast=parse(expression);let count=0;
 ast.traverse(node=>{
  if(++count>120||!['OperatorNode','FunctionNode','SymbolNode','ConstantNode','ParenthesisNode'].includes(node.type))throw new Error('仅支持一元数学表达式');
  const value=node as typeof node & {name?:string;op?:string;value?:unknown};
  if(value.type==='SymbolNode'&&!symbols.has(value.name??''))throw new Error('不支持的函数或变量');
  if(value.type==='OperatorNode'&&!['+','-','*','/','^'].includes(value.op??''))throw new Error('不支持的运算');
  if(value.type==='ConstantNode'&&typeof value.value!=='number')throw new Error('仅支持数值常量');
 });
 const compiled=ast.compile();
 return x=>{try{const y=compiled.evaluate({x});return typeof y==='number'&&Number.isFinite(y)?y:NaN;}catch{return NaN;}};
}
