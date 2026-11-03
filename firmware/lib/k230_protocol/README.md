# K230 三色协议接收器

纯 C99，只依赖 `stdint.h` / `string.h`，可用于 MSPM0、STM32 或电脑测试；当前工程使用 MSPM0G3507。

1. 初始化串口中断前调用 `K230_Init()`。
2. 接收中断把字节交给 `K230_IRQHandler(byte)`；发现串口错误调用 `K230_RxError()`。
3. 主循环反复调用 `K230_Poll(now_ms)`，再读 `K230_Online()`、`K230_PickTarget()`、`g_vision`。

`g_vision` 只在主循环解析时提交；不要在中断中读它做动作。离线时槽位可保留用于诊断，使用数据前必须检查在线状态。串口/环形缓冲错误导致缓冲丢弃并重新同步。解析规则、范围和坐标含义见 [协议文档](../../../docs/通信协议.md)。

`tests/test_protocols.c` 覆盖错误字段、溢出、原子提交、断线、时间回绕、重新同步、三色选择及总线报文。执行 `tools/test_protocols.ps1` 可在此电脑重跑。
