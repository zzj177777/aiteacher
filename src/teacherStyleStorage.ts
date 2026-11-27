export const teacherStyleStorageKey='aiteacher.teacher-styles.token.v1';

export function teacherStyleHeaders():Record<string,string>{
 try{const token=localStorage.getItem(teacherStyleStorageKey);return token?{'X-Teacher-Style-Token':token}:{};}catch{return {};}
}

export function ensureTeacherStyleToken(){
 try{
  if(!localStorage.getItem(teacherStyleStorageKey)){
   const token=Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join('');
   localStorage.setItem(teacherStyleStorageKey,token);
   if(localStorage.getItem(teacherStyleStorageKey)!==token)throw new Error();
  }
 }catch{throw new Error('浏览器暂时无法保存恢复凭据。请允许本地存储后再创建，已填写内容会保留。');}
}
