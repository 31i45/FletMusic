# FletMusic
Totally AI generated project. 

Pyncm API + Flet + pygame-ce. 

A free music player like **YesPlayMusic**.

# Create .exe app
`pyinstaller FletMusic.spec`

FletMusic 开源项目完整分析

这是一个纯Python+AI辅助开发的极简在线音乐播放器，核心定位是轻量、免费、可播放完整歌曲，对标YesPlayMusic但更轻量化、响应更快。

一、项目基础信息

• 名称：FletMusic

• 定位：免费听整首歌曲的极简音乐播放器

• 开发背景：受YesPlayMusic启发，解决其响应慢问题

• 开发方式：全程AI生成代码，作者仅做整合与调试

• 用途：仅限学习/研究/技术交流，严禁商业与非法爬取

• 打包产物：Windows单exe，约35MB

二、核心技术栈

• UI框架：Flet（Flutter渲染，Python跨平台GUI）

• 音频播放：pygame‑ce（稳定音频解码与播放）

• 音乐数据源：pyncm（网易云音乐第三方Python API）

• 打包工具：PyInstaller

• 异步框架：asyncio（网络请求与UI解耦）

三、核心功能

1. 在线音乐搜索：歌单/单曲双模式搜索

2. 完整歌曲播放：仅播放免费可播歌曲，过滤试听曲

3. 播放控制：播放/暂停、进度条、自动下一首

4. 缓存机制：本地临时缓存，减少重复下载

5. 歌单查看：加载歌单并播放内部歌曲

6. 极简UI：卡片式封面、信息清晰、无冗余功能

四、架构与代码设计

1. 模块化分层（清晰易维护）

• MusicAPI：网络请求、搜索、歌单、歌曲URL获取

• AudioPlayer：pygame封装，播放/暂停/停止/进度同步

• AudioCache：本地临时文件缓存管理

• PlayQueueManager：播放队列与切歌逻辑

• PlayerUI：底部播放栏、进度、歌曲信息

• UIManager：页面、搜索、列表、歌单渲染

• MusicPlayerApp：入口与业务编排

2. 关键设计亮点

• 装饰器缓存：避免重复API请求

• 异步非阻塞：网络/IO不卡UI

• 免费歌曲过滤：只播可完整播放曲目

• 单一职责：类与函数职责清晰

• 响应式UI：Flet组件自动适配

五、AI Coding开发流程（作者经验）

1. 不重复造轮子 → 优先用成熟开源库

2. 先做HLD高层设计

3. 核心功能优先，用AI快速实现

4. 开启详细日志，便于调试

5. 逐步补全功能

6. 最后按KISS/DRY/OOP优化代码

六、部署与运行

1. 环境依赖
pip install flet pygame-ce pyncm pyinstaller
2. 运行项目
python fletmusic.py
3. 打包exe
pyinstaller FletMusic.spec
生成：dist/FletMusic.exe（≈35MB）

七、优势亮点

• 极轻量：体积小、启动快、占用低

• 响应更快：比YesPlayMusic更流畅

• 纯Python：学习成本低，易二次开发

• AI友好：非程序员也能按流程复刻

• 干净无广告：仅保留核心播放功能

八、局限与风险

• 仅免费歌曲：VIP/付费曲无法播放

• 依赖第三方API：pyncm失效则项目不可用

• 无歌词、EQ、音效：功能极简

• 合规风险：未经授权爬取可能侵权

• 仅Windows打包：跨平台需额外配置

九、适合人群与用途

• 想学习Python+Flet+AI做桌面应用

• 需要轻量无广告音乐播放器

• 研究第三方音乐API与音频播放

• 零基础想快速做完整项目的人

十、总结

FletMusic是AI辅助开发的优秀范例：用成熟组件+清晰架构，快速实现可用产品，代码规范、易读、易扩展。
它证明非专业开发者也能用AI做出实用工具，同时提醒：开源项目务必遵守版权与法律边界。