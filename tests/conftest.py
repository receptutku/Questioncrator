from __future__ import annotations

import os

# Test paketinin geneli süreç içi çalışır (hız). Sandbox testleri kendi
# içinde `process` kipini açıkça seçer.
os.environ.setdefault("QC_SANDBOX", "inline")
