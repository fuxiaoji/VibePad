"""更新 GitHub 仓库 About 和 Topics。需先创建 Personal Access Token。

步骤:
    1. 打开 https://github.com/settings/tokens/new
    2. Note 填 "controller-repo-meta", Expiration 选 Custom → 30天
    3. 勾选 "Repository access" 下 Write 权限 (或直接勾 repo scope)
    4. 点击 Generate token, 复制令牌
    5. 运行: python update_repo_meta.py <你的token>
"""
import sys, json, urllib.request

OWNER = "fuxiaoji"
REPO = "controller"

DESCRIPTION = (
    "🎮 手柄操控电脑 | Vibe Coding + Copilot/Claude Code 快捷键映射 | "
    "Switch 风格三级焦点导航 | Gamepad-to-Keyboard/Mouse with UIA Focus Navigation"
)

TOPICS = [
    "vibecoding", "vibe-coding", "gamepad", "controller",
    "gamepad-to-keyboard", "spatial-navigation", "uiautomation",
    "copilot", "claude-code", "windows", "win32",
    "bilibili", "accessibility", "python", "productivity"
]

HOMEPAGE = "https://github.com/fuxiaoji/controller"

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

token = sys.argv[1]
url = f"https://api.github.com/repos/{OWNER}/{REPO}"

data = json.dumps({
    "description": DESCRIPTION,
    "homepage": HOMEPAGE,
    "topics": TOPICS,
    "has_wiki": False,
}).encode()

req = urllib.request.Request(url, data=data, method="PATCH")
req.add_header("Accept", "application/vnd.github+json")
req.add_header("Authorization", f"Bearer {token}")
req.add_header("User-Agent", "controller-cli")
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"✓ 仓库已更新")
        print(f"  Description: {result.get('description', 'N/A')[:80]}...")
        print(f"  Topics: {result.get('topics', [])}")
        print(f"  URL: {result.get('html_url')}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"✗ 失败 ({e.code}): {body}")
