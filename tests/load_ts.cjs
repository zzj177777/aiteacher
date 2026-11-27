const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
module.exports=function load(file,deps={}){
 const compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const mod={exports:{}};
 new Function('require','module','exports',compiled)(name=>{
  if(deps[name])return deps[name];
  if(name.startsWith('.')){
   const base=path.resolve(path.dirname(file),name),target=[base+'.ts',base+'.tsx',base].find(candidate=>fs.existsSync(candidate));
   if(target)return load(target);
  }
  return require(name);
 },mod,mod.exports);
 return mod.exports;
};
