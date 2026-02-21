# PDF解析解决方案

针对研究型智能代理项目中PDF解析经常报错的问题，以下是几种好用的免费且轻量的解决方案：

## 1. PyMuPDF (fitz) - 推荐

PyMuPDF是一个非常高效且功能丰富的PDF处理库：

```python
import fitz  # PyMuPDF

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

# 也可以提取特定页面
def extract_text_from_page(pdf_path, page_num):
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    text = page.get_text()
    doc.close()
    return text
```

**优点：**
- 解析速度快
- 支持加密PDF
- 支持图像提取
- 内存占用相对较低
- 支持多种文档格式（PDF, XPS, EPUB等）

## 2. pdfplumber

基于pdfminer.six构建，接口更友好：

```python
import pdfplumber

def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""  # 处理可能的None值
    return text
```

**优点：**
- 更友好的API
- 能够提取表格数据
- 处理布局信息较好
- 相对稳定

## 3. pymupdf-rw (另一个PyMuPDF变体)

```python
import pymupdf as fitz  # 另一种导入方式

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text
```

## 4. pypdf (原PyPDF2)

pypdf是PyPDF2的现代化分支：

```python
from pypdf import PdfReader

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text
```

**优点：**
- 轻量级
- 纯Python实现
- 维护活跃

## 5. 综合解决方案示例

为了提高稳定性，可以结合多种方案：

```python
def robust_pdf_extract(pdf_path):
    """尝试多种PDF解析方法"""
    
    # 方法1: PyMuPDF
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if text.strip():
            return text
    except Exception as e:
        print(f"PyMuPDF failed: {e}")
    
    # 方法2: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        if text.strip():
            return text
    except Exception as e:
        print(f"pdfplumber failed: {e}")
    
    # 方法3: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        if text.strip():
            return text
    except Exception as e:
        print(f"pypdf failed: {e}")
    
    return "PDF解析失败: 无法提取文本内容"
```

## 推荐安装命令

```bash
# 推荐组合
pip install PyMuPDF pdfplumber pypdf

# 或者只安装最推荐的
pip install PyMuPDF
```

## 针对项目的建议

对于研究代理项目，建议：

1. **首选 PyMuPDF** - 性能最好，功能最全面
2. **添加异常处理** - 对各种PDF格式错误进行捕获
3. **实现降级策略** - 当一种方法失败时自动尝试其他方法
4. **预处理检查** - 检查PDF是否损坏或受保护

PyMuPDF是最推荐的选择，因为它不仅速度快、功能强，而且对各种PDF格式的兼容性也很好，同时内存占用相对可控。