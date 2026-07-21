"""
ffmpeg 自动安装脚本

功能：
    1. 检测系统中是否已安装 ffmpeg
    2. 如果未安装，下载并解压到项目目录（非C盘）
    3. 将 ffmpeg 的 bin 目录添加到系统 PATH
    4. 验证安装是否成功
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil


def is_ffmpeg_installed() -> bool:
    """检测 ffmpeg 是否已安装"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and "ffmpeg version" in result.stdout:
            print(f"✓ ffmpeg 已安装: {result.stdout.splitlines()[0]}")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"检测 ffmpeg 失败: {e}")
    
    print("✗ ffmpeg 未安装或未添加到 PATH")
    return False


def get_ffmpeg_download_url() -> str:
    """获取 ffmpeg 下载地址"""
    return "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-full_build.zip"


def download_ffmpeg(download_path: str) -> str:
    """下载 ffmpeg"""
    url = get_ffmpeg_download_url()
    print(f"\n正在下载 ffmpeg: {url}")
    
    try:
        urllib.request.urlretrieve(url, download_path)
        print(f"✓ 下载完成: {download_path}")
        return download_path
    except Exception as e:
        print(f"✗ 下载失败: {e}")
        raise


def extract_ffmpeg(zip_path: str, extract_dir: str) -> str:
    """解压 ffmpeg"""
    print(f"\n正在解压 ffmpeg 到: {extract_dir}")
    
    os.makedirs(extract_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
            print("✓ 解压完成")
        
        zip_name = os.path.splitext(os.path.basename(zip_path))[0]
        extracted_dir = os.path.join(extract_dir, zip_name)
        
        if os.path.exists(extracted_dir):
            return extracted_dir
        
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path) and "ffmpeg" in item.lower():
                return item_path
        
        raise RuntimeError("未找到解压后的 ffmpeg 目录")
        
    except Exception as e:
        print(f"✗ 解压失败: {e}")
        raise


def add_to_path(bin_dir: str) -> None:
    """将 ffmpeg 的 bin 目录添加到系统 PATH"""
    print(f"\n正在将 ffmpeg 添加到系统 PATH: {bin_dir}")
    
    try:
        import winreg
        
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
        )
        
        path_value, _ = winreg.QueryValueEx(key, "Path")
        
        if bin_dir not in path_value:
            new_path = f"{path_value};{bin_dir}"
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            print("✓ 已添加到用户 PATH")
        else:
            print("✓ ffmpeg 已在 PATH 中")
        
        winreg.CloseKey(key)
        
        subprocess.run(
            ["setx", "PATH", f"%PATH%;{bin_dir}"],
            capture_output=True,
            text=True
        )
        
        os.environ["PATH"] = f"{os.environ['PATH']};{bin_dir}"
        
        print("✓ 当前进程 PATH 已更新")
        
    except Exception as e:
        print(f"✗ 添加到 PATH 失败: {e}")
        print(f"请手动将以下路径添加到系统 PATH:")
        print(f"  {bin_dir}")


def verify_installation() -> bool:
    """验证 ffmpeg 安装是否成功"""
    print("\n" + "=" * 60)
    print("验证安装")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and "ffmpeg version" in result.stdout:
            print("✓ ffmpeg 安装成功！")
            print(f"\n版本信息:")
            print(result.stdout.splitlines()[0])
            return True
        else:
            print("✗ ffmpeg 验证失败")
            print(f"错误信息: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("✗ ffmpeg 仍未找到，请重启终端或手动添加 PATH")
        return False
    except Exception as e:
        print(f"✗ 验证异常: {e}")
        return False


def main() -> None:
    """主函数"""
    print("=" * 60)
    print("ffmpeg 自动安装脚本")
    print("=" * 60)
    
    if is_ffmpeg_installed():
        print("\nffmpeg 已安装，无需重复安装")
        sys.exit(0)
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    install_parent_dir = os.path.join(project_root, "bin")
    zip_path = os.path.join(install_parent_dir, "ffmpeg.zip")
    
    print(f"\n安装目录: {install_parent_dir}")
    print(f"下载路径: {zip_path}")
    
    os.makedirs(install_parent_dir, exist_ok=True)
    
    try:
        if not os.path.exists(zip_path):
            download_ffmpeg(zip_path)
        
        extracted_dir = extract_ffmpeg(zip_path, install_parent_dir)
        
        os.remove(zip_path)
        print("✓ 临时文件已删除")
        
        bin_dir = os.path.join(extracted_dir, "bin")
        ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")
        
        if not os.path.exists(ffmpeg_exe):
            raise RuntimeError(f"ffmpeg.exe 不存在于: {bin_dir}")
        
        print(f"✓ ffmpeg.exe 路径: {ffmpeg_exe}")
        
        add_to_path(bin_dir)
        
        if verify_installation():
            print("\n" + "=" * 60)
            print("安装完成！")
            print("=" * 60)
            print(f"\nffmpeg 安装路径: {extracted_dir}")
            print(f"bin 目录: {bin_dir}")
            print("\n提示: 如果当前终端仍无法使用 ffmpeg，请重启终端")
        else:
            print("\n安装未完全成功，请手动检查")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n安装失败: {e}")
        import traceback
        traceback.print_exc()
        
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print("✓ 已清理临时文件")
        
        sys.exit(1)


if __name__ == "__main__":
    main()
