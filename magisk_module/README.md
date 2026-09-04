# QuantumROM SM-P613 Camera & Video Fix Module

This module replaces the ported Exynos/unpatched system libraries with the Qualcomm-compatible patched binaries:

## Directory Mapping

```
system/
├── lib64/
│   ├── libcore2nativeutil.camera.samsung.so   <-- Fixes Photo/Video preview black screen (Forces QCOM vendor = 2)
│   └── libstagefright.so                     <-- Fixes Video mode freeze & mediaserver FORTIFY crash (fread count = 255)
└── lib/
    ├── libcore2nativeutil.camera.samsung.so   <-- 32-bit preview fix
    └── libstagefright.so                     <-- 32-bit video recording fix
```

When building QuantumROM directly into `system.img`, copy these files into the corresponding paths inside the extracted system root:
- `system/system/lib64/...`
- `system/system/lib/...`
