# 两份教学 Skill 中文阅读译本

两份译文分别保留上游的教学规则、数字门槛、命令、工作区文件名和元数据，不把它们混合成同一种教学法。

| 中文文件 | 教学定位 | 上游原文 |
|---|---|---|
| [Jane Street 苏格拉底式导师](./janestreet/socratic-tutor/SKILL.md) | 起点诊断、逐个提问、能力分级、间隔复习与最终测评 | [socratic-tutor/SKILL.md](https://github.com/janestreet/agent_skills/blob/master/socratic-tutor/SKILL.md) |
| [Matt Pocock 持续学习导师](./mattpocock/teach/SKILL.md) | 学习目标、可信资料、交互短课、学习记录和参考文档 | [teach/SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/productivity/teach/SKILL.md) |

## 翻译范围

- 已完整翻译上一轮调研中读取的两个 `SKILL.md` 主体，包括适用范围和限制。
- Jane Street 的英文命令保留原名，后附中文解释。
- Matt 的 `disable-model-invocation`、`argument-hint`、工作区路径和模板文件名保留；其中面向人的文本已翻译。
- Matt 的三个配套模板本次未取得原文，因此没有自行编写或冒充译文；主文件中保留指向官方模板的链接。本包是中文阅读译本，不是包含全部依赖的离线安装包。

## 来源版本

译文依据本次对话上一轮调研中已完整读取的上游正文。此次尝试重新下载原文、配套模板和许可时，自动权限审核两次未在期限内完成；网页读取服务也发生连接错误，因此没有固定提交 SHA，也没有宣称已核对到上游最新版本。

## 作者与许可

原始内容分别来自 Jane Street 的 `janestreet/agent_skills` 和 Matt Pocock 的 `mattpocock/skills`。中文文件是翻译衍生内容，不是上游官方中文版，原始内容的版权归各自权利人。

上一轮调研确认两个仓库均标注 MIT 许可。原始许可与版权声明见 [Jane Street LICENSE.md](https://github.com/janestreet/agent_skills/blob/master/LICENSE.md) 和 [Matt Pocock 仓库的许可入口](https://github.com/mattpocock/skills)。本包未重新取得许可文件原文，保留上游链接供核对。

## 格式校验

Jane Street 译本通过了 skill-creator 的 Skill 结构校验。Matt 译本的 YAML 结构正确，但原版包含 `argument-hint` 和 `disable-model-invocation` 两个 Claude 专用字段，Codex 的严格校验器不接受；此次按原样保留，没有为了通过校验而改变原版调用约定。

## 阅读说明

这两份文件描述的是各自原有教学策略。例如，Jane Street 要求先完成诊断再教学；Matt 要求更改学习目标前获得确认。这些要求按原文保留，并不代表已将它们应用到 AI 私教项目的运行流程。
