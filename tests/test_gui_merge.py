import os
import unittest
from unittest.mock import MagicMock
from arqparse.ui.gui import GuiApp
import tempfile
import shutil

class TestMergeVPNConfigs(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.app = GuiApp()
        self.app.RESULTS_DIR = self.test_dir
        # Мокаем метод логирования, чтобы не было ошибок
        self.app._log = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_merge_preserves_old_data_on_empty_update(self):
        out_file = os.path.join(self.test_dir, "all_top_vpn.txt")
        
        # 1. Создаем старый файл с данными
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write("#profile-update-interval: 48\n#support-url: http://t.me/arq\n\n")
            f.write("# SECTION: Base VPN\ncfg_base_1\n")
            f.write("# SECTION: Bypass VPN\ncfg_bypass_1\n")
        
        # 2. Создаем обновленный Base VPN, но пустой Bypass VPN
        base_file = os.path.join(self.test_dir, "top_base_vpn.txt")
        bypass_file = os.path.join(self.test_dir, "top_bypass_vpn.txt")
        
        with open(base_file, 'w', encoding='utf-8') as f:
            f.write("new_base_cfg\n")
        # Bypass файл пуст или не существует (здесь не создаем)
        
        # 3. Запускаем слияние
        self.app.merge_vpn_configs()
        
        # 4. Проверяем
        with open(out_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        self.assertIn("new_base_cfg", content)
        self.assertIn("cfg_bypass_1", content) # Старый обход сохранился!
        self.assertIn("# SECTION: Base VPN", content)
        self.assertIn("# SECTION: Bypass VPN", content)

if __name__ == '__main__':
    unittest.main()
