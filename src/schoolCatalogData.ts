export type StageId='primary'|'junior'|'senior';
export type SchoolPath={stage:StageId;subject:string;grade?:string;term?:1|2};
export type SchoolSubject={id:string;name:string;description:string;icon:string;tone:string;group:'基础学科'|'综合素养'};
type SchoolStage={id:StageId;name:string;range:string;caption:string;grades:{id:string;name:string}[];subjects:string[]};

const subject=(id:string,name:string,description:string,icon:string,tone:string,group:SchoolSubject['group']='基础学科'):SchoolSubject=>({id,name,description,icon,tone,group});
export const schoolSubjects:SchoolSubject[]=[
 subject('chinese','语文','读懂文字，也学会表达。','languages','sand'),
 subject('math','数学','把问题想清楚，把方法学明白。','math','sage'),
 subject('english','英语','一点点听懂、读懂、说出来。','english','blue'),
 subject('physics','物理','理解现象背后的规律。','physics','blue'),
 subject('chemistry','化学','认识物质，发现变化。','chemistry','lilac'),
 subject('biology','生物学','探索生命与自然。','biology','sage'),
 subject('history','历史','沿着时间，看懂故事与变化。','history','sand'),
 subject('geography','地理','从身边出发，认识更大的世界。','geography','blue'),
 subject('ethics','政治','认识规则，理解社会生活。','ethics','sand'),
 subject('politics','政治','理解社会，练习独立思考。','ethics','sand'),
];
export const schoolStages:SchoolStage[]=[
 {id:'primary',name:'小学',range:'一年级至六年级',caption:'打好基础，保持好奇',grades:['一年级','二年级','三年级','四年级','五年级','六年级'].map((name,i)=>({id:`g${i+1}`,name})),subjects:['chinese','math','english']},
 {id:'junior',name:'初中',range:'七年级至九年级',caption:'连起知识，找到方法',grades:['七年级','八年级','九年级'].map((name,i)=>({id:`g${i+7}`,name})),subjects:['chinese','math','english','physics','chemistry','geography','biology','ethics','history']},
 {id:'senior',name:'高中',range:'高一至高三',caption:'深入理解，形成体系',grades:['高一','高二','高三'].map((name,i)=>({id:`g${i+10}`,name})),subjects:['chinese','math','english','physics','chemistry','geography','biology','politics','history']},
];
export function subjectsFor(stage:StageId){const ids=schoolStages.find(item=>item.id===stage)!.subjects;return ids.map(id=>schoolSubjects.find(item=>item.id===id)!);}
export function restoreSchoolPath(value:{stage_id?:unknown;subject_id?:unknown;grade_id?:unknown;term?:unknown}):SchoolPath|null{
 const stage=schoolStages.find(item=>item.id===value.stage_id);
 if(!stage||!stage.subjects.includes(value.subject_id as string))return null;
 const base:SchoolPath={stage:stage.id,subject:value.subject_id as string};
 if(stage.grades.some(item=>item.id===value.grade_id)&&(value.term===1||value.term===2))return {...base,grade:value.grade_id as string,term:value.term};
 return base;
}
