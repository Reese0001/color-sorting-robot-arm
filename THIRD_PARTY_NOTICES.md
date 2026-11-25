# 第三方来源与许可

`firmware/vendor/mspm0_sdk/` 是 TI MSPM0 SDK 的最小源码子集，版本/提交和原文件 SHA256 记录在 SOURCE_MANIFEST.json。版权和许可原样保留；详见 license_mspm0_sdk_2_11_00_07.txt、manifest_mspm0_sdk_2_11_00_07.html 及源文件头。

`firmware/keil/startup_mspm0g350x_uvision.s` 基于 TI 启动文件，栈预留改为 2048 字节，保留原版权。CMSIS 代码保留 Arm 原始许可。

Keil、CanMV IDE、TI 设备包、Python、GCC、PowerShell 以及可选 pySerial 需按各自许可安装；没有把这些安装程序或系统驱动打包。

项目自有代码的许可见根目录 [LICENSE](LICENSE)。`firmware/g3519_wiring_test/pololu/` 保留 VL53L0X 库及原许可。`build/sdk_overlay/` 中的 TI 头文件保留原版权声明。课堂包中的厂商文档、上位机和参考库按各自许可使用。
