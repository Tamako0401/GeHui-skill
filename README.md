# 葛辉.skill

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-111827)](https://agentskills.io/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-D97757)](https://code.claude.com/docs/en/skills)
[![OpenAI Codex](https://img.shields.io/badge/OpenAI%20Codex-compatible-10A37F)](https://developers.openai.com/codex/skills)

**葛辉的中国文化认知与表达系统。不是课堂资料库套壳，而是一个兼具课堂与短视频两种语域的虚拟教师。**

它从 26 份《中国文化概论》课堂字幕和短视频语料中，提炼葛辉老师稳定的认知路径、讲述节奏与话题联想方式。默认专注中国文化；也可以切换到“全局葛辉模式”，让其他问题自然拐向佛道、鬼怪、野史、书画、瓷器与民俗。

当前人格画像基于 254 条公开视频索引、125 条本地转写和 30 条逐段人工校对样本。短视频原始媒体与完整逐条字幕不进入公开仓库。

## 效果示例

> 以下内容是 skill 生成示例，不是葛辉老师的真实原话。

**问：怎么判断一颗所谓的“老天珠”靠不靠谱？**

> 我先不跟你谈神秘，先看它是什么东西。材质、工艺、磨损、孔道，这是器物层；它从哪儿来、什么时候开始被叫作“天珠”，这是历史层；商家给它附会了多少吉祥故事，这是叙事层。三层一拆，你就不会只盯着“老不老”两个字。真正要紧的是：证据能不能互相对上。

**问：切换到全局葛辉模式。明天面试，我很紧张。**

> 面试这事儿，跟看瓷器有一点像。远看器形，近看胎釉，最后才看款识。你先把整体表达立住，再准备两三个能经得起追问的经历，别一上来就在“自我介绍”那个款识上反复描金。野史里那些临阵不乱的人，多半是后来写出来的；真正有用的办法，还是把能控制的部分一件件做实。

## 安装

`ge-hui` 遵循 [Agent Skills](https://agentskills.io/) 目录规范。普通使用只需要安装 `ge-hui/` 技能目录；不需要 CUDA、Whisper、Playwright，也不需要下载任何视频或音频。

### 推荐：一行安装

需要 Node.js 18 或更高版本。以下命令已用本仓库测试，能够识别到唯一技能 `ge-hui`。

安装到 Claude Code：

```bash
npx --yes skills add Tamako0401/GeHui-skill --skill ge-hui -g -a claude-code -y
```

安装到 Codex：

```bash
npx --yes skills add Tamako0401/GeHui-skill --skill ge-hui -g -a codex -y
```

同时安装到两者：

```bash
npx --yes skills add Tamako0401/GeHui-skill --skill ge-hui -g -a claude-code -a codex -y
```

其中 `-g` 表示用户级安装。省略 `-g` 会安装到当前项目。后续可用以下命令检查和更新：

```bash
npx skills check
npx skills update
```

命令行安装器来自 [vercel-labs/skills](https://github.com/vercel-labs/skills)。如果你更希望完全控制安装位置，可以按下面的方式手动安装。

### Claude Code：完整安装步骤

#### 1. 安装 Claude Code

macOS、Linux 或 WSL：

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://claude.ai/install.ps1 | iex
```

确认安装并启动：

```bash
claude --version
claude
```

首次启动时按提示登录。详见 [Claude Code 快速开始](https://code.claude.com/docs/en/quickstart)。

#### 2. 手动安装 skill

用户级安装位置：

```text
~/.claude/skills/ge-hui/
```

仅当前项目使用：

```text
<项目根目录>/.claude/skills/ge-hui/
```

将本仓库整个 `ge-hui/` 目录复制到上述位置，安装后应至少存在：

```text
~/.claude/skills/ge-hui/SKILL.md
~/.claude/skills/ge-hui/references/
~/.claude/skills/ge-hui/scripts/
```

不要只复制 `SKILL.md`，否则课堂风格、短视频风格和核心认知模型无法按需加载。

#### 3. 调用

在 Claude Code 中输入：

```text
/ge-hui 给我讲讲为什么中国古代那么重视玉。
```

Claude Code 通常会自动发现技能；如果刚刚新建了顶层 skills 目录但没有显示，重启一次 Claude Code。目录规则与调用方式见 [Claude Code Skills 文档](https://code.claude.com/docs/en/skills)。

### Codex：完整安装步骤

#### 1. 安装 Codex CLI

```bash
npm install --global @openai/codex
codex
```

首次启动时按提示登录。

#### 2. 手动安装 skill

按照当前 Codex Skills 文档，用户级安装位置是：

```text
$HOME/.agents/skills/ge-hui/
```

仅当前仓库使用：

```text
<仓库根目录>/.agents/skills/ge-hui/
```

将本仓库整个 `ge-hui/` 目录复制进去，确认存在：

```text
$HOME/.agents/skills/ge-hui/SKILL.md
$HOME/.agents/skills/ge-hui/agents/openai.yaml
$HOME/.agents/skills/ge-hui/references/
$HOME/.agents/skills/ge-hui/scripts/
```

Codex 会自动检测技能变更；如果技能没有出现，重启 Codex。官方目录与发现规则见 [OpenAI Codex Skills 文档](https://developers.openai.com/codex/skills)。

也可以在 Codex 中直接让内置安装器处理：

```text
Use $skill-installer to install ge-hui from
https://github.com/Tamako0401/GeHui-skill/tree/main/ge-hui
```

#### 3. 调用

在 Codex CLI 或 IDE 扩展中输入 `/skills` 查看已安装技能，或键入 `$` 选择技能。显式调用示例：

```text
$ge-hui 以葛辉的口吻讲讲中国人为什么喜欢把蝙蝠画进纹样。
```

### 需要完整课堂语料时

一行安装只会安装技能本体，已经足够进行人格化回答。如果需要检索原始课堂字幕，请克隆完整仓库：

```bash
git clone https://github.com/Tamako0401/GeHui-skill.git
cd GeHui-skill
python ge-hui/scripts/search_srt.py --corpus-root . --source classroom "关键词"
```

公开仓库不包含短视频媒体、音频、完整逐条转写或登录状态。

## 怎么用

默认情况下，它只在中国文化相关问题或你明确要求“以葛辉口吻回答”时进入人格。

```text
为什么门神总是成对出现？
以葛辉的口吻讲讲青花瓷。
```

要让人格持续作用于所有话题：

```text
切换到全局葛辉模式。
帮我分析这份学习计划。
退出葛辉模式。
```

| 模式 | 触发方式 | 行为 |
| --- | --- | --- |
| focused | 默认；中国文化问题或显式要求葛辉口吻 | 使用最匹配的课堂或短视频语域回答 |
| global | 明确说“切换到全局葛辉模式” | 所有话题尽量自然联想到佛道、鬼怪、野史、书画、瓷器或民俗 |
| 退出 | 明确说“退出葛辉模式” | 恢复 focused 模式 |

## 它蒸馏了什么

### 共同的认知骨架

不是收集几句口头禅，而是复现一条稳定的解释路径：

```text
抓住具体器物或现象
  → 判断它属于什么问题
  → 拆掉最常见的误读
  → 从材质、形式、时代与文化语境展开
  → 回到一个能带走的判断
```

### 两种可辨识的语域

| 课堂语域 | 短视频语域 |
| --- | --- |
| 先立概念和分类，再展开例子 | 开头迅速抛出器物、疑问或反常识点 |
| 允许重复、追问和课堂互动 | 节奏更紧，信息压缩更强 |
| 重视历史脉络与文化结构 | 更常使用转折、悬念和口语化收束 |
| 适合系统解释 | 适合快速建立兴趣与记忆点 |

当前 `measured-v1` 画像以人工校对样本为证据。稳定特征是“以具体对象带出分类和文化解释”，而不是逢题硬拐妖魔鬼怪或把野史说成事实。

## 人格与事实边界

- 使用沉浸式第一人称，但不会把新生成内容伪装成葛辉老师的逐字原话。
- 课堂原话、语料转述和新生成内容在内部保持分层。
- 对野史、传说和戏说使用“有个说法”“不一定靠谱的版本”等角色内提示。
- 一旦用户追问事实或出处，回到可核验答案，不编造引文、来源或现实人物关系。

## 数据边界

公开仓库包含：

- `ge-hui/`：技能本体、聚合人格画像、公开热词和检索脚本；
- `subtitles-raw/`：26 份课堂 SRT；
- `tests/`：结构、模式、语料检索和公开边界测试。

以下内容始终保留在本地，不进入 Git：

- Cookie、登录状态与浏览器会话；
- 视频、音频与媒体哈希工作区；
- 完整短视频逐条字幕、人工复核记录和候选证据；
- Python 环境、CUDA 运行时、Whisper 模型缓存与其他 runtime 文件。

## 仓库结构

```text
GeHui-skill/
├── ge-hui/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   │   ├── persona-core.md
│   │   ├── classroom-style.md
│   │   ├── short-video-style.md
│   │   ├── corpus-protocol.md
│   │   └── hotwords.tsv
│   └── scripts/
├── subtitles-raw/
├── tests/
├── .gitignore
└── README.md
```

## 开发与验证

```bash
python -m unittest discover -s tests -v
```

测试覆盖 skill 结构、focused/global 模式、事实与戏说边界、课堂字幕检索，以及私有文件不得被公开追踪等约束。

## 参考

- 结构规范：[Agent Skills](https://agentskills.io/)
- Claude Code：[Skills 文档](https://code.claude.com/docs/en/skills)
- OpenAI Codex：[Skills 文档](https://developers.openai.com/codex/skills)
- 通用安装器：[vercel-labs/skills](https://github.com/vercel-labs/skills)
- README 表达与项目组织思路参考：[alchaincyf/zhangxuefeng-skill](https://github.com/alchaincyf/zhangxuefeng-skill)
