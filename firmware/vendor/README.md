# Vendor sources

`mspm0_sdk/` contains a minimal source/header subset of the public
[Texas Instruments MSPM0 SDK](https://github.com/TexasInstruments/mspm0-sdk),
commit `20807db79aa17b49f87ab8ec87f6b6d63ee2cb32` (SDK 2.11.00.07).

Files retain their original copyright notices. TI sources use the licenses
identified in `license_mspm0_sdk_2_11_00_07.txt` and
`manifest_mspm0_sdk_2_11_00_07.html`; CMSIS headers contain Arm Apache-2.0 notices.
`SOURCE_MANIFEST.json` records downloaded files and SHA-256 hashes.
No SDK installer or full SysConfig runtime is required to compile this project.

The assembly startup copy in `firmware/keil/` has one deliberate change:
the stack reservation is 2048 bytes instead of 256 bytes. The source original
remains unchanged here. The linker scatter file in `firmware/keil/` is maintained
by this project and excludes the NONMAIN configuration regions.

The separate official Keil DFP 1.3.1 was downloaded from TI and installed in
`C:/Keil_v5/ARM/PACK/TexasInstruments/MSPM0G1X0X_G3X0X_DFP/1.3.1`.
Pack SHA-256: `071bd317fc0f152ded6b2ae594d79c6fc5eb9952370526b4c14ef5b3b9807860`.
Its archive is a local download in `tools/downloads/` and is not checked in.
