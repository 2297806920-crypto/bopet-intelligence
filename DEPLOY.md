# 上传并发布 BOPET Intelligence

本文按“最省事”的顺序写。推荐先用 **Streamlit Community Cloud** 发布一个可访问网址，不需要买服务器。

## 0. 先选发布方式

| 方式 | 适合 | 费用 | 备注 |
|---|---|---|---|
| Streamlit Community Cloud | 答辩/演示/内部试用 | 免费 | 需要 GitHub；公开或私有仓库均可 |
| 公司服务器 / VPS | 长期运行、内网 | 服务器费用 | 需要端口、反向代理、HTTPS |
| Docker | 运维交付 | 服务器费用 | 需要 Docker 基础 |

下面详细写 **Streamlit Community Cloud**。

## 1. 准备一个“干净”的部署目录

不要直接把整个项目根目录上传。项目里的 `outputs/` 约 **2.8 GB**，包含大量实验中间结果；` .venv/` 约 **302 MB**，是本地虚拟环境。二者都不能上传。

我已经生成了一个最小部署包：

```text
deploy/
```

也可以用压缩包：

```text
BOPET_Intelligence_Deploy.zip
```

部署包只包含：

- `streamlit_app.py`、`config.py`、`qa_agent.py`、`plan_agent.py` 等入口；
- `agents/ core/ evaluators/ optimizers/ scenarios/ services/ tools/ ui/`；
- `assets/`、`.streamlit/config.toml`；
- `data/database/bopet.db`（约 1.9 MB，文献只读库）；
- `data/constraints/`；
- 少量真实实验摘要，用于验证页和 demo 回放；
- `requirements.txt`。

不包含：

- `.venv/`
- 2.8 GB 的 `outputs/` 全量结果
- 本地备份、zip、截图、著作权材料
- 任何 API Key

## 2. 上传到 GitHub

### 2.1 创建仓库

1. 登录 GitHub。
2. 右上角 `+` → `New repository`。
3. 名称例如 `bopet-intelligence`。
4. 选择 `Private` 或 `Public`。
5. 不要勾选自动生成 README（部署包已有文件）。
6. 点击 `Create repository`。

### 2.2 用 GitHub Desktop 上传（推荐给不熟 Git 的人）

1. 安装 GitHub Desktop，登录账号。
2. `File` → `Add local repository`。
3. 选择：

```text
C:\Users\22978\Desktop\bopet_agent_loop_starter\deploy
```

4. 如果提示不是 Git 仓库，点 `create a repository`。
5. 提交信息填 `BOPET Intelligence V3.0 UI`。
6. 点 `Commit to main`。
7. 点 `Publish repository`，选择刚才的仓库。
8. 如果仓库设为 Private，保持 Private 即可。

### 2.3 或用命令行

```powershell
cd C:\Users\22978\Desktop\bopet_agent_loop_starter\deploy

git init
git add .
git commit -m "BOPET Intelligence V3.0 UI"
git branch -M main
git remote add origin https://github.com/你的用户名/bopet-intelligence.git
git push -u origin main
```

> 如果 `git push` 要求登录，使用 GitHub 的 Personal Access Token，不要用账号密码。

### 2.4 上传前检查

确认仓库里 **没有**：

```text
.venv/
outputs/          # 只保留部署包里的少量摘要，不要上传全量
.streamlit/secrets.toml
*.zip
```

确认仓库里 **有**：

```text
streamlit_app.py
requirements.txt
data/database/bopet.db
ui/
assets/
.streamlit/config.toml
```

## 3. 在 Streamlit Community Cloud 部署

1. 打开 https://share.streamlit.io/
2. 用 GitHub 登录。
3. 点 `Create app` / `New app`。
4. 选择：
   - Repository：你的 `bopet-intelligence`
   - Branch：`main`
   - Main file path：`streamlit_app.py`
   - Python version：优先选 **3.12**。如果平台只提供 3.13，也可以选 3.13。
5. 点 `Deploy`。
6. 第一次构建会安装 `requirements.txt`，通常需要 1–3 分钟。

成功后地址类似：

```text
https://bopet-intelligence.streamlit.app
```

这个地址就可以发给评委或同事。

## 4. 配置 API（可选）

不配置 API 也可以运行：系统自动使用规则模式，所有页面都能打开。

如果要接书生/InternLM：

1. 进入 Streamlit Cloud 的 app 页面。
2. 右上角 `Settings` → `Secrets`。
3. 填：

```toml
LLM_PROVIDER = "internlm"
LLM_BASE_URL = "https://discovery-api.intern-ai.org.cn/v1"
LLM_MODEL = "你的完整模型名"
LLM_API_KEY = "你的有效Key"
```

4. 保存后 app 会自动重启。

**不要把 Key 写进 `streamlit_app.py`，不要提交 `.streamlit/secrets.toml`。**

本项目支持从 Streamlit Secrets 读取这些值；没有 Key 时不会报错，只是 API 状态显示未配置。

## 5. 部署后检查

打开网址，依次检查：

- 侧边栏 8 个页面是否能切换；
- 系统总览的数字是否来自数据库；
- 证据知识库是否能检索；
- 数理约束表是否能显示；
- 智能优化点击运行是否能完成；
- 多维评价是否有四个区域；
- 实验验证是否有结果；
- 工程审核是否能打开；
- 系统设置是否显示 Database connected；
- 无 API Key 时是否仍能运行。

## 6. 常见问题

### `ModuleNotFoundError`

确认仓库根目录有 `requirements.txt`，且 Cloud 的 Main file path 是 `streamlit_app.py`。

### 数据库找不到

确认仓库里有：

```text
data/database/bopet.db
```

不要只上传代码目录。

### 页面打开但实验验证为空

部署包只带了实验摘要。全量 `outputs/` 不应上传；验证页显示空状态是正常的。若要完整曲线，需要单独上传 `outputs/v31_experiments/runs/` 中少量需要的运行目录。

### app 休眠

Community Cloud 长时间无人访问会休眠；再次打开会自动唤醒。答辩前提前打开一次。

### API 401

Key 无效、过期或复制不完整。到书生控制台重新创建并更新 Secrets，不要在页面里明文粘贴。

### 想用公司服务器

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

然后用 Nginx/Caddy 做 HTTPS 反向代理；不要直接把 8501 暴露到公网。

## 7. 数据与合规

- `bopet.db` 来自文献 PDF 抽取；公开部署前确认文献再分发权限。
- 页面里出现的本地 PDF 路径只是字符串，不会上传 PDF 文件。
- 生产/经济数字是 `SCENARIO_ESTIMATION`，不是现场实测。
- 不连接 PLC/MES；工程审核页是本地演示。
- 不要把真实 API Key、客户数据、现场数据放进公开仓库。
