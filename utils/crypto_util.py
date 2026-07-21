"""
加解密模块

提供配置文件加密解密功能，保护敏感密钥。

功能特性：
    1. AES 对称加密
    2. 配置文件加密存储
    3. 安全的密钥管理
"""

import os
import json
import base64
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from utils.path_helper import get_secret_config_path
from utils.logger import get_error_logger


logger = get_error_logger()


class CryptoUtil:
    """
    加密工具类
    
    使用 Fernet 进行 AES 对称加密。
    """
    
    def __init__(self, key: Optional[bytes] = None) -> None:
        """
        初始化加密工具
        
        Args:
            key: 加密密钥，如果为 None 则使用默认密钥
        """
        if key is None:
            key = self._generate_default_key()
        
        self._fernet = Fernet(key)
    
    def _generate_default_key(self) -> bytes:
        """生成默认密钥（基于机器特征）"""
        try:
            import platform
            import hashlib
            
            machine_id = platform.node() + os.path.expanduser("~")
            seed = hashlib.sha256(machine_id.encode()).digest()
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"multilang_video_crawler",
                iterations=100000,
                backend=default_backend()
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(seed))
            return key
        except Exception:
            return Fernet.generate_key()
    
    def encrypt(self, data: str) -> str:
        """
        加密字符串
        
        Args:
            data: 待加密的字符串
            
        Returns:
            加密后的字符串
        """
        try:
            encrypted = self._fernet.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise
    
    def decrypt(self, data: str) -> str:
        """
        解密字符串
        
        Args:
            data: 待解密的字符串
            
        Returns:
            解密后的字符串
        """
        try:
            decrypted = self._fernet.decrypt(data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise
    
    def encrypt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        加密文件
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径，如果为 None 则在原路径后加 .enc 后缀
            
        Returns:
            输出文件路径
        """
        if output_path is None:
            output_path = input_path + ".enc"
        
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            encrypted = self.encrypt(content)
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(encrypted)
            
            logger.info(f"文件已加密: {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"加密文件失败: {e}")
            raise
    
    def decrypt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        解密文件
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径，如果为 None 则去掉 .enc 后缀
            
        Returns:
            输出文件路径
        """
        if output_path is None:
            if input_path.endswith(".enc"):
                output_path = input_path[:-4]
            else:
                output_path = input_path + ".decrypted"
        
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            decrypted = self.decrypt(content)
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(decrypted)
            
            logger.info(f"文件已解密: {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"解密文件失败: {e}")
            raise
    
    def load_secret_config(self) -> Dict[str, Any]:
        """
        加载加密的密钥配置文件
        
        Returns:
            解密后的配置字典
        """
        secret_path = get_secret_config_path()
        
        if not os.path.exists(secret_path):
            logger.warning(f"密钥配置文件不存在: {secret_path}")
            return {}
        
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            decrypted = self.decrypt(content)
            return json.loads(decrypted)
        
        except Exception as e:
            logger.error(f"加载密钥配置文件失败: {e}")
            return {}
    
    def save_secret_config(self, config: Dict[str, Any]) -> None:
        """
        保存加密的密钥配置文件
        
        Args:
            config: 配置字典
        """
        secret_path = get_secret_config_path()
        
        try:
            content = json.dumps(config, ensure_ascii=False, indent=2)
            encrypted = self.encrypt(content)
            
            with open(secret_path, "w", encoding="utf-8") as f:
                f.write(encrypted)
            
            logger.info(f"密钥配置文件已保存: {secret_path}")
        
        except Exception as e:
            logger.error(f"保存密钥配置文件失败: {e}")
            raise


# 便捷函数
_crypto_util: Optional[CryptoUtil] = None


def get_crypto_util() -> CryptoUtil:
    """获取加密工具实例（单例）"""
    global _crypto_util
    if _crypto_util is None:
        _crypto_util = CryptoUtil()
    return _crypto_util


def encrypt(data: str) -> str:
    """
    便捷函数：加密字符串
    
    Args:
        data: 待加密的字符串
        
    Returns:
        加密后的字符串
    """
    return get_crypto_util().encrypt(data)


def decrypt(data: str) -> str:
    """
    便捷函数：解密字符串
    
    Args:
        data: 待解密的字符串
        
    Returns:
        解密后的字符串
    """
    return get_crypto_util().decrypt(data)


def load_secret_config() -> Dict[str, Any]:
    """
    便捷函数：加载加密的密钥配置文件
    
    Returns:
        解密后的配置字典
    """
    return get_crypto_util().load_secret_config()


def save_secret_config(config: Dict[str, Any]) -> None:
    """
    便捷函数：保存加密的密钥配置文件
    
    Args:
        config: 配置字典
    """
    get_crypto_util().save_secret_config(config)


def init_crypto_util(key: Optional[bytes] = None) -> None:
    """
    初始化加密工具
    
    Args:
        key: 加密密钥
    """
    global _crypto_util
    _crypto_util = CryptoUtil(key)
