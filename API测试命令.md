# Agent API 测试命令

## 完整测试流程

### 1. 关闭已有进程并清理日志

```bash
# 关闭所有python进程并删除日志
taskkill /F /IM python.exe 2>nul
del "E:\Research_Agent\agent_server.log" 2>nul
echo "清理完成"
```

### 2. 启动服务

```bash
cd "E:\Research_Agent"
python -c "import subprocess; subprocess.Popen(['python', 'agent.py'], stdout=open('agent_server.log','w', encoding='utf-8'), stderr=subprocess.STDOUT)"
```

### 3. 测试问题

```bash
python -c "
import requests
import json
url = 'http://localhost:8004/'
headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer test'}
data = {'question': '你的问题'}
resp = requests.post(url, json=data, headers=headers, timeout=700)
result = resp.json()
print(json.dumps(result, ensure_ascii=False))
"
```

### 4. 分析日志

```bash
# 读取最后5000字符
python -c "
import sys
content = open(r'E:\Research_Agent\agent_server.log', encoding='utf-8', errors='replace').read()
sys.stdout.buffer.write(content[-5000:].encode('utf-8'))
"
```

---

## 测试问题

"E:\Research_Agent\validation.jsonl"

---

## 查看日志

```bash
# 实时查看日志
tail -50 "E:\Research_Agent\agent_server.log"

# 或使用Python
python -c "print(open('E:\\Research_Agent\\agent_server.log').read()[-3000:])"
```

## 验证集问题列表

问题位于 `validation.jsonl` 文件中，共10道题。

## 配置说明

- **端口**: 8004
- **Token**: test
- **超时**: 600秒（约10分钟）
- **Max Steps**: 40步

---

## 常见问题处理

### 1. 打印响应时编码错误

Windows 环境下直接 `print(resp.text)` 可能报错：
```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 4726
```

**解决方案**：强制 UTF-8 编码输出

```bash
python -c "
import requests
url = 'http://localhost:8004/'
headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer test'}
data = {'question': '你的问题'}
resp = requests.post(url, json=data, headers=headers, timeout=700)
print(resp.text.encode('utf-8', errors='replace').decode('utf-8'))
"
```

### 2. 读取日志时编码错误

```bash
# 使用 UTF-8 编码读取日志
python -c "print(open(r'E:\Research_Agent\agent_server.log', encoding='utf-8', errors='replace').read()[-5000:])"

# 或分块读取
python -c "
with open(r'E:\Research_Agent\agent_server.log', encoding='utf-8', errors='replace') as f:
    f.seek(0, 2)
    f.seek(max(0, f.tell() - 5000))
    print(f.read())
"
```

### 3. 实时查看日志（Linux/Mac）

```bash
tail -50 "E:\Research_Agent\agent_server.log"
```
