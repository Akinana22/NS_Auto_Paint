"""
配置管理器 - 通用配置管理模块 v2.2.0
支持按功能类型管理用户配置，支持默认配置 fallback，提供原子操作。
目录结构：
conf/
├── default/                      # 预置默认配置（开发时放入）
│   ├── color_curve_default.json
│   └── key_mapping_default.json
├── color_curve/                  # 调色曲线配置
│   ├── manifest.json
│   ├── cfg_001.json
│   └── ...
├── key_mapping/                  # 按键映射配置
│   ├── manifest.json
│   └── ...
└── app_state.json                # 应用状态（窗口大小等，可选）
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path
from core.utils.logger import get_logger
from core.utils.resource import resource_path

logger = get_logger("ConfigManager")


class ConfigManager:
    """配置管理器单例"""

    _instances = {}

    def __new__(cls, config_type: str, base_dir: str = "conf"):
        if config_type not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[config_type] = instance
        return cls._instances[config_type]

    def __init__(self, config_type: str, base_dir: str = "conf"):
        if self._initialized:
            return

        self.config_type = config_type
        # 将相对路径转换为打包安全的绝对路径
        self.base_dir = Path(resource_path(base_dir))
        self.config_dir = self.base_dir / config_type
        self.default_dir = self.base_dir / "default"
        self.manifest_path = self.config_dir / "manifest.json"
        self._initialized = True
        self._ensure_dirs()
        self._ensure_manifest()

    def _ensure_dirs(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.default_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_manifest(self):
        if not self.manifest_path.exists():
            self._write_manifest({"active": None, "mappings": {}})

    def _read_manifest(self) -> Dict:
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"active": None, "mappings": {}}

    def _write_manifest(self, data: Dict):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_next_filename(self) -> str:
        existing = list(self.config_dir.glob("cfg_*.json"))
        if not existing:
            return "cfg_001.json"
        numbers = []
        for p in existing:
            try:
                num = int(p.stem.split("_")[1])
                numbers.append(num)
            except:
                continue
        next_num = max(numbers) + 1
        return f"cfg_{next_num:03d}.json"

    def _validate_config_name(self, name: str) -> bool:
        """配置名不能为空，不能包含特殊字符，不能为 'default'（忽略大小写）"""
        if not name or not name.strip():
            return False
        if name.lower() == "default":
            return False
        forbidden = r'\/:*?"<>|'
        if any(c in name for c in forbidden):
            return False
        return True

    # ---------- 公开接口 ----------
    def list_configs(self) -> List[Dict[str, str]]:
        manifest = self._read_manifest()
        mappings = manifest.get("mappings", {})
        result = []
        for name, filename in mappings.items():
            if (self.config_dir / filename).exists():
                result.append({"name": name, "filename": filename})
        return result

    def get_active_config(self) -> Optional[Dict[str, Any]]:
        manifest = self._read_manifest()
        active_filename = manifest.get("active")
        if active_filename:
            filepath = self.config_dir / active_filename
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    name = None
                    for n, fn in manifest.get("mappings", {}).items():
                        if fn == active_filename:
                            name = n
                            break
                    return {
                        "name": name or "未知",
                        "data": data,
                        "filename": active_filename,
                    }
                except Exception as e:
                    logger.error(f"读取配置文件失败 {active_filename}: {e}")
        default_file = self.default_dir / f"{self.config_type}_default.json"
        if default_file.exists():
            try:
                with open(default_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {"name": "default", "data": data, "filename": None}
            except Exception as e:
                logger.error(f"读取默认配置失败 {default_file}: {e}")
        return {"name": "default", "data": {}, "filename": None}

    def set_active_config(self, filename: str) -> bool:
        manifest = self._read_manifest()
        manifest["active"] = filename
        self._write_manifest(manifest)
        return True

    def create_config(self, name: str, data: Dict) -> Optional[str]:
        if not self._validate_config_name(name):
            logger.warning(
                f"无效的配置名: {name}（不能为空、包含特殊字符或为 'default'）"
            )
            return None
        manifest = self._read_manifest()
        mappings = manifest.get("mappings", {})
        if name in mappings:
            logger.warning(f"配置名已存在: {name}")
            return None
        filename = self._get_next_filename()
        filepath = self.config_dir / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配置文件失败 {filename}: {e}")
            return None
        mappings[name] = filename
        manifest["mappings"] = mappings
        self._write_manifest(manifest)
        return filename

    def update_config(self, filename: str, data: Dict) -> bool:
        filepath = self.config_dir / filename
        if not filepath.exists():
            logger.error(f"配置文件不存在: {filename}")
            return False
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"更新配置文件失败 {filename}: {e}")
            return False

    def rename_config(self, old_name: str, new_name: str) -> bool:
        if not self._validate_config_name(new_name):
            logger.warning(f"无效的新配置名: {new_name}")
            return False
        manifest = self._read_manifest()
        mappings = manifest.get("mappings", {})
        if old_name not in mappings:
            return False
        if new_name in mappings and new_name != old_name:
            return False
        filename = mappings.pop(old_name)
        mappings[new_name] = filename
        manifest["mappings"] = mappings
        self._write_manifest(manifest)
        return True

    def delete_config(self, name: str) -> bool:
        manifest = self._read_manifest()
        mappings = manifest.get("mappings", {})
        if name not in mappings:
            return False
        filename = mappings[name]
        filepath = self.config_dir / filename
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception as e:
                logger.error(f"删除配置文件失败 {filename}: {e}")
                return False
        del mappings[name]
        manifest["mappings"] = mappings
        if manifest.get("active") == filename:
            manifest["active"] = None
        self._write_manifest(manifest)
        return True

    def get_config_data_by_filename(self, filename: str) -> Optional[Dict]:
        filepath = self.config_dir / filename
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取配置失败 {filename}: {e}")
            return None

    def get_default_config_data(self) -> Dict:
        default_file = self.default_dir / f"{self.config_type}_default.json"
        if default_file.exists():
            try:
                with open(default_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取默认配置失败 {default_file}: {e}")
        return {}

    def restore_default(self) -> bool:
        manifest = self._read_manifest()
        manifest["active"] = None
        self._write_manifest(manifest)
        return True

    def get_current_config_display_name(self) -> str:
        active = self.get_active_config()
        return active.get("name", "default")
