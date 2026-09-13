# 项目自导览手册 · 深入篇:数据与服务器 + Docker(第 6-7 讲)

> **定位**:主手册(第 0-5 讲)的向下钻取——把「数据到底存在哪」「Docker 在中间干了什么」这两块地基彻底打牢。
> **事实来源**:全部按 2026-09-04 实测核对(repo 根 `Dockerfile`、`backend/app/config.py`、`.dockerignore`、`deploy-azure` skill)。
> **读法**:和主手册一样,每讲末尾自测;这篇过了,你就敢在生产上动手了。

---

## 第 6 讲 · 数据和服务器的真正关系

### 6.1 先打破一个直觉:**服务器上没有你的数据**

很多人以为「数据在服务器上」。在你的项目里,准确的说法是——**跑代码的机器和存数据的机器,是两家不同公司的三台机器**:

```
   Azure Web App(东南亚)          Supabase(AWS 日本)
  ┌──────────────────┐          ┌──────────────────────┐
  │  容器里只有:      │  网络    │  Postgres:23 张表     │
  │  Python 代码      │◄───────►│  (帖子/用户/课表…)    │
  │  编译好的前端      │  加密连接 │  Storage:头像/图片    │
  │  Python 环境      │          │  (文件形式,不在表里)  │
  │  【没有任何数据】  │          └──────────────────────┘
  └──────────────────┘
```

- **Azure 容器 = 租来的厨房**:只带菜谱(代码),不带食材
- **Supabase Postgres = 另一家公司的仓库**:所有结构化数据
- **Supabase Storage = 仓库旁的文件柜**:图片文件
- **重部署 = 整间厨房换成一间崭新的**,仓库和文件柜原地不动

### 6.2 「无状态」:为什么敢随便重启、回滚、重部署

后端程序**不持有任何不该丢的东西**:

| 状态 | 实际放在哪 | 服务器炸了会怎样 |
|------|-----------|----------------|
| 登录态 | 用户手里的 JWT + 库里的 refresh_tokens | 无感,手环还能用 |
| 帖子/课评/课表 | Postgres | 无损(根本不在服务器上) |
| 头像图片 | Supabase Storage | 无损 |
| 热数据缓存 | 容器内存里的 TTLCache | 自动重建(慢几秒) |
| 容器里的临时文件 | 容器文件系统 | **全丢——但本来就不该有** |

这就是整个架构最值钱的一个性质:**服务器是消耗品,数据是资产,两者物理分离**。所以第 5 讲的「应急三招」(重启/回滚)才敢那么随便用。

### 6.3 容器文件系统是「阅后即焚」

容器每次重启/重部署,内部文件系统**归零**——里面写过的任何文件(日志、临时文件、`__pycache__`)全部消失。

由此推出本项目的三条设计纪律:

1. **图片上传必须走 Storage**(`storage_service.py` 转存 Supabase)——落在容器磁盘上的图,重启就没了
2. **日志必须 print 到 stdout**,由 Azure 收走进 Log stream——不是写文件
3. 任何新功能如果「把文件存在服务器上」,那就是 bug,review 时拦下

### 6.4 同一份代码,两套地址:环境变量机制

代码里**永远不写死**数据库地址。`config.py` 全部长这样:

```python
DATABASE_URL = os.getenv("DATABASE_URL", "")   # 从环境读,读不到就空
```

然后两套环境各自注入:

| 环境 | 谁来注入值 | DATABASE_URL 指向 |
|------|-----------|------------------|
| 本地开发 | `backend/.env` 文件(`load_dotenv` 读) | 本机 brew postgres |
| 生产 | Azure 应用配置(appsettings,门户里改) | Supabase pooler(aws-1 日本) |

关键安全事实:**`.dockerignore` 里写着 `.env`**——本地这个文件被明确挡在镜像之外。所以:

- 密钥(数据库密码、SECRET_KEY、Supabase key)**永远不会进镜像、不会进 ACR、不会进 git**
- 生产换密码/换库 = 改 Azure 应用配置 + 重启,**不碰代码**
- 已知坑:本地 `.env` 里的 postgres socket 地址可能是死的,跑 pytest 时要 `env DATABASE_URL=...` 覆盖(memory: local-pytest-recipe)

### 6.5 连接的细节:pooler 和两种模式

Supabase 不给你数据库的直连地址,给的是一个「接线总机」(pooler),有两种模式:

