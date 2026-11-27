import React from 'react';
import {createRoot} from 'react-dom/client';
import CourseLibrary from './CourseLibrary';
if(window.location.pathname==='/digital-classroom')document.title='数字人课堂 · AI 私教';
const DigitalClassroom=React.lazy(()=>import('./DigitalClassroom'));
import 'katex/dist/katex.min.css';
import './rich-text.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode>{window.location.pathname==='/digital-classroom'?<React.Suspense fallback={<p>正在打开数字人课堂…</p>}><DigitalClassroom/></React.Suspense>:<CourseLibrary />}</React.StrictMode>);
