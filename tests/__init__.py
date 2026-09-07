# -*- coding: utf-8 -*-
"""本地测试包标记：防止 site-packages 中第三方 `tests` 包（ultralytics 附带）
遮蔽本目录，导致 `python -m unittest discover -s tests` 导入失败。"""
