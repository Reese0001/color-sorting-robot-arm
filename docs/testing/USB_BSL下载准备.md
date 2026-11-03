# USB 下载与复测 — 2026-11-03

当前板子已经烧录成功，不需要再次烧录。`robot bench v2.1` 的完整 16KiB CRC 为 `9F28C009`，16 个 1KiB 分段也全部匹配，应用串口及红/绿/蓝三条七步模拟路线通过。

## 日常使用

保持电脑 USB 接核心板 USB-C，COM8 / 115200 / 8N1。正常运行不按 BSL；需要重启时只按 RST。

- 双击 `tools/烧录后检查串口.bat`：看到 PONG 和 PASS 表示收发正常。
- 双击 `tools/板端三色流程自检_不动舵机.bat`：约 25 秒，红左、绿中、蓝右各显示一次 PASS。
- 双击 `tools/打开COM8串口查看.bat`：只查看每秒状态。关闭此窗口后才能运行其他串口工具。

当前 `motion=0 armed=0 bus=0`，三色流程是板上模拟，不带动机械臂。K230 未连接时 `online=0 target=NONE` 正常。

## 只有需要重新下载时

1. 关闭所有串口查看和测试窗口，保持只接主控 USB。
2. 双击 `tools/USB直接烧录_自动等待BSL.bat`。
3. 看到 `READY_AUTO_BSL` 后：按住核心板 BSL → 短按并松开 RST → 等 1 秒 → 松开 BSL。不用回车，不用切窗口。
4. 脚本只擦写 MAIN 的 `0x00000000..0x00003FFF`，128 字节分包；完整 CRC 匹配后才发启动命令。
5. 成功须见 `MAIN_PROGRAM_AND_CRC_VERIFIED` 和 `START_APPLICATION_ACK`，再运行串口检查。程序退出码或电源灯本身不能代替这些结果。

本次遇到一次“全部写完但即时 CRC 不一致”：工具中止且没有启动。重新按 BSL/RST 进入 BSL 后，只读核验得到全部正确 CRC，未重新擦写。原因尚未确定，不能把所有 CRC 错误都当成可忽略。

如果再次遇到这一情况，保留日志；可以双击 `tools/只校验并启动_不重写.bat`，等 READY 后按 BSL/RST。这个入口只核验既有 MAIN，CRC 不匹配仍会中止，匹配才启动。若中途写入失败，需完整重写，不能把部分成功当作全片成功。

## 固件与下载保护

- 固件：`firmware/keil/Objects/robot_mspm0.hex`，16312 个有效字节，补 FF 到 16384 字节。
- SHA256：`ce9a961c87d8072bd5d9ca1b0bbc80120e5738a781326dabd1291ff385fc671d`。
- 自建 Python/.NET 工具 `bsl_direct.py` 依据 TI 协议编写，不是 TI 官方成品下载工具。BSL 使用 9600 / 8N1，应用使用 115200 / 8N1。
- 已核实本板接受默认 32 字节 FF 密码。工具记录解锁状态，拒绝连续尝试不确定或被拒绝的密码。不要删除 `auth_state.json` 绕过限制。
- 不使用 Factory Reset、Mass Erase，不写 NONMAIN/BCR/BSL。重新编译后先审查地址、向量、输出开关，再更新批准的固件哈希。
- 当前 CH340 使用 3.3.2011.11，原 3.9.2024.9 备份在 `tools/driver_recovery/original_3_9`。暂保持已验证组合；如需恢复，用该目录上一级的 `switch_ch340.ps1 -Mode Restore`（管理员），不能把切换驱动等同于必然修复。

TI UniFlash/DSS 和 ST-Link/OpenOCD 的旧入口保留作排查备用，本次成功来自上述自建 USB BSL 工具。Keil 继续负责编译，不能把 CH340 选成 Keil 调试器直接 Load。

完整实测：[11 月 3 日记录](2026-11-03恢复烧录记录.md)。协议依据：[TI SLAU887A](https://www.ti.com/lit/ug/slau887a/slau887a.pdf)。
