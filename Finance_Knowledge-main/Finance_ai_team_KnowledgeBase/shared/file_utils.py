"""文件工具模块。

提供文件读写、遍历、编码检测辅助函数。
"""

from pathlib import Path
from typing import Union


def list_txt_files(directory: Union[str, Path]) -> list[Path]:
    """列出目录下所有 .txt 文件。

    Args:
        directory: 目标目录路径。

    Returns:
        排序后的 .txt 文件路径列表。
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"路径不存在或不是目录: {directory}")

    files = sorted(dir_path.glob("*.txt"))
    return files


def ensure_output_dir(directory: Union[str, Path]) -> Path:
    """确保输出目录存在，不存在则创建。

    Args:
        directory: 目录路径。

    Returns:
        Path 对象。
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def read_file_bytes(path: Union[str, Path]) -> bytes:
    """以二进制方式读取文件。

    Args:
        path: 文件路径。

    Returns:
        文件内容的字节数据。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return file_path.read_bytes()


def write_text_file(path: Union[str, Path], content: str, encoding: str = "utf-8") -> None:
    """以指定编码写入文本文件。

    Args:
        path: 输出文件路径。
        content: 文本内容。
        encoding: 目标编码。
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding=encoding)


def make_output_path(input_path: Union[str, Path], output_dir: Union[str, Path]) -> Path:
    """根据输入文件路径生成对应的输出路径（.txt → .md）。

    Args:
        input_path: 输入文件路径。
        output_dir: 输出目录。

    Returns:
        输出 .md 文件路径。
    """
    input_name = Path(input_path).stem
    output_dir = Path(output_dir)
    return output_dir / f"{input_name}.md"
