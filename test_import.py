import chroma_hnswlib
import hnswlib

try:
    print("chroma_hnswlib 导入成功")
except ImportError:
    print("chroma_hnswlib 导入失败")

try:
    print("hnswlib 导入成功")
    print("hnswlib 可用属性：", dir(hnswlib))  # 这里不会再调用 `__version__`
except ImportError:
    print("hnswlib 导入失败")
