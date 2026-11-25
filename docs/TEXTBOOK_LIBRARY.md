# 教材资料库

## 当前能力

课程中心 →「教材资料库」，或小学数学 → 某学期 →「查看本学期教材资料」。人教版普通小学数学一至六年级上下册共 12 个入口，支持筛选、来源查看、本地 PDF 阅读和下载。当前官方目录记录与历史教材文件是两个独立层次，不把旧版文件当成当前目录对应的新版。

- 当前官方目录：12 册书目，核验日期 2026-11-25，来源 https://jc.pep.com.cn/ 。具体版次尚待核验，仍是 `reference_only`；`full_text_available=false`、`toc_available=false` 指当前目录版本。
- 本地上册：6 册，官方 2022 年专题 https://bp.pep.com.cn/xsjc2022/index.html 的公开 JPEG 页面，逐页验证后按原顺序合成图片 PDF，保留原图、页哈希和来源配置。
- 本地下册：6 册，公开镜像仓库 https://github.com/ardorleo/keben 中的现有 PDF。固定文件身份存于 `mirror_sources.json`，下载时校验 Git blob SHA、字节数、PDF 页数、标题与出版社，不执行第三方代码。界面明确标为“公开镜像存档（旧版参考）”。版本以具体教材版权页为准。
- 下载批次：12 册，1472 页，487702550 字节（PDF 合计）。逐册校验 SHA-256，抽查封面、内页和末页渲染；不以下载成功代替版本核验。

**文件已入库，正文 RAG 尚未实现。** 本地 PDF 保存通过 `local_editions` 表示；当前搜索仅查书目，未把教材正文交给模型。章节入口仍显示待接入，不使用模型大纲冒充课本目录。

## 文件与接口

- `backend/resources/textbooks/catalog.json`：当前官方公开目录的精选书目，保留官方 ID、标题、学期、阅读链接、核验日期及目录资产 SHA-256。不从教材编号推断出版年；不把官方 `pdfurl` 的 HTML 阅读器误当 PDF。
- `backend/resources/textbooks/mirror_sources.json`：下册公开镜像来源、相对仓库路径、下载地址、固定 Git blob SHA 和字节数。不是官方当前版本的身份证明。
- `data/materials/index.json`：仅包含完成校验的本地教材清单。资源按 `data/materials/{material_id}/{edition_id}/document.pdf` 保存，每份另有 `manifest.json`。上册还保留 `pages/` 原始页面、逐页校验和、`source-config.js`。此目录已被 Git 忽略；不会随代码推送教材文件。
- `AITEACHER_MATERIALS_DIR`：可覆盖本地文件目录；默认项目 `data/materials`。不存在/损坏的索引按无本地文件处理，不影响官方书目。索引每次请求读取，完整书目元数据首次请求缓存；修改书目或镜像身份清单后重启服务。
- `GET /api/materials`：返回当前书目、可用 `local_editions`、来源与 `local_book_count`。支持 `grade=1..6`、`term=1..2`、`semester_id`、`q`。筛选后计数对应结果集。
- `GET /api/materials/{id}`：单册书目与可用本地版本。
- `GET /api/materials/{id}/editions/{edition_id}/pdf`：本地 PDF，默认 inline；`?download=true` 为附件下载。支持单段 Range（含后缀范围）、If-Range；无效范围 416，未知、缺失或不完整文件 404。
- 当前部署的 Starlette 不自带 FileResponse Range，因此材料模块补充了有界分块读取，避免跳页时反复下载整本教材。

接口是公共只读资料，不混入个人课程和课堂记录；无任意 URL 代理、远程抓取或路径参数映射。只允许固定教材及版本 ID，并检查最终文件路径位于配置目录内。只有来源、大小、格式与清单一致的完整文件才对外展示。访问请求不调用大模型或外网。

## 导入与交接

`scripts/download_textbooks.py` 使用 Pillow、reportlab、pypdf，可用文档工具的 Python 环境运行：

```powershell
python scripts/download_textbooks.py                # 六册官方历史上册，支持断点续传
python scripts/download_textbooks.py --mirror-lower # 六册已识别的公开镜像下册
```

默认输出 `data/materials`，可用 `--output` 指定目录，用 `--grades 1 2` 选择年级。需要这些 Python 库的仅是导入工具，在线服务不依赖 PDF 处理库。导入时不用登录、验证码破解或受保护内容解密；遇到 401/403 停止该资源。未完成的教材不写入索引，已完成教材不会因下一本失败被抹掉。

新增来源：先核对教材、年级、册次和版权页 → 记录稳定版本身份和真实来源 → 扩展允许的来源及导入规则 → 完整下载并验证 → 原子更新索引 → 浏览器检查阅读/下载。禁止静默覆盖已有历史版本或更改学习记录所引用的教材版本。

界面由 `src/TextbookLibrary.tsx` 实现，导航由 `CourseLibrary.tsx` 管理。刷新恢复原学期入口；筛选仅当前页面有效。更新部署时同时发布代码、构建产物和 `data/materials` 的完整资源及索引，不能只推前端便宣称文件入库。

公开获取不等于允许再分发或商业复制；目前仅保存用户本机资料。后续公开发布或商用前需确认相应授权。

## 后续

正文利用需另做：按版次核验真实目录 → 提取 PDF 文本或 OCR → 校对中文、公式和页码 → 保存可引用的文字片段 → 检索并给模型携带来源页码。图片 PDF 不能直接当成已有可检索正文。教材概念依赖和学生掌握状态仍需单独建模。

验证：`python -m unittest discover -s tests -p test_materials.py` 检查书目、过滤、来源、路径、缺失文件与 PDF 流式读取；`node tests/materials_browser.cjs` 检查入口、12 个学期、筛选、错误重试及手机布局。设置 `MATERIALS_TEST_URL=http://127.0.0.1:8000` 可验证实际服务的 PDF 范围阅读与下载响应。
