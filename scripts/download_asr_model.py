"""
ASR 模型下载脚本

将 faster-whisper 的 small 模型下载到项目内部 models/asr/ 目录，
避免依赖系统缓存目录，方便打包和迁移。

用法：
    python scripts/download_asr_model.py            # 下载 small 模型（默认）
    python scripts/download_asr_model.py medium      # 下载 medium 模型
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.path_helper import get_asr_model_dir


def download_model(model_size: str = "small") -> None:
    """下载 faster-whisper 模型到项目内部

    Args:
        model_size: 模型大小（tiny/base/small/medium/large）
    """
    model_dir = str(get_asr_model_dir())
    print(f"模型存放目录: {model_dir}")
    print(f"准备下载 faster-whisper {model_size} 模型...")
    print(f"模型大小参考: tiny=39MB, base=74MB, small=244MB, medium=769MB, large=1.5GB")
    print("-" * 60)

    try:
        from faster_whisper import WhisperModel

        # 通过 WhisperModel 构造函数触发模型下载
        # device="cpu" 适合无 GPU 环境
        # compute_type="int8" 在 CPU 上性能最好
        print(f"开始下载 {model_size} 模型（首次下载需要几分钟）...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=model_dir
        )
        print("-" * 60)
        print(f"[成功] {model_size} 模型已下载到: {model_dir}")

        # 列出模型文件
        files = os.listdir(model_dir)
        print(f"模型目录内容: {files}")

        # 测试模型是否可加载
        print("\n验证模型可加载性...")
        del model
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=model_dir
        )
        print("[成功] 模型加载验证通过")
        del model

    except Exception as e:
        print(f"[错误] 模型下载失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    model_size = sys.argv[1] if len(sys.argv) >= 2 else "small"
    if model_size not in ["tiny", "base", "small", "medium", "large"]:
        print(f"[错误] 不支持的模型大小: {model_size}")
        print("可选: tiny / base / small / medium / large")
        sys.exit(1)
    download_model(model_size)