| 端口 | 模式 | 什么时候用 |
|------|------|-----------|
| 6543 | transaction(事务) | **平时后端连它**(省连接数) |
| 5432 | session(会话) | **灌库专用** |

⚠️ 历史事故:在 6543 上跑 seed 灌库会「**静默烂一半**」——不报错,但部分数据没进去。灌库永远切 5432。
⚠️ 本地 VPN 可能挡 6543 的 TLS 连接(asyncpg 报 connection_lost)——此时灌库改走 **REST 443**(Supabase HTTP API,VPN 挡不住)。

连接池:`DB_POOL_MIN=1 / DB_POOL_MAX=5`(容器小,养不起太多连接)。

### 6.6 数据的三个「家」(总表,接主手册 2.5)

| 家 | 装什么 | 改它 = 走哪条链 |
|----|--------|----------------|
| Supabase Postgres(23 张表) | 用户/帖子/课评/修读记录… | 灌库链(REST/seed) |
| Supabase Storage | 头像、帖子图片 | 用户上传/API |
| 镜像里的 `data/*.py` | 55 专业毕业规则、GE 目录 | **后端链(改代码=重新 build 镜像!)** |

第三行是最反直觉的:改一条毕业规则,走的不是「改数据」,而是「改代码 → buildx → ACR → Azure」整条后端链。

### 6.7 一次「存数据」的旅程(以写课评为例)

课评提交 → 验 JWT → (审核闸门) → asyncpg 把一行 INSERT 进 `course_reviews` → 数据落进 Supabase(日本) → 别人看课评页:先查容器内存缓存,没有再 SELECT → 回来路上顺手放进缓存。

和第 0 讲的「发帖 6 步」是同一个模式——**后端永远只是数据和用户之间的搬运工,自己不攒东西**。

**自测**:①重部署会丢什么、不丢什么?②为什么上传图片必须走 Storage?③本地和生产连的是同一个数据库吗?`DATABASE_URL` 的值分别从哪来?④灌库用 6543 还是 5432,为什么?⑤改一条毕业规则要走哪条链?

---

## 第 7 讲 · Docker:从代码到一台「现成机器」

### 7.1 为什么需要它

没有 Docker 的世界:「在我 Mac 上明明能跑啊」——但 Azure 的服务器上没有你的 Python 3.12、没有那 40 个 pip 包、没有编译好的前端 CSS。Docker 的解法:**把「能跑的整个环境」连同代码一起打包带走**,在哪台机器上都是同一个东西。

### 7.2 四个词,一辈子不混

| 词 | 人话 | 你项目里的对应物 |
|----|------|----------------|
| **Dockerfile** | 菜谱(怎么打包) | repo 根那个 `Dockerfile` |
| **image(镜像)** | 按菜谱做好的冷冻半成品,**不可变**,带名字(tag) | `hkmucampusreg.azurecr.io/hkmu-backend:8902d72` |
| **container(容器)** | 把半成品热出来、正在跑的那份 | Azure Web App 里跑着的那个 |
| **ACR** | 放冷冻半成品的仓库(Azure 家的) | `hkmucampusreg.azurecr.io` |

一台 image 可以处处起 container;tag 就是它的「姓名+版本」。

### 7.3 你的 Dockerfile 逐段解读(真实文件,两段式)

```
Stage 1(node:20-alpine)——只为一件事:编译 Tailwind CSS
  npm ci → build-css.sh → 产出 css/app.min.css
  ※ app.min.css 是构建产物:源码里没有、gitignore 了——所以前端必须在镜像里构建

Stage 2(python:3.12-slim)——真正的运行时
  COPY requirements.txt → pip install    ← 全是 manylinux wheel,不需要 apt(避开了 apt 被墙的坑)
  COPY backend/                           ← 后端代码(.env 被 .dockerignore 挡住,进不来)
  COPY --from=css 编译好的 frontend/       ← 网页前端打进镜像,由后端容器一起服务!
  COPY scripts/                           ← 灌库脚本也随行
  EXPOSE 8000
  CMD uvicorn backend.app.main:app --port ${PORT:-8000}
```

三个直接推论:

1. **改网页前端 = 必须重新 build 镜像**(前端活在镜像里)——这就是主手册 4.4 表里「网页前端随 4.1」的原因
2. **密钥永不进镜像**(`.dockerignore` 挡 `.env`;生产值由 Azure 注入)
3. `${PORT}` 由 Azure 注入——容器不自己决定端口

