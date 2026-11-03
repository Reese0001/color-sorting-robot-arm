# 第三方来源与许可

`firmware/vendor/mspm0_sdk/` 是 TI MSPM0 SDK 的最小源码子集，版本/提交和原文件 SHA256 记录在 SOURCE_MANIFEST.json。版权和许可原样保留；详见 license_mspm0_sdk_2_11_00_07.txt、manifest_mspm0_sdk_2_11_00_07.html 及源文件头。

`firmware/keil/startup_mspm0g350x_uvision.s` 基于 TI 启动文件，栈预留改为 2048 字节，保留原版权。CMSIS 代码保留 Arm 原始许可。

Keil、CanMV IDE、TI 设备包、Python、GCC、PowerShell 以及可选 pySerial 需按各自许可安装；没有把这些安装程序或系统驱动打包。

项目自有代码尚未单独选择开源许可证，本次没有擅自套用 MIT/GPL。公开仓库之前可按实际需求补充 LICENSE，不能用它覆盖第三方许可证。
