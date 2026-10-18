#!/bin/bash
set -euo pipefail
package_root="$(cd "$(dirname "$0")" && pwd)"
suite_python="${HS_SUITE_PYTHON:-$HOME/miniconda3/bin/python3}"
if [[ ! -x "$suite_python" ]]; then
  echo "没有找到现有 Python。此自用安装包不附带 Python。"
  echo "默认使用 ~/miniconda3/bin/python3，也可用 HS_SUITE_PYTHON 指定。"
  exit 1
fi
exec "$suite_python" "$package_root/install.py" --install