### 7.4 完整生命周期:从一个 commit 到线上容器(真实命令)

```
① git commit 8902d72 → PR → CI 绿 → 合 main
② docker buildx build --platform linux/amd64 \
     -t hkmucampusreg.azurecr.io/hkmu-backend:8902d72 --push .
③ az webapp config container set(四参一起带:image + registry-url + user + password)
④ az webapp restart
⑤ Azure 拉新镜像 → 停旧容器 → 起新容器 → init_db(补缺失的列)→ uvicorn 就绪
⑥ 验证(别只看 health!)
```

每一步的「为什么」:

- **②为什么 `--platform linux/amd64`**:你的 Mac 是 Apple Silicon(arm64 指令集),Azure 服务器是 x86(amd64)——**两台机器说的"机器话"不同**,必须交叉打包。buildx 用 QEMU 模拟,所以要 3-8 分钟
- **③为什么四参一起带**:只带 image 不带凭证会**清掉**已存的拉取密码 → Azure 拉镜像 401 → 容器根本起不来(经典坑 1)
- **登录 ACR 用 admin 凭证**(`az acr credential show` 现拿 password + `docker login`),别用 `az acr login`(会超时)
- **⑥为什么别只看 health**:container set 后旧容器可能还在服务 30-60 秒,旧容器也返 200——要用「本次改动会变的那个端点」验证新代码真的上了
- 完整带 fallback 的命令在 **`deploy-azure` skill**,让 Claude 走它

### 7.5 tag = commit hash:回滚的数学

镜像**不可变**:同一个 tag 永远是同一份内容(所以 build 完不会「覆盖」旧版,而是用新 hash 起新名)。

- 今天的线上:`...:8902d72`
- 发现坏了:把 webapp 镜像指回 `...:41bde1b` + restart → **几十秒回到昨天**
- git log 里的 hash = 镜像名 = 回滚地址簿,一一对应

### 7.6 重部署时间线(容器视角,秒级)

```
停旧容器(断流几秒)→ 拉新镜像(分层下载,没变的层不重下)
→ 起新容器(文件系统全新=空的)→ init_db 建表/补列 → uvicorn 启动 → 接流量
```

事故对照(全是真实发生过的):

| 症状 | 真因 | 教训 |
|------|------|------|
| 部署后一直 503,容器起不来 | DDL 注释里有分号 → init_db 崩 | database.py 注释永远不带分号/引号 |
| 起容器就崩,日志 import error | requirements.txt 漏了一个包 | 加依赖 = 改 requirements + 重 build,两者不分家 |
| 部署完生产返的还是旧值 | buildx 复用了旧 `COPY backend/` 层(stale cache) | 部署脚本里先 grep 镜像内代码验证,没命中才 `--no-cache` |

### 7.7 Docker 在这个项目里的边界(别过度想象)

- 它**只干一件事**:把后端打包运上 Azure
- 本地开发**不用 Docker**:直接 `python -m uvicorn`(CLAUDE.md 的启动命令)+ 本机 postgres
- **数据库永远不在容器里**(Supabase 托管,跨公司)
- 小程序、未来的 iOS,和 Docker 完全无关

**自测**:①image 和 container 的区别一句话;②buildx 为什么要 `--platform linux/amd64`;③改了 `frontend/css` 要不要重新 build?为什么?④回滚具体是哪两步?⑤为什么部署后不能只看 health 200?

---

## 附录 C · 部署六坑速查(提炼自 deploy-azure skill)

| # | 坑 | 一句话修法 |
|---|-----|-----------|
| 1 | container set 少带凭证 → 拉镜像 401 | 四参一起带(image/url/user/password) |
| 2 | 本地 VPN 挡 6543 → seed 连不上 | 灌库改走 REST 443 |
| 3 | az CLI 走 VPN 代理写操作 503 | 重试 2-3 发;死磕不过换节点/热点 |
| 4 | health 200 是旧容器 | 用本次改动会变的端点验证 |
| 5 | buildx 复用旧 COPY 层 | 先 grep 镜像内新代码,没命中才 --no-cache |
| 6 | DDL 注释带分号 → init_db 崩 503 | 注释永远无分号无引号 |

---

*本篇是主手册第 2/4/5 讲的钻取篇,权威源在 repo `docs/ops/`;结构变更先改 repo 再同步 wiki。*
